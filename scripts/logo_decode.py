#!/usr/bin/env python3
"""Render OSD font tiles from a JXC 4K flash dump to a PNG contact sheet (static analysis).

usage: logo_decode.py <dump> <start-hex> <count> <out.png> [--bpp 2] [--w 12] [--h 9] [--cols N] [--scale N] [--stride BYTES]
Default tile = 12x9 px, 2 bpp, MSB-first row-major = 27 bytes (bank0 font at 0x28C6.., [fw] digits 0-3 legible).
Pixel value -> grey: 0 black, 1 dark, 2 light, 3 white.
"""
import sys
from PIL import Image

def tile_px(b, w, h, bpp):
    px, mask = [], (1 << bpp) - 1
    for v in b:
        for k in range(8 - bpp, -1, -bpp):
            px.append((v >> k) & mask)
    return [px[r*w:(r+1)*w] for r in range(h)]

def main():
    a = sys.argv
    dump, start, count, out = a[1], int(a[2], 16), int(a[3]), a[4]
    opt = lambda n, d: int(a[a.index(n)+1]) if n in a else d
    bpp, w, h = opt("--bpp", 2), opt("--w", 12), opt("--h", 9)
    cols, sc = opt("--cols", 30), opt("--scale", 2)
    stride = opt("--stride", w*h*bpp//8)
    d = open(dump, "rb").read()
    rows = (count + cols - 1)//cols
    im = Image.new("L", (cols*(w+2), rows*(h+2)), 100)
    for n in range(count):
        o = start + stride*n
        t = tile_px(d[o:o+(w*h*bpp+7)//8], w, h, bpp)
        ox, oy = (n % cols)*(w+2), (n//cols)*(h+2)
        for r in range(h):
            for c in range(w):
                im.putpixel((ox+c, oy+r), t[r][c]*255//((1 << bpp)-1))
    im.resize((im.width*sc, im.height*sc), Image.NEAREST).save(out)

if __name__ == "__main__":
    main()
