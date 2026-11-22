#!/usr/bin/env python3
"""Firmware time per Pac-Man step (test cmd 0xB8) in the simulator: mean / max over N steps and the steps per second that follows.

usage: pacman_speed.py BIN [--steps N]
  Draws the maze (0xB7), then sends one step cmd at a time and polls the firmware step counter (s_usStep, found via g_usAwtoPcPosV) every POLL_S of firmware time.
  Time per step = end of the cmd write -> counter change (includes the main loop pass that picks the cmd up). Nothing touches hardware.
Log: ./tmp/logs/pacman_speed.log
"""
import argparse
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R
import pacman_sim as P

LOG = R.ROOT / "tmp/logs/pacman_speed.log"
POLL_S = 0.0002                 # firmware time between counter reads: resolution of the result (0.2 ms)
DRAW_WAIT_S = 3.0               # the draw uploads ~14 KB; the sim needs well under this (expected ~1 fw s)
STEP_LIMIT_S = 0.5              # one step must finish well inside the 586 ms watchdog: expiry = step lost, logged


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--steps", type=int, default=200)
    a = ap.parse_args()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60")
    sess.boot()
    addr = sess.bus.m.addr("g_usAwtoPcPosV") - 2         # s_usStep is static (not in the map): the 2 bytes before g_usAwtoPcPosV in pacman_classic.c's XSEG1
    rd = lambda: int.from_bytes(sess.bus.m.rd(addr, 2), "big")
    P.send(sess, P.TC_DRAW)
    sess.bus.wait(DRAW_WAIT_S)
    times, sends = [], []
    for _ in range(a.steps):
        before = rd()
        t0 = sess.bus.now()
        P.send(sess, P.TC_STEP)
        t1 = sess.bus.now()
        while rd() == before and sess.bus.now() - t1 < STEP_LIMIT_S:
            sess.bus.wait(POLL_S)
        if rd() == before:
            say(f"step lost after {STEP_LIMIT_S} s (counter {before})")
            continue
        times.append((sess.bus.now() - t1) * 1000.0)
        sends.append((t1 - t0) * 1000.0)
    times.sort()
    mean = sum(times) / len(times)
    say(f"{a.bin.name}: {len(times)} steps, firmware ms per step (after the cmd write .. counter change): mean {mean:.2f}, median {times[len(times) // 2]:.2f}, min {times[0]:.2f}, max {times[-1]:.2f} -> {1000.0 / mean:.0f} steps/s; the cmd write itself takes {sum(sends) / len(sends):.2f} ms of bus time")
    return 0


if __name__ == "__main__":
    sys.exit(main())
