import sys
sys.argv=['x']
exec(open('/mnt/2tb/git/awto-ddc/tmp/vlcdec.py').read().split("for off in (0x228C6")[0])
L,end,nibs=dec(0x23B41)
by=[(nibs[i]<<4)|nibs[i+1] for i in range(0,len(nibs)-1,2)]
bits=[]
for i in range(0,len(by)-2,3):
    for b in (by[i+2],by[i+1],by[i]): bits+=[(b>>k)&1 for k in range(7,-1,-1)]
G=len(bits)//216
def cell(n): return [bits[n*216+r*12:n*216+r*12+12] for r in range(18)]
C=[cell(n) for n in range(G)]
def hmis(a,b): return sum(a[r][11]!=b[r][0] for r in range(18))
def vmis(a,b): return sum(a[17][c]!=b[0][c] for c in range(12))
best=[]
for cols in range(8,40):
    for g0 in range(0,G-cols*3):
        n=(G-g0)//cols
        if n<4: continue
        s=0;c=0
        for k in range(min(n*cols,400)):
            i=g0+k
            if k%cols<cols-1 and i+1<G: s+=hmis(C[i],C[i+1]);c+=18
            if i+cols<G: s+=vmis(C[i],C[i+cols]);c+=12
        best.append((s/c,cols,g0))
best.sort();print(best[:8])
