"""Reusable widgets: the colour-coded live log panel and the status bar."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog, Static

# Level -> (glyph, Rich style) for the log panel.
LEVEL_STYLE: dict[str, tuple[str, str]] = {
    "debug": ("··", "dim"),
    "info": ("i ", "cyan"),
    "ok": ("✓ ", "bold green"),
    "warn": ("! ", "bold yellow"),
    "error": ("✗ ", "bold red"),
}


class LogPanel(RichLog):
    """A RichLog that renders TxUltra log events with severity colouring."""

    def __init__(self, **kwargs) -> None:
        # markup=False: plugin output is untrusted text, don't parse markup in
        # it. We build styled Text ourselves for the level prefix.
        # wrap=True + min_width=0: RichLog defaults min_width to 78, which forces
        # long lines to render at 78 cols and get cut off on a narrow phone
        # screen. min_width=0 lets lines wrap to the actual widget width.
        super().__init__(
            highlight=False, markup=False, wrap=True, min_width=0, **kwargs
        )

    def write_event(self, level: str, text: str) -> None:
        glyph, style = LEVEL_STYLE.get(level, ("  ", "white"))
        line = Text()
        line.append(glyph, style=style)
        line.append(text, style=style if level in ("ok", "warn", "error") else "")
        self.write(line)


class StatusBar(Static):
    """One-line status with a spinner while a module is running.

    Plain attributes (not reactives) to avoid watcher/init ordering issues —
    the app drives it via ``set_running`` / ``set_label``.
    """

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, **kwargs) -> None:
        super().__init__("[dim]●[/] Idle", **kwargs)
        self._frame = 0
        self._timer = None
        self._running = False
        self._label = "Idle"

    def set_running(self, running: bool, label: str | None = None) -> None:
        if label is not None:
            self._label = label
        self._running = running
        if running and self._timer is None:
            self._timer = self.set_interval(0.1, self._tick)
        elif not running and self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._paint()

    def set_label(self, label: str) -> None:
        self._label = label
        self._paint()

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(self._FRAMES)
        self._paint()

    def _paint(self) -> None:
        if self._running:
            spin = self._FRAMES[self._frame]
            self.update(f"[bold cyan]{spin}[/] {self._label}")
        else:
            self.update(f"[dim]●[/] {self._label}")
