#!/usr/bin/env python3
"""Tile-count model behind docs/saver-fps-plan.md: how many tiles a saver frame must redraw / upload, full vs incremental.

usage: saver_fps_model.py [--frames N]
  Scope 1 (fw/test/scope_saver.c constants): trace pixels per frame (osd_line per px step, Bresenham split per column),
  tiles touched now, tiles to redraw incrementally (now | last frame), distinct static graticule tiles.
Log: ./tmp/logs/saver_fps_model.log
"""
import argparse
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/saver_fps_model.log"
TW, TH = 12, 18
SC_COLS, SC_ROWS = 32, 12                           # scope_saver.c AWTO_SC_COLS / _ROWS
SC_W, SC_H = SC_COLS * TW, SC_ROWS * TH
SINE = [round(127 * math.sin(2 * math.pi * k / 64)) for k in range(64)]
AMP1, AMP2, H2_PER_PX, H2_PH, PH_STEP = 62, 28, 4, 2, 3
GRID_X, GRID_Y, DOT = 48, 54, 4


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def sc_y(x: int, ph: int) -> int:
    v1 = (SINE[(x + ph) & 63] * AMP1) >> 7
    v2 = (SINE[(x * H2_PER_PX + ph * H2_PH) & 63] * AMP2) >> 7
    return SC_H // 2 - v1 - v2


def sc_trace(ph: int) -> set:
    px = set()
    for x in range(1, SC_W + 1):
        y0, y1 = sc_y(x - 1, ph), sc_y(x, ph)
        d = abs(y1 - y0)
        s = 1 if y1 >= y0 else -1
        e0 = d // 2
        for k in range(e0 + 1):                     # first half (and the start pixel) in column x - 1
            px.add((x - 1, y0 + s * k))
        for k in range(e0 + 1, d + 1):
            px.add((x, y0 + s * k))
        px.add((x, y1))
    return {(x, y) for x, y in px if 0 <= x < SC_W and 0 <= y < SC_H}


def sc_static() -> int:
    tiles = set()
    for r in range(SC_ROWS):
        for c in range(SC_COLS):
            t = []
            for y in range(r * TH, r * TH + TH):
                for x in range(c * TW, c * TW + TW):
                    on = (y % GRID_Y == 0 and x % DOT == 0) or (x % GRID_X == 0 and y % DOT == 0) or y in (0, SC_H - 1) or x in (0, SC_W - 1)
                    t.append(on)
            tiles.add(tuple(t))
    return len(tiles)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=64)
    a = ap.parse_args()
    prev, now_n, dirty_n, px_n = None, [], [], []
    for f in range(a.frames + 1):
        px = sc_trace((f * PH_STEP) & 0xFF)
        tiles = {(x // TW, y // TH) for x, y in px}
        if prev is not None:
            now_n.append(len(tiles))
            dirty_n.append(len(tiles | prev))
            px_n.append(len(px))
        prev = tiles
    say(f"scope 1: {SC_COLS * SC_ROWS} cells; trace px per frame mean {sum(px_n) / len(px_n):.0f} max {max(px_n)}; "
        f"trace tiles mean {sum(now_n) / len(now_n):.0f} max {max(now_n)}; incremental (now | last) mean {sum(dirty_n) / len(dirty_n):.0f} max {max(dirty_n)}; "
        f"distinct static graticule tiles {sc_static()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
