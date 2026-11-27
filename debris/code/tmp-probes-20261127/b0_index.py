import re,collections,json
B='/home/dan/vendors/realtek/analysis/jxc-4k/bank0/'
t=open(B+'decompiled_named.c').read()
parts=re.split(r'\n(?=/\* @ 0x)|\n(?=\n\n\n\n(?:[a-z]))',t)
# robust: split by function definitions via disasm instead
asm=open(B+'disassembly.asm').read()
blocks=re.split(r'\n(?=; ==== )',asm)
funcs={}
for b in blocks:
    m=re.match(r'; ==== (\S+) @ CODE:([0-9a-f]+)',b)
    if not m: continue
    n,a=m.group(1),m.group(2)
    lines=[l for l in b.split('\n') if l.startswith('CODE:')]
    calls=[]
    for l in lines:
        mm=re.search(r'(LCALL|ACALL|LJMP|AJMP) 0x([0-9a-f]+)',l)
        if mm: calls.append((mm.group(1),mm.group(2).zfill(4)))
    funcs[a]=dict(name=n,n=len(lines),calls=calls,last=lines[-1] if lines else '')
json.dump(funcs,open('tmp/b0_funcs.json','w'))
callers=collections.defaultdict(set)
for a,f in funcs.items():
    for k,c in f['calls']: callers[c].add(a)
json.dump({k:sorted(v) for k,v in callers.items()},open('tmp/b0_callers.json','w'))
print(len(funcs))
