from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from typing import cast
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from exporter import export_pdf, export_txt, format_text
from generator import CancelledError, Config, Question, Worksheet, generate


class ExporterTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent
        self.temp = TemporaryDirectory(prefix="mentalmathgen-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertEqual(self.root.resolve().parent, parent)
        self.sheet = generate(Config(count=60, min_numbers=2, max_numbers=4, mul_div=True, fractions=True, brackets=True, seed=42))

    def test_separate_text_files_preserve_order_spacing_and_utf8(self):
        for answers in (False, True):
            path = self.root / ("答案.txt" if answers else "题目.txt")
            export_txt(self.sheet, path, answers=answers, spacing=2)
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            self.assertNotIn(b"\r", raw)
            self.assertFalse(raw.endswith(b"\n"))
            separator = "\n" if answers else "\n\n\n"
            lines = text.split(separator)
            self.assertEqual(len(lines), 60)
            for index, (line, question) in enumerate(zip(lines, self.sheet.questions), 1):
                expected = question.answer if answers else f"{question.expression} = ________"
                self.assertEqual(line, f"{index}. {expected}")

    def test_pdf_chinese_fonts_pagination_and_separate_content(self):
        for answers in (False, True):
            path = self.root / ("答案.pdf" if answers else "题目.pdf")
            export_pdf(self.sheet, path, answers=answers, spacing=1)
            reader = PdfReader(path)
            self.assertGreater(len(reader.pages), 1)
            metadata = reader.metadata
            assert metadata is not None
            self.assertEqual(metadata.title, "参考答案" if answers else "口算练习")
            all_text = "\n".join(page.extract_text() for page in reader.pages)
            for index, question in enumerate(self.sheet.questions, 1):
                expected = question.answer if answers else f"{question.expression} = ________"
                self.assertIn(f"{index}. {expected}\n", all_text)
            if answers:
                self.assertNotIn("________", all_text)
            else:
                self.assertEqual(all_text.count("= ________"), 60)
            for index, page in enumerate(reader.pages, 1):
                self.assertIn(f"第 {index} 页", page.extract_text())
                resources = page["/Resources"]
                assert isinstance(resources, DictionaryObject)
                fonts = resources["/Font"]
                assert isinstance(fonts, DictionaryObject)
                embedded = False
                for reference in fonts.values():
                    font = reference.get_object()
                    assert isinstance(font, DictionaryObject)
                    if "/FontDescriptor" in font:
                        descriptor = font["/FontDescriptor"]
                        assert isinstance(descriptor, DictionaryObject)
                        embedded = embedded or "/FontFile2" in descriptor
                self.assertTrue(embedded)

    def test_long_questions_wrap_without_losing_text(self):
        expression = " + ".join(["1000000"] * 16)
        sheet = Worksheet(Config(count=2, min_numbers=16, max_numbers=16), (Question(expression, Fraction(16000000)),) * 2, 1)
        path = self.root / "long.pdf"
        export_pdf(sheet, path, spacing=100)
        reader = PdfReader(path)
        self.assertEqual(len(reader.pages), 2)
        text = " ".join(page.extract_text() for page in reader.pages)
        self.assertEqual(text.count("1000000"), 32)
        self.assertEqual(text.count("= ________"), 2)

    def test_export_cancellation_preserves_existing_file_and_removes_temporary(self):
        sheet = replace(self.sheet, questions=self.sheet.questions * 2)
        path = self.root / "existing.pdf"
        path.write_bytes(b"previous document")
        cancel = Event()
        with self.assertRaises(CancelledError):
            export_pdf(sheet, path, cancel=cancel, progress=lambda _completed, _total: cancel.set())
        self.assertEqual(path.read_bytes(), b"previous document")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_write_error_preserves_existing_file(self):
        path = self.root / "existing.txt"
        path.write_bytes(b"previous document")
        with patch("exporter.os.replace", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                export_txt(self.sheet, path)
        self.assertEqual(path.read_bytes(), b"previous document")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_invalid_spacing(self):
        for spacing in (-1, 101, 1.5):
            with self.subTest(spacing=spacing), self.assertRaises(ValueError):
                # Deliberately pass malformed values to exercise runtime validation.
                format_text(self.sheet, spacing=cast(int, spacing))


if __name__ == "__main__":
    unittest.main()