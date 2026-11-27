import sys,re; sys.path.insert(0,'scripts')
import fw_sim_vendor as V, fw_sim as S
class StateLog(S.Dev):
    def __init__(self,a): self.writes=(a,); self.rows=[]
    def on_write(self,m,a):
        v=m.rd(a)[0]
        if (v&0x1f)==1 and self.rows and (self.rows[-1][3]&0x1f)==2 or len(self.rows)<1:
            sp=m.rd(0x81,1,'sfr')[0]
            st=m.rd(0x00,256,'iram') if False else m.cmd("dump iram 0x80 0xff")
            self.stack=(sp,st)
        mt=re.search(r"Stop at 0x([0-9a-f]+)", m.last_out)
        self.rows.append((m.instr,m.rd(0xFFFF)[0]&15,int(mt.group(1),16) if mt else -1,v))
sl=StateLog(0xe22e)
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60',None,[sl])
for i in range(47): m.run(1_000_000)
sp,st=sl.stack
print(hex(sp)); print(st[-1500:])
