#!/usr/bin/env python3
"""One render of the awto menu in fw_sim: open PAGE (and optionally move the cursor / edit), save a PNG.

usage: menu_shot.py BIN MAP PAGE|all [--hl 0|1] [--keys right,right,menu] [--out OUT.png|DIR] [--mode 1080p60|2160p60]
  --hl: ui_hl_style (0 = blue bar behind white text, 1 = blue '>' marker + underline; #87), written before the menu opens
  --keys: menu keys sent after opening (menu_cli names: menu right left exit)
  PAGE=all: render every page after one simulator boot; --out is a directory containing walk_<page>.png files
Log: tmp/logs/menu_shot.log
"""
import argparse
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu_cli as MC  # noqa: E402
import osd_render as R  # noqa: E402
import settings_cli as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/menu_shot.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def shot(s, out, bg="grey", scale=2):
    R.save(s.snap(), out, bg, scale)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("page")
    ap.add_argument("--hl", type=int, default=None)
    ap.add_argument("--keys", default="")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, a.mode)
    s.boot()
    mt = a.map.read_text(errors="replace")
    if a.hl is not None:
        s.bus.m.wr(s.bus.addr("ui_hl_style"), bytes([a.hl]))
    m = MC.Menu(C.Box(s.bus, mt, True), mt, True)
    if a.page == "all":
        out = a.out or ROOT / "tmp/menu_pages"
        out.mkdir(parents=True, exist_ok=True)
        pages = [("main", MC.MAIN)] + [(p["group"], i) for i, p in enumerate(MC.T.PAGES)]
        for name, page in pages:
            m.cmd("open", page)
            s.bus.wait(0.3)
            dst = out / f"walk_{name}.png"
            shot(s, dst)
            say(f"{dst}: {MC.Menu.show(m.state())}")
    else:
        out = a.out or ROOT / "tmp/menu_shot.png"
        m.cmd("open", MC.page_of(a.page))
        for k in filter(None, a.keys.split(",")):
            m.cmd("key", MC.KEYS[k])
        s.bus.wait(0.3)
        shot(s, out)
        say(f"{out}: {MC.Menu.show(m.state())}")
    s.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
