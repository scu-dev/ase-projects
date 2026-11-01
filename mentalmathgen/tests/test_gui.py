from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from tkinter import ttk
import unittest
from unittest.mock import patch

from exporter import format_text
from generator import CancelledError, Config, GenerationError, Progress, Worksheet
from main import MentalMathApp


class TestApp(MentalMathApp):
    """Expose protected task controls to the GUI test harness."""

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def export_buttons(self) -> tuple[ttk.Button, ...]:
        return tuple(self._export_buttons)

    def start_generation(self) -> None:
        self._start_generation()

    def start_export(self, answers: bool, extension: str) -> None:
        self._start_export(answers, extension)

    def set_busy(self, busy: bool) -> None:
        self._set_busy(busy)

    def cancel_job(self) -> None:
        self._cancel_job()

    def close(self) -> None:
        self._close()


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.app = TestApp()
        self.app.withdraw()
        self.app.update_idletasks()
        self.addCleanup(self.app.close)
        self.app.fields["seed"].set("42")
        parent = Path(__file__).resolve().parent
        self.temp = TemporaryDirectory(prefix="mentalmathgen-gui-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertEqual(self.root.resolve().parent, parent)

    def finish(self):
        deadline = monotonic() + 15
        while self.app.busy and monotonic() < deadline:
            self.app.update()
            sleep(0.005)
        self.assertFalse(self.app.busy, "Background operation did not finish")

    def test_generate_preview_spacing_and_replacement(self):
        self.app.start_generation()
        self.assertTrue(self.app.generate_button.instate(["disabled"]))
        self.assertTrue(self.app.entries["count"].instate(["disabled"]))
        self.finish()
        sheet = self.app.worksheet
        assert sheet is not None
        self.assertEqual(len(sheet.questions), 20)
        for answers, preview in enumerate(self.app.previews):
            self.assertEqual(preview.get("1.0", "end-1c"), format_text(sheet, answers=bool(answers)))
        self.app.spacing.set("2")
        self.assertIs(self.app.worksheet, sheet)
        self.assertIn("\n\n\n", self.app.previews[0].get("1.0", "end"))
        self.app.fields["count"].set("5")
        self.assertIn("上一份", self.app.status.get())
        self.app.start_generation()
        self.finish()
        replacement = self.app.worksheet
        assert replacement is not None
        self.assertEqual(len(replacement.questions), 5)
        self.assertTrue(all(button.instate(["!disabled"]) for button in self.app.export_buttons))

    def test_options_do_not_depend_on_operand_counts(self):
        self.assertTrue(self.app.checks["brackets"].instate(["!disabled"]))
        self.assertTrue(self.app.checks["remainder"].instate(["disabled"]))
        self.app.options["mul_div"].set(True)
        for variable in self.app.options.values():
            variable.set(True)
        for minimum, maximum in (("2", "2"), ("2", "5"), ("3", "6"), ("16", "16"), ("", "3")):
            with self.subTest(minimum=minimum, maximum=maximum):
                self.app.fields["min_numbers"].set(minimum)
                self.app.fields["max_numbers"].set(maximum)
                self.assertTrue(all(check.instate(["!disabled"]) for check in self.app.checks.values()))
                self.assertTrue(all(variable.get() for variable in self.app.options.values()))
        self.app.set_busy(True)
        self.assertTrue(all(check.instate(["disabled"]) for check in self.app.checks.values()))
        self.app.set_busy(False)
        self.assertTrue(all(check.instate(["!disabled"]) for check in self.app.checks.values()))

    def test_random_operand_range_reaches_generated_questions(self):
        self.app.fields["count"].set("40")
        self.app.fields["min_numbers"].set("2")
        self.app.fields["max_numbers"].set("5")
        self.app.start_generation()
        self.finish()
        sheet = self.app.worksheet
        assert sheet is not None
        self.assertEqual((sheet.config.min_numbers, sheet.config.max_numbers), (2, 5))
        self.assertEqual({len(re.findall(r"\d+", q.expression)) for q in sheet.questions}, {2, 3, 4, 5})

    def test_invalid_operand_ranges_do_not_start_generation(self):
        for minimum, maximum in (("1", "2"), ("2", "1"), ("5", "4"), ("2", "17"), ("", "3")):
            with self.subTest(minimum=minimum, maximum=maximum):
                self.app.fields["min_numbers"].set(minimum)
                self.app.fields["max_numbers"].set(maximum)
                with patch("main.messagebox.showerror") as error:
                    self.app.start_generation()
                error.assert_called_once()
                self.assertFalse(self.app.busy)
                self.assertIsNone(self.app.worksheet)

    def test_invalid_input_and_impossible_request(self):
        self.app.fields["count"].set("abc")
        with patch("main.messagebox.showerror") as error:
            self.app.start_generation()
        error.assert_called_once()
        self.assertFalse(self.app.busy)
        self.app.fields["count"].set("20")
        self.app.fields["maximum"].set("0")
        with patch("main.messagebox.showerror") as error:
            self.app.start_generation()
            self.finish()
        error.assert_called_once()
        self.assertIsNone(self.app.worksheet)
        self.assertTrue(self.app.generate_button.instate(["!disabled"]))
        self.assertTrue(all(button.instate(["disabled"]) for button in self.app.export_buttons))

    def test_failure_and_cancellation_preserve_previous_worksheet(self):
        self.app.start_generation()
        self.finish()
        sheet = self.app.worksheet
        with patch("main.generate", side_effect=GenerationError("not enough questions")):
            with patch("main.messagebox.showerror") as error:
                self.app.start_generation()
                self.finish()
        error.assert_called_once()
        self.assertIs(self.app.worksheet, sheet)

        def slow_generate(config: Config, cancel: Event, progress: Progress) -> Worksheet:
            while not cancel.wait(0.01):
                progress(0, config.count)
            raise CancelledError()

        with patch("main.generate", side_effect=slow_generate):
            self.app.start_generation()
            self.app.cancel_job()
            self.finish()
        self.assertIs(self.app.worksheet, sheet)
        self.assertIn("取消", self.app.status.get())
        self.assertTrue(self.app.generate_button.instate(["!disabled"]))

    def test_all_four_exports_and_dialog_cancellation(self):
        self.app.fields["max_numbers"].set("4")
        self.app.start_generation()
        self.finish()
        sheet = self.app.worksheet
        for answers in (False, True):
            for extension in ("txt", "pdf"):
                path = self.root / f"{'answers' if answers else 'questions'}.{extension}"
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)):
                    self.app.start_export(answers, extension)
                    self.finish()
                self.assertTrue(path.is_file())
                self.assertIs(self.app.worksheet, sheet)
                self.assertIn("已导出", self.app.status.get())
        with patch("main.filedialog.asksaveasfilename", return_value=""):
            self.app.start_export(False, "txt")
        self.assertFalse(self.app.busy)
        self.assertEqual(len(list(self.root.iterdir())), 4)

    def test_export_error_and_invalid_spacing_restore_controls(self):
        self.app.start_generation()
        self.finish()
        self.app.spacing.set("bad")
        with patch("main.messagebox.showerror") as error:
            self.app.start_export(False, "txt")
        error.assert_called_once()
        self.app.spacing.set("0")
        with patch("main.export_txt", side_effect=PermissionError("read-only")):
            with patch("main.filedialog.asksaveasfilename", return_value=str(self.root / "test.txt")):
                with patch("main.messagebox.showerror") as error:
                    self.app.start_export(False, "txt")
                    self.finish()
        error.assert_called_once()
        self.assertTrue(self.app.generate_button.instate(["!disabled"]))
        self.assertTrue(all(button.instate(["!disabled"]) for button in self.app.export_buttons))


if __name__ == "__main__":
    unittest.main()