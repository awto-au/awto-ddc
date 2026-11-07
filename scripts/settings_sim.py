#!/usr/bin/env python3
"""Offline check of the settings registry firmware (awto-ddc#67) in fw_sim: menu renders, key navigation, host
mailbox get/set, NVRAM round trip across a reboot, recovery to defaults.

usage: settings_sim.py BIN [--map MAP] [--out tmp/osd67] [--mode 1080p60] [--no-pages]
  Boot 1 (flash sectors 0xFD000-0xFEFFF erased): Menu opens our menu; every page and sub-page is walked with the
  front keys (osd_test key injection) and rendered to OUT/menu_<group>.png (+ main, edit, risky prompt); then host
  sets via the mailbox (settings_cli.Box), save.
  Boot 2 (same flash): the values are read back; test command 0x40 restores the defaults.
  Flash model: AwtoFlIo (fw/awto/settings/glue.inc) is stubbed with a Python NOR model (program clears bits, 4 KiB erase).
Exit 1 on any failed check. Log: ./tmp/logs/settings_sim.log; report OUT/settings_sim.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R
import settings_cli as C
import settings_table as T

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/settings_sim.log"
GAP_MS = 400.0          # fw ms after a key before the next one / a snapshot: a full page redraw is ~40 fw ms in the sim
NV_BASE, NV_LEN = 0xFD000, 0x2000


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class Flash:
    """NOR model of the two settings sectors, served to AwtoFlIo (struct StAwtoFl, big-endian build)."""

    def __init__(self):
        self.mem = bytearray(b"\xff" * NV_LEN)
        self.ops = {"read": 0, "write": 0, "erase": 0}

    def stub(self, m, _r):
        a = m.addr("g_stAwtoFl")
        b = m.rd(a, 9)
        op, bank = b[0], b[2]
        addr, n, ptr = b[3] << 8 | b[4], b[5] << 8 | b[6], b[7] << 8 | b[8]
        fa = (bank << 16 | addr) - NV_BASE
        ok = 0 <= fa and fa + max(n, 1) <= NV_LEN
        if ok and op == 1:
            m.wr(ptr, bytes(self.mem[fa:fa + n])); self.ops["read"] += 1
        elif ok and op == 2:
            src = m.rd(ptr, n)
            for i, v in enumerate(src):
                self.mem[fa + i] &= v
            self.ops["write"] += 1
        elif ok and op == 3:
            s = fa & ~0xFFF
            self.mem[s:s + 0x1000] = b"\xff" * 0x1000; self.ops["erase"] += 1
        m.wr(a + 1, bytes([1 if ok else 0]))
        return {}                                         # skip the SDK flash code


class Run:
    def __init__(self, a, flash: Flash, tag: str):
        self.s = R.Session(a.bin, a.map, a.mode)
        self.s.bus.m.stub("AwtoFlIo", flash.stub)
        self.a, self.tag = a, tag
        self.box = None

    def boot(self):
        self.s.boot()
        self.box = C.Box(self.s.bus, Path(self.a.map).read_text(errors="replace"), sim=True)

    def key(self, name: str, n: int = 1):
        for _ in range(n):
            self.s.act(name)
            self.s.run_to(self.s.ms() + GAP_MS)

    def shot(self, name: str):
        out = self.a.out / f"menu_{name}.png"
        R.save(self.s.snap(), out, "grey", 2)
        return str(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/osd67")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--no-pages", action="store_true", help="skip the page walk (NVRAM / mailbox checks only)")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    a.out.mkdir(parents=True, exist_ok=True)
    rep = {"image": str(a.bin), "checks": [], "png": []}
    fails = 0

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        rep["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    flash = Flash()
    r = Run(a, flash, "b1")
    try:
        r.boot()
        sch = r.box.schema()
        check("schema", sch == T.SCHEMA, f"fw 0x{sch:04X} table 0x{T.SCHEMA:04X}")
        b = T.BY_NAME
        check("boot defaults", r.box.get_row(b["brightness"]) == b["brightness"]["default"] and
              r.box.get_row(b["panel_t3"]) == b["panel_t3"]["default"])
        if not a.no_pages:
            r.key("menu")
            rep["png"].append(r.shot("main"))
            tops = [i for i, p in enumerate(T.PAGES) if p["parent"] == 0xFF]
            for k, pi in enumerate(tops):
                if k:
                    r.key("right")
                r.key("menu")
                rep["png"].append(r.shot(T.PAGES[pi]["group"]))
                subs = [e & 0x7F for e in T.PAGES[pi]["entries"] if e & 0x80]
                for j, sp in enumerate(subs):
                    if j:
                        r.key("right")
                    r.key("menu")
                    rep["png"].append(r.shot(T.PAGES[sp]["group"]))
                    r.key("exit")
                r.key("exit")
            # edit: Picture > Backlight +2 (live), Menu sets
            r.key("left", len(tops) - 1)                   # back to Picture (wraps the other way)
            r.key("menu"); r.key("menu"); r.key("right", 2)
            rep["png"].append(r.shot("edit"))
            r.key("menu")
            v = r.box.get_row(b["brightness"])
            check("menu edit backlight +2", v == b["brightness"]["default"] + 2, f"got {v}")
            r.key("exit")
            # risky prompt: Panel timing > T3 +1 step, then Exit = undo
            r.key("right", tops.index(next(i for i, p in enumerate(T.PAGES) if p["group"] == "panel")))
            r.key("menu")
            r.key("right", [T.ROWS[e]["name"] for e in T.PAGES[next(i for i, p in enumerate(T.PAGES) if p["group"] == "panel")]["entries"]].index("panel_t3"))
            r.key("menu"); r.key("right"); r.key("menu")
            rep["png"].append(r.shot("risky"))
            v = r.box.get_row(b["panel_t3"])
            check("risky pending value", v == b["panel_t3"]["default"] + b["panel_t3"]["step"], f"got {v}")
            r.key("exit")
            v = r.box.get_row(b["panel_t3"])
            check("risky undo (Exit)", v == b["panel_t3"]["default"], f"got {v}")
            r.key("exit"); r.key("exit")
        # host mailbox: plain, enum, risky (confirmed), MCCS code
        r.box.set_row(b["contrast"], 33)
        r.box.set_row(b["gamma"], 3)
        r.box.set_row(b["panel_t3"], 900)
        cur, mx, _ = r.box.call(1, 0x10)
        check("VCP 0x10 = brightness row", cur == r.box.get_row(b["brightness"]) and mx == 100, f"{cur}/{mx}")
        r.box.call(2, 0xE3, 2)                             # save now
        want = {n: r.box.get_row(b[n]) for n in ("brightness", "contrast", "gamma", "panel_t3")}
        check("flash written", flash.ops["write"] > 0, str(flash.ops))
    finally:
        r.s.bus.close()

    r2 = Run(a, flash, "b2")
    try:
        r2.boot()
        got = {n: r2.box.get_row(T.BY_NAME[n]) for n in want}
        check("NVRAM round trip across reboot", got == want, f"want {want} got {got}")
        r2.s.act("defaults")
        r2.s.run_to(r2.s.ms() + GAP_MS)
        got = {n: r2.box.get_row(T.BY_NAME[n]) for n in want}
        dfl = {n: T.BY_NAME[n]["default"] for n in want}
        check("test command 0x40 -> defaults", got == dfl, f"got {got}")
    finally:
        r2.s.bus.close()
    rep["flash_ops"] = flash.ops
    (a.out / "settings_sim.json").write_text(json.dumps(rep, indent=1))
    say(f"settings_sim: {len(rep['checks']) - fails}/{len(rep['checks'])} checks pass, {len(rep['png'])} PNGs in {a.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
