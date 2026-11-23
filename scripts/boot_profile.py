#!/usr/bin/env python3
"""Boot cost of a running image over the debug link (#216): main-loop segment totals since the last reset + time to ACTIVE.

usage: boot_profile.py BUS --serial S --map MAP [--table T]
  The image needs -D_AWTO_LOOP_PROF=_ON (fw/diag/loopprof.c). Read right after a reset, without re-arming: a segment that
  blocked at boot shows its time in full. Also prints the sync log's timing lines (INITIAL / SEARCH / ACTIVE).
  Waits up to 5 s for the unit to answer (the repo's monitor-wait limit; it answers ~1.5 s after the reset).
Log: ./tmp/logs/boot_profile.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link
import dbg_xdata as X
import i2cbus
import loop_prof as L
import rtd_i2c_bridge as B
from _repo import ROOT

LOG = ROOT / "tmp/logs/boot_profile.log"
WAIT_S = 5.0
POLL_S = 0.5


def say(s):
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    a = ap.parse_args()
    base = L.base_of(a.map.read_text(errors="replace"))
    if base is None:
        say(f"{a.map.name}: no g_stAwtoLoopProf (build with -D_AWTO_LOOP_PROF=_ON)")
        return 1
    t0, raw = time.monotonic(), None
    while raw is None and time.monotonic() - t0 < WAIT_S:
        try:
            i2cbus.require_unit(a.bus, a.serial)          # EDID is silent for ~1 s after a reset: part of the bounded wait
            with dbg_link.linked(a.bus):
                io = B.Real(a.bus, allow_write=True, regread=True)
                try:
                    raw = X.read_blocks(io, base, 7 + 4 * len(L.SLOTS))
                finally:
                    io.close()
        except SystemExit:
            time.sleep(POLL_S)
    if raw is None:
        say("the unit did not answer within 5 s")
        return 1
    per, passes = int.from_bytes(raw[1:3], "big"), int.from_bytes(raw[3:7], "big")
    t2 = [int.from_bytes(raw[7 + 4 * i:11 + 4 * i], "big") for i in range(len(L.SLOTS))]
    say(f"{a.map.name}: {passes} main-loop passes since reset, Timer2 {per} counts/ms; ms per segment since reset:")
    for name, c in sorted(zip(L.SLOTS, t2), key=lambda x: -x[1])[:6]:
        say(f"  {c / per:7.0f} ms  {name}")
    import subprocess
    out = subprocess.run([sys.executable, str(ROOT / "scripts/sync_log.py"), str(a.bus), "--map", str(a.map), "--serial", a.serial],
                         capture_output=True, text=True, check=False).stdout
    for l in out.splitlines():
        if re.search(r"system:in (INITIAL|SEARCH|DISPLAY SETTING) for", l):
            say("  " + re.sub(r"^\S+ +", "", l.strip())[:130])
    return 0


if __name__ == "__main__":
    sys.exit(main())
