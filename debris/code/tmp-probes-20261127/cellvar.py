#!/usr/bin/env python3
"""Test within-cell pixel-order variants at cols=56 to remove shear. Render each."""
from pathlib import Path
from PIL import Image
DUMP='/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin'
OUT=Path('/home/dan/vendors/realtek/analysis/logo/glyphdec')
d=open(DUMP,'rb').read()
CODES=['0','100','1010','1011','1100','11010','11011','11100','111010','111011','111100','111101','1111100','1111101','1111110','11111110']
def dec(off):
    m=d[off:off+8];L=(d[off+8]<<8)|d[off+9];vals=[]
    for b in m: vals+=[b>>4,b&15]
    tab={c:v for c,v in zip(CODES,vals)};nibs=[];code='';end=None
    for bi,b in enumerate(d[off+10:off+10+L+8]):
        for k in range(8):
            code+=str((b>>k)&1)
            if code in tab: nibs.append(tab[code]);code=''
            elif code=='11111111': end=(bi,k);break
            elif len(code)>8: return None
        if end: break
    return bytes(((nibs[i]<<4)|nibs[i+1]) for i in range(0,len(nibs)-1,2))
by=dec(0x23B41); N=len(by)//27

def cell_variant(t, order, msb):
    """Return 18x12 grid. order: byte triple order per word. msb: bit order within byte."""
    base=t*27; grid=[]
    for w in range(9):
        trip=[by[base+w*3],by[base+w*3+1],by[base+w*3+2]]
        if order=='b2b1b0': trip=[trip[2],trip[1],trip[0]]
        elif order=='b0b1b2': pass
        elif order=='b1b2b0': trip=[trip[1],trip[2],trip[0]]
        line=[]
        for b in trip:
            if msb: line+=[(b>>k)&1 for k in range(7,-1,-1)]
            else: line+=[(b>>k)&1 for k in range(8)]
        grid.append(line[:12]); grid.append(line[12:])
    return grid

def render(order,msb,cols,skip,colmajor=False):
    n=N-skip; rows=(n+cols-1)//cols
    im=Image.new('L',(cols*12,rows*18),200)
    for ti in range(n):
        g=cell_variant(skip+ti,order,msb)
        if colmajor:
            cx=ti//rows; cy=ti%rows
        else:
            cx=ti%cols; cy=ti//cols
        ox,oy=cx*12,cy*18
        for r in range(18):
            for c in range(12):
                im.putpixel((ox+c,oy+r),0 if g[r][c] else 255)
    tag=f'{order}_{"msb" if msb else "lsb"}_c{cols}_s{skip}{"_cm" if colmajor else ""}'
    im.save(OUT/f'var_{tag}.png'); return tag

jobs=[]
for order in ('b2b1b0','b0b1b2'):
    for msb in (True,False):
        jobs.append(render(order,msb,56,104))
# column-major assembly at 56
jobs.append(render('b2b1b0',True,56,104,colmajor=True))
print('\n'.join(jobs))
