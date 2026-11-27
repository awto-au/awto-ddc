import sys
sys.path.insert(0,'scripts')
import trace_diff as T
f={'V':'tmp/logs/trace_vendor_2160p60.tsv','O':'tmp/logs/trace_AWT26110003-wb-frc2-be_2160p60.tsv'}[sys.argv[1]]
rows,ds,end=T.load(f); t0=float(rows[ds][2])
a=float(sys.argv[2]); b=float(sys.argv[3])
for r in rows[ds:end+1]:
    t=float(r[2])-t0
    if a<=t<=b and (r[6]=='CALL' or int(r[7],16) in (2,3,5,0xc,0xd,0x28,0x2f,0x10,0x1a,0x3040,0x31c0,0x31c1,0x31c3) or 'WATCH' in r[8]):
        print(f"{t:7.1f} {r[6][0]} {r[7]} {r[8][:30]:30} {r[9]:>2} {r[10]:>2} {r[5][:40]}")
