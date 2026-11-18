#!/usr/bin/env python3
"""OSD conformance cases: the host-only unit-3 tests that settle the [spec-model] guesses of osd_model (docs/osd/sim-coverage.tsv).

usage: osd_conform.py --list
       osd_conform.py --sim CASE [--out PNG] [--opt NAME=VAL ...]   render the case in the model (no hardware)
       osd_conform.py --conform CASE CAPTURE.png [--tol N] [--box X0,Y0,X1,Y1]   diff a capture of the case against the model render
       osd_conform.py --hw CASE --bus N --yes-unit-3               write the case into the OSD of unit 3 over ISP (volatile; NOT run by agents)
Case = Img (osd_demo.py) drawn at the top-left 640 x 360 of the panel at 1:1 (delay step 1 px, no scale-up, 4K input). A capture is a
photo / screen grab of that region; --conform crops + resizes it to the model canvas and reports the share of pixels within --tol
(default 40 per channel, photo colour error) and exits 0 at >= 0.97. The case question names what the capture settles.
--hw reuses scripts/rtd_osd.py (ISP F4/F5, volatile regs / SRAM only, the MCU is halted by the ISP session: no firmware writes race).
Log: ./tmp/logs/osd_conform.log
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import osd_demo as D  # noqa: E402
import osd_model as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/osd_conform.log"
MATCH = 0.97


@dataclass
class Case:
    name: str
    question: str                    # what the capture decides, and how to read it
    build: Callable[[], D.Img]
    opt: dict | None = None          # Opt fields the sim run uses (the literal reading under test)


CASES: dict[str, Case] = {}


def case(name: str, question: str, opt: dict | None = None):
    def deco(fn):
        CASES[name] = Case(name, question, fn, opt)
        return fn
    return deco


def _ramp_tables(i: D.Img):
    for k in range(4):
        i.reg(0x60 + k, (2 * k + 1) << 4 | 2 * k)               # 8x8 line k = k (SDK QC ramp)
    for k in range(8):
        i.reg(0x64 + k, (2 * k + 1) << 4 | 2 * k)               # 16x16
    for k in range(32):
        i.reg(0x6C + k, k)                                      # 32x32
    return i


@case("C-ROUND", "Rounded corners with the SDK QC ramp tables (line k = value k): is value = visible px of the line from the window edge "
                 "(chamfer, sim) or hidden px (notch)? Count the cut px of the top line of the 16 px window: 16 = visible reading, 0 = hidden reading.")
def _():
    i = _ramp_tables(D.Img())
    i.window(0, 20, 20, 99, 99, 2, adr10=(0x78 | 1, 0, 0)).window(5, 120, 20, 199, 99, 3, adr10=(0x78 | 3, 0, 0)).window(10, 220, 20, 339, 119, 4, adr10=(0x78 | 5, 0, 0))
    return i


@case("C-GRID", "Grid pitch in px for pitch 2000 um with panel pitch regs 3A35..37 = 500 (125 um): sim 16 px. Measure the line spacing.")
def _():
    return D.DEMOS["window_grid"].build()


@case("C-CHESS", "Chessboard square size for window 8 pix_step 8 and for 4_x / 5_x (no step register): measure the squares.")
def _():
    i = D.Img().window(8, 20, 20, 179, 99, 2, adr5=(0x80, 1, 4), adr9=(0, 8, 0))
    return i.window(10, 220, 20, 379, 99, 2, adr4=(0x80, 1, 4)).window(18, 20, 140, 179, 219, 2, adr4=(0x80, 1, 4))


@case("C-GRAD", "Gradient: px per level for step 1..4, level count, polarity, saturated / reversed colours (bounce). Compare ramps to the sim.")
def _():
    i = D.Img()
    for k in range(4):
        i.window(0 if k == 0 else 5 + k - 1, 20, 20 + 70 * k, 299, 80 + 70 * k, 4, gradient=dict(dir=0, pol=(1, 1, 0), en=(1, 0, 1), step=k + 1))
    return i


@case("C-EFF", "Window effects: shadow types 1..4 (side, offset), 3D button 1 / 2 (which edge is sha / bor), border (inside or outside), "
               "width / height units. Compare the photo to the sim geometry.")
def _():
    i = D.Img()
    for k in range(8):
        i.window(k if k != 6 else 9, 20 + 150 * (k % 4), 20 + 120 * (k // 4), 120 + 150 * (k % 4), 90 + 120 * (k // 4), 3, eff=(k, 4, 4, 1, 15))
    return i


@case("C-PRIO", "Window vs font priority: for each of windows 2, 3, 4, 8, 9 (3A07 / 3A08) and the 4_x / 5_x border bit: is the window under or over "
                "the text? Windows 0, 1, 5, 6, 7 have no priority bit: which side are they on (sim: under).")
def _():
    i = D.Img()
    for k, w in enumerate((0, 1, 2, 3, 4, 5, 6, 7, 8, 9)):
        i.window(w, 10 + 60 * k, 20, 60 + 60 * k, 70, 2 + k % 6)
    i.map([(18, [i.c1(1, 1, 0)] * 50)]).place(10, 35)
    i.reg(0x07, 0x03).reg(0x08, 0xC0)
    return i


@case("C-BLEND", "Alpha level direction: 0x6C[4:2] / 0x8F level 64 of 256 - is the video share 25 % (sim) or 75 %? Types 01 / 10 / 11 on window, font fg, char bg.",
      )
def _():
    i = D.Img().window(0, 20, 20, 300, 120, 2, blend=True)
    i.map([(18, [i.c1(1, 1, 4)] * 20)]).place(30, 40)
    i.reg(0x0A, 0x08, 0x0C)
    i.ovl[0] |= 0x08
    return i


@case("C-OFFS", "Position offsets 3A2C / 3A2F (delay units) and 3A32 (window offsets, px) and the fine-tune bits 3A1E[7,3]: measure the shift of a "
                "window + text from the same image with offsets 0 (sim option osd_offsets).", opt=dict(osd_offsets=True))
def _():
    i = D.Img().window(0, 10, 10, 69, 49, 2)
    i.map([(18, [i.c1(1, 1, 4)] * 5)]).place(80, 10)
    i.reg(0x2F, 5).reg(0x2C, 3).reg(0x32, 0x21)
    return i


@case("C-DSEL", "Second OSD delay: window 0 with osd_delay_sel (ADR3[2]) and font A / B delay select (3A18[2:1]) on delay 2 at (200, 60): does each follow it?")
def _():
    i = D.Img().window(0, 0, 0, 59, 39, 2, delay2=True).window(1, 0, 60, 59, 99, 3)
    i.map([(18, [i.c1(1, 1, 4)] * 4)]).place(10, 10)
    i.reg(0x04, 50).reg(0x03, 8).reg(0x18, 0x04, 0x04)
    return i


@case("C-FMASK", "Font mask 3A45..4C: units of row / column (map row index, cell index = sim) and inclusive end.", opt=dict(fontmask_unit="cell"))
def _():
    return D.DEMOS["font_mask"].build()


@case("C-ROWTOT", "font_row_total 3A3E / 3F / 40: does a smaller value than the map's row count hide the rows below it (sim option row_total)?", opt=dict(row_total=True))
def _():
    i = D.Img().window(0, 10, 10, 200, 100, 8)
    i.text_boxes(4, 6, 1, 4).place(12, 12)
    i.reg(0x3F, 2).reg(0x3E, 2)
    return i


@case("C-AREA", "osd_wid1 / osd_len1 3A38..3A: does the first OSD clip to wid x len (px, sim option area_clip)?", opt=dict(area_clip=True))
def _():
    i = D.Img().window(0, 10, 10, 300, 200, 8)
    i.text_boxes(5, 20, 1, 4).place(12, 12)
    i.reg(0x38, 0).reg(0x39, 60).reg(0x3A, 100)
    return i


@case("C-SUREG", "Scale-up region 3AC4..CB: with factor 200 %, is the source the region (start / size in panel px, sim option su_region) or the whole OSD? "
                 "Which px is the output origin?", opt=dict(su_region=True))
def _():
    i = D.Img().window(0, 10, 10, 129, 79, 2).place(12, 12)
    i.text_boxes(3, 8, 1, 4)
    i.reg(0xC0, 0x80).reg(0xC2, 32).reg(0xC3, 32)
    for a, v in ((0xC4, 0), (0xC5, 22), (0xC6, 0), (0xC7, 22), (0xC8, 0), (0xC9, 40), (0xCA, 0), (0xCB, 60)):
        i.reg(a, v)
    return i


@case("C-SUBD", "Scale-up boundary condition (3AC0[1:0] neighbourhood / thin / fat) and initial phase (3AC1): edge shape of a 150 % scaled 1 px line pattern.")
def _():
    i = D.Img()
    i.map([(18, [i.c1(5, 1, 0)] * 10)]).place(12, 12)
    i.reg(0xC0, 0x80 | 0x01).reg(0xC2, 42).reg(0xC3, 42)
    return i


@case("C-ROTWIN", "Auto rotation 180 / CW / CCW with windows that have rotate_en (ADR9[0]): do the windows turn with the text block (sim option win_rotate)?",
      opt=dict(win_rotate=True))
def _():
    i = D.Img().window(0, 0, 0, 79, 39, 2, adr9=(1, 1, 0)).window(2, 0, 50, 79, 89, 3, adr9=(0, 1, 0))
    i.map([(18, [i.c1(1, 1, 4)] * 8)]).place(40, 40, font=(100, 0))
    i.reg(0x41, 0x21)
    return i


@case("C-PG", "Pattern generator: increment / toggle per pixel / line step, clamp, invert, step fractions. Sim toggle = init / init + delta (option pg_toggle).")
def _():
    return D.DEMOS["pattern_gen"].build()


@case("C-F4B", "4-bit font background select 3A07[2]: byte2[1:0] (regdb default) or byte0[3:0] (SDK + unit-3 photo)? Cells with B0 bg 5, B2 palette flags 0x0F.")
def _():
    i = D.Img()
    i.map([(18, [i.c4(0, 5)] * 4)]).place(12, 12)
    return i


@case("C-24X36", "24x36 font mode (3A43[6]): glyph storage order and cell layout of a 1-bit glyph with a distinct corner pattern.")
def _():
    i = D.Img()
    i.reg(0x43, 0x40)
    i.map([(36, [i.c1(1, 1, 4, 24), i.c1(4, 1, 4, 24)])]).place(12, 12)
    return i


@case("C-POPON", "Pop-on / roll-up (3A18[7:6], [0]): with maps A and B holding different text, which is shown for display_base_sel 0 / 1, and when does a change apply?")
def _():
    i = D.DEMOS["two_fonts"].build()
    i.reg(0x18, 0xC8, 0xFF)
    return i


@case("C-VBND", "Vertical boundary 3A18[5], 3A1E / 3A1F / 3A20: units of upper / lower (panel lines or scaled lines), fnt_win_v_bd_align 3A18[4].")
def _():
    i = D.Img().window(0, 0, 0, 300, 200, 2)
    i.text_boxes(8, 10, 1, 4).place(12, 12)
    i.reg(0x18, 0x20, 0x20).reg(0x1E, 0).reg(0x1F, 40).reg(0x20, 120)
    return i


@case("C-FCWIN", "Window enable mirrors 3A57..5A (R/W): set only the fc bit with the word enable 0 (and the reverse): which one enables the window (sim: the word)?")
def _():
    i = D.Img().window(0, 20, 20, 99, 99, 2).window(1, 120, 20, 199, 99, 3)
    i.wword(0, 3, [i.win[M.win_base(0) + 3][0], i.win[M.win_base(0) + 3][1], 0])     # word enable 0
    i.reg(0x57, 0x01)                                                                 # fc_win0_win_en = 1
    i.wword(1, 3, [i.win[M.win_base(1) + 3][0], i.win[M.win_base(1) + 3][1], 1])     # word enable 1
    return i


@case("C-NARROW", "Narrow characters (width 1..11) in zone middle / left / right: shown columns, rounding of the middle zone for odd widths, minimum width.")
def _():
    i = D.Img()
    i.map([(18, [i.c1(3, 1, 4, w) for w in range(1, 12)])]).place(12, 12)
    return i


@case("C-READ", "SRAM read-back: stale first pass and junk cases (docs/osd-hw-tests.md): scripts/osd_hw_test.py rd covers it; no screen capture.")
def _():
    return D.Img()


def say(s: str):
    import isostamp
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def sim(c: Case, overrides: dict | None = None) -> np.ndarray:
    kw = dict(c.opt or {})
    kw.update(overrides or {})
    return c.build().render(D.DW, D.DH, "black", M.Opt(**kw))


def conform(c: Case, capture: Path, tol: int, box: tuple | None) -> float:
    from PIL import Image
    im = Image.open(capture).convert("RGB")
    if box:
        im = im.crop(box)
    ref = sim(c)
    im = np.asarray(im.resize((ref.shape[1], ref.shape[0]), Image.BILINEAR), np.int16)
    ok = (np.abs(im - ref.astype(np.int16)) <= tol).all(axis=2)
    return float(ok.mean())


def apply_hw(img: D.Img, bus: int):
    """Write the image into the OSD of the unit on `bus` (rtd_osd.Osd): palette, window SRAM, font SRAM, frame registers last (osd_en last)."""
    import rtd_osd as R
    o = R.Osd(bus)
    o.enter()
    o.osd_enable(False)
    for k, (r, g, b) in enumerate(img.pal):
        o.set_color(k, r, g, b)
    for sel, d in ((R.SRAM_WIN, img.win), (R.SRAM_FONT, img.font)):
        o.set_opt(sel)
        for a in sorted(d):
            o.write_word(a, *d[a])
    for a in range(0x100):
        if a != 2:
            o.wr(0x3A00 + a, img.regs[a])
    o.wr(0x006C, img.ovl[0])
    o.wr(0x008F, img.ovl[1])
    for a in range(16):
        o.wr(0x07F0 + a, img.pg[a])
    o.wr(0x3A02, img.regs[2])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sim", metavar="CASE")
    ap.add_argument("--conform", nargs=2, metavar=("CASE", "CAPTURE"))
    ap.add_argument("--hw", metavar="CASE")
    ap.add_argument("--bus", type=int)
    ap.add_argument("--yes-unit-3", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--opt", action="append", default=[], help="Opt override NAME=VAL (bool 0/1 or text)")
    ap.add_argument("--tol", type=int, default=40)
    ap.add_argument("--box", help="crop of the capture X0,Y0,X1,Y1")
    a = ap.parse_args()
    if a.list:
        for c in CASES.values():
            print(f"{c.name}\t{c.question}")
        return 0
    ov = {k: (v if not v.isdigit() else bool(int(v))) for k, v in (s.split("=", 1) for s in a.opt)}
    if a.sim:
        from PIL import Image
        out = a.out or ROOT / f"tmp/osd_conform/{a.sim}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(sim(CASES[a.sim], ov)).save(out)
        say(f"{a.sim}: sim render -> {out}")
        return 0
    if a.conform:
        name, cap = a.conform
        share = conform(CASES[name], Path(cap), a.tol, tuple(int(v) for v in a.box.split(",")) if a.box else None)
        say(f"{name}: {share:.3f} of the pixels within {a.tol} of the model: {'MATCH' if share >= MATCH else 'DIFFERENT'} ({CASES[name].question})")
        return 0 if share >= MATCH else 1
    if a.hw:
        if not (a.yes_unit_3 and a.bus):
            raise SystemExit("--hw needs --bus N --yes-unit-3 (unit 3 is the test unit; do not run while another test owns it)")
        apply_hw(CASES[a.hw].build(), a.bus)
        say(f"{a.hw}: written to bus {a.bus} (volatile); photograph the top-left {D.DW} x {D.DH} px, then --conform {a.hw} PHOTO")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
