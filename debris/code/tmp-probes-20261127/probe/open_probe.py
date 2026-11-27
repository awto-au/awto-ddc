import sys
sys.argv=["x"]
sys.path.insert(0,"/mnt/2tb/git/awto-ddc-keys/scripts")
import keys_sim as K
R=K.R
b,m=sys.argv_bin if hasattr(sys,"argv_bin") else (None,None)
import os
bin_=os.environ["BIN"]; map_=bin_[:-4]+".map"
from pathlib import Path
s=R.Session(Path(bin_),Path(map_),"2160p60")
s.boot()
k=K.Keys(s)
k.put(*K.IDLE)
k.until("KEY",lambda st: st["a0"]==0xF8 and st["mask"]==0,3000)
st=k.state(False); print("start", st, flush=True)
# force a non-ACTIVE mode state value
mode=int(os.environ.get("MODE","3"))
s.bus.m.wr(k.mode_a, bytes([mode]))
k.cmd(0x41)
st,el=k.until("DRAW",lambda st: st["open"]==1 and st["drawn"]==1,K.CMD_MS+K.DRAW_MS)
print("mode",mode,"after first 0x41:",{x:y for x,y in k.state(False).items()}, el, flush=True)
s.bus.m.wr(k.mode_a, bytes([3]))
k.cmd(0x41)
k.dwell(1000)
print("after second 0x41 (mode 3):",k.state(False), flush=True)
