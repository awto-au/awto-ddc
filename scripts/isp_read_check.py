#!/usr/bin/env python3
"""Read-path check: flash read with 64 B vs N B FIFO reads must give the same bytes; times both (#61). Read-only.

usage: isp_read_check.py <bus> --serial AWT2611000N [--kib 64] [--chunk 256]
  Enters ISP (MCU halted), reads the first --kib KiB with read_chunk 64 and with --chunk, compares, resets the scaler.
  ISP enter / exit also go to the unit log tmp/logs/unit-<serial>.log. Log: ./tmp/logs/isp_read_check.log
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
    ap.add_argument("--kib", type=int, default=64)
    ap.add_argument("--chunk", type=int, default=256, choices=(128, 256))
    a = ap.parse_args()
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    P.LOG = rtd_proto.setup_logs("isp_read_check").main
    ulog = (root / f"tmp/logs/unit-{a.serial}.log").open("a")

    def unit(s):
        ulog.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} [isp_read_check] {s}\n"); ulog.flush(); P.log(s)

    i2cbus.require_unit(a.bus, a.serial)
    isp = Rtd(a.bus)
    unit(f"ISP enter (MCU halted) bus {a.bus}")
    t_in = time.monotonic()
    isp.write(0x6F, 0x80)
    try:
        res = {}
        for ch in (64, a.chunk):
            isp.read_chunk = ch
            t0 = time.monotonic()
            res[ch] = isp.read_flash(0, a.kib * 1024)
            P.log(f"chunk {ch}: {a.kib} KiB in {time.monotonic() - t0:.2f} s")
        same = res[64] == res[a.chunk]
        P.log(f"{'SAME' if same else 'DIFFER'}: chunk 64 vs {a.chunk} over {a.kib} KiB")
    finally:
        isp.write(0xEE, 0x02)                     # scaler reset = ISP exit (monitor reboots)
        unit(f"ISP exit (reset) after {time.monotonic() - t_in:.1f} s")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
