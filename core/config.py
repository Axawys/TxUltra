"""Configuration loading with graceful defaults.

Reads ``config.toml`` from the project root if present, otherwise falls back to
``config.example.toml``, otherwise to built-in defaults. Never raises on a
missing/partial file — missing keys just use defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older Python
    tomllib = None  # type: ignore


DEFAULTS: dict = {
    "general": {"theme": "dark"},
    "network": {"default_interface": "wlan0"},
    "root": {"wrapper": "tsu"},
    "wifi": {
        "wordlist": "/sdcard/wordlists/rockyou.txt",
        "deauth_count": 5,
        "scan_seconds": 20,
        "capture_seconds": 60,
    },
}


@dataclass
class Settings:
    """Typed, flattened view of the config the whole app reads from."""

    theme: str = "dark"
    default_interface: str = "wlan0"
    root_wrapper: str = "tsu"
    wordlist: str = "/sdcard/wordlists/rockyou.txt"
    deauth_count: int = 5
    scan_seconds: int = 20
    capture_seconds: int = 60
    # Raw parsed dict, so custom plugins can read their own [sections].
    raw: dict = field(default_factory=dict)

    def section(self, name: str) -> dict:
        """Return a raw config section (for custom plugin settings)."""
        return dict(self.raw.get(name, {}))


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_settings(project_root: Path) -> Settings:
    """Load settings, merging file over defaults. Tolerant of any failure."""
    data = dict(DEFAULTS)
    for name in ("config.toml", "config.example.toml"):
        path = project_root / name
        if path.is_file() and tomllib is not None:
            try:
                with path.open("rb") as fh:
                    data = _deep_merge(data, tomllib.load(fh))
                break
            except Exception:
                # Corrupt config should never crash the app; use defaults.
                continue

    g, n, r, w = (
        data.get("general", {}),
        data.get("network", {}),
        data.get("root", {}),
        data.get("wifi", {}),
    )
    return Settings(
        theme=g.get("theme", "dark"),
        default_interface=n.get("default_interface", "wlan0"),
        root_wrapper=r.get("wrapper", "tsu"),
        wordlist=w.get("wordlist", DEFAULTS["wifi"]["wordlist"]),
        deauth_count=int(w.get("deauth_count", 5)),
        scan_seconds=int(w.get("scan_seconds", 20)),
        capture_seconds=int(w.get("capture_seconds", 60)),
        raw=data,
    )
