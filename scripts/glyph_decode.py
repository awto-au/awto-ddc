#!/usr/bin/env python3
"""Offline decode of a Realtek RTD OSD VLC glyph blob -> clean tile atlas (static; reads a dump only).

CONFIRMED FORMAT (2026-11-04, blobs A/C render as clean icons+text, D as clean logo fragments):
  blob = [8-byte VLC value map][2-byte BE stream length N][N-byte VLC stream, END=0xFF]
  - VLC codes: regdb 0x3A0F-0x3A16 prefix set; value map = the blob's own 8 header bytes
    (16 nibbles vlc_0..vlc_f), NOT the all-zero hardware reset map.
  - stream: bits consumed LSB-first within each byte; decoded nibbles pair high-first into bytes.
  - tile: 1bpp 12x18 = 9 words x 24 bit = 27 bytes. Word w -> rows (2w, 2w+1). The 3 stored bytes
    of a word are read B2,B1,B0 (reverse); within a byte MSB = leftmost pixel. Pixel 1 = foreground.
  - The blob is a DE-DUPLICATED glyph atlas (unique tiles in font-tool reference-scan order), NOT a
    raster. Final image placement lives in a separate runtime char-map (glyph-index grid), not in the
    blob -> rendering the raw atlas as a rectangular grid is EXPECTED to look sheared/scrambled for a
    logo blob; individual tiles are nonetheless clean. See docs/boot-logo.md.

usage: glyph_decode.py <dump> <start-hex> [outdir] [--cols N] [--grid COLSxROWS@SKIP]
  default: clean contact-sheet atlas (gaps between tiles) of the whole blob.
  --grid: also render a gap-less rectangular grid (a placement GUESS; needs the real char-map).
Log: tmp/logs/glyph_decode.log
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

CODES = ["0","100","1010","1011","1100","11010","11011","11100","111010","111011",
         "111100","111101","1111100","1111101","1111110","11111110"]


def decode_blob(d, off):
    """Return (map_hex, length, tile_bytes) for the blob at offset `off`. tile_bytes = decoded stream
    without the END byte, as raw bytes (27 per 1bpp 12x18 glyph)."""
    vals = []
    for b in d[off:off + 8]:
        vals += [b >> 4, b & 15]
    tab = {c: v for c, v in zip(CODES, vals)}
    length = (d[off + 8] << 8) | d[off + 9]
    nibs = []
    code = ""
    end = False
    for b in d[off + 10:off + 10 + length + 8]:
        for k in range(8):                       # LSB-first
            code += str((b >> k) & 1)
            if code in tab:
                nibs.append(tab[code]); code = ""
            elif code == "11111111":
                end = True; break
            elif len(code) > 8:
                raise ValueError("bad VLC code at blob %#x" % off)
        if end:
            break
    by = bytes(((nibs[i] << 4) | nibs[i + 1]) for i in range(0, len(nibs) - 1, 2))
    return d[off:off + 8].hex(), length, by


def tile(by, t):
    """1bpp 12x18 glyph t -> 18x12 uint8 (1 = foreground). Word w -> rows (2w,2w+1); bytes B2,B1,B0; MSB left."""
    base = t * 27
    g = np.zeros((18, 12), dtype=np.uint8)
    for w in range(9):
        line = []
        for b in (by[base + w * 3 + 2], by[base + w * 3 + 1], by[base + w * 3]):
            line += [(b >> k) & 1 for k in range(7, -1, -1)]
        g[2 * w] = line[:12]
        g[2 * w + 1] = line[12:]
    return g


def atlas(by, cols=24, scale=2, gap=2):
    n = len(by) // 27
    rows = (n + cols - 1) // cols
    canvas = np.full((rows * (18 + gap) + gap, cols * (12 + gap) + gap), 140, dtype=np.uint8)
    for t in range(n):
        r, c = divmod(t, cols)
        y, x = gap + r * (18 + gap), gap + c * (12 + gap)
        canvas[y:y + 18, x:x + 12] = 255 - tile(by, t) * 255
    im = Image.fromarray(canvas, "L")
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def grid(by, cols, rows, skip=0):
    """Gap-less rectangular placement GUESS (needs the real runtime char-map to be correct)."""
    canvas = np.zeros((rows * 18, cols * 12), dtype=np.uint8)
    n = len(by) // 27
    for i in range(cols * rows):
        if skip + i >= n:
            break
        r, c = divmod(i, cols)
        canvas[r * 18:r * 18 + 18, c * 12:c * 12 + 12] = tile(by, skip + i)
    return Image.fromarray((255 - canvas * 255).astype("uint8"), "L")


if __name__ == "__main__":
    a = sys.argv[1:]
    d = open(a[0], "rb").read()
    off = int(a[1], 16)
    out = Path(a[2]).expanduser() if len(a) > 2 and not a[2].startswith("--") else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    opt = lambda k, dflt: a[a.index(k) + 1] if k in a else dflt
    cols = int(opt("--cols", "24"))
    maphex, length, by = decode_blob(d, off)
    n = len(by) // 27
    print(f"blob {off:#07x}: map={maphex} len={length} tiles={n}")
    p = out / f"atlas_{off:06x}.png"
    atlas(by, cols=cols).save(p)
    print("wrote", p)
    if "--grid" in a:
        spec = opt("--grid", "54x9@0")
        cr, _, sk = spec.partition("@")
        gc, gr = (int(x) for x in cr.split("x"))
        sk = int(sk) if sk else 0
        p = out / f"grid_{off:06x}_{gc}x{gr}_s{sk}.png"
        grid(by, gc, gr, sk).save(p)
        print("wrote", p, "(placement guess; needs runtime char-map)")
