"""Smallest possible plugin — copy this to start a new module.

It needs no external tools and no root, so it always runs. Use it as a live
template for the plugin contract: metadata + an async ``run`` that yields
events from ``core.events``.
"""

from __future__ import annotations

import asyncio

from core import events as ev
from core.plugin_base import Plugin


class ExamplePlugin(Plugin):
    name = "Example / Echo"
    category = "Examples"
    description = "Demo module: streams a few lines and a fake progress bar."
    requires_root = False
    required_binaries = []  # pure-Python, nothing external

    async def run(self, ctx):
        yield ev.info("This is the example plugin.")
        yield ev.status("Working...")

        # Demonstrate live streaming from a real subprocess (portable).
        async for line in ctx.stream(["python", "-c", "print('hello from a child process')"]):
            yield ev.info(line)

        # Demonstrate a determinate progress bar.
        steps = 5
        for i in range(1, steps + 1):
            await asyncio.sleep(0.3)
            yield ev.progress(i / steps, f"step {i}/{steps}")
            yield ev.debug(f"did step {i}")

        # Demonstrate the different log levels / colours.
        yield ev.warn("this is a warning line")
        yield ev.ok("example finished successfully")
