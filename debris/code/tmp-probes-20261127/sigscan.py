import sys
d=open(sys.argv[1],'rb').read()
n=len(d)
hits=[]
for i in range(n-12):
    b=d[i:i+8]
    nib=set()
    for x in b: nib.add(x>>4); nib.add(x&15)
    if len(nib)==16:
        L=(d[i+8]<<8)|d[i+9]
        if 8<=L<=0x6000 and i+10+L<=n:
            hits.append((i,L,b.hex()))
print(len(hits))
for h in hits[:60]:
    i,L,_=h
    tail=d[i+10+L-2:i+10+L].hex()
    print(f"0x{i:06X} len={L} map={h[2]} streamtail={tail}")
