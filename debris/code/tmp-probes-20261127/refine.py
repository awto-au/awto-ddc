#!/usr/bin/env python3
"""Refine blob-D decode: render tile-grid layouts at many widths + pixel orders, find legible logo."""
import sys
from pathlib import Path
from PIL import Image

DUMP = '/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin'
OUT = Path('/home/dan/vendors/realtek/analysis/logo/glyphdec')
OUT.mkdir(parents=True, exist_ok=True)
d = open(DUMP, 'rb').read()
CODES = ['0','100','1010','1011','1100','11010','11011','11100','111010','111011','111100','111101','1111100','1111101','1111110','11111110']

def dec(off):
    m = d[off:off+8]; L = (d[off+8] << 8) | d[off+9]
    vals = []
    for b in m: vals += [b >> 4, b & 15]
    tab = {c: v for c, v in zip(CODES, vals)}
    nibs = []; code = ''; end = None
    for bi, b in enumerate(d[off+10:off+10+L+8]):
        for k in range(8):               # LSB-first
            code += str((b >> k) & 1)
            if code in tab: nibs.append(tab[code]); code = ''
            elif code == '11111111': end = (bi, k); break
            elif len(code) > 8: return None
        if end: break
    return L, end, nibs

def nib_to_bytes(nibs):
    return bytes(((nibs[i] << 4) | nibs[i+1]) for i in range(0, len(nibs) - 1, 2))

def tile_bits_b2b1b0(by, t):
    """Doc model: 27 bytes/tile, 3 bytes per 24-bit word read B2,B1,B0; MSB left. 18 rows x 12."""
    base = t * 27
    bits = []
    for w in range(9):                 # 9 words per tile
        b0, b1, b2 = by[base+w*3], by[base+w*3+1], by[base+w*3+2]
        for b in (b2, b1, b0):
            bits += [(b >> k) & 1 for k in range(7, -1, -1)]
    return bits  # 216 bits = 18 rows of 12

def tile_bits_b0b1b2(by, t):
    base = t * 27
    bits = []
    for w in range(9):
        b0, b1, b2 = by[base+w*3], by[base+w*3+1], by[base+w*3+2]
        for b in (b0, b1, b2):
            bits += [(b >> k) & 1 for k in range(7, -1, -1)]
    return bits

def render_grid(by, ntiles, tilefn, cols, skip, name):
    rows = (ntiles + cols - 1) // cols
    im = Image.new('L', (cols*12, rows*18), 128)
    for t in range(ntiles):
        tb = tilefn(by, skip + t)
        tx, ty = (t % cols)*12, (t // cols)*18
        for p in range(216):
            im.putpixel((tx + p % 12, ty + p // 12), 0 if tb[p] else 255)
    im = im.resize((im.width*2, im.height*2), Image.NEAREST)
    im.save(OUT / name)

if __name__ == '__main__':
    L, end, nibs = dec(0x23B41)
    by = nib_to_bytes(nibs)
    ntot = len(by) // 27
    print('tiles', ntot)
    # widths to scan over the whole set and over skipped sets
    jobs = [
        (ntot, tile_bits_b2b1b0, 0, 'd_full_b2b1b0'),
        (ntot, tile_bits_b0b1b2, 0, 'd_full_b0b1b2'),
    ]
    for skip in (100, 103, 96):
        jobs.append((ntot - skip, tile_bits_b2b1b0, skip, f'd_skip{skip}_b2b1b0'))
    cols_scan = [16, 18, 20, 22, 23, 24, 27, 54]
    for (nt, fn, skip, tag) in jobs:
        for cols in cols_scan:
            render_grid(by, nt, fn, cols, skip, f'{tag}_c{cols}.png')
    print('done', len(list(OUT.glob('d_*.png'))))
