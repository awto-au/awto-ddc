#!/usr/bin/env python3
"""Restore Dan's desktop layout (scripts/desk_layout.json) for the monitors that are present; 'off' connectors stay off (#78).

usage: desk_layout.py show | restore [--dry-run] | check | store | watch | save | mirror <off-conn> <host-conn> | unmirror
- Why: with one monitor missing (unit 2 dark) mutter rejects its stored configuration, falls back to a row, turns DP-1
  back on, and unit 3 auto-searches onto DP. `gdctl set --persistent` alone did not stop it.
- restore: each row (same y) keeps its order; a missing monitor's slot is closed by shifting the ones right of it left
  (mutter refuses gaps). A monitor in another row keeps its x, clamped to touch the row below. Primary = first present
  in "primary". Modes from the file. One `gdctl set` call, TEMPORARY (ApplyMonitorsConfig method 1): a persistent apply
  pops GNOME's "Keep these display settings?" dialog and reverts in 20 s unanswered (Dan 2026-11-08). Persistence = `store`.
- store: also written by restore. ~/.config/monitors.xml entry for the connected set (incl. 'off' connectors as
  <disabled>) replaced by this layout; old file copied to tmp/monitors.xml.<stamp>. Why: `gdctl set --persistent` left the
  file untouched (mtime 2026-11-07) and a stale entry for this set (DP-1 at 2560x1600@59.987, a mode our EDID dropped) made
  mutter fall back to a row on every DPMS wake / hot-plug.
- check: exit 0 if the live layout already equals what restore would set (positions, primary, no 'off' connector).
- watch: mutter's MonitorsChanged D-Bus signal (`gdbus monitor`; drm uevents miss mutter's own re-layout after a
  wake); once the signals have been quiet for SETTLE_S and the desktop is not in DPMS power
  save, restore if the layout differs. Why: a monitor that drops HPD in standby (card2 change event ~5 s into a DPMS off,
  2026-11-08) makes mutter rebuild a default row with DP-1 on, and it keeps that row after the wake.
- watch only undoes mutter's fallback (one row at y 0, or an 'off' connector on): a layout Dan arranges himself is left
  alone; `save` writes the live layout into the json.
- mirror / unmirror: test-mode flag (tmp/desk_layout_mirror.json). While set, an 'off' connector sharing its host's
  logical monitor (same position) is an allowed state for watch / check / restore, not mutter's fallback.
  `dev.py mode --unit 2 --dp mirror|off` sets / clears it around the gdctl call (#60, #83 two-input tests).
- dev.py calls restore after flash / reset / power-cycle / recover (unit reboots re-plug a monitor).
Log: ./tmp/logs/desk_layout.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


REPO = _repo()
LOG = REPO / "tmp/logs/desk_layout.log"
CFG = REPO / "scripts/desk_layout.json"
W = 3840                    # logical width of every monitor here (4K, scale 1)
H = 2160
# gdctl show ~0.1 s; set = a modeset of 4 outputs, measured 2-3 s (dev.py GDCTL_SET_S); 3x cold worst case (awto-dan#53)
SHOW_S = 5
SET_S = 15


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def live() -> tuple[list[str], dict[str, tuple[int, int]], str | None]:
    """(connected connectors, {connector: (x, y)} of the logical monitors, primary connector)."""
    out = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=SHOW_S, check=True).stdout
    mons = re.findall(r"Monitor (\S+) \(", out.split("Logical monitors:")[0])
    pos, prim = {}, None
    for blk in out.split("Logical monitor #")[1:]:
        p = re.search(r"Position: \((-?\d+), (-?\d+)\)", blk)
        conns = re.findall(r"──(\S+) \(", blk.split("Monitors:")[-1])
        for c in conns:
            pos[c] = (int(p.group(1)), int(p.group(2)))
        if re.search(r"Primary: yes", blk) and conns:
            prim = conns[0]
    return mons, pos, prim


MONXML = Path.home() / ".config/monitors.xml"


def specs() -> dict[str, tuple[str, str, str]]:
    """connector -> (vendor, product, serial) from gdctl show."""
    out = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=SHOW_S, check=True).stdout
    res = {}
    for m in re.finditer(r"Monitor (\S+) \(.*?\n.*?Vendor: (.*?)\n.*?Product: (.*?)\n.*?Serial: (.*?)\n", out, re.S):
        res[m.group(1)] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
    return res


def store(want: list[dict], prim: str | None, present: list[str]) -> str:
    import xml.etree.ElementTree as ET
    cfg = json.loads(CFG.read_text())
    sp = specs()

    def spec(parent, conn):
        s = ET.SubElement(parent, "monitorspec")
        for tag, v in zip(("connector", "vendor", "product", "serial"), (conn, *sp[conn]), strict=True):
            ET.SubElement(s, tag).text = v

    new = ET.Element("configuration")
    ET.SubElement(new, "layoutmode").text = "logical"
    for m in want:
        lm = ET.SubElement(new, "logicalmonitor")
        for tag, v in (("x", m["x"]), ("y", m["y"]), ("scale", 1)):
            ET.SubElement(lm, tag).text = str(v)
        if m["connector"] == prim:
            ET.SubElement(lm, "primary").text = "yes"
        mon = ET.SubElement(lm, "monitor")
        spec(mon, m["connector"])
        mode = ET.SubElement(mon, "mode")
        w, rest = m["mode"].split("x")
        h, rate = rest.split("@")
        for tag, v in (("width", w), ("height", h), ("rate", rate)):
            ET.SubElement(mode, tag).text = v
    off = [c for c in present if c in cfg["off"]]
    if off:
        dis = ET.SubElement(new, "disabled")
        for c in off:
            spec(dis, c)
    key = {(c, *sp[c]) for c in present}
    tree = ET.parse(MONXML)
    root = tree.getroot()
    dropped = 0
    for c in root.findall("configuration"):
        have = {tuple(s.findtext(k) for k in ("connector", "vendor", "product", "serial")) for s in c.iter("monitorspec")}
        if have == key:
            root.remove(c)
            dropped += 1
    root.append(new)
    bak = REPO / "tmp" / f"monitors.xml.{time.strftime('%Y%m%d-%H%M%S')}"
    bak.write_bytes(MONXML.read_bytes())
    ET.indent(tree)
    tree.write(MONXML, encoding="unicode")
    return f"monitors.xml: {dropped} entry(s) for this set replaced (backup {bak.name})"


def plan(present: list[str]) -> tuple[list[dict], str | None]:
    cfg = json.loads(CFG.read_text())
    want = [dict(m) for m in cfg["monitors"] if m["connector"] in present and m["connector"] not in cfg["off"]]
    allm = cfg["monitors"]
    rows = sorted({m["y"] for m in allm}, reverse=True)       # bottom row first (largest y)
    for y in rows:
        stored = sorted([m for m in allm if m["y"] == y], key=lambda m: m["x"])
        x = stored[0]["x"]
        for s in stored:
            for m in want:
                if m["connector"] == s["connector"]:
                    m["x"] = x
                    x += W
    for y in rows[1:]:                                         # upper rows: touch the span of the row below
        below = [m for m in want if m["y"] == y + H]
        if not below:
            continue
        lo, hi = min(m["x"] for m in below), max(m["x"] for m in below) + W
        for m in want:
            if m["y"] == y:
                m["x"] = min(max(m["x"], lo), hi - W)
    prim = next((c for c in cfg["primary"] if any(m["connector"] == c for m in want)), None)
    return want, prim


def gdctl_args(want: list[dict], prim: str | None) -> list[str]:
    a = []
    for m in want:
        a += ["--logical-monitor", *(["--primary"] if m["connector"] == prim else []),
              "--monitor", m["connector"], "--mode", m["mode"], "--x", str(m["x"]), "--y", str(m["y"])]
    return a


MIRROR = REPO / "tmp/desk_layout_mirror.json"


def mirrors() -> dict[str, str]:
    """Test-mode mirrors {off connector: host connector}; empty when the flag file is absent."""
    try:
        return json.loads(MIRROR.read_text())
    except (OSError, ValueError):
        return {}


def strip_mirrors(pos: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """pos without flagged mirror connectors that sit in their host's logical monitor."""
    mir = mirrors()
    return {c: p for c, p in pos.items() if not (c in mir and pos.get(mir[c]) == p)}


def same_layout(pos: dict[str, tuple[int, int]], prim_now: str | None, want: list[dict], prim: str | None) -> bool:
    pos = strip_mirrors(pos)
    return (prim_now == prim and set(pos) == {m["connector"] for m in want}
            and all(pos.get(m["connector"]) == (m["x"], m["y"]) for m in want))


def fallback(pos: dict[str, tuple[int, int]]) -> bool:
    """mutter's fallback: every monitor in one row at y 0 (its default), or an 'off' connector on the desktop."""
    off = json.loads(CFG.read_text())["off"]
    pos = strip_mirrors(pos)
    return any(c in pos for c in off) or (len(pos) > 1 and all(y == 0 for _x, y in pos.values()))


SETTLE_S = 3.0             # a re-plug + mutter re-layout is 1-2 s of events (2026-11-08); restore after 3 s of quiet
MUTTER_PS = ["busctl", "--user", "get-property", "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
             "org.gnome.Mutter.DisplayConfig", "PowerSaveMode"]


def watch() -> int:
    import select
    p = subprocess.Popen(["gdbus", "monitor", "--session", "--dest", "org.gnome.Mutter.DisplayConfig",
                          "--object-path", "/org/gnome/Mutter/DisplayConfig"], stdout=subprocess.PIPE, text=True)
    log("watch: gdbus monitor org.gnome.Mutter.DisplayConfig started")
    pending = True                              # check once at start
    while True:
        r, _, _ = select.select([p.stdout], [], [], SETTLE_S if pending else None)   # blocks on events, no poll loop
        if r:
            line = p.stdout.readline()
            if not line:
                log("watch: gdbus monitor ended")
                return 1
            pending = pending or "MonitorsChanged" in line
            continue
        pending = False
        ps = subprocess.run(MUTTER_PS, capture_output=True, text=True, timeout=SHOW_S, check=False).stdout.split()
        if ps[-1:] != ["0"]:
            pending = True                      # DPMS off: re-check after the next quiet window, not now
            continue
        mons, pos, prim_now = live()
        want, prim = plan(mons)
        if same_layout(pos, prim_now, want, prim):
            continue
        if not fallback(pos):
            log(f"watch: layout differs but is not mutter's fallback ({pos}): Dan's own change, left alone")
            continue
        r2 = subprocess.run(["gdctl", "set", *gdctl_args(want, prim)], capture_output=True, text=True,
                            timeout=SET_S, check=False)
        log(f"watch: layout differed ({pos}, primary {prim_now}); restore (temporary apply) rc={r2.returncode} "
            + ", ".join(f"{m['connector']}@{m['x']},{m['y']}" for m in want))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["show", "restore", "check", "store", "watch", "save", "mirror", "unmirror"])
    ap.add_argument("conns", nargs="*", help="mirror: <off connector> <host connector>, e.g. DP-1 HDMI-2")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.action == "watch":
        return watch()
    if a.action == "mirror":
        off = json.loads(CFG.read_text())["off"]
        if len(a.conns) != 2 or a.conns[0] not in off:
            ap.error(f"mirror: <off connector> <host connector>; off connectors: {off}")
        MIRROR.write_text(json.dumps({**mirrors(), a.conns[0]: a.conns[1]}) + "\n")
        log(f"mirror: {a.conns[0]} allowed in {a.conns[1]}'s logical monitor (test mode, {MIRROR.name})")
        return 0
    if a.action == "unmirror":
        MIRROR.unlink(missing_ok=True)
        log("unmirror: test-mode mirrors cleared")
        return 0
    mons, pos, prim_now = live()
    want, prim = plan(mons)
    same = same_layout(pos, prim_now, want, prim)
    desc = ", ".join(f"{m['connector']}@{m['x']},{m['y']}" for m in want) + f"; primary {prim}"
    if a.action == "show":
        log(f"connected {mons}; live {pos} primary {prim_now}; want {desc}; {'same' if same else 'DIFFERS'}")
        return 0
    if a.action == "save":
        cfg = json.loads(CFG.read_text())
        sp = specs()
        modes = {m["connector"]: m["mode"] for m in cfg["monitors"]}
        cur = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=SHOW_S, check=True).stdout
        for c in pos:
            mm = re.search(rf"Monitor {re.escape(c)} \(.*?Current mode\s*\n\W*(\d+x\d+@[\d.]+)", cur, re.S)
            if mm:
                modes[c] = mm.group(1)
        cfg["monitors"] = [{"connector": c, "serial": sp.get(c, ("", "", ""))[2], "mode": modes.get(c, "3840x2160@60.000"),
                            "x": x, "y": y} for c, (x, y) in sorted(pos.items(), key=lambda kv: (kv[1][1], kv[1][0]))]
        if prim_now:
            cfg["primary"] = [prim_now] + [c for c in cfg["primary"] if c != prim_now]
        CFG.write_text(json.dumps(cfg, indent=2) + "\n")
        log(f"save: {pos}, primary {prim_now} -> {CFG.name}")
        return 0
    if a.action == "store":
        log(store(want, prim, mons))
        return 0
    if a.action == "check":
        log(f"layout {'OK' if same else 'DIFFERS'}{' (mirrors ' + str(mirrors()) + ')' if mirrors() else ''}: live {pos} primary {prim_now}; want {desc}")
        return 0 if same else 1
    if same:
        log(f"restore: already {desc}; " + store(want, prim, mons))
        return 0
    cmd = ["gdctl", "set", *gdctl_args(want, prim)]
    if a.dry_run:
        log("restore (dry run): " + " ".join(cmd))
        return 0
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=SET_S, check=False)
    except subprocess.TimeoutExpired:
        log(f"restore: gdctl set timed out after {SET_S} s; layout left as mutter has it")
        return 1
    log(f"restore (temporary apply) rc={r.returncode}: {desc} (was {pos}, primary {prim_now}) {r.stderr.strip()[:200]}")
    if r.returncode == 0:
        log(store(want, prim, mons))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
