import pickle,sys
info,callers=pickle.load(open('tmp/b3/idx.pkl','rb'))
lo=int(sys.argv[1],16);hi=int(sys.argv[2],16)
for a in sorted(info):
    if lo<=a<hi:
        n,l,cs,regs,b=info[a]
        r=[x for x in regs if x not in('DAT_EXTMEM','FUN_CODE') and not x.startswith(('DAT_','FUN_','UNK','PTR_','BYTE','LAB_'))]
        print('%04x %-18s L%-3d cl%-2d co%-2d %s'%(a,n[:18],l,len(callers[a]),len(cs),','.join(sorted(r))[:90]))
