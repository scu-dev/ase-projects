from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk


class RangeSelector(ttk.Frame):
    def __init__(
        self, master: tk.Misc, *, title: str, lower: tk.StringVar, upper: tk.StringVar,
        minimum: int, maximum: int, on_expand: Callable[[RangeSelector], None],
    ) -> None:
        super().__init__(master)
        self._lower, self._upper = lower, upper
        self.minimum, self.maximum = minimum, maximum
        self.expanded = False
        self._on_expand = on_expand
        self._enabled = True
        self._active = 0
        self._dragging = False
        self._values = (minimum, maximum)
        self._unit = self.winfo_fpixels("1i") / 96
        self.columnconfigure(0, weight=1)

        heading = ttk.Frame(self)
        heading.grid(row=0, column=0, sticky="ew")
        heading.columnconfigure(0, weight=1)
        label = ttk.Label(heading, text=title)
        label.grid(row=0, column=0, sticky="w")
        label.bind("<Button-1>", self._toggle)
        self.toggle_button = ttk.Button(heading, width=12, command=self._toggle)
        self.toggle_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        self.editor = ttk.Frame(self)
        self.editor.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.editor.columnconfigure(1, weight=1)
        self.editor.columnconfigure(3, weight=1)
        ttk.Label(self.editor, text="最小").grid(row=0, column=0, padx=(0, 6))
        self.lower_entry = ttk.Spinbox(
            self.editor, textvariable=lower, from_=minimum, to=maximum, width=5,
        )
        self.lower_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.editor, text="最大").grid(row=0, column=2, padx=(12, 6))
        self.upper_entry = ttk.Spinbox(
            self.editor, textvariable=upper, from_=minimum, to=maximum, width=5,
        )
        self.upper_entry.grid(row=0, column=3, sticky="ew")

        style = ttk.Style(self)
        self._background = str(style.lookup("TFrame", "background") or "#f0f0f0")
        self._foreground = str(style.lookup("TLabel", "foreground") or "#242424")
        self.canvas = tk.Canvas(
            self.editor, width=200 * self._unit, height=62 * self._unit,
            background=self._background, highlightthickness=0, takefocus=True,
        )
        self.canvas.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.canvas.bind("<Configure>", self._draw)
        self.canvas.bind("<FocusIn>", self._draw)
        self.canvas.bind("<FocusOut>", self._draw)
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<KeyPress>", self._key)
        self._traces = (
            lower.trace_add("write", self._refresh),
            upper.trace_add("write", self._refresh),
        )
        self.editor.grid_remove()
        self._refresh()

    def _read_values(self) -> tuple[int, int] | None:
        try:
            lower, upper = int(self._lower.get()), int(self._upper.get())
        except ValueError:
            return None
        if self.minimum <= lower <= upper <= self.maximum:
            return lower, upper
        return None

    @property
    def valid(self) -> bool:
        return self._read_values() is not None

    def _refresh(self, *_args: str) -> None:
        values = self._read_values()
        if values is not None:
            self._values = values
            self.lower_entry.configure(to=values[1])
            self.upper_entry.configure(from_=values[0])
            summary = f"{values[0]} ～ {values[1]}"
        else:
            summary = "待修正"
        self.toggle_button.configure(text=f"{summary}  {'▾' if self.expanded else '▸'}")
        self._draw()

    def _toggle(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self._enabled:
            self.toggle_button.focus_set()
            self.set_expanded(not self.expanded)

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self.expanded:
            return
        self.expanded = expanded
        if expanded:
            self._on_expand(self)
            self.editor.grid()
        else:
            focus = self.focus_get()
            if focus is not None and str(focus).startswith(f"{self.editor}."):
                self.toggle_button.focus_set()
            self.editor.grid_remove()
        self._refresh()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._dragging = False
        for control in (self.toggle_button, self.lower_entry, self.upper_entry):
            control.state(["!disabled"] if enabled else ["disabled"])
        self.canvas.configure(takefocus=enabled)
        self._draw()

    def _track(self) -> tuple[float, float]:
        width = self.canvas.winfo_width()
        if width <= 1:
            width = self.canvas.winfo_reqwidth()
        margin = 14 * self._unit
        return margin, width - margin

    def _positions(self) -> tuple[tuple[float, float], tuple[float, float]]:
        left, right = self._track()
        span = self.maximum - self.minimum
        low = left + (right - left) * (self._values[0] - self.minimum) / span
        high = left + (right - left) * (self._values[1] - self.minimum) / span
        y = 23 * self._unit
        offset = 10 * self._unit if high - low < 18 * self._unit else 0
        return (low, y - offset), (high, y + offset)

    def _draw(self, _event: tk.Event[tk.Canvas] | None = None) -> None:
        self.canvas.delete("all")
        left, right = self._track()
        y, radius = 23 * self._unit, 7 * self._unit
        color = "#286ab0" if self._enabled else "#a6a6a6"
        positions = self._positions()
        self.canvas.create_line(left, y, right, y, fill="#cccccc", width=4 * self._unit, tags="track")
        self.canvas.create_line(
            positions[0][0], y, positions[1][0], y, fill=color, width=4 * self._unit,
        )
        focused = self._enabled and self.canvas.focus_get() == self.canvas
        for index, (x, thumb_y) in enumerate(positions):
            self.canvas.create_line(x, y, x, thumb_y, fill=color, width=self._unit)
            self.canvas.create_oval(
                x - radius, thumb_y - radius, x + radius, thumb_y + radius,
                fill=color if focused and self._active == index else self._background,
                outline=color, width=2 * self._unit,
                tags="lower" if index == 0 else "upper",
            )
        for x, value in ((left, self.minimum), (right, self.maximum)):
            self.canvas.create_text(
                x, 57 * self._unit, text=str(value), anchor="s", font="TkDefaultFont",
                fill=self._foreground if self._enabled else "#888888",
            )

    def _set_value(self, value: int) -> None:
        lower, upper = self._values
        if self._active == 0:
            lower = max(self.minimum, min(value, upper))
        else:
            upper = min(self.maximum, max(value, lower))
        for variable, number in ((self._lower, lower), (self._upper, upper)):
            if variable.get() != str(number):
                variable.set(str(number))
        self._draw()

    def _move_to(self, x: int) -> None:
        left, right = self._track()
        value = self.minimum + round((x - left) / (right - left) * (self.maximum - self.minimum))
        self._set_value(value)

    def _press(self, event: tk.Event[tk.Canvas]) -> None:
        if not self._enabled:
            return
        positions = self._positions()
        distances = tuple((event.x - x) ** 2 + (event.y - y) ** 2 for x, y in positions)
        self._active = 0 if distances[0] < distances[1] else 1
        self._dragging = True
        self.canvas.focus_set()
        self._move_to(event.x)

    def _drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._enabled and self._dragging:
            self._move_to(event.x)

    def _release(self, _event: tk.Event[tk.Canvas]) -> None:
        self._dragging = False

    def _key(self, event: tk.Event[tk.Canvas]) -> str | None:
        if not self._enabled:
            return None
        value = self._values[self._active]
        if event.keysym in ("Left", "Down"):
            self._set_value(value - 1)
        elif event.keysym in ("Right", "Up"):
            self._set_value(value + 1)
        elif event.keysym == "Home":
            self._set_value(self.minimum)
        elif event.keysym == "End":
            self._set_value(self.maximum)
        elif event.keysym in ("Tab", "ISO_Left_Tab"):
            backwards = event.keysym == "ISO_Left_Tab" or bool(int(event.state) & 1)
            if self._active != int(backwards):
                return None
            self._active = 0 if backwards else 1
            self._draw()
        else:
            return None
        return "break"

    def destroy(self) -> None:
        for variable, trace in zip((self._lower, self._upper), self._traces):
            variable.trace_remove("write", trace)
        super().destroy()