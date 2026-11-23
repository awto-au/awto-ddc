#!/usr/bin/env python3
"""Per-port status word of a running unit (#323): g_pucAwtoPortSt D1..D3 over the debug link (0x35, link on).

usage: port_status.py BUS --serial S --map MAP.map
  bits: 0x01 cable pin, 0x02 TMDS clock (D2 / D3), 0x04 DP link trained (D1), 0x08 EDID read, 0x10 DP AUX seen (D1), 0x80 polled
Log: tmp/logs/port_status.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B
import sync_log as SL
from _log import log_line

NAMES = ((0x01, "cable"), (0x02, "clock"), (0x04, "link"), (0x08, "edid"), (0x10, "aux"), (0x80, "polled"))
LOG = Path(__file__).resolve().parent.parent / "tmp/logs/port_status.log"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    a = ap.parse_args()
    i2cbus.require_unit(a.bus, a.serial)
    io = B.Real(a.bus, allow_write=False, regread=True)
    try:
        raw = X.read_blocks(io, SL.sym(a.map, "g_pucAwtoPortSt"), 3)
    finally:
        io.close()
    if raw is None:
        log_line("port_status: read over 0x35 failed", LOG)
        return 1
    for i, v in enumerate(bytes(raw)):
        log_line(f"D{i + 1} status 0x{v:02X}: " + (", ".join(n for m, n in NAMES if v & m) or "none"), LOG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
