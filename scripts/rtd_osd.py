#!/usr/bin/env python3
"""Clean-room PC-driven OSD for RTD2795-class scalers, over the ISP F4/F5 window (volatile RAM/regs only).

usage: rtd_osd.py <bus> [--keep] [--pack N] [--text STR] [--no-reset] OP [OP ...]
  probe                 read OSD ports + frame regs (no writes besides page select)
  rd:0x0090 / wr:0x0090=0x00   scaler reg 0xPPRR (PP = page via 0x9F, RR = index)
  osdw:SRAM:ADDR=B0,B1,B2      write one 3-byte OSD word (SRAM = win|font), hex bytes
  osdr:SRAM:ADDR[:N]           read N words back (default 1)
  palette:IDX=RRGGBB           set one 64-entry LUT colour (0x6E/0x6F)
  upload-font                  glyphs for the chars of --text into font SRAM
  win0                         WIN0 geometry + colour (solid rectangle)
  enable / disable             osd_en (0x3A02 bit0); disable first sets 0x94=0x00
  draw-test                    full sequence: palette, font, map, WIN0, enable (text + window)
  clear                        disable OSD (0x94=0x00 -> osd_en=0)
Ends with scaler reset (0xEE=0x02, monitor reboots) unless --keep/--no-reset.
Facts: docs/reversing/realtek-rtd/osd.md. Log: ./tmp/logs/rtd_osd.log
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P

# --- hardware facts [spec from regdb RTD2795T-CG] -------------------------------------------------
PAGE_SEL = 0x9F                                  # per-page select register
OSD_ADR_MSB, OSD_ADR_LSB, OSD_DATA, OSD_MISC, OSD_WOPT = 0x90, 0x91, 0x92, 0x93, 0x94
LUT_ADDR, LUT_PORT = 0x6E, 0x6F                  # page 0: bit7 lut_acc_en, [5:0] index; 24-bit colour via port
FRAME_BASE = 0x3A00                              # FRAME_CTRL_00..; 02 bit0 = osd_en
SRAM_WIN, SRAM_FONT = 0b00, 0b10                 # 0x94 bits 3:2
BYTESEL_ALL = 0b111                              # 0x94 bits 7:5
WIN_BASE = 0x100                                 # WINn_ADR0 word index = 0x100 + 4*n (n = 0..9)

# 5x7 glyph rows (bit4 = left pixel); our own bitmaps
GLYPHS = {
    " ": [0] * 7,
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
}
GW, GH = 12, 18          # glyph cell, 1 bit/pixel -> 216 bits = 9 words of 24 bits [oss-understood]
WORDS_PER_GLYPH = 9


class Osd:
    def __init__(self, bus: int, path: str = "f4f5"):
        self.isp = P.Isp(bus)
        self.path = path
        self.page = None
        self.halted = False

    # -- ISP session --
    def enter(self) -> None:
        self.isp.write(0x6F, 0x80)
        if not self.isp.read(0x6F) & 0x80:
            raise RuntimeError("ISP mode not enabled")
        self.halted = True

    def reset(self) -> None:
        try:
            self.isp.write(0xEE, 0x02)
        except OSError:
            pass     # expected: scaler resets mid-transfer
        P.log("reset scaler MCU (0xEE <- 0x02): monitor reboots")

    # -- raw scaler regs (index within current page) --
    def _rd(self, idx):
        if self.path == "direct":
            return self.isp.read(idx)
        self.isp.write(0xF4, idx); return self.isp.read(0xF5)

    def _wr(self, idx, v):
        if self.path == "direct":
            self.isp.write(idx, v); return
        self.isp.write(0xF4, idx); self.isp.write(0xF5, v)

    def select_page(self, p: int) -> None:
        if self.page != p:
            self._wr(PAGE_SEL, p); self.page = p

    def rd(self, reg16: int) -> int:
        self.select_page(reg16 >> 8); return self._rd(reg16 & 0xFF)

    def wr(self, reg16: int, v: int) -> None:
        self.select_page(reg16 >> 8); self._wr(reg16 & 0xFF, v)

    def rmw(self, reg16, mask, val):
        self.wr(reg16, (self.rd(reg16) & ~mask) | (val & mask))

    # -- OSD access port (page 0) --
    def set_opt(self, sram: int, bytesel: int = BYTESEL_ALL) -> None:
        self.wr(OSD_WOPT, (bytesel << 5) | (sram << 2))

    def set_addr(self, a: int) -> None:
        self.wr(OSD_ADR_MSB, (a >> 8) & 0x7F); self.wr(OSD_ADR_LSB, a & 0xFF)

    def write_word(self, a: int, b0: int, b1: int, b2: int) -> None:
        """Write Byte0..2 of OSD word `a` (bytesel/sram_sel must be set already)."""
        self.set_addr(a)
        self.select_page(0)
        self.isp.write(0xF4, OSD_DATA)
        for b in (b0, b1, b2):
            self.isp.write(0xF5, b)

    def read_word(self, a: int, byte: int) -> int:
        """Read one byte plane (0..2): bytesel selects the plane; data port read."""
        self.set_addr(a)
        self.select_page(0)
        self.isp.write(0xF4, OSD_DATA)
        return self.isp.read(0xF5)

    # -- palette --
    def set_color(self, idx: int, r: int, g: int, b: int) -> None:
        self.select_page(0)
        self._wr(LUT_ADDR, 0x80 | idx)
        for c in (r, g, b):
            self._wr(LUT_PORT, c)
        self._wr(LUT_ADDR, 0x00)

    # -- frame --
    def osd_enable(self, on: bool) -> None:
        if on:
            self.rmw(FRAME_BASE + 2, 0x01, 1)
        else:
            self.set_opt(SRAM_WIN, 0)           # 0x94 = 0x00 required before clearing osd_en
            self.rmw(FRAME_BASE + 2, 0x01, 0)

    # -- window 0 --
    def win_set(self, n, x0, y0, x1, y1, color, enable=True):
        self.set_opt(SRAM_WIN)
        base = WIN_BASE + 4 * n
        self.write_word(base + 0, 0, 0, 0)                                   # no border/shadow/gradient
        self.write_word(base + 1, ((x0 >> 8) & 15) << 4 | ((y0 >> 8) & 15), x0 & 255, y0 & 255)
        self.write_word(base + 2, ((x1 >> 8) & 15) << 4 | ((y1 >> 8) & 15), x1 & 255, y1 & 255)
        self.write_word(base + 3, (color & 0x20),                            # win_color[5] at bit5
                        (0 << 5) | (color & 0x1F),                           # gra_level=0, color[4:0]
                        0x01 if enable else 0x00)                            # win_en

    # -- font --
    @staticmethod
    def glyph_words(ch: str, pack: int):
        rows5 = GLYPHS[ch]
        lines = [0] * GH
        for r in range(7):                          # 5x7 scaled 2x -> 10x14, centred in 12x18
            bits = 0
            for c in range(5):
                if rows5[r] >> (4 - c) & 1:
                    bits |= 3 << (2 * (4 - c))      # 10 bits wide
            for dy in (0, 1):
                lines[2 + 2 * r + dy] = bits << 1   # 1px left margin in 12-bit line
        out = []
        for k in range(WORDS_PER_GLYPH):
            a, b = lines[2 * k], lines[2 * k + 1]
            w = (a << 12) | b                                   # pack 0: line 2k high, 2k+1 low
            if pack == 1:
                w = (b << 12) | a
            if pack == 2:                                       # bit-reversed lines (left pixel = bit0)
                rev = lambda v: int(f"{v:012b}"[::-1], 2)
                w = (rev(a) << 12) | rev(b)
            out.append((w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF))   # Byte0 = LSB
        return out

    def upload_font(self, chars: str, font_base_words: int, pack: int) -> dict:
        self.set_opt(SRAM_FONT)
        idx = {}
        for i, ch in enumerate(chars):
            idx[ch] = i
            for k, (b0, b1, b2) in enumerate(self.glyph_words(ch, pack)):
                self.write_word(font_base_words + i * WORDS_PER_GLYPH + k, b0, b1, b2)
        return idx

    def write_map(self, fs_base: int, text: str, idx: dict, fg: int, bg: int, rowcmd):
        """One row: 3-byte row command then 3 bytes per character, then a zero row command."""
        self.set_opt(SRAM_FONT)
        a = fs_base
        self.write_word(a, *rowcmd(len(text))); a += 1
        for ch in text:
            self.write_word(a, (bg << 4) | fg, idx[ch], 0); a += 1
        self.write_word(a, 0, 0, 0)


def default_rowcmd(n):
    return (GH, GW, n)            # [guess] height, width, char count


def draw_test(o: Osd, text="HELLO", pack=0, fs_base=0x000, font_base=0x100, x=0x20, y=0x08):
    # palette: 1 = dark blue (window), 2 = white (fg), 3 = red (bg)
    o.set_color(1, 0x00, 0x00, 0xA0); o.set_color(2, 0xFF, 0xFF, 0xFF); o.set_color(3, 0xC0, 0x00, 0x00)
    o.wr(OSD_MISC, 0x00)                                   # db_enable=0: writes latch immediately
    o.rmw(0x01DC, 0x08, 0x08)                              # DCLK_GATED_CTRL2.osd_clken
    chars = "".join(dict.fromkeys(text + " "))
    idx = o.upload_font(chars, font_base, pack)
    o.wr(FRAME_BASE + 0x0C, fs_base & 0xFF)                # fs_base[7:0]
    o.rmw(FRAME_BASE + 0x0D, 0xF0, (fs_base >> 8) << 4)    # fs_base[11:8]
    o.rmw(FRAME_BASE + 0x0D, 0x0F, font_base & 0xF)        # font_base[3:0]
    o.wr(FRAME_BASE + 0x0E, font_base >> 4)                # font_base[11:4]
    o.write_map(fs_base, text, idx, fg=2, bg=3, rowcmd=default_rowcmd)
    o.win_set(0, 0, 0, 12 * len(text) + 8, 40, color=1)
    o.wr(FRAME_BASE + 0, y)                                # vert_delay1[10:3]
    o.wr(FRAME_BASE + 1, x)                                # hori_delay1[9:2]
    o.set_opt(SRAM_WIN)
    o.osd_enable(True)


def main() -> int:
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_osd.log").open("a")
    args = sys.argv[1:]
    bus = int(args.pop(0))
    keep = "--keep" in args or "--no-reset" in args
    pack, text, path = 0, "HELLO", "f4f5"
    ops = []
    while args:
        a = args.pop(0)
        if a == "--pack": pack = int(args.pop(0))
        elif a == "--text": text = args.pop(0)
        elif a == "--path": path = args.pop(0)
        elif a in ("--keep", "--no-reset"): pass
        else: ops.append(a)
    o = Osd(bus, path)
    P.log(f"bus={bus} path={path} ops={ops} pack={pack} text={text!r} keep={keep}")
    o.enter()
    try:
        for op in ops:
            kind, _, arg = op.partition(":")
            if kind == "probe":
                for r in (0x0000, 0x0090, 0x0091, 0x0092, 0x0093, 0x0094, 0x006E, 0x01DC, 0x3A02, 0x3A0C, 0x3A0D, 0x3A0E):
                    P.log(f"rd 0x{r:04x} = 0x{o.rd(r):02x}")
            elif kind == "rd":
                r = int(arg, 0); P.log(f"rd 0x{r:04x} = 0x{o.rd(r):02x}")
            elif kind == "wr":
                r, v = (int(x, 0) for x in arg.split("="))
                o.wr(r, v); P.log(f"wr 0x{r:04x} <- 0x{v:02x}")
            elif kind == "osdw":
                s, rest = arg.split(":"); a_, d = rest.split("=")
                b = [int(x, 16) for x in d.split(",")]
                o.set_opt(SRAM_WIN if s == "win" else SRAM_FONT)
                o.write_word(int(a_, 0), *b); P.log(f"osdw {s} 0x{int(a_, 0):04x} <- {b}")
            elif kind == "osdr":
                parts = arg.split(":"); s = parts[0]; a_ = int(parts[1], 0)
                n = int(parts[2]) if len(parts) > 2 else 1
                for i in range(n):
                    got = []
                    for plane in (1, 2, 4):                # bytesel one plane at a time for read-back
                        o.set_opt(SRAM_WIN if s == "win" else SRAM_FONT, plane)
                        got.append(o.read_word(a_ + i, plane))
                    P.log(f"osdr {s} 0x{a_ + i:04x} = {[hex(x) for x in got]}")
            elif kind == "osdscan":                      # osdscan:SRAM:START:N -> non-zero words, all 3 planes
                s, a_, n = arg.split(":"); a_, n = int(a_, 0), int(n, 0)
                for i in range(n):
                    got = []
                    for plane in (1, 2, 4):
                        o.set_opt(SRAM_WIN if s == "win" else SRAM_FONT, plane)
                        got.append(o.read_word(a_ + i, plane))
                    if any(got):
                        P.log(f"osdscan {s} 0x{a_ + i:04x} = {[hex(x) for x in got]}")
            elif kind == "palette":
                i, c = arg.split("="); c = int(c, 16)
                o.set_color(int(i, 0), c >> 16, (c >> 8) & 255, c & 255); P.log(f"palette {i} <- {c:06x}")
            elif kind == "upload-font":
                P.log(f"font idx {o.upload_font(''.join(dict.fromkeys(text + ' ')), 0x100, pack)}")
            elif kind == "win0":
                o.win_set(0, 0, 0, 12 * len(text) + 8, 40, 1); P.log("win0 set")
            elif kind == "enable":
                o.osd_enable(True); P.log("osd_en=1")
            elif kind in ("disable", "clear"):
                o.osd_enable(False); P.log("osd_en=0")
            elif kind == "draw-test":
                draw_test(o, text, pack)
                for r in (0x0093, 0x0094, 0x3A00, 0x3A01, 0x3A02, 0x3A0C, 0x3A0D, 0x3A0E, 0x01DC):
                    P.log(f"readback 0x{r:04x} = 0x{o.rd(r):02x}")
            else:
                P.log(f"unknown op {op}")
    finally:
        if not keep:
            o.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
