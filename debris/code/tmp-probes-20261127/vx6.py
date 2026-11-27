import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V, fw_sim as S
class StateLog(S.Dev):
    def __init__(self,a): self.writes=(a,); self.rows=[]
    def on_write(self,m,a):
        import re
        mt=re.search(r"Stop at 0x([0-9a-f]+)", m.last_out)
        self.rows.append((m.instr,m.rd(0xFFFF)[0]&15,int(mt.group(1),16) if mt else -1,m.rd(a)[0]))
sl=StateLog(0xe22e)
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60',None,[sl])
for i in range(60): m.run(1_000_000)
prev=None
for i,b,pc,v in sl.rows:
    if prev is None or (v&0x1f)!=(prev&0x1f) or i>44_000_000:
        print(i,b,hex(pc),m.where(b,pc),hex(v))
    prev=v
