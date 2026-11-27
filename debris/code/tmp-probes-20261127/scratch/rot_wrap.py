"""Scratch: con_wrap_sim at Rotate 180 (disp_rotate via the MCCS paged pair), demo log, raw map rows un-mirrored."""
import sys
sys.path.insert(0, "/mnt/2tb/git/awto-ddc/scripts")
from pathlib import Path
import con_wrap_sim as C
import settings_table as T

b = Path(sys.argv[1])
s = C.Sim(b, b.with_suffix(".map"))
s.bus.run_until_mode(C.MODE_ACTIVE, 160_000_000)
rid = T.BY_NAME["disp_rotate"]["id"]
s.mccs.set(0xE0, rid)
s.mccs.set(0xE1, 1)
s.bus.wait(2.0)
s.cmd(0x26)
s.bus.wait(1.0)
s.cmd(0x3A)
s.bus.wait(3.0)
st = C.M.snapshot if False else None
rows = s.text()
W = max(len(r) for r in rows)
for i, r in enumerate(rows):
    v = r.ljust(W)                           # osd_model layout is already in viewer order
    st = len(v) - len(v.lstrip())
    print(f"{i:3d} start {st:3d} len {len(v.rstrip()):3d} {v.strip()[:40]!r}")
