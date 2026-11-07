#!/usr/bin/env python3
"""Main-loop cost per handler from g_stAwtoLoopProf (image built with -D_AWTO_LOOP_PROF=_ON, fw/sdcc/awto_loopprof.inc).

usage: loop_prof.py <bus> --serial S --map MAP [--secs 3] [--label L]
  Arms (ucReset=1), waits --secs, reads the block: one line per slot = us per pass and share of the pass.
  Slot k = the code from AWTO_LP(k) up to AWTO_LP(k+1); the last slot wraps to the next pass start.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (root / "tmp/logs/loop_prof.log").open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    m = re.search(r"^D:\s+([0-9A-F]{8})\s+_g_stAwtoLoopProf\b", a.map.read_text(errors="replace"), re.MULTILINE)
    if not m:
        say(f"g_stAwtoLoopProf not in {a.map}: image without -D_AWTO_LOOP_PROF=_ON"); return 1
    base = int(m.group(1), 16) & 0xFFFF
    i2cbus.require_unit(a.bus, a.serial)
    io = B.Real(a.bus, allow_write=True, regread=True)
    try:
        if not (io.write(X.DEV8, 0x01, bytes([base >> 8])) and io.write(X.DEV8, 0x03, b"\x01")      # as sw_timeline.py
                and io.write(X.DEV8, 0x3B, bytes([base & 0xFF]))):
            say("arm write NAKed"); return 1
        time.sleep(a.secs)                                     # sampling window; firmware accumulates on its own
        raw = X.read_blocks(io, base, 7 + 4 * len(SLOTS))
    finally:
        io.close()
    if raw is None:
        say("read failed (0x35 silent)"); return 1
    per, passes = int.from_bytes(raw[1:3], "big"), int.from_bytes(raw[3:7], "big")
    t2 = [int.from_bytes(raw[7 + 4 * i:11 + 4 * i], "big") for i in range(len(SLOTS))]
    if passes < 2 or per == 0:
        say(f"no passes counted (passes {passes}, per {per})"); return 1
    us = [c * 1000.0 / per / (passes - 1) for c in t2]
    tot = sum(us)
    say(f"{a.serial} {a.label}: {passes} passes in ~{a.secs:.1f} s, {tot:.0f} us/pass ({1e6 / tot:.0f}/s incl. probe cost)")
    for name, u in sorted(zip(SLOTS, us), key=lambda x: -x[1]):
        say(f"  {u:8.1f} us  {100 * u / tot:5.1f} %  {name}")
    with (root / "tmp/logs/loop_prof.tsv").open("a") as t:
        t.write("\t".join([time.strftime('%Y-%m-%dT%H:%M:%S%z'), a.serial, a.label, f"{tot:.0f}"] + [f"{u:.1f}" for u in us]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
