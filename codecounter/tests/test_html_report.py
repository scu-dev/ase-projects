from html.parser import HTMLParser
import json
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory
from typing import TypedDict, cast
import unittest
from unittest.mock import patch

from counter import COLUMNS, Counts, ScanError, ScanResult, count_source
from exporter import export_html
from html_report import render_html


class ChartGroup(TypedDict):
    language: str
    code: int
    blank: int
    comment: int
    functions: int
    maximum: int
    minimum: int
    average: str
    median: str
    bins: list[int]


class ChartData(TypedDict):
    bins: list[str]
    groups: list[ChartGroup]


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.resources: list[str] = []
        self.scripts = 0
        self.json = ""
        self.row: list[str] = []
        self.cell: str | None = None
        self.in_data = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for name in ("src", "href"):
            if value := attributes.get(name):
                self.resources.append(value)
        if tag == "script":
            self.scripts += 1
            self.in_data = attributes.get("id") == "report-data"
        elif tag == "tr":
            self.row = []
        elif tag in ("th", "td"):
            self.cell = ""

    def handle_data(self, data: str) -> None:
        if self.in_data:
            self.json += data
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_data = False
        elif tag in ("th", "td"):
            assert self.cell is not None
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)

    def data(self) -> ChartData:
        return cast(ChartData, json.loads(self.json))


class HtmlReportTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="codecounter-html-", dir=Path(__file__).resolve().parent)
        self.root = Path(temporary.name)
        self.addCleanup(temporary.cleanup)
        self.result = ScanResult()
        self.result.languages["C"].add(count_source(b"int a() {}\nint b() {}\nint global;", "C"))
        self.result.languages["Python"].add(count_source(b"def f():\n    # comment\n\n    return 1", "Python"))

    def parse(self, result: ScanResult | None = None, directory: Path | None = None) -> ReportParser:
        parser = ReportParser()
        parser.feed(render_html(result or self.result, directory or self.root))
        return parser

    def test_histogram_boundaries_and_pooled_function_statistics(self) -> None:
        sizes = [1, 5, 6, 10, 11, 20, 21, 50, 51, 100, 101, 999]
        result = ScanResult()
        result.languages["C"].add(Counts(code=sum(sizes), function_lines=sizes))
        result.languages["Python"].add(Counts(code=4, function_lines=[1, 1, 2]))
        data = self.parse(result).data()
        self.assertEqual(data["bins"], ["1–5 行", "6–10 行", "11–20 行", "21–50 行", "51–100 行", "101 行以上"])
        self.assertEqual([group["language"] for group in data["groups"]], ["全部语言", "C", "C++", "JAVA", "Python", "C#"])
        total, c = data["groups"][:2]
        self.assertEqual(c["bins"], [2] * 6)
        self.assertEqual(total["bins"], [5, 2, 2, 2, 2, 2])
        self.assertEqual(total["functions"], 15)
        self.assertEqual((total["maximum"], total["minimum"]), (999, 1))
        self.assertEqual(total["average"], f"{mean(sizes + [1, 1, 2]):.2f}")
        self.assertEqual(total["median"], f"{median(sizes + [1, 1, 2]):.2f}")
        for group in data["groups"]:
            self.assertEqual(sum(group["bins"]), group["functions"])

    def test_table_matches_existing_columns_and_line_counts(self) -> None:
        parser = self.parse()
        self.assertEqual(parser.rows[0], [title for _, title in COLUMNS])
        self.assertEqual(parser.rows[1:], [[str(value) for value in item.row()] for item in self.result.languages.values()])
        total = parser.data()["groups"][0]
        self.assertEqual((total["code"], total["comment"], total["blank"], total["functions"]), (5, 1, 1, 3))
        self.assertEqual(total["bins"], [3, 0, 0, 0, 0, 0])
        self.assertEqual(parser.resources, [])
        self.assertEqual(parser.scripts, 2)

    def test_empty_and_non_function_sources_have_zero_function_statistics(self) -> None:
        result = ScanResult()
        for populated in (False, True):
            with self.subTest(populated=populated):
                if populated:
                    result.languages["C"].add(count_source(b"int global;", "C"))
                parser = self.parse(result)
                self.assertEqual(len(parser.rows), 6)
                for group in parser.data()["groups"]:
                    self.assertEqual(group["bins"], [0] * 6)
                    self.assertEqual((group["functions"], group["maximum"], group["minimum"]), (0, 0, 0))
                    self.assertEqual((group["average"], group["median"]), ("0.00", "0.00"))
                if not populated:
                    self.assertIn("未找到支持的源文件", render_html(result, self.root))

    def test_partial_results_are_labelled_and_binary_skips_remain_silent(self) -> None:
        for cancelled, failed in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(cancelled=cancelled, failed=failed):
                result = ScanResult(cancelled=cancelled)
                result.skipped_binary.append(self.root / "secret-binary.c")
                if failed:
                    result.errors.append(ScanError(self.root / "bad.py", "read failed"))
                html = render_html(result, self.root)
                self.assertEqual("结果不完整：" in html, cancelled or failed)
                self.assertEqual("扫描已取消" in html, cancelled)
                self.assertEqual("1 项读取失败" in html, failed)
                self.assertNotIn("secret-binary", html)
                self.assertNotIn("二进制", html)

    def test_text_and_embedded_json_cannot_inject_html_or_scripts(self) -> None:
        directory = self.root / '<img src=x onerror="alert(1)">&中文$files'
        name = '</script><script>alert("x")</script>&\u2028\u2029'
        self.result.languages["C"].language = name
        html = render_html(self.result, directory)
        parser = self.parse(self.result, directory)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("&amp;中文$files", html)
        self.assertEqual(parser.scripts, 2)
        self.assertEqual(parser.resources, [])
        self.assertEqual(parser.rows[1][0], name)
        self.assertEqual(parser.data()["groups"][1]["language"], name)
        self.assertNotIn("</script", parser.json)

    def test_html_export_overwrites_atomically_and_preserves_report_on_failure(self) -> None:
        path = self.root / "中文 结果.html"
        path.write_bytes(b"previous report")
        export_html(self.result, path, self.root)
        data = path.read_bytes()
        self.assertEqual(data.decode("utf-8"), render_html(self.result, self.root))
        self.assertFalse(data.endswith(b"\n"))
        self.assertNotIn(b"\r\n", data)
        self.assertEqual(list(self.root.glob(".codecounter-*.tmp")), [])
        with patch("exporter.Path.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                export_html(ScanResult(), path, self.root)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(list(self.root.glob(".codecounter-*.tmp")), [])

    def test_missing_destination_reports_failure_without_creating_files(self) -> None:
        path = self.root / "missing" / "report.html"
        with self.assertRaises(OSError):
            export_html(self.result, path, self.root)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()