#!/usr/bin/env python3
"""Read-only extras of the I2C probe: multi-byte reads of 0x4A / 0x4B and the HDMI SCDC offsets at 0x54 (docs/clock-sweep.md "temperature proxy").

usage: i2c_probe2.py --bus B --serial S
  i2ctransfer `w1@ADDR OFF r16` (one pointer write, one 16-byte read) at OFF 0x00 / 0x40 / 0x6F for 0x4A and 0x4B; SCDC (0x54) single-byte reads only, never a write to SCDC.
Log ./tmp/logs/i2c_probe.log
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2c_probe as P

SCDC_OFFS = (0x01, 0x02, 0x10, 0x20, 0x21, 0x40, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    a = ap.parse_args()
    import i2cbus
    i2cbus.require_unit(a.bus, a.serial)
    for ad in (0x4A, 0x4B):
        for off in (0x00, 0x40, 0x6F):
            out = subprocess.run(["i2ctransfer", "-y", str(a.bus), f"w1@0x{ad:02X}", f"0x{off:02X}", "r16"], capture_output=True, text=True, timeout=P.I2C_S, check=False).stdout.strip()
            P.say(f"bus {a.bus} 0x{ad:02X} offset 0x{off:02X} 16-byte read: {out or 'no answer'}")
    vals = []
    for off in SCDC_OFFS:
        out = P.run(["i2cget", "-y", str(a.bus), "0x54", f"0x{off:02X}", "b"]).strip()
        vals.append(f"{off:02X}={out[2:] if out.startswith('0x') else '--'}")
    P.say(f"bus {a.bus} SCDC 0x54 (read-only): {' '.join(vals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
