#!/usr/bin/env python3
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
def tilebits(t):
    base=t*27;bits=[]
    for w in range(9):
        b0,b1,b2=by[base+w*3],by[base+w*3+1],by[base+w*3+2]
        for b in (b2,b1,b0): bits+=[(b>>k)&1 for k in range(7,-1,-1)]
    return bits
def render(cols,skip,tag):
    n=N-skip; rows=(n+cols-1)//cols
    im=Image.new('L',(cols*12,rows*18),200)
    for t in range(n):
        tb=tilebits(skip+t); tx,ty=(t%cols)*12,(t//cols)*18
        for p in range(216): im.putpixel((tx+p%12,ty+p//12),0 if tb[p] else 255)
    im=im.resize((im.width,im.height),Image.NEAREST)
    im.save(OUT/f'd56_{tag}.png'); print('wrote',tag,'rows',rows)
for skip in (0,98,100,102,104,106):
    render(56,skip,f's{skip}')
# also render full from 0 at 56 to see header+body together
