#!/usr/bin/env python3
"""OSD feature demos: a register / SRAM image per feature, rendered by osd_model (no firmware, no hardware).

API (also used by scripts/osd_manual.py and osd_conform.py):
  Img()                       register + SRAM image builder -> .state() (OsdState), .render(W, H, bg, opt) -> RGB array
  DEMOS                       {name: Demo(name, feature, caption, tag, build)}; build() -> Img
  render_png(img, path, ...)  one PNG (bg = grey | bars | checker | black | white), optional crop box and integer upscale
CLI: osd_demo.py [NAME ...] [--out DIR] [--list]   (default out tmp/osd_demo/)
Tags: hw = behaviour measured on a unit; databook = regdb text; spec-model = most literal reading, see docs/osd/sim-coverage.md.
Log: ./tmp/logs/osd_demo.log
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import osd_model as M  # noqa: E402
import osd_gfx as G  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/osd_demo.log"
DW, DH = 640, 360                                  # demo canvas (model coordinates are absolute px, so a small canvas renders the same pixels)
PAL16 = [(0, 0, 0), (255, 255, 255), (224, 32, 32), (32, 192, 32), (48, 80, 255), (255, 224, 0), (0, 200, 200), (224, 0, 224),
         (128, 128, 128), (255, 128, 0), (128, 0, 255), (0, 128, 64), (96, 48, 16), (255, 160, 192), (160, 224, 255), (64, 64, 64)]
FS_BASE, ROW_BASE, FONT_BASE = 0x020, 0x000, 0x200     # map chars / row commands / glyph store (font SRAM words)
BAR, SOLID = 1, 2                                   # glyph ids of the demo font: 0 blank, 1 box outline, 2 solid, 3.. letters


def box_rows(kind: str) -> list[list[int]]:
    """18 rows x 12 px of a demo glyph: box (outline), solid, plus, ramp (diagonal), dots."""
    r = [[0] * 12 for _ in range(18)]
    for y in range(18):
        for x in range(12):
            if kind == "solid":
                r[y][x] = 1
            elif kind == "box":
                r[y][x] = int(y in (0, 17) or x in (0, 11))
            elif kind == "plus":
                r[y][x] = int(x in (5, 6) or y in (8, 9))
            elif kind == "ramp":
                r[y][x] = int(x * 18 // 12 <= y)
            elif kind == "dots":
                r[y][x] = int((x + y) % 4 == 0)
    return r


class Img:
    """Register image: frame registers 0x3A00..0x3AFF, window SRAM, font SRAM, palette, overlay port. Defaults: OSD on, step 1 px, 640x360 canvas."""

    def __init__(self):
        self.regs = bytearray(0x100)
        self.win: dict = {}
        self.font: dict = {}
        self.pal = list(PAL16) + [(4 * i, 255 - 4 * i, 128) for i in range(48)]
        self.ovl = [0x01, 0x00]
        self.pg = bytearray(16)
        self.nfont = 0
        self.rowcmds: list = []
        self.chars: list = []
        self.reg(0x02, 0x01)
        self.reg(0x06, 0x10)
        self.reg(0x19, ROW_BASE)
        self.reg(0x0C, FS_BASE & 255)
        self.reg(0x0D, (FS_BASE >> 8) << 4 | FONT_BASE & 15)
        self.reg(0x0E, FONT_BASE >> 4 & 255)
        for g, k in enumerate(("blank", "box", "solid", "plus", "ramp", "dots")):
            self.glyph(g, box_rows(k) if k != "blank" else [[0] * 12 for _ in range(18)])

    # -- registers
    def reg(self, a: int, v: int, mask: int = 0xFF):
        a &= 0xFF
        self.regs[a] = (self.regs[a] & ~mask & 0xFF) | (v & mask)
        return self

    def place(self, x: int, y: int, font=(0, 0)):
        """First OSD origin (x px, y lines; step 1 px) and font A offset."""
        self.reg(0x01, x >> 2).reg(0x02, (x & 3) << 6, 0xC0).reg(0x06, x >> 10 << 2, 0x0C)
        self.reg(0x00, y >> 3).reg(0x02, (y & 7) << 3, 0x38)
        self.reg(0x24, font[0] >> 8 << 4 | font[1] >> 8, 0xFF).reg(0x25, font[0] & 255).reg(0x26, font[1] & 255)
        return self

    def set_pal(self, idx, rgb):
        self.pal[idx] = tuple(rgb)
        return self

    # -- window SRAM
    def wword(self, i: int, k: int, b):
        self.win[M.win_base(i) + k] = list(b)

    def window(self, i: int, x0, y0, x1, y1, color, *, eff=None, gradient=None, blend=False, delay2=False, **extra):
        """Window i at (x0,y0)-(x1,y1) inclusive. eff = (opt 0..7, width, height, sha, bor) shadow / 3D / border; gradient = dict(dir, pol, en, step, ...)."""
        w0, w1, w2, w3 = [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]
        w1[0], w1[1], w1[2] = (x0 >> 8) << 4 | (y0 >> 8), x0 & 255, y0 & 255
        w2[0], w2[1], w2[2] = (x1 >> 8) << 4 | (y1 >> 8), x1 & 255, y1 & 255
        w3[0] = (color >> 5 & 1) << 5 | (delay2 << 2)
        w3[1] = color & 31
        w3[2] = 1 | blend << 7
        if eff:
            opt, ew, eh, sha, bor = eff
            w3[2] |= 0x10 | opt << 1
            w0[0] = (sha >> 4 & 1) << 7 | (bor >> 4 & 1) << 6 | (ew - 1) << 3 | (eh - 1)
            w0[1] = (sha & 15) << 4 | bor & 15
            w3[0] |= (sha >> 5 & 1) << 7 | (bor >> 5 & 1) << 6
        if gradient:
            g = gradient
            w3[2] |= 0x40 | g.get("dir", 0) << 5
            pol, en = g.get("pol", (1, 1, 1)), g.get("en", (1, 1, 1))
            w0[2] = pol[0] << 7 | pol[1] << 6 | pol[2] << 5 | (g.get("step", 1) - 1) << 3 | en[0] << 2 | en[1] << 1 | en[2]
        for k, w in enumerate((w0, w1, w2, w3)):
            self.wword(i, k, w)
        for n, (b0, b1, b2) in extra.items():              # raw ADRn words: adr5=(b0,b1,b2)
            self.win[M.win_adr(i, int(n[3:]))] = [b0, b1, b2]
        return self

    # -- font SRAM
    def glyph(self, gid: int, rows, plane: int = 0):
        """1-bit glyph gid (18 rows x 12 px lists)."""
        by = G.pack_rows(rows)
        for w in range(9):
            self.font[FONT_BASE + 9 * gid + w] = list(by[3 * w:3 * w + 3])

    def glyph_n(self, base_unit: int, nplanes: int, gid: int, planes_rows, lsb_first: bool):
        """Multi-plane glyph at FONT_BASE + unit * (gid) with plane order per the 2-bit hardware result (plane A = low bit)."""
        for k, rows in enumerate(planes_rows):
            by = G.pack_rows(rows)
            for w in range(9):
                self.font[FONT_BASE + base_unit * gid + 9 * k + w] = list(by[3 * w:3 * w + 3])

    def map(self, rows, base: int = ROW_BASE, fs: int = FS_BASE):
        """rows = list of (height, [char words as [b0,b1,b2]]). Writes row commands + char words."""
        a, ca = base, fs
        for h, chars in rows:
            self.font[a] = [0x80, h - 1, len(chars)]
            a += 1
            for c in chars:
                self.font[ca] = list(c)
                ca += 1
        return self

    @staticmethod
    def c1(gid: int, fg: int = 1, bg: int = 0, width: int = 12):
        return [0x40 | (gid >> 8) << 5 | width & 31, gid & 255, fg << 4 | bg]

    @staticmethod
    def c2(gid: int, cols: tuple):
        c0, c1, c2, c3 = cols
        return [0x80 | (c0 >> 3 & 1) << 5 | (c1 >> 3 & 1) << 4 | c3 << 1 | (c0 >> 2 & 1), gid, (c0 & 3) << 6 | c2 << 3 | c1 & 7]

    @staticmethod
    def blank(w: int, bg: int = 0):
        return [0x00, w, bg]

    @staticmethod
    def c4(gid: int, bg: int = 0):
        return [0xC0 | bg & 0x3F, gid, 0]

    def text_boxes(self, rows: int, cols: int, fg: int = 1, bg: int = 0, kinds=(1, 2, 3, 4, 5), h: int = 18):
        """rows x cols of demo glyphs (cycled)."""
        return self.map([(h, [self.c1(kinds[(r + c) % len(kinds)], fg, bg) for c in range(cols)]) for r in range(rows)])

    # -- output
    def state(self) -> M.OsdState:
        return M.OsdState({k: list(v) for k, v in self.win.items()}, {k: list(v) for k, v in self.font.items()}, list(self.pal),
                          bytes(self.regs), tuple(self.ovl), 0.0, 0, bytes(self.pg))

    def render(self, W: int = DW, H: int = DH, bg: str = "bars", opt=None, opaque: bool = False) -> np.ndarray:
        return M.render(self.state(), W, H, bg=background(bg, W, H), alpha_opaque=opaque, opt=opt)


def background(kind: str, W: int, H: int) -> np.ndarray:
    """Picture under the OSD: bars (75 % colour bars over a ramp), checker, or a flat colour."""
    if kind == "checker":
        yy, xx = np.mgrid[0:H, 0:W]
        return np.repeat((((yy // 20) + (xx // 20)) % 2 * 40 + 100).astype(np.uint8)[:, :, None], 3, axis=2)
    if kind == "bars":
        img = np.empty((H, W, 3), np.uint8)
        cols = [(191, 191, 191), (191, 191, 0), (0, 191, 191), (0, 191, 0), (191, 0, 191), (191, 0, 0), (0, 0, 191)]
        for i, c in enumerate(cols):
            img[:H * 2 // 3, i * W // 7:(i + 1) * W // 7] = c
        img[H * 2 // 3:] = np.linspace(0, 255, W, dtype=np.float32).astype(np.uint8)[None, :, None]
        return img
    return np.full((H, W, 3), {"grey": 128, "black": 0, "white": 255}[kind], np.uint8)


def render_png(img: Img, path: Path, bg: str = "grey", crop=None, up: int = 1, W: int = DW, H: int = DH, opt=None):
    from PIL import Image
    a = img.render(W, H, bg, opt)
    if crop:
        x0, y0, x1, y1 = crop
        a = a[y0:y1, x0:x1]
    im = Image.fromarray(a)
    if up > 1:
        im = im.resize((im.width * up, im.height * up), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


@dataclass
class Demo:
    name: str
    feature: str                                  # id in docs/osd/sim-coverage.tsv
    caption: str
    tag: str                                      # hw | databook | spec-model
    build: Callable[[], Img]
    bg: str = "grey"
    crop: tuple | None = None


DEMOS: dict[str, Demo] = {}


def demo(name: str, feature: str, caption: str, tag: str, bg: str = "grey", crop=None):
    def deco(fn):
        DEMOS[name] = Demo(name, feature, caption, tag, fn, bg, crop)
        return fn
    return deco


# --- demos ---------------------------------------------------------------------------------------------------------------
@demo("window_flat", "win_basic", "Window 0: flat colour 2, (40,30)-(199,119).", "databook")
def _(): return Img().window(0, 40, 30, 199, 119, 2)


@demo("window_blend", "blend_alpha", "Alpha blending type 01 (windows only), level 128/256: window 0 over colour bars [direction of the level: spec-model].", "spec-model", bg="bars")
def _():
    i = Img().window(0, 40, 30, 299, 219, 2, blend=True)
    i.reg(0x0A, 0x04, 0x0C)
    i.ovl[0] |= 0x08
    return i


@demo("window_gradient", "win_gradient", "Window gradient, horizontal, R up / B down, 2 steps per level.", "spec-model")
def _(): return Img().window(0, 40, 30, 299, 119, 4, gradient=dict(dir=0, pol=(1, 1, 0), en=(1, 0, 1), step=2))


@demo("window_shadow", "win_effect", "Window effect types: shadow 1, 3D button 1, border.", "spec-model")
def _():
    i = Img()
    i.window(0, 30, 30, 129, 99, 3, eff=(0, 4, 4, 8, 8))
    i.window(1, 170, 30, 269, 99, 3, eff=(4, 4, 4, 1, 15))
    i.window(5, 310, 30, 409, 99, 3, eff=(7, 4, 4, 5, 5))
    return i


@demo("window_chess", "win_chessboard", "Chessboard window 8: colours 1 / 4, pixel step 8 (windows 4_x / 5_x: colours in ADR4, no step register).", "spec-model")
def _():
    i = Img().window(8, 40, 30, 199, 119, 2, adr5=(0x80, 1, 4), adr9=(0, 8, 0))
    return i


@demo("window_round", "win_round", "Rounded corners (all four), size code 01 = 16 px, pattern registers 0x3A60..8B.", "spec-model")
def _():
    i = Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 2 | 1, 0, 0))
    return i


@demo("window_grid", "win_grid", "Grid on window 2: 2 px lines, pitch from panel pitch registers.", "spec-model")
def _():
    i = Img().window(2, 40, 30, 299, 149, 4)
    i.win[0x183] = [0x40 | 5, 0xC0, 2000 & 255]                # width 2, colour 5, H + V, pitch 2000 um
    i.win[0x184] = [(2000 >> 8) << 1 | 1, 0, 0]
    i.reg(0x35, 0x11).reg(0x36, 0xF4).reg(0x37, 0xF4)           # panel pitch 500 / 4 = 125 um -> 16 px
    return i


@demo("font_1bit", "font_1bit", "1-bit characters: foreground 1 on background 4, background 0 = transparent (cell 3).", "hw")
def _():
    i = Img().window(0, 20, 20, 299, 129, 8)
    i.map([(18, [i.c1(1, 1, 4), i.c1(2, 5, 0), i.c1(3, 3, 4), i.c1(4, 1, 0), i.c1(5, 2, 4)]), (18, [i.c1(5, 6, 0), i.c1(4, 1, 2), i.c1(3, 1, 0)])])
    i.place(24, 24)
    return i


@demo("font_2bit", "font_2bit", "2-bit characters: pixel value selects one of four colours, plane A = low bit [hw, unit 3 ladder].", "hw", bg="bars")
def _():
    i = Img()
    a = [[(x // 3) % 2 for x in range(12)] for _ in range(18)]
    b = [[(y // 3) % 2 for _ in range(12)] for y in range(18)]
    i.reg(0x21, 0x00, 0x03).reg(0x22, 0)
    i.glyph_n(18, 2, 0, [a, b], True)
    i.map([(18, [i.c2(0, (2, 3, 4, 5)), i.c2(0, (6, 7, 9, 10))])])
    return i.place(24, 24)


@demo("font_width", "font_width", "Narrow 1-bit characters (width 6 and 8), zone middle / left / right.", "databook")
def _():
    i = Img()
    i.map([(18, [i.c1(2, 1, 4, 6), i.c1(2, 1, 4, 8), i.c1(1, 1, 4, 12)])])
    return i.place(24, 24).reg(0x02, 0x02, 0x06)


@demo("font_blank", "font_blank", "Blank cells: 20 px wide, background colour 2 and 4.", "databook")
def _():
    i = Img()
    i.map([(18, [i.blank(20, 2), i.c1(1, 1, 0), i.blank(20, 4)])])
    return i.place(24, 24)


@demo("double_size", "db_size", "Double width + double height: every window and character doubled.", "hw")
def _():
    i = Img().window(0, 10, 10, 129, 79, 2)
    i.map([(18, [i.c1(1, 1, 4), i.c1(2, 1, 4)])])
    return i.place(12, 12).reg(0x0A, 0x03, 0x03)


@demo("two_fonts", "font_b", "Two font maps: A at delay 1, B at delay 2.", "spec-model")
def _():
    i = Img()
    i.map([(18, [i.c1(1, 1, 4)] * 3)])
    i.reg(0x18, 0x0A, 0x0A)                                        # two fonts + font B on the second delay
    i.map([(18, [i.c1(2, 1, 4)] * 3)], base=0x08, fs=0x060)
    i.reg(0x1A, 0x08).reg(0x1B, 0x00).reg(0x1D, 0x60).reg(0x1C, FS_BASE & 255)
    i.reg(0x03, 60 >> 3).reg(0x05, (60 & 7) << 3, 0x38).reg(0x04, 40 >> 2)
    return i.place(24, 24)


@demo("highlight", "highlight", "Highlight windows 4-1 and 4-6: font colours inside the window replaced.", "databook")
def _():
    i = Img()
    i.window(10, 0, 0, 71, 17, 8).window(15, 72, 0, 143, 17, 8)
    i.map([(18, [i.c1(1, 1, 4)] * 12)]).place(24, 24)
    i.reg(0x2A, 0x40 | 2).reg(0x2B, 3)
    i.reg(0x51, 0x40 | 6).reg(0x52, 7)
    return i


@demo("palette", "palette", "64-colour LUT: 16 solid cells for the first 16 entries.", "hw")
def _():
    i = Img()
    i.map([(18, [i.blank(12, c) for c in range(1, 16)])]).place(10, 10)
    return i


@demo("scale_up", "scale_up", "Scale-up engine 150 % (factor 42): output = 64 / factor x the OSD.", "spec-model")
def _():
    i = Img().window(0, 10, 10, 99, 59, 2)
    i.map([(18, [i.c1(1, 1, 4), i.c1(2, 5, 4)])]).place(12, 12)
    i.reg(0xC0, 0x80).reg(0xC2, 42).reg(0xC3, 42)
    return i


@demo("font_mask", "font_mask", "Font A mask region: rows 1..1, columns 2..3 not drawn.", "spec-model")
def _():
    i = Img().window(0, 10, 10, 129, 79, 8)
    i.text_boxes(3, 6, 1, 4).place(12, 12)
    i.reg(0x45, 0x80 | 1).reg(0x46, 1).reg(0x49, 2).reg(0x4A, 3)
    return i


@demo("pattern_gen", "disp_pg", "Display pattern generator (page 7): red incremental per pixel step (4 px), green toggled per line step (8 lines), blue inverted.", "spec-model")
def _():
    i = Img()
    i.reg(0x02, 0x00)
    for a, v in ((0xF0, 0x81), (0xF1, 0x88), (0xF2, 0x20), (0xF6, 0x08), (0xF7, 0x08), (0xF8, 0x04), (0xF9, 0x08)):
        i.pg[a - 0xF0] = v
    return i


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    import isostamp
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/osd_demo")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for d in DEMOS.values():
            print(f"{d.name}\t{d.feature}\t{d.tag}\t{d.caption}")
        return 0
    for n in a.names or DEMOS:
        d = DEMOS[n]
        p = render_png(d.build(), a.out / f"{n}.png", d.bg, d.crop, 2)
        say(f"{n} [{d.tag}] -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
