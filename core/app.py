"""TxUltra Textual application: sidebar menu + live log + module runner.

Responsibilities:
* Load plugins and build a category-grouped, keyboard-and-touch navigable menu.
* Show per-module details and preflight status.
* Run the selected module in a cancellable worker, streaming its yielded events
  into the colour-coded log / status / progress widgets.

Everything module-specific lives in ``plugins/``; this file never needs editing
to add a tool.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)

from core import events as ev
from core.config import load_settings
from core.context import Context
from core.plugin_base import Plugin
from core.plugin_loader import load_plugins
from core.preflight import check_plugin
from core.shell import CommandError, ShellRunner
from ui.widgets import LogPanel, StatusBar


class PluginItem(ListItem):
    """Selectable sidebar entry bound to a plugin."""

    def __init__(self, plugin: Plugin) -> None:
        super().__init__(Label(f"  {plugin.name}"))
        self.plugin = plugin


class HeaderItem(ListItem):
    """Non-selectable category label in the sidebar."""

    def __init__(self, category: str) -> None:
        super().__init__(Label(f"[b]{category}[/b]"))
        self.disabled = True
        self.plugin = None


class TxUltraApp(App):
    """The root application."""

    TITLE = "TxUltra"
    SUB_TITLE = "modular security TUI for Termux"

    CSS = """
    #sidebar {
        width: 32;
        border-right: solid $primary;
    }
    #sidebar-title { padding: 0 1; background: $primary; color: $text; }
    #menu { height: 1fr; }
    #main { width: 1fr; }
    #details {
        height: auto;
        min-height: 5;
        padding: 0 1;
        border-bottom: solid $primary-darken-2;
    }
    #log { height: 1fr; border: none; padding: 0 1; }
    #controls { height: auto; padding: 0 1; }
    #controls Button { margin: 0 1 0 0; }
    #progress { padding: 0 1; height: 1; }
    #status { padding: 0 1; height: 1; background: $panel; }

    #modal-box {
        width: 70; height: auto; max-height: 80%;
        padding: 1 2; border: thick $primary; background: $surface;
        align: center middle;
    }
    #modal-title { text-style: bold; color: $warning; padding-bottom: 1; }
    #modal-message { padding-bottom: 1; }
    #modal-list { height: auto; max-height: 16; }
    #modal-buttons { height: auto; align: center middle; }
    #modal-buttons Button { margin: 1 0 0 0; width: 100%; }
    """

    BINDINGS = [
        ("r", "run", "Run"),
        ("s", "stop", "Stop"),
        ("escape", "stop", "Stop"),
        ("tab", "focus_next", "Next pane"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        root = Path(__file__).resolve().parent.parent
        self.project_root = root
        self.settings = load_settings(root)
        self.shell = ShellRunner(self.settings.root_wrapper)
        # App-lifetime scratch space shared with plugins via ctx.session.
        self.session_store: dict = {}
        self._load = load_plugins("plugins")
        self._current: Plugin | None = None
        self._worker = None

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("Modules", id="sidebar-title")
                yield ListView(*self._build_menu(), id="menu")
            with Vertical(id="main"):
                yield Static(self._welcome(), id="details")
                yield LogPanel(id="log")
                with Horizontal(id="controls"):
                    yield Button("Run ▶", variant="success", id="run")
                    yield Button("Stop ■", variant="error", id="stop")
                yield ProgressBar(id="progress", total=100, show_eta=False)
                yield StatusBar(id="status")
        yield Footer()

    def _build_menu(self) -> list[ListItem]:
        items: list[ListItem] = []
        last_cat = None
        for plugin in self._load.plugins:
            if plugin.category != last_cat:
                items.append(HeaderItem(plugin.category))
                last_cat = plugin.category
            items.append(PluginItem(plugin))
        if not items:
            items.append(HeaderItem("No plugins found"))
        return items

    def _welcome(self) -> str:
        n = len(self._load.plugins)
        theme = "dark" if self.settings.theme != "light" else "light"
        return (
            f"[b]Welcome to TxUltra[/b]  —  {n} module(s) loaded.\n"
            f"Select a module on the left (arrows/Tab or tap), then [b]Run ▶[/b] "
            f"or press [b]r[/b]. Press [b]s[/b]/[b]Esc[/b] to stop, [b]q[/b] to quit.\n"
            f"[dim]interface={self.settings.default_interface}  "
            f"root_wrapper={self.settings.root_wrapper or '(none)'}  theme={theme}[/dim]"
        )

    # -- lifecycle ------------------------------------------------------------

    def on_mount(self) -> None:
        self.theme = "textual-dark" if self.settings.theme != "light" else "textual-light"
        log = self.query_one("#log", LogPanel)
        log.write_event("info", "TxUltra started. Plugins auto-loaded from plugins/.")
        for module, error in self._load.errors:
            log.write_event("error", f"failed to load {module}: {error}")
        self.query_one("#status", StatusBar).set_label("Idle")
        self.query_one("#progress", ProgressBar).update(total=100, progress=0)

    # -- menu interaction -----------------------------------------------------

    @on(ListView.Highlighted, "#menu")
    def _on_highlight(self, event: ListView.Highlighted) -> None:
        item = event.item
        if isinstance(item, PluginItem):
            self._select(item.plugin)

    @on(ListView.Selected, "#menu")
    def _on_select(self, event: ListView.Selected) -> None:
        # Enter / tap on a module: select it and run immediately.
        item = event.item
        if isinstance(item, PluginItem):
            self._select(item.plugin)
            self.action_run()

    def _select(self, plugin: Plugin) -> None:
        self._current = plugin
        check = check_plugin(plugin, self.settings.root_wrapper)
        lines = [
            f"[b]{plugin.name}[/b]   [dim]({plugin.category})[/dim]",
            plugin.description or "",
            f"root: {'required' if plugin.requires_root else 'no'}    "
            f"binaries: {', '.join(plugin.required_binaries) or '—'}",
        ]
        if check.ready:
            lines.append("[green]✓ preflight OK[/green]")
        else:
            lines.append("[yellow]! preflight:[/yellow] " + "; ".join(check.hints))
        self.query_one("#details", Static).update("\n".join(lines))

    # -- run / stop -----------------------------------------------------------

    @on(Button.Pressed, "#run")
    def _btn_run(self) -> None:
        self.action_run()

    @on(Button.Pressed, "#stop")
    def _btn_stop(self) -> None:
        self.action_stop()

    def action_run(self) -> None:
        if self._current is None:
            self._notify_status("Select a module first")
            return
        if self._worker is not None and self._worker.is_running:
            self._notify_status("A module is already running — stop it first")
            return
        self._worker = self.run_worker(
            self._drive(self._current), exclusive=True, name="module"
        )

    def action_stop(self) -> None:
        if self._worker is not None and self._worker.is_running:
            self._worker.cancel()
            self.run_worker(self.shell.terminate_all(), name="terminate")
            self._set_running(False, "Stopped")
            self.query_one("#log", LogPanel).write_event("warn", "Module stopped.")

    async def _drive(self, plugin: Plugin) -> None:
        """Iterate a plugin's event stream and render each event."""
        log = self.query_one("#log", LogPanel)
        self._set_running(True, f"Running {plugin.name}")
        log.write_event("info", f"── {plugin.name} ──")
        ctx = Context(self, self.settings, self.shell)
        try:
            async for event in plugin.run(ctx):
                self._dispatch(event)
        except CommandError as exc:
            log.write_event("error", str(exc))
        except Exception as exc:  # never leak a traceback into the TUI
            log.write_event("error", f"{type(exc).__name__}: {exc}")
        finally:
            self._set_running(False, "Idle")

    def _dispatch(self, event) -> None:
        log = self.query_one("#log", LogPanel)
        if isinstance(event, ev.Log):
            log.write_event(event.level, event.text)
        elif isinstance(event, ev.Status):
            self.query_one("#status", StatusBar).set_label(event.text)
        elif isinstance(event, ev.Progress):
            pb = self.query_one("#progress", ProgressBar)
            if event.fraction is None:
                pb.update(total=None)  # indeterminate
            else:
                pb.update(total=100, progress=max(0.0, min(1.0, event.fraction)) * 100)
            if event.text:
                self.query_one("#status", StatusBar).set_label(event.text)
        elif isinstance(event, ev.Render):
            if event.renderable is not None:
                log.write(event.renderable)

    # -- helpers --------------------------------------------------------------

    def _set_running(self, running: bool, label: str) -> None:
        status = self.query_one("#status", StatusBar)
        status.set_running(running, label)
        if not running:
            self.query_one("#progress", ProgressBar).update(total=100, progress=0)

    def _notify_status(self, text: str) -> None:
        self.query_one("#status", StatusBar).set_label(text)


def main() -> None:
    TxUltraApp().run()


if __name__ == "__main__":
    main()
