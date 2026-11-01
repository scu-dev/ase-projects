import argparse
from pathlib import Path
from queue import Empty, SimpleQueue
import sys
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Literal, Protocol, cast

from counter import COLUMNS, ScanResult, format_report, scan_directory
from exporter import export_csv, export_xlsx


type ScanEvent = (
    tuple[Literal["progress"], tuple[int, str]]
    | tuple[Literal["result"], ScanResult]
    | tuple[Literal["error"], Exception]
)


class ScrollView(Protocol):
    # Tkinter's stubs leave the variadic scrollbar arguments untyped.
    def xview(self, *args: str) -> tuple[float, float] | None: ...
    def yview(self, *args: str) -> tuple[float, float] | None: ...


class CodeCounterApp(tk.Tk):
    def __init__(self, directory: str | Path | None = None) -> None:
        super().__init__()
        self.title("CodeCounter")
        self.geometry("1180x600")
        self.minsize(900, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.directory = tk.StringVar(self, value=str(directory if directory is not None else Path.cwd()))
        self.status = tk.StringVar(self, value="选择目录后开始统计。")
        self._busy = False
        self._closed = False
        self._cancel = Event()
        self._events: SimpleQueue[ScanEvent] = SimpleQueue()
        self._poll_id: str | None = None
        self._result: ScanResult | None = None

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        self._build_ui()
        self.directory.trace_add("write", self._directory_changed)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        content = ttk.Frame(self, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        header = ttk.Frame(content)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="代码统计",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.export_csv_button = ttk.Button(
            header, text="导出 CSV…", command=lambda: self._export_results("csv"), state="disabled"
        )
        self.export_csv_button.grid(row=0, column=1, padx=(8, 0))
        self.export_xlsx_button = ttk.Button(
            header, text="导出 XLSX…", command=lambda: self._export_results("xlsx"), state="disabled"
        )
        self.export_xlsx_button.grid(row=0, column=2, padx=(8, 0))

        ttk.Label(content, text="统计目录").grid(
            row=1, column=0, sticky="w", pady=(0, 6)
        )

        directory_bar = ttk.Frame(content)
        directory_bar.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        directory_bar.columnconfigure(0, weight=1)

        self.directory_entry = ttk.Entry(
            directory_bar, textvariable=self.directory
        )
        self.directory_entry.grid(row=0, column=0, sticky="ew")
        self.directory_entry.bind("<Return>", lambda event: self._start_scan())

        self.browse_button = ttk.Button(
            directory_bar, text="浏览…", command=self._choose_directory
        )
        self.browse_button.grid(row=0, column=1, padx=(8, 0))

        self.scan_button = ttk.Button(
            directory_bar, text="开始统计", command=self._start_scan
        )
        self.scan_button.grid(row=0, column=2, padx=(8, 0))
        self.scan_button.bind("<Return>", lambda event: self._start_scan())

        self.cancel_button = ttk.Button(
            directory_bar, text="取消", command=self._cancel_scan, state="disabled"
        )
        self.cancel_button.grid(row=0, column=3, padx=(8, 0))

        results = ttk.Frame(content)
        results.grid(row=3, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)

        self.results = ttk.Treeview(
            results,
            columns=tuple(name for name, _ in COLUMNS),
            show="headings",
            selectmode="browse",
        )
        for name, heading in COLUMNS:
            self.results.heading(name, text=heading)
            self.results.column(
                name, width=105, minwidth=85,
                anchor="w" if name == "language" else "e",
            )
        self.results.grid(row=0, column=0, sticky="nsew")

        scroll_view = cast(ScrollView, self.results)
        scrollbar = ttk.Scrollbar(
            results, orient="vertical", command=scroll_view.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(
            results, orient="horizontal", command=scroll_view.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self.results.configure(
            yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set
        )

        ttk.Label(content, textvariable=self.status, anchor="w", width=1).grid(
            row=4, column=0, sticky="ew", pady=(12, 0)
        )

    def _directory_changed(self, *_args: str) -> None:
        if not self._busy:
            self._clear_results()
            self.status.set("选择目录后开始统计。")

    def _clear_results(self) -> None:
        self._result = None
        self.export_csv_button.state(["disabled"])
        self.export_xlsx_button.state(["disabled"])
        for item in self.results.get_children():
            self.results.delete(item)

    def _choose_directory(self) -> None:
        try:
            initial = Path(self.directory.get()).expanduser()
            if not initial.is_dir():
                initial = Path.cwd()
        except (OSError, ValueError, RuntimeError):
            initial = Path.cwd()
        selected = filedialog.askdirectory(
            parent=self,
            title="选择要统计的目录",
            initialdir=str(initial),
            mustexist=True,
        )
        if selected:
            self.directory.set(str(Path(selected)))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (self.directory_entry, self.browse_button, self.scan_button):
            widget.state(["disabled"] if busy else ["!disabled"])
        self.cancel_button.state(["!disabled"] if busy else ["disabled"])
        for button in (self.export_csv_button, self.export_xlsx_button):
            button.state(["disabled"] if busy or self._result is None else ["!disabled"])

    def _start_scan(self) -> None:
        if self._busy or self._closed:
            return
        value = self.directory.get().strip()
        try:
            if not value:
                raise ValueError("请输入要统计的目录。")
            directory = Path(value).expanduser().resolve()
            if not directory.is_dir():
                raise ValueError("目录不存在、无法访问，或所选路径不是文件夹。")
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("无法开始统计", str(error), parent=self)
            return
        self.directory.set(str(directory))
        self._clear_results()
        self._cancel = Event()
        self._set_busy(True)
        self.status.set("正在扫描目录…")
        Thread(target=self._scan_worker, args=(directory,), daemon=True).start()
        self._poll_id = self.after(75, self._poll_events)

    def _scan_worker(self, directory: Path) -> None:
        try:
            result = scan_directory(
                directory, self._cancel,
                lambda files, path: self._events.put(("progress", (files, path.name))),
            )
            self._events.put(("result", result))
        except Exception as error:
            self._events.put(("error", error))

    def _poll_events(self) -> None:
        self._poll_id = None
        if self._closed:
            return
        while True:
            try:
                event = self._events.get_nowait()
            except Empty:
                break
            if event[0] == "progress":
                if not self._cancel.is_set():
                    files, name = event[1]
                    self.status.set(f"正在统计，已读取 {files} 个源文件：{name}")
            elif event[0] == "result":
                self._finish_scan(event[1])
            elif event[0] == "error":
                self._set_busy(False)
                self.status.set("统计失败。")
                messagebox.showerror("统计失败", str(event[1]), parent=self)
        if self._busy:
            self._poll_id = self.after(75, self._poll_events)

    def _finish_scan(self, result: ScanResult) -> None:
        self._result = result
        self._set_busy(False)
        for item in result.languages.values():
            self.results.insert("", "end", values=item.row())
        summary = f"{result.files} 个源文件，耗时 {result.elapsed:.3f} 秒。"
        if result.cancelled:
            self.status.set("已取消，仅显示已完成文件的统计：" + summary)
        elif result.errors:
            self.status.set(f"有 {len(result.errors)} 项读取失败，结果不完整；" + summary)
        elif result.files == 0:
            self.status.set("未找到支持的源文件；" + summary)
        else:
            self.status.set("统计完成：" + summary)
        if result.errors:
            details = "\n\n".join(f"{error.path}\n{error.message}" for error in result.errors)
            messagebox.showerror(
                "读取失败",
                f"有 {len(result.errors)} 项读取失败，统计结果不完整。\n\n{details}",
                parent=self,
            )

    def _export_results(self, file_format: Literal["csv", "xlsx"]) -> None:
        result = self._result
        if self._busy or result is None:
            return
        try:
            selected = filedialog.asksaveasfilename(
                parent=self,
                title=f"导出 {file_format.upper()}",
                initialfile=f"codecounter.{file_format}",
                defaultextension=f".{file_format}",
                filetypes=((f"{file_format.upper()} 文件", f"*.{file_format}"),),
                confirmoverwrite=True,
            )
            if not selected:
                return
            path = Path(selected)
            if file_format == "csv":
                export_csv(result, path)
            else:
                export_xlsx(result, path)
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            messagebox.showerror("导出失败", str(error), parent=self)
            return
        messagebox.showinfo("导出完成", f"已保存到：\n{path}", parent=self)

    def _cancel_scan(self) -> None:
        if self._busy:
            self._cancel.set()
            self.cancel_button.state(["disabled"])
            self.status.set("正在取消…")

    def _close(self) -> None:
        self._closed = True
        self._cancel.set()
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
        self.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="统计本地源代码，默认打开 GUI。")
    parser.add_argument("directory", nargs="?", default=".", help="目标目录，默认当前目录")
    parser.add_argument("--cli", action="store_true", help="在控制台输出统计结果")
    args = parser.parse_args()
    if args.cli:
        try:
            result = scan_directory(Path(args.directory))
        except (OSError, ValueError, RuntimeError) as error:
            print(error, file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 130
        print(format_report(result))
        for error in result.errors:
            print(f"{error.path}: {error.message}", file=sys.stderr)
        return int(bool(result.errors) or result.cancelled)
    app = CodeCounterApp(args.directory)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())