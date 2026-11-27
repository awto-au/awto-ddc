import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V, fw_sim as S, fw_regs
PAGES=(0x00,0x01,0x05,0x45,0x20,0x30,0x31,0x37,0x40)
devs_extra=[]
m0,h=None,None
img=V.VENDOR_IMG.read_bytes()
devs,hdmi=S.video_devs(img,'2160p60')
taken={ad for d in devs for ad in (*d.reads,*d.writes)}
ranges={pg<<8|i for pg in PAGES for i in range(256)}-taken
wl=S.WriteLog(ranges)
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60',None,[wl])
names=fw_regs.names()
last=None
for i in range(50):
    m.run(1_000_000)
rows=[r for r in wl.rows if r[0]>45_000_000]
print(len(wl.rows),len(rows))
for i,b,pc,a,v in rows:
    if "osd" in m.where(b,pc).lower() or 0x90<=a<=0x94 and a<0x100: continue
    print(i,b,m.where(b,pc),hex(a),names.get(a,'?'),hex(v))
