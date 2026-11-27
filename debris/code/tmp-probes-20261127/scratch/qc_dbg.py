import sys,os
os.environ["AWTO_SIM_CORE"]="fast"
sys.path.insert(0,"scripts")
from pathlib import Path
import osd_render as R, card_shot as C, osd_model as M, numpy as np
q=Path("tmp/scratch/qcsim/tmp/fw/AWT26110003-qcsim4-be")
s=R.Session(Path(str(q)+".bin"),Path(str(q)+".map"),"1080p60"); s.boot()
for n in [int(x) for x in sys.argv[1:]]:
    C.send(s,0xB2+n); s.bus.wait(4.0); st=s.snap(); g=M.frame_geometry(st)
    r=st.regs
    print("frame",n,"3A02",hex(r[2]),"3A0A",hex(r[0x0A]),"3A0B",hex(r[0x0B]),"3A17",hex(r[0x17]),"3A18",hex(r[0x18]),"6C/8F",st.ovl,"rows A",len(M.layout_rows(st,g)),"rows B",len(M.layout_rows(st,g,g["row_base1"],g["fs_base1"])), "nwin",M.summary(st)["nwin"], "dbl", r[0x0A]&3, "su", hex(r[0xC0]))
