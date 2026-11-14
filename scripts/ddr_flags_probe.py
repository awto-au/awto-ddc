#!/usr/bin/env python3
"""awto-ddc#26: DDR PHY read-window / calibration flags on a running unit (debug slave 0x35, main NOT paused).

usage: ddr_flags_probe.py --unit N --bus B --serial S [--n 20] [--clear]
  Reads pages 8F/CF flag regs (VALID_WIN_DET*, INT_STATUS*), optionally clears them (write 00), re-reads n times.
  Run only at steady ACTIVE, never during a modeset. Log: tmp/logs/ddr_flags_probe.log
"""
import argparse, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
f2 = lambda v: "--" if v is None else format(v, "02x")
# page-relative: VALID_WIN_DET_0, SLIC0/1 (04..0B), INT_STATUS0_0, INT_STATUS1 SET0/1 (f1..f7), INT_STATUS3 (02/03/06/07 of page+1)
FLAGS = [0x14, 0x88, 0x8a, 0x03] + list(range(0x04, 0x0C)) + [0xEF] + list(range(0xF1, 0xF8))
LIVE = [0x88, 0x8A, 0x8C, 0x8E, 0x8F]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()
    lf = (ROOT / "tmp/logs/ddr_flags_probe.log").open("a")

    def log(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)

    def snap(tag):
        for pg in (0x8F, 0xCF):
            log(f"{tag} P{pg:02X} " + " ".join(f"{r:02x}={f2(rd(d, pg << 8 | r))}" for r in FLAGS))

    snap("before")
    if a.clear:
        for pg in (0x8F, 0xCF):
            for r in FLAGS:
                wr(d, pg << 8 | r, 0x00)
        snap("after-clear")
        for i in range(a.n):
            snap(f"re-read {i}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
