#!/usr/bin/env python3
"""Read-only I2C address probe of the test unit's host bus (docs/clock-sweep.md "temperature proxy").

usage: i2c_probe.py --bus B --serial S [--reps N] [--skip 0x30,0x35,0x37,0x4A,0x50]
  `i2cdetect -y -r` (read-byte probe, no writes), then for every ACKing address not in --skip: `i2cget -y B ADDR REG b` for REG 0x00..0x0F, N times.
  i2cget with a register sends that register byte as a data-address write first; no i2cset, no block write.
Log ./tmp/logs/i2c_probe.log
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/i2c_probe.log"
I2C_S = 5.0                                # one i2cget / i2cdetect call: ms-scale transfers; expiry = logged as no answer


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=I2C_S * 20).stdout
    except subprocess.TimeoutExpired:
        return ""


def detect(bus: int) -> list[int]:
    out = run(["i2cdetect", "-y", "-r", str(bus)])
    addrs = []
    for line in out.splitlines()[1:]:
        m = re.match(r"([0-9a-f]0):(.*)", line)
        if not m:
            continue
        for i, tok in enumerate(m.group(2).split()):
            if re.fullmatch(r"[0-9a-f]{2}", tok):
                addrs.append(int(m.group(1), 16) + i)
    return addrs


def probe(a, skip: set[int], state: str) -> None:
    addrs = detect(a.bus)
    say(f"bus {a.bus} [{state}]: ACK at {' '.join(f'0x{x:02X}' for x in addrs)}")
    for ad in addrs:
        if ad in skip:
            continue
        for rep in range(a.reps):
            vals = []
            for reg in range(16):
                out = run(["i2cget", "-y", str(a.bus), f"0x{ad:02X}", f"0x{reg:02X}", "b"]).strip()
                vals.append(out[2:] if out.startswith("0x") else "--")
            say(f"bus {a.bus} [{state}] 0x{ad:02X} regs 00..0F read {rep + 1}: {' '.join(vals)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--skip", default="0x30,0x35,0x37,0x4A,0x50")
    ap.add_argument("--halt", action="store_true", help="probe a second time with the MCU halted (ISP enable 0x6F <- 0x80); the scaler is reset afterwards (0xEE <- 0x02)")
    a = ap.parse_args()
    import i2cbus
    i2cbus.require_unit(a.bus, a.serial)
    skip = {int(x, 0) for x in a.skip.split(",") if x}
    probe(a, skip, "firmware running")
    if a.halt:
        from rtd_flash_sector import Rtd
        isp = Rtd(a.bus)
        try:
            isp.write(0x6F, 0x80)
            say(f"ISP enable: 0x6F reads 0x{isp.read(0x6F):02X} (bit 7 = MCU halted)")
            probe(a, skip | {0x4A}, "MCU halted (ISP enabled)")
        finally:
            try:
                isp.write(0xEE, 0x02)
                say("scaler reset sent (0xEE <- 0x02)")
            except OSError as e:
                say(f"reset failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
