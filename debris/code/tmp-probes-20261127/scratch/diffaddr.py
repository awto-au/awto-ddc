import gzip,glob,os,re,collections
def load(f):
    d={}
    for i,l in enumerate(gzip.open(f,'rt')):
        c=l.rstrip('\n').split('\t')
        if i==0 or len(c)<17 or c[4]!='REG':continue
        d.setdefault(int(c[1],16),set()).add(c[5])
    return d
ours=load('re/regdb/RTD2795T-CG.tsv.gz')
for f in sorted(glob.glob('re/regdb/*.gz')):
    n=os.path.basename(f)[:-7]
    if n.startswith('RTD2795'):continue
    o=load(f)
    miss=sorted(set(o)-set(ours))
    # group to ranges
    pg=collections.Counter(a>>8 for a in miss)
    print('==',n,'missing-in-ours',len(miss),'pages:',' '.join('%02X:%d'%(p,c) for p,c in sorted(pg.items())))
    for a in miss:
        nm=','.join(sorted(o[a]))
        if re.search(r'TSEN|THERM|TEMP|ADC|OSC|DFT|TEST|MON|SENS|RING|PTAT|CAL',nm,re.I): print('   %04X %s'%(a,nm))
