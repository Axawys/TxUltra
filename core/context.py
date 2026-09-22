"""The ``ctx`` object handed to every plugin's ``run()``.

It bundles everything a tool needs so plugin code stays small and declarative:

* ``ctx.settings``            -> typed Settings (wordlist, interface, ...).
* ``ctx.stream(cmd)``         -> async-iterate a command's live output.
* ``ctx.capture(cmd)``        -> run to completion, get (rc, text).
* ``ctx.which(bin)``          -> path or None.
* ``ctx.select(title, opts)`` -> await a user's choice from a modal list.
* ``ctx.confirm(title, msg)`` -> await yes/no from a modal.
* ``ctx.session``             -> dict persisted for the whole app session
                                 (e.g. a module's authorization flag).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

from core.config import Settings
from core.shell import ShellRunner


class Context:
    """Runtime services available to a plugin during ``run()``."""

    def __init__(self, app, settings: Settings, shell: ShellRunner) -> None:
        self._app = app
        self.settings = settings
        self._shell = shell
        # Shared, app-lifetime scratch space keyed by the plugin (or anything).
        self.session: dict[str, Any] = app.session_store

    # -- shell passthroughs ---------------------------------------------------

    def stream(
        self, cmd: str | Sequence[str], *, use_root: bool = False
    ) -> AsyncIterator[str]:
        """Async-iterate live output of ``cmd`` (see ShellRunner.stream)."""
        return self._shell.stream(cmd, use_root=use_root)

    async def capture(
        self, cmd: str | Sequence[str], *, use_root: bool = False
    ) -> tuple[int, str]:
        """Run ``cmd`` to completion; return (returncode, combined output)."""
        return await self._shell.capture(cmd, use_root=use_root)

    async def spawn(self, cmd, *, use_root: bool = False):
        """Start a background helper process; returns a handle for ``stop``."""
        return await self._shell.start(cmd, use_root=use_root)

    async def stop(self, proc) -> None:
        """Stop a process started with ``spawn``."""
        await self._shell.stop(proc)

    def which(self, binary: str) -> str | None:
        """Absolute path of ``binary`` on PATH, or None."""
        from core.shell import which

        return which(binary)

    # -- user interaction (modal screens, awaited from the worker) ------------

    async def select(self, title: str, options: list[tuple[str, Any]]) -> Any | None:
        """Show a selectable list; return the chosen option's value or None.

        ``options`` is a list of ``(label, value)``. Cancelled -> None.
        """
        from ui.screens import SelectScreen

        return await self._app.push_screen_wait(SelectScreen(title, options))

    async def confirm(self, title: str, message: str) -> bool:
        """Show a yes/no modal; return True only on explicit confirm."""
        from ui.screens import ConfirmScreen

        return bool(await self._app.push_screen_wait(ConfirmScreen(title, message)))

    # -- settings convenience -------------------------------------------------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Read an arbitrary value from the raw config (for custom plugins)."""
        return self.settings.section(section).get(key, default)
