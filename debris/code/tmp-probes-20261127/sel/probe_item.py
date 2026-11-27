import sys
sys.path.insert(0, "/mnt/2tb/git/awto-ddc-seltools/scripts")
from pathlib import Path
import osd_render as R, key_sim_test as K
b = Path("/mnt/2tb/git/awto-ddc/tmp/fw/AWT26110002-wb-p14ui-sel1-be.bin")
s = R.Session(b, b.with_suffix(".map"), "1080p60"); s.boot(); k = K.Keys(s)
k.wait(1000)
ud = k.m.addr("g_stOSDUserData")
k.tap("SOURCE"); print("open", k.m.rd(ud, 24).hex())
for _ in range(4):
    k.tap("SOURCE", ms=100, gap=150); print(k.args["AwtoSrcSet"][-1], k.m.rd(ud, 24).hex())
