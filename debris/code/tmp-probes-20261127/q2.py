import sys
sys.path.insert(0,'scripts')
import trace_diff as T
f={'V':'tmp/logs/trace_vendor_2160p60.tsv','O':'tmp/logs/trace_AWT26110003-wb-4kmeas-be_2160p60.tsv'}[sys.argv[1]]
a,b=float(sys.argv[2]),float(sys.argv[3])
rows,ds,end=T.load(f); t0=float(rows[ds][2])
for r in rows[ds:end+1]:
    t=float(r[2])-t0
    if a<=t<=b and r[6]!='STATE' and int(r[7],16) not in T.NOISE and r[8]!='MemoryCheck' and 'MemoryCheck' not in r[8]:
        print(f"{t:7.1f} {r[6][0]} {r[7]} {r[8][:30]:30} {r[9]:>2} {r[10]:>2} {r[5][:36]}")
