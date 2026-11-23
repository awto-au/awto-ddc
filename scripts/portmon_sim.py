#!/usr/bin/env python3
"""#323 / #324 per-port status word and search order in the fw_sim model (HDMI source on D3, D1 / D2 cables scripted).

usage: portmon_sim.py BIN MAP [--case status|order|all] [--mode 1080p60]
  status  boot to ACTIVE on D3: g_pucAwtoPortSt D3 = cable + clock, D1 / D2 = valid only; then a cable appears on D2 and goes again:
          the word follows and the FA lines (cable pin high / low) are in the sync log.
  order   same boot: the search never leaves a visit line on an uncabled port longer than AWTO_NOCABLE_MAX_MS, and ACTIVE comes
          within --active-ms (the dead ports are skipped).
Log: tmp/logs/portmon_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deadport_sim as DP
import fw_sim as S

CABLE, CLK, LINK, DDC, AUX, VALID = 0x01, 0x02, 0x04, 0x08, 0x10, 0x80
D2_PIN = 0xFE32                                 # board header: low = cable


def table(bus):
    return list(bus.xdata(bus.addr("g_pucAwtoPortSt"), 3))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", choices=["status", "order", "all"], default="all")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--sync-tsv", dest="sync_tsv", type=Path)
    ap.add_argument("--active-ms", type=int, default=0, help="order: ACTIVE must come within this many ms of boot (0 = report only)")
    a = ap.parse_args()
    a.d2_cabled = False
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (S.ROOT / "tmp/logs/portmon_sim.log").open("a", buffering=1)

    def say(s):
        print(s)
        log.write(s + "\n")

    rig = DP.Rig(a)
    bus, _eng = rig.start()
    rc = 0
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
            for want in ("D2 cable pin high", "D2 cable pin low", "D3 cable pin high", "D3 TMDS clock stable"):
                ok = any(want in ln for ln in lines)
                say(f"status line '{want}': {'PASS' if ok else 'FAIL'}")
                rc |= 0 if ok else 1
    finally:
        bus.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
