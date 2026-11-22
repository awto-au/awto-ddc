#!/usr/bin/env python3
"""Scope 2 (fw/test/scope_saver2.c) in the firmware simulator: frame rate + PNG frames, upright or Rotate 180. Nothing touches hardware.

usage: scope2_sim.py BIN [--out DIR] [--frames N] [--rotate] [--png K]
  Starts the saver by DDC/CI VCP 0xEB = 4 (as scripts/saver_sim.py), then polls the frame counter g_usAwtoS2Frame (+1 at the first column of every frame)
  every POLL_S of firmware time. Reports firmware ms per frame (mean / min / max over N frames), per column, frames per second.
  --png K: render every K-th frame to DIR/f<counter>.png (the OSD area is 3840 x 2160 shown at 1920 x 1080).
Log: ./tmp/logs/scope2_sim.log
"""
import argparse
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/scope2_sim.log"
VCP_SAVER, SAVER_SCOPE2 = 0xEB, 4
ROW_DISP_ROTATE = 32            # registry row id of disp_rotate
ROTATE_SETTLE_S = 6.0           # fw time for the display re-set after Rotate changes (as saver_sim.py)
POLL_S = 0.001                  # fw time between counter reads: 1 ms = the resolution of a frame time
FRAME_LIMIT_S = 5.0             # a frame must finish well inside this: expiry = no counter change, logged
COLS = 40                       # tile columns of the raster (scripts/gen_scope2.py)


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scope2_sim")
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--png", type=int, default=0)
    ap.add_argument("--cols", type=int, default=COLS)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1 if a.rotate else 0)
    sess.bus.wait(ROTATE_SETTLE_S)
    addr = sess.bus.m.addr("g_usAwtoS2Frame")
    rd = lambda: int.from_bytes(sess.bus.m.rd(addr, 2), "big")
    ddc.set(VCP_SAVER, SAVER_SCOPE2)
    t_start = sess.bus.now()
    last, t_last, times = rd(), None, []
    tag = "rot" if a.rotate else "up"
    while len(times) < a.frames:
        t0 = sess.bus.now()
        while rd() == last and sess.bus.now() - t0 < FRAME_LIMIT_S:
            sess.bus.wait(POLL_S)
        if rd() == last:
            say(f"no frame within {FRAME_LIMIT_S} s (counter {last})")
            return 1
        now, last = sess.bus.now(), rd()
        if t_last is not None:
            times.append((now - t_last) * 1000.0)
            if a.png and last % a.png == 0:
                sess.bus.wait(0.0)
                R.render_snap(sess.snap(), "black", 2).save(a.out / f"{tag}_f{last:04d}.png")
        elif last == 1:
            say(f"first frame (hidden) started {now - t_start:.3f} s after the start cmd")
        t_last = now
    sess.bus.close()
    times.sort()
    mean = sum(times) / len(times)
    say(f"{a.bin.name} {tag}: {len(times)} frames, fw ms per frame mean {mean:.1f} min {times[0]:.1f} max {times[-1]:.1f} -> {1000.0 / mean:.2f} frames/s; per column {mean / a.cols:.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
