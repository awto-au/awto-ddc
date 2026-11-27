#!/usr/bin/env python3
"""Column-major tile assembly sweep: tile i -> (row=i%H, col=i//H). Sweep H (tile-rows)."""
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
    base=t*27; g=np.zeros((18,12),dtype=np.uint8)
    for w in range(9):
        line=[]
        for b in (by[base+w*3+2],by[base+w*3+1],by[base+w*3]):
            line+=[(b>>k)&1 for k in range(7,-1,-1)]
        g[2*w]=line[:12]; g[2*w+1]=line[12:]
    return g
T=[tilearr(t) for t in range(N)]

def colmajor(H,skip):
    n=N-skip; cols=(n+H-1)//H
    canvas=np.zeros((H*18,cols*12),dtype=np.uint8)
    for i in range(n):
        t=T[skip+i]; c=i//H; r=i%H
        canvas[r*18:r*18+18,c*12:c*12+12]=t
    return canvas

# edge-score for column-major
def score_cm(H,skip):
    n=N-skip
    s=0;c=0
    for i in range(min(n,500)):
        r=i%H; cc=i//H
        if r<H-1 and skip+i+1<N:  # below neighbour is i+1
            a=T[skip+i]; b=T[skip+i+1]
            s+=int((a[17]!=b[0]).sum()); c+=12
        if skip+i+H<N:  # right neighbour is i+H
            a=T[skip+i]; b=T[skip+i+H]
            s+=int((a[:,11]!=b[:,0]).sum()); c+=18
    return s/c if c else 1
res=[]
for skip in range(90,140):
    for H in range(6,16):
        res.append((score_cm(H,skip),H,skip))
res.sort()
print('best column-major (score,H,skip):')
for r in res[:15]: print(f'  score={r[0]:.4f} H={r[1]} skip={r[2]}')
for (sc,H,skip) in res[:4]:
    Image.fromarray((255-colmajor(H,skip)*255).astype('uint8'),'L').save(OUT/f'cm_H{H}_s{skip}.png')
print('rendered')
