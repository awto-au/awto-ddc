import re,json,os,sys
B='/home/dan/vendors/realtek/analysis/jxc-4k/bank0/'
asm=open(B+'disassembly.asm').read()
dump=open(os.path.expanduser('~/vendors/realtek/analysis/dumps/jxc-4k-flash-a.bin'),'rb').read()
bk={0x29:0,0x3b:1,0x4d:2,0x5f:3,0x71:4,0x83:5,0x95:6}
blocks=re.split(r'\n(?=; ==== )',asm)
th={}
for b in blocks:
    m=re.match(r'; ==== (\S+) @ CODE:([0-9a-f]+)',b)
    if not m: continue
    a=int(m.group(2),16)
    ins=[l for l in b.split('\n') if l.startswith('CODE:')]
    if len(ins)==2 and 'MOV DPTR,#' in ins[0] and 'LJMP 0x04' in ins[1]:
        imm=int(re.search(r'#0x([0-9a-f]+)',ins[0]).group(1),16)
        d=int(re.search(r'LJMP 0x([0-9a-f]+)',ins[1]).group(1),16)
        if d>>8==4 and (d&0xff) in bk: th[a]=(bk[d&0xff],imm,'func')
# missing: raw
f=json.load(open('tmp/b0_funcs.json')); c=json.load(open('tmp/b0_callers.json'))
for k in c:
    a=int(k,16)
    if k in f or a>=0x28c6: continue
    bb=dump[a:a+6]
    if len(bb)==6 and bb[0]==0x90 and bb[3]==0x02 and bb[4]==0x04 and bb[5] in bk:
        th[a]=(bk[bb[5]],(bb[1]<<8)|bb[2],'label')
json.dump({f'{a:04x}':v for a,v in th.items()},open('tmp/b0_thunks.json','w'))
print(len(th),sum(1 for v in th.values() if v[2]=='label'))
