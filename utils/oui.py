"""Tiny MAC-address vendor (OUI) lookup.

Uses an optional system OUI database if one is present, otherwise falls back to
a small built-in table of common vendors. Good enough to annotate a host table;
for full coverage drop a standard ``oui.txt`` (IEEE format) next to this file.
"""

from __future__ import annotations

import re
from pathlib import Path

# Minimal built-in fallback: first 3 octets (uppercase, no separators).
_BUILTIN: dict[str, str] = {
    "FCFBFB": "Apple",
    "F0F61C": "Apple",
    "A4C138": "Apple",
    "DCA632": "Raspberry Pi",
    "B827EB": "Raspberry Pi",
    "E45F01": "Raspberry Pi",
    "001A11": "Google",
    "3C5AB4": "Google",
    "F4F5D8": "Google",
    "D83134": "Roku",
    "50C7BF": "TP-Link",
    "AC84C6": "TP-Link",
    "C46E1F": "TP-Link",
    "E894F6": "TP-Link",
    "001374": "AVM (FRITZ!Box)",
    "3C37E6": "AVM (FRITZ!Box)",
    "000C43": "Ralink/MediaTek",
    "0018E7": "Cameo/Realtek",
    "5254AB": "Realtek",
    "0013EF": "Xiaomi",
    "286C07": "Xiaomi",
    "F8A45F": "Xiaomi",
    "001DD8": "Microsoft",
    "7C1E52": "Microsoft",
    "005056": "VMware",
    "080027": "VirtualBox",
    "525400": "QEMU/KVM",
}

_cache: dict[str, str] | None = None


def _normalize(mac: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", mac).upper()


def _load_db() -> dict[str, str]:
    """Load a full IEEE oui.txt if available; else the built-in table."""
    global _cache
    if _cache is not None:
        return _cache

    db = dict(_BUILTIN)
    # Common locations where an oui database might live.
    candidates = [
        Path(__file__).with_name("oui.txt"),
        Path("/usr/share/nmap/nmap-mac-prefixes"),
        Path("/data/data/com.termux/files/usr/share/nmap/nmap-mac-prefixes"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                for line in path.read_text("utf-8", "replace").splitlines():
                    # Support "AABBCC Vendor" (nmap) and IEEE "AA-BB-CC (hex) V".
                    m = re.match(r"^\s*([0-9A-Fa-f]{6})\s+(.+?)\s*$", line)
                    if m:
                        db.setdefault(m.group(1).upper(), m.group(2))
                        continue
                    m = re.match(
                        r"^\s*([0-9A-Fa-f]{2}[-:]){2}[0-9A-Fa-f]{2}\s+\(hex\)\s+(.+?)\s*$",
                        line,
                    )
                    if m:
                        prefix = _normalize(line.split()[0])[:6]
                        db.setdefault(prefix, m.group(2))
                break
        except Exception:
            continue

    _cache = db
    return db


def vendor(mac: str) -> str:
    """Return a best-effort vendor name for ``mac`` (or 'Unknown')."""
    norm = _normalize(mac)
    if len(norm) < 6:
        return "Unknown"
    return _load_db().get(norm[:6], "Unknown")
