#!/usr/bin/env python3
"""md5 of the OSD state of the non-saver screens in the firmware sim: proves a write-path change left every cell, glyph and palette byte as it was.

usage: osd_screens_md5.py BIN MAP [--rotate] [--tsv OUT]      osd_screens_md5.py --compare A.tsv B.tsv
  Screens: console (boot console, text layer osd_tc_cells), flash preview (VCP 0xEB = 7: flash_screen.c map + glyph writes).
  Same state hash as saver_frames_md5.py (font SRAM, window SRAM, palette, OSD registers, overlay). Nothing touches hardware.
Log: ./tmp/logs/osd_screens_md5.log
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import osd_render as R
from _log import log_line as _log_line
from saver_frames_md5 import ROTATE_SETTLE_S, ROW_DISP_ROTATE, VCP_SAVER, state_md5

LOG = R.ROOT / "tmp/logs/osd_screens_md5.log"
VCP_FLASH_PREVIEW = 7
CONSOLE_S = 4.0                          # fw time after boot: the console has drawn its boot lines (saver_sim / splash_sim use 3 s)
FLASH_S = 8.0                            # preview draws in chunks per main pass (flash_screen.c AWTO_FS_STEP_*): 2.7 x the sim's 3 s


def say(s: str) -> None:
    _log_line(s, LOG)


def run(a) -> int:
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map, "1080p60", devs=[eng])
    sess.boot(sync_console=True)
    ddc = D.Mccs(sess.bus, eng)
    if a.rotate:
        ddc.set(0xE0, ROW_DISP_ROTATE)
        ddc.set(0xE1, 1)
        sess.bus.wait(ROTATE_SETTLE_S)
    sess.bus.wait(CONSOLE_S)
    rows = [("console", state_md5(sess.snap()))]
    ddc.set(VCP_SAVER, VCP_FLASH_PREVIEW)
    sess.bus.wait(FLASH_S)
    rows.append(("flash_preview", state_md5(sess.snap())))
    sess.bus.close()
    out = "screen\tstate_md5\n" + "".join(f"{k}\t{v}\n" for k, v in rows)
    if a.tsv:
        a.tsv.parent.mkdir(parents=True, exist_ok=True)
        a.tsv.write_text(out)
    say(f"{a.bin.name}{' rotate' if a.rotate else ''}: " + ", ".join(f"{k} {v}" for k, v in rows))
    return 0


def compare(pa: Path, pb: Path) -> int:
    def load(p):
        return dict(ln.split("\t") for ln in p.read_text().splitlines()[1:])
    ra, rb = load(pa), load(pb)
    diff = [k for k in ra if ra[k] != rb.get(k)]
    ok = not diff and set(ra) == set(rb)
    say(f"compare {pa.name} vs {pb.name}: {len(ra)} screens, {len(diff)} differ {diff}: {'IDENTICAL' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--compare", nargs=2, type=Path)
    a = ap.parse_args()
    if a.compare:
        return compare(*a.compare)
    if not a.bin or not a.map:
        ap.error("BIN and MAP required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
