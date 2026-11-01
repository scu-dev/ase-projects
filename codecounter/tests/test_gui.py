import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from counter import Counts, ScanResult
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

    def finish(self):
        deadline = monotonic() + 10
        ticks = 0
        while self.app.scan_button.instate(["disabled"]) and monotonic() < deadline:
            self.app.update()
            ticks += 1
            sleep(0.005)
        self.assertFalse(self.app.scan_button.instate(["disabled"]), "Background scan did not complete")
        self.assertGreater(ticks, 0)

    def test_scan_then_rescan_replaces_results(self):
        path = self.root / "example.cs"
        path.write_text("class Example { int F() => 1; }\n", encoding="utf-8")
        self.app.scan_button.invoke()
        self.assertTrue(self.app.scan_button.instate(["disabled"]))
        self.assertTrue(self.app.directory_entry.instate(["disabled"]))
        self.finish()
        self.assertEqual(len(self.app.results.get_children()), 5)
        row = self.app.results.item(self.app.results.get_children()[-1], "values")
        self.assertEqual(row, ("C#", "1", "1", "0", "0", "1", "1", "1", "1.00", "1.00"))
        path.write_text("", encoding="utf-8")
        self.app.scan_button.invoke()
        self.finish()
        self.assertEqual(len(self.app.results.get_children()), 5)
        row = self.app.results.item(self.app.results.get_children()[-1], "values")
        self.assertEqual(row[1:6], ("1", "0", "0", "0", "0"))
        self.assertTrue(self.app.scan_button.instate(["!disabled"]))

    def test_invalid_directory_does_not_start_worker(self):
        self.app.directory.set(str(self.root / "missing"))
        with patch("main.messagebox.showerror") as showerror:
            self.app.scan_button.invoke()
        showerror.assert_called_once()
        self.assertFalse(self.app.scan_button.instate(["disabled"]))
        self.assertEqual(self.app.results.get_children(), ())

    def test_empty_directory_and_changed_path(self):
        self.app.scan_button.invoke()
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
            self.app.scan_button.invoke()
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
        self.assertTrue(self.app.scan_button.instate(["!disabled"]))

    def test_binary_files_are_skipped_without_notices(self):
        (self.root / "photo.cpp").write_bytes(b"\xff\xd8\xff\xe0JPEG")
        with patch("main.messagebox.showerror") as showerror:
            self.app.scan_button.invoke()
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
                self.app.scan_button.invoke()
                self.finish()
        showerror.assert_called_once()
        self.assertTrue(self.app.scan_button.instate(["!disabled"]))
        self.assertIn("失败", self.app.status.get())

    def test_export_buttons_follow_result_and_scan_state(self) -> None:
        buttons = (self.app.export_csv_button, self.app.export_xlsx_button)
        with patch("main.filedialog.asksaveasfilename") as save_dialog:
            for button in buttons:
                self.assertTrue(button.instate(["disabled"]))
                button.invoke()
            save_dialog.assert_not_called()
        self.app.scan_button.invoke()
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))
        self.finish()
        self.assertTrue(all(button.instate(["!disabled"]) for button in buttons))
        self.app.scan_button.invoke()
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))
        self.finish()
        self.app.directory.set(str(self.root / "another"))
        self.assertTrue(all(button.instate(["disabled"]) for button in buttons))

    def test_export_buttons_save_csv_and_xlsx(self) -> None:
        (self.root / "example.cs").write_text("class Example { int F() => 1; }", encoding="utf-8")
        self.app.scan_button.invoke()
        self.finish()
        status = self.app.status.get()
        for suffix, button in (("csv", self.app.export_csv_button), ("xlsx", self.app.export_xlsx_button)):
            with self.subTest(format=suffix):
                path = self.root / f"中文 结果.{suffix}"
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)) as save_dialog:
                    with patch("main.messagebox.showinfo") as showinfo:
                        button.invoke()
                save_dialog.assert_called_once()
                showinfo.assert_called_once()
                self.assertTrue(path.is_file())
                self.assertEqual(self.app.status.get(), status)
        with (self.root / "中文 结果.csv").open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        visible = [list(self.app.results.item(item, "values")) for item in self.app.results.get_children()]
        self.assertEqual(rows[1:], visible)
        with ZipFile(self.root / "中文 结果.xlsx") as archive:
            self.assertIsNone(archive.testzip())

    def test_cancel_export_creates_no_file_and_keeps_results(self) -> None:
        self.app.scan_button.invoke()
        self.finish()
        with patch("main.filedialog.asksaveasfilename", return_value=""):
            with patch("main.messagebox.showinfo") as showinfo, patch("main.messagebox.showerror") as showerror:
                self.app.export_csv_button.invoke()
                self.app.export_xlsx_button.invoke()
        showinfo.assert_not_called()
        showerror.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(len(self.app.results.get_children()), 5)
        self.assertTrue(self.app.export_csv_button.instate(["!disabled"]))

    def test_export_failure_shows_error_and_keeps_results(self) -> None:
        self.app.scan_button.invoke()
        self.finish()
        for suffix, button in (("csv", self.app.export_csv_button), ("xlsx", self.app.export_xlsx_button)):
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
        self.app.scan_button.invoke()
        self.finish()
        source.write_text("", encoding="utf-8")
        self.app.scan_button.invoke()
        self.finish()
        path = self.root / "latest.csv"
        with patch("main.filedialog.asksaveasfilename", return_value=str(path)), patch("main.messagebox.showinfo"):
            self.app.export_csv_button.invoke()
        with path.open(encoding="utf-8-sig", newline="") as output:
            rows = list(csv.reader(output))
        self.assertEqual(rows[4], ["Python", "1", "0", "0", "0", "0", "0", "0", "0.00", "0.00"])

    def test_cancelled_scan_can_export_completed_results(self) -> None:
        result = ScanResult(cancelled=True)
        result.languages["C"].add(Counts(code=3, functions=1))
        with patch("main.scan_directory", return_value=result):
            self.app.scan_button.invoke()
            self.finish()
        self.assertIn("已取消", self.app.status.get())
        path = self.root / "partial.csv"
        with patch("main.filedialog.asksaveasfilename", return_value=str(path)), patch("main.messagebox.showinfo"):
            self.app.export_csv_button.invoke()
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        self.assertEqual(rows[1], ["C", "1", "3", "0", "0", "1", "3", "3", "3.00", "3.00"])
        self.assertIn("已取消", self.app.status.get())


if __name__ == "__main__":
    unittest.main()