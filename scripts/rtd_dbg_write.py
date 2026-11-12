#!/usr/bin/env python3
"""Write XDATA bytes in the RUNNING firmware over debug slave 0x35 (no halt), e.g. to raise an OSD event (#7).

usage: rtd_dbg_write.py <bus> --serial AWT2611000N ADDR=VAL [ADDR=VAL ...]
  ADDR/VAL hex. SDK ScalerDebug cmds: 0x01 [hi] (stage), 0x03 [val] (stage), 0x3B [lo] -> ScalerSetByte.
  --serial must equal the EDID serial at 0x50 on that bus (i2cbus.require_unit).
  Example: raise the input-info pop-up: OSD event byte g_stOsdInfo+5 (map) = _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG (9).
Log: ./tmp/logs/rtd_dbg_write.log (decoded I2C lines + one --label line per write)
     ./tmp/logs/rtd_dbg_write.raw.log (I2C byte trace)
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_i2c_bridge as B  # noqa: E402
import i2cbus  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402

DEV8 = 0x6A                                   # 7-bit 0x35


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("writes", nargs="+")
    ap.add_argument("--map", default=None, help="image .map: names XDATA addresses in the decoded log")
    ap.add_argument("--label", default="", help="meaning of the write(s), logged instead of decoding bytes later")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = B.setup_logs("rtd_dbg_write", map=a.map).main   # decoded I2C + label lines; byte trace in .raw.log
    i2cbus.dev_hint("dbg-write", "rtd_dbg_write.py")
    i2cbus.require_unit(a.bus, a.serial)
    w = B.Real(a.bus, allow_write=True)
    for item in a.writes:
        ad, v = (int(x, 16) for x in item.split("="))
        ok = w.write(DEV8, 0x01, bytes([ad >> 8])) and w.write(DEV8, 0x03, bytes([v])) \
            and w.write(DEV8, 0x3B, bytes([ad & 0xFF]))
        line = f"{a.label + ': ' if a.label else ''}0x{ad:04X} <- 0x{v:02X} {'ok' if ok else 'NO ACK'} (bus {a.bus})"
        print(line); log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
