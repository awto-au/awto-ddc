import re,glob,sys,collections
CALL=re.compile(r"^\s+(?:lcall|ljmp|acall|ajmp)\s+(\w+)\s*$")
FN=re.compile(r"^(_\w+):{1,2}\s*$")
calls=collections.defaultdict(set); cur=None
for f in glob.glob(sys.argv[1]+'/*.asm'):
    for l in open(f,errors='replace'):
        m=FN.match(l)
        if m and not m.group(1).startswith(('_s_','__str')): cur=m.group(1)
        m=CALL.match(l)
        if m and cur: calls[cur].add(m.group(1))
# path from A back to A
import itertools
def path(a,b):
    prev={a:None}; q=collections.deque([a])
    while q:
        x=q.popleft()
        for y in calls.get(x,()):
            if y not in prev:
                prev[y]=x; q.append(y)
                if y==b:
                    p=[y]
                    while prev[p[-1]] is not None: p.append(prev[p[-1]])
                    return p[::-1]
for start in sys.argv[2:]:
    for c in calls[start]:
        p=path(c,start)
        if p: print(start,'->',' -> '.join([c]+p[1:])); break
