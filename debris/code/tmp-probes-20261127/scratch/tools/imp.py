import os,shutil,json,hashlib,sys
D='/mnt/2tb/git/awto-ddc/tmp/scratch/doom-complete/doom-download';R='/mnt/2tb/git/awto-games-dw8051'
def h(p):return hashlib.sha256(open(p,'rb').read()).hexdigest()
man=json.load(open(D+'/download-manifest.json'))
imported=set(open('/mnt/2tb/git/awto-ddc/tmp/scratch/import-list.txt').read().split('\n'))
def dest(p):
    if p.startswith('source/'):
        rel=p[7:]
        return rel if rel in imported or os.path.exists(R+'/'+rel) and h(R+'/'+rel)==h(D+'/'+p) else None
    if p.startswith('checkpoints/'):
        rel=p[12:]
        if rel.startswith('source/'): return None
        if rel=='README.md': return None
        if '/' not in rel and rel.endswith('_README.md'): return 'docs/checkpoints/'+rel
        return 'artifacts/'+rel
    return p
out=[];stats={'copied':0,'identical_skipped':0,'dropped_source':0,'dup_readme':0};added=0;big=[]
for e in man['files']:
    p=e['path'];d=dest(p)
    if p=='README.md': continue   # download README replaced by merged README
    if p=='download-manifest.json': continue
    if d is None:
        if p.startswith('source/'): stats['dropped_source']+=1
        else: stats['dup_readme']+=1
        continue
    src=D+'/'+p;dst=R+'/'+d
    if os.path.exists(dst) and h(dst)==e['sha256']: stats['identical_skipped']+=1
    else:
        os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(src,dst);stats['copied']+=1;added+=e['bytes'];big.append((e['bytes'],d))
    out.append({'path':d,'bytes':e['bytes'],'sha256':e['sha256']})
# source entries imported/identical now mapped; also doom delta source files included above via dest
# README entries
for p,d in (('checkpoints/README.md','translated/PROJECT_README.md'),):
    pass
# top-level copy of download README as docs
shutil.copy2(D+'/README.md',R+'/docs/download-README.md')
sys.stderr.write(str(stats)+'\n'+str(added)+'\n')
big.sort(reverse=True);print(big[:15])
man2={k:v for k,v in man.items() if k!='files'};man2['version']=2
man2['note']='paths are relative to the awto-games-dw8051 repo root; checkpoints/ merged into artifacts/ and docs/checkpoints/; source/ delta files at repo-relative paths; full awto-ddc snapshot not included'
man2['files']=sorted(out,key=lambda x:x['path'])
json.dump(man2,open(R+'/download-manifest.json','w'),indent=1)
