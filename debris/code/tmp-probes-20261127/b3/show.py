import pickle,sys,re
info,callers=pickle.load(open('tmp/b3/idx.pkl','rb'))
for s in sys.argv[1:]:
    a=int(s,16)
    n,l,cs,regs,b=info[a]
    b=re.sub(r'\n\s*(byte|undefined\d*|short|ushort|uint|int|char|ulong|undefined)\s+[^\n]*;','',b)
    b=re.sub(r'\n\n+','\n',b)
    print('=== %04x callers=%s'%(a,[hex(x) for x in sorted(callers[a])]))
    print(b.strip())
