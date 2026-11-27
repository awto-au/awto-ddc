#!/usr/bin/env python3
"""Search dump for a glyph-index map for blob D (586 glyphs).
Indices need up to 586 -> 16-bit (2 bytes). Look for runs of u16 values mostly < 586,
~560-900 entries, possibly with 0xFFFF/0xFEFE separators. Also try byte-indices if a logo
sub-set is small. Report dense regions."""
import numpy as np
d=open('/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin','rb').read()
n=len(d)
NG=586
# ---- u16-LE scan ----
def scan_u16(le=True):
    hits=[]
    i=0
    while i<n-2:
        # try to extend a run of u16 in [0,NG)
        j=i; cnt=0; cntlt=0
        while j<n-1:
            v=(d[j]|(d[j+1]<<8)) if le else ((d[j]<<8)|d[j+1])
            if v<NG: cntlt+=1
            else: break
            j+=2; cnt+=1
        if cnt>=100:
            hits.append((i,cnt,j))
            i=j
        else:
            i+=1
    return hits
for le in (True,False):
    h=scan_u16(le)
    lbl='LE' if le else 'BE'
    print('u16',lbl,'runs of >=100 values in [0,586):',len(h))
    for (st,cnt,en) in sorted(h,key=lambda x:-x[1])[:8]:
        print(f'  0x{st:06X} count={cnt} end=0x{en:06X}')
# ---- byte-index scan (if indices < 256, e.g. logo uses glyphs 0..255) ----
# look for runs where most bytes < some cap and length ~ a grid (e.g. 560-900)
print()
arr=np.frombuffer(d,dtype=np.uint8)
# sliding: density of bytes < 200 over window 700
for cap in (128,200):
    best=[]
    W=700
    cs=np.cumsum((arr<cap).astype(int))
    for i in range(0,n-W,50):
        dens=(cs[i+W]-cs[i])/W
        if dens>0.97: best.append((i,round(dens,3)))
    # merge
    print(f'byte<{cap} dense (>0.97) 700-windows:',len(best),'first few:',best[:6])
