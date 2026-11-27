import json,re,sys,glob,os
R='/mnt/2tb/git/awto-ddc/re/jxc-4k/'
th=json.load(open('tmp/b0_thunks.json'))
# existing rows (all statuses) in bank0 file
exist_addr=set(); exist_name=set()
for l in open(R+'ghidra_names_bank0.tsv'):
    if l.startswith('#') or not l.strip(): continue
    p=l.rstrip('\n').split('\t')
    exist_addr.add(p[0].lower()); exist_name.add(p[1])
# names from other banks
bank_names={}
for b in range(1,7):
    d={}
    for l in open(R+f'ghidra_names_bank{b}.tsv'):
        if l.startswith('#') or not l.strip(): continue
        p=l.split('\t')
        if p[0].startswith('CODE:') and len(p)>2 and p[2] in('func','label'):
            d[int(p[0][5:],16)]=p[1]
    bank_names[b]=d
rows=[]  # (addr, name, type, comment, conf)
def add(a,n,t,c,conf): rows.append((a,n,t,c,conf))
# ---- hand rows come from tmp/b0_hand.tsv
for l in open('tmp/b0_hand.tsv'):
    if l.startswith('#') or not l.strip(): continue
    p=l.rstrip('\n').split('\t')
    rows.append(tuple(p))
hand_names={r[1] for r in rows}
hand_addr={r[0].lower() for r in rows}
used=set(exist_name)|hand_names
hand_by_addr={r[0].lower():r[1] for r in rows if r[0].startswith('CODE:')}
bn=dict(bank_names); bn[0]={int(a[5:],16):n for a,n in hand_by_addr.items()}
for a in sorted(th):
    bank,imm,typ=th[a]
    key=f'CODE:{int(a,16):04x}'
    if key in exist_addr or key in hand_addr: continue
    tn=bn.get(bank,{}).get(imm)
    if bank==0 and tn is None: tn=None
    base=f'bcall_{tn}' if tn else f'bcall_b{bank}_{imm:04x}'
    name=base
    if name in used: name=f'{base}_{int(a,16):04x}'
    used.add(name)
    c=f'Banked-call trampoline: DPTR=0x{imm:04X} + LJMP bank{bank} dispatcher (0x04xx); target in bank {bank}' + (' (named in that bank)' if tn else '')+ ('' if typ=='func' else '; not a Ghidra function in the export (bytes read from flash image)')
    rows.append((key,name,typ,c,'high'))
out=[]
for r in rows:
    out.append('\t'.join([r[0],r[1],r[2],r[3],'[re-agent]',r[4]]))
open('tmp/b0_rows.tsv','w').write('\n'.join(out)+'\n')
from collections import Counter
print(len(out),Counter(r[4] for r in rows))
# dup checks
names=[r[1] for r in rows]; addrs=[r[0] for r in rows]
print('dup names',[n for n,c in Counter(names).items() if c>1]); print('dup addr',[n for n,c in Counter(addrs).items() if c>1])
print('clash existing', [n for n in names if n in exist_name], [a for a in addrs if a in exist_addr])
