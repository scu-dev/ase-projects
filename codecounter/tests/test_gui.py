import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import sys
import tkinter as tk
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from counter import ScanResult, count_source
from main import CodeCounterApp


class GuiTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent
        self.temporary = TemporaryDirectory(prefix="codecounter-gui-", dir=parent)
        self.root = Path(self.temporary.name).resolve()
        self.assertEqual(self.root.parent, parent)
        self.addCleanup(self.temporary.cleanup)
        self.app = CodeCounterApp(self.root)
        self.app.withdraw()
        self.app.update_idletasks()
        self.addCleanup(self.app.tk.call, self.app.protocol("WM_DELETE_WINDOW"))

    def choose_directory(self, path: Path | None = None) -> None:
        selected = str(path) if path is not None else self.app.directory.get()
        with patch("main.filedialog.askdirectory", return_value=selected):
            self.app.browse_button.invoke()

    def finish(self):
        deadline = monotonic() + 10
        ticks = 0
        while self.app.browse_button.instate(["disabled"]) and monotonic() < deadline:
            self.app.update()
            ticks += 1
            sleep(0.005)
        self.assertFalse(self.app.browse_button.instate(["disabled"]), "Background scan did not complete")
        self.assertGreater(ticks, 0)

    def drop(
        self, data: tuple[str, ...] | str, data_type: str = "CF_HDROP",
        target: tk.Misc | None = None, offered_types: tuple[str, ...] | None = None,
    ) -> str:
        # Exercise the same Tcl dispatch used by Windows OLE drop notifications,
        # including target lookup, data quoting and the registered Python callback.
        widget = str(target if target is not None else self.app.results)
        types = offered_types if offered_types is not None else (data_type,)
        action = self.app.tk.call(
            "tkdnd::olednd::HandleDragEnter", widget, types, ("copy",), (), 0, 0, types,
        )
        self.assertEqual(action, "copy")
        self.assertEqual(self.app.tk.call("tkdnd::olednd::GetDataType", widget, types), data_type)
        return str(self.app.tk.call("tkdnd::olednd::HandleDrop", widget, (), 0, 0, data_type, data))

    def test_choosing_folder_starts_scan_immediately(self) -> None:
        selected = self.root / "中文 文件夹"
        selected.mkdir()
        (selected / "example.c").write_text("int f() {}", encoding="utf-8")
        self.assertEqual(self.app.browse_button.cget("text"), "选择文件夹")
        self.assertFalse(hasattr(self.app, "scan_button"))
        self.choose_directory(selected)
        self.assertEqual(self.app.directory.get(), str(selected))
        self.assertTrue(self.app.browse_button.instate(["disabled"]))
        self.finish()
        row = self.app.results.item(self.app.results.get_children()[0], "values")
        self.assertEqual(row[1:6], ("1", "1", "0", "0", "1"))

    def test_cancelling_folder_selection_keeps_existing_results(self) -> None:
        self.choose_directory()
        self.finish()
        rows = self.app.results.get_children()
        status = self.app.status.get()
        with patch("main.filedialog.askdirectory", return_value=""), patch("main.scan_directory") as scan:
            self.app.browse_button.invoke()
        scan.assert_not_called()
        self.assertEqual(self.app.directory.get(), str(self.root))
        self.assertEqual(self.app.results.get_children(), rows)
        self.assertEqual(self.app.status.get(), status)
        self.assertTrue(self.app.export_html_button.instate(["!disabled"]))

    @unittest.skipUnless(sys.platform == "win32", "Windows native drop dispatch")
    def test_dropping_folder_over_window_controls_starts_scan(self) -> None:
        folder = self.root / "中文 空格 {项目} [x] $y ;z %D"
        folder.mkdir()
        (folder / "example.py").write_text("def f():\n    return 1", encoding="utf-8")
        for target in (self.app, self.app.results, self.app.directory_entry, self.app.export_html_button):
            with self.subTest(target=str(target)):
                self.assertEqual(self.drop((str(folder),), target=target), "copy")
                self.assertTrue(self.app.browse_button.instate(["disabled"]))
                self.finish()
                self.assertEqual(self.app.directory.get(), str(folder))
                row = self.app.results.item(self.app.results.get_children()[3], "values")
                self.assertEqual(row[1:6], ("1", "2", "0", "0", "1"))

    @unittest.skipUnless(sys.platform == "win32", "Windows native drop dispatch")
    def test_file_drop_prefers_file_list_over_text_format(self) -> None:
        self.assertEqual(self.drop((str(self.root),), offered_types=("CF_UNICODETEXT", "CF_HDROP")), "copy")
        self.finish()
        self.assertEqual(self.app.directory.get(), str(self.root))
        self.assertIn("未找到", self.app.status.get())

    @unittest.skipUnless(sys.platform == "win32", "Windows native drop dispatch")
    def test_invalid_drops_show_errors_without_replacing_results(self) -> None:
        source = self.root / "source.c"
        source.write_text("int f() {}", encoding="utf-8")
        folder = self.root / "another"
        folder.mkdir()
        self.choose_directory()
        self.finish()
        rows = self.app.results.get_children()
        status = self.app.status.get()
        cases: tuple[tuple[str, tuple[str, ...] | str], ...] = (
            ("CF_HDROP", (str(source),)),
            ("CF_HDROP", (str(self.root), str(folder))),
            ("CF_HDROP", (str(folder), str(source))),
            ("CF_HDROP", (str(self.root / "missing"),)),
            ("CF_HDROP", ()),
            ("CF_HDROP", ("",)),
            ("CF_HDROP", "{"),
            ("CF_UNICODETEXT", str(folder)),
            ("CF_UNICODETEXT", "arbitrary text"),
        )
        for data_type, data in cases:
            with self.subTest(data_type=data_type, data=data):
                with patch("main.messagebox.showerror") as showerror, patch("main.scan_directory") as scan:
                    self.assertEqual(self.drop(data, data_type), "refuse_drop")
                    showerror.assert_not_called()
                    self.app.update()
                scan.assert_not_called()
                showerror.assert_called_once()
                self.assertEqual(showerror.call_args.args[0], "无法接收拖入")
                self.assertEqual(self.app.directory.get(), str(self.root))
                self.assertEqual(self.app.results.get_children(), rows)
                self.assertEqual(self.app.status.get(), status)
                self.assertTrue(self.app.export_html_button.instate(["!disabled"]))

    @unittest.skipUnless(sys.platform == "win32", "Windows native drop dispatch")
    def test_drop_during_scan_does_not_start_another_worker(self) -> None:
        release = Event()

        def wait_for_release(*_args: object) -> ScanResult:
            release.wait(5)
            return ScanResult()

        folder = self.root / "another"
        folder.mkdir()
        with patch("main.scan_directory", side_effect=wait_for_release) as scan:
            self.choose_directory()
            try:
                with patch("main.messagebox.showerror") as showerror:
                    self.assertEqual(self.drop((str(folder),)), "refuse_drop")
                    self.app.update()
                showerror.assert_called_once()
                self.assertIn("正在统计", showerror.call_args.args[1])
                self.assertEqual(self.app.directory.get(), str(self.root))
                self.assertTrue(self.app.browse_button.instate(["disabled"]))
            finally:
                release.set()
                self.finish()
            scan.assert_called_once()
            self.assertEqual(self.drop((str(folder),)), "copy")
            self.finish()
            self.assertEqual(self.app.directory.get(), str(folder))

    def test_scan_then_rescan_replaces_results(self):
        path = self.root / "example.cs"
        path.write_text("class Example {\n int field;\n int F() => 1;\n int G() {\n return 2;\n }\n}", encoding="utf-8")
        self.choose_directory()
        self.assertTrue(self.app.browse_button.instate(["disabled"]))
        self.assertTrue(self.app.directory_entry.instate(["disabled"]))
        self.finish()
        self.assertEqual(len(self.app.results.get_children()), 5)
        row = self.app.results.item(self.app.results.get_children()[-1], "values")
        self.assertEqual(row, ("C#", "1", "7", "0", "0", "2", "3", "1", "2.00", "2.00"))
        path.write_text("", encoding="utf-8")
        self.choose_directory()
        self.finish()
        self.assertEqual(len(self.app.results.get_children()), 5)
        row = self.app.results.item(self.app.results.get_children()[-1], "values")
        self.assertEqual(row[1:6], ("1", "0", "0", "0", "0"))
        self.assertTrue(self.app.browse_button.instate(["!disabled"]))

    def test_invalid_directory_does_not_start_worker(self):
        self.app.directory.set(str(self.root / "missing"))
        with patch("main.messagebox.showerror") as showerror:
            self.choose_directory()
        showerror.assert_called_once()
        self.assertFalse(self.app.browse_button.instate(["disabled"]))
        self.assertEqual(self.app.results.get_children(), ())

    def test_empty_directory_and_changed_path(self):
        self.choose_directory()
        self.finish()
        self.assertIn("未找到", self.app.status.get())
        self.assertEqual(len(self.app.results.get_children()), 5)
        self.app.directory.set(str(self.root / "another"))
        self.assertEqual(self.app.results.get_children(), ())

    def test_partial_failures_are_shown_in_one_error_dialog(self):
        (self.root / "bad.c").write_bytes(b"\xff\xfe\x00")
        (self.root / "bad.py").write_bytes(b"\xff\xfe\x00")
        (self.root / "good.c").write_text("int f() {}", encoding="utf-8")
        with patch("main.messagebox.showerror") as showerror:
            self.choose_directory()
            self.finish()
        showerror.assert_called_once()
        title, message = showerror.call_args.args
        self.assertEqual(title, "读取失败")
        self.assertIn(str(self.root / "bad.c"), message)
        self.assertIn(str(self.root / "bad.py"), message)
        self.assertIn("2 项读取失败", message)
        self.assertIn("结果不完整", self.app.status.get())
        row = self.app.results.item(self.app.results.get_children()[0], "values")
        self.assertEqual(row[1], "1")
        self.assertTrue(self.app.browse_button.instate(["!disabled"]))

    def test_binary_files_are_skipped_without_notices(self):
        (self.root / "photo.cpp").write_bytes(b"\xff\xd8\xff\xe0JPEG")
        with patch("main.messagebox.showerror") as showerror:
            self.choose_directory()
            self.finish()
        showerror.assert_not_called()
        self.assertNotIn("二进制", self.app.status.get())
        self.assertNotIn("跳过", self.app.status.get())
        self.assertEqual(len(self.app.results.get_children()), 5)
        for item in self.app.results.get_children():
            self.assertEqual(self.app.results.item(item, "values")[1], "0")

    def test_worker_error_restores_controls(self):
        with patch("main.scan_directory", side_effect=RuntimeError("test failure")):
            with patch("main.messagebox.showerror") as showerror:
                self.choose_directory()
                self.finish()
        showerror.assert_called_once()
        self.assertTrue(self.app.browse_button.instate(["!disabled"]))
        self.assertIn("失败", self.app.status.get())

    def test_export_buttons_follow_result_and_scan_state(self) -> None:
        buttons = (self.app.export_csv_button, self.app.export_xlsx_button, self.app.export_html_button)
        with patch("main.filedialog.asksaveasfilename") as save_dialog:
            for button in buttons:
                self.assertTrue(button.instate(["disabled"]))
                button.invoke()
            save_dialog.assert_not_called()
        self.choose_directory()
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))
        self.finish()
        self.assertTrue(all(button.instate(["!disabled"]) for button in buttons))
        self.choose_directory()
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))
        self.finish()
        self.app.directory.set(str(self.root / "another"))
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))

    def test_export_buttons_save_csv_xlsx_and_html(self) -> None:
        (self.root / "example.cs").write_text("class Example { int F() => 1; }", encoding="utf-8")
        self.choose_directory()
        self.finish()
        status = self.app.status.get()
        self.assertEqual(self.app.export_html_button.cget("text"), "导出 HTML 可视化...")
        for suffix, button in (
            ("csv", self.app.export_csv_button), ("xlsx", self.app.export_xlsx_button), ("html", self.app.export_html_button),
        ):
            with self.subTest(format=suffix):
                path = self.root / f"中文 结果.{suffix}"
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)) as save_dialog:
                    with patch("main.messagebox.showinfo") as showinfo:
                        button.invoke()
                save_dialog.assert_called_once()
                showinfo.assert_called_once()
                self.assertTrue(path.is_file())
                self.assertEqual(self.app.status.get(), status)
                if suffix == "html":
                    self.assertEqual(save_dialog.call_args.kwargs["title"], "导出 HTML 可视化")
                    self.assertEqual(save_dialog.call_args.kwargs["defaultextension"], ".html")
                    html = path.read_text(encoding="utf-8")
                    self.assertIn(str(self.root), html)
                    self.assertIn("函数长度分布", html)
                    self.assertIn('<th scope="row">C#</th><td>1</td>', html)
        with (self.root / "中文 结果.csv").open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        visible = [list(self.app.results.item(item, "values")) for item in self.app.results.get_children()]
        self.assertEqual(rows[1:], visible)
        with ZipFile(self.root / "中文 结果.xlsx") as archive:
            self.assertIsNone(archive.testzip())

    def test_cancel_export_creates_no_file_and_keeps_results(self) -> None:
        self.choose_directory()
        self.finish()
        with patch("main.filedialog.asksaveasfilename", return_value=""):
            with patch("main.messagebox.showinfo") as showinfo, patch("main.messagebox.showerror") as showerror:
                self.app.export_csv_button.invoke()
                self.app.export_xlsx_button.invoke()
                self.app.export_html_button.invoke()
        showinfo.assert_not_called()
        showerror.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(len(self.app.results.get_children()), 5)
        self.assertTrue(self.app.export_csv_button.instate(["!disabled"]))

    def test_export_failure_shows_error_and_keeps_results(self) -> None:
        self.choose_directory()
        self.finish()
        for suffix, button in (
            ("csv", self.app.export_csv_button), ("xlsx", self.app.export_xlsx_button), ("html", self.app.export_html_button),
        ):
            with self.subTest(format=suffix):
                path = self.root / f"locked.{suffix}"
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)):
                    with patch(f"main.export_{suffix}", side_effect=PermissionError("file is locked")):
                        with patch("main.messagebox.showerror") as showerror, patch("main.messagebox.showinfo") as showinfo:
                            button.invoke()
                showerror.assert_called_once_with("导出失败", "file is locked", parent=self.app)
                showinfo.assert_not_called()
                self.assertEqual(len(self.app.results.get_children()), 5)
                self.assertTrue(button.instate(["!disabled"]))

    def test_export_after_rescan_uses_latest_results(self) -> None:
        source = self.root / "example.py"
        source.write_text("pass", encoding="utf-8")
        self.choose_directory()
        self.finish()
        source.write_text("", encoding="utf-8")
        self.choose_directory()
        self.finish()
        path = self.root / "latest.csv"
        with patch("main.filedialog.asksaveasfilename", return_value=str(path)), patch("main.messagebox.showinfo"):
            self.app.export_csv_button.invoke()
        with path.open(encoding="utf-8-sig", newline="") as output:
            rows = list(csv.reader(output))
        self.assertEqual(rows[4], ["Python", "1", "0", "0", "0", "0", "0", "0", "0.00", "0.00"])
        html_path = self.root / "latest.html"
        with patch("main.filedialog.asksaveasfilename", return_value=str(html_path)), patch("main.messagebox.showinfo"):
            self.app.export_html_button.invoke()
        self.assertIn('<th scope="row">Python</th><td>1</td><td>0</td>', html_path.read_text(encoding="utf-8"))

    def test_cancelled_scan_can_export_completed_results(self) -> None:
        result = ScanResult(cancelled=True)
        result.languages["C"].add(count_source(b"int f() {\n return 1;\n}", "C"))
        with patch("main.scan_directory", return_value=result):
            self.choose_directory()
            self.finish()
        self.assertIn("已取消", self.app.status.get())

        html_path = self.root / "partial.html"
        with patch("main.filedialog.asksaveasfilename", return_value=str(html_path)), patch("main.messagebox.showinfo"):
            self.app.export_html_button.invoke()
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("结果不完整：扫描已取消", html)
        self.assertIn('<th scope="row">C</th><td>1</td><td>3</td>', html)
        path = self.root / "partial.csv"
        with patch("main.filedialog.asksaveasfilename", return_value=str(path)), patch("main.messagebox.showinfo"):
            self.app.export_csv_button.invoke()
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        self.assertEqual(rows[1], ["C", "1", "3", "0", "0", "1", "3", "3", "3.00", "3.00"])
        self.assertIn("已取消", self.app.status.get())


if __name__ == "__main__":
    unittest.main()