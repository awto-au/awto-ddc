#!/usr/bin/env python3
"""Reboot the scaler MCU over the ISP slave 0x4A (no mains cycle): enter ISP (0x6F <- 0x80), then 0xEE <- 0x02.

usage: rtd_reset.py <bus> --serial AWT2611000N [--identity TEXT]
  Same reset the flasher sends at the end of every flash. Takes <1 s vs the 8 s relay OFF time.
  Does not help when 0x4A itself is silent (hard wedge): use `./dev.py power-cycle`.
Log: ./tmp/logs/rtd_reset.log (decoded) + rtd_reset.raw.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link
import i2cbus  # noqa: E402
import rtd_proto  # noqa: E402
from rtd_flash_sector import Rtd  # noqa: E402

ISP_EN, ISP_EN_VAL = 0x6F, 0x80
RESET, RESET_VAL = 0xEE, 0x02


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--identity", default="", help="unit proven another way (EDID silent); logged")
    a = ap.parse_args()
    lg = rtd_proto.setup_logs("rtd_reset")
    i2cbus.require_unit(a.bus, a.serial, a.identity or None)
    try:
        with dbg_link.flash_guard(a.bus):
            isp = Rtd(a.bus)
            isp.write(ISP_EN, ISP_EN_VAL)
            if not isp.read(ISP_EN) & ISP_EN_VAL:
                lg.log(f"bus {a.bus}: ISP enable did not read back; resetting anyway")
            isp.write(RESET, RESET_VAL)
    except dbg_link.FlashPreflightError as e:
        lg.log(f"bus {a.bus}: reset refused before ISP: {e}")
        return 6
    except OSError as e:
        lg.log(f"bus {a.bus}: ISP slave 0x4A not answering ({e}); use ./dev.py power-cycle")
        print(f"reset failed: 0x4A not answering ({e})")
        return 1
    lg.log(f"bus {a.bus}: scaler reset sent (0xEE <- 0x02)")
    print("scaler reset sent (0xEE <- 0x02)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

