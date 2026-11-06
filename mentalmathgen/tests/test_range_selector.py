import tkinter as tk
import unittest

from range_selector import RangeSelector


class RangeSelectorTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tk.call("wm", "attributes", self.root, "-alpha", 0.0)
        self.root.geometry("340x210")
        self.addCleanup(self.root.destroy)
        self.lower = tk.StringVar(self.root, "2")
        self.upper = tk.StringVar(self.root, "2")
        self.selector = RangeSelector(
            self.root, title="每题数字个数", lower=self.lower, upper=self.upper,
            minimum=2, maximum=16, on_expand=lambda _selected: None,
        )
        self.selector.pack(fill="x", padx=12, pady=12)
        self.root.deiconify()
        self.root.update()

    def expand(self):
        self.selector.toggle_button.invoke()
        self.root.update()

    def drag(self, handle: str, destination: float):
        canvas = self.selector.canvas
        left, top, right, bottom = canvas.coords(handle)
        x, y = round((left + right) / 2), round((top + bottom) / 2)
        canvas.event_generate("<Button-1>", x=x, y=y)
        canvas.event_generate("<B1-Motion>", x=round(destination), y=y)
        canvas.event_generate("<ButtonRelease-1>", x=round(destination), y=y)
        self.root.update()

    def test_expand_collapse_keeps_precise_values(self):
        self.assertFalse(self.selector.expanded)
        self.assertFalse(self.selector.editor.winfo_ismapped())
        self.expand()
        self.assertTrue(self.selector.editor.winfo_ismapped())
        self.selector.upper_entry.delete(0, "end")
        self.selector.upper_entry.insert(0, "8")
        self.assertIn("2 ～ 8", self.selector.toggle_button.cget("text"))
        self.selector.toggle_button.invoke()
        self.root.update()
        self.assertFalse(self.selector.editor.winfo_ismapped())
        self.expand()
        self.assertEqual(self.selector.upper_entry.get(), "8")

    def test_overlapping_handles_can_separate_and_cannot_cross(self):
        self.expand()
        canvas = self.selector.canvas
        low = canvas.coords("lower")
        high = canvas.coords("upper")
        self.assertEqual(low[0], high[0])
        self.assertLess(low[3], high[1])
        left, _, right, _ = canvas.coords("track")
        self.drag("upper", right + 100)
        self.assertEqual((self.lower.get(), self.upper.get()), ("2", "16"))
        self.drag("lower", right + 100)
        self.assertEqual((self.lower.get(), self.upper.get()), ("16", "16"))
        self.drag("upper", left - 100)
        self.assertEqual((self.lower.get(), self.upper.get()), ("16", "16"))
        self.drag("lower", left - 100)
        self.assertEqual((self.lower.get(), self.upper.get()), ("2", "16"))

    def test_keyboard_adjusts_both_bounds_and_respects_limits(self):
        self.expand()
        canvas = self.selector.canvas
        canvas.focus_force()
        self.root.update()
        canvas.event_generate("<KeyPress-Tab>")
        canvas.event_generate("<KeyPress-Right>")
        self.assertEqual(self.upper.get(), "3")
        canvas.event_generate("<KeyPress-End>")
        self.assertEqual(self.upper.get(), "16")
        canvas.event_generate("<KeyPress-Right>")
        self.assertEqual(self.upper.get(), "16")
        canvas.event_generate("<Shift-KeyPress-Tab>")
        canvas.event_generate("<KeyPress-End>")
        self.assertEqual(self.lower.get(), "16")
        canvas.event_generate("<KeyPress-Home>")
        canvas.event_generate("<KeyPress-Left>")
        self.assertEqual(self.lower.get(), "2")
        canvas.event_generate("<KeyPress-Tab>")
        canvas.event_generate("<KeyPress-Home>")
        self.assertEqual(self.upper.get(), "2")
        canvas.event_generate("<KeyPress-Tab>")
        self.root.update()
        self.assertNotEqual(self.root.focus_get(), canvas)

    def test_disabled_controls_ignore_dragging_and_toggle(self):
        self.expand()
        self.selector.set_enabled(False)
        self.selector.toggle_button.invoke()
        self.assertTrue(self.selector.expanded)
        self.drag("upper", 1000)
        self.assertEqual(self.upper.get(), "2")
        self.assertTrue(self.selector.lower_entry.instate(["disabled"]))
        self.assertTrue(self.selector.upper_entry.instate(["disabled"]))
        self.selector.set_enabled(True)
        self.drag("upper", 1000)
        self.assertEqual(self.upper.get(), "16")

    def test_invalid_input_can_be_corrected(self):
        self.expand()
        for invalid in ("", "abc", "17", "1", "2.5"):
            with self.subTest(value=invalid):
                self.selector.upper_entry.delete(0, "end")
                self.selector.upper_entry.insert(0, invalid)
                self.assertFalse(self.selector.valid)
                self.assertIn("待修正", self.selector.toggle_button.cget("text"))
        self.upper.set("8")
        self.assertTrue(self.selector.valid)
        self.assertIn("2 ～ 8", self.selector.toggle_button.cget("text"))
        self.lower.set("9")
        self.assertFalse(self.selector.valid)
        self.upper.set("10")
        self.assertTrue(self.selector.valid)

    def test_track_follows_available_width(self):
        self.expand()
        for width in (340, 230, 420):
            with self.subTest(width=width):
                self.root.geometry(f"{width}x210")
                self.root.update()
                canvas = self.selector.canvas
                left, _, right, _ = canvas.coords("track")
                self.assertAlmostEqual(left, canvas.winfo_width() - right)
                self.drag("upper", right)
                self.assertEqual(self.upper.get(), "16")


if __name__ == "__main__":
    unittest.main()