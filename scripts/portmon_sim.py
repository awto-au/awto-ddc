#!/usr/bin/env python3
"""#323 / #324 per-port status word and search order in the fw_sim model (HDMI source on D3, D1 / D2 cables scripted).

usage: portmon_sim.py BIN MAP [--case status|order|all] [--mode 1080p60]
  status  boot to ACTIVE on D3: g_pucAwtoPortSt D3 = cable + clock, D1 / D2 = valid only; then a cable appears on D2 and goes again:
          the word follows and the FA lines (`cable pin: D2 high`, one per poll, #359) are in the sync log.
  nolive  no cable on any port: every port is still searched (the full pass, no port skipped).
  order   boot with D2 uncabled (dead: the search never reaches it) and with D2 cabled but silent (left within SILENT_MAX_MS,
          not the 2 s HDMI dwell); both end ACTIVE on D3.
Log: tmp/logs/portmon_sim.log
"""
import argparse
import re
import sys
from pathlib import Path

from _log import Logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as DD
import deadport_sim as DP
import fw_sim as S

CABLE, CLK, LINK, DDC, AUX, VALID = 0x01, 0x02, 0x04, 0x08, 0x10, 0x80
D2_PIN = 0xFE32                                 # board header: low = cable
SILENT_MAX_MS = 1800                            # _SOURCE_DEFAULT_SEARCH_TIME_SILENT_PORT 1000 ms + 2 sim passes (the sim main loop is coarse)


def table(bus):
    return list(bus.xdata(bus.addr("g_pucAwtoPortSt"), 3))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", choices=["status", "order", "nolive", "all"], default="all")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--sync-tsv", dest="sync_tsv", type=Path)
    a = ap.parse_args()
    a.d2_cabled = False
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = Logger(S.ROOT / "tmp/logs/portmon_sim.log", stamp_echo=False)

    say = log.say

    rc = 0
    rig = DP.Rig(a)
    bus, _eng = rig.start()
    try:
        if not rig.up:
            say("FAIL no ACTIVE at boot")
            return 1
        st = table(bus)
        say(f"{a.bin.name}: after boot D1..D3 status {[f'{v:02X}' for v in st]}")
        if a.case in ("status", "all"):
            ok = st[2] & (VALID | CABLE | CLK) == (VALID | CABLE | CLK) and st[0] == VALID and st[1] == VALID
            say(f"status boot: {'PASS' if ok else 'FAIL'} (want D1 80, D2 80, D3 83)")
            rc |= 0 if ok else 1
            pins = next(d for d in bus.m.devs if isinstance(d, DP.Pins))
            pins.cells[D2_PIN] = 0
            bus.m.put(f"set memory xram 0x{D2_PIN:x} 0x0")
            bus.wait(0.3)
            st = table(bus)
            ok = st[1] & CABLE != 0
            say(f"status D2 cable on: {'PASS' if ok else 'FAIL'} {[f'{v:02X}' for v in st]}")
            rc |= 0 if ok else 1
            pins.cells[D2_PIN] = 1
            bus.m.put(f"set memory xram 0x{D2_PIN:x} 0x1")
            bus.wait(0.3)
            st = table(bus)
            ok = st[1] & (CABLE | DDC | CLK) == 0
            say(f"status D2 cable off: {'PASS' if ok else 'FAIL'} {[f'{v:02X}' for v in st]}")
            rc |= 0 if ok else 1
            lines = DP.synclog(a, bus, lambda _s: None)
            cab = [ln.split("cable pin: ", 1)[1] for ln in lines if "cable pin: " in ln]
            for want in ("D2 high", "D2 low", "D3 high", "D3 TMDS clock stable"):
                ok = any(want in ln for ln in lines) if "TMDS" in want else any(want in c.split(", ") for c in cab)
                say(f"status line '{want}': {'PASS' if ok else 'FAIL'}")
                rc |= 0 if ok else 1
        bus.close()
        if a.case in ("order", "all"):
            for cabled in (False, True):
                a.d2_cabled = cabled
                rig = DP.Rig(a)
                bus, _eng = rig.start()
                try:
                    lines = DP.synclog(a, bus, lambda _s: None)
                    left = [(m.group(1), int(m.group(2))) for m in (re.search(r"search left (D\d) after (\d+)ms", ln) for ln in lines) if m]
                    d2 = [ms for p, ms in left if p == "D2"]
                    taken = any("input taken:D3" in ln for ln in lines)
                    ok = rig.up and taken and ((not d2) if not cabled else (len(d2) == 1 and d2[0] <= SILENT_MAX_MS))
                    say(f"order D2 {'cabled, silent' if cabled else 'uncabled'}: {'PASS' if ok else 'FAIL'} D2 visits {d2}, D3 taken {taken}")
                    rc |= 0 if ok else 1
                finally:
                    bus.close()
        if a.case in ("nolive", "all"):
            eng = DD.DdcEngine()
            bus = S.SimBus(a.bin, a.map, video=a.mode, port="D3", devs=[DP.Pins({**DP.NOCABLE_D1, 0xFE32: 1, 0xFE2C: 1}), eng])
            try:
                bus.wait(4.0)
                lines = DP.synclog(a, bus, lambda _s: None)
                seen = sorted({m.group(1) for m in (re.search(r"search reached (D\d)", ln) for ln in lines) if m})
                ok = seen == ["D1", "D2", "D3"]
                say(f"nolive: {'PASS' if ok else 'FAIL'} ports reached {seen} (want D1 D2 D3)")
                rc |= 0 if ok else 1
            finally:
                bus.close()
    finally:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
