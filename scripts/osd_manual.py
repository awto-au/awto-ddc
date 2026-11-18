#!/usr/bin/env python3
"""Sim captures for the OSD manual (docs/osd/): one small labelled demo per feature -> docs/osd/img/<feature>.png.

usage: python scripts/osd_manual.py [--only ID ...] [--check] [--list]
  default  render every modelled feature into docs/osd/img/
  --check  regenerate in memory, compare the decoded pixels with the committed PNGs, exit 1 on a difference / missing / stray file
           (pixels, not file bytes: the PNG encoder / zlib version may differ between hosts)
  --list   id, status, registers of every feature (modelled or not: modelled = has a function in FEATURES)
Log: tmp/logs/osd_manual.log. Deterministic: no clock, no random, no firmware run; own glyphs only (Spleen 5x8, fw/rtdfw/awto/osd).
Thin layer over scripts/osd_model.py: a feature = one function returning a Scene; a new model feature = one function + one FEATURES row.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import isostamp  # noqa: E402
import osd_model as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs/osd/img"
LOG = ROOT / "tmp/logs/osd_manual.log"
W, H, K = 192, 108, 3                      # demo canvas (panel px at 1x) and the PNG upscale
CAP_H = 14                                 # caption strip height (PNG px)
GW, GH = M.GW, M.GH
BG_DARK, BG_LIGHT = 70, 120                # checker background levels (so blending shows)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


# --- own text: Spleen 5x8 (BSD, committed in fw/rtdfw/awto/osd) ------------------------------------------------------
_SP: dict[str, list[int]] = {}


def spleen(ch: str) -> list[int]:
    if not _SP:
        for ln in (ROOT / "fw/rtdfw/awto/osd/spleen-5x8.hex").read_text().splitlines():
            if ln and not ln.startswith("#"):
                cp, hx = ln.split(":")
                _SP[chr(int(cp, 16))] = list(bytes.fromhex(hx))
    return _SP.get(ch, _SP["?"])


def caption(s: str, width: int) -> np.ndarray:
    out = np.empty((CAP_H, width, 3), np.uint8)
    out[:] = (24, 24, 32)
    for k, ch in enumerate(s):
        for y, row in enumerate(spleen(ch)):
            for x in range(5):
                px = 4 + 6 * k + x
                if row >> (7 - x) & 1 and px < width:
                    out[3 + y, px] = (255, 255, 255)
    return out


def words_of(rows) -> list[list[int]]:
    """18 rows of 12-bit ints (MSB left) -> 9 words [B0, B1, B2] (osd_model.tile order)."""
    out = []
    for w in range(9):
        v = rows[2 * w] << 12 | rows[2 * w + 1]
        out.append([v & 255, v >> 8 & 255, v >> 16 & 255])
    return out


def spleen_rows(ch: str) -> list[int]:
    """Spleen 5x8 doubled to 10 x 16 inside the 12 x 18 cell (1 px margin)."""
    rows = [0] * GH
    for y, row in enumerate(spleen(ch)):
        bits = 0
        for x in range(5):
            if row >> (7 - x) & 1:
                bits |= 3 << (12 - 2 * (x + 1))
        rows[1 + 2 * y] = rows[2 + 2 * y] = bits >> 1
    return rows


def turned(rows: list[int]) -> list[int]:
    """Glyph turned 180 inside the cell (osd_rot.c): rows reversed, each row bit-reversed over 12 bits."""
    return [int(f"{r:012b}"[::-1], 2) for r in rows[::-1]]


def pack2(c0, c1, c2, c3):
    """2-bit char colours -> (B0, B2) (SDK OsdFontPut2Bit packing as read by osd_model.decode_char)."""
    return 0x80 | ((c0 & 8) << 2) | ((c1 & 8) << 1) | ((c3 & 7) << 1) | ((c0 & 4) >> 2), ((c0 & 3) << 6) | ((c2 & 7) << 3) | (c1 & 7)


# --- scene -----------------------------------------------------------------------------------------------------------------
class Scene:
    def __init__(self, title: str, tag: str):
        self.title, self.tag = title, tag
        self.regs = bytearray(256)
        self.st = M.OsdState()
        self.st.pal = [(0, 0, 0)] * 64
        self.ovl = [1, 0]                                     # 0x6C[0] overlay port on, alpha level 0 = opaque
        self.regs[0x02] = 1                                   # osd_en; delay 0 = origin at the canvas corner
        self.ids: dict = {}
        self.gbase = 0
        self.pg = bytearray(16)                               # page 7 0x07F0.. pattern generator
        base = {0: (0, 0, 0), 1: (255, 255, 255), 2: (220, 40, 40), 3: (40, 200, 60), 4: (50, 90, 230), 5: (240, 200, 30),
                6: (40, 200, 220), 7: (200, 60, 200), 8: (128, 128, 128), 9: (255, 140, 0), 10: (10, 10, 60), 11: (250, 250, 160)}
        for i in range(12, 64):
            base[i] = (i * 4 % 256, i * 11 % 256, 255 - i * 4 % 256)
        for i, c in base.items():
            self.st.pal[i] = c

    def r(self, off: int, v: int) -> "Scene":
        self.regs[off] = v & 255
        return self

    def alpha(self, level: int, typ: int) -> "Scene":
        self.ovl = [1 | (level >> 5) << 2, (level & 31) << 3]
        self.regs[0x0A] = self.regs[0x0A] & ~0x0C | typ << 2
        return self

    def win(self, i: int, x0: int, y0: int, x1: int, y1: int, color: int, blend: int = 0, eff=None, grad=None, extra=None) -> "Scene":
        """eff = (opt, width, height, sha, bor); grad = dict(dir, pol, en, step); extra = {adr_no: [b0, b1, b2]}."""
        b, w = M.win_base(i), self.st.win
        w[b + 1] = [(x0 >> 8) << 4 | (y0 >> 8), x0 & 255, y0 & 255]
        w[b + 2] = [(x1 >> 8) << 4 | (y1 >> 8), x1 & 255, y1 & 255]
        a0, a3 = [0, 0, 0], [(color >> 5 & 1) << 5, color & 31, 1 | blend << 7]
        if eff:
            opt, ew, eh, sha, bor = eff
            a0[0], a0[1] = (ew - 1) << 3 | (eh - 1), (sha & 15) << 4 | (bor & 15)
            a3[2] |= 16 | opt << 1
        if grad:
            a3[2] |= 64 | grad.get("dir", 0) << 5
            a0[2] = sum(grad["pol"][j] << (7 - j) for j in range(3)) | (grad.get("step", 1) - 1) << 3 | sum(grad["en"][j] << (2 - j) for j in range(3))
        w[b], w[b + 3] = a0, a3
        for n, v in (extra or {}).items():
            w[M.win_adr(i, n)] = v
        return self

    def cells(self, s: str, fg: int = 1, bg: int = 0, width: int = GW) -> list:
        out = []
        for ch in s:
            self.ids.setdefault(ch, len(self.ids))
            out.append([0x40 | width, self.ids[ch], fg << 4 | bg])
        return out

    def map(self, rows, row_h: int = GH, row_base: int = 0, load_text: bool = True) -> "Scene":
        """Row commands from row_base, end marker, char words, then the glyph area; map A registers set."""
        n = len(rows)
        for k, row in enumerate(rows):
            self.st.font[row_base + k] = [0x80, row_h - 1, len(row)]
        self.st.font[row_base + n] = [0, 0, 0]
        fs = row_base + n + 1
        a = fs
        for row in rows:
            for cw in row:
                self.st.font[a] = list(cw)
                a += 1
        self.gbase = a
        self.regs[0x19], self.regs[0x0C] = row_base, fs & 255
        self.regs[0x0D], self.regs[0x0E], self.regs[0x17] = (fs >> 8) << 4 | a & 15, a >> 4 & 255, (a >> 12 & 7) << 3
        if load_text:
            for ch, gid in self.ids.items():
                self.glyph(gid, words_of(spleen_rows(ch)))
        return self

    def glyph(self, gid: int, words, per: int = 9) -> None:
        for k, wd in enumerate(words):
            self.st.font[self.gbase + per * gid + k] = wd

    def render(self) -> np.ndarray:
        yy, xx = np.mgrid[0:H, 0:W]
        c = np.where(((yy // 12) + (xx // 12)) % 2, BG_LIGHT, BG_DARK)
        bg = np.stack([c, c, c + 24], axis=2).astype(np.uint8)
        st = M.OsdState(self.st.win, self.st.font, self.st.pal, bytes(self.regs), tuple(self.ovl), 0.0, 0, bytes(self.pg))
        img = np.kron(M.render(st, W, H, bg=bg), np.ones((K, K, 1), np.uint8))
        return np.concatenate([img, caption(f"{self.title}  {self.tag}", img.shape[1])], axis=0)


def text(rows_txt, widths=None, fg=1, bg=0, title="", tag="", at=(10, 10), row_h=GH) -> Scene:
    s = Scene(title, tag)
    s.map([s.cells(t, fg, bg, (widths or {}).get(k, GW)) for k, t in enumerate(rows_txt)], row_h)
    s.r(0x24, at[0] >> 8).r(0x25, at[0]).r(0x26, at[1])        # font A delay (px, lines)
    return s


# --- features: one function each ----------------------------------------------------------------------------------------------
def f_text_1bit():
    s = text(["OSD 1BIT", "FG 5 BG 4", "BG 0 CLEAR"], title="1-bit chars", tag="[hw: text on unit 3]")
    for k in range(8, 17):                                    # row 1: fg 5 bg 4
        c = s.st.font[s.regs[0x0C] + k]
        c[2] = 5 << 4 | 4
    return s


def f_char_width():
    return text(["WIDTH 12", "WIDTH 8", "WIDTH 6"], {0: 12, 1: 8, 2: 6}, 1, 4, "char width B0[4:0]", "[hw: proportional text]")


def _zone(z, name):
    s = text(["MID", "LEFT", "RIGHT"][:1] * 1 and ["ZONE"], {0: 8}, 1, 4, f"disp_zone {name}", "3A02[2:1] [spec-model]")
    s.r(0x02, 1 | z << 1)
    return s


def f_zone_0():
    return _zone(0, "00 middle")


def f_zone_1():
    return _zone(1, "01 left")


def f_zone_2():
    return _zone(2, "10 right")


def f_text_2bit():
    s = Scene("2-bit chars", "[hw: plane A = bit 0]")
    cells = []
    b0, b2 = pack2(0, 2, 3, 4)
    for g in range(4):
        cells.append([b0, g, b2])
    s.map([cells, cells], load_text=False)
    for g in range(4):
        lv = [[(x // 3 + y // 3 + g) % 4 for x in range(12)] for y in range(GH)]
        for p in range(2):
            s.glyph(2 * g + p * 0, [[0, 0, 0]] * 0)
        for p in range(2):
            rows = [sum(((lv[y][x] >> p) & 1) << (11 - x) for x in range(12)) for y in range(GH)]
            for k, wd in enumerate(words_of(rows)):
                s.st.font[s.gbase + 18 * g + 9 * p + k] = wd
    s.r(0x24, 0).r(0x25, 10).r(0x26, 10)
    return s


def f_text_4bit():
    s = Scene("4-bit chars", "[sdk-hyp: planes MSB first]")
    cells = [[0xC0 | 10, g, 0] for g in range(3)]
    s.map([cells, cells], load_text=False)
    for g in range(3):
        for p in range(4):                                    # plane p = bit 3 - p of the value; value = column position + g
            rows = [sum((((x + 1 + g * 4) % 16 >> (3 - p)) & 1) << (11 - x) for x in range(12)) for y in range(GH)]
            for k, wd in enumerate(words_of(rows)):
                s.st.font[s.gbase + 36 * g + 9 * p + k] = wd
    s.r(0x24, 0).r(0x25, 10).r(0x26, 10)
    return s


def f_blank_cells():
    s = Scene("blank cells", "[sdk-hyp: blank word]")
    row = s.cells("AB") + [[0, 40, 2]] + s.cells("CD") + [[0, 24, 3]] + s.cells("E")
    s.map([row, row[:2] + [[0, 100, 4]] + row[3:5]])
    s.r(0x24, 0).r(0x25, 8).r(0x26, 10)
    return s


def f_palette():
    s = Scene("palette 0..63", "[spec: 64 x 24 bit LUT]")
    rows = [[[0, 6, k] for k in range(r * 32, r * 32 + 32)] for r in range(2)]
    s.map(rows, 18)
    return s


def f_win_solid():
    s = Scene("window solid", "[hw: boot window]")
    for k, col in enumerate((2, 3, 4, 5)):
        s.win(k, 8 + k * 44, 20, 8 + k * 44 + 36, 80, col)
    return s


def _eff(opt, title):
    s = Scene(title, f"3A eff_opt {opt} [spec-model]")
    s.win(0, 40, 24, 140, 72, 4, eff=(opt, 6, 6, 1, 2))
    return s


def f_win_shadow():
    return _eff(0, "window shadow")


def f_win_3d():
    return _eff(4, "window 3D button")


def f_win_border():
    return _eff(7, "window border")


def f_win_gradient():
    s = Scene("window gradient", "WIN0 RGB+ H [spec-model]")
    s.st.pal[12] = (0, 0, 40)
    s.win(0, 10, 10, 90, 98, 12, grad=dict(dir=0, pol=(1, 1, 1), en=(1, 1, 1), step=4))
    s.win(5, 100, 10, 180, 98, 12, grad=dict(dir=1, pol=(1, 0, 0), en=(1, 0, 0), step=4))
    return s


def f_win_gray():
    s = Scene("window gray level", "ADR9[1] [spec-model]")
    s.win(0, 20, 20, 90, 88, 2, extra={9: [0x02, 1, 0]})
    s.win(5, 100, 20, 170, 88, 2)
    return s


def f_win_round():
    s = Scene("window rounded corners", "ADR10, 3A60..8B [spec-model]")
    for k in range(4):                                          # SDK QC tables: line k = value k (visible px of the line)
        s.r(0x60 + k, (2 * k + 1) << 4 | 2 * k)
    for k in range(8):
        s.r(0x64 + k, (2 * k + 1) << 4 | 2 * k)
    for k in range(32):
        s.r(0x6C + k, k)
    s.win(0, 10, 10, 69, 69, 2, extra={10: [0x78 | 1, 0, 0]})
    s.win(5, 90, 10, 169, 69, 3, extra={10: [0x78 | 3, 0, 0]})
    s.win(10, 190, 10, 289, 89, 4, extra={10: [0x78 | 5, 0, 0]})
    return s


def f_font_mask():
    s = text(["ROW ZERO TEXT", "ROW ONE MASKED", "ROW TWO TEXT"], fg=1, bg=4, title="font mask region", tag="3A45..4C: row 1, cols 4..7 [spec-model]")
    s.r(0x45, 0x81).r(0x46, 1).r(0x49, 4).r(0x4A, 7)
    return s


def f_vertical_boundary():
    s = text(["BOUNDARY ROW A", "BOUNDARY ROW B", "BOUNDARY ROW C"], fg=1, bg=4, title="vertical boundary", tag="3A18[5], 3A1E..20: lines 20..40 [spec-model]")
    s.win(0, 4, 4, 150, 70, 2)
    s.r(0x18, 0x20).r(0x1E, 0).r(0x1F, 20).r(0x20, 40)
    return s


def f_pattern_gen():
    s = Scene("display pattern generator", "page 7 0x07F0.. [spec-model]")
    for a, v in ((0, 0x81), (1, 0x88), (2, 0x20), (6, 0x08), (7, 0x08), (8, 0x04), (9, 0x08)):
        s.pg[a] = v
    return s


def f_win_chess():
    s = Scene("window chessboard", "WIN8 ADR5/9 [spec-model]")
    s.win(8, 30, 20, 160, 88, 0, extra={5: [0x80, 2, 5], 9: [0, 8, 0]})
    return s


def f_win_grid():
    s = Scene("window grid lines", "WIN2 ADR7/8 [spec-model]")
    s.win(2, 20, 12, 172, 96, 10)
    s.st.win[0x183] = [1 << 6 | 5, 0xC0, 0xD0]                # width 2, colour 5, H + V, offset 0, pitch low byte
    s.st.win[0x184] = [7 << 1 | 1, 0, 0]                      # pitch 0x7D0 = 2000 um, grid_en
    s.r(0x35, 0x11).r(0x36, 0xF4).r(0x37, 0xF4)               # panel pitch U(9.2) 500 = 125 um per px -> 16 px
    return s


def f_win_mask_colour():
    s = Scene("special colour mask", "ADR9[2:3] [spec-model]")
    s.win(0, 20, 20, 90, 88, 2, extra={9: [0x04, 1, 0]})      # AND with the picture
    s.win(5, 100, 20, 170, 88, 5, extra={9: [0x0C, 1, 0]})    # OR with the picture
    return s


def f_win_priority():
    s = text(["WINDOW OVER", "AND UNDER"], title="window vs font", tag="3A07[0] win3 higher [spec-model]")
    s.win(3, 8, 8, 120, 30, 3)
    s.win(1, 8, 44, 120, 66, 3)
    s.r(0x07, 0x01)
    return s


def _blend(typ, name):
    s = text(["BLEND TEXT", "BG CELLS"], fg=1, bg=4, title=f"alpha type {typ}", tag=f"3A0A[3:2] {name} [spec-model]")
    s.win(0, 4, 50, 180, 100, 2, blend=1)
    s.alpha(128, typ)
    return s


def f_blend_01():
    return _blend(1, "01 windows")


def f_blend_10():
    return _blend(2, "10 all")


def f_blend_11():
    return _blend(3, "11 win+bg")


def f_highlight():
    s = text(["HIGHLIGHT", "OUTSIDE"], fg=1, bg=4, title="highlight 4_1", tag="3A2A..2B [spec-model]")
    s.win(10, 0, 8, 130, 32, 10)
    s.r(0x2A, 0x40 | 5).r(0x2B, 3)
    return s


def f_win7_mask():
    s = text(["INSIDE ONLY", "WIN 7 MASK"], fg=1, bg=4, title="window 7 mask region", tag="3A09[6:5]=10 [spec-model]")
    s.win(7, 4, 4, 100, 30, 10)
    s.r(0x09, 2 << 5)
    return s


def f_blend_colour():
    s = Scene("specific colour blend", "3A09[7], 3A08/09 idx 2 [spec-model]")
    s.win(0, 10, 20, 80, 88, 2)
    s.win(1, 100, 20, 170, 88, 3)
    s.r(0x09, 0x80 | 2).r(0x08, 0)
    s.alpha(128, 0)
    return s


def _two(popon):
    s = Scene("font B", "3A18[3] [spec-model]") if popon is None else Scene(f"pop-on base {popon}", "3A18 [spec-model]")
    ids = {}

    def cells(t, fg, bg):
        out = []
        for ch in t:
            ids.setdefault(ch, len(ids))
            out.append([0x40 | GW, ids[ch], fg << 4 | bg])
        return out
    a, b = cells("FONT A MAP", 1, 4), cells("FONT B" if popon is None else "PAGE B", 5, 2)
    s.st.font[0], s.st.font[1] = [0x80, GH - 1, len(a)], [0, 0, 0]
    s.st.font[2], s.st.font[3] = [0x80, GH - 1, len(b)], [0, 0, 0]
    fa, fb = 4, 4 + len(a)
    for k, cw in enumerate(a):
        s.st.font[fa + k] = cw
    for k, cw in enumerate(b):
        s.st.font[fb + k] = cw
    s.gbase = fb + len(b)
    for ch, gid in ids.items():
        s.glyph(gid, words_of(spleen_rows(ch)))
    s.r(0x19, 0).r(0x1A, 2).r(0x1B, (fa >> 8) << 4 | fb >> 8).r(0x1C, fa).r(0x1D, fb)
    s.r(0x0D, s.gbase & 15).r(0x0E, s.gbase >> 4).r(0x17, (s.gbase >> 12 & 7) << 3)
    if popon is None:
        s.r(0x18, 0x0A).r(0x03, 5).r(0x04, 1).r(0x05, 0x40)    # B origin delay2: hd 5 x 4 = 20 px, vd 40 lines
        s.r(0x24, 0).r(0x25, 3).r(0x26, 6)
    else:
        s.r(0x18, 0xC8 | popon)
        s.r(0x24, 0).r(0x25, 10).r(0x26, 10)
    return s


def f_font_b():
    return _two(None)


def f_pop_on_0():
    return _two(0)


def f_pop_on_1():
    return _two(1)


def f_double_size():
    s = text(["2X SIZE"], title="double size", tag="3A0A[1:0] = 3 [hw: console 2x]", at=(6, 6))
    s.win(0, 2, 2, 60, 24, 10)
    s.r(0x0A, 3)
    return s


def _su(factor, name):
    s = text(["SCALE UP", "REGION"], fg=1, bg=4, title=f"scale-up {name}", tag=f"3AC0 factor {factor} [hw: on, polarity]", at=(2, 2))
    s.win(0, 0, 0, 100, 40, 10)
    s.r(0xC0, 0x80).r(0xC2, factor).r(0xC3, factor)
    return s


def f_scale_up_2():
    return _su(32, "x2")


def f_scale_up_1p5():
    return _su(43, "x1.5")


def f_position():
    s = text(["POSITION"], title="position delay", tag="3A00..02 hd 8 vd 16 [hw]", at=(2, 2))
    s.win(0, 0, 0, 100, 24, 10)
    s.r(0x01, 8 >> 2).r(0x02, 1 | (8 & 3) << 6 | (16 & 7) << 3).r(0x00, 16 >> 3)
    return s


def f_rot180_software():
    s = Scene("software Rotate 180", "osd_rot.c [emu]")
    txt = ["ROTATE", "180 TURN"]
    rows = [s.cells(t, 1, 4) for t in txt]
    ids = s.ids
    s.map(list(reversed([list(reversed(r)) for r in rows])), load_text=False)    # map cells mirrored
    for ch, gid in ids.items():
        s.glyph(gid, words_of(turned(spleen_rows(ch))))                          # each glyph turned inside its cell
    s.r(0x24, 0).r(0x25, 10).r(0x26, 10)
    return s


# id, title, registers, status, function (None = not modelled)
FEATURES: list[tuple] = [
    ("text_1bit", "1-bit characters", "3A0C..0E, row/char words", "hw", f_text_1bit),
    ("char_width", "character width", "char B0[4:0]", "hw", f_char_width),
    ("zone_0", "display zone middle", "3A02[2:1]=00", "spec-model", f_zone_0),
    ("zone_1", "display zone left", "3A02[2:1]=01", "spec-model", f_zone_1),
    ("zone_2", "display zone right", "3A02[2:1]=10", "spec-model", f_zone_2),
    ("text_2bit", "2-bit characters", "char B0[7:6]=10, 3A21..22", "hw", f_text_2bit),
    ("text_4bit", "4-bit characters", "char B0[7:6]=11, 3A21, 3A23", "sdk-hyp", f_text_4bit),
    ("blank_cells", "blank cells", "char B0[7:6]=00", "sdk-hyp", f_blank_cells),
    ("palette", "palette", "0x6E/0x6F", "spec", f_palette),
    ("win_solid", "window solid", "WINn_ADR1..3", "hw", f_win_solid),
    ("win_shadow", "window shadow", "ADR0/3 eff_opt 0..3", "spec-model", f_win_shadow),
    ("win_3d", "window 3D button", "ADR0/3 eff_opt 4,5", "spec-model", f_win_3d),
    ("win_border", "window border", "ADR0/3 eff_opt 7", "spec-model", f_win_border),
    ("win_round", "window rounded corners", "ADR10, 3A60..8B", "spec-model", f_win_round),
    ("win_gradient", "window gradient", "ADR0/3/6/8/9", "hw", f_win_gradient),
    ("win_gray", "window gray level", "ADR9[1]", "spec-model", f_win_gray),
    ("font_mask", "font mask regions", "3A45..4C", "spec-model", f_font_mask),
    ("vertical_boundary", "vertical boundary", "3A18[5], 3A1E..20", "spec-model", f_vertical_boundary),
    ("pattern_gen", "display pattern generator", "DISP_PG_* 0x07F0..FE", "spec-model", f_pattern_gen),
    ("win_chess", "window chessboard", "ADR5/ADR9", "spec-model", f_win_chess),
    ("win_grid", "window grid lines", "WIN2..4 ADR7/8, 3A35..37", "hw", f_win_grid),
    ("win_mask_colour", "special colour mask", "ADR9[2:3]", "spec-model", f_win_mask_colour),
    ("win_priority", "window vs font priority", "3A07, 3A08", "spec-model", f_win_priority),
    ("blend_01", "alpha: windows only", "3A0A[3:2]=01, 006C, 008F", "hw", f_blend_01),
    ("blend_10", "alpha: all", "3A0A[3:2]=10", "hw", f_blend_10),
    ("blend_11", "alpha: window + char bg", "3A0A[3:2]=11", "hw", f_blend_11),
    ("win7_mask", "window 7 mask region", "3A09[6:5]", "spec-model", f_win7_mask),
    ("blend_colour", "specific colour blending", "3A08, 3A09[7,3:0]", "spec-model", f_blend_colour),
    ("highlight", "highlight windows", "3A2A..56", "spec-model", f_highlight),
    ("font_b", "font B", "3A18[3], 3A19..1D, 3A27..29", "spec-model", f_font_b),
    ("pop_on_0", "pop-on base 0", "3A18[7:6,0]", "spec-model", f_pop_on_0),
    ("pop_on_1", "pop-on base 1", "3A18[7:6,0]", "spec-model", f_pop_on_1),
    ("double_size", "double size", "3A0A[1:0]", "hw", f_double_size),
    ("scale_up_2", "scale-up x2", "3AC0..CB", "hw", f_scale_up_2),
    ("scale_up_1p5", "scale-up x1.5", "3AC0..CB", "spec-model", f_scale_up_1p5),
    ("position", "position delay", "3A00..02, 3A06", "hw", f_position),
    ("rot180_software", "software Rotate 180", "fw/osd/osd_rot.c", "hw", f_rot180_software),
]


def build(ids=None) -> dict[str, np.ndarray]:
    out = {}
    for fid, title, regs, status, fn in FEATURES:
        if ids and fid not in ids:
            continue
        s = fn() if fn else None
        if s is None:
            say(f"{fid}: not modelled (no picture)")
            continue
        out[fid] = s.render()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for fid, title, regs, status, fn in FEATURES:
            print(f"{fid}\t{status}\t{'rendered' if fn and fn() is not None else 'not modelled'}\t{regs}")
        return 0
    imgs = build(a.only)
    if a.check:
        bad = 0
        for fid, arr in imgs.items():
            p = IMG / f"{fid}.png"
            if not p.exists():
                say(f"CHECK missing {p.relative_to(ROOT)}")
                bad += 1
            elif not np.array_equal(np.asarray(Image.open(p).convert("RGB")), arr):
                say(f"CHECK differs {p.relative_to(ROOT)}")
                bad += 1
        stray = sorted(set(p.stem for p in IMG.glob("*.png")) - set(imgs)) if not a.only and IMG.exists() else []
        for f in stray:
            say(f"CHECK stray image {f}.png")
        bad += len(stray)
        say(f"CHECK {'OK' if not bad else 'FAILED'}: {len(imgs)} images, {bad} problems")
        return 1 if bad else 0
    IMG.mkdir(parents=True, exist_ok=True)
    for fid, arr in imgs.items():
        p = IMG / f"{fid}.png"
        Image.fromarray(arr).save(p, optimize=True)
        say(f"{fid}: {arr.shape[1]}x{arr.shape[0]} {p.stat().st_size} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
