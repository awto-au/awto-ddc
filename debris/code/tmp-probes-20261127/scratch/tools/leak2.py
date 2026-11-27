import zipfile,sys,os,io,collections
root=sys.argv[1]
dp=zipfile.ZipFile(root+'/translated/doom-assets.dpak')
keys={}
for n in dp.namelist():
    if n.startswith('raw/'):
        b=dp.read(n)
        if len(b)>=256 and len(set(b[:64]))>6: keys[b[:64]]=n
        if len(b)>=256 and len(set(b[-64:]))>6: keys[b[-64:]]=n
print(len(keys),'keys')
rep=collections.Counter()
ex=collections.defaultdict(set)
def scan(label,data):
    for k,n in keys.items():
        if k in data: rep[label]+=1; ex[label].add(n)
for dirpath,_,fs in os.walk(root):
    if '/source' in dirpath+'/' and dirpath.startswith(root+'/source'): continue
    for f in fs:
        p=os.path.join(dirpath,f)
        if f.endswith(('.png','.mp4')) or p.endswith('doom1.wad'): continue
        lab=os.path.relpath(p,root)
        if f.endswith(('.zip','.dpak')):
            z=zipfile.ZipFile(p)
            data=b''.join(z.read(n) for n in z.namelist() if not n.startswith('raw/'))
        else: data=open(p,'rb').read()
        scan(lab,data)
byd=collections.Counter()
for k,v in rep.items(): byd[os.path.dirname(k)]+=1
for k,v in sorted(rep.items())[:400]: print(v,k,sorted(ex[k])[:3])
