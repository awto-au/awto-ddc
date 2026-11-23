#!/usr/bin/env python3
"""Build an awto boot splash for an RTD2795-class scaler: black background + a discreet mono logo,
drawn the Realtek way (OSD window + 1-bit font glyphs + palette), plus the hardware pattern-generator
proof-of-control sequence. Clean-room: encodes from the decoded OSD data format, no SDK code.

Why runtime-OSD and not a flash byte-patch (see docs/boot-logo.md):
  The firmware's Dahua splash is VLC-compressed glyph data fetched by a RUNTIME-COMPUTED banked flash
  pointer (bank6:0x4272 download, 0x3A17 VLC-decode on; descriptor bank1:0x3837). There is no fixed
  byte-slot to overwrite without resolving that pointer on hardware, so a blind flash patch risks a
  brick. This tool targets the VOLATILE OSD RAM instead (reversible by power-cycle) via rtd_osd.py,
  which is how we prove control before ever touching flash.

usage:
  make_logo.py glyphs   [--out DIR]   emit awto glyph bitmaps + a sanity render PNG (no hardware)
  make_logo.py osd-plan [--out DIR]   emit the rtd_osd.py op list that draws black-bg + awto logo
  make_logo.py patgen                 print the D-domain pattern-generator enable sequence (regs)
  make_logo.py selftest               no hardware, no files: checks the glyph encoder round-trips

Format facts used (tagged in docs/boot-logo.md): OSD window geometry 12-bit hor/ver sta/end (so a
window can cover the whole 4K panel and be placed anywhere); 64x24-bit palette; font glyphs 1/2/4 bpp;
our logo uses 1-bpp glyphs (fg index / bg index per cell) laid out as a font-select map row.
Output PNGs/sector files go to ~/vendors/realtek/analysis/logo/ (NOT git). Nothing is written to flash.
"""
import sys
from pathlib import Path

CELL_W, CELL_H = 12, 18          # OSD glyph cell [oss-understood]; matches rtd_osd.py GW/GH
WORDS_PER_GLYPH = 9              # 12x18 1-bit = 216 bits = 9 x 24-bit OSD words


# --- discreet "awto" wordmark, 5x7 pixel letters, 1px gap -> a compact mono bitmap ----------------
# Clean-room letterforms (our own), bit4 = leftmost pixel of each 5-wide row.
FONT5x7 = {
    "a": [0x00, 0x0E, 0x01, 0x0F, 0x11, 0x0F, 0x00],
    "w": [0x00, 0x11, 0x11, 0x15, 0x15, 0x0A, 0x00],
    "t": [0x04, 0x0E, 0x04, 0x04, 0x04, 0x05, 0x02],
    "o": [0x00, 0x0E, 0x11, 0x11, 0x11, 0x0E, 0x00],
    " ": [0, 0, 0, 0, 0, 0, 0],
}


def wordmark_bitmap(text="awto"):
    """Return (w, h, rows) 1-bit bitmap of the wordmark; rows are ints MSB=leftmost pixel."""
    letters = [FONT5x7[c] for c in text]
    lw, lh = 5, 7
    gap = 1
    w = len(letters) * (lw + gap) - gap
    rows = []
    for r in range(lh):
        bits = 0
        x = 0
        for li, g in enumerate(letters):
            rowbits = g[r] & 0x1F
            # place 5-bit letter at column x, MSB = leftmost
            bits |= rowbits << (w - x - lw)
            x += lw + gap
        rows.append(bits)
    return w, lh, rows


def glyph_cells(text="awto"):
    """Pack the wordmark into CELL_W x CELL_H 1-bit glyph cells (one cell per logo tile).
    The wordmark is centred in a single wide strip of N cells. Returns list of cells, each a
    list of CELL_H ints (CELL_W-bit rows, bit CELL_W-1 = leftmost)."""
    w, h, rows = wordmark_bitmap(text)
    ncells = (w + CELL_W - 1) // CELL_W
    pad_top = (CELL_H - h) // 2
    cells = []
    for c in range(ncells):
        cell = [0] * CELL_H
        for r in range(h):
            # slice CELL_W bits of this row starting at column c*CELL_W
            src = rows[r]
            start = c * CELL_W
            chunk = 0
            for k in range(CELL_W):
                col = start + k
                if col < w and (src >> (w - col - 1)) & 1:
                    chunk |= 1 << (CELL_W - k - 1)
            cell[pad_top + r] = chunk
        cells.append(cell)
    return cells


def cell_to_words(cell, pack=0):
    """Encode one CELL_W x CELL_H 1-bit cell into WORDS_PER_GLYPH 24-bit OSD words (Byte0=LSB).
    pack 0: line 2k -> bits[23:12], line 2k+1 -> bits[11:0] (matches rtd_osd.glyph_words pack 0)."""
    out = []
    for k in range(WORDS_PER_GLYPH):
        a, b = cell[2 * k], cell[2 * k + 1]
        if pack == 0:
            wv = (a << 12) | b
        elif pack == 1:
            wv = (b << 12) | a
        else:
            rev = lambda v: int(f"{v:0{CELL_W}b}"[::-1], 2)
            wv = (rev(a) << 12) | rev(b)
        out.append((wv & 0xFF, (wv >> 8) & 0xFF, (wv >> 16) & 0xFF))
    return out


def words_to_cell(words, pack=0):
    """Inverse of cell_to_words, for the selftest round-trip."""
    cell = [0] * CELL_H
    for k, (b0, b1, b2) in enumerate(words):
        wv = b0 | (b1 << 8) | (b2 << 16)
        a, b = (wv >> 12) & 0xFFF, wv & 0xFFF
        if pack == 1:
            a, b = b, a
        elif pack == 2:
            rev = lambda v: int(f"{v:0{CELL_W}b}"[::-1], 2)
            a, b = rev((wv >> 12) & 0xFFF), rev(wv & 0xFFF)
        cell[2 * k], cell[2 * k + 1] = a, b
    return cell


def sanity_png(out_dir, text="awto"):
    from PIL import Image
    cells = glyph_cells(text)
    w = len(cells) * CELL_W
    im = Image.new("L", (w, CELL_H), 0)          # black bg (our splash)
    for ci, cell in enumerate(cells):
        for r in range(CELL_H):
            for k in range(CELL_W):
                if (cell[r] >> (CELL_W - k - 1)) & 1:
                    im.putpixel((ci * CELL_W + k, r), 255)   # white logo ink on black
    p = out_dir / "awto_logo_sanity.png"
    im.resize((w * 8, CELL_H * 8), Image.NEAREST).save(p)
    return p, w, CELL_H, len(cells)


# --- OSD draw plan (volatile; feed to rtd_osd.py) -------------------------------------------------
def osd_plan(text="awto"):
    """Return a list of rtd_osd.py ops that draw black-bg + white awto logo centred on a 4K panel.
    Palette: 0 = black (bg), 1 = white (logo). Window covers the whole screen = black; the font map
    places the logo glyphs centred. Font glyphs uploaded as 1-bit cells, pack 0."""
    cells = glyph_cells(text)
    n = len(cells)
    FS_BASE, FONT_BASE = 0x000, 0x100
    ops = []
    ops.append("palette:0=000000")                       # black background
    ops.append("palette:1=FFFFFF")                       # white logo ink
    for i, cell in enumerate(cells):                     # upload glyph cells to font SRAM
        for k, (b0, b1, b2) in enumerate(cell_to_words(cell)):
            ops.append(f"osdw:font:0x{FONT_BASE + i * WORDS_PER_GLYPH + k:x}={b0:02x},{b1:02x},{b2:02x}")
    # font-select map at FS_BASE: row cmd (h,w,len) then one char word per cell (bg<<4|fg, glyphidx, 0)
    ops.append(f"osdw:font:0x{FS_BASE:x}={CELL_H:02x},{CELL_W:02x},{n:02x}")
    for i in range(n):
        ops.append(f"osdw:font:0x{FS_BASE + 1 + i:x}={(0 << 4) | 1:02x},{i:02x},00")  # bg=0 fg=1
    ops.append(f"osdw:font:0x{FS_BASE + 1 + n:x}=00,00,00")                            # terminator
    # font bases
    ops.append(f"wr:0x3A0C={FS_BASE & 0xFF:#x}")
    ops.append(f"wr:0x3A0D={(((FS_BASE >> 8) & 0xF) << 4) | (FONT_BASE & 0xF):#x}")
    ops.append(f"wr:0x3A0E={FONT_BASE >> 4:#x}")
    # WIN0 = whole panel, colour 0 (black). 4K panel 3840x2160; window geometry is 12-bit.
    ops.append("osdw:win:0x100=00,00,00")
    ops.append("osdw:win:0x101=00,00,00")                # start (0,0): B0 hi/lo nibbles=0, B1/B2=0
    # ADR2 B0=[7:4]hor_end[11:8] [3:0]ver_end[11:8], B1=hor_end[7:0], B2=ver_end[7:0]
    # end (3840,2160)=(0xF00,0x870): B0=0xF8, B1=0x00, B2=0x70
    ops.append("osdw:win:0x102=f8,00,70")                # end (3840,2160)
    ops.append("osdw:win:0x103=00,00,01")                # win_en, colour 0
    ops.append("enable")
    return ops, n


# --- hardware pattern generator (zero-art proof of display control) -------------------------------
PATGEN = """\
D-domain Pattern Generator (page 7, 0x07F0-0x07FF) [spec from regdb RTD2795T-CG].
Zero-bitmap proof that we control what the panel shows. Volatile (lost on reset); reversible.
Vertical colour bars (toggle red per pixel-step) example:
  wr 0x07F3 = 0xFF        ; DISP_PG_R_INITIAL  (red init = full-scale)
  wr 0x07F8 = 0x08        ; DISP_PG_PIXEL_STEP (step; must not be 0)
  wr 0x07F0 = 0x82        ; DISP_PG_R_CTRL: pg_enable(bit7)=1, pg_mode(bit6)=0 pattern,
                          ;   pixel_r_tog_en(bit1)=1 -> red toggles every pixel-step = vertical bars
Solid field example (pick a flat colour, no toggle/inc):
  wr 0x07F3/4/5 = init R/G/B ; wr 0x07F0 = 0x80 (enable only) ; 0x07F1=0x00 0x07F2=0x00
Disable: wr 0x07F0 = 0x00.
(I-domain generator exists too at page0 I_PG_*_M1, 0x0025 group, pg_mode 0x0025 idx98 [7:6].)
"""


def selftest():
    cells = glyph_cells("awto")
    for i, cell in enumerate(cells):
        got = words_to_cell(cell_to_words(cell, 0), 0)
        assert got == cell, f"cell {i} round-trip failed"
    w, h, rows = wordmark_bitmap("awto")
    assert len(rows) == 7 and w == 4 * 6 - 1, (w, len(rows))
    print(f"selftest OK: {len(cells)} glyph cells, wordmark {w}x{h}, {WORDS_PER_GLYPH} words/cell")
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 2
    cmd = a[0]
    out = Path(a[a.index("--out") + 1]) if "--out" in a else Path.home() / "vendors/realtek/analysis/logo"
    if cmd == "selftest":
        return selftest()
    if cmd == "patgen":
        print(PATGEN); return 0
    out.mkdir(parents=True, exist_ok=True)
    if cmd == "glyphs":
        p, w, h, n = sanity_png(out)
        print(f"wrote {p}  ({w}x{h} px, {n} glyph cells, 1-bpp)")
        cells = glyph_cells("awto")
        words = [wd for cell in cells for wd in cell_to_words(cell)]
        raw = out / "awto_glyphs.bin"
        raw.write_bytes(bytes(b for wd in words for b in wd))
        print(f"wrote {raw}  ({len(words)} OSD words = {len(words) * 3} bytes)")
        return 0
    if cmd == "osd-plan":
        ops, n = osd_plan()
        p = out / "awto_osd_plan.txt"
        p.write_text("# rtd_osd.py op list: black bg + white awto logo (volatile, power-cycle reverts)\n"
                     "# run: python scripts/rtd_osd.py <bus> --keep " + " ".join(ops) + "\n"
                     + "\n".join(ops) + "\n")
        print(f"wrote {p}  ({len(ops)} ops, {n} logo glyph cells)")
        print("run on hardware (volatile, reversible):")
        print(f"  python scripts/rtd_osd.py <bus> --keep {' '.join(ops[:3])} ...  (full list in {p})")
        return 0
    print(f"unknown command {cmd!r}"); return 2


if __name__ == "__main__":
    sys.exit(main())
