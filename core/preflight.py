"""Environment / capability checks.

Two jobs:

* Per-plugin readiness: are its ``required_binaries`` present, and if it needs
  root, is a root wrapper usable?
* Adapter capability: can the wireless interface do monitor mode / packet
  injection (parsed from ``iw list``)?

Everything returns plain data + friendly hints; nothing here raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.shell import which

# Friendly install hints per binary (Termux `pkg` names / notes).
INSTALL_HINTS: dict[str, str] = {
    "nmap": "pkg install nmap",
    "arp-scan": "pkg install arp-scan  (or use the nmap fallback)",
    "iw": "pkg install iw  (needs root + compatible adapter)",
    "ip": "pkg install iproute2",
    "aircrack-ng": "pkg install aircrack-ng",
    "airmon-ng": "part of aircrack-ng: pkg install aircrack-ng",
    "airodump-ng": "part of aircrack-ng: pkg install aircrack-ng",
    "aireplay-ng": "part of aircrack-ng: pkg install aircrack-ng",
    "hashcat": "pkg install hashcat  (optional, GPU/CPU cracking)",
    "tsu": "pkg install tsu  (root shell wrapper; device must be rooted)",
    "termux-wifi-connectioninfo": "pkg install termux-api  + install the Termux:API app",
}

# Adapters that commonly do monitor mode over OTG on Android, for the hint text.
ADAPTER_HINT = (
    "Most phones' built-in Wi-Fi cannot do monitor mode. Use an external USB "
    "adapter over OTG with a supported chipset (e.g. Atheros AR9271, Ralink "
    "RT3070/RT5370, Realtek RTL8812AU). Then: pkg install root-repo && "
    "pkg install aircrack-ng iw."
)


@dataclass
class PluginCheck:
    """Result of checking one plugin's requirements."""

    ready: bool
    missing_binaries: list[str] = field(default_factory=list)
    needs_root: bool = False
    root_available: bool = True
    hints: list[str] = field(default_factory=list)


def check_root(root_wrapper: str) -> bool:
    """Best-effort: is the configured root wrapper present on PATH?"""
    if not root_wrapper:
        return False
    first = root_wrapper.split()[0]
    return which(first) is not None


def check_plugin(plugin, root_wrapper: str) -> PluginCheck:
    """Check a plugin's binaries and (if needed) root availability."""
    missing = [b for b in plugin.required_binaries if which(b) is None]
    root_ok = True
    hints: list[str] = []

    if plugin.requires_root:
        root_ok = check_root(root_wrapper)
        if not root_ok:
            hints.append(
                f"Root required but wrapper '{root_wrapper or '(unset)'}' not "
                f"found. {INSTALL_HINTS.get('tsu', '')}"
            )

    for b in missing:
        hints.append(f"missing '{b}': {INSTALL_HINTS.get(b, 'install it via pkg')}")

    ready = not missing and root_ok
    return PluginCheck(
        ready=ready,
        missing_binaries=missing,
        needs_root=plugin.requires_root,
        root_available=root_ok,
        hints=hints,
    )


def parse_monitor_capability(iw_list_output: str) -> dict[str, bool]:
    """Parse ``iw list`` output for monitor-mode / injection support.

    Returns ``{"monitor": bool, "injection_hint": bool}``. ``iw`` cannot prove
    injection works, but 'monitor' among supported interface modes is the
    prerequisite, so we surface it as a hint.
    """
    text = iw_list_output.lower()
    monitor = "* monitor" in text or "monitor\n" in text
    return {"monitor": monitor, "injection_hint": monitor}
