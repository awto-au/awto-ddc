#!/usr/bin/env python3
"""Write scaler registers over ISP (MCU halted), read each back, leave the MCU halted (live A/B tests, #7).

usage: rtd_reg_poke.py <bus> --serial AWT2611000N ADDR=VAL [ADDR=VAL ...] [--reset]
  ADDR/VAL hex (e.g. FE34=1). Any page incl. FE/FF XFRs via F4/F5 + page select 0x9F (rtd_osd.Osd).
  --serial must equal the EDID serial at 0x50 on that bus (guards against a recabled unit); EDID silent
  (MCU halted) -> --identity "<how proven>" is required and logged.
  --reset: ISP reset (0xEE) at the end = monitor reboots and the pokes are lost.
Log: ./tmp/logs/rtd_reg_poke.log
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus  # noqa: E402
import rtd_isp_probe as P  # noqa: E402
import rtd_proto  # noqa: E402
from rtd_osd import Osd  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("pokes", nargs="+")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--identity", help="when EDID is silent (MCU halted in ISP): how the bus was proven to be this unit")
    a = ap.parse_args()
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    P.LOG = rtd_proto.setup_logs("rtd_reg_poke").main
    i2cbus.dev_hint("poke", "rtd_reg_poke.py")
    s = i2cbus.require_unit(a.bus, a.serial, a.identity)
    if s is None:
        P.log(f"EDID silent; identity per caller: {a.identity}")
    o = Osd(a.bus)
    o.enter()
    for pk in a.pokes:
        ad, v = (int(x, 16) for x in pk.split("="))
        before = o.rd(ad)
        o.wr(ad, v)
        after = o.rd(ad)
        line = f"0x{ad:04X}: 0x{before:02X} -> wrote 0x{v:02X}, reads 0x{after:02X}"
        print(line); P.log(line)
    if a.reset:
        o.reset()
    else:
        P.log("MCU left halted (ISP); --reset or power-cycle to revert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
