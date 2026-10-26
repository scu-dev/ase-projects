from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk


class CodeCounterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CodeCounter")
        self.geometry("900x560")
        self.minsize(680, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.directory = tk.StringVar(self, value=str(Path.cwd()))
        self.status = tk.StringVar(self, value="界面已就绪，统计功能待实现。")

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        self._build_ui()

    def _build_ui(self) -> None:
        content = ttk.Frame(self, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        ttk.Label(
            content,
            text="代码统计",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 16))

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

        ttk.Button(
            directory_bar, text="浏览…", command=self._choose_directory
        ).grid(row=0, column=1, padx=(8, 0))

        self.scan_button = ttk.Button(
            directory_bar, text="开始统计", state="disabled"
        )
        self.scan_button.grid(row=0, column=2, padx=(8, 0))

        results = ttk.Frame(content)
        results.grid(row=3, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)

        columns = (
            ("language", "语言"),
            ("files", "文件数"),
            ("blank", "空白行"),
            ("comment", "注释行"),
            ("code", "代码行"),
        )
        self.results = ttk.Treeview(
            results,
            columns=tuple(name for name, _ in columns),
            show="headings",
            selectmode="browse",
        )
        for name, heading in columns:
            self.results.heading(name, text=heading)
            self.results.column(
                name,
                width=180 if name == "language" else 110,
                minwidth=80,
                anchor="w" if name == "language" else "e",
            )
        self.results.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            results, orient="vertical", command=self.results.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results.configure(yscrollcommand=scrollbar.set)

        ttk.Label(content, textvariable=self.status, anchor="w").grid(
            row=4, column=0, sticky="ew", pady=(12, 0)
        )

    def _choose_directory(self) -> None:
        initial = Path(self.directory.get()).expanduser()
        if not initial.is_dir():
            initial = Path.cwd()

        selected = filedialog.askdirectory(
            parent=self,
            title="选择要统计的目录",
            initialdir=str(initial),
            mustexist=True,
        )
        if selected:
            self.directory.set(str(Path(selected)))
            self.status.set("已选择目录，统计功能待实现。")


def main() -> None:
    app = CodeCounterApp()
    app.mainloop()


if __name__ == "__main__":
    main()