"""Modal screens used by ``ctx.select`` / ``ctx.confirm``.

They are pushed with ``push_screen_wait`` from inside a plugin worker, so the
plugin can pause and await a user decision (pick a target network, confirm
authorization) without the core knowing anything about the specific tool.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static


class _ValueItem(ListItem):
    """A ListItem that carries an arbitrary payload value."""

    def __init__(self, label: str, value: Any) -> None:
        super().__init__(Label(label))
        self.value = value


class SelectScreen(ModalScreen[Any]):
    """Pick one option from a list. Dismisses with the value, or None on Esc."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, Any]]) -> None:
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(self._title, id="modal-title")
            yield ListView(
                *[_ValueItem(label, value) for label, value in self._options],
                id="modal-list",
            )
            yield Static("[dim]Enter = select   Esc = cancel[/dim]")

    def on_mount(self) -> None:
        self.query_one("#modal-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        self.dismiss(getattr(item, "value", None))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation. Dismisses True only on explicit confirm."""

    BINDINGS = [("escape", "deny", "No")]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(self._title, id="modal-title")
            yield Static(self._message, id="modal-message")
            with Vertical(id="modal-buttons"):
                yield Button("Confirm", variant="success", id="yes")
                yield Button("Cancel", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_deny(self) -> None:
        self.dismiss(False)
