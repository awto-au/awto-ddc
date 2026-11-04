#!/usr/bin/env python3
"""Offline VLC glyph decode + contact sheet of a flash-dump region (static; reads a file only).

usage: glyph_decode.py <dump> <start-hex> <nbytes-hex> <outdir> [--map zero|identity|freq] [--bpp 1|2|4] [--cells 12x18,16x16,8x16]
Value map: regdb reset of 0x3A0F-0x3A16 (vlc_0..vlc_f) is all 0x00 -> 'zero' = hardware default (degenerate).
Stream is cut at END (1111_1111); each segment -> nibbles -> bpp-packed pixels -> WxH cell. Log: tmp/logs/glyph_decode.log
"""
import sys, os, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vlc_probe import CODES, DEC
from PIL import Image


def decode_idx(buf):
    """Return list of segments of code indices (value-map independent)."""
    bits = "".join(f"{b:08b}" for b in buf)
    out, cur, code = [], [], ""
    for ch in bits:
        code += ch
        if code == "11111111":
            out.append(cur); cur = []; code = ""
        elif code in DEC:
            cur.append(DEC[code]); code = ""
    if cur: out.append(cur)
    return out


def make_map(kind, segs):
    if kind == "zero": return [0] * 16
    if kind == "identity": return list(range(16))
    cnt = collections.Counter(v for s in segs for v in s)  # freq rank -> value 0,1,2..
    m = [0] * 16
    for rank, (idx, _) in enumerate(cnt.most_common()): m[idx] = rank
    return m


def pixels(seg, m, bpp):
    nib = [m[i] for i in seg]
    if bpp == 4: return nib
    px = []
    for n in nib:
        if bpp == 1: px += [(n >> s) & 1 for s in (3, 2, 1, 0)]
        else: px += [(n >> 2) & 3, n & 3]
    return px


def sheet(segs, m, bpp, w, h, n, cols, path):
    rows = (min(n, len(segs)) + cols - 1) // cols
    im = Image.new("L", (cols * (w + 1), rows * (h + 1)), 128)
    mx = {1: 1, 2: 3, 4: 15}[bpp]
    for k, s in enumerate(segs[:n]):
        px = pixels(s, m, bpp)[: w * h]
        x0, y0 = (k % cols) * (w + 1), (k // cols) * (h + 1)
        for i, v in enumerate(px):
            im.putpixel((x0 + i % w, y0 + i // w), 255 - v * 255 // mx)
    im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
    im.save(path)


if __name__ == "__main__":
    a = sys.argv[1:]
    d = open(a[0], "rb").read()
    s, n = int(a[1], 16), int(a[2], 16)
    out = Path(a[3]).expanduser(); out.mkdir(parents=True, exist_ok=True)
    opt = lambda k, dflt: a[a.index(k) + 1] if k in a else dflt
    kinds = [opt("--map", "zero,identity,freq")][0].split(",")
    bpps = [int(x) for x in opt("--bpp", "1,2,4").split(",")]
    cells = [tuple(map(int, c.split("x"))) for c in opt("--cells", "12x18,16x16,8x16").split(",")]
    segs = [g for g in decode_idx(d[s:s + n]) if g]
    lens = collections.Counter(len(g) for g in segs)
    print("segments", len(segs), "top lens", lens.most_common(8))
    for kind in kinds:
        m = make_map(kind, segs)
        print(kind, "map", m)
        for bpp in bpps:
            for (w, h) in cells:
                p = out / f"glyph_{s:06x}_{kind}_{bpp}bpp_{w}x{h}.png"
                sheet(segs, m, bpp, w, h, 64, 8, p)
