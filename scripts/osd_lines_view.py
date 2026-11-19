#!/usr/bin/env python3
"""See the OSD line renderer (tools/osd_lines, awto-ddc#226) through our OSD model: scope trace -> font tiles -> screen image.

usage: osd_lines_view.py [--out PNG] [--scale N]
  Builds tools/osd_lines/scope_dump.c (host gcc), which draws a 384 x 216 trace with osd_line and prints every uploaded tile.
  The tiles go into an OsdState (osd_model.py) the way the firmware would write them: row commands, 12 x 18 1-bit char commands,
  glyph words (canonical bytes -> Realtek word order B0,B1,B2 = c2,c1,c0), palette, position; render() paints the panel image.
  Check: every tile decoded back by the model (glyph_bits) must equal the renderer's own pixels. Output PNG = the OSD area x N.
Log: ./tmp/logs/osd_lines_view.log
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import isostamp
import numpy as np

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_model as M

LOG = ROOT / "tmp/logs/osd_lines_view.log"
SRC = ROOT / "tools/osd_lines"
EXE = ROOT / "tmp/scratch/scope_dump"
COLS, ROWS, TW, TH = 32, 12, 12, 18
FS_BASE = ROWS + 1                      # row commands 0..ROWS-1, end word at ROWS, char commands from ROWS + 1 [SDK OsdFuncApplyMap]
FONT_BASE = 512                         # above the 384 char commands; glyph id i at FONT_BASE + 9 * i
FG, BG = 2, 1                           # palette indexes
HD, VD = 100, 40                        # OSD origin: hd * 4 px, vd px (step 4, scale 1)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def build_and_run() -> tuple[dict, list]:
    EXE.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["gcc", "-O2", "-Wall", f"-I{SRC}", str(SRC / "osd_lines.c"), str(SRC / "scope_dump.c"), "-o", str(EXE), "-lm"],
                       capture_output=True, text=True, check=False)
    if r.returncode:
        sys.exit(f"gcc failed:\n{r.stderr}")
    out = subprocess.run([str(EXE)], capture_output=True, text=True, check=True).stdout.splitlines()
    tiles, px = {}, []
    for ln in out:
        f = ln.split()
        if f[0] == "tile":
            tiles[int(f[1])] = bytes(int(x, 16) for x in f[2:])
        elif f[0] == "px":
            px.append(f[2])
    return tiles, px


def make_state(tiles: dict) -> M.OsdState:
    st = M.OsdState()
    st.pal[BG] = (8, 24, 12)
    st.pal[FG] = (70, 255, 110)
    for r in range(ROWS):                                         # row command: present, height - 1, char count
        st.font[r] = [0x80, TH - 1, COLS]
    st.font[ROWS] = [0, 0, 0]                                     # end of the row commands
    for i in range(COLS * ROWS):                                  # char command: 1-bit, width 12, id (bit 8 in B0[5]), colours
        st.font[FS_BASE + i] = [0x40 | 0x0C | (0x20 if i >= 256 else 0), i & 0xFF, (FG << 4) | BG]
    for i, b in tiles.items():
        for k in range(9):                                        # canonical bytes c0 c1 c2 of word k -> stored B0 B1 B2 = c2 c1 c0
            c0, c1, c2 = b[3 * k:3 * k + 3]
            st.font[FONT_BASE + 9 * i + k] = [c2, c1, c0]
    regs = bytearray(256)
    regs[0x00] = VD >> 3
    regs[0x01] = HD >> 2
    regs[0x02] = 0x01 | ((HD & 3) << 6) | ((VD & 7) << 3)       # osd_en, hd[1:0], vd[2:0]
    regs[0x0C] = FS_BASE & 0xFF
    regs[0x0D] = ((FS_BASE >> 8) << 4) | (FONT_BASE & 0x0F)
    regs[0x0E] = (FONT_BASE >> 4) & 0xFF
    regs[0x17] = ((FONT_BASE >> 12) & 7) << 3
    regs[0x19] = 0                                                # row command base
    regs[0xC0] = 0x80                                             # scale-up engine off
    st.regs = bytes(regs)
    st.ovl = (0x01, 0x00)                                         # overlay port on
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scratch/osd_lines_scope.png")
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args()
    tiles, px = build_and_run()
    say(f"scope_dump: {len(tiles)} tiles uploaded, canvas {len(px[0])} x {len(px)}")
    st = make_state(tiles)
    g = M.frame_geometry(st)
    bad = 0
    for i in range(COLS * ROWS):
        bits = M.glyph_bits(st, g, i)
        want = np.array([[int(px[(i // COLS) * TH + y][(i % COLS) * TW + x]) for x in range(TW)] for y in range(TH)], np.uint8)
        if bits.shape != want.shape or not (bits.astype(np.uint8) == want).all():
            bad += 1
    say(f"model decode vs renderer pixels: {COLS * ROWS - bad} of {COLS * ROWS} tiles identical" + ("" if not bad else f", {bad} DIFFER"))
    img = M.render(st, 1920, 1080, bg=(40, 40, 48))
    ox, oy = HD * g["step"] * g["sx"], VD * g["sy"]
    crop = img[max(oy - 20, 0):oy + ROWS * TH + 20, max(ox - 20, 0):ox + COLS * TW + 20]
    from PIL import Image
    Image.fromarray(np.kron(crop, np.ones((a.scale, a.scale, 1), np.uint8))).save(a.out)
    say(f"rendered the OSD area (origin {ox},{oy}) x{a.scale} -> {a.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
