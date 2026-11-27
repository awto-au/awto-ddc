#!/usr/bin/env python3
"""Treat decoded tile-pixels as one continuous pixel stream; find stride (px/row) that
maximizes correlation between row r and row r+1. Handles non-tile-aligned widths.
Two pixel orderings: (a) tiles then within-tile raster, (b) already-raster."""
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

# pixel stream A: tile-order, within tile B2,B1,B0 MSB, 18 rows x12. This is what we rendered.
def stream_tilepix():
    s=[]
    for t in range(N):
        base=t*27
        for w in range(9):
            for b in (by[base+w*3+2],by[base+w*3+1],by[base+w*3]):
                s+=[(b>>k)&1 for k in range(7,-1,-1)]
    return np.array(s,dtype=np.int8)

# pixel stream B: raw bit stream MSB-first, no tiling
def stream_raw(msb=True):
    s=[]
    for b in by:
        if msb: s+=[(b>>k)&1 for k in range(7,-1,-1)]
        else: s+=[(b>>k)&1 for k in range(8)]
    return np.array(s,dtype=np.int8)

def best_stride(s, lo, hi):
    res=[]
    for W in range(lo,hi+1):
        H=len(s)//W
        if H<20: continue
        a=s[:W*H].reshape(H,W).astype(np.int16)
        # correlation between adjacent rows: fraction of matching pixels
        match=(a[:-1]==a[1:]).mean()
        res.append((match,W,H))
    res.sort(reverse=True)
    return res

sA=stream_tilepix()
sB=stream_raw(True)
sBl=stream_raw(False)
print('stream A (tile-pixel) best strides:')
for r in best_stride(sA,600,760)[:10]: print(f'  match={r[0]:.4f} W={r[1]} H={r[2]}')
print('stream B (raw MSB) best strides:')
for r in best_stride(sB,400,900)[:10]: print(f'  match={r[0]:.4f} W={r[1]} H={r[2]}')
print('stream B (raw LSB) best strides:')
for r in best_stride(sBl,400,900)[:10]: print(f'  match={r[0]:.4f} W={r[1]} H={r[2]}')

def render_stream(s,W,name,skiprows=0):
    H=len(s)//W
    a=s[skiprows*W:W*H].reshape(-1,W)
    im=Image.fromarray((255-a.astype('uint8')*255),'L')
    im.save(OUT/name)
# render top candidates
for s,tag,rng in [(sA,'A',(600,760)),(sB,'Braw',(400,900)),(sBl,'Blsb',(400,900))]:
    top=best_stride(s,*rng)[:3]
    for (m,W,H) in top:
        render_stream(s,W,f'stride_{tag}_W{W}.png')
print('rendered top candidates')
