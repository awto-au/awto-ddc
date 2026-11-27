import pickle,sys,re
info,callers=pickle.load(open('tmp/b3/idx.pkl','rb'))
lo=int(sys.argv[1],16);hi=int(sys.argv[2],16)
for a in sorted(info):
    if lo<=a<hi:
        n,l,cs,regs,b=info[a]
        b=re.sub(r'\n\s*(?:byte|undefined\d*|short|ushort|uint|int|char|ulong|undefined|bool|byte \*|undefined1 \*)\s+\**[\w, \*]+;','',b)
        b=re.sub(r'/\* WARNING[^\n]*\*/\n','',b)
        b=re.sub(r'\n\s*\n+','\n',b)
        print('=== %04x cl=%s'%(a,','.join('%x'%x for x in sorted(callers[a]))[:60]))
        print(b.strip())
