#!/usr/bin/env python3
"""Screensaver check in the firmware simulator (docs/screensaver.md): DDC/CI VCP 0xEB starts / stops Pac-Man and the scope; PNGs of each.

usage: saver_sim.py [BIN MAP] [--out DIR]
  - BIN / MAP default: tmp/fw/AWT26110003-sv1-be.{bin,map} (wb_build.py --tree . --serial AWT26110003 --tag sv1 -D _AWTO_AUDIO_TEST).
  - Steps: boot; VCP 0xEB = 3 (scope), wait 4 s fw time, render; = 0 (stop), render; = 2 (Pac-Man), render; = 0. PASS = font SRAM written when started,
    OSD closed (no window cells drawn) after stop. Exit 1 on a FAIL.
Log: ./tmp/logs/saver_sim.log
"""
import argparse
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_sim.log"
VCP_SAVER = 0xEB
RUN_S = 4.0                     # fw time for the draw (scope: 64 passes of tile uploads, ~1.5 s) plus one frame
STOP_S = 1.0                    # fw time for the stop (OSD close)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def lit(st) -> int:
    return sum(1 for w in st.font.values() if any(w))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=ROOT / "tmp/fw/AWT26110003-sv1-be.bin")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/saver_sim")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    fails = 0
    for name, val in (("scope", 3), ("pacman", 2)):
        base = lit(sess.snap())
        ddc.set(VCP_SAVER, val)
        sess.bus.wait(RUN_S)
        st = sess.snap()
        R.render_snap(st, "black", 2).save(a.out / f"{name}_run.png")
        ok = lit(st) > base
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = {val} ({name}): font words lit {base} -> {lit(st)}")
        ddc.set(VCP_SAVER, 0)
        sess.bus.wait(STOP_S)
        st = sess.snap()
        img = R.render_snap(st, "black", 2)
        img.save(a.out / f"{name}_stop.png")
        bright = sum(1 for p in img.convert("L").resize((96, 54)).getdata() if p > 0)
        ok = bright == 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = 0: screen after stop has {bright} lit samples of 5184")
    sess.bus.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
