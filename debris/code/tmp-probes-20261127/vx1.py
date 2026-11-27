import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V, fw_sim as S
from pathlib import Path
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60')
V.stub_at(m,5,0xf97b,'ScanInputPortX',lambda m,r: print('SCAN',m.instr,r['r']) )
V.stub_at(m,5,0x7a31,'ScanHdmi5',lambda m,r: print('SCAN5',m.instr))
V.stub_at(m,5,0xfce9,'PreD2',lambda m,r: print('PRE2',m.instr,r['r'][7]))
for i in range(60):
    m.run(1_000_000)
print(m.stub_hits)
h=V.pc_hist(m,200)
for k,v in h.most_common(10): print(v,k)
