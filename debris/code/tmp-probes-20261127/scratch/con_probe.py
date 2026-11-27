import sys
sys.path.insert(0, "scripts")
import osd_render as R
s = R.Session(__import__("pathlib").Path(sys.argv[1]), __import__("pathlib").Path(sys.argv[2]), "1080p60")
s.boot(sync_console=True)
g = s.bus.addr("g_stAwtoGpio") + 3
t0 = s.bus.now()
last = None
for i in range(60):
    v = s.bus.m.rd(g)[0]
    if v != last:
        print(f"{(s.bus.now() - t0) * 1000:6.0f} ms after ACTIVE: console flag {v}")
        last = v
    s.bus.wait(0.1)
