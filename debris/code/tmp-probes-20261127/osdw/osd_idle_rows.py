#!/usr/bin/env python3
"""Scratch: OSD data writes per map row in 1 s idle with the console open (host_time_sim boot)."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, "/mnt/2tb/git/awto-ddc/scripts")
import host_time_sim as H  # noqa: E402
import osd_model as M  # noqa: E402

b = Path(sys.argv[1])
s = H.Sim(b, b.with_suffix(".map"))
s.boot()
t_end = s.bus.now() + H.CON_S
while "AWTO DIAGNOSTICS" not in s.title() and s.bus.now() < t_end:
    s.bus.wait(0.25)
s.bus.wait(1.5)
st = s.model.snapshot(s.m, 0)
fs = M.frame_geometry(st)["fs_base"]
s.model.trace, s.model.trace_on = [], True
s.bus.wait(1.0)
s.model.trace_on = False
rows = collections.Counter()
kinds = collections.Counter()
for w, ad, _ in s.model.trace:
    k = (w >> 2) & 3
    kinds[k] += 1
    if k == M.SRAM_FONT and fs <= ad < fs + 120 * 63:
        rows[(ad - fs) // 120] += 1
print("total", len(s.model.trace), "by sram kind", dict(kinds))
print("font-select writes per map row:", dict(sorted(rows.items())))
for r in s.text():
    print("|" + r.rstrip())
