#!/usr/bin/env python3
"""Watch front-panel key presses live by polling the scaler's ADC key registers over DDC/ISP.

usage: rtd_keywatch.py <bus> [--halt] [--secs N]
Default: MCU left RUNNING; reads scaler regs via F4/F5 (index/data) at ISP 0x4A and decodes the
key bands from buttons.md. Press each physical button; the decoded key is printed when it changes.
--halt: enter ISP (stops MCU) first — only if the running read returns nothing (then presses may not
register, since the halted MCU is not scanning). --secs: watch duration (default 25).
Reads only; no writes except the F4 index byte. Bands [fw] from docs/reversing/realtek-rtd/buttons.md.
Log: ./tmp/logs/rtd_keywatch.log
"""
import os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P

# (mask, source reg, lo, hi, provisional label) from buttons.md
BANDS = [
    (0x02, 0xFF09, 0xC0, 0xE0, "A0-top (SOURCE/AUTO?)"),
    (0x04, 0xFF09, 0x28, 0x48, "DOWN?"),
    (0x08, 0xFF0A, 0x28, 0x48, "UP?"),
    (0x10, 0xFF09, 0x70, 0x90, "MENU?"),
    (0x20, 0xFF0A, 0x68, 0x88, "A1-mid (SOURCE/AUTO?)"),
]


def decode(a0, a1):
    hits = []
    for mask, reg, lo, hi, label in BANDS:
        v = a0 if reg == 0xFF09 else a1
        if lo <= v < hi:
            hits.append(label)
    return hits


def main() -> int:
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_keywatch.log").open("a")
    bus = int(sys.argv[1])
    secs = int(sys.argv[sys.argv.index("--secs") + 1]) if "--secs" in sys.argv else 25
    isp = P.Isp(bus)
    if "--halt" in sys.argv:
        isp.write(0x6F, 0x80)
        P.log("MCU halted (ISP)")
    P.log(f"keywatch bus={bus} secs={secs}: press each button now")

    def rd(r):
        isp.write(0xF4, r); return isp.read(0xF5)

    last = None
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            a0, a1 = rd(0xFF09), rd(0xFF0A)
            p30 = isp.read(0x25)  # P3.x port snapshot (POWER = P3.0); reg per buttons.md note
        except OSError as e:
            P.log(f"read error {e}"); break
        key = decode(a0, a1)
        state = (a0, a1, tuple(key))
        if state != last:
            P.log(f"A0=0x{a0:02x} A1=0x{a1:02x} P3=0x{p30:02x} -> {key or 'idle'}")
            last = state
    P.log("keywatch done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
