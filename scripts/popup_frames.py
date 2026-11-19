#!/usr/bin/env python3
"""Every small pop-up card on the full panel frame (sim), one PNG each + a frame sheet with the card margins.

usage: AWTO_SIM_CORE=fast popup_frames.py BIN MAP [--out DIR] [--prefix after_]
- Per card: clear holds (0x27), raise it (card_shot SHOTS command bytes), wait, snapshot; selector last.
- No MENU between cards: with nothing open it opens the awto menu and the next card draws over it (the old card_shot garble).
- DIR/<prefix><name>.png = whole panel at 1/2 size; DIR/<prefix>frames.png = the sheet. Log: tmp/logs/card_shot.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_shot as C
import osd_render as R

CARDS = [("nosignal", 0x50), ("nocable", 0x51), ("nosupport", 0x52), ("autoadjust", 0x54), ("info", 0x55), ("autocolour", 0x56),
         ("ddcci_port", 0x57), ("powersaving", 0x58), ("panel", 0x59), ("backlight", C.K_UP), ("selector", C.K_SOURCE)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=C.ROOT / "tmp/popup_frames")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds after the command before the snapshot")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    frames = []
    s = R.Session(a.bin, a.map, "1080p60")
    try:
        s.boot()
        for name, cmd in CARDS:
            C.send(s, C.CLEAR)
            s.bus.wait(a.wait)
            C.send(s, cmd)
            s.bus.wait(a.wait)
            if name == "selector":
                C.send(s, C.K_UP)                   # SOURCE alone draws nothing in the sim (as card_shot selector_source); a step does
                s.bus.wait(a.wait)
            out = a.out / f"{a.prefix}{name}.png"
            if C.shot(s.snap(), out, name):
                frames.append((name, out))
    finally:
        s.bus.close()
    C.frame_sheet(frames, a.out / f"{a.prefix}frames.png")
    return 0 if len(frames) == len(CARDS) else 1


if __name__ == "__main__":
    sys.exit(main())
