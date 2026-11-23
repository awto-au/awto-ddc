#!/usr/bin/env python3
"""RTD2795T OSD model for fw_sim: captures what the firmware writes into the OSD and renders what the panel shows (#46, #63).

Library (no CLI; CLI = osd_render.py). Facts: docs/osd/README.md (the OSD manual), regdb re/regdb/.
- OsdModel (fw_sim.Dev): taps scaler regs 0x90 addr MSB, 0x91 addr LSB, 0x92 data, 0x94 write option (bytesel/sram_sel),
  0x6E/0x6F palette LUT. Keeps window SRAM (sram_sel 00) and font-select/font SRAM (10) as {word: [B0, B1, B2]}.
  VLC font download (0x3A17[0]) is decoded on the fly (map 0x3A0F..16); write protection 0x3A33/34 applied.
- snapshot(m) = model state + frame registers (XRAM 0x3A00-0x3AFF, 0x6C, 0x8F) at one moment.
- render(snap) -> RGB uint8 (panel H x W), OSD composited over a background.
Feature list, evidence and test per feature: docs/osd/sim-coverage.tsv (typed) / sim-coverage.md. Behaviour the regdb leaves open is
modelled as the most literal reading behind an Opt switch [spec-model] and listed there with the test that would settle it.
Feature demos / register-image builder: scripts/osd_demo.py. Hardware conformance hook: scripts/osd_conform.py.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S
import numpy as np
import osd_vlc
from glyph_decode import CODES, tile

ADR_MSB, ADR_LSB, DATA, MISC, WOPT = 0x90, 0x91, 0x92, 0x93, 0x94
LUT_ADDR, LUT_PORT = 0x6E, 0x6F
SRAM_WIN, SRAM_FONT = 0, 2
GW, GH = 12, 18                                   # 1-bit glyph cell
SRAM_WORDS = 12288                                # _OSD_SRAM_SIZE, RL6449_OSD_Gen_Option.h
FRAME = 0x3A00
END_CODE = "11111111"
PG_BASE = 0x07F0
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
class Opt:
    """Switches for behaviour the regdb leaves open [spec-model]; defaults keep every measured / saver result unchanged."""
    osd_offsets: bool = False        # add 3A2C / 3A2F (OSD delay offsets, delay units) and 3A32 (window offsets, px) to the position
    area_clip: bool = False          # clip the first OSD to osd_wid1 x osd_len1 (3A38..3A3A) [units px, guess]
    row_total: bool = False          # stop map A after font_a_row_total rows (3A3F) when non-zero
    su_region: bool = False          # scale-up acts on the region 3AC4..CB instead of the bounding box of the OSD
    win_rotate: bool = False         # windows with ADR9[0] follow the auto rotation of the font block
    pg_toggle: str = "delta"         # pattern generator toggle: alternate between init and init + delta
    fontmask_unit: str = "cell"      # 3A45..4C row / column unit: map row index / character cell index
    plane4_lsb: bool = False         # 4-bit glyph plane order: False = first plane is the MSB (QC icons), True = LSB as measured for 2-bit (OT-1)
    round_circle: bool = True        # round-corner pattern tables all zero: quarter circle of the pattern size


OPT = Opt()


@dataclass
class OsdState:
    win: dict = field(default_factory=dict)          # window SRAM  {word: [b0, b1, b2]}
    font: dict = field(default_factory=dict)         # font select + font SRAM
    pal: list = field(default_factory=lambda: [(0, 0, 0)] * 64)
    regs: bytes = b""                                # XRAM 0x3A00..0x3AFF
    ovl: tuple = (0, 0)                              # 0x006C, 0x008F
    t_ms: float = 0.0
    nwr: int = 0
    pg: bytes = b""                                  # page 7 0x07F0..0x07FF: display pattern generator

    def reg(self, a: int) -> int:
        return self.regs[a - FRAME] if self.regs else 0


class OsdModel(S.Dev):
    """Write tap on the OSD port + palette; state in .st. `mem` = callable(addr) -> XRAM byte (m.rd) for the protection/VLC regs."""
    reads = (TB_OUT, DATA)
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
        self.rdq: list[int] = []                     # read-back bytes queued for the data port (SRAM read function 3A33[4])
        self._cur: list[int] = []
        self.rd_last: list[int] = []                 # previous word read: the first pass of a read returns it (stale)

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
            self._arm_read(m)
            return
        if a == WOPT:
            self.plane, self.pend = 0, [0, 0, 0]
            self._arm_read(m)
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
        elif a == DATA and self.rdq:
            self.rdq.pop(0)
            if not self.rdq:                           # next word (auto increment): two passes again
                self.rd_last = self._cur
                self.addr = (self.addr + 1) & 0x7FFF
                self._arm_read(m, keep=True)
            else:
                self._rd_preload(m)

    JUNK = (0x48, 0x11, 0x30)                          # [hw] what a read returns while the scan engine owns the SRAM (circuit on)

    def read_ok(self, m) -> bool:
        """SRAM read-back works with the OSD circuit off (3A02[0]), sram_read_en (3A33[4]), scale-up off (3AC0[7]) and overlay off (6C[0]) [hw, docs/osd-hw-tests.md]."""
        return bool(self._rd(m, FRAME + 0x33) & 0x10) and not self._rd(m, FRAME + 2) & 1 and not self._rd(m, FRAME + 0xC0) & 0x80 and not self._rd(m, 0x6C) & 1

    def _arm_read(self, m, keep: bool = False):
        """Queue the bytes the next reads return: first pass = the previously read word (stale), second pass = this word [databook 3A33[4]: the 2nd read is right]."""
        if not self._rd(m, FRAME + 0x33) & 0x10:
            self.rdq = []
            return
        wopt = self._rd(m, WOPT)
        sel, bytesel = (wopt >> 2) & 3, (wopt >> 5) & 7
        planes = [p for p in range(3) if bytesel >> p & 1] or [0]
        d = self.st.win if sel == SRAM_WIN else self.st.font if sel == SRAM_FONT else {}
        w = d.get(self.addr, [0, 0, 0])
        cur = [w[p] for p in planes] if self.read_ok(m) else [self.JUNK[p] for p in planes]
        stale = self.rd_last if len(self.rd_last) == len(planes) else [0] * len(planes)
        self.rdq, self._cur = list(stale) + cur, cur
        self.log.append(("read", sel, self.addr, bytes(cur).hex(), self.read_ok(m)))
        self._rd_preload(m)

    def _rd_preload(self, m):
        if self.rdq:
            m.put(f"set memory xram 0x{DATA:x} 0x{self.rdq[0]:x}")
            m.flush()

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
                        bytes(m.rd(FRAME, 0x100)), (self._rd(m, 0x6C), self._rd(m, 0x8F)), t_ms, s.nwr, bytes(m.rd(PG_BASE, 16)))


# --- decoders over a snapshot ---------------------------------------------------------------------------------------
def win_base(i: int) -> int:
    """Window index: 0..9 = WIN0..9, 10..17 = WIN4_1..4_8, 18..25 = WIN5_1..5_8 (word base of ADR0)."""
    return 0x100 + 4 * i if i < 10 else 0x200 + 4 * (i - 10)


_WINNAME = ["WIN0", "WIN1", "WIN2", "WIN3", "WIN4", "WIN5", "WIN6", "WIN7", "WIN8", "WIN9"] + [f"WIN4_{k}" for k in range(1, 9)] + [f"WIN5_{k}" for k in range(1, 9)]
_ADR = {}


def win_adr(i: int, n: int) -> int | None:
    """Word address of WIN<i>_ADR<n> from the regdb (None = this window has no such word)."""
    if not _ADR:
        import csv
        import gzip
        with gzip.open(Path(__file__).resolve().parent.parent / "re/regdb/RTD2795T-CG.tsv.gz", "rt") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r["kind"] == "REG" and r["register"].startswith("WIN") and r["register"].endswith("_LSB") and "_ADR" in r["register"]:
                    _ADR[r["register"][:-4]] = int(r["port_idx"])
    return _ADR.get(f"{_WINNAME[i]}_ADR{n}")


def sat_adr4(i: int) -> int:
    """Word of WIN<i>_ADR4 (saturated colour R, G, B bytes; regdb): windows 1..4 have none."""
    if i == 0:
        return 336
    return 346 + 2 * (i - 5) if 5 <= i <= 9 else 0          # windows 4_x / 5_x have a chessboard word at ADR4 instead [regdb]


def decode_window(win: dict, i: int) -> dict | None:
    w = [win.get(win_base(i) + k, [0, 0, 0]) for k in range(4)]
    en = w[3][2] & 1
    x0 = (w[1][0] >> 4) << 8 | w[1][1]
    y0 = (w[1][0] & 15) << 8 | w[1][2]
    x1 = (w[2][0] >> 4) << 8 | w[2][1]
    y1 = (w[2][0] & 15) << 8 | w[2][2]
    return {"i": i, "en": en, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "color": (w[3][0] >> 5 & 1) << 5 | w[3][1] & 0x1F,
                "blend": w[3][2] >> 7 & 1, "eff_en": w[3][2] >> 4 & 1, "eff_opt": w[3][2] >> 1 & 7,
                "bor": (w[3][0] >> 6 & 1) << 5 | (w[0][0] >> 6 & 1) << 4 | (w[0][1] & 15), "sha": (w[3][0] >> 7 & 1) << 5 | (w[0][0] >> 7 & 1) << 4 | (w[0][1] >> 4),   # colour index bits 5 / 4 / 3:0 in ADR3 / ADR0 / ADR0 [regdb]
                "dsel": w[3][0] >> 2 & 1,
                "eff_w": (w[0][0] >> 3 & 7) + 1, "eff_h": (w[0][0] & 7) + 1, "gra": (w[3][2] >> 6 & 1) if i == 0 or 5 <= i <= 9 else 0, "gdir": w[3][2] >> 5 & 1,
                "gpol": (w[0][2] >> 7 & 1, w[0][2] >> 6 & 1, w[0][2] >> 5 & 1), "gstep": (w[0][2] >> 3 & 3) + 1,
                "gen": (w[0][2] >> 2 & 1, w[0][2] >> 1 & 1, w[0][2] & 1), "gsat": win.get(win_base(i) + 3, [0, 0, 0])[0] >> 4 & 1, "lvext": win.get(win_base(i) + 3, [0, 0, 0])[0] & 1,
                "grev": win.get(win_base(i) + 3, [0, 0, 0])[0] >> 3 & 1, "satc": tuple(win.get(sat_adr4(i), [0, 0, 0])) if sat_adr4(i) else None}


EFF_NAMES = ["shadow1", "shadow2", "shadow3", "shadow4", "3D1", "3D2", "rsv", "border"]


def describe_window(st: OsdState, w: dict) -> list[str]:
    """Short label lines for a decoded window: index, colour, and every effect the model knows (for annotated renders)."""
    out = [f"W{w['i']} c{w['color']}"]
    if w["gra"]:
        ch = "".join(("RGB"[j] + ("+" if w["gpol"][j] else "-")) for j in range(3) if w["gen"][j]) or "flat"
        out.append(f"grad {'V' if w['gdir'] else 'H'} {ch} s{w['gstep']}" + (" sat" if w["gsat"] else "") + (" rev" if w["grev"] else ""))
    if 2 <= w["i"] <= 4:
        g7 = st.win.get(0x183 + 7 * (w["i"] - 2), [0, 0, 0])
        g8 = st.win.get(0x184 + 7 * (w["i"] - 2), [0, 0, 0])
        if g8[0] & 1:
            out.append(f"grid {'H' if g7[1] >> 7 & 1 else ''}{'V' if g7[1] >> 6 & 1 else ''} w{(g7[0] >> 6) + 1}")
    if w["eff_en"]:
        out.append(f"{EFF_NAMES[w['eff_opt']]} {w['eff_w']}px")
    if w["blend"]:
        out.append("blend")
    ex = window_extras(st, w["i"])
    if ex["cb"]:
        out.append(f"chess {ex['cb'][0]}/{ex['cb'][1]} {ex['pix']}px")
    if ex["round"]:
        out.append(f"round {ex['round'][0]}px")
    if ex["gray"]:
        out.append("gray")
    if ex["mask"] is not None:
        out.append("mask " + ("OR" if ex["mask"] else "AND"))
    return out


def window_extras(st: OsdState, i: int) -> dict:
    """Chessboard colours (ADR5), pixel step (ADR9), gray level (ADR9 bit 1), rotate (ADR9 bit 0), rounded corners (ADR10) of window i."""
    g = lambda n: st.win.get(win_adr(i, n), [0, 0, 0]) if win_adr(i, n) else [0, 0, 0]
    a9, a10 = g(9), g(10)
    cbw = win_adr(i, 5) if i in (8, 9) else win_adr(i, 4) if i >= 10 else None     # chessboard word: ADR5 of windows 8 / 9, ADR4 of 4_x / 5_x [regdb]
    a5 = st.win.get(cbw, [0, 0, 0]) if cbw else [0, 0, 0]
    cb = (a5[1] & 0x3F, a5[2] & 0x3F) if a5[0] & 0x80 else None
    code = a10[0] >> 1 & 3
    rd = (8 << code, tuple(a10[0] >> b & 1 for b in (6, 5, 4, 3))) if a10[0] & 1 and code < 3 else None   # size 8 / 16 / 32 [regdb]; corners UL, LL, UR, LR
    mk = (a9[0] >> 3 & 1) if a9[0] & 4 else None
    return {"cb": cb, "pix": max(a9[1], 1), "gray": a9[0] >> 1 & 1, "round": rd, "mask": mk, "rot": a9[0] & 1}


def round_cuts(st: OsdState, n: int, opt: Opt) -> list[int]:
    """Pixels hidden per corner line (line 0 = the window edge) for a rounded window of size n (8 / 16 / 32).
    Pattern registers 0x3A60.. hold one value per line (3 / 4 / 5 bit). [spec-model] value = visible pixels of that line inside the
    corner square, so the SDK QC ramp (line k = k) is a chamfer; all-zero table = quarter circle (opt.round_circle)."""
    r = st.reg
    if n == 8:
        v = [r(FRAME + 0x60 + k // 2) >> (4 if k & 1 else 0) & 7 for k in range(8)]
    elif n == 16:
        v = [r(FRAME + 0x64 + k // 2) >> (4 if k & 1 else 0) & 15 for k in range(16)]
    else:
        v = [r(FRAME + 0x6C + k) & 31 for k in range(32)]
    if not any(v) and opt.round_circle:
        return [max(0, n - round((n * n - (n - k - 0.5) ** 2) ** 0.5)) for k in range(n)]
    return [n - x for x in v]


def round_mask(st: OsdState, wl: int, hl: int, n: int, corners, opt: Opt) -> np.ndarray:
    """Visible mask (hl x wl, logical px) of a window with the four corners (UL, LL, UR, LR) rounded by the pattern of size n."""
    mk = np.ones((hl, wl), bool)
    cuts = round_cuts(st, n, opt)
    for k in range(min(n, hl, wl)):
        c = min(cuts[k], wl)
        if not c:
            continue
        if corners[0]:
            mk[k, :c] = False
        if corners[2]:
            mk[k, wl - c:] = False
        if corners[1]:
            mk[hl - 1 - k, :c] = False
        if corners[3]:
            mk[hl - 1 - k, wl - c:] = False
    return mk


def pg_image(pg: bytes, W: int, H: int, opt: Opt | None = None) -> np.ndarray | None:
    """Display pattern generator (page 7 0x07F0..FF) as an (H, W, 3) picture, None when off. Per channel (R, G, B = CTRL 0xF0 / F1 / F2,
    init F3..F5 = value[11:4]): increment / toggle per pixel step and per line step by the delta (12 bit), clamp or wrap, invert.
    [databook] register text; [spec-model] toggle = alternate init / init + delta; random mode (pg_mode) = flat init value."""
    opt = opt or OPT
    if len(pg) < 16 or not pg[0] & 0x80:
        return None
    pd = (pg[10] >> 6 & 3) << 10 | pg[6] << 2 | pg[14] >> 4 & 3
    ld = (pg[10] >> 2 & 3) << 10 | pg[7] << 2 | pg[14] & 3
    ps = max(pg[8] + (pg[10] >> 4 & 3) / 4.0, 0.25)
    ls = max(pg[9] + (pg[10] & 3) / 4.0, 0.25)
    xs = np.floor(np.arange(W) / ps).astype(np.int64)[None, :]
    ys = np.floor(np.arange(H) / ls).astype(np.int64)[:, None]
    out = np.zeros((H, W, 3), np.uint8)
    for c in range(3):
        ctl, v = pg[c], np.full((H, W), pg[3 + c] << 4, np.int64)
        if not ctl & 0x40:
            if ctl & 1:
                v = v + pd * xs
            if ctl & 2:
                v = v + (xs & 1) * (pd if opt.pg_toggle == "delta" else 0xFFF)
            if ctl & 4:
                v = v + ld * ys
            if ctl & 8:
                v = v + (ys & 1) * (ld if opt.pg_toggle == "delta" else 0xFFF)
        v = np.minimum(v, 0xFFF) if ctl & 0x10 else v & 0xFFF
        if ctl & 0x20:
            v = 0xFFF - v
        out[:, :, c] = (v >> 4).astype(np.uint8)
    return out


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
        return {"kind": kind, "id": b1, "width": GW, "cols": (c0, c1, b2 >> 3 & 7, b0 >> 1 & 7), "fg": c1, "bg": c0}
    if kind == "4bit":                                   # SDK ScalerOsdChange4BitColor: B0 = 0xC0 | background colour, B2 = palette-set flags [SDK]; bg index 0 is drawn (photo, unit 3)
        return {"kind": kind, "id": b1, "width": GW, "fg": 0, "bg": b0 & 0x3F, "pset": b2}
    if kind == "blank":                                  # SDK OsdBlankFont: B0 = type, B1 = pixel length, B2 = background colour (6 bit)
        return {"kind": kind, "id": 0, "width": b1, "fg": 0, "bg": b2 & 0x3F}
    return {"kind": kind, "id": b1 + (256 if kind == "1bit" and b0 & 0x20 else 0), "width": b0 & 0x1F, "fg": b2 >> 4, "bg": b2 & 15}


def frame_geometry(st: OsdState) -> dict:
    r = st.reg
    step = 1 if r(FRAME + 6) & 0x10 else 4
    hd = r(FRAME + 1) << 2 | r(FRAME + 2) >> 6 | (r(FRAME + 6) >> 2 & 3) << 10
    vd = r(FRAME) << 3 | (r(FRAME + 2) >> 3 & 7)
    fh = (r(FRAME + 0x24) >> 4) << 8 | r(FRAME + 0x25)
    fv = (r(FRAME + 0x24) & 15) << 8 | r(FRAME + 0x26)
    return {"en": r(FRAME + 2) & 1, "sx": 2 if r(FRAME + 0x0A) & 2 else 1, "sy": 2 if r(FRAME + 0x0A) & 1 else 1,
                "hd": hd, "vd": vd, "step": step, "fh": fh, "fv": fv,
                "fs_base": ((r(FRAME + 0x1B) >> 4) << 8 | r(FRAME + 0x1C)) if ((r(FRAME + 0x18) & 0xC0) == 0x80 or r(FRAME + 0x18) & 0x08) else  # roll-up / two fonts: font-select base 0
                ((r(FRAME + 0x0D) >> 4) << 8 | r(FRAME + 0x0C)),
                "two": r(FRAME + 0x18) >> 3 & 1, "row_base1": r(FRAME + 0x1A), "fs_base1": (r(FRAME + 0x1B) & 15) << 8 | r(FRAME + 0x1D),
                "hd2": r(FRAME + 4) << 2 | r(FRAME + 5) >> 6 | (r(FRAME + 6) & 3) << 10, "vd2": r(FRAME + 3) << 3 | (r(FRAME + 5) >> 3 & 7),
                "fhb": (r(FRAME + 0x27) >> 4) << 8 | r(FRAME + 0x28), "fvb": (r(FRAME + 0x27) & 15) << 8 | r(FRAME + 0x29), "font_base": (r(FRAME + 0x17) >> 3 & 7) << 12 | r(FRAME + 0x0E) << 4 | r(FRAME + 0x0D) & 15,
                "row_base": r(FRAME + 0x19), "blend_type": r(FRAME + 0x0A) >> 2 & 3, "zone": r(FRAME + 2) >> 1 & 3,
                "su_on": r(FRAME + 0xC0) >> 7 & 1, "big": r(FRAME + 0x43) >> 6 & 1, "fb_shift": (r(FRAME + 0x5C) << 4 | r(FRAME + 0x5D) & 15) if r(FRAME + 0x5E) & 0x80 else 0}


def glyph_bits(st: OsdState, g: dict, gid: int) -> np.ndarray:
    if g.get("big"):                                   # 24x36 mode (3A43[6]): 36 words per glyph, rows of 24 px read row-major [guess, QC data decodes jumbled]
        by = bytes(b for k in range(36) for b in st.font.get(g["font_base"] + 36 * gid + k, [0, 0, 0]))
        return np.array(osd_vlc.unpack_unit(by, 2 * GW, 2 * GH, 1), bool)
    base = g["font_base"] + 9 * gid
    by = bytes(b for k in range(9) for b in st.font.get(base + k, [0, 0, 0]))
    return tile(by, 0)


def _planes(st: OsdState, base: int, n: int, lsb_first: bool = False) -> np.ndarray:
    """n bit planes, each stored like a 1 bpp glyph (9 words). lsb_first: plane k = bit k (2-bit, unit 3 ladder, docs/osd-hw-tests.md T9);
    else MSB plane first (4-bit: from Realtek's QC icons only, awto-ddc#227, not seen on a unit)."""
    v = np.zeros((GH, GW), np.uint8)
    for k in range(n):
        by = bytes(b for w in range(9) for b in st.font.get(base + 9 * k + w, [0, 0, 0]))
        bit = tile(by, 0).astype(np.uint8)
        v = (v | (bit << k)) if lsb_first else ((v << 1) | bit)
    return v


def glyph_levels2(st: OsdState, g: dict, gid: int) -> np.ndarray:
    """2-bit glyph: 18 words at font_base + 18 * (char_sel_2bit_offset + id) [QC: offset 16, id 0 = tile 32]."""
    off2 = (st.reg(FRAME + 0x21) >> 1 & 1) << 8 | st.reg(FRAME + 0x22)
    return _planes(st, g["font_base"] + 18 * (off2 + gid), 2, lsb_first=True)


def glyph_levels4(st: OsdState, g: dict, gid: int, lsb_first: bool = False) -> np.ndarray:
    """4-bit glyph: 36 words at font_base + 36 * (char_sel_4bit_offset + id) [QC: offset 0, ICON_4BIT(0) = 38]."""
    off4 = (st.reg(FRAME + 0x21) & 1) << 8 | st.reg(FRAME + 0x23)
    return _planes(st, g["font_base"] + 36 * (off4 + gid), 4, lsb_first)


def layout_rows(st: OsdState, g: dict, rb: int | None = None, cb: int | None = None) -> list[dict]:
    """A font map: row commands from row_base (B0 bit7 = row present, B1 = height-1, B2 = char count), chars from fs_base."""
    rows, a, ca = [], g["row_base"] if rb is None else rb, g["fs_base"] if cb is None else cb
    for _ in range(255):
        rc = st.font.get(a)
        if rc is None or not rc[0] & 0x80:
            break
        n = rc[2]
        rows.append({"h": (rc[1] & 0x3F) + 1, "n": n, "chars": [decode_char(st.font.get(ca + k, [0, 0, 0])) for k in range(n)]})
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
            if ch["kind"] == "1bit" and glyph_bits(st, g, ch["id"]).any() or ch["kind"] == "2bit" and glyph_levels2(st, g, ch["id"]).any():
                cols.append(k)
        out.append(cols)
    return out


def blend_alpha(st: OsdState) -> float:
    """Video weight of a blending OSD pixel: alpha_blending_level (0x6C[4:2] = bits 7:5, 0x8F[7:3] = bits 4:0) / 256.
    [derived] SDK OsdFuncTransparency / ScalerOsdSetTransparency (0..255, 0 = blending off = opaque); regdb 3-bit view
    '001~111: 1/8~7/8'. Direction (level = video share) from the SDK menu item 'Transparency', not measured on a panel."""
    return (((st.ovl[0] >> 2) & 7) << 5 | st.ovl[1] >> 3) / 256.0


def render(st: OsdState, W: int = 3840, H: int = 2160, bg=(128, 128, 128), alpha_opaque: bool = False, opt: Opt | None = None) -> np.ndarray:
    """Composite the OSD over a background: a flat colour or an (H, W, 3) picture. Returns uint8 (H, W, 3).
    The OSD layer (windows + fonts, last writer wins) is built first, then blended once per pixel: a window pixel with its
    blend_en blends when alpha_blend_type (0x3A0A[3:2]) is 01 / 10 / 11; font foreground only at 10; character background at 10 / 11.
    A window pixel inside a character cell (cell background index 0 shows the window) counts as character background: at 01 it
    stays opaque [measured unit 1 2026-11-13: type 01 level 51 menu not see-through, type 11 see-through; awto-ddc#176]."""
    opt = opt or OPT
    img = np.empty((H, W, 3), np.uint8)
    img[:] = bg
    pgi = pg_image(st.pg, W, H, opt)                          # pattern generator replaces the picture
    if pgi is not None:
        img[:] = pgi
    g = frame_geometry(st)
    if not g["en"] or not st.ovl[0] & 1:                      # 0x6C[0] overlay port off = ScalerOsdDisableOsd (SRAM keeps its content)
        return img
    sx, sy = g["sx"], g["sy"]
    dh, dv = (st.reg(FRAME + 0x2F), st.reg(FRAME + 0x2C)) if opt.osd_offsets else (0, 0)     # OSD delay offsets in delay units [spec-model]
    fh1, fv1 = ((st.reg(FRAME + 0x1E) >> 7 & 1) if sx == 2 else 0, (st.reg(FRAME + 0x1E) >> 3 & 1) if sy == 2 else 0) if opt.osd_offsets else (0, 0)
    ox, oy = (g["hd"] + dh) * g["step"] * sx + fh1, (g["vd"] + dv) * sy + fv1      # panel px of the OSD origin: delay x step x scale [spec, SDK OsdDispSetPosition]
    ox2, oy2 = (g["hd2"] + dh) * g["step"] * sx + fh1, (g["vd2"] + dv) * sy + fv1  # second OSD delay (frame_ctrl_03..05)
    wofs = (st.reg(FRAME + 0x32) & 15, st.reg(FRAME + 0x32) >> 4) if opt.osd_offsets else (0, 0)   # window offset h, v [spec-model, px]

    def worig(w):                                             # window delay select ADR3[2]: first / second OSD delay
        return (ox2 + wofs[0] * sx, oy2 + wofs[1] * sy) if w["dsel"] else (ox + wofs[0] * sx, oy + wofs[1] * sy)
    t = 0.0 if alpha_opaque else blend_alpha(st)
    bt = g["blend_type"]
    a_win = t if bt in (1, 2, 3) else 0.0                      # video share per OSD element (0 = opaque)
    a_fg = t if bt == 2 else 0.0
    a_cbg = t if bt in (2, 3) else 0.0
    osd = np.zeros((H, W, 3), np.uint8)
    cov = np.zeros((H, W), bool)
    vid = np.zeros((H, W), np.float32)                       # video share of the OSD pixel
    kind = np.zeros((H, W), np.uint8)                        # 1 font foreground, 2 character background, 3 window (for highlight / window 6, 7 functions)
    masks = []                                               # special colour mask windows: applied to the video at the end

    def rect(x0, y0, x1, y1, rgb, a):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if x1 > x0 and y1 > y0:
            osd[y0:y1, x0:x1] = rgb
            cov[y0:y1, x0:x1] = True
            vid[y0:y1, x0:x1] = a
            kind[y0:y1, x0:x1] = 3

    def paint_(px, py, mk, rgb, a, k=1):
        ys, xs = py + np.arange(mk.shape[0])[:, None], px + np.arange(mk.shape[1])[None, :]
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & mk
        yy, xx = np.broadcast_to(ys, mk.shape)[ok], np.broadcast_to(xs, mk.shape)[ok]
        osd[yy, xx] = rgb
        cov[yy, xx] = True
        vid[yy, xx] = a
        kind[yy, xx] = k

    paint = paint_

    wins = [w for i in range(26) if (w := decode_window(st.win, i)) and w["en"]]
    higher = {3: st.reg(FRAME + 7) & 1, 4: st.reg(FRAME + 7) >> 1 & 1, 2: st.reg(FRAME + 8) >> 7, 9: st.reg(FRAME + 8) >> 6 & 1, 8: st.reg(FRAME + 8) >> 5 & 1}

    def draw_grid(w, X0, Y0, X1, Y1, a):                  # grid line fields WIN2..4_ADR7/8 (regdb); pitch um -> px assumes the QC panel pitch 993 [guess]
        if not 2 <= w["i"] <= 4:
            return
        g7 = st.win.get(0x183 + 7 * (w["i"] - 2), [0, 0, 0])
        g8 = st.win.get(0x184 + 7 * (w["i"] - 2), [0, 0, 0])
        if not g8[0] & 1:
            return
        width, col, hen, ven, off = (g7[0] >> 6) + 1, g7[0] & 0x3F, g7[1] >> 7 & 1, g7[1] >> 6 & 1, g7[1] & 0x3F
        um = (g8[0] >> 1) << 8 | g7[2]                   # pitch in um; panel pitch U(9.2) um per px (3A35..37) [regdb]; unset: 993 / 4 um (QC panel) [guess]
        hpp = ((st.reg(FRAME + 0x35) >> 4 & 7) << 8 | st.reg(FRAME + 0x36)) / 4.0 or 993 / 4.0
        vpp = ((st.reg(FRAME + 0x35) & 7) << 8 | st.reg(FRAME + 0x37)) / 4.0 or 993 / 4.0
        c = st.pal[col]
        for k in range(off, Y1 - Y0, max(1, round(um / vpp)) * sy) if hen else ():
            rect(X0, Y0 + k, X1, min(Y0 + k + width * sy, Y1), c, a)
        for k in range(off, X1 - X0, max(1, round(um / hpp)) * sx) if ven else ():
            rect(X0 + k, Y0, min(X0 + k + width * sx, X1), Y1, c, a)

    one_px = sx == 1 and sy == 1
    ones_ = np.ones((sy, sx), bool)

    def up(m):                                                # logical -> panel pixels (double width / height)
        return m if one_px else np.kron(m, ones_)

    def draw_win(w):
        wx, wy = worig(w)
        X0, Y0, X1, Y1 = wx + w["x0"] * sx, wy + w["y0"] * sy, wx + (w["x1"] + 1) * sx, wy + (w["y1"] + 1) * sy
        a = a_win if w["blend"] else 0.0
        if w["gra"] and X1 > X0 and Y1 > Y0:             # gradient [register doc, approximation: 8 levels, gra_step px per level]
            n = (X1 - X0) if not w["gdir"] else (Y1 - Y0)
            base = st.pal[w["color"]]
            a6, a8, a9 = (st.win.get(win_adr(w["i"], q) or -1, [0, 0, 0]) for q in (6, 8, 9))
            stp = a8[1] if (a9[0] & 0x10 and a8[1]) else w["gstep"]          # ADR9[4] step extension: ADR8 MSB = px per level [register doc]
            lvl = [a6[j] for j in range(3)] if w["lvext"] else [8, 8, 8]      # ADR3[0] level extension: per-channel level ADR6 [register doc, guess: value per step]
            for k in range(0, n, stp * (sx if not w["gdir"] else sy)):
                li = min(k // (stp * (sx if not w["gdir"] else sy)), 255 if w["lvext"] else 31)
                c = []
                for j in range(3):
                    lv = li * lvl[j]
                    v = base[j] + ((lv if w["gpol"][j] else -lv) if w["gen"][j] else 0)
                    if w["gsat"] and w["satc"] and w["gen"][j]:       # saturated colour = the end value; reversed = bounce back [register doc, guess]
                        e = w["satc"][j]
                        span = abs(e - base[j]) or 1
                        d = abs(v - base[j])
                        d = (span - abs(d % (2 * span) - span)) if w["grev"] else min(d, span)
                        v = base[j] + (d if e >= base[j] else -d)
                    c.append(max(0, min(255, v)))
                c = tuple(c)
                m = stp * (sx if not w["gdir"] else sy)
                if not w["gdir"]:
                    rect(X0 + k, Y0, min(X0 + k + m, X1), Y1, c, a)
                else:
                    rect(X0, Y0 + k, X1, min(Y0 + k + m, Y1), c, a)
            return
        ex = window_extras(st, w["i"])
        col = st.pal[w["color"]]
        if ex["mask"] is not None and X1 > X0 and Y1 > Y0:   # special colour mask: window colour AND / OR the video, no OSD pixel
            masks.append((X0, Y0, X1, Y1, col, ex["mask"]))
            return
        if ex["gray"]:                                     # gray level function: luma of the window colour [register doc, guess]
            lum = int(0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2])
            col = (lum, lum, lum)
        if ex["cb"] and X1 > X0 and Y1 > Y0:               # chessboard: two palette colours in squares of pix_step px [register doc, guess]
            stp = ex["pix"] * sx
            cx0, cy0, cx1, cy1 = max(X0, 0), max(Y0, 0), min(X1, W), min(Y1, H)
            if cx1 > cx0 and cy1 > cy0:
                sel = ((((np.arange(cy0, cy1) - Y0) // stp)[:, None] + ((np.arange(cx0, cx1) - X0) // stp)[None, :]) & 1)
                osd[cy0:cy1, cx0:cx1] = np.array([st.pal[ex["cb"][0]], st.pal[ex["cb"][1]]], np.uint8)[sel]
                cov[cy0:cy1, cx0:cx1] = True
                vid[cy0:cy1, cx0:cx1] = a
                kind[cy0:cy1, cx0:cx1] = 3
        elif ex["round"] and X1 > X0 and Y1 > Y0:           # rounded corners: pattern tables 0x3A60..8B on the enabled corners [spec-model]
            mk = round_mask(st, w["x1"] + 1 - w["x0"], w["y1"] + 1 - w["y0"], ex["round"][0], ex["round"][1], opt)
            paint(X0, Y0, up(mk), col, a)
        else:
            rect(X0, Y0, X1, Y1, col, a)
        draw_grid(w, X0, Y0, X1, Y1, a)
        if w["eff_en"]:                                   # shadow types 0..3 / 3D button 4,5 [register doc, approximation]
            ew, eh = w["eff_w"] * sx, w["eff_h"] * sy
            sh, bo = st.pal[w["sha"]], st.pal[w["bor"]]
            if w["eff_opt"] >= 4:                         # 3D: sha = left/top edge, bor = right/bottom edge, inside the window
                rect(X0, Y0, X1, Y0 + eh, sh, a)
                rect(X0, Y0, X0 + ew, Y1, sh, a)
                rect(X0, Y1 - eh, X1, Y1, bo, a)
                rect(X1 - ew, Y0, X1, Y1, bo, a)
            else:                                         # shadow: bar right + below (bor colour border)
                rect(X1, Y0 + eh, X1 + ew, Y1 + eh, sh, a)
                rect(X0 + ew, Y1, X1 + ew, Y1 + eh, sh, a)

    rot = (st.reg(FRAME + 0x41) >> 4 & 3) if st.reg(FRAME + 0x41) & 1 else None     # auto rotation: 0 CCW, 1 CW, 2 180 (3A41 [5:4] / [0])
    rk = {0: 1, 1: -1, 2: 2}.get(rot)
    late = []
    rwin = {w["i"] for w in wins if opt.win_rotate and rk is not None and window_extras(st, w["i"])["rot"]}     # windows that follow the auto rotation [spec-model]
    for w in wins:
        if w["i"] >= 10 and w["eff_en"] and (st.win.get(win_base(w["i"]) + 3, [0, 0, 0])[0] >> 1 & 1):
            late.append(w)                                    # ADR3[1] bor_higher_font: border above the font [regdb]
        if not higher.get(w["i"]) and w["i"] not in rwin:
            draw_win(w)
    # fonts
    fa_o = (ox2, oy2) if st.reg(FRAME + 0x18) >> 2 & 1 else (ox, oy)     # font A / B reference delay select 3A18[2] / [1]
    fb_o = (ox2, oy2) if st.reg(FRAME + 0x18) >> 1 & 1 else (ox, oy)
    fx, fy = fa_o[0] + g["fh"] * sx, fa_o[1] + g["fv"] * sy

    gm: dict = {}

    def memo(key, fn):                                        # glyph bitmaps decoded once per render
        if key not in gm:
            gm[key] = fn()
        return gm[key]

    def P_NONE(*a, **k):
        return None

    def C_NONE(*a, **k):
        return None

    def cell_(px, py, cw, ch_h):                               # window pixels under this cell -> character-background class
        x0, y0, x1, y1 = max(px, 0), max(py, 0), min(px + cw * sx, W), min(py + ch_h * sy, H)
        if x1 > x0 and y1 > y0:
            v = vid[y0:y1, x0:x1]
            v[cov[y0:y1, x0:x1]] = a_cbg

    def draw_rows(rows, fx, fy, which=0):
        y = 0
        mr = st.reg(FRAME + (0x47 if which else 0x45))              # mask region of font A / B (3A45..4C): rows / columns = map row / cell index [spec-model]
        mrow, mcol = (mr & 0x7F, st.reg(FRAME + (0x48 if which else 0x46)) & 0x7F), (st.reg(FRAME + (0x4B if which else 0x49)), st.reg(FRAME + (0x4C if which else 0x4A)))
        for ri, row in enumerate(rows):
            x = 0
            if rk is None and fy + y * sy >= H:                    # below the panel: nothing further shows (not with rotation: the block turns back in)
                break
            for ci, ch in enumerate(row["chars"]):
                if rk is None and fx + x * sx >= W:
                    break
                masked = bool(mr & 0x80) and mrow[0] <= ri <= mrow[1] and mcol[0] <= ci <= mcol[1]
                paint = P_NONE if masked else paint_
                cell = C_NONE if masked else cell_
                gw = 2 * GW if g.get("big") else GW
                cw = {"1bit": ch["width"] if 0 < ch["width"] < gw else gw, "2bit": GW}.get(ch["kind"], ch["width"] or GW)   # = the advance below
                cell(fx + x * sx, fy + y * sy, cw, row["h"])
                if ch["kind"] == "1bit":
                    bits = memo(("g1", ch["id"]), lambda ch=ch: glyph_bits(st, g, ch["id"]))
                    w = ch["width"] if 0 < ch["width"] < gw else gw
                    c0 = {0: (gw - w + 1) // 2, 1: 0, 2: gw - w}.get(g["zone"], 0)
                    bits = bits[:, c0:c0 + w]
                    fg, bgc = st.pal[ch["fg"]], ch["bg"]
                    px, py = fx + x * sx, fy + y * sy
                    if bits.size:
                        for val, rgb, solid, a in ((1, fg, True, a_fg), (0, st.pal[bgc], bgc != 0, a_cbg)):   # bg index 0 = transparent [spec osd-font-download.md]
                            if solid:
                                paint(px, py, up(bits == val), rgb, a, 1 if val == 1 else 2)
                    x += w
                elif ch["kind"] == "blank":                          # SDK OsdBlankFont: B1 = pixel length, B2 = background colour
                    bw = ch["width"] or GW
                    bcol = ch["bg"] & (0x0F if st.reg(FRAME + 0x33) & 0x20 else 0x3F)   # blank_color_en (3A33[5]) 1: colour bits [5:4] ignored [databook]
                    if bcol != 0:
                        paint(fx + x * sx, fy + y * sy, np.ones((row["h"] * sy, bw * sx), bool), st.pal[bcol], a_cbg, 2)
                    x += bw
                elif ch["kind"] == "4bit":                           # bit planes; palette index = pixel value, 0 transparent [guess, QC palette sets 0]
                    lv = memo(("g4", ch["id"]), lambda ch=ch: glyph_levels4(st, g, ch["id"], opt.plane4_lsb))
                    px, py = fx + x * sx, fy + y * sy
                    paint(px, py, up(lv == 0), st.pal[ch["bg"]], a_cbg, 2)   # background pixels = the command's background colour, index 0 included
                    for v in range(1, 16):
                        paint(px, py, up(lv == v), st.pal[v], a_fg)
                    x += GW
                elif ch["kind"] == "2bit":
                    lv = memo(("g2", ch["id"]), lambda ch=ch: glyph_levels2(st, g, ch["id"]))
                    px, py = fx + x * sx, fy + y * sy
                    for v in range(4):
                        ci = ch["cols"][v]
                        if ci == 0:                                  # colour index 0 = transparent (as the 1-bit background) [spec]
                            continue
                        paint(px, py, up(lv == v), st.pal[ci], a_fg)
                    x += GW
                else:
                    x += ch["width"] or GW
            y += row["h"]

    def rotated(fn):                                        # the engine rotates map + font SRAM; the sim does not, so rotate the drawn map [approximation]
        if rk is None:
            return fn()
        o0, c0, v0 = osd.copy(), cov.copy(), vid.copy()
        fn()
        ch = (cov != c0) | (osd != o0).any(axis=2)
        if not ch.any():
            return
        ys, xs = np.nonzero(ch)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        so, sc, sv = osd[y0:y1, x0:x1].copy(), cov[y0:y1, x0:x1].copy(), vid[y0:y1, x0:x1].copy()
        osd[y0:y1, x0:x1], cov[y0:y1, x0:x1], vid[y0:y1, x0:x1] = o0[y0:y1, x0:x1], c0[y0:y1, x0:x1], v0[y0:y1, x0:x1]
        so, sc, sv = np.rot90(so, rk), np.rot90(sc, rk), np.rot90(sv, rk)
        h, w = sc.shape
        h, w = min(h, H - y0), min(w, W - x0)
        m = sc[:h, :w]
        osd[y0:y0 + h, x0:x0 + w][m] = so[:h, :w][m]
        cov[y0:y0 + h, x0:x0 + w] |= m
        vid[y0:y0 + h, x0:x0 + w][m] = sv[:h, :w][m]
    popon = (st.reg(FRAME + 0x18) & 0xC0) == 0xC0             # pop-on (3A18[7] special + [6]): one map shown, [0] picks A (0) / B (1); ScalerOsdPopOn sets [6] even when disabling [SDK]
    pop_b = st.reg(FRAME + 0x18) & 1
    cap = lambda rows, tot: rows[:tot] if opt.row_total and tot else rows      # font_a_row_total (3A3F) / font_b (3A40) [spec-model]
    if not (popon and pop_b):
        rotated(lambda: ([draw_win(w) for w in wins if w["i"] in rwin], draw_rows(cap(layout_rows(st, g), st.reg(FRAME + 0x3F)), fx, fy, 0)))
    if g["two"] and not (popon and not pop_b):                                              # second map: its own origin (hd2 / vd2) and font delay
        rotated(lambda: draw_rows(cap(layout_rows(st, g, g["row_base1"], g["fs_base1"]), st.reg(FRAME + 0x40)), fb_o[0] + g["fhb"] * sx, fb_o[1] + g["fvb"] * sy, 1))
    for w in wins:
        if higher.get(w["i"]) and w["i"] not in rwin:
            draw_win(w)
    for w in late:                                            # redraw the window frame (colour edge only) over the font
        wx, wy = worig(w)
        X0, Y0, X1, Y1 = wx + w["x0"] * sx, wy + w["y0"] * sy, wx + (w["x1"] + 1) * sx, wy + (w["y1"] + 1) * sy
        bw, bh = w["eff_w"] * sx, w["eff_h"] * sy
        c = st.pal[w["bor"]]
        for r_ in ((X0, Y0, X1, Y0 + bh), (X0, Y1 - bh, X1, Y1), (X0, Y0, X0 + bw, Y1), (X1 - bw, Y0, X1, Y1)):
            rect(*r_, c, 0.0)
    if opt.area_clip:                                         # first OSD area osd_wid1 x osd_len1 (3A38..3A3A) [spec-model, px]
        aw, al = (st.reg(FRAME + 0x38) & 15) << 8 | st.reg(FRAME + 0x3A), (st.reg(FRAME + 0x38) >> 4) << 8 | st.reg(FRAME + 0x39)
        if aw and al:
            keep = np.zeros((H, W), bool)
            keep[max(oy, 0):max(oy + al * sy, 0), max(ox, 0):max(ox + aw * sx, 0)] = True
            cov &= keep
    if st.reg(FRAME + 0x18) & 0x20:                           # vertical boundary: OSD only between the upper and lower line [3A1E / 3A1F / 3A20; units = panel lines, guess]
        up = (st.reg(FRAME + 0x1E) >> 4 & 7) << 8 | st.reg(FRAME + 0x1F)
        lo = (st.reg(FRAME + 0x1E) & 7) << 8 | st.reg(FRAME + 0x20)
        cov[:max(oy + up, 0)] = False
        cov[oy + lo:] = False
    if st.reg(FRAME + 0xC0) & 0x80 and cov.any():             # scale-up engine: ratio = 64 / factor (150 % -> 42, 200 % -> 32 in the QC), nearest-neighbour [guess]
        rh, rv = 64.0 / max(st.reg(FRAME + 0xC3) & 63, 1), 64.0 / max(st.reg(FRAME + 0xC2) & 63, 1)
        ys_, xs_ = np.nonzero(cov)
        y0_, x0_ = ys_.min(), xs_.min()
        h0, w0 = ys_.max() + 1 - y0_, xs_.max() + 1 - x0_
        if opt.su_region:                                     # source region 3AC4..CB (start / size) instead of the OSD bounding box [spec-model, panel px]
            y0_, x0_ = min(st.reg(FRAME + 0xC4) << 8 | st.reg(FRAME + 0xC5), H - 1), min(st.reg(FRAME + 0xC6) << 8 | st.reg(FRAME + 0xC7), W - 1)
            h0, w0 = min(max((st.reg(FRAME + 0xC8) & 15) << 8 | st.reg(FRAME + 0xC9), 1), H - y0_), min(max((st.reg(FRAME + 0xCA) & 15) << 8 | st.reg(FRAME + 0xCB), 1), W - x0_)
        h1, w1 = min(int(h0 * rv), H - y0_), min(int(w0 * rh), W - x0_)
        iy = np.minimum((np.arange(h1) / rv).astype(int), h0 - 1) + y0_
        ix = np.minimum((np.arange(w1) / rh).astype(int), w0 - 1) + x0_
        for arr in (osd, cov, vid, kind):
            sub = arr[np.ix_(iy, ix)].copy()
            arr[y0_:y0_ + h0, x0_:x0_ + w0] = 0
            arr[y0_:y0_ + h1, x0_:x0_ + w1] = sub

    def rect_of(i):
        w = decode_window(st.win, i)
        if not w or not w["en"]:
            return None
        wx, wy = worig(w)
        return (max(wx + w["x0"] * sx, 0), max(wy + w["y0"] * sy, 0), min(wx + (w["x1"] + 1) * sx, W), min(wy + (w["y1"] + 1) * sy, H))
    for k, (ra, rb, wi) in enumerate(((0x2A, 0x2B, 10), (0x2D, 0x2E, 11), (0x30, 0x31, 12), (0x4D, 0x4E, 13), (0x4F, 0x50, 14), (0x51, 0x52, 15),
                                      (0x53, 0x54, 16), (0x55, 0x56, 17))):   # highlight (ScalerOsdWindowHighlightFunction): font colours inside windows 4-1..4-8
        r_ = rect_of(wi)
        if r_ and st.reg(FRAME + ra) & 0x40 and r_[2] > r_[0] and r_[3] > r_[1]:
            sl = (slice(r_[1], r_[3]), slice(r_[0], r_[2]))
            osd[sl][kind[sl] == 1] = st.pal[st.reg(FRAME + ra) & 0x3F]
            osd[sl][kind[sl] == 2] = st.pal[st.reg(FRAME + rb) & 0x3F]
    for win, en, typ in ((6, st.reg(FRAME + 0x21) >> 6 & 1, st.reg(FRAME + 0x21) >> 2 & 3), (7, st.reg(FRAME + 9) >> 5 & 3 == 1, st.reg(FRAME + 0x21) >> 4 & 3)):   # window 6 / 7 blending functions
        r_ = rect_of(win)
        if en and r_ and r_[2] > r_[0] and r_[3] > r_[1]:
            sl = (slice(r_[1], r_[3]), slice(r_[0], r_[2]))
            fgv, bgv = ((0.0, 0.0), (0.0, t), (t, 0.0), (t, t))[typ]          # NO_BLENDING_BOTH / _FOREGROUND / _BACKGROUND / BLENDING_BOTH [SDK enum order]
            vv = vid[sl]
            vv[kind[sl] == 1] = fgv
            vv[kind[sl] == 2] = bgv
    m7 = st.reg(FRAME + 9) >> 5 & 3
    r7 = rect_of(7)
    if m7 in (2, 3) and r7 and r7[2] > r7[0] and r7[3] > r7[1]:              # window 7 mask region: 2 = OSD appears only inside, 3 = hidden inside (all / font only)
        inside = np.zeros((H, W), bool)
        inside[r7[1]:r7[3], r7[0]:r7[2]] = True
        if m7 == 2:
            cov &= inside
        else:
            cov &= ~(inside & ((kind == 1) | (kind == 2) | (st.reg(FRAME + 7) >> 3 & 1 == 0)))
    if st.reg(FRAME + 9) & 0x80:                              # specific colour blending (ScalerOsdSpecificColorBlending): this LUT index blends [SDK, guess: any element]
        idx = (st.reg(FRAME + 8) >> 2 & 3) << 4 | st.reg(FRAME + 9) & 15
        hit = np.zeros((H, W), bool)
        for j in ([idx] if st.reg(FRAME + 8) >> 4 & 1 else [j for j in range(64) if j & 15 == idx & 15]):   # all_match_type2: 0 = match LUT index bits [3:0] only
            hit |= (osd == np.array(st.pal[j], np.uint8)).all(axis=2)
        vid[cov & hit] = t
    k = vid[cov][:, None]
    img[cov] = (osd[cov] * (1.0 - k) + img[cov] * k + 0.5).astype(np.uint8)
    for X0, Y0, X1, Y1, col, opt in masks:
        X0, Y0, X1, Y1 = max(X0, 0), max(Y0, 0), min(X1, W), min(Y1, H)
        cc = np.array(col, np.uint8)
        img[Y0:Y1, X0:X1] = (img[Y0:Y1, X0:X1] | cc) if opt else (img[Y0:Y1, X0:X1] & cc)
    return img


def summary(st: OsdState) -> dict:
    g = frame_geometry(st)
    rows = layout_rows(st, g)
    ids = {(c["kind"], c["id"]) for r in rows for c in r["chars"] if c["kind"] in ("1bit", "2bit")}
    return dict(g, nwin=sum(1 for i in range(26) if decode_window(st.win, i)["en"]), rows=len(rows),
                cols=max((r["n"] for r in rows), default=0), cells=sum(r["n"] for r in rows), uniq_ids=len(ids),
                max_id=max((i for _, i in ids), default=-1), font_words=len(st.font), win_words=len(st.win))
