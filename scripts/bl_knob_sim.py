#!/usr/bin/env python3
"""Backlight on-delay test knob in fw_sim (docs/bl-delay-sweep.md): cold boot with the knob pre-seeded in the no-init RAM.

usage: AWTO_SIM_CORE=fast bl_knob_sim.py BIN MAP [--values 0,150,400]
  Per value: knob written before the first instruction (as the host does before an ISP reset), boot to ACTIVE.
  PASS per value: line 11 E2 shows the value; line 11 E1 'ms after video ready' in [value, value + SLACK_MS]; the backlight pin
  edge matches the E1 'ms after MCU boot' (+-EDGE_SLACK_MS). No knob: no E1 / E2 line, pin on before the link is up (default).
Log: tmp/logs/bl_knob_sim.log
"""
import argparse
import re
import sys
from argparse import Namespace
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_sim as P

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/bl_knob_sim.log"
KNOB_ADDR, MAGIC, SEED = 0xF698, 0x4C, 0xB5          # RL6449_Project.h AWTO_BLK_*
SLACK_MS = 30           # main-loop pass (the machine steps once per pass) after the due time; sim worst ~25 ms
EDGE_SLACK_MS = 12      # sim t2 origin is ~11 ms before the fw ms origin (constant at 0 / 150 / 400)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def knob_bytes(ms: int) -> bytes:
    lo, hi = ms & 0xFF, ms >> 8
    return bytes([MAGIC, lo, hi, SEED ^ MAGIC ^ lo ^ hi])


def one(bin_, map_, value: int | None) -> int:
    r = P.Run(Namespace(bin=bin_, map=map_, mode="1080p60", report=False))
    try:
        if value is not None:
            r.m.wr(KNOB_ADDR, knob_bytes(value))
        ok = r.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        r.check(ok, f"knob {value}: boot to ACTIVE")
        r.bus.dbg_link_on()
        r.bus.wait(P.SETTLE_MS / 1000)
        r.ring_lines("boot")
        e2 = [ev for ev in r.ring_ev if ev[:2] == (0x11, 0xE2)]
        e1 = [ev for ev in r.ring_ev if ev[:2] == (0x11, 0xE1)]
        pins = [e for e in r.events if e[2] == "BL pin" and e[3] == 1]
        if value is None:
            r.check(not e1 and not e2, "no knob: no E1 / E2 line")
            r.check(bool(pins), "no knob: backlight pin on")
        else:
            r.check(len(e2) == 1 and e2[0][3] == value, "E2 line shows the knob", f"{[e[3] for e in e2]}")
            r.check(len(e1) == 1, "one E1 line")
            if e1:
                boot_ms, ref_ms = e1[0][3] & 0xFFFF, e1[0][3] >> 16
                r.check(value <= ref_ms <= value + SLACK_MS, "pin on after video ready + knob", f"{ref_ms} ms (knob {value})")
                r.check(bool(pins) and 0 <= e1[0][2] - pins[0][0] <= EDGE_SLACK_MS, "pin edge matches the E1 ring time",
                        f"edge {pins[0][0] if pins else None}, ring {e1[0][2]}, value {boot_ms}")
    finally:
        r.bus.close()
    return r.fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--values", default="0,150,400")
    a = ap.parse_args()
    fails = one(a.bin, a.map, None)
    for v in (int(x) for x in a.values.split(",") if re.fullmatch(r"\d+", x)):
        fails += one(a.bin, a.map, v)
    say(f"{'PASS' if fails == 0 else 'FAIL'} bl_knob_sim {a.bin.name}: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
