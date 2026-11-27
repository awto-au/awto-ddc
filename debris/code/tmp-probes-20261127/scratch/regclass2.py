import pickle, collections, sys
sys.argv=['x']
exec(open('/mnt/2tb/git/awto-ddc/tmp/scratch/regclass.py').read().split("dumps = []")[0])
P = pickle.load(open(OUT+'regclass.pkl','rb')); rows=P['rows']; dumps=P['dumps']
for i,d in enumerate(dumps): print(i,d['unit'][-1],d['label'],d['ts'].strftime('%m%d-%H%M%S'))
# sessions: consecutive same-unit dumps with gaps<=5min
order=sorted(range(len(dumps)),key=lambda i:(dumps[i]['unit'],dumps[i]['ts']))
sess=[];cur=[]
for i in order:
    if cur and dumps[i]['unit']==dumps[cur[-1]]['unit'] and (dumps[i]['ts']-dumps[cur[-1]]['ts']).total_seconds()<=420 and dumps[i]['label']==dumps[cur[-1]]['label']: cur.append(i)
    else:
        if len(cur)>1: sess.append(cur)
        cur=[i]
if len(cur)>1: sess.append(cur)
print('sessions',[[dumps[i]['ts'].strftime('%m%d-%H%M') for i in s] for s in sess])
out=open(OUT+'regclass_b2_changing_within_session.tsv','w')
out.write('page_addr\tregdb\treg\tsdk\tport_or_risky\tn_sessions_changing\tvalues_by_session\n')
cnt=collections.Counter()
res=[]
for r in rows:
    vd=dict(r['vals']); ch=[]
    for s in sess:
        v=[vd[i] for i in s if i in vd]
        if len(set(v))>1: ch.append(' '.join(f'{x:02X}' for x in v))
    if ch:
        res.append((r,ch)); cnt[(r['st'],r['isport'])]+=1
        out.write('\t'.join([r['addr'],r['st'],r['reg'],r['sdk'],str(int(r['isport'])),str(len(ch)),' / '.join(ch)])+'\n')
print(cnt, len(sess))
pg=collections.Counter(r['page'] for r,ch in res if not r['isport'])
print({f'{k:02X}':v for k,v in sorted(pg.items())})
