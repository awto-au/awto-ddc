#!/usr/bin/env python3
"""Within-tile: 9 words, each 24 bits. Test how words map to the 18 rows and byte/bit order.
A wrong word->row mapping shears each tile -> global diagonal shear. Score by edge-continuity
at the best row-major width for each mapping; render top few."""
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

def tile(t, trip_order, bit_msb, word_rows):
    """word_rows: 'adjacent' -> word w = rows (2w,2w+1); 'split' -> word w = rows (w, w+9)."""
    base=t*27; g=np.zeros((18,12),dtype=np.uint8)
    for w in range(9):
        raw=[by[base+w*3],by[base+w*3+1],by[base+w*3+2]]
        trip=[raw[k] for k in trip_order]
        line=[]
        for b in trip:
            if bit_msb: line+=[(b>>k)&1 for k in range(7,-1,-1)]
            else: line+=[(b>>k)&1 for k in range(8)]
        if word_rows=='adjacent':
            g[2*w]=line[:12]; g[2*w+1]=line[12:]
        else:  # split: first halves then second halves
            g[w]=line[:12]; g[w+9]=line[12:]
    return g

def build_T(trip_order,bit_msb,word_rows):
    return [tile(t,trip_order,bit_msb,word_rows) for t in range(N)]

def best_width(T,skip,lo=48,hi=60):
    best=(9,0)
    for cols in range(lo,hi+1):
        n=N-skip; rows=n//cols
        if rows<6: continue
        s=0;c=0
        for i in range(min(n,400)):
            t=skip+i; r,cc=divmod(i,cols)
            if cc<cols-1 and t+1<N: s+=int((T[t][:,11]!=T[t+1][:,0]).sum()); c+=18
            if t+cols<N: s+=int((T[t][17]!=T[t+cols][0]).sum()); c+=12
        if c and s/c<best[0]: best=(s/c,cols)
    return best

orders=[(2,1,0),(0,1,2),(1,2,0),(0,2,1),(2,0,1),(1,0,2)]
res=[]
for trip in orders:
    for msb in (True,False):
        for wr in ('adjacent','split'):
            T=build_T(trip,msb,wr)
            sc,cols=best_width(T,104)
            res.append((sc,trip,msb,wr,cols))
res.sort()
print('best (score,triporder,msb,wordrows,cols):')
for r in res[:12]: print(f'  {r[0]:.4f} trip={r[1]} msb={r[2]} wr={r[3]} cols={r[4]}')
# render top 4
for (sc,trip,msb,wr,cols) in res[:4]:
    T=build_T(trip,msb,wr); n=N-104; rows=(n+cols-1)//cols
    canvas=np.zeros((rows*18,cols*12),dtype=np.uint8)
    for i in range(n):
        r,c=divmod(i,cols); canvas[r*18:r*18+18,c*12:c*12+12]=T[104+i]
    tag=f'wm_{"".join(map(str,trip))}_{"msb" if msb else "lsb"}_{wr}_c{cols}'
    Image.fromarray((255-canvas*255).astype('uint8'),'L').save(OUT/f'{tag}.png')
    print('rendered',tag)
