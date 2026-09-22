"""The plugin interface every TxUltra tool implements.

Copy this shape to build your own module (see ``plugins/_example.py``)::

    from core.plugin_base import Plugin
    from core import events as ev

    class MyTool(Plugin):
        name = "My Tool"
        category = "Recon"
        description = "What it does, one line."
        requires_root = False
        required_binaries = ["nmap"]

        async def run(self, ctx):
            yield ev.info("hello")
            async for line in ctx.stream("nmap -sn 192.168.0.0/24"):
                yield ev.info(line)
            yield ev.ok("done")

Expose it to the loader either by naming the class (any ``Plugin`` subclass in
the module is auto-registered) or by assigning ``PLUGIN = MyTool()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, ClassVar

from core.events import Log


class Plugin(ABC):
    """Base class for all tools.

    The class attributes are metadata the core reads to build the menu and run
    preflight checks. ``run`` is the only method you must implement.
    """

    # Human-readable name shown in the sidebar.
    name: ClassVar[str] = "Unnamed"
    # Grouping label in the sidebar (e.g. "Recon", "Wireless", "Defensive").
    category: ClassVar[str] = "General"
    # One-line description shown in the details panel.
    description: ClassVar[str] = ""
    # Whether the tool needs root (tsu/su). Preflight warns if root is absent.
    requires_root: ClassVar[bool] = False
    # External binaries the tool calls; preflight checks they exist on PATH.
    required_binaries: ClassVar[list[str]] = []

    @abstractmethod
    async def run(self, ctx) -> AsyncIterator[Log]:
        """Execute the tool.

        This is an *async generator*: ``yield`` structured events from
        ``core.events`` to drive the live log / status / progress UI. Use the
        awaitable helpers on ``ctx`` (``ctx.stream``, ``ctx.select``,
        ``ctx.confirm``, ``ctx.get``) for I/O and user interaction.

        Cancellation: when the user presses Stop, the running worker is
        cancelled and a ``CancelledError`` is raised inside this generator.
        Wrap any cleanup (return adapter to managed mode, kill children) in
        ``try/finally`` so teardown always runs.
        """
        raise NotImplementedError
        # The following makes this a generator for type-checkers; never reached.
        if False:  # pragma: no cover
            yield
