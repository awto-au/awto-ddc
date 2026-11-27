import sys,time
sys.path.insert(0,'scripts')
from pathlib import Path
import fw_sim as F
b=Path('tmp/fw/AWT26110003-wb-dbg1-be.bin'); m=Path('tmp/fw/AWT26110003-wb-dbg1-be.map')
img=b.read_bytes()
fl=F.FlashPort(img)
s=F.open_native(img,F.ROOT/'tmp/fwsim'/b.stem,open('/dev/null','w'),fl,[])
out=F.run_chunk(s,fl,3000000); print(repr(out[-600:]))
t=time.time()
for i in range(200):
    out=F.run_chunk(s,fl,50)
print(time.time()-t); print(out)
s.send('timer list'); print(s.read_until(rb'\n',2))
