import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60')
V.stub_at(m,5,0xf97b,'ScanX',lambda m,r: print('SCAN',m.instr,r['r']))
last=None
for i in range(60):
    m.run(1_000_000)
    v=(m.rd(0xe22e,1).hex(), m.rd(0xe23a,1).hex())
    if v!=last: print(i,'e22e/e23a',v); last=v
print(m.stub_hits)
h=V.pc_hist(m,200)
for k,v in h.most_common(10): print(v,k)
