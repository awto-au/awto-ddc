#!/usr/bin/env python3
"""OSD hardware levers for saver frame rate (docs/saver-fps-hw.md): write-path costs and the run-glyph trace budget.

usage: saver_hw_budget.py [--dclk-khz N ...] [--raster WxH ...] [--cw PX ...] [--shift PX] [--frames N]
  1. Burst-DMA byte time from the SDK OSD gap formula (fw/rtdfw/awto/reg/burst.c hb_osd_gap) per display clock.
  2. Glyph upload cost per tile (1-bit 27 B, 2-bit 54 B): per-byte times measured on unit 3 (docs/osd-hw-tests.md T1/T2) vs burst.
  3. Run-glyph trace (1-bit chars of width CW px, glyph = one vertical run in an 18-row cell): SRAM / id / row-length limits and
     the map writes per frame for a Scope-2-like pulse moving SHIFT px per frame (changed cells only, glyph-id byte only).
No hardware, no sim. Log: ./tmp/logs/saver_hw_budget.log
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[1]


ROOT = repo_root()
LOG = ROOT / "tmp/logs/saver_hw_budget.log"

F_SYS_HZ = 351e6 / 4            # MCU clock: M2PLL 351 MHz / FFED[5:2] 4 / FFEE[5:2] 1, read on unit 2 (tmp/regs/*-ps-*.json, 2026-11-12)
GAP_K = 12109500                # hb_osd_gap constant (= 69 x 351 x 1000 x 2 / 4, burst.c)
US_PORT_SDK = 4.12              # us per byte, ScalerOsdDataPort, unit 3 (osd-hw-tests.md T1, 2026-11-18)
US_PORT_DIRECT = 2.39           # us per byte, direct AWTO_XFR loop, EA off (T2)
US_PORT_TRIPLE = 2.46           # us per byte, direct unrolled triples, EA off (T5)
BURST_SETUP_XFR = 16            # register accesses around one burst (hb_burst S1..S12)
US_PER_XFR = 2.4                # one scaler register access from C, ~ the direct port byte time [guess]
SRAM_WORDS = 12288              # _OSD_SRAM_SIZE, read back on unit 3 (docs/osd/limits.md)
MAP_FETCH_LIMIT = 8192          # display reads cells below this map address (docs/osd/tiles-fonts.md, unit 2)
ROW_CHARS_MAX = 255             # row command char count: 8 bit (docs/osd/limits.md)
GLYPH_H = 18                    # rows of a glyph cell
WORDS_1BIT = 9
IDS_1BIT = 512


def say(lf, s):
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    lf.write(line + "\n")


def burst_us_per_byte(dclk_khz: int, hdouble: bool) -> float:
    g = max(2, min(0xFF, (GAP_K // dclk_khz - 2) * (2 if hdouble else 1)))
    return 2 * g / F_SYS_HZ * 1e6      # SCA_INF_PERIOD TI = SYS_PERIOD x 2 x g (regdb 0xFFFB); SYS = MCU clock [guess]


def pulse_y(x: int, w: int, h: int, x0: int) -> int:
    """Scope-2-like pulse: low, rising edge, high, falling edge (raster px, y down)."""
    lo, hi = int(h * 0.8), int(h * 0.2)
    rise, top = w // 40, w // 4
    p = (x - x0) % w
    if p < rise:
        return lo + (hi - lo) * p // rise
    if p < rise + top:
        return hi
    if p < 2 * rise + top:
        return hi + (lo - hi) * (p - rise - top) // rise
    return lo


def trace_cells(w: int, h: int, cw: int, x0: int) -> dict:
    """cell (row, col) -> glyph key (run top, run bottom inside the cell) for one frame."""
    cells = {}
    for c in range(w // cw):
        ys = [pulse_y(c * cw + k, w, h, x0) for k in range(-1, cw)]
        a, b = min(ys), max(ys)
        for r in range(a // GLYPH_H, b // GLYPH_H + 1):
            cells[(r, c)] = (max(a, r * GLYPH_H) - r * GLYPH_H, min(b, r * GLYPH_H + GLYPH_H - 1) - r * GLYPH_H)
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dclk-khz", type=int, nargs="*", default=[533000, 594000])   # panel typical (AWTO_M280DCA_E3B.h) and 4K60 CTA
    ap.add_argument("--raster", nargs="*", default=["480x270", "960x540"])
    ap.add_argument("--cw", type=int, nargs="*", default=[2, 4, 6])
    ap.add_argument("--shift", type=int, default=8, help="pulse move per frame, raster px")
    ap.add_argument("--frames", type=int, default=16)
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", buffering=1) as lf:
        say(lf, "== 1. burst byte time (SDK gap formula, SYS = MCU clock 87.75 MHz [guess])")
        for d in a.dclk_khz:
            say(lf, f"dclk {d / 1000:.0f} MHz: {burst_us_per_byte(d, False):.3f} us/B (db_width off), {burst_us_per_byte(d, True):.3f} us/B (on)")
        bb = burst_us_per_byte(a.dclk_khz[0], False)
        say(lf, "== 2. glyph upload per tile, us")
        for name, n in (("1-bit", 27), ("2-bit", 54)):
            burst = BURST_SETUP_XFR * US_PER_XFR + n * bb
            say(lf, f"{name} {n} B: ScalerOsdDataPort {n * US_PORT_SDK:.0f}, direct {n * US_PORT_DIRECT:.0f}, "
                    f"triples {n * US_PORT_TRIPLE:.0f}, burst {burst:.0f} (setup {BURST_SETUP_XFR} x {US_PER_XFR} us + {bb:.2f} us/B)")
        say(lf, f"== 3. run-glyph trace, pulse moving {a.shift} px / frame, {a.frames} frames")
        runs = GLYPH_H * (GLYPH_H + 1) // 2
        for ras in a.raster:
            w, h = (int(v) for v in ras.split("x"))
            rows = h // GLYPH_H
            for cw in a.cw:
                cols = w // cw
                map_words = rows + 1 + rows * cols
                glyph_words = (runs + 1) * WORDS_1BIT
                ok = cols <= ROW_CHARS_MAX and map_words < MAP_FETCH_LIMIT and map_words + glyph_words <= SRAM_WORDS
                prev = trace_cells(w, h, cw, 0)
                writes = xfr = 0
                for f in range(1, a.frames + 1):
                    cur = trace_cells(w, h, cw, f * a.shift)
                    changed = sorted(k for k in set(prev) | set(cur) if prev.get(k) != cur.get(k))
                    writes += len(changed)
                    last = None
                    for k in changed:                       # address set (0x90 / 0x91) only where the cell does not follow the last one
                        xfr += 1 if last is not None and k == (last[0], last[1] + 1) else 3
                        last = k
                    prev = cur
                say(lf, f"{ras} cw {cw}: {cols} chars x {rows} rows, map {map_words} + glyphs {glyph_words} words "
                        f"({'fits' if ok else 'DOES NOT FIT'}: row <= {ROW_CHARS_MAX}, map < {MAP_FETCH_LIMIT}, SRAM <= {SRAM_WORDS}); "
                        f"{writes / a.frames:.0f} cells / frame, {xfr / a.frames:.0f} XFR writes = "
                        f"{xfr / a.frames * US_PER_XFR / 1000:.2f} ms / frame at {US_PER_XFR} us")
    return 0


if __name__ == "__main__":
    sys.exit(main())
