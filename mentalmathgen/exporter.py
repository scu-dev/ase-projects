from collections.abc import Generator
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from threading import Event
from typing import Protocol, cast

from generator import Progress, Worksheet, check_cancelled


def validate_spacing(spacing: int) -> None:
    if type(spacing) is not int or not 0 <= spacing <= 100:
        raise ValueError("题间空行数必须是 0～100 的整数。")


def format_text(worksheet: Worksheet, *, answers: bool = False, spacing: int = 0) -> str:
    validate_spacing(spacing)
    if answers:
        return "\n".join(f"{index}. {question.answer}" for index, question in enumerate(worksheet.questions, 1))
    separator = "\n" * (spacing + 1)
    return separator.join(
        f"{index}. {question.expression} = ________"
        for index, question in enumerate(worksheet.questions, 1)
    )


@contextmanager
def _destination(path: Path, cancel: Event | None) -> Generator[Path, None, None]:
    check_cancelled(cancel)
    handle, temporary = tempfile.mkstemp(prefix=".mentalmathgen-", suffix=path.suffix, dir=path.parent)
    os.close(handle)
    try:
        yield Path(temporary)
        check_cancelled(cancel)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def export_txt(
    worksheet: Worksheet, path: str | Path, *, answers: bool = False,
    spacing: int = 0, cancel: Event | None = None, progress: Progress | None = None,
) -> None:
    text = format_text(worksheet, answers=answers, spacing=spacing)
    with _destination(Path(path), cancel) as temporary:
        temporary.write_text(text, encoding="utf-8", newline="\n")
    if progress:
        progress(len(worksheet.questions), len(worksheet.questions))


def _pdf_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont, TTFError

    class FontRegistry(Protocol):
        def registerFont(self, font: TTFont) -> None: ...

    # ReportLab accepts TTFont here, but its bundled stub omits the parameter type.
    registry = cast(FontRegistry, pdfmetrics)
    name = "MentalMathChinese"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = (
        fonts / "simsun.ttc",
        fonts / "simhei.ttf",
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    )
    for path in candidates:
        if path.is_file():
            try:
                registry.registerFont(TTFont(name, str(path), subfontIndex=0))
                return name
            except (OSError, TTFError):
                continue
    raise RuntimeError("未找到可嵌入 PDF 的中文字体。请安装宋体、黑体或文泉驿正黑后重试。")


def export_pdf(
    worksheet: Worksheet, path: str | Path, *, answers: bool = False,
    spacing: int = 0, cancel: Event | None = None, progress: Progress | None = None,
) -> None:
    validate_spacing(spacing)
    check_cancelled(cancel)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen.canvas import Canvas
    except ImportError as error:
        raise RuntimeError("缺少 PDF 依赖，请在项目目录运行 uv sync 后重试。") from error

    font = _pdf_font()
    title = "参考答案" if answers else "口算练习"
    width, height = A4
    margin, bottom, leading = 48, 52, 20
    with _destination(Path(path), cancel) as temporary:
        canvas = Canvas(str(temporary), pagesize=A4)
        canvas.setTitle(title)
        canvas.setAuthor("MentalMathGen")
        page = 0

        def new_page() -> float:
            nonlocal page
            if page:
                canvas.showPage()
            page += 1
            canvas.setFillColorRGB(0.12, 0.16, 0.22)
            canvas.setFont(font, 20)
            canvas.drawString(margin, height - 54, title)
            canvas.setFont(font, 10)
            canvas.drawRightString(width - margin, height - 52, f"共 {len(worksheet.questions)} 题")
            canvas.setFillColorRGB(0.35, 0.39, 0.45)
            subtitle = (
                "带余除法格式：商...余数"
                if answers else "姓名：________________    日期：________________"
            )
            canvas.drawString(margin, height - 79, subtitle)
            canvas.setStrokeColorRGB(0.78, 0.81, 0.85)
            canvas.line(margin, height - 92, width - margin, height - 92)
            canvas.setFont(font, 9)
            canvas.drawRightString(width - margin, 28, f"第 {page} 页")
            canvas.setFillColorRGB(0.08, 0.10, 0.14)
            canvas.setFont(font, 12)
            return height - 120

        y = new_page()
        for index, question in enumerate(worksheet.questions, 1):
            check_cancelled(cancel)
            tokens = [question.answer] if answers else [*question.expression.split(), "= ________"]
            lines: list[str] = []
            line = f"{index}."
            for token in tokens:
                candidate = f"{line} {token}"
                if canvas.stringWidth(candidate, font, 12) > width - 2 * margin:
                    lines.append(line)
                    line = token
                else:
                    line = candidate
            lines.append(line)
            if y - (len(lines) - 1) * leading < bottom:
                y = new_page()
            for line in lines:
                canvas.drawString(margin, y, line)
                y -= leading
            # At a page boundary, excess blank lines are discarded instead of making empty pages.
            y -= 6 + (0 if answers else spacing * leading)
            if progress and (index % 100 == 0 or index == len(worksheet.questions)):
                progress(index, len(worksheet.questions))
        canvas.save()