#!/usr/bin/env python3
"""Render the glyph data of Realtek's RL6449 QC OSD test (awto-ddc#227): what its patterns look like, from the font tables alone.

usage: qc_osd_patterns.py [--qc FILE] [--out PNG] [--scale N]
  Reads the QC source (default: the upstream mirror RL6449_Series_QC_OSD.c), decodes the VLC font blobs (osd_vlc.py) and draws:
  - tQCFONT_GLOBAL      1 bpp 12 x 18 glyph atlas
  - tQCFONT_2BITBROOK   48 glyphs 2 bpp, arranged 8 x 6 as tQCICON_2BIT
  - tQCFONT_4BITLUFFY   77 glyphs 4 bpp, arranged 11 x 7 as tQCICON_4BIT
  Colours: tPALETTE_QC (64 x R G B). Glyph storage: bit planes (see glyphs()). 2 bpp: pixel value v -> palette index v (QC: COLOR_00..11 = 0..3); 4 bpp: v -> palette index v
  [guess: the QC draws it with palette sets 00_01_02_03 | 04..07 | 08..11 | 12..15 and background 1]. Index 0 = transparent: grey here.
  Not decoded: tQCFONT_24_36_* (the 24 x 36 mode layout is not understood: row-pair / plane packing gives garbage), tQCDRAW_MAP (map command words, 856 words), the window / gradient tests (register sequences, no image data).
Log: ./tmp/logs/qc_osd_patterns.log
"""
import argparse
import os
import re
import sys
import isostamp  # noqa: E402
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_vlc as V  # noqa: E402

LOG = ROOT / "tmp/logs/qc_osd_patterns.log"
QC = Path("/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST/Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_QC_OSD.c")
TRANSPARENT = (70, 70, 78)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def tables(src: str) -> dict:
    out = {}
    for m in re.finditer(r"BYTE code (\w+)\[\]\s*=\s*\{(.*?)\};", src, re.S):
        body = m.group(2)
        if re.search(r"ICON_|_NEXT_|_CLEAR|_END_", body):
            continue
        out[m.group(1)] = bytes(int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", body))
    return out


def glyphs(data: bytes, w: int, h: int, bpp: int) -> list:
    """Multi-bit glyph = bpp bit planes, each stored like a 1-bit glyph (w * h / 24 words, 24-bit words low byte first, MSB plane
    first). Pixel value = planes read MSB-first. Evidence: Realtek's own 2 / 4 bpp icons decode to clean pictures this way and
    to noise with row-major packed pixels (pack_unit / unpack_unit, which is only 'derived')."""
    plane = w * h // 8
    unit = plane * bpp
    out = []
    for i in range(0, len(data) - unit + 1, unit):
        v = np.zeros((h, w), np.uint8)
        for p in range(bpp):
            v = (v << 1) | np.array(V.unpack_unit(data[i + p * plane:i + (p + 1) * plane], w, h, 1), np.uint8)
        out.append(v)
    return out


def paint(g: np.ndarray, pal: list, bpp: int) -> np.ndarray:
    img = np.zeros(g.shape + (3,), np.uint8)
    for v in range(1 << bpp):
        img[g == v] = TRANSPARENT if v == 0 else pal[v]
    return img


def grid(gl: list, cols: int, pal: list, bpp: int, gap: int = 1) -> np.ndarray:
    h, w = gl[0].shape
    rows = (len(gl) + cols - 1) // cols
    img = np.full((rows * (h + gap) + gap, cols * (w + gap) + gap, 3), 20, np.uint8)
    for i, g in enumerate(gl):
        r, c = divmod(i, cols)
        img[gap + r * (h + gap):gap + r * (h + gap) + h, gap + c * (w + gap):gap + c * (w + gap) + w] = paint(g, pal, bpp)
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qc", type=Path, default=QC)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scratch/qc_osd_patterns.png")
    ap.add_argument("--scale", type=int, default=6)
    a = ap.parse_args()
    t = tables(a.qc.read_text(errors="replace"))
    pal_raw = t["tPALETTE_QC"]
    pal = [tuple(pal_raw[3 * i:3 * i + 3]) for i in range(len(pal_raw) // 3)]
    say(f"palette: {len(pal)} entries; fonts: " + ", ".join(f"{n} {len(t[n])} B" for n in t if n.startswith("tQCFONT")))
    sections = []
    glob = glyphs(V.decode(t["tQCFONT_GLOBAL"]), 12, 18, 1)
    sections.append((f"tQCFONT_GLOBAL: {len(glob)} x 1 bpp 12x18", grid(glob, 11, [None, (255, 255, 255)], 1)))
    brook = glyphs(V.decode(t["tQCFONT_2BITBROOK"]), 12, 18, 2)
    sections.append((f"tQCFONT_2BITBROOK: {len(brook)} x 2 bpp, icon 8 x 6", grid(brook, 8, pal, 2, gap=0)))
    luffy = glyphs(V.decode(t["tQCFONT_4BITLUFFY"]), 12, 18, 4)
    sections.append((f"tQCFONT_4BITLUFFY: {len(luffy)} x 4 bpp, icon 11 x 7 [palette guess]", grid(luffy, 11, pal, 4, gap=0)))
    from PIL import Image, ImageDraw
    tiles = []
    for title, im in sections:
        big = np.kron(im, np.ones((a.scale, a.scale, 1), np.uint8))
        lab = Image.new("RGB", (big.shape[1], 22), (30, 30, 34))
        ImageDraw.Draw(lab).text((4, 4), title, fill=(230, 230, 230))
        tiles.append(np.concatenate([np.array(lab), big], axis=0))
        say(f"{title}: {im.shape[1]} x {im.shape[0]} px")
    wd = max(x.shape[1] for x in tiles)
    sheet = np.full((sum(x.shape[0] + 10 for x in tiles), wd, 3), 30, np.uint8)
    y = 0
    for x in tiles:
        sheet[y:y + x.shape[0], :x.shape[1]] = x
        y += x.shape[0] + 10
    a.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(a.out)
    say(f"sheet -> {a.out} ({sheet.shape[1]} x {sheet.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
