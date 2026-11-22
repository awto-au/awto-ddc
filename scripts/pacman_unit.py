#!/usr/bin/env python3
"""Play the Pac-Man OSD prototype demo on a unit (fw/test/pacman_classic.c, test cmds 0xB7 draw / 0xB8 next step / 0xB9 off).

usage: pacman_unit.py BUS --serial S --map MAP [--loops N] [--fps F] [--keep]
  Sends 0xB4 (maze), then 0xB5 once per frame period, N x 96 frames, then 0xB6 (unless --keep). Debug link on for the run.
Log: ./tmp/logs/pacman_unit.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from _log import log_line as _log_line

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
LOG = ROOT / "tmp/logs/pacman_unit.log"
TESTCMD_OFF = 0x28           # isr_g_stAwtoDiag.ucTestCmd
TC_ON, TC_STEP, TC_OFF = 0xB7, 0xB8, 0xB9
FRAMES = 1040                # AWTO_PC_STEPS (sub-steps: 4 per game step)
LOAD_S = 1.0                 # the maze + 343 glyphs go through the data port: ~12 k bytes, ~0.2 s on the unit; 5x
FPS = 32.0                   # 4 sub-steps per 125 ms game step (the saver pace); one sub-step is ~8 cells


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--factor", type=int, default=None, help="scale-up factor (ratio = 64 / factor, 0 = off); default = the image's")
    ap.add_argument("--pos", type=int, nargs=2, metavar=("H", "V"), default=None, help="OSD position (hd, vd units)")
    ap.add_argument("--keep", action="store_true", help="leave the last frame on screen")
    a = ap.parse_args()
    import dbg_link
    import i2cbus
    import rtd_i2c_bridge as B

    i2cbus.require_unit(a.bus, a.serial)
    hit = re.search(r"^\S*\s+([0-9A-F]{8})\s+_isr_g_stAwtoDiag\b", a.map.read_text(errors="replace"), re.MULTILINE)
    if not hit:
        sys.exit(f"isr_g_stAwtoDiag not in {a.map}")
    cmd = (int(hit.group(1), 16) & 0xFFFF) + TESTCMD_OFF
    period = 1.0 / a.fps
    tc_on, tc_step, tc_off = TC_ON, TC_STEP, TC_OFF
    frames = FRAMES
    pos_sym = "g_usAwtoPcPos"
    with dbg_link.linked(a.bus, 4):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            def send(c: int) -> bool:
                return io.write(0x6A, 0x01, bytes([cmd >> 8])) and io.write(0x6A, 0x03, bytes([c])) and io.write(0x6A, 0x3B, bytes([cmd & 0xFF]))
            def poke(sym: str, v: int, width: int = 1) -> None:          # XDATA bytes, big endian for a WORD
                ad = int(re.search(r"^\S*\s+([0-9A-F]{8})\s+_?" + sym + r"\b", a.map.read_text(errors="replace"), re.MULTILINE).group(1), 16) & 0xFFFF
                for k in range(width):
                    byte = (v >> (8 * (width - 1 - k))) & 0xFF
                    io.write(0x6A, 0x01, bytes([(ad + k) >> 8])) and io.write(0x6A, 0x03, bytes([byte])) and io.write(0x6A, 0x3B, bytes([(ad + k) & 0xFF]))
            if a.factor is not None:
                poke("g_ucAwtoPcFactor", a.factor)
            if a.pos is not None:
                poke(pos_sym + "H", a.pos[0], 2)
                poke(pos_sym + "V", a.pos[1], 2)
            say(f"maze (0x{tc_on:02X}): {'sent' if send(tc_on) else 'NAK'}")
            time.sleep(LOAD_S)
            nak = 0
            t0 = time.monotonic()
            for n in range(a.loops * frames):
                if not send(tc_step):
                    nak += 1
                time.sleep(max(0.0, t0 + (n + 1) * period - time.monotonic()))
            say(f"{a.loops * frames} frames sent at {a.fps:g} fps, {nak} NAK")
            if not a.keep:
                send(tc_off)
                say(f"off (0x{tc_off:02X})")
        finally:
            io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
