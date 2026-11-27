import re,sys
def load(p):
    out=[]
    for l in open(p):
        m=re.match(r"\+\s*(\d+) ms (.*)",l.strip())
        if m: out.append((int(m.group(1)),m.group(2)))
    return out
PH=[("POWER off: key -> power off line", r"power off requested by|^panel off requested$", r"^power off$"),
    ("POWER on: key -> mode ACTIVE", r"^power key on", r"^mode ACTIVE"),
    ("POWER off in DS: key -> power off line", r"power off requested by|^panel off requested$", r"^power off$"),
    ("POWER on: key -> mode ACTIVE", r"^power key on", r"^mode ACTIVE"),
    ("switch D3: cmd -> mode NO SIGNAL", r"^switch to D3", r"^mode NO SIGNAL"),
    ("switch D2: cmd -> mode ACTIVE", r"^switch to D2", r"^mode ACTIVE"),
    ("signal lost: judge -> hold L1", r"^judge: source unstable", r"^hold L1"),
    ("signal back -> fast path taken", r"^hold: signal back", r"^fast path taken|FAST SWITCH -> ACTIVE"),
    ("VCP D6=4: -> power saving line", r"power saving requested by DDC|^panel off requested$", r"^power saving$"),
    ("SOURCE wake: -> mode ACTIVE", r"^wake on", r"^mode ACTIVE")]
def phases(ls, skip_boot=True):
    i=next(k for k,(t,x) in enumerate(ls) if re.search(r"^mode ACTIVE",x))+1
    res=[]
    for name,a,b in PH:
        ia=next((k for k in range(i,len(ls)) if re.search(a,ls[k][1])),None)
        if ia is None: res.append((name,None)); continue
        ib=next((k for k in range(ia,len(ls)) if re.search(b,ls[k][1])),None)
        if ib is None: res.append((name,None)); continue
        res.append((name,(ls[ib][0]-ls[ia][0])&0xFFFF)); i=ib+1
    return res
A=phases(load(sys.argv[1])); B=phases(load(sys.argv[2]))
for (n,a),(_,b) in zip(A,B): print(f"| {n} | {a} | {b} |")
