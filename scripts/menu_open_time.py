#!/usr/bin/env python3
"""Sim time of the awto menu open and of its font load (before / after the #87 text layer): host tool, fw_sim, no video.

usage: menu_open_time.py BIN MAP
  menu open = mailbox `open main` command to answer. font load = entry of osd_font_load to the next step (osd_tc_bar in the 24x36
  layer, osd_tc_place in the 12x18 menu). Sim ms of the T2 tick. Log: tmp/logs/menu_open_time.log
"""
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim  # noqa: E402
import menu_cli as MC  # noqa: E402
import settings_cli as C  # noqa: E402

LOG = Path(__file__).resolve().parents[1] / "tmp/logs/menu_open_time.log"


def main():
    b, mp = Path(sys.argv[1]), Path(sys.argv[2])
    bus = fw_sim.SimBus(b, mp)
    mt = mp.read_text(errors="replace")
    m = MC.Menu(C.Box(bus, mt, True), mt, True)
    hits = {}

    def w(name):
        def f(m_, r):
            hits.setdefault(name, bus.now())
            return None
        try:
            bus.m.stub(name, f)
        except Exception:
            pass
    for n in ("osd_font_load", "osd_tc_bar", "osd_tc_place", "osd_tc_show"):
        w(n)
    t0 = bus.now()
    m.cmd("open", MC.page_of("main"))
    t1 = bus.now()
    nxt = hits.get("osd_tc_bar", hits.get("osd_tc_place"))
    line = f"{b.name}: menu open {(t1 - t0) * 1000:.0f} ms, font load {(nxt - hits['osd_font_load']) * 1000:.0f} ms (osd_font_load {hits['osd_font_load']:.3f} s, next step {nxt:.3f} s)"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + line + "\n")
    print(line)
    bus.close()


if __name__ == "__main__":
    main()
