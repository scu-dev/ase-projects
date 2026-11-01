from collections.abc import Callable
from functools import partial
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Literal

from exporter import export_pdf, export_txt, format_text, validate_spacing
from generator import CancelledError, Config, Worksheet, generate


type WorkerEvent = (
    tuple[Literal["progress"], tuple[int, int]]
    | tuple[Literal["result"], Worksheet | Path]
    | tuple[Literal["cancelled"], None]
    | tuple[Literal["error"], Exception]
)


class MentalMathApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("口算题目生成器")
        self.geometry("1120x760")
        self.minsize(960, 680)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.fields = {
            name: tk.StringVar(self, value=value)
            for name, value in (
                ("count", "20"), ("min_numbers", "2"), ("max_numbers", "2"), ("minimum", "0"),
                ("maximum", "20"), ("seed", ""),
            )
        }
        self.options = {
            name: tk.BooleanVar(self, value=False)
            for name in ("mul_div", "brackets", "negative", "remainder", "fractions")
        }
        self.spacing = tk.StringVar(self, value="0")
        self.status = tk.StringVar(self, value="设置参数后点击“生成题目”。")
        self.worksheet: Worksheet | None = None
        self._busy = False
        self._closed = False
        self._job: Literal["generate", "export"] = "generate"
        self._cancel = Event()
        self._events: SimpleQueue[WorkerEvent] = SimpleQueue()
        self._poll_id: str | None = None
        self._controls: list[ttk.Widget] = []
        self.entries: dict[str, ttk.Entry] = {}
        self.checks: dict[str, ttk.Checkbutton] = {}
        self._export_buttons: list[ttk.Button] = []
        self._save_directory = Path.cwd()

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        self._build_ui()
        for variable in (*self.fields.values(), *self.options.values()):
            variable.trace_add("write", self._settings_changed)
        self.spacing.trace_add("write", self._spacing_changed)
        self._set_busy(False)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        content = ttk.Frame(self, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(1, weight=1)

        sidebar = ttk.Frame(content)
        sidebar.grid(row=1, column=0, sticky="ns", padx=(0, 16))
        sidebar.columnconfigure(0, weight=1)
        settings = ttk.LabelFrame(sidebar, text="生成设置", padding=12)
        settings.grid(row=0, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)
        for row, (name, label, low, high) in enumerate((
            ("count", "题目数量", 1, 10_000),
            ("min_numbers", "每题最小数字个数", 2, 16),
            ("max_numbers", "每题最大数字个数", 2, 16),
            ("minimum", "最小数值", 0, 1_000_000),
            ("maximum", "最大数值", 0, 1_000_000),
        )):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            entry = ttk.Spinbox(settings, textvariable=self.fields[name], from_=low, to=high, width=12)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.entries[name] = entry
            self._controls.append(entry)
        ttk.Separator(settings).grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
        for row, (name, label) in enumerate((
            ("mul_div", "允许乘除法"),
            ("brackets", "使用括号（超过两个数字时）"),
            ("negative", "允许中间结果及答案为负数"),
            ("remainder", "除法允许余数（两个数字时）"),
            ("fractions", "除法允许分数（超过两个数字时）"),
        ), 6):
            check = ttk.Checkbutton(settings, text=label, variable=self.options[name])
            check.grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
            self.checks[name] = check
            self._controls.append(check)
        ttk.Separator(settings).grid(row=11, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(settings, text="种子（留空随机）").grid(row=12, column=0, sticky="w", padx=(0, 12))
        seed = ttk.Entry(settings, textvariable=self.fields["seed"], width=12)
        seed.grid(row=12, column=1, sticky="ew")
        self.entries["seed"] = seed
        self._controls.append(seed)

        actions = ttk.Frame(sidebar)
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        actions.columnconfigure(0, weight=1)
        self.generate_button = ttk.Button(actions, text="生成题目", command=self._start_generation)
        self.generate_button.grid(row=0, column=0, sticky="ew")
        self.cancel_button = ttk.Button(actions, text="取消", command=self._cancel_job)
        self.cancel_button.grid(row=0, column=1, padx=(8, 0))
        self.status_label = ttk.Label(
            sidebar, textvariable=self.status, width=1, anchor="w", justify="left", wraplength=300,
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        preview = ttk.LabelFrame(content, text="试卷预览", padding=12)
        preview.grid(row=1, column=1, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.tabs = ttk.Notebook(preview)
        self.tabs.grid(row=0, column=0, sticky="nsew")
        self.previews: list[tk.Text] = []
        for title in ("题目", "答案"):
            frame = ttk.Frame(self.tabs)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            text = tk.Text(
                frame, wrap="word", state="disabled", font=("Microsoft YaHei UI", 12),
                padx=14, pady=12, relief="flat", width=40, height=15,
                background="white", foreground="#18202a", insertbackground="#18202a",
            )
            text.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(frame, orient="vertical", command=partial(self._scroll_preview, text))
            scrollbar.grid(row=0, column=1, sticky="ns")
            text.configure(yscrollcommand=scrollbar.set)
            self.tabs.add(frame, text=title)
            self.previews.append(text)

        layout = ttk.Frame(preview)
        layout.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        ttk.Label(layout, text="题间空行").grid(row=0, column=0, sticky="w")
        self.spacing_entry = ttk.Spinbox(layout, textvariable=self.spacing, from_=0, to=100, width=6)
        self.spacing_entry.grid(row=0, column=1, padx=(8, 0))
        self._controls.append(self.spacing_entry)
        exports = ttk.Frame(preview)
        exports.grid(row=2, column=0, sticky="ew")
        for index, (label, answers, extension) in enumerate((
            ("下载题目 txt", False, "txt"), ("下载答案 txt", True, "txt"),
            ("下载题目 PDF", False, "pdf"), ("下载答案 PDF", True, "pdf"),
        )):
            exports.columnconfigure(index, weight=1)
            button = ttk.Button(exports, text=label, command=partial(self._start_export, answers, extension))
            button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 6, 0))
            self._export_buttons.append(button)

    @staticmethod
    def _scroll_preview(
        preview: tk.Text, action: Literal["moveto", "scroll"], value: str,
        units: Literal["units", "pages"] = "units",
    ) -> None:
        if action == "moveto":
            preview.yview_moveto(float(value))
        else:
            preview.yview_scroll(int(value), units)

    def _read_config(self) -> Config:
        labels = {
            "count": "题目数量", "min_numbers": "每题最小数字个数", "max_numbers": "每题最大数字个数",
            "minimum": "最小数值", "maximum": "最大数值", "seed": "随机种子",
        }
        values: dict[str, int] = {}
        for name, variable in self.fields.items():
            text = variable.get().strip()
            if name == "seed" and not text:
                continue
            try:
                values[name] = int(text)
            except ValueError:
                self.entries[name].focus_set()
                raise ValueError(f"{labels[name]}必须填写整数。") from None
        return Config(
            count=values["count"], min_numbers=values["min_numbers"], max_numbers=values["max_numbers"],
            minimum=values["minimum"], maximum=values["maximum"], seed=values.get("seed"),
            mul_div=self.options["mul_div"].get(), brackets=self.options["brackets"].get(),
            negative=self.options["negative"].get(), remainder=self.options["remainder"].get(),
            fractions=self.options["fractions"].get(),
        )

    def _read_spacing(self) -> int:
        try:
            spacing = int(self.spacing.get().strip())
        except ValueError:
            raise ValueError("题间空行数必须是 0～100 的整数。") from None
        validate_spacing(spacing)
        return spacing

    def _settings_changed(self, *_args: str) -> None:
        self._update_options()
        if not self._busy and self.worksheet is not None:
            self.status.set("参数已修改，请重新生成；当前预览和导出仍对应上一份试卷。")

    def _spacing_changed(self, *_args: str) -> None:
        try:
            self._render_preview()
        except ValueError:
            self.status.set("题间空行数必须是 0～100 的整数。")

    def _update_options(self) -> None:
        enabled = self.options["mul_div"].get() and not self._busy
        for name in ("remainder", "fractions"):
            self.checks[name].state(["!disabled"] if enabled else ["disabled"])

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for control in (*self._controls, self.generate_button):
            control.state(["disabled"] if busy else ["!disabled"])
        self.cancel_button.state(["!disabled"] if busy else ["disabled"])
        for button in self._export_buttons:
            button.state(["!disabled"] if self.worksheet is not None and not busy else ["disabled"])
        self._update_options()

    def _begin_job(self, kind: Literal["generate", "export"], operation: Callable[[], Worksheet | Path]) -> None:
        self._job = kind
        self._set_busy(True)
        self.status.set("正在生成题目…" if kind == "generate" else "正在导出文件…")
        Thread(target=self._worker, args=(operation,), daemon=True).start()
        self._poll_id = self.after(60, self._poll_events)

    def _report_progress(self, completed: int, total: int) -> None:
        self._events.put(("progress", (completed, total)))

    def _start_generation(self) -> None:
        if self._busy or self._closed:
            return
        try:
            config = self._read_config()
            self._read_spacing()
        except ValueError as error:
            messagebox.showerror("参数有误", str(error), parent=self)
            return
        self._cancel = Event()
        self._begin_job("generate", partial(generate, config, self._cancel, self._report_progress))

    def _start_export(self, answers: bool, extension: str) -> None:
        if self._busy or self._closed or self.worksheet is None:
            return
        try:
            spacing = self._read_spacing()
        except ValueError as error:
            messagebox.showerror("参数有误", str(error), parent=self)
            return
        label = "答案" if answers else "题目"
        selected = filedialog.asksaveasfilename(
            parent=self, title=f"导出口算{label}", initialdir=str(self._save_directory),
            initialfile=f"口算{label}.{extension}", defaultextension=f".{extension}",
            filetypes=[("PDF 文档" if extension == "pdf" else "UTF-8 文本", f"*.{extension}")],
        )
        if not selected:
            return
        path = Path(selected)
        self._save_directory = path.parent
        worksheet = self.worksheet
        self._cancel = Event()
        exporter = export_pdf if extension == "pdf" else export_txt

        def save() -> Path:
            exporter(worksheet, path, answers=answers, spacing=spacing, cancel=self._cancel, progress=self._report_progress)
            return path

        self._begin_job("export", save)

    def _worker(self, operation: Callable[[], Worksheet | Path]) -> None:
        try:
            self._events.put(("result", operation()))
        except CancelledError:
            self._events.put(("cancelled", None))
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
                completed, total = event[1]
                if not self._cancel.is_set():
                    label = "生成" if self._job == "generate" else "导出"
                    self.status.set(f"正在{label}：{completed} / {total} 道题…")
                continue
            self._set_busy(False)
            if event[0] == "cancelled" or (
                event[0] == "result" and isinstance(event[1], Worksheet) and self._cancel.is_set()
            ):
                self.status.set("已取消。" + ("上一份试卷已保留。" if self.worksheet else ""))
            elif event[0] == "result":
                result = event[1]
                if isinstance(result, Worksheet):
                    self.worksheet = result
                    self._render_preview()
                    self.status.set("生成完成。")
                    self._set_busy(False)
                else:
                    self.status.set(f"已导出：{result}")
            elif event[0] == "error":
                label = "生成失败" if self._job == "generate" else "导出失败"
                self.status.set(label + "。" + ("上一份试卷已保留。" if self.worksheet else ""))
                messagebox.showerror(label, str(event[1]), parent=self)
        if self._busy:
            self._poll_id = self.after(60, self._poll_events)

    def _render_preview(self) -> None:
        if self.worksheet is None:
            return
        spacing = self._read_spacing()
        for answers, preview in enumerate(self.previews):
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", format_text(self.worksheet, answers=bool(answers), spacing=spacing))
            preview.configure(state="disabled")

    def _cancel_job(self) -> None:
        if self._busy:
            self._cancel.set()
            self.cancel_button.state(["disabled"])
            self.status.set("正在取消…")

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel.set()
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
        self.destroy()


def main() -> int:
    app = MentalMathApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())