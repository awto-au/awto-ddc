#!/usr/bin/env python3
"""Clean contact sheet of blob-D tiles with gaps, to judge if individual tiles are clean strokes."""
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
def tile(t):
    base=t*27; g=np.zeros((18,12),dtype=np.uint8)
    for w in range(9):
        line=[]
        for b in (by[base+w*3+2],by[base+w*3+1],by[base+w*3]): line+=[(b>>k)&1 for k in range(7,-1,-1)]
        g[2*w]=line[:12]; g[2*w+1]=line[12:]
    return g
def sheet(tiles_idx,cols,name,scale=3):
    rows=(len(tiles_idx)+cols-1)//cols
    gap=2
    canvas=np.full((rows*(18+gap)+gap,cols*(12+gap)+gap),140,dtype=np.uint8)
    for k,ti in enumerate(tiles_idx):
        r,c=divmod(k,cols); g=tile(ti)
        y=gap+r*(18+gap); x=gap+c*(12+gap)
        canvas[y:y+18,x:x+12]=255-g*255
    im=Image.fromarray(canvas,'L').resize((canvas.shape[1]*scale,canvas.shape[0]*scale),Image.NEAREST)
    im.save(OUT/name)
# full contact sheet of all 586, and the body region 104..
sheet(list(range(N)),28,'contact_D_all.png',scale=2)
sheet(list(range(104,N)),28,'contact_D_body.png',scale=2)
sheet(list(range(0,120)),20,'contact_D_head.png',scale=3)
print('done')
