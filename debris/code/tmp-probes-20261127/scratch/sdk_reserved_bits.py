import re,gzip,os,collections
R='/mnt/2tb/git/awto-ddc'
fields=collections.defaultdict(list)
for l in gzip.open(R+'/re/regdb/RTD2795T-CG.tsv.gz','rt'):
    f=l.rstrip('\n').split('\t')
    if len(f)<17 or f[4]!='FIELD': continue
    try: a=int(f[1],16); hi=int(f[6]); lo=int(f[7])
    except: continue
    fields[a].append((hi,lo,f[8],f[16].strip()))
defs={}
H=R+'/fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h'
for l in open(H,errors='replace'):
    m=re.match(r'#define\s+(P[0-9A-F]+_[0-9A-F]{2}_\w+)\s+(0x[0-9A-Fa-f]+)',l)
    if m: defs[m.group(1)]=int(m.group(2),16)
for fn in ['RL6449_Series_McuInterface.h']:
    for l in open(R+'/fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Header/'+fn,errors='replace'):
        m=re.search(r'__at\((0x[0-9A-Fa-f]+)\).*?\b(MCU_\w+)\s*;',l)
        if m: defs[m.group(2)]=int(m.group(1),16)
def ev(s):
    s=re.sub(r'\b_BIT(\d)\b',lambda m:str(1<<int(m.group(1))),s)
    s=re.sub(r'\(BYTE\)|\(unsigned char\)','',s)
    if re.search(r'[A-Za-z_]',re.sub(r'0x[0-9A-Fa-f]+','',s)): return None
    try: return eval(s,{},{})&0xFF
    except: return None
def split_args(s):
    d=0;cur='';out=[]
    for c in s:
        if c=='(':d+=1
        if c==')':d-=1
        if c==',' and d==0: out.append(cur.strip());cur=''
        else: cur+=c
    out.append(cur.strip());return out
call=re.compile(r'\b(ScalerSetBit|ScalerSetByte|ScalerSetBit_EXINT|ScalerSetByte_EXINT|ScalerSetBit_WDINT)\s*\((.*)\)\s*;')
res=collections.defaultdict(lambda:{'sites':[],'bits':set()})
def weak(d): d=d.strip().lower(); return d=='' or d.startswith('reserved') or d.startswith('dummy') or d in('rsv','reserve')
for root,_,fs in os.walk(R+'/fw/sdk'):
    for fn in fs:
        if not fn.endswith('.c') and not fn.endswith('.h'): continue
        p=os.path.join(root,fn)
        if 'RegCommonInclude' in fn: continue
        for i,l in enumerate(open(p,errors='replace'),1):
            m=call.search(l)
            if not m: continue
            a=split_args(m.group(2))
            if len(a)<2 or a[0] not in defs: continue
            addr=defs[a[0]]
            if m.group(1).startswith('ScalerSetBit') and len(a)==3:
                an=ev(a[1].replace('~','0xFF^') if False else a[1]) if '~' not in a[1] else None
                if '~' in a[1]:
                    inner=a[1].strip()
                    inner=inner[1:] if inner.startswith('~') else inner
                    v=ev(inner); 
                    if v is None: continue
                    touched=v
                else:
                    v=ev(a[1]); 
                    if v is None: continue
                    touched=(~v)&0xFF
                orv=ev(a[2]); 
                if orv is not None: touched|=orv
            elif m.group(1).startswith('ScalerSetByte'):
                v=ev(a[1])
                if v is None: continue
                touched=v   # only the 1 bits
            else: continue
            for b in range(8):
                if not touched>>b&1: continue
                cov=[x for x in fields.get(addr,[]) if x[1]<=b<=x[0]]
                if not fields.get(addr): kind='NOREG'
                elif not cov: kind='NOFIELD'
                elif all(weak(x[3]) for x in cov): kind='WEAK:'+cov[0][2]
                else: continue
                key=(a[0],addr,b,kind)
                res[key]['sites'].append(f"{p.replace(R+'/fw/sdk/','')}:{i}")
out=open(R+'/tmp/scratch/sdk_reserved_bits.tsv','w')
for (n,a,b,k),v in sorted(res.items(),key=lambda x:(x[0][1],x[0][2])):
    out.write(f"{n}\t0x{a:04X}\tbit{b}\t{k}\t{len(v['sites'])}\t{v['sites'][0]}\n")
print(len(res))
