"""Structured events that a plugin's ``run()`` yields back to the UI.

A plugin never touches Textual widgets directly. Instead its ``run(ctx)``
async-generator *yields* small immutable event objects, and the app decides how
to render them. This keeps plugins UI-agnostic and easy to test.

Emit them with the tiny constructors so plugin code stays readable::

    yield info("Scanning subnet...")
    yield ok("Handshake captured")
    yield warn("telnet (23) open on router")
    yield error("nmap not found")
    yield status("Cracking...")
    yield progress(0.42, "3/7 hosts")
    yield table(rich_table)          # render an arbitrary Rich renderable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Log severity levels -> used for colour coding in the live log panel.
LEVELS = ("debug", "info", "ok", "warn", "error")


@dataclass(frozen=True)
class Log:
    """A single log line with a severity level."""

    level: str
    text: str


@dataclass(frozen=True)
class Status:
    """Short one-line status shown in the status bar (replaces previous)."""

    text: str


@dataclass(frozen=True)
class Progress:
    """Progress update. ``fraction`` is 0..1, or ``None`` for indeterminate."""

    fraction: float | None = None
    text: str = ""


@dataclass(frozen=True)
class Render:
    """Render an arbitrary Rich renderable (e.g. a Table) in the log panel."""

    renderable: Any = None
    meta: dict = field(default_factory=dict)


# --- convenience constructors ------------------------------------------------

def debug(text: str) -> Log:
    return Log("debug", text)


def info(text: str) -> Log:
    return Log("info", text)


def ok(text: str) -> Log:
    return Log("ok", text)


def warn(text: str) -> Log:
    return Log("warn", text)


def error(text: str) -> Log:
    return Log("error", text)


def status(text: str) -> Status:
    return Status(text)


def progress(fraction: float | None = None, text: str = "") -> Progress:
    return Progress(fraction, text)


def table(renderable: Any, **meta: Any) -> Render:
    return Render(renderable, meta)
