#!/usr/bin/env python3
"""Firmware time per Asteroids column pass / frame / game step in the simulator (VCP 0xEB = 8). Nothing touches hardware.

usage: asteroids_speed.py BIN [--seconds S]
  Starts the saver, then polls the column counter (g_ucAwtoAstCol) and the step counter (g_usAwtoAstStep) every POLL_S of firmware time.
  Pass time = column change to column change (includes the main loop pass around it); the pass that wraps the column to 0 starts a frame (game step + column 0).
  Frame = one step to the next; steps/s follows (includes the AWTO_SAVER_AST_MS pause).
Log: ./tmp/logs/asteroids_speed.log
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

LOG = R.ROOT / "tmp/logs/asteroids_speed.log"
VCP_SAVER, VCP_ASTEROIDS = 0xEB, 8
POLL_S = 0.0002                 # resolution of the result (0.2 ms of firmware time)
SETTLE_S = 8.0                  # first (hidden) frame draws every glyph: not counted
ROW_DISP_ROTATE = 32
ROTATE_SETTLE_S = 6.0


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--seconds", type=float, default=20.0)
    a = ap.parse_args()
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 0)
    sess.bus.wait(ROTATE_SETTLE_S)
    col_a, step_a = sess.bus.m.addr("g_ucAwtoAstCol"), sess.bus.m.addr("g_usAwtoAstStep")
    col = lambda: sess.bus.m.rd(col_a, 1)[0]
    step = lambda: int.from_bytes(sess.bus.m.rd(step_a, 2), "big")
    ddc.set(VCP_SAVER, VCP_ASTEROIDS)
    sess.bus.wait(SETTLE_S)
    t_end = sess.bus.now() + a.seconds
    last_col, t_col, last_step, t_step = col(), sess.bus.now(), step(), sess.bus.now()
    passes, frames, first = [], [], []
    while sess.bus.now() < t_end:
        sess.bus.wait(POLL_S)
        c, s, t = col(), step(), sess.bus.now()
        if c != last_col:
            (first if last_col == 0 else passes).append((t - t_col) * 1000.0)   # the pass that ran column 0 also ran the game step
            last_col, t_col = c, t
        if s != last_step:
            frames.append((t - t_step) * 1000.0)
            last_step, t_step = s, t
    passes.sort()
    say("pass ms percentiles 0/10/25/50/75/90/100: " + " ".join(f"{passes[min(len(passes) - 1, int(len(passes) * q))]:.1f}" for q in (0, 0.1, 0.25, 0.5, 0.75, 0.9, 1)))
    mean = sum(passes) / len(passes)
    fmean = sum(frames) / len(frames)
    say(f"{a.bin.name}: {len(passes)} column passes: mean {mean:.1f} ms, median {passes[len(passes) // 2]:.1f}, p95 {passes[int(len(passes) * 0.95)]:.1f}, max {passes[-1]:.1f}")
    first.sort()
    say(f"column 0 passes (game step + column): {len(first)}, mean {sum(first) / len(first):.1f} ms, max {first[-1]:.1f}")
    say(f"{len(frames)} frames (= game steps): mean {fmean:.0f} ms -> {1000.0 / fmean:.2f} steps/s")
    sess.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
