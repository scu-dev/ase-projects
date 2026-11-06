import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree.ElementTree import Element, fromstring
from zipfile import ZipFile

from counter import ScanResult, count_source
from exporter import export_csv, export_xlsx


HEADINGS = ("语言", "源文件数", "代码行数", "空行数", "注释行数", "函数个数", "最大值", "最小值", "均值", "中位数")
NAMESPACES = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = Path(__file__).resolve().parent
        temporary = TemporaryDirectory(prefix="codecounter-export-", dir=parent)
        self.root = Path(temporary.name).resolve()
        self.assertEqual(self.root.parent, parent)
        self.addCleanup(temporary.cleanup)
        self.result = ScanResult()
        for source in (b"int a() {}\nint b() {}\nint global;", b"int c() {\n return 0;\n}\n\n// comment", b"int data;"):
            self.result.languages["C"].add(count_source(source, "C"))
        self.result.languages["C#"].add(count_source(b"class C {\n int F() => 10;\n}", "C#"))

    def test_csv_preserves_headers_order_and_display_precision(self) -> None:
        path = self.root / "中文 统计.csv"
        export_csv(self.result, path)
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(tuple(rows[0]), HEADINGS)
        self.assertEqual([row[0] for row in rows[1:]], ["C", "C++", "JAVA", "Python", "C#"])
        self.assertEqual(rows[1], ["C", "3", "7", "1", "1", "3", "3", "1", "1.67", "1.00"])
        self.assertEqual(rows[5], ["C#", "1", "3", "0", "0", "1", "1", "1", "1.00", "1.00"])
        self.assertTrue(all(len(row) == 10 for row in rows))

    def test_xlsx_has_numeric_cells_and_preserves_unrounded_mean(self) -> None:
        path = self.root / "中文 统计.xlsx"
        export_xlsx(self.result, path)
        with ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            worksheet = fromstring(archive.read("xl/worksheets/sheet1.xml"))
            styles = fromstring(archive.read("xl/styles.xml"))
            workbook = fromstring(archive.read("xl/workbook.xml"))

        def cell(address: str) -> Element:
            found = worksheet.find(f".//s:c[@r='{address}']", NAMESPACES)
            assert found is not None, address
            return found

        rows = worksheet.findall("s:sheetData/s:row", NAMESPACES)
        self.assertEqual(len(rows), 6)
        titles = [item.findtext("s:is/s:t", namespaces=NAMESPACES) for item in rows[0]]
        self.assertEqual(tuple(titles), HEADINGS)
        self.assertEqual(cell("A6").findtext("s:is/s:t", namespaces=NAMESPACES), "C#")
        self.assertEqual(cell("B2").findtext("s:v", namespaces=NAMESPACES), "3")
        self.assertEqual(cell("C2").findtext("s:v", namespaces=NAMESPACES), "7")
        self.assertEqual(cell("G2").findtext("s:v", namespaces=NAMESPACES), "3")
        self.assertEqual(cell("H2").findtext("s:v", namespaces=NAMESPACES), "1")
        self.assertAlmostEqual(float(cell("I2").findtext("s:v", default="nan", namespaces=NAMESPACES)), 5 / 3)
        self.assertEqual(float(cell("J2").findtext("s:v", default="nan", namespaces=NAMESPACES)), 1)
        for row in rows[1:]:
            self.assertEqual(len(row), 10)
            self.assertTrue(all(item.get("t") == "n" for item in list(row)[1:]))
            self.assertEqual(row[0].get("t"), "inlineStr")
            for item in list(row)[8:]:
                style = styles.findall("s:cellXfs/s:xf", NAMESPACES)[int(item.get("s", "0"))]
                self.assertEqual(style.get("numFmtId"), "2")
        sheet = workbook.find("s:sheets/s:sheet", NAMESPACES)
        assert sheet is not None
        self.assertEqual(sheet.get("name"), "代码统计")
        pane = worksheet.find("s:sheetViews/s:sheetView/s:pane", NAMESPACES)
        assert pane is not None
        self.assertEqual((pane.get("state"), pane.get("topLeftCell")), ("frozen", "A2"))
        self.assertEqual(len(worksheet.findall(".//s:f", NAMESPACES)), 0)

    def test_xlsx_relationships_and_content_types_reference_existing_parts(self) -> None:
        path = self.root / "result.xlsx"
        export_xlsx(self.result, path)
        with ZipFile(path) as archive:
            paths = set(archive.namelist())
            for part in paths:
                fromstring(archive.read(part))
            for rels_path, prefix in (("_rels/.rels", ""), ("xl/_rels/workbook.xml.rels", "xl/")):
                for relationship in fromstring(archive.read(rels_path)):
                    target = relationship.get("Target")
                    assert target is not None
                    self.assertIn(prefix + target, paths)
            types = fromstring(archive.read("[Content_Types].xml"))
            overrides = {entry.get("PartName"): entry.get("ContentType") for entry in types if entry.get("PartName")}
            self.assertEqual(overrides["/xl/workbook.xml"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
            self.assertIn("/xl/worksheets/sheet1.xml", overrides)
            self.assertIn("/xl/styles.xml", overrides)

    def test_empty_results_export_five_zero_rows(self) -> None:
        result = ScanResult()
        csv_path = self.root / "empty.csv"
        xlsx_path = self.root / "empty.xlsx"
        export_csv(result, csv_path)
        export_xlsx(result, xlsx_path)
        with csv_path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        self.assertEqual(len(rows), 6)
        for row in rows[1:]:
            self.assertEqual(row[1:], ["0"] * 7 + ["0.00", "0.00"])
        with ZipFile(xlsx_path) as archive:
            worksheet = fromstring(archive.read("xl/worksheets/sheet1.xml"))
        numbers = worksheet.findall(".//s:c[@t='n']/s:v", NAMESPACES)
        self.assertEqual(len(numbers), 45)
        self.assertTrue(all(float(item.text or "nan") == 0 for item in numbers))

    def test_export_replaces_existing_report_and_removes_temporary_files(self) -> None:
        for suffix, export in (("csv", export_csv), ("xlsx", export_xlsx)):
            with self.subTest(format=suffix):
                path = self.root / f"existing.{suffix}"
                path.write_bytes(b"previous report")
                export(self.result, path)
                self.assertNotEqual(path.read_bytes(), b"previous report")
                self.assertEqual(list(self.root.glob(".codecounter-*.tmp")), [])

    def test_replace_failure_preserves_previous_report_and_cleans_up(self) -> None:
        for suffix, export in (("csv", export_csv), ("xlsx", export_xlsx)):
            with self.subTest(format=suffix):
                path = self.root / f"locked.{suffix}"
                path.write_bytes(b"previous report")
                with patch("exporter.Path.replace", side_effect=PermissionError("file is locked")):
                    with self.assertRaises(PermissionError):
                        export(self.result, path)
                self.assertEqual(path.read_bytes(), b"previous report")
                self.assertEqual(list(self.root.glob(".codecounter-*.tmp")), [])

    def test_missing_destination_directory_reports_failure(self) -> None:
        for suffix, export in (("csv", export_csv), ("xlsx", export_xlsx)):
            with self.subTest(format=suffix):
                path = self.root / "missing" / f"result.{suffix}"
                with self.assertRaises(OSError):
                    export(self.result, path)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()