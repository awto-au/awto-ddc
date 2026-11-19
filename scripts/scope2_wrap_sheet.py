#!/usr/bin/env python3
"""Contact sheet of Scope 2 frames across one drift wrap (docs/scope-realism.md D-R3): delta t readout jump. Host-side model, nothing touches hardware.

usage: scope2_wrap_sheet.py [--before 12] [--after 6] [--wrap 1] [--fixed] [--out PNG]
  Re-runs the firmware's S2Params arithmetic (fw/test/scope_saver2.c: drift +X0_STEP per frame, wrap at X0_RANGE -> spread +1, delta t = (x90 - x10) * PS_PER_DIV / DIV_X)
  and draws each frame from the gen_scope2.py raster model (graticule, pulse, 10 %/90 % cursors, delta t text). --wrap N: the N-th wrap (1 = spread 4 -> 5).
  --fixed: the proposed fix, spread constant at SPREAD_MIN (readout constant). Also prints the table (frame, pulse x0, readout, change).
Log: ./tmp/logs/scope2_wrap_sheet.log
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_scope2 as G
import isostamp

ROOT = G.ROOT
LOG = ROOT / "tmp/logs/scope2_wrap_sheet.log"
FPS_SIM, FPS_HW = 6.6, 5.63             # docs/scope-realism.md section 2 (sim 2026-11-18, unit 3 stock 2026-11-19)
GREEN, RED, CURSOR = (60, 255, 80), (150, 30, 30), (255, 220, 60)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def states(geo, fixed):
    """Yield (frame, x0, spread, x10, x90, ps, wrapped) per S2Params call, as the firmware (first call = frame 1)."""
    drift, spread, n = 0, geo.spread_min, 0
    while True:
        n += 1
        drift += G.X0_STEP
        wrapped = drift >= geo.x0_range
        if wrapped:
            drift -= geo.x0_range
            if not fixed:
                spread += 1
                if spread >= geo.spread_min + geo.spread_range:
                    spread = geo.spread_min
        x0 = geo.x0_min + drift
        x10, x90 = x0 + geo.i10 * spread, x0 + geo.i90 * spread
        yield n, x0, spread, x10, x90, (x90 - x10) * G.PS_PER_DIV // geo.div_x, wrapped


def pulse(geo, x, x0, spread):
    if x < x0:
        return 0
    d = x - x0
    i = d // spread
    if i >= len(G.PULSE):
        return 0
    a = G.PULSE[i]
    b = G.PULSE[i + 1] if i + 1 < len(G.PULSE) else 0
    return a + (b - a) * (d - i * spread) // spread


def frame(geo, st, base):
    n, x0, spread, x10, x90, ps, _ = st
    msb, lsb = base
    im = np.zeros((geo.h, geo.w, 3), np.uint8)
    im[lsb == 1] = RED
    im[msb == 1] = GREEN
    for x in range(geo.w):
        y = geo.base_y - pulse(geo, x, x0, spread) * geo.amp // G.PULSE_PEAK
        for t in range(G.THICK + 1):
            im[min(y + t, geo.h - 1), x] = GREEN
    for cx in (x10, x90):
        if 0 <= cx < geo.w:
            im[::3, cx] = CURSOR
    text = f"{ps // 1000}.{ps % 1000 // 10:02d} ns"
    r = Image.fromarray(im)
    a = np.array(r)
    a[geo.num_y:geo.num_y + geo.num_h, geo.num_x:geo.num_x + geo.num_w] = 0      # readout cells are redrawn clean
    r = Image.fromarray(a)
    d = ImageDraw.Draw(r)
    for ci, ch in enumerate(text):
        for cx, bits in enumerate(G.FONT[ch]):
            for ry in range(G.FONT_H):
                if bits >> ry & 1:
                    px, py = geo.num_x + ci * G.FONT_ADV * geo.num_ts + cx * geo.num_ts, geo.num_y + ry * geo.num_ts
                    d.rectangle([px, py, px + geo.num_ts - 1, py + geo.num_ts - 1], fill=GREEN)
    return r, text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", type=int, default=12)
    ap.add_argument("--after", type=int, default=6)
    ap.add_argument("--wrap", type=int, default=1)
    ap.add_argument("--fixed", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scratch/scope2_wrap_sheet.png")
    a = ap.parse_args()
    geo = G.Geo(G.BASE_RASTER)
    base = G.draw_static(geo)
    seq = list(next_n(states(geo, a.fixed), 3000))
    wraps = [s[0] for s in seq if s[6]]
    wf = wraps[a.wrap - 1]
    sel = [s for s in seq if wf - a.before <= s[0] <= wf + a.after]
    cols = 3
    rows = (len(sel) + cols - 1) // cols
    fh = 20 * 2 + 4
    cw, ch = geo.w, geo.h + fh
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * 6, rows * ch + (rows + 1) * 6 + 30), (20, 20, 20))
    font = ImageFont.load_default(size=22)
    ImageDraw.Draw(sheet).text((6, 4), f"Scope 2, frames {sel[0][0]}..{sel[-1][0]}, wrap at frame {wf}" + (" - FIXED (constant spread)" if a.fixed else " - current firmware"), font=font, fill=(255, 255, 255))
    prev, prev_ps, table = None, 0, []
    for k, s in enumerate(sel):
        im, text = frame(geo, s, base)
        tile = Image.new("RGB", (cw, ch), (0, 0, 0))
        tile.paste(im, (0, 0))
        d = ImageDraw.Draw(tile)
        chg = "" if prev is None else ("same" if text == prev else f"{(s[5] - prev_ps) / 1000:+.2f} ns")
        mark = s[6]
        d.text((6, geo.h + 4), f"frame {s[0]}  x0 {s[1]}  {text}  {chg}", font=font, fill=(255, 80, 80) if mark else (255, 255, 255))
        if mark:
            d.rectangle([0, 0, cw - 1, ch - 1], outline=(255, 60, 60), width=4)
            d.text((6, 6), "WRAP", font=font, fill=(255, 60, 60))
        sheet.paste(tile, (6 + (k % cols) * (cw + 6), 36 + 6 + (k // cols) * (ch + 6)))
        table.append((s[0], s[1], s[2], text, chg, mark))
        prev, prev_ps = text, s[5]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    say(f"wrote {a.out}" + (" (fixed)" if a.fixed else ""))
    say("frame | pulse x0 | spread | readout | change vs previous")
    for f, x0, sp, t, c, m in table:
        say(f"{f:5d} | {x0:8d} | {sp:6d} | {t:8s} | {c}{'  <- WRAP' if m else ''}")
    if not a.fixed:
        ps = [(s[5], s[0]) for s in seq if s[6]]
        say(f"wraps at frames {wraps[:8]}; readouts after each wrap {[p for p, _ in ps[:7]]} ps; interval {wraps[1] - wraps[0]} frames = {(wraps[1] - wraps[0]) / FPS_HW:.1f} s at {FPS_HW} fps (hw), {(wraps[1] - wraps[0]) / FPS_SIM:.1f} s at {FPS_SIM} (sim), {(wraps[1] - wraps[0]) / 31:.1f} s at 31 fps")
    return 0


def next_n(gen, n):
    for _ in range(n):
        yield next(gen)


if __name__ == "__main__":
    sys.exit(main())
