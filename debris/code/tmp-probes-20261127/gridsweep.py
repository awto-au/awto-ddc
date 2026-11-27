#!/usr/bin/env python3
"""Render blob D as proper tile grids across widths 48-60, skip variants. Visual de-shear search."""
from pathlib import Path
import numpy as np
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
def tilearr(t):
    base=t*27; g=np.zeros((18,12),dtype=np.uint8); idx=0
    for w in range(9):
        line=[]
        for b in (by[base+w*3+2],by[base+w*3+1],by[base+w*3]):
            line+=[(b>>k)&1 for k in range(7,-1,-1)]
        g[2*w]=line[:12]; g[2*w+1]=line[12:]
    return g
T=[tilearr(t) for t in range(N)]
def grid(cols,skip):
    n=N-skip; rows=(n+cols-1)//cols
    canvas=np.zeros((rows*18,cols*12),dtype=np.uint8)
    for i in range(n):
        t=T[skip+i]; r,c=divmod(i,cols)
        canvas[r*18:r*18+18,c*12:c*12+12]=t
    return canvas
# build a vertical stack of candidate widths for one skip, labelled
def stack(skip,widths):
    imgs=[]
    for w in widths:
        g=grid(w,skip)
        im=(255-g*255).astype('uint8')
        imgs.append((w,im))
    return imgs
for skip in (98,100,104):
    for w in range(48,61):
        g=grid(w,skip)
        Image.fromarray((255-g*255).astype('uint8'),'L').save(OUT/f'grid_s{skip}_c{w}.png')
print('done')
