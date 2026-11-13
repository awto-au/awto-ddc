#!/usr/bin/env python3
"""Main-loop cost per handler from g_stAwtoLoopProf (image built with -D_AWTO_LOOP_PROF=_ON, fw/diag/loopprof.c).

usage: loop_prof.py <bus> --serial S --map MAP [--secs 3] [--label L] [--ps-only]
  Arms (ucReset=1), waits --secs, reads the block: one line per slot = us per pass and share of the pass.
  Slot k = the code from AWTO_LP(k) up to AWTO_LP(k+1); the last slot wraps to the next pass start.
  --ps-only: only passes in power status SAVING count (ucPsOnly, #144; images from tmds2 on). Library: arm(), report().
Log: ./tmp/logs/loop_prof.log ; summary rows: ./tmp/logs/loop_prof.tsv
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

SLOTS = ["key+diag+testcmd", "SysPowerHandler", "SysJudgeHandler", "SysTimerHandler", "SysSourceHandler", "SysModeHandler",
         "SysDpRxHandler", "SysTMDSRxHandler", "HDCP2 / MST", "OSD handler", "DDC/CI handler", "colour + ScalerDebug"]
PS_ONLY_OFF = 7 + 4 * len(SLOTS)          # StAwtoLoopProf.ucPsOnly
ROOT = Path(__file__).resolve().parent.parent


def base_of(map_text: str):
    m = re.search(r"^D:\s+([0-9A-F]{8})\s+_g_stAwtoLoopProf\b", map_text, re.MULTILINE)
    return int(m.group(1), 16) & 0xFFFF if m else None


def poke(io, addr: int, v: int) -> bool:
    return (io.write(X.DEV8, 0x01, bytes([addr >> 8])) and io.write(X.DEV8, 0x03, bytes([v]))      # as sw_timeline.py
            and io.write(X.DEV8, 0x3B, bytes([addr & 0xFF])))


def arm(io, base: int, ps_only: bool = False) -> bool:
    return (not ps_only or poke(io, base + PS_ONLY_OFF, 1)) and poke(io, base, 1)


def report(io, base: int, say, serial: str, label: str, secs: float) -> int:
    raw = X.read_blocks(io, base, 7 + 4 * len(SLOTS))
    if raw is None:
        say("read failed (0x35 silent)"); return 1
    per, passes = int.from_bytes(raw[1:3], "big"), int.from_bytes(raw[3:7], "big")
    t2 = [int.from_bytes(raw[7 + 4 * i:11 + 4 * i], "big") for i in range(len(SLOTS))]
    if passes < 2 or per == 0:
        say(f"no passes counted (passes {passes}, per {per})"); return 1
    us = [c * 1000.0 / per / (passes - 1) for c in t2]
    tot = sum(us)
    say(f"{serial} {label}: {passes} passes in ~{secs:.1f} s, {tot:.0f} us/pass ({1e6 / tot:.0f}/s incl. probe cost), "
        f"Timer2 {per} counts/ms")
    for name, u in sorted(zip(SLOTS, us), key=lambda x: -x[1]):
        say(f"  {u:8.1f} us  {100 * u / tot:5.1f} %  {name}")
    with (ROOT / "tmp/logs/loop_prof.tsv").open("a") as t:
        t.write("\t".join([time.strftime('%Y-%m-%dT%H:%M:%S%z'), serial, label, f"{tot:.0f}"] + [f"{u:.1f}" for u in us]) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--label", default="")
    ap.add_argument("--ps-only", action="store_true")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/loop_prof.log").open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    base = base_of(a.map.read_text(errors="replace"))
    if base is None:
        say(f"g_stAwtoLoopProf not in {a.map}: image without -D_AWTO_LOOP_PROF=_ON"); return 1
    i2cbus.require_unit(a.bus, a.serial)
    io = B.Real(a.bus, allow_write=True, regread=True)
    try:
        if not arm(io, base, a.ps_only):
            say("arm write NAKed"); return 1
        time.sleep(a.secs)                                     # sampling window; firmware accumulates on its own
        return report(io, base, say, a.serial, a.label, a.secs)
    finally:
        io.close()


if __name__ == "__main__":
    sys.exit(main())
