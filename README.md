# TxUltra

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform: Termux](https://img.shields.io/badge/platform-Termux%20%2F%20Android-green)

A modular, touch- and keyboard-friendly **TUI toolkit for security work in
Termux (Android)**, built on [Textual](https://textual.textualize.io/).

TxUltra is a *framework* first: the core gives you a live log, a plugin menu,
preflight checks and a cancellable module runner. Tools live in `plugins/` and
are auto-discovered — **add a file, get a menu entry, no core changes**.

Ships with two modules:

| Module | Category | What it does |
|--------|----------|--------------|
| **Network Audit** | Defensive | Audits the Wi-Fi you're on: gateway, subnet, host discovery, port scan, risk report. |
| **Wi-Fi WPA/WPA2 Audit** | Wireless | Authorized password-strength test of **your own** Wi-Fi with the aircrack-ng suite. |

> ⚠️ **Authorized use only.** The Wi-Fi module actively tests a network and can
> send deauth frames. Use it only on networks you own or have **written
> permission** to test. It shows an authorization gate before doing anything.

---

## Requirements

**Python** ≥ 3.11 (for `tomllib`; older works but skips config parsing).

**Python package:**
```bash
pip install -r requirements.txt   # just: textual, rich
```

**External tools** (called via `subprocess`, not reimplemented):

```bash
pkg update
pkg install python nmap iproute2 arp-scan        # Network Audit
pkg install root-repo && pkg install aircrack-ng iw   # Wi-Fi Audit
pkg install tsu                                  # root wrapper (rooted device)
pkg install termux-api                           # optional: AP info
```

## Installation & running

### Termux (Android) — primary target

```bash
# 1. base tooling
pkg update && pkg upgrade
pkg install python git

# 2. get the code
git clone https://github.com/Axawys/TxUltra.git
cd TxUltra

# 3. python deps
pip install -r requirements.txt

# 4. external security tools (install what the modules you use need)
pkg install nmap iproute2 arp-scan               # Module 1: Network Audit
pkg install root-repo && pkg install aircrack-ng iw   # Module 2: Wi-Fi Audit
pkg install tsu                                  # root wrapper (rooted device)
pkg install termux-api                           # optional: current-AP info

# 5. configure (copy the template, then edit)
cp config.example.toml config.toml
nano config.toml            # set wordlist path, default interface, root wrapper

# 6. run
python txultra.py
```

> If a tool is missing, TxUltra tells you in the module's **Preflight** line with
> the exact `pkg install …` to run — nothing crashes.

### Desktop / development (Linux, for hacking on plugins)

The core, UI and both modules run on any Linux with Python 3.11+. The Wi-Fi
module's live steps still need the aircrack-ng suite, root and a capable
adapter, but you can develop and navigate the whole TUI without them.

```bash
git clone https://github.com/Axawys/TxUltra.git && cd TxUltra
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml
python txultra.py
```

## Configuration

Edit `config.toml` (see `config.example.toml` for every key):

- `network.default_interface` — e.g. `wlan0` (built-in) or `wlan1` (OTG adapter).
- `root.wrapper` — `tsu`, `su -c`, or `sudo`. Empty = run unprivileged.
- `wifi.wordlist` — path to your dictionary (e.g. `/sdcard/wordlists/rockyou.txt`).
- `wifi.deauth_count`, `wifi.scan_seconds`, `wifi.capture_seconds` — tuning.
- `general.theme` — `dark` or `light`.

## Hardware notes (Wi-Fi module)

Most phones' **built-in Wi-Fi cannot do monitor mode / packet injection**. You
generally need:

- a **rooted** device (`tsu`/`su`), and
- an **external USB Wi-Fi adapter over OTG** with a supported chipset
  (Atheros AR9271, Ralink RT3070/RT5370, Realtek RTL8812AU, …).

The **Preflight** line under each module tells you what's missing and how to
install it. Verify monitor capability with `iw list` (look for `* monitor`).

## Keyboard & touch

| Key | Action | Touch |
|-----|--------|-------|
| ↑/↓, Tab | navigate menu / panes | tap an item |
| Enter | run highlighted module | tap a module |
| `r` | run selected | tap **Run ▶** |
| `s` / Esc | stop running module | tap **Stop ■** |
| `q` | quit | — |

The live log colour-codes severity (info/ok/warn/error) and auto-scrolls; long
steps show a spinner and progress bar.

---

## Writing your own module

Drop a file in `plugins/`. Minimal example (`plugins/_example.py` is the live
template):

```python
from core import events as ev
from core.plugin_base import Plugin

class MyTool(Plugin):
    name = "My Tool"
    category = "Recon"
    description = "One-line description."
    requires_root = False
    required_binaries = ["nmap"]     # preflight checks these exist

    async def run(self, ctx):
        yield ev.info("starting")
        async for line in ctx.stream("nmap -sn 192.168.0.0/24"):
            yield ev.info(line)                       # live stream
        choice = await ctx.select("Pick one", [("A", 1), ("B", 2)])
        yield ev.ok(f"you chose {choice}")
```

### The plugin contract

**Metadata** (class attributes): `name`, `category`, `description`,
`requires_root`, `required_binaries`.

**`async def run(self, ctx)`** is an async generator. `yield` events from
`core.events`:

| Event | Constructor | Effect |
|-------|-------------|--------|
| Log | `ev.info/ok/warn/error/debug(text)` | colour-coded log line |
| Status | `ev.status(text)` | status-bar text |
| Progress | `ev.progress(fraction, text)` | progress bar (`None` = spinner) |
| Render | `ev.table(rich_renderable)` | draw a Rich table/renderable |

**`ctx` services:**

- `ctx.settings` — typed config (`wordlist`, `default_interface`, …).
- `async for line in ctx.stream(cmd, use_root=False)` — stream a command live.
- `rc, out = await ctx.capture(cmd)` — run to completion.
- `proc = await ctx.spawn(cmd)` / `await ctx.stop(proc)` — background helper.
- `await ctx.select(title, [(label, value), …])` — modal picker.
- `await ctx.confirm(title, message)` — yes/no modal.
- `ctx.which(binary)` — path or `None`.
- `ctx.session` — dict shared for the whole app run (e.g. auth flags).
- `ctx.get(section, key, default)` — read custom `[section]` config.

**Cancellation:** on Stop the worker is cancelled inside `run`. Put teardown
(restore adapter, kill children) in a `try/finally`.

## Project layout

```
txultra.py            entry point
config.example.toml   config template
core/                 app, plugin system, context, shell, config, preflight
  app.py              Textual App (menu + log + runner)
  plugin_base.py      Plugin ABC — the interface you implement
  plugin_loader.py    auto-discovery of plugins/
  context.py          the `ctx` handed to run()
  shell.py            async subprocess streaming
  events.py           structured UI events
  config.py           config loading
  preflight.py        binary/root/adapter checks
ui/
  widgets.py          colour log panel, status bar
  screens.py          select / confirm modals
utils/
  oui.py              MAC vendor lookup
plugins/
  _example.py         template plugin
  network_audit.py    Module 1
  wifi_pentest.py     Module 2
```

## Troubleshooting

- **"preflight" warns about a binary** → install it (`pkg install …`, hint shown).
- **Monitor mode won't enable** → need root + a compatible OTG adapter.
- **arp-scan finds nothing** → it needs root; the app falls back to `nmap -sn`.
- **A plugin fails to import** → the error is shown in the log at startup;
  other plugins still load.

## Legal & responsible use

TxUltra is intended for **defensive security, education, and authorized testing
only**. The Wi-Fi module can transmit deauthentication frames and recover
passphrases — actions that are illegal against networks you do not own or lack
**written permission** to test. You are solely responsible for how you use it.
The authors accept no liability for misuse or for any damage caused.

## License

Licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE)
for the full text.

    TxUltra — modular security TUI for Termux
    Copyright (C) 2026 Axawys

    This program is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version.

    This program is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
    more details.

    You should have received a copy of the GNU General Public License along
    with this program. If not, see <https://www.gnu.org/licenses/>.
