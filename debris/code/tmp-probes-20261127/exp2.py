import sys,time,os
sys.path.insert(0,'scripts')
from pathlib import Path
import fw_profile as P, fw_sim as F
b=Path('tmp/fw/AWT26110003-wb-dbg1-be.bin'); m=Path('tmp/fw/AWT26110003-wb-dbg1-be.map')
s,sym,where=P.boot(b.read_bytes(),m,True,open('/dev/null','w'))
print("booted")
s.send('delete'); s.send('break xram w 0xf6e5'); s.send('info breakpoints')
time.sleep(0.5)
print(os.read(s.p.stdout.fileno(),65536).decode()[-800:])
for i in range(3):
    s.send('step 1'); time.sleep(0.3)
    print(os.read(s.p.stdout.fileno(),65536).decode()[-300:])
