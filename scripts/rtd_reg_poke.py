#!/usr/bin/env python3
"""Write scaler registers over ISP (MCU halted), read each back, leave the MCU halted (live A/B tests, #7).

usage: rtd_reg_poke.py <bus> --serial AWT2611000N ADDR=VAL [ADDR=VAL ...] [--reset]
  ADDR/VAL hex (e.g. FE34=1). Any page incl. FE/FF XFRs via F4/F5 + page select 0x9F (rtd_osd.Osd).
  --serial must equal the EDID serial at 0x50 on that bus (guards against a recabled unit); EDID silent
  (MCU halted) -> --identity "<how proven>" is required and logged.
  --reset: ISP reset (0xEE) at the end = monitor reboots and the pokes are lost.
Log: ./tmp/logs/rtd_reg_poke.log
"""
import argparse, fcntl, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P  # noqa: E402
import rtd_proto  # noqa: E402
from rtd_osd import Osd  # noqa: E402


def edid_serial(bus: int) -> str | None:
    fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
    try:
        fcntl.ioctl(fd, 0x0703, 0x50)
        os.write(fd, b"\x00")
        e = os.read(fd, 128)
        rtd_proto.trace(0x50, "w", 0, b"")
        rtd_proto.trace(0x50, "r", 0, e, 128)
    except OSError as ex:
        rtd_proto.trace(0x50, "r", 0, None, 128, str(ex))
        return None
    finally:
        os.close(fd)
    for i in range(54, 126, 18):
        if e[i:i + 3] == b"\0\0\0" and e[i + 3] == 0xFF:
            return e[i + 5:i + 18].split(b"\n")[0].decode("latin-1").strip()
    return None


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
    s = edid_serial(a.bus)
    if s != a.serial and not (s is None and a.identity):
        sys.exit(f"bus {a.bus}: EDID serial {s!r} != {a.serial!r}; refusing (EDID silent: pass --identity)")
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
