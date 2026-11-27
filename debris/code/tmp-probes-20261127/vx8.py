import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60')
old=m.stubs[0xf85f][0]
def f(m_,r):
    if m_.instr<60_000_000: print('STABLE',m_.instr,r['r'])
    return old[2](m_,r)
m.stubs[0xf85f][0]=(old[0],old[1],f)
for i in range(47): m.run(1_000_000)
