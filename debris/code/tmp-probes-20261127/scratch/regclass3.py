import pickle,collections,re,gzip,csv
R='/mnt/2tb/git/awto-ddc/'
P=pickle.load(open(R+'tmp/scratch/regclass.pkl','rb')); rows=P['rows']; dumps=P['dumps']
named=collections.defaultdict(int)
for r in csv.DictReader(gzip.open(R+'re/regdb/RTD2795T-CG.tsv.gz','rt'),delimiter='\t'):
    if r['kind']=='FIELD' and r['field'].strip() and not re.match(r'^(reserved|dummy|rsvd|res|resv|reserve|unused)\w*$',r['field'].strip(),re.I):
        hi,lo=int(r['bit_high']),int(r['bit_low']); named[int(r['address'],0)]|=((1<<(hi-lo+1))-1)<<lo
sess_pairs=None
out=open(R+'tmp/scratch/regclass_c2_doc_unnamed_bits_nonzero.tsv','w')
out.write('page_addr\treg\tnamed_mask\tunnamed_bits_seen\tdistinct_values\tvaries_same_state\n')
n=0;nc=0;tot=0
for r in rows:
    if r['st']!='doc' or r['isport'] or (r['a']&0xFF)==0x9F: continue
    m=named[r['a']]; un=(~m)&0xFF
    if not un: continue
    tot+=1
    seen=0
    for v in r['uniq']: seen|=v&un
    if seen:
        n+=1
        out.write('\t'.join([r['addr'],r['reg'],f'{m:02X}',f'{seen:02X}',' '.join(f'{v:02X}' for v in r['uniq']),str(int(r['sg']))])+'\n')
print('docs regs with unnamed bits',tot,'with nonzero unnamed bits',n)
# cross-only undocumented
for r in rows:
    if r['st']!='doc' and r['vary'] and not r['sg'] and not r['isport'] and (r['a']&0xFF)!=0x9F: print(r['addr'],r['st'],r['reg'],' '.join(f'{v:02X}' for v in r['uniq']))
# excl 9F column stats
nz9=[r for r in rows if (r['a']&0xFF)!=0x9F]
print('regs excl 9F',len(nz9),'allzero',sum(r['uniq']==[0] for r in nz9),'allFF',sum(r['uniq']==[255] for r in nz9),'mix',sum(set(r['uniq'])<={0,255} and len(r['uniq'])==2 for r in nz9))
print('undoc nz excl9F',sum(1 for r in nz9 if r['st']!='doc' and r['nz']),'undoc chg excl9F',sum(1 for r in nz9 if r['st']!='doc' and r['sg'] and not r['isport']))
# constant & all nonzero undoc: count constants
und=[r for r in nz9 if r['st']!='doc' and r['nz']]
print('undoc nz constant across all dumps',sum(len(r['uniq'])==1 for r in und),'varying',sum(len(r['uniq'])>1 for r in und))
# unique modulo mirrors: undoc nz excluding pages that mirror
mir={0x67,0x68,0xC8,0xCA,0xCE,0xCF,0x9E,0xA8,0xAF,0xAB,0x77}
print('undoc nz excl mirror pages',sum(1 for r in und if r['page'] not in mir))
# ports data/index bytes present in pages and nonzero
print('port/risky addr in page dumps',sum(r['isport'] for r in rows), 'those changing',sum(r['isport'] and not r['vary']==False for r in rows))
# doc regs: constant across all dumps and nonzero != reset
dd=[r for r in rows if r['st']=='doc' and not r['isport'] and (r['a']&0xFF)!=0x9F]
print('doc regs',len(dd),'varying any',sum(r['vary'] for r in dd),'varying same group',sum(r['sg'] for r in dd))
