#!/usr/bin/env python3
"""Stack high-water of the running image: g_ucAwtoStackHigh (highest IRAM stack byte written since boot; guard 0xF0 = fatal).

usage: stack_high.py BUS --serial S --map MAP
Log: ./tmp/logs/stack_high.log
"""
import argparse
import sys
from pathlib import Path

import isostamp
from _repo import ROOT

LOG = ROOT / "tmp/logs/stack_high.log"
GUARD = 0xF0            # AWTO_STACK_GUARD


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_link
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    import sw_timeline as T

    i2cbus.require_unit(a.bus, a.serial)
    addr, raw = T.sym(a.map, "g_ucAwtoStackHigh"), None
    with dbg_link.linked(a.bus, 2):
        io = B.Real(a.bus, allow_write=False, regread=True)
        for _ in range(3):
            raw = X.read_blocks(io, addr, 1)
            if raw is not None:
                break
        io.close()
    if raw is None:
        print("read failed")
        return 1
    line = f"{isostamp.now()} {a.map.name}: stack high-water 0x{raw[0]:02X}, guard 0x{GUARD:02X}, {GUARD - raw[0]} B below the guard"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
