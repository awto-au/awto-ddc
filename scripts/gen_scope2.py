#!/usr/bin/env python3
"""Generate fw/test/scope2_data.inc: graticule tiles, cell map, pulse table and font of Scope 2 (fw/test/scope_saver2.c, docs/screensaver.md).

usage: gen_scope2.py [--check] [--raster W] [--model]
  Raster 480 x 270 px = 40 x 15 tiles of 12 x 18 (scaled 8x to 3840 x 2160; other panels: factor 64 * 480 / panel width in the firmware).
  2-bit glyphs: plane A (first 9 words, low bit on the unit) = green (trace, readouts), plane B = red (graticule, level marks); 9 words = 27 bytes per plane, bytes in data port order (docs/osd/rotation.md).
  Static tiles (deduped) get ids 0..N-1; the rest of the 256 ids are dynamic slots the firmware allocates in a ring (trace, cursor and readout tiles).
  --model: worst-case dynamic tiles per frame over all pulse positions / speeds, against the slots available.
  --check: exit 1 when the file on disk differs.
Log: ./tmp/logs/gen_scope2.log
"""
import argparse
import sys

import numpy as np
import osd_gfx as OG
from _repo import ROOT

OUT = ROOT / "fw/test/scope2_data.inc"
LOG = ROOT / "tmp/logs/gen_scope2.log"

TW, TH = 12, 18
BASE_RASTER = 480                       # 480 x 270: 40 x 15 tiles
IDS = 256                               # 2-bit char command: 8 id bits (docs/osd/tiles-fonts.md)
DIV_COUNT_X, DIV_COUNT_Y = 8, 6         # graticule divisions
MINOR_PER_DIV = 5                       # minor ticks per division on the centre axes
BASE_DIV = 4                            # 0 % level: 4 divisions down; 100 % = 3 divisions above it
AMP_DIV = 3
PULSE_PEAK = 255
PS_PER_DIV = 1000
THICK = 1                               # trace drawn twice, THICK px apart
FONT_W, FONT_H, FONT_ADV = 5, 7, 6
SLOW_W = 336                            # the first Scope 2 raster width: pulse / text constants below are in its px and scaled by W / SLOW_W
SPREAD_MIN_1, SPREAD_RANGE_1 = 3, 4     # px per table step
X0_MIN_1, X0_RANGE_1 = 70, 90
X0_STEP = 2                             # px of pulse drift per frame

PULSE = [0, 0, 0, 1, 2, 3, 5, 8, 12, 18, 26, 36, 49, 65, 84, 106,
         130, 154, 176, 196, 213, 227, 238, 246, 251, 254, 255, 254, 251, 246, 239, 230,
         220, 209, 198, 186, 174, 162, 150, 139, 128, 118, 108, 99, 90, 82, 75, 68,
         62, 56, 50, 45, 40, 36, 32, 28, 25, 22, 19, 16, 13, 10, 7, 4]
FONT = {                                # 5 x 7, one byte per column (bit 0 = top row)
    "0": (0x3E, 0x51, 0x49, 0x45, 0x3E), "1": (0x00, 0x42, 0x7F, 0x40, 0x00), "2": (0x42, 0x61, 0x51, 0x49, 0x46),
    "3": (0x21, 0x41, 0x45, 0x4B, 0x31), "4": (0x18, 0x14, 0x12, 0x7F, 0x10), "5": (0x27, 0x45, 0x45, 0x45, 0x39),
    "6": (0x3C, 0x4A, 0x49, 0x49, 0x30), "7": (0x01, 0x71, 0x09, 0x05, 0x03), "8": (0x36, 0x49, 0x49, 0x49, 0x36),
    "9": (0x06, 0x49, 0x49, 0x29, 0x1E), ".": (0x00, 0x60, 0x60, 0x00, 0x00), ">": (0x00, 0x41, 0x22, 0x14, 0x08),
    "k": (0x7F, 0x10, 0x28, 0x44, 0x00), "H": (0x7F, 0x08, 0x08, 0x08, 0x7F), "z": (0x44, 0x64, 0x54, 0x4C, 0x44),
    "n": (0x7C, 0x08, 0x04, 0x04, 0x78), "s": (0x48, 0x54, 0x54, 0x54, 0x20), "m": (0x7C, 0x04, 0x18, 0x04, 0x78),
    " ": (0x00, 0x00, 0x00, 0x00, 0x00), "V": (0x1F, 0x20, 0x40, 0x20, 0x1F), "t": (0x04, 0x3F, 0x44, 0x40, 0x20), "D": (0x60, 0x58, 0x46, 0x58, 0x60),   # D = delta
}
DYN_CHARS = "0123456789.ns"             # the firmware draws the delta t number: only these glyphs go into the header


class Geo:
    def __init__(self, raster: int):
        assert raster % BASE_RASTER == 0
        self.k = raster // BASE_RASTER               # text scale
        self.w = raster
        self.h = raster * 270 // 480
        assert self.w % TW == 0 and self.h % TH == 0
        self.cols, self.rows = self.w // TW, self.h // TH
        assert self.w % (DIV_COUNT_X * MINOR_PER_DIV) == 0 and self.h % (DIV_COUNT_Y * MINOR_PER_DIV) == 0
        self.div_x, self.div_y = self.w // DIV_COUNT_X, self.h // DIV_COUNT_Y
        self.tick_x, self.tick_y = self.div_x // MINOR_PER_DIV, self.div_y // MINOR_PER_DIV
        self.tick_len = 4 * self.k
        self.base_y = BASE_DIV * self.div_y
        self.amp = AMP_DIV * self.div_y
        self.p10, self.p90 = self.amp // 10, self.amp * 9 // 10
        sc = self.w / SLOW_W
        self.spread_min, self.spread_range = round(SPREAD_MIN_1 * sc), round(SPREAD_RANGE_1 * sc)
        self.x0_min, self.x0_range = round(X0_MIN_1 * sc), round(X0_RANGE_1 * sc)
        self.num_ts = 2 * self.k
        self.num_w = 7 * FONT_ADV * self.num_ts
        self.num_h = FONT_H * self.num_ts
        self.num_x, self.num_y = round(306 * self.w / 480), 20 * self.k
        self.num_col0, self.num_col1 = self.num_x // TW, (self.num_x + self.num_w - 1) // TW
        self.num_row0, self.num_row1 = self.num_y // TH, (self.num_y + self.num_h - 1) // TH
        self.num_n = (self.num_col1 - self.num_col0 + 1) * (self.num_row1 - self.num_row0 + 1)
        # delta t of the cursors (10 % / 90 % points of the rising edge) = table indexes of the first >= p10 / p90
        lvl = [p * self.amp // PULSE_PEAK for p in PULSE]
        self.i10 = next(i for i, v in enumerate(lvl) if v >= self.p10)
        self.i90 = next(i for i, v in enumerate(lvl) if v >= self.p90)


def text_px(plane, geo, s, x, y, ts):
    for ch_i, ch in enumerate(s):
        cols = FONT[ch]
        for cx, bits in enumerate(cols):
            for ry in range(FONT_H):
                if bits >> ry & 1:
                    for dy in range(ts):
                        for dx in range(ts):
                            px, py = x + ch_i * FONT_ADV * ts + cx * ts + dx, y + ry * ts + dy
                            if 0 <= px < geo.w and 0 <= py < geo.h:
                                plane[py, px] = 1


def draw_static(geo):
    msb = np.zeros((geo.h, geo.w), np.uint8)
    lsb = np.zeros((geo.h, geo.w), np.uint8)
    for x in range(geo.w):
        if x % geo.div_x == 0 or x == geo.w - 1:
            lsb[:, x] = 1
    for y in range(geo.h):
        if y % geo.div_y == 0 or y == geo.h - 1:
            lsb[y, :] = 1
    for x in range(0, geo.w, geo.tick_x):
        lsb[geo.h // 2 - geo.tick_len:geo.h // 2 + geo.tick_len + 1, x] = 1
    for y in range(0, geo.h, geo.tick_y):
        lsb[y, geo.w // 2 - geo.tick_len:geo.w // 2 + geo.tick_len + 1] = 1
    k = geo.k
    for s, lvl in (("100", geo.amp), ("90", geo.p90), ("10", geo.p10), ("0", 0)):
        text_px(lsb, geo, s, 3 * k, geo.base_y - lvl - 3 * k, k)
    text_px(msb, geo, "1129.500 kHz", 8 * k, 6 * k, k)
    text_px(msb, geo, "Dt", round(280 * geo.w / 480), 6 * k, k)
    text_px(msb, geo, ">200mV", 8 * k, geo.h - 17 * k, k)
    text_px(msb, geo, "1ns", round(243 * geo.w / 480), geo.h - 17 * k, k)
    return msb, lsb


def pack(plane, tx, ty, turned=False):
    """One 12 x 18 tile -> 27 stream bytes (the byte order of the OSD data port, osd_gfx.pack_rows). turned: the tile turned 180 inside itself (Rotate 180, docs/osd/rotation.md)."""
    rows = [[int(v) for v in r] for r in plane[ty * TH:(ty + 1) * TH, tx * TW:(tx + 1) * TW]]
    return OG.pack_rows(OG.turned(rows) if turned else rows)


def tiles(geo):
    msb, lsb = draw_static(geo)
    uniq, ids, cell = {}, [], []
    for ty in range(geo.rows):
        for tx in range(geo.cols):
            cell.append(OG.add_unique(ids, uniq, (pack(msb, tx, ty), pack(lsb, tx, ty))))
    return ids, cell


def pulse_y(geo, x, x0, spread):
    if x < x0:
        i = None
    else:
        i = (x - x0) // spread
    p = PULSE[i] if i is not None and i < len(PULSE) else 0
    return geo.base_y - (p * geo.amp) // PULSE_PEAK


def column_masks(geo, x0, spread, cell):
    """Per column: (dynamic row mask, tiles that need a slot) for one pulse position, as the firmware computes them per column pass.
    A tile with only a cursor in it shares one slot per static base id within the column pass."""
    x10, x90 = x0 + geo.i10 * spread, x0 + geo.i90 * spread
    assert x10 // TW != x90 // TW
    out = []
    for c in range(geo.cols):
        ox = c * TW
        ys = [pulse_y(geo, max(ox - 1, 0) if j == 0 else ox - 1 + j, x0, spread) for j in range(14)]
        r0, r1 = min(ys) // TH, min((max(ys) + THICK) // TH, geo.rows - 1)
        busy = set(range(r0, r1 + 1))
        cur = c in (x10 // TW, x90 // TW)
        if cur and geo.num_col0 <= c <= geo.num_col1:               # the readout tiles live in their own slots, except under a cursor
            busy |= set(range(geo.num_row0, geo.num_row1 + 1))
        mask = sum(1 << r for r in busy)
        slots = len(busy)
        if cur:
            only = set(range(geo.rows)) - busy
            mask |= sum(1 << r for r in only)
            slots += len({cell[r * geo.cols + c] for r in only})
        out.append((mask, slots))
    return out


def model(geo, nstatic, cell):
    """Worst case live dynamic tiles (all columns at once) and the largest single column, over every pulse position and speed."""
    worst_t, worst_k = 0, 0
    for spread in range(geo.spread_min, geo.spread_min + geo.spread_range):
        for off in range(geo.x0_range):
            m = column_masks(geo, geo.x0_min + off, spread, cell)
            worst_t, worst_k = max(worst_t, sum(v[1] for v in m)), max(worst_k, max(v[1] for v in m))
    return worst_t, worst_k, IDS - nstatic - geo.num_n


def emit(raster: int) -> str:
    geo = Geo(raster)
    ids, cell = tiles(geo)
    ns = len(ids)
    t, kmax, slots = model(geo, ns, cell)
    assert t + kmax <= slots, f"dynamic tiles {t} + {kmax} > {slots} slots"
    mask_t = "uint16_t" if geo.rows <= 16 else "uint32_t"
    o = ["// GENERATED by scripts/gen_scope2.py (python scripts/gen_scope2.py); do not edit. Included by scope_saver2.c only.", ""]
    d = lambda n, v, c="": o.append(f"#define AWTO_S2_{n:<22} {v}" + (f"  // {c}" if c else ""))
    d("W", geo.w, "raster px")
    d("H", geo.h)
    d("COLS", geo.cols, "tiles")
    d("ROWS", geo.rows)
    d("STATIC_N", ns, "static tile ids 0..N-1, then the readout tiles, then the dynamic ring up to 255")
    d("MASK_T", mask_t)
    d("DIV_X", geo.div_x, f"{DIV_COUNT_X} divisions across")
    d("BASE_Y", geo.base_y, "0 % level")
    d("AMP", geo.amp, "100 % above the baseline")
    d("I10", geo.i10, "pulse table index of the 10 % point")
    d("I90", geo.i90, "and of the 90 % point")
    d("PS_PER_DIV", PS_PER_DIV)
    d("PULSE_N", len(PULSE))
    d("PULSE_PEAK", PULSE_PEAK)
    d("SPREAD_MIN", geo.spread_min, "px per table step")
    d("SPREAD_RANGE", geo.spread_range)
    d("X0_MIN", geo.x0_min, "pulse start x")
    d("X0_RANGE", geo.x0_range)
    d("X0_STEP", X0_STEP, "px of drift per frame")
    d("THICK", THICK, "trace drawn twice, this many px apart")
    d("TS_NUM", geo.num_ts, "text scale of the delta t number")
    d("NUM_X", geo.num_x)
    d("NUM_Y", geo.num_y)
    d("NUM_COL0", geo.num_col0)
    d("NUM_COL1", geo.num_col1)
    d("NUM_ROW0", geo.num_row0)
    d("NUM_ROW1", geo.num_row1)
    d("FONT_N", len(DYN_CHARS))
    o.append(f"// model: worst case {t} live dynamic tiles + largest column {kmax} of {slots} slots")
    o.append("")
    o.append("#pragma place group(scope2_12)                // data and its readers share a bank (docs/banking)")
    o.append(f"static __code uint8_t s_tS2Pulse[{len(PULSE)}] = {{" + ", ".join(map(str, PULSE)) + "};")
    o.append("#pragma place group(scope2_11)")
    o.append(f"static __code uint8_t s_tS2Font[{len(DYN_CHARS)}][6] = {{")
    for ch in DYN_CHARS:
        o.append(f"    {{'{ch}', " + ", ".join(f"0x{b:02X}" for b in FONT[ch]) + "},")
    o.append("};")
    o.append("#pragma place group(scope2_12)")
    o.append(f"static __code uint8_t s_tS2Cell[{len(cell)}] = {{")
    for i in range(0, len(cell), geo.cols):
        o.append("    " + ", ".join(str(v) for v in cell[i:i + geo.cols]) + ",")
    o.append("};")
    o.append("#pragma place group(scope2_12)")
    o.append(f"static __code uint8_t s_tS2Base[{ns}][54] = {{        // per id: green plane 27 bytes, red plane 27 bytes, in data port byte order (turned on use for Rotate 180)")
    for k in ids:
        o.append("    {" + ", ".join(f"0x{b:02X}" for b in k[0] + k[1]) + "},")
    o.append("};")
    return "\n".join(o) + "\n"


say = OG.logger(LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--raster", type=int, default=BASE_RASTER)
    ap.add_argument("--model", action="store_true")
    a = ap.parse_args()
    geo = Geo(a.raster)
    ids, cell = tiles(geo)
    t, k, slots = model(geo, len(ids), cell)
    say(f"raster {geo.w} x {geo.h} = {geo.cols} x {geo.rows} tiles: {len(ids)} static ids, {slots} dynamic slots, worst case {t} live + column {k}")
    if a.model:
        return 0 if t + k <= slots else 1
    text = emit(a.raster)
    if a.check:
        same = OUT.exists() and OUT.read_text() == text
        say(f"{OUT.name}: {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    OUT.write_text(text)
    say(f"wrote {OUT} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
