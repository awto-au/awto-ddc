#!/usr/bin/env python3
"""Held test visual in the fw_sim model (#28): does a held logo / pop-up survive the SDK's own OSD paths for N s?

usage: hold_sim.py BIN MAP [--cmd 0x24|0x26] [--secs 10] [--mode 2160p60]
  Boot to ACTIVE, raise the info pop-up (event 10: arms the SDK's _USER_TIMER_EVENT_OSD_DISABLE, the path that cleared
  the held logo on unit 3, 14:28), then the hold command, run --secs of firmware time.
  PASS: hold bits still set and no OsdFuncDisableOsd after the hold (OsdDispDisableOsd calls are allowed: blocked + logged).
Log: tmp/logs/hold_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S
import rtd_proto as P

DEV8 = 0x6A
TESTCMD = 0xF6F8                       # g_stAwtoDiag + 0x28
HOLD = 0xF6FF                          # g_stAwtoDiag + 0x2F


def wr(bus, addr: int, val: int) -> bool:
    return bus.write(DEV8, 0x01, bytes([addr >> 8])) and bus.write(DEV8, 0x03, bytes([val])) and bus.write(DEV8, 0x3B, bytes([addr & 0xFF]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--cmd", default="0x24")
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--mode", default="2160p60")
    a = ap.parse_args()
    log = (S.ROOT / "tmp/logs/hold_sim.log").open("a", buffering=1)

    def say(s):
        print(s); log.write(s + "\n")

    cmd = int(a.cmd, 0)
    bus = S.SimBus(a.bin, a.map, video=a.mode)
    calls = {"OsdFuncDisableOsd": 0, "OsdDispDisableOsd": 0}
    armed = [False]
    for fn in calls:
        bus.m.stub(fn, lambda m, r, fn=fn: (calls.__setitem__(fn, calls[fn] + armed[0])) and None)
    try:
        if not bus.run_until_mode(3):
            say(f"FAIL {a.bin.name}: no ACTIVE"); return 1
        osd = P.osd_offsets_from_map(a.map.read_text(errors="replace"))
        base = bus.addr("g_stOsdInfo")
        ok = wr(bus, base + osd["ucOsdEventMsg"], 10)          # info pop-up: arms the 6 s OSD-disable timer
        bus.wait(1.0)
        ok = ok and wr(bus, TESTCMD, cmd)
        bus.wait(0.5)                                          # the logo draw itself calls OsdFuncDisableOsd: count after it
        armed[0] = True
        bus.wait(a.secs)
        hold = bus.xdata(HOLD)[0]
        try:
            blocks = bus.xdata(bus.addr("g_stAwtoSw") + 11)[0]     # StAwtoSw.ucHoldBlocks
        except Exception:                                      # image without #60 log
            blocks = -1
        want = 0x01 if cmd == 0x24 else 0x02
        good = ok and (hold & want) and calls["OsdFuncDisableOsd"] == 0
        say(f"{'PASS' if good else 'FAIL'} {a.bin.name} cmd 0x{cmd:02X} {a.secs:g} s: hold 0x{hold:02X}, OsdFuncDisableOsd {calls['OsdFuncDisableOsd']}, "
            f"OsdDispDisableOsd {calls['OsdDispDisableOsd']} (blocked), hold blocks {blocks}, writes {'ok' if ok else 'NAK'}")
        return 0 if good else 1
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main())
