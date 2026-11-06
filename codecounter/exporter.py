import csv
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile

from counter import COLUMNS, ScanResult
from html_report import render_html


_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOCUMENT_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTENT_TYPE_PREFIX = "application/vnd.openxmlformats-officedocument.spreadsheetml."

_STYLES = f'''<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="{_SPREADSHEET_NS}">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF24476B"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center"/>
    </xf>
    <xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _write_atomic(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".codecounter-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_csv(result: ScanResult, path: Path) -> None:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(title for _, title in COLUMNS)
    writer.writerows(item.row() for item in result.languages.values())
    _write_atomic(path, output.getvalue().removesuffix("\n").encode("utf-8-sig"))


def export_html(result: ScanResult, path: Path, directory: Path) -> None:
    _write_atomic(path, render_html(result, directory).encode("utf-8"))


def _xml(root: Element) -> bytes:
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _relationships(*entries: tuple[str, str, str]) -> bytes:
    root = Element("Relationships", xmlns=_PACKAGE_RELS_NS)
    for identifier, kind, target in entries:
        SubElement(root, "Relationship", Id=identifier, Type=f"{_DOCUMENT_RELS_NS}/{kind}", Target=target)
    return _xml(root)


def _content_types() -> bytes:
    root = Element("Types", xmlns=_CONTENT_TYPES_NS)
    SubElement(root, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    SubElement(root, "Default", Extension="xml", ContentType="application/xml")
    for path, kind in (
        ("/xl/workbook.xml", "sheet.main"),
        ("/xl/worksheets/sheet1.xml", "worksheet"),
        ("/xl/styles.xml", "styles"),
    ):
        SubElement(root, "Override", PartName=path, ContentType=f"{_CONTENT_TYPE_PREFIX}{kind}+xml")
    return _xml(root)


def _workbook() -> bytes:
    root = Element("workbook", {"xmlns": _SPREADSHEET_NS, "xmlns:r": _DOCUMENT_RELS_NS})
    sheets = SubElement(root, "sheets")
    SubElement(sheets, "sheet", {"name": "代码统计", "sheetId": "1", "r:id": "rId1"})
    return _xml(root)


def _worksheet(result: ScanResult) -> bytes:
    rows: list[tuple[str | int | float, ...]] = [tuple(title for _, title in COLUMNS)]
    for item in result.languages.values():
        # Preserve the numeric precision; Excel applies the two-decimal display format.
        rows.append((*item.row()[:8], item.average, item.median))

    root = Element("worksheet", xmlns=_SPREADSHEET_NS)
    last_column = chr(ord("A") + len(COLUMNS) - 1)
    table_range = f"A1:{last_column}{len(rows)}"
    SubElement(root, "dimension", ref=table_range)
    views = SubElement(root, "sheetViews")
    view = SubElement(views, "sheetView", workbookViewId="0")
    SubElement(view, "pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
    SubElement(view, "selection", pane="bottomLeft", activeCell="A2", sqref="A2")
    SubElement(root, "sheetFormatPr", defaultRowHeight="18")
    columns = SubElement(root, "cols")
    SubElement(columns, "col", min="1", max="1", width="12", customWidth="1")
    SubElement(columns, "col", min="2", max=str(len(COLUMNS)), width="14", customWidth="1")
    sheet_data = SubElement(root, "sheetData")
    for row_index, values in enumerate(rows, start=1):
        row = SubElement(sheet_data, "row", r=str(row_index))
        if row_index == 1:
            row.set("ht", "26")
            row.set("customHeight", "1")
        for column_index, value in enumerate(values):
            address = f"{chr(ord('A') + column_index)}{row_index}"
            cell = SubElement(row, "c", r=address)
            if row_index == 1:
                cell.set("s", "1")
            elif column_index >= 8:
                cell.set("s", "2")
            if isinstance(value, str):
                cell.set("t", "inlineStr")
                SubElement(SubElement(cell, "is"), "t").text = value
            else:
                cell.set("t", "n")
                SubElement(cell, "v").text = str(value)
    SubElement(root, "autoFilter", ref=table_range)
    return _xml(root)


def export_xlsx(result: ScanResult, path: Path) -> None:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _relationships(("rId1", "officeDocument", "xl/workbook.xml")))
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _relationships(
            ("rId1", "worksheet", "worksheets/sheet1.xml"),
            ("rId2", "styles", "styles.xml"),
        ))
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet(result))
    _write_atomic(path, output.getvalue())