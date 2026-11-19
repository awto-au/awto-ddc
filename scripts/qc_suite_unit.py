#!/usr/bin/env python3
"""Run Realtek's QC OSD frames one after another on a unit, for someone watching it (awto-ddc#227).

usage: qc_suite_unit.py BUS --serial S --map MAP [--first N] [--last N] [--hold-s S]
  Needs an image with the QC frame harness (test cmd 0xB2 + n: n = 0 test pattern, n = k frames 0..k-1 replayed and frame k-1 left
  on screen; scripts/qc_frames_shot.py NAMES). Sends each command over the debug link, waits for the firmware to take it, holds the
  picture HOLD_S, logs the frame name + local time so a viewer can match what they saw. Ends with the OSD off (test cmd 0xB1).
Log: ./tmp/logs/qc_suite_unit.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
LOG = ROOT / "tmp/logs/qc_suite_unit.log"
TESTCMD_OFF = 0x28           # isr_g_stAwtoDiag.ucTestCmd
TC = 0xB2                    # harness base: 0xB2 + n
TC_OFF = 0xB1                # QC OSD off
HOLD_S = 6.0                 # a person looks at the unit: reading a frame takes a few seconds, not a measured device time


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--last", type=int, default=23)
    ap.add_argument("--hold-s", type=float, default=HOLD_S)
    a = ap.parse_args()
    import dbg_link
    import i2cbus
    import rtd_i2c_bridge as B
    from qc_frames_shot import NAMES

    i2cbus.require_unit(a.bus, a.serial)
    hit = re.search(r"^\S*\s+([0-9A-F]{8})\s+_isr_g_stAwtoDiag\b", a.map.read_text(errors="replace"), re.MULTILINE)
    if not hit:
        sys.exit(f"isr_g_stAwtoDiag not in {a.map}")
    cmd = (int(hit.group(1), 16) & 0xFFFF) + TESTCMD_OFF
    with dbg_link.linked(a.bus, 8):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            def send(c: int) -> bool:
                return io.write(0x6A, 0x01, bytes([cmd >> 8])) and io.write(0x6A, 0x03, bytes([c])) and io.write(0x6A, 0x3B, bytes([cmd & 0xFF]))

            for n in range(a.first, a.last + 1):
                name = NAMES[n] if n < len(NAMES) else f"frame {n}"
                ok = send(TC + n)
                say(f"frame index {n}: {name} cmd 0x{TC + n:02X} {'sent' if ok else 'NAK'}")
                if not ok:
                    continue
                time.sleep(a.hold_s)
            send(TC_OFF)
            say("QC OSD off (0xB1)")
        finally:
            io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
