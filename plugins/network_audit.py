"""Module 1 — Network Audit (defensive).

Inspects the network this device is *currently* connected to:

1. Local facts: default gateway, own IP/subnet, current AP encryption.
2. Host discovery on the subnet (arp-scan if available+root, else `nmap -sn`).
3. Port scan of the router and discovered hosts (nmap), flagging risky
   services (telnet, UPnP, exposed admin panels, SMB, ADB, ...).
4. A plain-language summary of what to look at.

Purely observational: it scans the local network you are on. No spoofing, no
injection. Missing tools produce a clear message, never a traceback.
"""

from __future__ import annotations

import json
import re

from rich.table import Table

from core import events as ev
from core.plugin_base import Plugin
from utils.oui import vendor

# service port -> (label, why it matters) for risk highlighting.
RISKY_PORTS: dict[int, tuple[str, str]] = {
    21: ("ftp", "cleartext file transfer"),
    23: ("telnet", "cleartext remote login — should be disabled"),
    2323: ("telnet-alt", "cleartext remote login on alt port"),
    139: ("netbios", "legacy SMB/NetBIOS exposure"),
    445: ("smb", "file sharing — patch & restrict"),
    161: ("snmp", "device management — often default community strings"),
    1900: ("upnp", "UPnP exposed — can open ports automatically"),
    3389: ("rdp", "remote desktop exposed"),
    5555: ("adb", "Android Debug Bridge exposed — remote control risk"),
    37215: ("upnp-cve", "known router UPnP exploit port"),
    8080: ("http-admin", "possible admin interface"),
    8443: ("https-admin", "possible admin interface"),
}
# Ports that are an admin panel when reachable from the LAN on the router.
ADMIN_PORTS = {80, 443, 8080, 8443}


class NetworkAudit(Plugin):
    name = "Network Audit"
    category = "Defensive"
    description = "Audit the Wi-Fi you're on: gateway, hosts, open ports, risks."
    requires_root = False  # arp-scan wants root, but nmap -sn is the fallback
    required_binaries = ["nmap", "ip"]

    async def run(self, ctx):
        yield ev.status("Gathering local network facts")

        gateway, cidr, iface = await self._local_facts(ctx)
        if gateway:
            yield ev.ok(f"Default gateway (router): {gateway}")
        else:
            yield ev.warn(
                "Could not determine default gateway. On Android the route is "
                "often hidden from unprivileged apps — try running TxUltra with "
                "root (e.g. `tsu -c \"python txultra.py\"`)."
            )
        if cidr:
            yield ev.ok(f"Your subnet: {cidr}  (interface {iface})")
        else:
            yield ev.error(
                "Could not determine your subnet. Check: (1) Wi-Fi is connected, "
                "(2) `iproute2` is installed (pkg install iproute2), (3) run with "
                "root — Android restricts `ip` output for non-root apps."
            )
            return

        # Current AP encryption (best-effort, needs termux-api).
        async for e in self._ap_encryption(ctx):
            yield e

        # -- host discovery ---------------------------------------------------
        yield ev.status("Discovering hosts")
        yield ev.progress(None, "scanning subnet")
        hosts = await self._discover(ctx, cidr)
        if not hosts:
            yield ev.warn("No hosts discovered (or scanner returned nothing).")
        else:
            yield ev.ok(f"Discovered {len(hosts)} host(s).")
            yield ev.table(self._host_table(hosts, gateway))

        # -- port scan --------------------------------------------------------
        # Always scan the router; scan other hosts too (bounded by count).
        targets = []
        if gateway:
            targets.append(gateway)
        targets += [h["ip"] for h in hosts if h["ip"] != gateway]

        findings: list[str] = []
        total = len(targets) or 1
        for idx, ip in enumerate(targets, 1):
            yield ev.status(f"Port-scanning {ip} ({idx}/{total})")
            yield ev.progress(idx / total, f"{ip}")
            open_ports = await self._scan_ports(ctx, ip)
            is_router = ip == gateway
            if open_ports:
                yield ev.info(
                    f"{ip}: open -> "
                    + ", ".join(f"{p}/{svc}" for p, svc in open_ports)
                )
                findings += self._assess(ip, open_ports, is_router)
            else:
                yield ev.debug(f"{ip}: no open ports in scanned range")

        # -- report -----------------------------------------------------------
        yield ev.status("Building report")
        yield ev.info("──────── AUDIT SUMMARY ────────")
        if not findings:
            yield ev.ok("No obviously risky services found in the scanned range.")
        else:
            for f in findings:
                yield ev.warn(f)
        yield ev.info(
            "Tip: close/patch flagged services, disable telnet & UPnP on the "
            "router, and change any default admin credentials."
        )
        yield ev.ok("Network audit complete.")

    # ------------------------------------------------------------------ facts

    async def _local_facts(self, ctx) -> tuple[str, str, str]:
        """Return (gateway_ip, subnet_cidr, interface).

        Android keeps routes in per-network tables, not the main table, so a
        plain ``ip route`` is usually empty for an unprivileged process. We try
        several sources — the main table, ``table all``, and the same with root
        — before giving up, and derive a /24 from the gateway as a last resort.
        """
        gateway = iface = cidr = ""
        gw_re = re.compile(r"default via (\d+\.\d+\.\d+\.\d+) dev (\S+)")

        # Source 0: /proc/net/route — a plain file that is usually readable in
        # Termux WITHOUT root, even when the `ip` command is sandboxed by
        # Android. It gives the default gateway, interface AND the on-link
        # subnet directly, so we try it first.
        gateway, iface, cidr = self._read_proc_route()

        # Source 1..N: the `ip` command, progressively broader. (cmd, use_root)
        route_attempts = [
            ("ip route", False),
            ("ip route show table all", False),
            ("ip route show table all", bool(ctx.settings.root_wrapper)),
        ]
        for cmd, use_root in route_attempts:
            if gateway:
                break
            try:
                _, route = await ctx.capture(cmd, use_root=use_root)
            except Exception:
                continue
            m = gw_re.search(route)
            if m:
                gateway, iface = m.group(1), m.group(2)
                break

        # Interface addresses — try one-line formats, unprivileged then root.
        addr_attempts = [
            ("ip -o -f inet addr show", False),
            ("ip -o addr show", False),
            ("ip -o -f inet addr show", bool(ctx.settings.root_wrapper)),
        ]
        best = None
        for cmd, use_root in addr_attempts:
            if cidr:
                break  # already have a subnet from /proc/net/route
            try:
                _, addrs = await ctx.capture(cmd, use_root=use_root)
            except Exception:
                continue
            for line in addrs.splitlines():
                m = re.search(
                    r"\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+/\d+)", line
                )
                if not m:
                    continue
                dev, addr = m.group(1), m.group(2)
                if dev == "lo":
                    continue
                if iface and dev == iface:
                    best = (dev, addr)
                    break
                if best is None:
                    best = (dev, addr)
            if best is not None:
                break

        if best:
            iface = iface or best[0]
            cidr = self._network_cidr(best[1])

        # Last resort: if we know the gateway but not the subnet, assume /24.
        if not cidr and gateway:
            cidr = re.sub(r"\.\d+$", ".0/24", gateway)

        return gateway, cidr, iface

    # -- /proc/net/route parsing (root-free Android fallback) -----------------

    @staticmethod
    def _hex_le_ip(hex8: str) -> str:
        """Convert a little-endian 32-bit hex value (as in /proc/net/route)
        into a dotted IPv4 string. E.g. '0102A8C0' -> '192.168.2.1'."""
        try:
            b = bytes.fromhex(hex8)
            return ".".join(str(x) for x in reversed(b))
        except ValueError:
            return ""

    @classmethod
    def _mask_prefix(cls, hex8: str) -> int:
        """Netmask hex -> prefix length. E.g. '00FFFFFF' -> 24."""
        ip = cls._hex_le_ip(hex8)
        if not ip:
            return 0
        return sum(bin(int(o)).count("1") for o in ip.split("."))

    def _read_proc_route(self) -> tuple[str, str, str]:
        """Parse /proc/net/route for (gateway, iface, subnet_cidr).

        This file is a normal /proc entry and is typically readable in Termux
        without root, unlike the sandboxed `ip` command on modern Android.
        Columns: Iface Destination Gateway Flags RefCnt Use Metric Mask ...
        """
        try:
            with open("/proc/net/route", "r") as fh:
                rows = [ln.split() for ln in fh.read().splitlines()[1:]]
        except OSError:
            return "", "", ""

        rows = [r for r in rows if len(r) >= 8]
        gateway = iface = cidr = ""

        # Default route: Destination == 0, Gateway != 0.
        for dev, dest, gw, _flags, _ref, _use, _metric, mask, *_ in rows:
            if dest == "00000000" and gw != "00000000":
                gateway, iface = self._hex_le_ip(gw), dev
                break

        # On-link subnet: a route with a real destination + mask (prefer our
        # gateway's interface).
        for dev, dest, gw, _flags, _ref, _use, _metric, mask, *_ in rows:
            if dest != "00000000" and mask not in ("00000000", ""):
                net = self._hex_le_ip(dest)
                prefix = self._mask_prefix(mask)
                if net and prefix and (dev == iface or not iface):
                    cidr = f"{net}/{prefix}"
                    if dev == iface:
                        break
        return gateway, iface, cidr

    @staticmethod
    def _network_cidr(addr_cidr: str) -> str:
        """Convert e.g. 192.168.1.34/24 -> 192.168.1.0/24 for scanning."""
        try:
            import ipaddress

            net = ipaddress.ip_interface(addr_cidr).network
            return str(net)
        except Exception:
            return addr_cidr

    async def _ap_encryption(self, ctx):
        """Report current AP encryption via termux-api if present."""
        if ctx.which("termux-wifi-connectioninfo") is None:
            yield ev.debug(
                "termux-api not installed — skipping AP encryption details "
                "(pkg install termux-api)."
            )
            return
        _, out = await ctx.capture("termux-wifi-connectioninfo")
        try:
            data = json.loads(out)
            ssid = data.get("ssid", "?").strip('"')
            supp = data.get("supplicant_state", "?")
            freq = data.get("frequency_mhz", "?")
            yield ev.ok(f"Connected AP: SSID={ssid}  freq={freq}MHz  state={supp}")
            yield ev.info(
                "Note: Android does not expose the AP cipher directly; verify "
                "WPA2/WPA3 in your router admin page."
            )
        except Exception:
            yield ev.debug("Could not parse termux-wifi-connectioninfo output.")

    # -------------------------------------------------------------- discovery

    async def _discover(self, ctx, cidr: str) -> list[dict]:
        """Discover hosts. arp-scan (root) preferred, else nmap -sn."""
        use_arp = ctx.which("arp-scan") is not None
        hosts: dict[str, dict] = {}

        if use_arp:
            # arp-scan needs root; try it, fall back to nmap on failure.
            rc, out = await ctx.capture(
                f"arp-scan --interface=auto --localnet", use_root=True
            )
            for line in out.splitlines():
                m = re.match(
                    r"^(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:]{17})\s*(.*)$", line
                )
                if m:
                    ip, mac = m.group(1), m.group(2)
                    hosts[ip] = {"ip": ip, "mac": mac, "vendor": vendor(mac)}
            if hosts:
                return list(hosts.values())

        # nmap ping sweep fallback (no root required).
        async for line in ctx.stream(f"nmap -sn -T4 {cidr}"):
            m = re.search(r"Nmap scan report for (?:.*\()?(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ip = m.group(1)
                hosts.setdefault(ip, {"ip": ip, "mac": "", "vendor": ""})
                self._last_ip = ip
            m = re.search(r"MAC Address:\s+([0-9A-Fa-f:]{17})\s*\((.*?)\)", line)
            if m and getattr(self, "_last_ip", None):
                hosts[self._last_ip]["mac"] = m.group(1)
                hosts[self._last_ip]["vendor"] = m.group(2) or vendor(m.group(1))
        return list(hosts.values())

    def _host_table(self, hosts: list[dict], gateway: str) -> Table:
        t = Table(title="Discovered hosts", expand=True)
        t.add_column("IP", style="cyan")
        t.add_column("MAC")
        t.add_column("Vendor")
        t.add_column("Role")
        for h in sorted(hosts, key=lambda x: tuple(int(o) for o in x["ip"].split("."))):
            role = "router" if h["ip"] == gateway else ""
            t.add_row(h["ip"], h.get("mac") or "—", h.get("vendor") or "—", role)
        return t

    # -------------------------------------------------------------- portscan

    async def _scan_ports(self, ctx, ip: str) -> list[tuple[int, str]]:
        """Scan common ports on ``ip``; return list of (port, service)."""
        open_ports: list[tuple[int, str]] = []
        cmd = f"nmap -Pn -T4 --top-ports 100 {ip}"
        async for line in ctx.stream(cmd):
            m = re.match(r"^(\d+)/tcp\s+open\s+(\S+)", line)
            if m:
                open_ports.append((int(m.group(1)), m.group(2)))
        return open_ports

    def _assess(self, ip, open_ports, is_router) -> list[str]:
        """Turn open ports into human warnings."""
        out: list[str] = []
        ports = {p for p, _ in open_ports}
        for port, svc in open_ports:
            if port in RISKY_PORTS:
                label, why = RISKY_PORTS[port]
                out.append(f"{ip}: {port}/{label} — {why}")
        if is_router:
            admin = sorted(ports & ADMIN_PORTS)
            if admin:
                out.append(
                    f"{ip} (router): admin interface reachable on "
                    f"{', '.join(map(str, admin))} — ensure a strong password."
                )
        return out
