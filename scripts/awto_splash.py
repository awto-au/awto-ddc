#!/usr/bin/env python3
"""awto boot splash -> RTD OSD 1-bpp tiles with per-cell fg/bg colour; volatile preview over ISP.

usage: awto_splash.py plan [--svg F] [--px N] [--scale 1|2]       tile stats + preview PNG, no hardware
       awto_splash.py <bus> draw [--svg F] [--px N] [--scale 1|2]  draw on the monitor (volatile)
  --svg    design file (default docs/logo/awto-monitor-splash-colour.svg, 640x360 full-screen design)
  --px     design width in OSD pixels (default 1920 = full 4K width at --scale 2)
  --scale  OSD scale 0x3A0A[1:0] (default 2)
Leaves the MCU halted with the splash up; power-cycle or `rtd_osd.py <bus> probe` (resets) to revert.

Hardware facts (cited in docs/reversing/realtek-rtd/osd.md, sdk-rl64xx-reference.md):
- 1 bpp char word = (0x4C, glyph index 8 bit, fg[7:4]|bg[3:0]); bg index 0 = transparent -> palette 1..15.
- Glyph index is 8 bit -> at most 256 unique tiles per map.
- WIN0 uses delay2 (ADR3 B0 bit2 osd_delay_sel) at the top-left; the tile map uses delay1, centred.
Log: ./tmp/logs/awto_splash.log. Preview: ./tmp/awto_splash_preview.png
"""
import io, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import SRAM_WIN, SRAM_FONT, FRAME_BASE, WIN_BASE, WORDS_PER_GLYPH
import rtd_tech_osd as T

CELL_W, CELL_H = 12, 18
CW_BYTE0 = 0x4C
PAL = {1: (0xFF, 0xFF, 0xFF), 2: (0xE3, 0x06, 0x13), 3: (0x00, 0x00, 0x00)}   # from the SVG fills
BG_IDX = 1
MAX_GLYPHS = 256
SRAM_WORDS = 12288                       # RL6449 OSD SRAM [SDK RL6449_OSD_Gen_Option.h]
SCREEN = (3840, 2160)


def render(svg: Path, px: int):
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(url=str(svg), output_width=px)
    return Image.open(io.BytesIO(png)).convert("RGB")


def quantise(im):
    """-> 2D list of palette indices (nearest colour)."""
    w, h = im.size
    px = im.load()
    def near(c):
        if max(c) - min(c) < 60:                         # grey AA edge: black/white, never red
            return 3 if sum(c) < 384 else 1
        return min(PAL, key=lambda k: sum((a - b) ** 2 for a, b in zip(c, PAL[k])))
    cache = {}
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            c = px[x, y]
            if c not in cache:
                cache[c] = near(c)
            row.append(cache[c])
        out.append(row)
    return out


def crop_to_cells(q):
    """Crop to the non-background bbox, pad to whole cells (centred). -> (grid, cols, rows)."""
    h, w = len(q), len(q[0])
    ys = [y for y in range(h) if any(v != BG_IDX for v in q[y])]
    xs = [x for x in range(w) if any(q[y][x] != BG_IDX for y in ys)]
    x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    cols = -(-(x1 - x0) // CELL_W); rows = -(-(y1 - y0) // CELL_H)
    px0 = x0 - (cols * CELL_W - (x1 - x0)) // 2
    py0 = y0 - (rows * CELL_H - (y1 - y0)) // 2
    def at(x, y):
        return q[y][x] if 0 <= x < w and 0 <= y < h else BG_IDX
    grid = [[at(px0 + x, py0 + y) for x in range(cols * CELL_W)] for y in range(rows * CELL_H)]
    return grid, cols, rows


def tile(grid, cols, rows):
    """-> glyphs (list of 18 12-bit rows; glyph 0 blank), cells[r][c] = (glyph, fg, bg)."""
    glyphs, index = [[0] * CELL_H], {tuple([0] * CELL_H): 0}
    full = (1 << CELL_W) - 1
    cells = []
    for r in range(rows):
        crow = []
        for c in range(cols):
            pix = [grid[r * CELL_H + y][c * CELL_W:(c + 1) * CELL_W] for y in range(CELL_H)]
            counts = {}
            for line in pix:
                for v in line:
                    counts[v] = counts.get(v, 0) + 1
            order = sorted(counts, key=lambda k: -counts[k])
            bg = order[0]; fg = order[1] if len(order) > 1 else order[0]
            bits = []
            for line in pix:          # a rare 3rd colour (edge AA) falls to bg
                b = 0
                for k, v in enumerate(line):
                    if v == fg and fg != bg:
                        b |= 1 << (CELL_W - 1 - k)
                bits.append(b)
            key, inv = tuple(bits), tuple(full ^ b for b in bits)
            if key in index:
                crow.append((index[key], fg, bg))
            elif inv in index:
                crow.append((index[inv], bg, fg))
            else:
                index[key] = len(glyphs); glyphs.append(bits)
                crow.append((index[key], fg, bg))
        cells.append(crow)
    return glyphs, cells


def glyph_words(bits):
    out = []
    for k in range(WORDS_PER_GLYPH):
        w = (bits[2 * k] << 12) | bits[2 * k + 1]
        out.append((w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF))
    return out


def preview(glyphs, cells, path: Path):
    from PIL import Image
    rows, cols = len(cells), len(cells[0])
    im = Image.new("RGB", (cols * CELL_W, rows * CELL_H))
    px = im.load()
    for r, crow in enumerate(cells):
        for c, (g, fg, bg) in enumerate(crow):
            for y in range(CELL_H):
                for x in range(CELL_W):
                    on = glyphs[g][y] >> (CELL_W - 1 - x) & 1
                    px[c * CELL_W + x, r * CELL_H + y] = PAL[fg if on else bg]
    im.save(path)


def build(svg, px):
    q = quantise(render(svg, px))
    grid, cols, rows = crop_to_cells(q)
    glyphs, cells = tile(grid, cols, rows)
    return glyphs, cells, cols, rows


def layout(cols, rows, n_glyphs):
    map_words = rows + 1 + rows * cols
    font_base = (map_words + 15) & ~15
    ok = (n_glyphs <= MAX_GLYPHS and cols <= 255 and font_base <= 0xFFF
          and font_base + n_glyphs * WORDS_PER_GLYPH <= SRAM_WORDS)
    return map_words, font_base, ok


def draw(bus, glyphs, cells, cols, rows, scale):
    _, font_base, ok = layout(cols, rows, len(glyphs))
    assert ok, "splash does not fit OSD SRAM / glyph limits"
    t = T.TechOsd(bus)
    o = t.o
    t.enter()
    for i, rgb in PAL.items():
        o.set_color(i, *rgb)
    o.wr(0x0093, 0x00)                                   # db_enable off
    o.rmw(0x01DC, 0x08, 0x08)                            # osd_clken
    o.rmw(0x006C, 0x01, 0x01)                            # overlay_port_en
    o.rmw(FRAME_BASE + 0x0A, 0x03, 0x03 if scale == 2 else 0)
    o.set_opt(SRAM_FONT)
    for gi, bits in enumerate(glyphs):
        for k, wd in enumerate(glyph_words(bits)):
            o.write_word(font_base + gi * WORDS_PER_GLYPH + k, *wd)
    for r in range(rows):
        o.write_word(r, 0x80, CELL_H - 1, cols)
    o.write_word(rows, 0, 0, 0)
    fs = rows + 1
    for r, crow in enumerate(cells):
        for c, (g, fg, bg) in enumerate(crow):
            o.write_word(fs + r * cols + c, CW_BYTE0, g, (fg << 4) | bg)
    o.wr(FRAME_BASE + 0x0C, fs & 0xFF)
    o.rmw(FRAME_BASE + 0x0D, 0xF0, ((fs >> 8) & 0xF) << 4)
    o.rmw(FRAME_BASE + 0x0D, 0x0F, font_base & 0xF)
    o.wr(FRAME_BASE + 0x0E, font_base >> 4)
    # WIN0 = full-screen background on delay2 (top-left); window units are pre-scale OSD px
    o.set_opt(SRAM_WIN)
    ww, wh = SCREEN[0] // scale, SCREEN[1] // scale
    o.write_word(WIN_BASE + 0, 0, 0, 0)
    o.write_word(WIN_BASE + 1, 0, 0, 0)
    o.write_word(WIN_BASE + 2, ((ww >> 8) & 15) << 4 | ((wh >> 8) & 15), ww & 255, wh & 255)
    o.write_word(WIN_BASE + 3, (BG_IDX & 0x20) | 0x04, BG_IDX & 0x1F, 0x01)   # osd_delay_sel=1, win_en
    o.wr(FRAME_BASE + 0x03, 0)                           # vert_delay2 = 0
    o.wr(FRAME_BASE + 0x04, 0)                           # hori_delay2[9:2]
    o.rmw(FRAME_BASE + 0x05, 0xF8, 0x02 << 6)            # hori_delay2 = 2 (regdb minimum), vert[2:0]=0
    t.set_origin((SCREEN[0] - cols * CELL_W * scale) // 2, (SCREEN[1] - rows * CELL_H * scale) // 2)
    o.set_opt(SRAM_WIN)
    o.osd_enable(True)
    P.log(f"splash drawn: {cols}x{rows} cells, {len(glyphs)} glyphs, font_base 0x{font_base:x}, scale {scale}")


def main():
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "awto_splash.log").open("a")
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    svg = Path(opt("--svg", root / "docs/logo/awto-monitor-splash-colour.svg"))
    px = int(opt("--px", 1920)); scale = int(opt("--scale", 2))
    glyphs, cells, cols, rows = build(svg, px)
    mw, fb, ok = layout(cols, rows, len(glyphs))
    prev = root / "tmp" / "awto_splash_preview.png"
    preview(glyphs, cells, prev)
    P.log(f"{svg.name} px={px} scale={scale}: {cols}x{rows} cells, {len(glyphs)} unique glyphs "
          f"(max {MAX_GLYPHS}), map {mw} words, font_base 0x{fb:x}, fits={ok}; preview {prev}")
    if a[0] == "plan":
        return 0 if ok else 1
    bus = int(a[0])
    if not ok:
        P.log("refusing to draw: does not fit"); return 1
    draw(bus, glyphs, cells, cols, rows, scale)
    P.log("OSD left up, MCU halted. Power-cycle or rtd_osd.py <bus> probe (resets) to revert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
