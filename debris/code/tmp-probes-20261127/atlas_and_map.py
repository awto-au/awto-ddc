#!/usr/bin/env python3
"""Clean tile atlas of each blob + char-map array search in code space."""
from pathlib import Path
from PIL import Image

DUMP = '/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin'
OUT = Path('/home/dan/vendors/realtek/analysis/logo/glyphdec')
d = open(DUMP, 'rb').read()
CODES = ['0','100','1010','1011','1100','11010','11011','11100','111010','111011','111100','111101','1111100','1111101','1111110','11111110']
BLOBS = {'A':0x228C6, 'B':0x22BED, 'C':0x231AB, 'D':0x23B41}

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

def tile_bits(by, t):
    base = t * 27; bits = []
    for w in range(9):
        b0, b1, b2 = by[base+w*3], by[base+w*3+1], by[base+w*3+2]
        for b in (b2, b1, b0):
            bits += [(b >> k) & 1 for k in range(7, -1, -1)]
    return bits

def atlas(name, by, cols=20):
    nt = len(by) // 27
    rows = (nt + cols - 1) // cols
    im = Image.new('L', (cols*13, rows*19), 160)
    for t in range(nt):
        tb = tile_bits(by, t)
        tx, ty = (t % cols)*13, (t // cols)*19
        for p in range(216):
            im.putpixel((tx + p % 12, ty + p // 12), 0 if tb[p] else 255)
    im = im.resize((im.width*2, im.height*2), Image.NEAREST)
    im.save(OUT / f'atlas_{name}.png')
    return nt

for k, off in BLOBS.items():
    by = dec(off)
    n = atlas(k, by)
    print(f'atlas {k} @ {off:#x}: {n} tiles')

# ---- char-map search: runs with 0xFE separators ending in 0xFF ----
# For a 70x10 grid: ~10 rows, each ending 0xFE, final 0xFF. Indices are small-ish bytes.
def scan_maps(maxidx=255):
    hits = []
    i = 0; n = len(d)
    while i < n - 20:
        # candidate start: look for a region with several 0xFE within a window, ending 0xFF
        if d[i] == 0xFE or d[i] == 0xFF:
            i += 1; continue
        j = i; rows = 0; cells = 0; ok = True; last_fe = -1
        while j < n and j - i < 2000:
            b = d[j]
            if b == 0xFF:
                break
            if b == 0xFE:
                rows += 1; last_fe = j
                if j > i and d[j-1] == 0xFE:  # two FE in a row unusual but allowed
                    pass
            # all bytes allowed; just count
            cells += 1
            j += 1
        if j < n and d[j] == 0xFF and 5 <= rows <= 14 and (j - i) > 50:
            hits.append((i, j, rows, j - i))
        i = j + 1 if (j < n and d[j] == 0xFF) else i + 1
    return hits

hits = scan_maps()
print(f'\ncandidate char-maps (0xFE-separated runs ending 0xFF, 5-14 rows): {len(hits)}')
for (st, en, rows, ln) in hits[:40]:
    seg = d[st:en]
    fe_pos = [p for p, b in enumerate(seg) if b == 0xFE]
    rowlens = []
    prev = 0
    for p in fe_pos:
        rowlens.append(p - prev); prev = p + 1
    rowlens.append(len(seg) - prev)
    print(f'0x{st:06X}-0x{en:06X} len={ln} rows={rows} rowlens={rowlens}')
