import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60')
calls=[]
names=['SysSourceJudge','SysPowerHandler','SysSourceHandler','SysSourceDetectPort','SysSourceSwitchPort','SysSourceSearchTimeInitial','SysSourceScanPortInitial','SysSourceCableDetection']
for n in names:
    m.stub(n, lambda m_,r,n=n: calls.append((m_.instr,n)))
for i in range(80):
    m.run(1_000_000)
from collections import Counter
c=Counter(n for _,n in calls); print(c)
seen=set()
for i,n in calls:
    if n not in seen: seen.add(n); print(i,n)
