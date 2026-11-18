#!/usr/bin/env python3
"""Generate fw/test/flash_screen_data.inc: glyphs and static text of the flash warning screen (#232).

usage: gen_flash_screen.py [--check]
  Screen = 30 x 11 tiles of 12 x 18 px, scaled up 64 / 6 = 10.67 (3840 px wide): a 72 x 72 px Pac-Man (6 x 4 tiles, mouth open / closed, glyph ids
  PM_OPEN.. / PM_CLOSED..), a title row, and three text rows the host flasher rewrites over ISP (scripts/flash_screen.py). Text font = 5 x 7 letters
  drawn 2x in a 12 x 18 tile. Glyph 0 is blank. 1-bit glyphs, 9 words = 27 bytes each, low byte first.
  This module is also the layout source for scripts/flash_screen.py (constants below).
  --check: exit 1 when the file on disk differs.
Log: ./tmp/logs/gen_flash_screen.log
"""
import argparse
import math
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_pacman_classic as G  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
OUT = ROOT / "fw/test/flash_screen_data.inc"
LOG = ROOT / "tmp/logs/gen_flash_screen.log"

COLS, ROWS = 30, 11                     # tiles; 30 x 12 px x 10.67 = 3840 px
TILE_W, TILE_H = 12, 18
PM_COLS, PM_ROWS = 6, 4                 # Pac-Man 72 x 72 px
PM_COL0, PM_ROW0 = 12, 2                # its top-left tile (centred: (30 - 6) / 2)
ROW_TITLE = 0
ROW_LINES = (6, 7, 8, 9, 10)            # phase + bank, address + sector + percent, interface, errors, time: rewritten by the host
TITLE = "FLASHING - DO NOT POWER OFF"
TITLE_SPLASH = "AWTO"                   # boot splash (docs/flash-screen.md): second title row of the same table, centred
FONT_CHARS = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ%./:-"      # glyph id = index (0 = blank)
PM_OPEN = len(FONT_CHARS)               # first glyph id of the open-mouth frame (24 tiles), then the closed frame
PM_CLOSED = PM_OPEN + PM_COLS * PM_ROWS
GLYPHS = PM_CLOSED + PM_COLS * PM_ROWS
MOUTH_DEG = 38                          # half angle of the open mouth, mouth to the right

F5 = {
    ' ': '00000/00000/00000/00000/00000/00000/00000',
    'A': '01110/10001/10001/11111/10001/10001/10001', 'B': '11110/10001/10001/11110/10001/10001/11110',
    'C': '01110/10001/10000/10000/10000/10001/01110', 'D': '11110/10001/10001/10001/10001/10001/11110',
    'E': '11111/10000/10000/11110/10000/10000/11111', 'F': '11111/10000/10000/11110/10000/10000/10000',
    'G': '01110/10001/10000/10111/10001/10001/01111', 'H': '10001/10001/10001/11111/10001/10001/10001',
    'I': '01110/00100/00100/00100/00100/00100/01110', 'J': '00111/00010/00010/00010/00010/10010/01100',
    'K': '10001/10010/10100/11000/10100/10010/10001', 'L': '10000/10000/10000/10000/10000/10000/11111',
    'M': '10001/11011/10101/10101/10001/10001/10001', 'N': '10001/11001/10101/10011/10001/10001/10001',
    'O': '01110/10001/10001/10001/10001/10001/01110', 'P': '11110/10001/10001/11110/10000/10000/10000',
    'Q': '01110/10001/10001/10001/10101/10010/01101', 'R': '11110/10001/10001/11110/10100/10010/10001',
    'S': '01111/10000/10000/01110/00001/00001/11110', 'T': '11111/00100/00100/00100/00100/00100/00100',
    'U': '10001/10001/10001/10001/10001/10001/01110', 'V': '10001/10001/10001/10001/10001/01010/00100',
    'W': '10001/10001/10001/10101/10101/10101/01010', 'X': '10001/10001/01010/00100/01010/10001/10001',
    'Y': '10001/10001/01010/00100/00100/00100/00100', 'Z': '11111/00001/00010/00100/01000/10000/11111',
    '0': '01110/10001/10011/10101/11001/10001/01110', '1': '00100/01100/00100/00100/00100/00100/01110',
    '2': '01110/10001/00001/00010/00100/01000/11111', '3': '11110/00001/00001/01110/00001/00001/11110',
    '4': '00010/00110/01010/10010/11111/00010/00010', '5': '11111/10000/11110/00001/00001/10001/01110',
    '6': '00110/01000/10000/11110/10001/10001/01110', '7': '11111/00001/00010/00100/01000/01000/01000',
    '8': '01110/10001/10001/01110/10001/10001/01110', '9': '01110/10001/10001/01111/00001/00010/01100',
    '%': '11000/11001/00010/00100/01000/10011/00011', '.': '00000/00000/00000/00000/00000/01100/01100',
    '/': '00001/00001/00010/00100/01000/10000/10000', ':': '00000/01100/01100/00000/01100/01100/00000',
    '-': '00000/00000/00000/11111/00000/00000/00000',
}


def blank():
    return [[0] * TILE_W for _ in range(TILE_H)]


def char_glyph(ch):
    """5 x 7 drawn 2 x: 10 x 14 px at x 1, y 2 of the 12 x 18 tile."""
    g = blank()
    for r, row in enumerate(F5[ch].split("/")):
        for c, v in enumerate(row):
            if v == "1":
                for dy in (0, 1):
                    for dx in (0, 1):
                        g[2 + 2 * r + dy][1 + 2 * c + dx] = 1
    return g


def pac_pixels(open_):
    """72 x 72 disc, mouth to the right when open."""
    n = PM_COLS * TILE_W
    img = [[0] * n for _ in range(PM_ROWS * TILE_H)]
    r = n / 2 - 1
    ang = math.radians(MOUTH_DEG)
    for y in range(len(img)):
        for x in range(n):
            dx, dy = x + .5 - n / 2, y + .5 - n / 2
            if dx * dx + dy * dy <= r * r and not (open_ and abs(math.atan2(dy, dx)) < ang):
                img[y][x] = 1
    return img


def pac_tiles(open_):
    img = pac_pixels(open_)
    tiles = []
    for tr in range(PM_ROWS):
        for tc in range(PM_COLS):
            tiles.append([row[tc * TILE_W:(tc + 1) * TILE_W] for row in img[tr * TILE_H:(tr + 1) * TILE_H]])
    return tiles


def glyph_list():
    out = [G.pack(char_glyph(ch), 1) for ch in FONT_CHARS]
    out += [G.pack(t, 1) for t in pac_tiles(True)]
    out += [G.pack(t, 1) for t in pac_tiles(False)]
    assert len(out) == GLYPHS
    return out


def ids(text):
    return [FONT_CHARS.find(ch) if ch in FONT_CHARS else 0 for ch in text.ljust(COLS)[:COLS]]     # a character the font lacks shows blank: text never stops the screen


def text() -> str:
    gl = glyph_list()
    rows = [("    " + ", ".join(f"0x{b:02X}" for b in g)) for g in gl]
    t = ", ".join(str(i) for i in ids(TITLE) + ids(TITLE_SPLASH.center(COLS)))
    return ("/* Generated by scripts/gen_flash_screen.py: do not edit. Glyph ids: font chars 0.., Pac-Man open frame from PM_OPEN, closed from PM_CLOSED (24 tiles each). */\n"
            f"#define AWTO_FS_COLS {COLS}\n#define AWTO_FS_ROWS {ROWS}\n#define AWTO_FS_PM_COLS {PM_COLS}\n#define AWTO_FS_PM_ROWS {PM_ROWS}\n"
            f"#define AWTO_FS_PM_COL0 {PM_COL0}\n#define AWTO_FS_PM_ROW0 {PM_ROW0}\n#define AWTO_FS_ROW_TITLE {ROW_TITLE}\n"
            f"#define AWTO_FS_PM_OPEN {PM_OPEN}\n#define AWTO_FS_PM_CLOSED {PM_CLOSED}\n#define AWTO_FS_GLYPHS {GLYPHS}\n#define AWTO_FS_GLYPH_BYTES 27\n"
            "#pragma place bank(11)                      // data and its readers (FsByte, FsTitle) share the bank\n"
            f"static const __code BYTE g_aucFsGlyph[AWTO_FS_GLYPHS * AWTO_FS_GLYPH_BYTES] = {{\n" + ",\n".join(rows) + "};\n"
            "#pragma place bank(11)\n"
            f"static const __code BYTE g_aucFsTitle[2 * AWTO_FS_COLS] = {{{t}}};\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    new = text()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if a.check:
        ok = OUT.exists() and OUT.read_text() == new
        print(f"{isostamp.now()} {OUT.name}: {'current' if ok else 'DIFFERS'}")
        return 0 if ok else 1
    OUT.write_text(new)
    line = f"{isostamp.now()} wrote {OUT} ({GLYPHS} glyphs)"
    LOG.open("a").write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
