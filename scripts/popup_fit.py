#!/usr/bin/env python3
"""Do the debug pop-up and key test screen rows fit the info pop-up's text window? (awto-ddc#39 #34, unit 2: characters wrapped)

usage: popup_fit.py [--list] [--tree DIR]
  The SDK pop-up string code (OsdPropPutString, centered): sums the glyph widths into ONE BYTE (px, wraps at 256), rounds up to
  12 px cells, centres the row in the 23-cell text field starting at cell 12 (map is 36 cells wide: text area cols 12..35 = 288 px).
  A row is OK when its width stays under LIMIT_PX (BYTE, with margin) and so inside the 24-cell text area. A row over it wraps: the
  byte sum overflows, the centring pad goes wrong and the map spills into the next row.
  A font page holds the glyph cells of its two rows (page 0 40 cells, 1 56, 2 48): a page over capacity wraps and overwrites.
  Rows below = the WORST CASE of every format string in fw/osd/console.c (key screen, debug pop-up),
  built from the same glyph mapping as AwtoPutChar (anything else prints '?'). Glyph widths come from the SDK font width table
  of the ported tree (tmp/sdcc-port/src ... FontWidthTable.h). Exit 1 when a row does not fit. Log: tmp/logs/popup_fit.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/popup_fit.log"
TEXT_COLS = 24                 # cells 12..35 of the 36 cell map
LIMIT_PX = 240                 # < 255 (BYTE sum) and < 288 (text area), with margin for the 12 px rounding and the centre pad
GLYPH_MAX = 26                 # AwtoPutGlyph clamp (the buffer holds 28)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    print(s)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")


def widths(tree):
    base = tree / "tmp/sdcc-port/src/User/RTD Series/RTD2014Osd/Header"
    t = (base / "TextTableBody/Rtd2014OsdTextTableBody_FontWidthTable.h").read_text()
    w = [int(x) for x in re.findall(r"\d+", t[t.index("{") + 1:t.index("};")])]
    d = (base / "RTD2014OsdTextTableDefine.h").read_text()
    e = d[d.index("enum OSDFontCBody0Def"):d.index("enum OSDFontCBodyChineseDef")]
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", e[e.index("{") + 1:e.index("}")])
    idx = {n: i for i, n in enumerate(names)}
    return w, idx


def glyph_px(w, idx, c):
    """px of one char as AwtoPutChar prints it ('W' / 'w' are two glyphs; unknown = '?')"""
    def g(code):
        return w[idx[f"U{code:04X}"]]
    if c in "Ww":
        return g(ord(c)) if f"U{ord(c):04X}" in idx else 0
    ok = c.isdigit() or c.isalpha() and c.isascii() or c in " :.-/"
    return g(ord(c) if ok else ord("?"))


def width(w, idx, s):
    n, px = 0, 0
    for c in s:
        k = 2 if c in "Ww" else 1
        if n + k > GLYPH_MAX:
            break
        n += k
        if c in "Ww":
            px += w[idx[f"U{ord(c):04X}_0"]] + w[idx[f"U{ord(c):04X}_1"]]
        else:
            px += glyph_px(w, idx, c)
    return px, n


# page capacity (cells): the SDK keeps one dynamic glyph cell per 12 px of text per page; rows (0,3) page 0, (1,4) page 1, (2,5) page 2;
# a page that runs out wraps its pointer and overwrites the first row's cells (RTD2014Include.h _OSD_PAGE_n_START/_END)
PAGE_CELLS = {0: 0x27 - 0x00 + 1, 1: 0x5F - 0x28 + 1, 2: 0xF0 - 0xC1 + 1}
# (screen, row, page, worst-case text) mirroring the C format strings (fw/osd/console.c).
# A0 / A1 ladders hold one key each, so at most 3 keys are down: one of MENU UP AUTO, one of SOURCE DOWN, and POWER.
ROWS = [
    ("key", "A0", 0, "A0 FF 31 0.996FS"),
    ("key", "A1+P30", 1, "A1 FF 31 0.996FS P30 1"),
    ("key", "KEY", 2, "KEY AUTO SOURCE POWER"),
    ("key", "MSG", 0, "MSG SOURCE R11 H1 INJ"),
    ("key", "LAST", 1, "LAST" + " M" * 8),
    ("key", "N", 2, "N 255 CLOSE UP DOWN"),
    ("dbg", "port", 0, "D4 3840x2160 60.000Hz"),
    ("dbg", "mode", 1, "ACTIVE 3  PWR SAVE"),
    ("dbg", "clk", 2, "PCLK 594.000 DCLK 540.028"),
    ("dbg", "loop", 0, "LOOP 12345/s H 135.000kHz"),
    ("dbg", "fw", 1, "FW wb-p14keys4"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    w, idx = widths(a.tree)
    bad = 0
    pages = {}
    for scr, name, page, text in ROWS:
        px, n = width(w, idx, text)
        cells = -(-px // 12) + 1                       # round up to 12 px cells + one parity pad cell
        over = px > LIMIT_PX or n >= GLYPH_MAX
        bad += over
        pages.setdefault((scr, page), []).append(cells)
        say(f"{'OVER' if over else 'ok  '} {scr:3s} {name:7s} {px:3d} px {n:2d} glyphs {cells:2d} cells (limit {LIMIT_PX} px, {GLYPH_MAX} glyphs)  {text!r}")
    for (scr, page), cs in sorted(pages.items()):
        full = sum(cs) > PAGE_CELLS[page]
        bad += full
        say(f"{'OVER' if full else 'ok  '} {scr:3s} font page {page}: {sum(cs)} of {PAGE_CELLS[page]} cells")
    say(f"popup_fit: {bad} problem(s) in {len(ROWS)} rows")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
