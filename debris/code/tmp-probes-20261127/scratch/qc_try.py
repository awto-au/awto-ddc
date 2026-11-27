import sys,os
os.environ["AWTO_SIM_CORE"]="fast"
sys.path.insert(0,"scripts")
from pathlib import Path
import osd_render as R, card_shot as C, numpy as np
from PIL import Image
q=Path("tmp/scratch/qcsim/tmp/fw/AWT26110003-qcsim4-be")
s=R.Session(Path(str(q)+".bin"),Path(str(q)+".map"),"1080p60")
s.boot()
C.send(s,0xB2+int(sys.argv[1]))
s.bus.wait(3.0)
st=s.snap()
out=Path(f"tmp/scratch/qcf_{sys.argv[1]}.png")
c=C.shot(st,out,f"qc{sys.argv[1]}")
print(c)
print("font words",len(st.font),"win",len(st.win),"reg3A02",hex(st.reg(0x3A02)),"ovl",st.ovl)
import osd_test as T
print("testcmd byte now", s.bus.m.rd(s.diag+T.TESTCMD_OFF,1))
import osd_model as M
print(M.summary(st))
g=M.frame_geometry(st); print(g)
rows=M.layout_rows(st,g); print("rows",len(rows),[ (r["h"],r["n"]) for r in rows[:6]])
r=st.regs
print("3A00..05",r[0:6].hex(),"3A06",hex(r[6]),"3A0A",hex(r[0x0A]),"3A0B",hex(r[0x0B]),"0C..0E",r[0x0C:0x0F].hex(),"17",hex(r[0x17]),"18",hex(r[0x18]),"19..1D",r[0x19:0x1E].hex(),"21..23",r[0x21:0x24].hex(),"24..29",r[0x24:0x2A].hex())
rows=M.layout_rows(st,g)
for ri in (0,1,5,7):
    print(ri,[(c["kind"],c["id"],c["width"],c["fg"],c["bg"]) for c in rows[ri]["chars"][:8]])
raw=[st.font[23+k] for k in range(8)]; print("raw cells row0", raw)
print("glyph0 words",[st.font.get(856+k) for k in range(9)])
print("glyph1 words",[st.font.get(856+9+k) for k in range(9)])
g=M.frame_geometry(st); print({k:g[k] for k in ("two","row_base1","fs_base1","hd2","vd2","fhb","fvb")})
rb=M.layout_rows(st,g,g["row_base1"],g["fs_base1"]); print("B rows",len(rb),[(r["h"],r["n"]) for r in rb[:8]])
print("row cmd B", [st.font.get(15+k) for k in range(8)])
print("cells B first", [st.font.get(471+k) for k in range(4)])
img=np.array(R.render_snap(st,"grey",1,False)); bgc=R.background("grey",R.PANEL_W,R.PANEL_H)
m=np.any(img!=bgc,axis=2); print("panel",img.shape,"nonbg rows range",np.nonzero(m.any(axis=1))[0][[0,-1]],"B region count",m[505:640].sum())
lv=M.glyph_levels4(st,g,38); print("luffy id38 levels used",np.unique(lv))
