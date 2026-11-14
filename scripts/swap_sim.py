#!/usr/bin/env python3
"""#79 runtime DDC channel swap in fw_sim: DDC/CI owns the host port by default, VCP E3 = A5 NN moves debug slave 0x35 there.

usage: swap_sim.py BIN [--map MAP] [--mode 1080p60]
  Checks (host on D2's DDC): after boot FF22 parked (7) and IIC_1 (FE86) on DDC2, 0x35 NAKs; setvcp E3 A50A -> FF22 on DDC2,
  IIC_1 parked, 0x35 answers, 600 s left; test cmd 0x3B -> back; test cmd 0x3C -> on, 0 s (until told back); 0x3B -> back.
  DDC/CI engine model: scripts/ddc_sim.py. Firmware: fw/diag/dbgport.c, fw/ddcci/ddcci.c (wb-p14swap).
Exit 1 on a failed check. Log: ./tmp/logs/swap_sim.log
"""
from __future__ import annotations

import argparse
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import ddc_sim as D  # noqa: E402
import dbg_xdata  # noqa: E402

LOG = S.ROOT / "tmp/logs/swap_sim.log"
DEV8 = 0x6A
TESTCMD = 0xF6F8            # isr_g_stAwtoDiag (0xF6D0, RL6449_Project.h) + 0x28
CMD_S = 0.05                # test cmd = main-loop pass (~1 ms) + an OSD draw can block it 375 ms: 50 ms covers the idle sim
PARK = 1                    # RL6449_Project.h AWTO_DBG_PARK_CH (DDC0)


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    eng = D.DdcEngine()
    bus = S.SimBus(a.bin, a.map, devs=[eng], video=a.mode, dbg_link=False)
    d = D.Mccs(bus, eng)
    sec_at = bus.addr("g_usAwtoDbgLinkSec")
    fails = 0

    def state(want_link: bool, want_sec: int | None, what: str):
        nonlocal fails
        ff22, fe86 = bus.xdata(0xFF22, 1)[0] & 7, bus.xdata(0xFE86, 1)[0] & 7
        r = dbg_xdata.read_bytes(bus, 0xF6D0, 2)
        sec = int.from_bytes(bus.xdata(sec_at, 2), "big")
        ok = (ff22, fe86) == ((3, PARK) if want_link else (PARK, 3)) and ((r is not None) == want_link) \
            and (want_sec is None or sec == want_sec)
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {what}: FF22 ch {ff22}, IIC_1 ch {fe86}, 0x35 {'answers' if r else 'NAK'}, "
            f"{sec} s left")

    def cmd(v: int):
        bus.write(DEV8, 0x01, bytes([TESTCMD >> 8])) and bus.write(DEV8, 0x03, bytes([v])) \
            and bus.write(DEV8, 0x3B, bytes([TESTCMD & 0xFF]))
        bus.wait(CMD_S)

    try:
        bus.wait(0.3)
        state(False, None, "boot: DDC/CI on the host port")
        g = d.get(0x60)
        say(f"{'PASS' if g and g['cur'] == 0x11 else 'FAIL'} getvcp 60 over DDC/CI: {g}")
        fails += not (g and g["cur"] == 0x11)
        d.set(0xE3, 0x1234)
        bus.wait(CMD_S)
        state(False, None, "setvcp E3 without the A5 magic: ignored")
        d.set(0xE3, 0xA50A)
        bus.wait(CMD_S)
        state(True, 600, "setvcp E3 A50A: debug link 10 min")
        cmd(0x3B)
        state(False, None, "test cmd 0x3B: back to DDC/CI")
        d.set(0xE3, 0xA5FF)
        bus.wait(CMD_S)
        state(True, 0, "setvcp E3 A5FF: debug link until told back")
        cmd(0x3B)
        state(False, None, "test cmd 0x3B: back to DDC/CI")
    finally:
        bus.close()
    say(f"swap_sim: {'PASS' if not fails else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
