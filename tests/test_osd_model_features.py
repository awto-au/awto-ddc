"""OSD model features, one test per feature of docs/osd/sim-coverage.tsv: known register image -> expected pixels (scripts/osd_demo.py Img).
Canvas 640 x 360, black picture under the OSD, overlay opaque unless a test is about blending. Image coordinates = panel px (delay step 1 px)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import osd_demo as D  # noqa: E402
import osd_model as M  # noqa: E402

P = D.PAL16
BLACK = (0, 0, 0)


def px(img, x, y, bg="black", opt=None, W=640, H=360):
    return tuple(int(v) for v in img.render(W, H, bg, opt)[y, x])


def grid_img(img, bg="black", opt=None):
    return img.render(640, 360, bg, opt)


def test_win_basic():
    i = D.Img().window(0, 40, 30, 199, 119, 2)
    a = grid_img(i)
    assert tuple(a[30, 40]) == P[2] and tuple(a[119, 199]) == P[2]
    assert tuple(a[120, 199]) == BLACK and tuple(a[29, 40]) == BLACK and tuple(a[30, 39]) == BLACK and tuple(a[30, 200]) == BLACK


def test_win_all_indices():
    i = D.Img()
    for k in range(26):
        i.window(k, 10 + 22 * k, 10, 10 + 22 * k + 15, 20, 1 + k % 15)
    a = grid_img(i)
    for k in range(26):
        assert tuple(a[15, 18 + 22 * k]) == P[1 + k % 15], k


def test_win_colour_index_6bit():
    i = D.Img().window(0, 0, 0, 9, 9, 40)
    assert px(i, 3, 3) == i.pal[40] and M.decode_window(i.state().win, 0)["color"] == 40


def test_win_effect_colour_index():
    i = D.Img().window(0, 20, 20, 59, 49, 3, eff=(0, 3, 3, 37, 21))
    w = M.decode_window(i.state().win, 0)
    assert w["sha"] == 37 and w["bor"] == 21 and w["eff_w"] == 3 and w["eff_h"] == 3
    assert px(i, 60, 24) == i.pal[37]                                    # shadow bar right of the window
    assert px(i, 30, 50) == i.pal[37]                                    # and below


def test_win_effect_3d():
    i = D.Img().window(0, 20, 20, 59, 49, 3, eff=(4, 2, 2, 1, 15))
    assert px(i, 30, 20) == P[1] and px(i, 20, 30) == P[1]               # left / top edge = shadow colour
    assert px(i, 30, 49) == P[15] and px(i, 59, 30) == P[15]             # right / bottom edge = border colour
    assert px(i, 30, 30) == P[3]


def test_win_gradient():
    i = D.Img().window(0, 40, 30, 299, 119, 4, gradient=dict(dir=0, pol=(1, 1, 0), en=(1, 0, 1), step=2))
    assert px(i, 40, 50) == P[4]
    assert px(i, 48, 50) == (P[4][0] + 32, P[4][1], P[4][2] - 32)        # 4 levels of 8 after 8 px at 2 px per level


def test_win_gradient_vertical():
    i = D.Img().window(0, 40, 30, 299, 119, 4, gradient=dict(dir=1, pol=(0, 1, 1), en=(1, 0, 0), step=1))
    assert px(i, 100, 30) == P[4] and px(i, 100, 34)[0] == P[4][0] - 32 and px(i, 200, 34) == px(i, 100, 34)


def test_win_chessboard():
    i = D.Img().window(8, 40, 30, 199, 119, 2, adr5=(0x80, 1, 4), adr9=(0, 8, 0))           # window 8: colours at ADR5, square = ADR9 pixel step
    assert px(i, 40, 30) == P[1] and px(i, 48, 30) == P[4] and px(i, 40, 38) == P[4] and px(i, 48, 38) == P[1]
    j = D.Img().window(10, 40, 30, 199, 119, 2, adr4=(0x80, 1, 4))                           # window 4_1: colours at ADR4, no step register: 1 px squares
    assert px(j, 40, 30) == P[1] and px(j, 41, 30) == P[4] and px(j, 40, 31) == P[4]


def test_win_gray_level():
    i = D.Img().window(0, 0, 0, 9, 9, 2, adr9=(0x02, 1, 0))
    assert px(i, 3, 3) == (89, 89, 89)


def test_win_color_mask():
    for opt, want in ((0x04, (128, 0, 0)), (0x0C, (224, 160, 160))):      # AND / OR of the window colour with the picture
        i = D.Img().window(0, 0, 0, 9, 9, 2, adr9=(opt, 1, 0))
        assert px(i, 3, 3, bg="grey") == want


def test_win_round_patterns():
    i = D.Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 1, 0, 0))            # 8 x 8, all corners; pattern line k = k visible px (SDK QC ramp)
    for k, r in enumerate((0x10, 0x32, 0x54, 0x76)):
        i.reg(0x60 + k, r)
    a = grid_img(i)
    assert tuple(a[30, 40]) == BLACK and tuple(a[30, 47]) == BLACK and tuple(a[30, 48]) == P[2]
    assert tuple(a[37, 40]) == BLACK and tuple(a[37, 41]) == P[2] and tuple(a[38, 40]) == P[2]
    assert tuple(a[119, 199]) == BLACK and tuple(a[119, 192]) == BLACK and tuple(a[119, 191]) == P[2]     # lower right: line 0 = the last row


def test_win_round_size_and_circle():
    i = D.Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 2 | 1, 0, 0))        # 16, tables zero -> quarter circle
    a = grid_img(i)
    assert tuple(a[30, 40]) == BLACK and tuple(a[30 + 8, 40 + 8]) == P[2] and tuple(a[60, 40]) == P[2]
    n = D.Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 6 | 1, 0, 0))        # size code 3 reserved: square
    assert px(n, 40, 30) == P[2]
    t = D.Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 4 | 1, 0, 0))        # 32: every line visible 31 px -> 1 px cut
    for k in range(32):
        t.reg(0x6C + k, 31)
    assert px(t, 40, 30) == BLACK and px(t, 41, 30) == P[2] and px(t, 41, 31) == P[2]
    off = D.Img().window(0, 40, 30, 199, 119, 2, adr10=(0x78 | 2 | 1, 0, 0))
    assert px(off, 40, 30, opt=M.Opt(round_circle=False)) == BLACK and px(off, 55, 45, opt=M.Opt(round_circle=False)) == BLACK   # tables zero, no fallback: visible 0 = the corner square is hidden


def test_win_grid():
    i = D.DEMOS["window_grid"].build()
    assert px(i, 40, 100) == P[5] and px(i, 41, 100) == P[5] and px(i, 50, 100) == P[4]
    assert px(i, 100, 30) == P[5] and px(i, 100, 40) == P[4] and px(i, 56, 100) == P[5]


def test_win_delay_select():
    i = D.Img().window(0, 0, 0, 9, 9, 2, delay2=True).reg(0x04, 25)
    assert px(i, 100, 3) == P[2] and px(i, 99, 3) == BLACK and px(i, 3, 3) == BLACK


def test_win_font_priority():
    i = D.Img().window(3, 0, 0, 40, 40, 2)
    i.map([(18, [i.c1(2, 1, 4)])])
    assert px(i, 5, 5) == P[1]                                            # window 3 below the font
    i.reg(0x07, 0x01, 0x01)
    assert px(i, 5, 5) == P[2]                                            # 3A07[0] = window 3 above the font


def test_highlight_windows_4_1_to_4_8():
    for k, (ra, rb, wi) in enumerate(((0x2A, 0x2B, 10), (0x2D, 0x2E, 11), (0x30, 0x31, 12), (0x4D, 0x4E, 13), (0x4F, 0x50, 14),
                                      (0x51, 0x52, 15), (0x53, 0x54, 16), (0x55, 0x56, 17))):
        i = D.Img().window(wi, 0, 0, 11, 17, 8)
        i.map([(18, [i.c1(1, 1, 4)])])
        i.reg(ra, 0x40 | 2).reg(rb, 3)
        assert px(i, 0, 0) == P[2] and px(i, 5, 5) == P[3], wi              # box edge -> highlight fg, interior -> highlight bg
        i.reg(ra, 2)                                                        # enable bit off: normal colours
        assert px(i, 0, 0) == P[1] and px(i, 5, 5) == P[4]


def test_font_1bit():
    i = D.Img()
    i.map([(18, [i.c1(1, 1, 4)])])
    i.place(24, 24)
    a = grid_img(i)
    assert tuple(a[24, 24]) == P[1] and tuple(a[41, 35]) == P[1] and tuple(a[30, 30]) == P[4]
    assert tuple(a[24, 36]) == BLACK and tuple(a[42, 24]) == BLACK
    t = D.Img().window(0, 0, 0, 40, 40, 2)
    t.map([(18, [t.c1(1, 1, 0)])])
    assert px(t, 5, 5) == P[2] and px(t, 0, 0) == P[1]                    # background colour 0 = transparent: the window shows


def test_font_width_and_zone():
    def img(zone):
        i = D.Img()
        i.map([(18, [i.c1(3, 1, 0, 6)])])
        return i.reg(0x02, zone << 1, 0x06)
    mid, left, right = img(0), img(1), img(2)
    assert px(mid, 2, 2) == P[1] and px(mid, 3, 2) == P[1] and px(mid, 5, 2) == BLACK       # glyph columns 3..8: the vertical bar x = 5, 6
    assert px(left, 5, 2) == P[1] and px(left, 3, 2) == BLACK                                # columns 0..5: bar x = 5 only
    assert px(right, 0, 2) == P[1] and px(right, 1, 2) == BLACK                                # columns 6..11: bar x = 6 -> index 0
    assert M.layout_rows(mid.state(), M.frame_geometry(mid.state()))[0]["chars"][0]["width"] == 6


def test_font_2bit_plane_order():
    one = [[1] * 12 for _ in range(18)]
    zero = [[0] * 12 for _ in range(18)]
    for planes, want in (([one, zero], 3), ([zero, one], 4), ([one, one], 5)):     # plane A = low bit: value 1 / 2 / 3 -> c1 / c2 / c3
        i = D.Img()
        i.glyph_n(18, 2, 0, planes, True)
        i.map([(18, [i.c2(0, (2, 3, 4, 5))])])
        assert px(i, 5, 5) == P[want]


def test_font_2bit_offset():
    i = D.Img()
    one = [[1] * 12 for _ in range(18)]
    zero = [[0] * 12 for _ in range(18)]
    i.glyph_n(18, 2, 5, [one, zero], True)                                 # glyph at unit 4 + 1: char_sel_2bit_offset = 4 -> id 1 hits it
    i.reg(0x22, 4)
    i.map([(18, [i.c2(1, (2, 3, 4, 5))])])
    assert px(i, 5, 5) == P[3]


def test_font_4bit_planes():
    i = D.Img()
    one, zero = [[1] * 12 for _ in range(18)], [[0] * 12 for _ in range(18)]
    i.glyph_n(36, 4, 0, [one, zero, zero, one], False)                    # planes MSB first (QC icons, not seen on a unit): 8 + 1 = 9
    i.map([(18, [i.c4(0, 0)])])
    assert px(i, 5, 5) == i.pal[9]


def test_font_blank_and_blank_color_enable():
    i = D.Img()
    i.map([(18, [i.blank(20, 18)])])
    assert px(i, 5, 5) == i.pal[18] and px(i, 19, 17) == i.pal[18] and px(i, 20, 5) == BLACK
    i.reg(0x33, 0x20, 0x20)                                               # blank colour bits [5:4] ignored: index 18 -> 2
    assert px(i, 5, 5) == P[2]


def test_font_mask_region():
    i = D.DEMOS["font_mask"].build()
    assert px(i, 12 + 12 * 2 + 6, 12 + 18 + 9) == P[8]                    # row 1 col 2: not drawn, the window shows
    assert px(i, 12 + 12 * 4 + 6, 12 + 18 + 9) != P[8]                    # col 4 drawn
    assert px(i, 12 + 12 * 2 + 6, 12 + 9) != P[8]                         # row 0 drawn
    i.reg(0x45, 0)
    assert px(i, 12 + 12 * 2 + 6, 12 + 18 + 9) != P[8]


def test_font_delay_select_and_two_maps():
    i = D.DEMOS["two_fonts"].build()
    assert px(i, 24, 24) == P[1] and px(i, 30, 30) == P[4]               # A at delay 1: box
    assert px(i, 45, 65) == P[1] and px(i, 40, 60) == P[1]               # B at delay 2 (40, 60): solid
    i.reg(0x18, 0x00, 0x02)                                                # font B on delay 1: drawn over A
    assert px(i, 30, 30) == P[1]


def test_double_size():
    i = D.DEMOS["double_size"].build()
    assert px(i, 44, 100) == P[2] and px(i, 43, 100) == BLACK and px(i, 283, 183) == P[2] and px(i, 284, 183) == BLACK and px(i, 283, 184) == BLACK


def test_osd_position_offsets():
    base = D.Img().window(0, 0, 0, 9, 9, 2)
    assert px(base, 0, 0) == P[2]
    base.reg(0x2F, 5).reg(0x2C, 2)
    assert px(base, 0, 0) == P[2]                                         # default model: the offset registers are not applied
    o = M.Opt(osd_offsets=True)
    assert px(base, 0, 0, opt=o) == BLACK and px(base, 5, 2, opt=o) == P[2] and px(base, 4, 2, opt=o) == BLACK
    base.reg(0x32, 0x21)                                                   # window offset h 1, v 2 (px)
    assert px(base, 6, 4, opt=o) == P[2] and px(base, 5, 4, opt=o) == BLACK


def test_scale_up_factor_and_enable():
    i = D.DEMOS["scale_up"].build()
    assert px(i, 100, 50) == P[2]
    # bounding box of the OSD: text + window start at (12, 12); factor 42 -> 64 / 42 = 1.52
    a = grid_img(i)
    ys, xs = np.nonzero((a != 0).any(axis=2))
    w_on = xs.max() - xs.min() + 1
    i.reg(0xC0, 0x00)                                                      # bit 7 = 0: engine off (SDK ScalerOsdScaleUpOnOff: bit 7 = on)
    b = grid_img(i)
    ys, xs = np.nonzero((b != 0).any(axis=2))
    w_off = xs.max() - xs.min() + 1
    assert abs(w_on / w_off - 64 / 42) < 0.02
    assert M.frame_geometry(i.state())["su_on"] == 0


def test_scale_up_region_option():
    i = D.Img().window(0, 10, 10, 99, 59, 2).place(12, 12)
    i.reg(0xC0, 0x80).reg(0xC2, 32).reg(0xC3, 32)                          # 200 %
    full = px(i, 22 + 170, 22 + 10)
    assert full == P[2]
    i.reg(0xC4, 0).reg(0xC5, 22).reg(0xC6, 0).reg(0xC7, 22).reg(0xC8, 0).reg(0xC9, 25).reg(0xCA, 0).reg(0xCB, 45)   # region 45 x 25 at (22, 22)
    o = M.Opt(su_region=True)
    assert px(i, 22 + 80, 22 + 10, opt=o) == P[2] and px(i, 22 + 92, 22 + 10, opt=o) == BLACK


def test_blend_window_alpha_type1():
    i = D.DEMOS["window_blend"].build()
    want = tuple(int(P[2][c] * 0.75 + 128 * 0.25 + 0.5) for c in range(3))
    assert px(i, 50, 40, bg="grey") == want
    i.reg(0x0A, 0x00, 0x0C)                                                # blending off: opaque
    assert px(i, 50, 40, bg="grey") == P[2]


def test_blend_font_types():
    def img(bt):
        i = D.Img().window(0, 0, 0, 40, 40, 2, blend=True)
        i.map([(18, [i.c1(1, 1, 4)])])
        i.reg(0x0A, bt << 2, 0x0C)
        i.ovl[0] |= 0x08
        return i
    f = lambda c: tuple(int(c[k] * 0.75 + 128 * 0.25 + 0.5) for k in range(3))
    assert px(img(1), 0, 0, bg="grey") == P[1] and px(img(1), 5, 5, bg="grey") == P[4]               # type 1: windows only
    assert px(img(2), 0, 0, bg="grey") == f(P[1]) and px(img(2), 5, 5, bg="grey") == f(P[4])         # type 2: all
    assert px(img(3), 0, 0, bg="grey") == P[1] and px(img(3), 5, 5, bg="grey") == f(P[4])            # type 3: window + character background
    assert px(img(1), 30, 30, bg="grey") == f(P[2])


def test_specific_colour_blend_nibble_match():
    i = D.Img().window(0, 0, 0, 9, 9, 18)
    i.ovl[0] |= 0x08
    i.reg(0x09, 0x80 | 2).reg(0x08, 0x00)                                   # blend index 2; match [3:0] only -> index 18 matches
    want = tuple(int(i.pal[18][c] * 0.75 + 128 * 0.25 + 0.5) for c in range(3))
    assert px(i, 3, 3, bg="grey") == want
    i.reg(0x08, 0x10)                                                       # all 6 bits: 18 != 2
    assert px(i, 3, 3, bg="grey") == i.pal[18]


def test_window7_mask_and_window6_function():
    i = D.Img().window(7, 0, 0, 19, 19, 2)
    i.map([(18, [i.c1(1, 1, 4)] * 4)])
    i.reg(0x09, 0x40, 0x60)                                                 # window 7 mask: OSD appears only inside
    assert px(i, 5, 5) != BLACK and px(i, 30, 5) == BLACK
    i.reg(0x09, 0x60, 0x60)                                                 # hidden inside
    assert px(i, 30, 5) != BLACK and px(i, 5, 5) == BLACK


def test_palette_and_overlay_off():
    i = D.Img().window(0, 0, 0, 9, 9, 7).set_pal(7, (1, 2, 3))
    assert px(i, 3, 3) == (1, 2, 3)
    i.ovl[0] = 0
    assert px(i, 3, 3) == BLACK                                             # 0x6C[0] overlay port off
    j = D.Img().window(0, 0, 0, 9, 9, 7)
    j.reg(0x02, 0)
    assert px(j, 3, 3) == BLACK                                             # 3A02[0] OSD circuit off


def test_vertical_boundary():
    i = D.Img()
    i.map([(18, [i.c1(2, 1, 0)])]).place(24, 24)
    i.reg(0x18, 0x20, 0x20).reg(0x1E, 0).reg(0x1F, 10).reg(0x20, 20)       # upper 10, lower 20 lines
    assert px(i, 30, 33) == BLACK and px(i, 30, 34) == P[1] and px(i, 30, 41) == P[1]
    i.reg(0x20, 15)                                                         # lower 15: lines >= 24 + 15 hidden
    assert px(i, 30, 38) == P[1] and px(i, 30, 39) == BLACK


def test_row_total_option():
    i = D.Img()
    i.map([(18, [i.c1(2, 1, 0)]), (18, [i.c1(2, 1, 0)])])
    i.reg(0x3F, 1)
    assert px(i, 5, 20) == P[1]
    assert px(i, 5, 20, opt=M.Opt(row_total=True)) == BLACK and px(i, 5, 5, opt=M.Opt(row_total=True)) == P[1]


def test_area_clip_option():
    i = D.Img()
    i.map([(18, [i.c1(2, 1, 0)] * 3)])
    i.reg(0x3A, 20).reg(0x39, 18)
    assert px(i, 30, 5) == P[1]
    o = M.Opt(area_clip=True)
    assert px(i, 19, 5, opt=o) == P[1] and px(i, 20, 5, opt=o) == BLACK and px(i, 5, 18, opt=o) == BLACK


def test_auto_rotate_180_and_window_option():
    i = D.Img().window(0, 0, 0, 39, 19, 2, adr9=(1, 1, 0))
    i.map([(18, [i.c1(2, 1, 0)])]).place(0, 0, font=(50, 0))
    i.reg(0x41, 0x21)                                                       # 180 degree, enabled
    assert px(i, 0, 0) == P[2]                                              # the window stays (rotation covers the font map)
    o = M.Opt(win_rotate=True)
    assert px(i, 0, 0, opt=o) == BLACK and px(i, 61, 0, opt=o) == P[2]


def test_pattern_generator():
    i = D.DEMOS["pattern_gen"].build()
    a = grid_img(i)
    assert tuple(a[0, 0]) == (0, 0, 255) and tuple(a[0, 8]) == (4, 0, 255) and tuple(a[8, 0]) == (0, 2, 255)
    i.pg[0] = 0
    assert px(i, 0, 0) == BLACK


def test_bands_geometry_decode():
    i = D.Img().place(300, 200, font=(10, 6))
    g = M.frame_geometry(i.state())
    assert (g["hd"], g["vd"], g["fh"], g["fv"], g["step"]) == (300, 200, 10, 6, 1)
