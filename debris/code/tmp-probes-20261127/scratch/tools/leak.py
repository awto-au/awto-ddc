import zipfile,sys,glob
root=sys.argv[1]
dp=zipfile.ZipFile(root+'/translated/doom-assets.dpak')
lumps={n:dp.read(n) for n in dp.namelist() if n.startswith('raw/')}
big={n:b for n,b in lumps.items() if len(b)>=64}
print(len(lumps),len(big))
def scan(label,data):
    hits=[]
    for n,b in big.items():
        # sample 3 windows of 48 bytes
        for off in (0,len(b)//2,len(b)-48):
            w=b[off:off+48]
            if len(set(w))>4 and w in data: hits.append((n,off));break
    print(label,len(data),'verbatim lump hits:',len(hits),hits[:8])
for f in ['/translated/native/E1M1/doom_renderer.bin','/translated/native/E1M1/tables.json']:
    scan(f,open(root+f,'rb').read())
z=zipfile.ZipFile(root+'/translated/native/E1M1/ddr.zip')
scan('ddr.zip all',b''.join(z.read(n) for n in z.namelist()))
# dpak non-raw
scan('dpak non-raw',b''.join(dp.read(n) for n in dp.namelist() if not n.startswith('raw/')))
