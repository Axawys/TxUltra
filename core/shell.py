"""Async subprocess helpers with streaming output.

Two primitives used everywhere:

* ``stream(cmd)``  -> async-iterate stdout+stderr line by line, live.
* ``capture(cmd)`` -> run to completion, return (returncode, full_text).

Both accept a command as a string (parsed with ``shlex``) or a list. Both can
optionally elevate via the configured root wrapper (tsu/su). Running processes
are tracked so the app can terminate them on Stop.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from typing import AsyncIterator, Sequence


class CommandError(Exception):
    """Raised for setup problems (missing binary) — carries a friendly text."""


def which(binary: str) -> str | None:
    """Return absolute path of ``binary`` on PATH, or None if absent."""
    return shutil.which(binary)


class ShellRunner:
    """Runs external commands and streams their output.

    Keeps a set of live processes so they can be force-terminated when the
    user stops a module mid-run.
    """

    def __init__(self, root_wrapper: str = "") -> None:
        self.root_wrapper = (root_wrapper or "").strip()
        self._procs: set[asyncio.subprocess.Process] = set()

    # -- command assembly -----------------------------------------------------

    def _argv(self, cmd: str | Sequence[str], use_root: bool) -> list[str]:
        argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        if use_root and self.root_wrapper:
            wrapper = shlex.split(self.root_wrapper)
            # `su -c` expects the whole command as ONE argument.
            if wrapper[-1] == "-c":
                return wrapper + [" ".join(shlex.quote(a) for a in argv)]
            return wrapper + argv
        return argv

    # -- streaming ------------------------------------------------------------

    async def stream(
        self,
        cmd: str | Sequence[str],
        *,
        use_root: bool = False,
    ) -> AsyncIterator[str]:
        """Yield combined stdout/stderr lines from ``cmd`` as they arrive."""
        argv = self._argv(cmd, use_root)
        if which(argv[0]) is None and "/" not in argv[0]:
            raise CommandError(f"'{argv[0]}' not found on PATH")

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            raise CommandError(f"cannot execute '{argv[0]}': {exc}") from exc

        self._procs.add(proc)
        try:
            assert proc.stdout is not None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                yield raw.decode("utf-8", "replace").rstrip("\n")
            await proc.wait()
        finally:
            # On cancellation or normal exit, make sure the child is gone.
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except (ProcessLookupError, asyncio.TimeoutError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
            self._procs.discard(proc)

    # -- one-shot -------------------------------------------------------------

    async def capture(
        self,
        cmd: str | Sequence[str],
        *,
        use_root: bool = False,
    ) -> tuple[int, str]:
        """Run ``cmd`` to completion; return (returncode, combined output)."""
        lines: list[str] = []
        rc = 0
        try:
            async for line in self.stream(cmd, use_root=use_root):
                lines.append(line)
        except CommandError:
            raise
        return rc, "\n".join(lines)

    # -- background processes -------------------------------------------------

    async def start(
        self,
        cmd: str | Sequence[str],
        *,
        use_root: bool = False,
    ) -> asyncio.subprocess.Process:
        """Launch ``cmd`` in the background (output discarded) and return it.

        Used when a tool needs a long-lived helper running concurrently — e.g.
        airodump-ng capturing while aireplay-ng sends deauth frames. Stop it
        with ``stop()``; it is tracked so global Stop kills it too.
        """
        argv = self._argv(cmd, use_root)
        if which(argv[0]) is None and "/" not in argv[0]:
            raise CommandError(f"'{argv[0]}' not found on PATH")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._procs.add(proc)
        return proc

    async def stop(self, proc: asyncio.subprocess.Process) -> None:
        """Terminate a process started with ``start()``."""
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        self._procs.discard(proc)

    async def terminate_all(self) -> None:
        """Terminate every tracked process (called on global Stop/quit)."""
        for proc in list(self._procs):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
