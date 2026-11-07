#!/usr/bin/env python3
"""Can this bus carry a burst write to the ISP page FIFO (0x70), and how long does it take? Nothing is programmed (#28).

usage: isp_write_probe.py <bus> --serial S [--sizes 64,128,255,256]
  Enters ISP (MCU halted), writes N bytes of 0xFF to 0x70 per size (fills the page buffer; no program start), times
  each write, then resets the scaler (ISP exit). NVIDIA DP-AUX i2c caps a transfer at 256 B: reg byte + 256 > cap.
  ISP enter/exit go to the unit log. Log: ./tmp/logs/isp_write_probe.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_isp_probe as P
import rtd_proto
from rtd_flash_sector import Rtd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--sizes", default="64,128,255,256")
    a = ap.parse_args()
    root = P.repo_root()
    P.LOG = rtd_proto.setup_logs("isp_write_probe").main
    ulog = (root / f"tmp/logs/unit-{a.serial}.log").open("a")

    def unit(s):
        ulog.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} [isp_write_probe] {s}\n"); ulog.flush(); P.log(s)

    i2cbus.require_unit(a.bus, a.serial)
    isp = Rtd(a.bus)
    unit(f"ISP enter (MCU halted) bus {a.bus}")
    t_in = time.monotonic()
    isp.write(0x6F, 0x80)
    try:
        for n in map(int, a.sizes.split(",")):
            t0 = time.monotonic()
            try:
                isp.write_block(0x70, b"\xff" * n)
                P.log(f"write 0x70 x {n} B: ok, {(time.monotonic() - t0) * 1000:.1f} ms")
            except OSError as e:
                P.log(f"write 0x70 x {n} B: FAIL {e!r} after {(time.monotonic() - t0) * 1000:.1f} ms")
        t0 = time.monotonic()
        for _ in range(5):
            isp.read(0x6F)
        P.log(f"1-byte register read: {(time.monotonic() - t0) / 5 * 1000:.1f} ms")
    finally:
        isp.write(0xEE, 0x02)
        unit(f"ISP exit (reset) after {time.monotonic() - t_in:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
