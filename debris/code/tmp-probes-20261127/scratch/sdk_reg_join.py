import re,gzip,os,collections,sys
R='/mnt/2tb/git/awto-ddc'
HDR=R+'/fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h'
reg=collections.defaultdict(lambda:{'names':set(),'desc':[], 'fields':0})
for l in gzip.open(R+'/re/regdb/RTD2795T-CG.tsv.gz','rt'):
    f=l.rstrip('\n').split('\t')
    if len(f)<17 or f[0]=='page': continue
    try: a=int(f[1],16)
    except: continue
    reg[a]['names'].add(f[5])
    if f[4]=='FIELD':
        reg[a]['fields']+=1
        d=f[16].strip(); fld=f[8]
        reg[a]['desc'].append((fld,d))
defs={}
for l in open(HDR,errors='replace'):
    m=re.match(r'#define\s+(P[0-9A-F]+_[0-9A-F]{2}_\w+)\s+(0x[0-9A-Fa-f]+)',l)
    if m: defs[m.group(1)]=int(m.group(2),16)
mcu={}
for fn in ['RL6449_Series_McuInterface.h','RL6449_Series_McuCommonInclude.h']:
    for l in open(R+'/fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Header/'+fn,errors='replace'):
        m=re.search(r'__at\((0x[0-9A-Fa-f]+)\).*?\b(MCU_\w+)\s*;',l)
        if m: mcu[m.group(2)]=int(m.group(1),16)
allsym=dict(defs); allsym.update(mcu)
# usage
use=collections.defaultdict(list)
pat=re.compile(r'\b(P[0-9A-F]+_[0-9A-F]{2}_\w+|MCU_\w+)\b')
for root,_,fs in os.walk(R+'/fw/sdk'):
    for fn in fs:
        if not fn.endswith(('.c','.h')): continue
        p=os.path.join(root,fn)
        if p==HDR or fn in ('AwtoRegs.h','RL6449_Series_McuInterface.h','RL6449_Series_McuCommonInclude.h'): continue
        if 'RegCommonInclude' in fn: continue
        for i,l in enumerate(open(p,errors='replace'),1):
            for m in pat.finditer(l):
                if m.group(1) in allsym: use[m.group(1)].append((p.replace(R+'/fw/sdk/',''),i,l.strip()))
def status(a):
    r=reg.get(a)
    if not r: return 'ABSENT'
    ds=[d for f,d in r['desc']]
    real=[d for d in ds if d and d.lower() not in('reserved','reserve','dummy','rsv')]
    if not r['desc']: return 'REG_NO_FIELDS'
    if not real: return 'EMPTY'
    return 'OK'
out=open(R+'/tmp/scratch/sdk_reg_join.tsv','w')
cnt=collections.Counter(); ucnt=collections.Counter()
for n,a in sorted(allsym.items(),key=lambda x:x[1]):
    s=status(a); cnt[s]+=1
    u=use.get(n,[])
    if u: ucnt[s]+=1
    out.write('\t'.join([n,'0x%04X'%a,s,','.join(sorted(reg[a]['names'])) if a in reg else '',str(len(u))]+[f'{p}:{i}: {t[:140]}' for p,i,t in u[:4]])+'\n')
print('defs',len(defs),'mcu',len(mcu)); print(cnt); print('used',ucnt)
