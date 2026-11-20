#!/usr/bin/env python3
"""Flash warning screen picture, two images side by side (upright and Rotate 180), rendered in the firmware sim (#232).

usage: flash_screen_pic.py OLD.bin NEW.bin [--out PNG]
  Per image: boot, Rotate 0 / 180 (settings row 32), VCP 0xEB = 5 (firmware draws), then the host's text rows are put into the OSD map with
  flash_screen._put (as tick() writes them over ISP, same Rotate 180 mirroring). Left = OLD, right = NEW; upright row above, Rotate 180 below.
Log: ./tmp/logs/flash_screen_pic.log
"""
import argparse
import os
import sys
from pathlib import Path

import isostamp
from PIL import Image

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import flash_screen as FS
import osd_render as R

LOG = R.ROOT / "tmp/logs/flash_screen_pic.log"
ROW_DISP_ROTATE = 32
SETTLE_S = 6.0                  # fw time for the display re-set after Rotate changes (saver_sim.py ROTATE_SETTLE_S)
DRAW_S = 3.0                    # fw time for the firmware's draw steps after VCP 0xEB = 5
SCALE = 4                       # 3840 -> 960 px per picture
INFO = {"phase": "BANKED", "bank": 6, "nbank": 15, "addr": 0x6F000, "sec": 112, "nsec": 224, "pct": 50, "iface": "DP-AUX 1000 KHZ BURST",
        "bad": 0, "recov": 0, "t": 61.0}


class Fake:
    def __init__(self, st):
        self.st = st

    def write_word(self, word, b0, b1, b2):
        self.st.font[word] = [b0, b1, b2]


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    LOG.open("a").write(line + "\n")
    print(line, flush=True)


def shot(binp: Path, rot: int) -> Image.Image:
    eng = D.DdcEngine()
    sess = R.Session(binp, binp.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, rot)
    sess.bus.wait(SETTLE_S)
    ddc.set(FS.VCP_SAVER, FS.VCP_FLASH_SCREEN)
    sess.bus.wait(DRAW_S)
    st = sess.snap()
    FS._rot = rot
    fake = Fake(st)
    for cell, gid in FS._cells(INFO).items():
        FS._put(fake, cell, gid)
    img = R.render_snap(st, "black", SCALE)
    sess.bus.close()
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--out", type=Path, default=R.ROOT / "tmp/flash_screen_pic.png")
    a = ap.parse_args()
    imgs = [[shot(b, rot) for b in (a.old, a.new)] for rot in (0, 1)]
    w, h = imgs[0][0].size
    gap = 8
    out = Image.new("RGB", (2 * w + gap, 2 * h + gap), (60, 60, 60))
    for r, row in enumerate(imgs):
        for c, im in enumerate(row):
            out.paste(im, (c * (w + gap), r * (h + gap)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out)
    say(f"wrote {a.out}: left old {a.old.name}, right new {a.new.name}; top Rotate 0, bottom Rotate 180")
    return 0


if __name__ == "__main__":
    sys.exit(main())
