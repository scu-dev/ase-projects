from bisect import bisect_left
from html import escape
import json
from pathlib import Path
from string import Template

from counter import COLUMNS, LanguageStats, ScanResult


_BIN_LIMITS = (5, 10, 20, 50, 100)
_BIN_LABELS = ("1–5 行", "6–10 行", "11–20 行", "21–50 行", "51–100 行", "101 行以上")


def _chart_data(stats: LanguageStats) -> dict[str, str | int | list[int]]:
    bins = [0] * (len(_BIN_LIMITS) + 1)
    for length in stats.function_lines:
        bins[bisect_left(_BIN_LIMITS, length)] += 1
    return {
        "language": stats.language,
        "code": stats.code,
        "blank": stats.blank,
        "comment": stats.comment,
        "functions": stats.functions,
        "maximum": stats.maximum,
        "minimum": stats.minimum,
        "average": f"{stats.average:.2f}",
        "median": f"{stats.median:.2f}",
        "bins": bins,
    }


def render_html(result: ScanResult, directory: Path) -> str:
    total = LanguageStats(
        "全部语言",
        files=result.files,
        code=sum(item.code for item in result.languages.values()),
        blank=sum(item.blank for item in result.languages.values()),
        comment=sum(item.comment for item in result.languages.values()),
        function_lines=[length for item in result.languages.values() for length in item.function_lines],
    )
    payload = json.dumps(
        {"bins": _BIN_LABELS, "groups": [_chart_data(total), *map(_chart_data, result.languages.values())]},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    # JSON sits in a script element; even inert JSON must not contain a closing tag.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    reasons: list[str] = []
    if result.cancelled:
        reasons.append("扫描已取消")
    if result.errors:
        reasons.append(f"有 {len(result.errors)} 项读取失败")
    if reasons:
        status = "结果不完整：" + "；".join(reasons) + "。以下仅包含已完成读取的文件。"
    elif result.files == 0:
        status = "未找到支持的源文件。"
    else:
        status = "统计完成"

    table_head = "".join(f'<th scope="col">{escape(title)}</th>' for _, title in COLUMNS)
    table_rows = "".join(
        "<tr>" + f'<th scope="row">{escape(item.language)}</th>'
        + "".join(f"<td>{value}</td>" for value in item.row()[1:]) + "</tr>"
        for item in result.languages.values()
    )
    template = Template(Path(__file__).with_name("report_template.html").read_text(encoding="utf-8"))
    return template.substitute(
        page_title=escape(directory.name or str(directory)),
        directory=escape(str(directory)),
        status=escape(status),
        status_class="partial" if reasons else "complete",
        files=f"{total.files:,}",
        code=f"{total.code:,}",
        functions=f"{total.functions:,}",
        table_head=table_head,
        table_rows=table_rows,
        data=payload,
    ).rstrip("\n")