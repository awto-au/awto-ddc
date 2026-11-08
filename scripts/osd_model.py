#!/usr/bin/env python3
"""RTD2795T OSD model for fw_sim: captures what the firmware writes into the OSD and renders what the panel shows (#46, #63).

Library (no CLI; CLI = osd_render.py). Facts: docs/reversing/realtek-rtd/osd.md, osd-font-download.md, regdb re/regdb/.
- OsdModel (fw_sim.Dev): taps scaler regs 0x90 addr MSB, 0x91 addr LSB, 0x92 data, 0x94 write option (bytesel/sram_sel),
  0x6E/0x6F palette LUT. Keeps window SRAM (sram_sel 00) and font-select/font SRAM (10) as {word: [B0, B1, B2]}.
  VLC font download (0x3A17[0]) is decoded on the fly (map 0x3A0F..16); write protection 0x3A33/34 applied.
- snapshot(m) = model state + frame registers (XRAM 0x3A00-0x3AFF, 0x6C, 0x8F) at one moment.
- render(snap) -> RGB uint8 (panel H x W), OSD composited over a background.
Model gaps (marked [guess] in the code): window border/shadow/gradient, 2/4-bit fonts, font B, rotation, 24x36 mode,
OSD pipeline position offsets (0x3A2C/2F), alpha direction, FB-shift (4-path) position.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import fw_sim as S  # noqa: E402
from glyph_decode import CODES, tile  # noqa: E402
import osd_vlc  # noqa: E402

ADR_MSB, ADR_LSB, DATA, MISC, WOPT = 0x90, 0x91, 0x92, 0x93, 0x94
LUT_ADDR, LUT_PORT = 0x6E, 0x6F
SRAM_WIN, SRAM_FONT = 0, 2
GW, GH = 12, 18                                   # 1-bit glyph cell
SRAM_WORDS = 12288                                # _OSD_SRAM_SIZE, RL6449_OSD_Gen_Option.h
FRAME = 0x3A00
END_CODE = "11111111"
TB_CTRL, TB_SHIFT12, TB_SHIFT3L, TB_IN, TB_OUT = 0xFF03, 0xFF04, 0xFF05, 0xFF06, 0xFF07   # triple-byte engine (regdb 0xFF03-07)


class TripleEngine:
    """Font triple-byte engine: builds proportional glyph cells (OsdPropPutString: 12 px cell = glyph pieces side by side).
    A triple A,B,C -> rows X = A7:4 B7:4 C7:4, Y = A3:0 B3:0 C3:0 (12 px, MSB left; ctrl bit6 reorder, bit5 undo on output).
    First triple after a restart: X,Y << FF04[7:4]. Later triples: OR'd in, >> FF05[7:4]. Output = X<<12|Y as 3 bytes.
    [guess] Semantics derived from the SDK call sequence (RTD2014OsdFontProp.c), not a hardware test."""

    def __init__(self):
        self.buf, self.first, self.acc, self.out = [], True, (0, 0), []

    @staticmethod
    def split(a, b, c, reorder):
        if not reorder:
            return (a << 4 | b >> 4) & 0xFFF, (b & 15) << 8 | c
        return (a >> 4) << 8 | (b >> 4) << 4 | c >> 4, (a & 15) << 8 | (b & 15) << 4 | c & 15

    def restart(self):
        self.buf, self.first, self.acc, self.out = [], True, (0, 0), []

    def put(self, ctrl, sh12, sh3l, v):
        self.buf.append(v)
        if len(self.buf) < 3:
            return
        x, y = self.split(*self.buf, bool(ctrl & 0x40))
        self.buf = []
        if self.first:
            n = sh12 >> 4
            self.acc = ((x << n) & 0xFFF, (y << n) & 0xFFF)
            self.first = False
        else:
            n = sh3l >> 4
            self.acc = (self.acc[0] | x >> n, self.acc[1] | y >> n)
        x, y = self.acc
        if ctrl & 0x20:                                   # output reorder back to A,B,C
            self.out = [(x >> 8) << 4 | y >> 8, (x >> 4 & 15) << 4 | y >> 4 & 15, (x & 15) << 4 | y & 15]
        else:
            self.out = [x >> 4, (x & 15) << 4 | y >> 8, y & 0xFF]


# --- VLC stream decoder (hardware: 0x3A17[0], codes + map regdb 0x3A0F-0x3A16) --------------------------------------
class VlcDecoder:
    """Bytes in (LSB-first bits) -> nibbles -> bytes (high nibble first). done = END code seen."""

    def __init__(self, vmap: list[int]):
        self.tab = {c: v for c, v in zip(CODES, vmap)}
        self.code, self.nib, self.done = "", [], False

    def feed(self, b: int) -> list[int]:
        out = []
        if self.done:
            return out
        for k in range(8):
            self.code += "1" if (b >> k) & 1 else "0"
            if self.code in self.tab:
                self.nib.append(self.tab[self.code]); self.code = ""
                if len(self.nib) == 2:
                    out.append(self.nib[0] << 4 | self.nib[1]); self.nib = []
            elif self.code == END_CODE:
                self.done = True
                break
            elif len(self.code) > 8:
                self.code = ""                       # not a code: resync (bad stream)
        return out


def vlc_map_from_regs(regs) -> list[int]:
    """0x3A0F..0x3A16: byte i = vlc_2i (high nibble), vlc_2i+1 (low)."""
    v = []
    for i in range(8):
        b = regs(FRAME + 0x0F + i)
        v += [b >> 4, b & 15]
    return v


@dataclass
class OsdState:
    win: dict = field(default_factory=dict)          # window SRAM  {word: [b0, b1, b2]}
    font: dict = field(default_factory=dict)         # font select + font SRAM
    pal: list = field(default_factory=lambda: [(0, 0, 0)] * 64)
    regs: bytes = b""                                # XRAM 0x3A00..0x3AFF
    ovl: tuple = (0, 0)                              # 0x006C, 0x008F
    t_ms: float = 0.0
    nwr: int = 0

    def reg(self, a: int) -> int:
        return self.regs[a - FRAME] if self.regs else 0


class OsdModel(S.Dev):
    """Write tap on the OSD port + palette; state in .st. `mem` = callable(addr) -> XRAM byte (m.rd) for the protection/VLC regs."""
    reads = (TB_OUT,)
    writes = (ADR_MSB, ADR_LSB, DATA, WOPT, LUT_ADDR, LUT_PORT, 0xFFF3, TB_CTRL, TB_IN)

    def __init__(self):
        self.st = OsdState()
        self.addr = 0
        self.plane = 0
        self.pend = [0, 0, 0]
        self.vlc: VlcDecoder | None = None
        self.vbytes: list[int] = []
        self.lut_idx, self.lut_buf = None, []
        self.log: list[tuple] = []                   # (kind, ...) of notable events, for tests
        self.img = b""                               # flash image for the burst-DMA engine (set by the session)
        self.trace: list[tuple] = []                 # (wopt, addr, value) of data-port writes when trace_on
        self.trace_on = False
        self.tb = TripleEngine()

    # -- helpers
    def _rd(self, m, a): return m.rd(a)[0]

    def _word_done(self, sel: int, word: list[int]):
        d = self.st.win if sel == SRAM_WIN else self.st.font if sel == SRAM_FONT else None
        if d is not None:
            old = d.get(self.addr)
            d[self.addr] = word
            if old is None:
                pass
        self.addr = (self.addr + 1) & 0x7FFF

    def on_write(self, m, a):
        v = self._rd(m, a)
        if a in (ADR_MSB, ADR_LSB):
            self.addr = (self._rd(m, ADR_MSB) & 0x7F) << 8 | self._rd(m, ADR_LSB)
            self.plane, self.pend, self.vlc, self.vbytes = 0, [0, 0, 0], None, []
            return
        if a == WOPT:
            self.plane, self.pend = 0, [0, 0, 0]
            return
        if a == LUT_ADDR:
            self.lut_idx, self.lut_buf = (v & 0x3F, []) if v & 0x80 else (None, [])
            return
        if a == LUT_PORT:
            if self.lut_idx is not None:
                self.lut_buf.append(v)
                if len(self.lut_buf) == 3:
                    self.st.pal[self.lut_idx] = tuple(self.lut_buf)
                    self.lut_idx, self.lut_buf = (self.lut_idx + 1) & 0x3F, []
            return
        if a == 0xFFF3:
            self._burst(m, v)
            return
        if a == TB_CTRL:
            if v & 3:                                      # restart bits auto-clear
                self.tb.restart()
                m.put(f"set memory xram 0x{TB_CTRL:x} 0x{v & ~3 & 0xFF:x}")
                m.flush()
            return
        if a == TB_IN:
            self.tb.put(self._rd(m, TB_CTRL), self._rd(m, TB_SHIFT12), self._rd(m, TB_SHIFT3L), v)
            self._tb_preload(m)
            return
        self._data(m, v)

    def on_read(self, m, a):
        if a == TB_OUT and self.tb.out:
            self.tb.out.pop(0)
            self._tb_preload(m)

    def _tb_preload(self, m):
        if self.tb.out:
            m.put(f"set memory xram 0x{TB_OUT:x} 0x{self.tb.out[0]:x}")
            m.flush()

    def _burst(self, m, v: int):
        """Scaler burst-DMA (ScalerBurstWrite): FFF3 bit3 = data burst (bit5 set = no address increment), count FFF9/A, source
        bank FFF6 + addr FFF7/8 (FFFC bit5 = from XRAM), host reg = page 0x9F : FFF4. Copies the bytes, then clears bit3 (done).
        Command bursts (bit4) are not modelled."""
        if not v & 0x08:
            return
        r = lambda a: self._rd(m, a)
        n, src, bank = r(0xFFF9) << 8 | r(0xFFFA), r(0xFFF7) << 8 | r(0xFFF8), r(0xFFF6)
        host = r(0x9F) << 8 | r(0xFFF4)
        data = m.rd(src, n) if r(0xFFFC) & 0x20 else self.img[bank * 0x10000 + src: bank * 0x10000 + src + n]
        self.log.append(("burst", host, n, bank, src, v, r(0xFFFC) & 0x20, bytes(data).hex()))
        for i, b in enumerate(data):
            if host == DATA:
                m.put(f"set memory xram 0x{DATA:x} 0x{b:x}")
                m.flush()
                self._data(m, b)
            else:
                m.put(f"set memory xram 0x{host + (0 if v & 0x20 else i):x} 0x{b:x}")
        m.put(f"set memory xram 0xfff3 0x{v & ~0x08 & 0xFF:x}")
        m.flush()

    def _data(self, m, v: int):
        self.st.nwr += 1
        wopt = self._rd(m, WOPT)
        if self.trace_on:
            self.trace.append((wopt, self.addr, v))
        sel, bytesel = (wopt >> 2) & 3, (wopt >> 5) & 7
        if sel == SRAM_FONT and self._rd(m, FRAME + 0x17) & 1 and not self._rd(m, FRAME + 0x17) & 2:
            if self.vlc is None:
                self.vlc = VlcDecoder(vlc_map_from_regs(lambda x: self._rd(m, x)))
                self.vbytes = []
            for b in self.vlc.feed(v):
                self.vbytes.append(b)
                if len(self.vbytes) == 3:
                    self._word_done(sel, self.vbytes)
                    self.vbytes = []
            return
        planes = [p for p in range(3) if bytesel >> p & 1]
        if not planes:
            return
        p = planes[self.plane]
        prot = self._protect(m, p)
        d = self.st.win if sel == SRAM_WIN else self.st.font if sel == SRAM_FONT else {}
        cur = list(d.get(self.addr, [0, 0, 0]))
        self.pend[p] = cur[p] & prot | v & ~prot & 0xFF
        self.plane += 1
        if self.plane == len(planes):
            word = cur
            for q in planes:
                word[q] = self.pend[q]
            self._word_done(sel, word)
            self.plane = 0

    def _protect(self, m, plane: int) -> int:
        """Write protection 0x3A33[0] on, [2:1] byte, 0x3A34 = bits kept (not overwritten) [spec regdb]."""
        c = self._rd(m, FRAME + 0x33)
        if c & 1 and ((c >> 1) & 3) == plane:
            return self._rd(m, FRAME + 0x34)
        return 0

    # -- capture
    def snapshot(self, m, t_ms: float = 0.0) -> OsdState:
        s = self.st
        return OsdState({k: list(v) for k, v in s.win.items()}, {k: list(v) for k, v in s.font.items()}, list(s.pal),
                        bytes(m.rd(FRAME, 0x100)), (self._rd(m, 0x6C), self._rd(m, 0x8F)), t_ms, s.nwr)


# --- decoders over a snapshot ---------------------------------------------------------------------------------------
def win_base(i: int) -> int:
    """Window index: 0..9 = WIN0..9, 10..17 = WIN4_1..4_8, 18..25 = WIN5_1..5_8 (word base of ADR0)."""
    return 0x100 + 4 * i if i < 10 else 0x200 + 4 * (i - 10)


def decode_window(win: dict, i: int) -> dict | None:
    w = [win.get(win_base(i) + k, [0, 0, 0]) for k in range(4)]
    en = w[3][2] & 1
    x0 = (w[1][0] >> 4) << 8 | w[1][1]
    y0 = (w[1][0] & 15) << 8 | w[1][2]
    x1 = (w[2][0] >> 4) << 8 | w[2][1]
    y1 = (w[2][0] & 15) << 8 | w[2][2]
    return dict(i=i, en=en, x0=x0, y0=y0, x1=x1, y1=y1, color=(w[3][0] >> 5 & 1) << 5 | w[3][1] & 0x1F,
                blend=w[3][2] >> 7 & 1, eff_en=w[3][2] >> 4 & 1, eff_opt=w[3][2] >> 1 & 7,
                bor=(w[0][0] >> 6 & 1) << 5 | (w[0][1] & 15), sha=(w[0][0] >> 7 & 1) << 5 | (w[0][1] >> 4))


def decode_char(w: list[int]) -> dict:
    """Char command [B0, B1, B2].
    1-bit: B0[7:6]=01, B0[5] = id bit 8 (font 256..511), B0[4:0] = width px; B2 = fg<<4|bg [SDK].
    2-bit: B0[7:6]=10, no width field (12 px); the 4 colours are spread over B0 and B2 (SDK OsdFontPut2Bit packing):
           B0 = 1 c0[3] c1[3] c3[2:0] c0[2];  B2 = c0[1:0] c2[2:0] c1[2:0];  pixel value v selects colour c<v> [SDK, derived]
    4-bit: B0[7:6]=11, layout not known: decoded as kind 4bit, drawn as nothing."""
    b0, b1, b2 = w
    kind = {0: "blank", 1: "1bit", 2: "2bit", 3: "4bit"}[b0 >> 6]
    if kind == "2bit":
        c0 = (b0 >> 5 & 1) << 3 | (b0 & 1) << 2 | b2 >> 6
        c1 = (b0 >> 4 & 1) << 3 | (b2 & 7)
        return dict(kind=kind, id=b1, width=GW, cols=(c0, c1, b2 >> 3 & 7, b0 >> 1 & 7), fg=c1, bg=c0)
    return dict(kind=kind, id=b1 + (256 if kind == "1bit" and b0 & 0x20 else 0), width=b0 & 0x1F, fg=b2 >> 4, bg=b2 & 15)


def frame_geometry(st: OsdState) -> dict:
    r = st.reg
    step = 1 if r(FRAME + 6) & 0x10 else 4
    hd = r(FRAME + 1) << 2 | r(FRAME + 2) >> 6 | (r(FRAME + 6) >> 2 & 3) << 10
    vd = r(FRAME) << 3 | (r(FRAME + 2) >> 3 & 7)
    fh = (r(FRAME + 0x24) >> 4) << 8 | r(FRAME + 0x25)
    fv = (r(FRAME + 0x24) & 15) << 8 | r(FRAME + 0x26)
    return dict(en=r(FRAME + 2) & 1, sx=2 if r(FRAME + 0x0A) & 2 else 1, sy=2 if r(FRAME + 0x0A) & 1 else 1,
                hd=hd, vd=vd, step=step, fh=fh, fv=fv,
                fs_base=(r(FRAME + 0x0D) >> 4) << 8 | r(FRAME + 0x0C), font_base=(r(FRAME + 0x17) >> 3 & 7) << 12 | r(FRAME + 0x0E) << 4 | r(FRAME + 0x0D) & 15,
                row_base=r(FRAME + 0x19), blend_type=r(FRAME + 0x0A) >> 2 & 3, zone=r(FRAME + 2) >> 1 & 3,
                su_on=int(not r(FRAME + 0xC0) & 0x80), fb_shift=(r(FRAME + 0x5C) << 4 | r(FRAME + 0x5D) & 15) if r(FRAME + 0x5E) & 0x80 else 0)


def glyph_bits(st: OsdState, g: dict, gid: int) -> np.ndarray:
    base = g["font_base"] + 9 * gid
    by = bytes(b for k in range(9) for b in st.font.get(base + k, [0, 0, 0]))
    return tile(by, 0)


def glyph_levels2(st: OsdState, g: dict, gid: int) -> np.ndarray:
    """2-bit glyph: 18 words, row-major 12 px, 2 bits per px MSB first, 24-bit words stored low byte first (osd_vlc.pack_unit).
    Address = font_base + 9 * char_sel_2bit_offset + 18 * id [derived from the 3A21/3A22 field text; not seen on hardware]."""
    off2 = (st.reg(FRAME + 0x21) >> 1 & 1) << 8 | st.reg(FRAME + 0x22)
    base = g["font_base"] + 9 * off2 + 18 * gid
    by = bytes(b for k in range(18) for b in st.font.get(base + k, [0, 0, 0]))
    return np.array(osd_vlc.unpack_unit(by, GW, GH, 2), np.uint8)


def layout_rows(st: OsdState, g: dict) -> list[dict]:
    """Font A map: row commands from row_base (B0 bit7 = row present, B1 = height-1, B2 = char count), chars from fs_base."""
    rows, a, ca = [], g["row_base"], g["fs_base"]
    for _ in range(255):
        rc = st.font.get(a)
        if rc is None or not rc[0] & 0x80:
            break
        n = rc[2]
        rows.append(dict(h=(rc[1] & 0x1F) + 1, n=n, chars=[decode_char(st.font.get(ca + k, [0, 0, 0])) for k in range(n)]))
        a, ca = a + 1, ca + n
    return rows


def ink_cells(st: OsdState) -> list[list[int]]:
    """Per map row: the cell columns that show ink (a 1-bit glyph with a set pixel, or a 2-bit glyph with a non-zero level).
    The hardware draws what the map says, wrapping at the row length (row command char count) into the next row and not clipping
    to the windows: this is what a text-fit check looks at (keys_sim, popup_fit)."""
    g = frame_geometry(st)
    out = []
    for row in layout_rows(st, g):
        cols = []
        for k, ch in enumerate(row["chars"]):
            if ch["kind"] == "1bit" and glyph_bits(st, g, ch["id"]).any():
                cols.append(k)
            elif ch["kind"] == "2bit" and glyph_levels2(st, g, ch["id"]).any():
                cols.append(k)
        out.append(cols)
    return out


def render(st: OsdState, W: int = 3840, H: int = 2160, bg=(128, 128, 128), alpha_opaque: bool = False) -> np.ndarray:
    """Composite the OSD over a flat background. Returns uint8 (H, W, 3)."""
    img = np.empty((H, W, 3), np.uint8)
    img[:] = bg
    g = frame_geometry(st)
    if not g["en"] or not st.ovl[0] & 1:                      # 0x6C[0] overlay port off = ScalerOsdDisableOsd (SRAM keeps its content)
        return img
    sx, sy = g["sx"], g["sy"]
    ox, oy = g["hd"] * g["step"] * sx, g["vd"] * sy          # panel px of the OSD origin: delay x step x scale [spec, SDK OsdDispSetPosition]
    level = ((st.ovl[0] >> 2) & 7) << 5 | st.ovl[1] >> 3
    opac = 1.0 if (alpha_opaque or level == 0 or g["blend_type"] == 0) else level / 255.0     # [guess] 255 = opaque

    def rect(x0, y0, x1, y1, rgb, a=1.0):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if x1 > x0 and y1 > y0:
            if a >= 1.0:
                img[y0:y1, x0:x1] = rgb
            else:
                img[y0:y1, x0:x1] = (img[y0:y1, x0:x1] * (1 - a) + np.array(rgb) * a).astype(np.uint8)

    wins = [w for i in range(26) if (w := decode_window(st.win, i)) and w["en"]]
    higher = {3: st.reg(FRAME + 7) & 1, 4: st.reg(FRAME + 7) >> 1 & 1, 2: st.reg(FRAME + 8) >> 7, 9: st.reg(FRAME + 8) >> 6 & 1, 8: st.reg(FRAME + 8) >> 5 & 1}

    def draw_win(w):
        a = opac if w["blend"] else 1.0
        rect(ox + w["x0"] * sx, oy + w["y0"] * sy, ox + (w["x1"] + 1) * sx, oy + (w["y1"] + 1) * sy, st.pal[w["color"]], a)

    for w in wins:
        if not higher.get(w["i"]):
            draw_win(w)
    # fonts
    fx, fy = ox + g["fh"] * sx, oy + g["fv"] * sy
    y = 0
    for row in layout_rows(st, g):
        x = 0
        for ch in row["chars"]:
            if ch["kind"] == "1bit":
                bits = glyph_bits(st, g, ch["id"])
                w = ch["width"] if 0 < ch["width"] < GW else GW
                c0 = {0: (GW - w) // 2, 1: 0, 2: GW - w}.get(g["zone"], 0)
                bits = bits[:, c0:c0 + w]
                fg, bgc = st.pal[ch["fg"]], ch["bg"]
                px, py = fx + x * sx, fy + y * sy
                if bits.size:
                    for val, rgb, solid in ((1, fg, True), (0, st.pal[bgc], bgc != 0)):      # bg index 0 = transparent [spec osd-font-download.md]
                        if not solid:
                            continue
                        mk = np.kron(bits == val, np.ones((sy, sx), bool))
                        ys, xs = py + np.arange(mk.shape[0])[:, None], px + np.arange(mk.shape[1])[None, :]
                        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & mk
                        img[np.broadcast_to(ys, mk.shape)[ok], np.broadcast_to(xs, mk.shape)[ok]] = rgb
                x += w
            elif ch["kind"] == "2bit":
                lv = glyph_levels2(st, g, ch["id"])
                px, py = fx + x * sx, fy + y * sy
                for v in range(4):
                    ci = ch["cols"][v]
                    if ci == 0:                                  # colour index 0 = transparent (as the 1-bit background) [spec]
                        continue
                    mk = np.kron(lv == v, np.ones((sy, sx), bool))
                    ys, xs = py + np.arange(mk.shape[0])[:, None], px + np.arange(mk.shape[1])[None, :]
                    ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & mk
                    img[np.broadcast_to(ys, mk.shape)[ok], np.broadcast_to(xs, mk.shape)[ok]] = st.pal[ci]
                x += GW
            else:
                x += ch["width"] or GW
        y += row["h"]
    for w in wins:
        if higher.get(w["i"]):
            draw_win(w)
    return img


def summary(st: OsdState) -> dict:
    g = frame_geometry(st)
    rows = layout_rows(st, g)
    ids = {(c["kind"], c["id"]) for r in rows for c in r["chars"] if c["kind"] in ("1bit", "2bit")}
    return dict(g, nwin=sum(1 for i in range(26) if decode_window(st.win, i)["en"]), rows=len(rows),
                cols=max((r["n"] for r in rows), default=0), cells=sum(r["n"] for r in rows), uniq_ids=len(ids),
                max_id=max((i for _, i in ids), default=-1), font_words=len(st.font), win_words=len(st.win))
