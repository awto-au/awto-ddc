import re,sys,collections
p='/home/dan/vendors/realtek/analysis/jxc-4k/bank3/decompiled_named.c'
txt=open(p).read()
parts=re.split(r'/\* @ 0x([0-9a-f]+)(?: \*/| -- [^\n]*)',txt)
funcs={}
for i in range(1,len(parts),2):
    a=int(parts[i],16); body=parts[i+1]
    funcs[a]=body
calls=collections.defaultdict(set)
callers=collections.defaultdict(set)
info={}
for a,b in funcs.items():
    m=re.search(r'\n([^\n(]*?)\b(\w+)\(([^)]*)\)\s*\n\s*\{',b)
    name=m.group(2) if m else '?'
    cs=set(int(x,16) for x in re.findall(r'(?:FUN_CODE_|thunk_FUN_CODE_)([0-9a-f]{4})\b',b))
    regs=set(re.findall(r'\b([A-Z][A-Z0-9_]+_at[0-9a-f]{4}|[A-Z][A-Z0-9_]{4,})\b',b))
    info[a]=(name,len(b.splitlines()),cs,regs,b)
    for c in cs: callers[c].add(a)
import pickle
pickle.dump((info,callers),open('/mnt/2tb/git/awto-ddc/tmp/b3/idx.pkl','wb'))
print(len(info))
