#!/usr/bin/env python3
"""Find true grid width of blob D by scoring vertical edge-continuity across tile columns.
If tiles are a raster in reading order at width W, then tile t's right edge should match
tile t+1's left edge (same row), and tile t's bottom should match tile t+W's top."""
from pathlib import Path
from PIL import Image

DUMP = '/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin'
OUT = Path('/home/dan/vendors/realtek/analysis/logo/glyphdec')
d = open(DUMP, 'rb').read()
CODES = ['0','100','1010','1011','1100','11010','11011','11100','111010','111011','111100','111101','1111100','1111101','1111110','11111110']

def dec(off):
    m = d[off:off+8]; L = (d[off+8] << 8) | d[off+9]
    vals = []
    for b in m: vals += [b >> 4, b & 15]
    tab = {c: v for c, v in zip(CODES, vals)}
    nibs = []; code = ''; end = None
    for bi, b in enumerate(d[off+10:off+10+L+8]):
        for k in range(8):
            code += str((b >> k) & 1)
            if code in tab: nibs.append(tab[code]); code = ''
            elif code == '11111111': end = (bi, k); break
            elif len(code) > 8: return None
        if end: break
    return bytes(((nibs[i] << 4) | nibs[i+1]) for i in range(0, len(nibs) - 1, 2))

by = dec(0x23B41)
N = len(by) // 27

def tile(t):  # 18 rows x 12 cols, B2,B1,B0 MSB-left
    base = t*27; rows = []
    for w in range(9):
        b0, b1, b2 = by[base+w*3], by[base+w*3+1], by[base+w*3+2]
        line = []
        for b in (b2, b1, b0):
            line += [(b >> k) & 1 for k in range(7, -1, -1)]
        rows.append(line[:12]); rows.append(line[12:])
    return rows  # 18 x 12

T = [tile(t) for t in range(N)]

def hmis(a, b):  # right col of a vs left col of b
    return sum(a[r][11] != b[r][0] for r in range(18))

def vmis(a, b):  # bottom row of a vs top row of b
    return sum(a[17][c] != b[0][c] for c in range(12))

# For each (skip, cols), score continuity over the image region
print('scoring widths (lower=more continuous)...')
results = []
for skip in range(90, 140):
    for cols in range(14, 75):
        n = N - skip
        rows = n // cols
        if rows < 6: continue
        s = 0; c = 0
        # sample
        for ri in range(rows):
            for ci in range(cols):
                t = skip + ri*cols + ci
                if t >= N: break
                if ci < cols-1 and t+1 < N:
                    s += hmis(T[t], T[t+1]); c += 18
                if ri < rows-1 and t+cols < N:
                    s += vmis(T[t], T[t+cols]); c += 12
        if c: results.append((s/c, cols, skip, rows))
results.sort()
print('top 25 (score, cols, skip, rows):')
for r in results[:25]:
    print(f'  score={r[0]:.4f} cols={r[1]} skip={r[2]} rows={r[3]}')
