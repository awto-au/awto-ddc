#!/usr/bin/env python3
"""Raw I2C transfer on one bus (run through `dev.py i2c`, which proves the bus by EDID serial; awto-ddc#276).
usage: i2c_raw.py --bus B --serial S --addr A [--write BYTE...] [--read N]
  write only = one write message; read only = one read message; both = write, repeated start, read. Output: `read: xx xx`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus

ADDR_MAX = 0x7F
READ_MAX = 255                                       # one I2C read message; larger needs a protocol, not a raw call


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--addr", type=lambda v: int(v, 0), required=True)
    ap.add_argument("--write", nargs="+", type=lambda v: int(v, 0), default=[])
    ap.add_argument("--read", type=int, default=0)
    a = ap.parse_args(argv)
    if not 0 <= a.addr <= ADDR_MAX:
        ap.error(f"address {a.addr:#x} is not 7-bit (max {ADDR_MAX:#x})")
    if any(not 0 <= b <= 0xFF for b in a.write):
        ap.error("write bytes must be 0..0xFF")
    if not 0 <= a.read <= READ_MAX:
        ap.error(f"--read 0..{READ_MAX}")
    if not a.write and not a.read:
        ap.error("nothing to do: give --write and / or --read")
    return a


def main(argv: list[str] | None = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    i2cbus.require_unit(a.bus, a.serial)
    ops = ([bytes(a.write)] if a.write else []) + ([a.read] if a.read else [])
    with i2cbus.Bus(a.bus) as b:
        out = b.ops(a.addr, ops)
    if a.read:
        print("read: " + " ".join(f"{x:02x}" for x in out[-1]))
    else:
        print(f"wrote {len(a.write)} byte(s) to {a.addr:#04x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
