# CodeCounter

使用 Python 3.12、Tkinter 和 ttk 的本地代码统计工具，无第三方包依赖。

## 运行

在当前目录执行：

```powershell
uv run main.py
```

已初始化本地虚拟环境时，也可以直接执行：

```powershell
.\.venv\Scripts\python.exe main.py
```

需要使用包含 Tcl/Tk 的 Python 解释器。

## 当前范围

目前仅初始化项目和 GUI 骨架：

- 支持输入目录路径或使用系统文件夹选择窗口。
- 提供语言、文件数、空白行、注释行、代码行的结果表格。
- 提供状态栏；“开始统计”按钮暂时禁用。

目录扫描和统计逻辑尚未实现，后续直接使用 Python 标准库编写，不调用现有 C/Rust 二进制。

## 文件

- `main.py`：程序入口和 Tkinter 界面。
- `pyproject.toml`：项目元数据，第三方依赖为空。
- `.python-version`：固定使用 Python 3.12。
- `uv.lock`：uv 项目锁文件。