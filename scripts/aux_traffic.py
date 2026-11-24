#!/usr/bin/env python3
"""Read-only DP AUX traffic for the TMDS PHY event-loss test (#256): N EDID block reads over the unit's I2C-over-AUX bus.

usage: aux_traffic.py BUS SERIAL N
- Refuses a bus whose EDID does not contain SERIAL. Every read is one AUX burst the monitor must answer from its EXINT0 handler.
- Result line: reads, errors (host-side timeouts / NAKs = lost requests), ms per read. Log: ./tmp/logs/aux_traffic.log
"""
import sys
import time
from pathlib import Path

import i2cbus
import isostamp

EDID_ADDR = 0x50
LOG = Path(__file__).resolve().parent.parent / "tmp/logs/aux_traffic.log"


def block(bus: i2cbus.Bus) -> bytes:
    bus.raw_write(EDID_ADDR, b"\x00")
    return bus.raw_read(EDID_ADDR, 128)


def main() -> int:
    bus, serial, n = sys.argv[1], sys.argv[2].encode(), int(sys.argv[3])
    fd = i2cbus.Bus(int(bus))
    if serial not in block(fd):
        print(f"bus {bus}: EDID has no {serial.decode()}; refused")
        return 1
    err = 0
    t0 = time.perf_counter()
    for _ in range(n):
        try:
            if len(block(fd)) != 128:
                err += 1
        except OSError:
            err += 1
    dt = time.perf_counter() - t0
    fd.close()
    line = f"{isostamp.now()} aux_traffic bus {bus}: {n} reads, errors {err}, {dt * 1000 / n:.2f} ms/read"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
