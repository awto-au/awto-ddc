#!/usr/bin/env python3
"""Play the Pac-Man OSD prototype demo on a unit (fw/test/pacman_osd.c, test cmds 0xB4 draw / 0xB5 next frame / 0xB6 off).

usage: pacman_unit.py BUS --serial S --map MAP [--loops N] [--fps F] [--keep]
  Sends 0xB4 (maze), then 0xB5 once per frame period, N x 96 frames, then 0xB6 (unless --keep). Debug link on for the run.
Log: ./tmp/logs/pacman_unit.log
"""
import argparse
import os
import re
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
LOG = ROOT / "tmp/logs/pacman_unit.log"
TESTCMD_OFF = 0x28           # isr_g_stAwtoDiag.ucTestCmd
TC_ON, TC_STEP, TC_OFF = 0xB4, 0xB5, 0xB6
FRAMES = 96                  # AWTO_PM_FRAMES
LOAD_S = 1.0                 # the maze + 343 glyphs go through the data port: ~12 k bytes, ~0.2 s on the unit; 5x
FPS = 8.0                    # demo pace a person can follow; one frame update is ~10 cells (< 5 ms)


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
    ap.add_argument("--loops", type=int, default=1)
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--keep", action="store_true", help="leave the last frame on screen")
    a = ap.parse_args()
    import dbg_link, i2cbus  # noqa: E401
    import rtd_i2c_bridge as B

    i2cbus.require_unit(a.bus, a.serial)
    hit = re.search(r"^\S*\s+([0-9A-F]{8})\s+_isr_g_stAwtoDiag\b", a.map.read_text(errors="replace"), re.M)
    if not hit:
        sys.exit(f"isr_g_stAwtoDiag not in {a.map}")
    cmd = (int(hit.group(1), 16) & 0xFFFF) + TESTCMD_OFF
    period = 1.0 / a.fps
    with dbg_link.linked(a.bus, 4):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            def send(c: int) -> bool:
                return io.write(0x6A, 0x01, bytes([cmd >> 8])) and io.write(0x6A, 0x03, bytes([c])) and io.write(0x6A, 0x3B, bytes([cmd & 0xFF]))
            say(f"maze (0x{TC_ON:02X}): {'sent' if send(TC_ON) else 'NAK'}")
            time.sleep(LOAD_S)
            nak = 0
            t0 = time.monotonic()
            for n in range(a.loops * FRAMES):
                if not send(TC_STEP):
                    nak += 1
                time.sleep(max(0.0, t0 + (n + 1) * period - time.monotonic()))
            say(f"{a.loops * FRAMES} frames sent at {a.fps:g} fps, {nak} NAK")
            if not a.keep:
                send(TC_OFF)
                say("off (0xB6)")
        finally:
            io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
