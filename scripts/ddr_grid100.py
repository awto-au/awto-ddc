#!/usr/bin/env python3
"""awto-ddc#255: a 100 x 100 screen-pixel square with a 10 x 10 colour grid and a 100 px circle, written into the frozen frame (held).

usage: ddr_grid100.py preview                       host PNG of the predicted picture (tmp/scratch/grid100_pred.png, x4)
       ddr_grid100.py --unit 1 --bus 18 run [--x0 N --y0 N]   frozen black frame + the figure, held until tmp/scratch/ddr_release
Mapping used (docs/data-channels.md, photos 2026-11-19): 3 B per pixel (memory order B, G, R), 16 B burst = units a, a + 1 (a even),
line pitch exactly 1440 units (the 40-row column showed no drift), every memory line is shown on 2 screen lines (so y_screen = 2 * line),
the write buffer has its 8 B halves swapped. The figure is composed on the host as final frame bytes; each touched 16 B burst is
written whole (mask 0), so no mask lane assumption is needed.
Log: ./tmp/logs/ddr_frame_test.log
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddr_frame_test as T
import ddr_freeze_test as F
import isostamp
from p037_test import rd as prd

ROOT = T.ROOT
SW = 3840
PAL = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (128, 0, 255), (255, 0, 255),
       (160, 82, 45), (128, 128, 128)]                               # 10 line colours (R, G, B)
CIRCLE = (255, 255, 255)
SIDE = 100                                                           # screen pixels
STEP = 10


def compose(x0: int, y0: int) -> dict[tuple[int, int], tuple[int, int, int]]:
    """{(x, memory line): (R, G, B)}; y0 is the first screen row (even), memory line = screen row / 2."""
    m0 = y0 // 2
    px: dict[tuple[int, int], tuple[int, int, int]] = {}
    xs = [x0 + STEP * i for i in range(SIDE // STEP)] + [x0 + SIDE - 1]
    for k, x in enumerate(xs):                                        # vertical lines, 1 px wide
        for m in range(m0, m0 + SIDE // 2):
            px[(x, m)] = PAL[min(k, 9)]
    ms = [m0 + (STEP // 2) * j for j in range(SIDE // STEP)] + [m0 + SIDE // 2 - 1]
    for k, m in enumerate(ms):                                        # horizontal lines, 1 memory line = 2 screen rows
        for x in range(x0, x0 + SIDE):
            px[(x, m)] = PAL[min(k, 9)]
    cx, cy = x0 + SIDE / 2 - 0.5, y0 + SIDE / 2 - 0.5                 # circle in screen geometry, then folded onto memory lines
    for n in range(1440):
        t = 2 * math.pi * n / 1440
        x = round(cx + (SIDE / 2 - 0.5) * math.cos(t))
        ys = round(cy + (SIDE / 2 - 0.5) * math.sin(t))
        px[(x, ys // 2)] = CIRCLE
    return px


def frame_bytes(px) -> dict[int, int]:
    fb: dict[int, int] = {}
    for (x, m), (r, g, b) in px.items():
        base = 3 * (m * SW + x)
        fb[base], fb[base + 1], fb[base + 2] = b, g, r                # memory order B, G, R
    return fb


def bursts(fb: dict[int, int]) -> list[tuple[int, list[int]]]:
    out = []
    for b in sorted({i // 16 for i in fb}):
        out.append((2 * b, [fb.get(16 * b + i, 0) for i in range(16)]))
    return out


def preview(x0: int, y0: int) -> None:
    from PIL import Image
    px = compose(x0, y0)
    im = Image.new("RGB", (SIDE + 20, SIDE + 20), (0, 0, 0))
    for (x, m), c in px.items():
        for dy in (0, 1):
            im.putpixel((x - x0 + 10, 2 * m + dy - y0 + 10), c)    # each memory line is shown twice
    im = im.resize((im.width * 4, im.height * 4), Image.NEAREST)
    out = ROOT / "tmp/scratch/grid100_pred.png"
    im.save(out)
    T.log(f"preview {out}: {len(px)} memory pixels, {len(bursts(frame_bytes(px)))} bursts")


def run(d, x0: int, y0: int) -> None:
    px = compose(x0, y0)
    bs = bursts(frame_bytes(px))
    F.frame_mode(d.io)
    t_on = time.monotonic()
    proc = F.pattern_start("solid 0 0 0")
    F.wait_marker(d, 0, bytes([0] * 16))
    F.freeze(d.io, True)
    r = T.MCU_DC["a"]
    d.wr(r["len"], 2)
    d.wr(r["wmask"], 0)
    d.wr(r["wmask"] + 1, 0)
    cur_a, cur_d = [None] * 4, [None] * 16
    t_w = time.monotonic()
    for a, mem in bs:
        buf = mem[8:] + mem[:8]                                       # write buffer halves swapped
        for i, sh in enumerate((24, 16, 8, 0)):
            v = (a >> sh) & 0xFF
            if cur_a[i] != v:
                d.wr(r["addr"] + i, v)
                cur_a[i] = v
        for i in range(16):
            if cur_d[i] != buf[i]:
                d.wr(r["wbuf"] + i, buf[i])
                cur_d[i] = buf[i]
        d.wr(r["cmd"], T.DC_CMD_WRITE)
    T.log(f"{len(bs)} bursts written in {time.monotonic() - t_w:.1f} s: square screen x {x0}..{x0 + SIDE - 1}, y {y0}..{y0 + SIDE - 1}")
    rel = ROOT / "tmp/scratch/ddr_release"
    if rel.exists():
        rel.unlink()
    T.log(f"FIGURE UP at {isostamp.now()}; holding until {rel} exists (backstop {F.HOLD_MAX_S:.0f} s)")
    t_h = time.monotonic()
    while not rel.exists() and time.monotonic() - t_h < F.HOLD_MAX_S:
        prd(d.io, F.OVERLAY)
    T.log(f"hold ended after {time.monotonic() - t_h:.0f} s: {'release file' if rel.exists() else 'BACKSTOP'}")
    F.finish(d, proc, t_on)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["preview", "run"])
    ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--bus", type=int, default=18)
    ap.add_argument("--x0", type=int, default=1700)
    ap.add_argument("--y0", type=int, default=1000)
    a = ap.parse_args()
    if a.op == "preview":
        preview(a.x0, a.y0)
        return 0
    d = T.Dbg(a.unit, a.bus)
    try:
        run(d, a.x0, a.y0)
    finally:
        d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
