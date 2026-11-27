#!/usr/bin/env python3
"""OSD SRAM hardware tests on the test unit (docs/osd-hw-tests.md): write paths, read-back, ladder, OT-8 cell mode.

usage: ./dev.py osd-hw-test [--unit N] TEST [TEST ...]   (runs osd_hw_test.py --bus B --serial S --map MAP [--bin BIN] TEST ...)
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c g_stAwtoOsdHw). The host drives the firmware over debug slave 0x35:
  params + ucGo = op, the main loop runs the op and clears ucGo. Read-back = 0x3A33 sram_read_en with the overlay off (the op does it).
  TESTs (PASS/FAIL criteria: docs/osd-hw-tests.md):
    regs   OSD register snapshot
    t1     pattern write through ScalerOsdDataPort, read back M1 + M2: glyph range, map range
    t2     the same through direct back-to-back stores (loop, unrolled triples), EA on / off
    t3     direct + gap sweep: the smallest gap with 0 errors (run only when t2 fails)
    cycle  T10 for a human: the ladder with a blue digit 1..6, variants 8 s each, looping until `cyclestop` (docs/osd-hw-tests.md)
    cyclestop  stop the cycle; check the ladder glyphs in SRAM are still as written
    ladder T9: 2-bit ids 0..255 as a 16 x 16 grid, plane A solid (left on screen) + the sim render of the same ladder
    ot8    OT-8, 24 x 36 cell mode on (3A43[6]): 8 test glyphs + 4 high ids, coded map; SRAM read back vs the host twin and the sim; left on screen
    ot8off OT-8 control: the same SRAM + map with the mode off (cells draw as 12 x 18 from the same words)
    ot8full OT-8 capacity: pattern over words 0..12221 (330 glyphs of 36 words + map, 99.5 % of the SRAM) written and read back M1 / M2; run BEFORE ot8 (overwrites the screen)
    t6     plane / colour screen for a human (left on screen)
    stop   saver off, OSD closed
Log: ./tmp/logs/osd_hw_test.log ; SRAM dumps: ./tmp/osd_hw/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/osd_hw_test.log"
OUT = ROOT / "tmp/osd_hw"
DEV8 = 0x6A
# StAwtoOsdHw (fw/test/testcmd.c), big-endian WORDs
O_GO, O_SEQ, O_STATE, O_MODE, O_GAP, O_FLAGS, O_SEED, O_OVL, O_ADDR, O_N = 0, 1, 2, 3, 4, 5, 6, 7, 8, 10
O_BAD, O_FIRST, O_CRC, O_MS, O_FRAME, O_REGS, O_BADB, O_BUF = 12, 14, 16, 18, 20, 22, 31, 39
N_REGS, BUF = 9, 54
O_RUN = O_BUF + BUF
SIZE = O_RUN + 1
REG_NAMES = ["3A02", "3A0B", "3A17", "3A33", "3A34", "3A41", "0093", "0094", "006C"]
OP_WRITE, OP_VERIFY, OP_READ, OP_CRC, OP_WRBUF, OP_PLANES, OP_UNUSED7, OP_REGS, OP_SAVER, OP_LADDER, OP_CYCLE, OP_BIG = range(1, 13)
M_SDK, M_DIRECT, M_GAP, M_TRIPLE = 0, 1, 2, 3
MODE_NAMES = {M_SDK: "ScalerOsdDataPort", M_DIRECT: "direct loop", M_GAP: "direct+gap", M_TRIPLE: "direct triples"}
F_EA_OFF, F_M2, F_HIDE, F_HOLD, F_REPEAT, F_RD_OVL, F_RD_SU = 1, 2, 4, 8, 16, 32, 64
ST_OK = 1
LFSR_POLY, LFSR_LOW, LFSR_STEPS = 0xB400, 0x5A, 8
WORD_B = 3
# SRAM ranges (words): the ladder (testcmd.c AWTO_OHW_LD_*: 256 2-bit glyphs of 18 words from 616, map before it); top = the unused end of the 12288-word SRAM
LD_FONT, LD_IDS, LD_STRIDE = 616, 256, 18
LD_END = LD_FONT + LD_IDS * LD_STRIDE
RANGES = {"glyphs": (LD_FONT, LD_IDS * LD_STRIDE), "map": (0, LD_FONT), "top": (0x2000, 0x1000)}
SAVER_OFF = 0                             # VCP 0xEB value 0 (fw/awto/savers.tsv)
# poll limits: 1.25 x the measured worst case on unit 3 (docs/osd-hw-tests.md "op times"); expiry = FAIL, logged with the elapsed time
US_PER_WRITE_BYTE = {M_SDK: 46.2, M_DIRECT: 46.2, M_GAP: 46.2, M_TRIPLE: 46.2}   # worst per byte incl. the pattern refill (all modes)
US_GAP_PASS = 1.0                         # not measured (t3 not needed: t2 passed); estimate 1 us per delay pass
US_PER_READ_BYTE = 200.0                  # verify: 13824 B in 2734 ms worst (circuit off, scale-up off, two 3-byte reads per word)
SAVER_OP_S = 0.25                         # saver request served in the op (one main-loop pass + the draw)
OP_FIXED_S = 0.25                         # one main-loop pass (max gap 20 ms, health) + the I2C of param write + polls
MARGIN = 1.25
CYCLE_LOOK_S = 58.0                       # cycle: 6 variants x 8 s, then the write counter is read
CYCLE_BAND_S = 0.02                       # cycle: a main pass may hold one 8 ms band or one DVS wait (16.7 ms at 60 Hz)
LADDER_GLYPH = bytes([0xFF]) * 27 + bytes(27)   # plane A solid, plane B 0
CAL = 1.0                                 # --cal: limits x 20 for a calibration run that measures the op times above


def say(s: str) -> None:
    _log_line(s, LOG)


def pattern(seed: int, n: int) -> bytes:
    """fw AwtoOhwNext: 16-bit Galois LFSR, 8 steps per byte, low byte out; start (seed << 8) | 0x5A."""
    s, out = (seed << 8) | LFSR_LOW, bytearray()
    for _ in range(n):
        for _ in range(LFSR_STEPS):
            s = (s >> 1) ^ LFSR_POLY if s & 1 else s >> 1
        out.append(s & 0xFF)
    return bytes(out)


def expected(seed: int, n: int, flags: int) -> bytes:
    """What a write op stores: the pattern, or its first BUF bytes repeated (F_REPEAT)."""
    if flags & F_REPEAT:
        return (pattern(seed, BUF) * (n // BUF + 1))[:n]
    return pattern(seed, n)


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


class Unit:
    """Real unit over debug slave 0x35 (dbg_link must be on)."""

    def __init__(self, bus: int, map_path: Path):
        import dbg_xdata as X
        import rtd_i2c_bridge as B
        import sw_timeline as T
        self.X = X
        self.io = B.Real(bus, allow_write=True, regread=True)
        self.base = T.sym(map_path, "g_stAwtoOsdHw")

    def wr(self, off: int, data: bytes) -> None:
        for i, v in enumerate(data):
            a = self.base + off + i
            if not (self.io.write(DEV8, 0x01, bytes([a >> 8])) and self.io.write(DEV8, 0x03, bytes([v]))
                    and self.io.write(DEV8, 0x3B, bytes([a & 0xFF]))):
                raise RuntimeError(f"debug write NAK at 0x{a:04X}")

    RD_TRIES = 40                             # a block read fails while the main loop is busy (cycle map variant: ~1 map rewrite per pass)

    def rd(self, off: int, n: int) -> bytes:
        r = None
        for _ in range(self.RD_TRIES):
            r = self.X.read_blocks(self.io, self.base + off, n)
            if r is not None:
                break
        if r is None:
            raise RuntimeError(f"debug read failed at 0x{self.base + off:04X}")
        return r

    def idle(self) -> None:
        pass                                  # the I2C transaction of the next poll is the pacing

    def now(self) -> float:
        return time.monotonic()

    def close(self) -> None:
        self.io.close()


class Sim:
    """Same ops in fw_sim (scripts/osd_render.Session): XDATA written / read directly, time advanced by idle()."""
    STEP_S = 0.005                            # sim time per poll

    def __init__(self, binp: Path, map_path: Path, rotate: bool):
        import ddc_sim as D
        import osd_render as R
        self.eng = D.DdcEngine()
        self.sess = R.Session(binp, map_path, "2160p60", devs=[self.eng])
        self.sess.boot()
        ddc = D.Mccs(self.sess.bus, self.eng)
        ddc.set(0xE0, 32)                     # settings row 32 disp_rotate through the paged pair
        ddc.set(0xE1, 1 if rotate else 0)
        self.sess.bus.wait(1.0)
        self.m = self.sess.bus.m
        self.base = self.m.addr("g_stAwtoOsdHw")

    def wr(self, off: int, data: bytes) -> None:
        self.m.wr(self.base + off, bytes(data))

    def rd(self, off: int, n: int) -> bytes:
        return bytes(self.m.rd(self.base + off, n))

    def idle(self) -> None:
        self.sess.bus.wait(self.STEP_S)

    def now(self) -> float:
        return self.sess.bus.now()

    def font(self) -> dict:
        return self.sess.model.st.font

    def close(self) -> None:
        self.sess.bus.close()


def op(dev, code: int, limit_s: float, *, mode=M_SDK, gap=0, flags=None, seed=0, addr=0, n=0, label="") -> dict:
    """Run one op; flags None = keep the current flags byte (F_HOLD survives). Reads always with the scale-up engine off
    (F_RD_SU): with it on, read-back returns junk (rows 0..14 read 01 10 00 instead of 80 11 28, unit 3 2026-11-18)."""
    if code in (OP_VERIFY, OP_READ, OP_CRC) and flags is not None:
        flags |= F_RD_SU
    p = bytes([mode, gap]) + (bytes([flags]) if flags is not None else dev.rd(O_FLAGS, 1)) + bytes([seed])
    dev.wr(O_MODE, p)
    dev.wr(O_ADDR, addr.to_bytes(2, "big") + n.to_bytes(2, "big"))
    seq0 = dev.rd(O_SEQ, 1)[0]
    dev.wr(O_GO, bytes([code]))
    t0 = dev.now()
    while True:
        dev.idle()
        try:
            h = dev.rd(O_GO, 2)
        except RuntimeError:                  # the block read is served by the main loop: busy while the op runs
            h = None
        if h is not None and h[0] == 0 and h[1] != seq0:
            break
        if dev.now() - t0 > limit_s:
            raise TimeoutError(f"op {code} {label}: not done after {dev.now() - t0:.2f} s (limit {limit_s:.2f} s)")
    raw = dev.rd(0, SIZE)
    be = lambda o: int.from_bytes(raw[o:o + 2], "big")
    return {"state": raw[O_STATE], "ovl": raw[O_OVL], "bad": be(O_BAD), "first": be(O_FIRST), "crc": be(O_CRC), "ms": be(O_MS), "frame": be(O_FRAME),
                "regs": dict(zip(REG_NAMES, raw[O_REGS:O_REGS + N_REGS])), "badb": raw[O_BADB:O_BADB + 8], "buf": raw[O_BUF:O_BUF + BUF], "run": raw[O_RUN],
                "host_s": dev.now() - t0}


def set_flags(dev, flags: int) -> None:
    dev.wr(O_FLAGS, bytes([flags]))


def lim_write(mode: int, nbytes: int, gap: int = 0) -> float:
    return CAL * MARGIN * (OP_FIXED_S + nbytes * (US_PER_WRITE_BYTE[mode] + gap * US_GAP_PASS) * 1e-6)


def lim_saver() -> float:
    return CAL * MARGIN * (OP_FIXED_S + SAVER_OP_S)


def lim_read(nbytes: int) -> float:
    return CAL * MARGIN * (OP_FIXED_S + nbytes * US_PER_READ_BYTE * 1e-6)


def regs_line(r: dict) -> str:
    return " ".join(f"{k}={v:02X}" for k, v in r["regs"].items()) + f" overlay={r['ovl']}"


def write_verify(dev, name: str, addr: int, words: int, mode: int, flags: int, seed: int, gap: int = 0) -> dict:
    """One case: pattern write, then read back M1 and M2. Returns the result row."""
    nb = words * WORD_B
    w = op(dev, OP_WRITE, lim_write(mode, nb, gap), mode=mode, gap=gap, flags=flags, seed=seed, addr=addr, n=nb, label=name)
    res = {"case": name, "mode": MODE_NAMES[mode], "gap": gap, "flags": flags, "addr": addr, "bytes": nb, "write_ms": w["ms"],
           "overlay": w["ovl"]}
    for mem, fl in (("M1", 0), ("M2", F_M2)):
        v = op(dev, OP_VERIFY, lim_read(nb), flags=(flags & (F_HOLD | F_REPEAT)) | fl, seed=seed, addr=addr, n=nb, label=name + " verify")
        res[mem] = (v["bad"], v["first"], v["badb"].hex(), v["ms"])
    ok = res["M1"][0] == 0 and res["M2"][0] == 0
    res["pass"] = ok
    say(f"  {'PASS' if ok else 'FAIL'} {name}: host {w['host_s']:.2f} s write, {res['M1'][3]} ms verify, {MODE_NAMES[mode]}{f' gap {gap}' if mode == M_GAP else ''}, flags 0x{flags:02X}, "
        f"words 0x{addr:04X}+{words}, {nb} B written in {w['ms']} ms ({w['ms'] * 1000.0 / nb:.2f} us/B), overlay {w['ovl']}; "
        f"M1 bad {res['M1'][0]} first {res['M1'][1]} {res['M1'][2]}; M2 bad {res['M2'][0]} first {res['M2'][1]} {res['M2'][2]}")
    if not ok:
        first = min(x for x in (res["M1"][1], res["M2"][1]) if x != 0xFFFF)
        shift_report(dev, addr, seed, first, flags)
    return res


def shift_report(dev, addr: int, seed: int, first: int, flags: int) -> None:
    """Read 18 words around the first bad byte; say whether the stored bytes are the pattern shifted (dropped / doubled bytes)."""
    w0 = addr + max(0, first // WORD_B - 3)
    r = op(dev, OP_READ, lim_read(BUF), flags=flags & F_HOLD, addr=w0, n=BUF // WORD_B, label="window")
    got = r["buf"]
    want = expected(seed, (w0 - addr) * WORD_B + BUF + 16, flags)[(w0 - addr) * WORD_B:]
    shifts = [k for k in range(-6, 7) if all(got[i] == want[i + k] for i in range(max(0, -k), BUF - 6) if 0 <= i + k < len(want))]
    say(f"    window words 0x{w0:04X}+18: got  {got.hex()}")
    say(f"    window words 0x{w0:04X}+18: want {want[:BUF].hex()}  pattern shift that matches the whole window: {shifts or 'none'}")


READ_GLITCHES = [0]                       # chunks whose two reads differed (a 1-byte read glitch was seen once, 2026-11-18 cycle run)
READ_TRIES = 4                            # reads of a chunk until two agree


def dump(dev, start: int, words: int, hold: int) -> bytes:
    """Each 18-word chunk read until two reads agree (read-back is not glitch-free; counted in READ_GLITCHES)."""
    out = bytearray()
    per = BUF // WORD_B
    for a in range(start, start + words, per):
        k = min(per, start + words - a)
        rd = lambda k=k, a=a: op(dev, OP_READ, lim_read(k * WORD_B), flags=hold, addr=a, n=k, label="dump")["buf"][:k * WORD_B]
        got = [rd(), rd()]
        while got[-1] != got[-2] and len(got) < READ_TRIES:
            got.append(rd())
        if got[-1] != got[-2]:
            raise RuntimeError(f"words 0x{a:04X}+{k}: {READ_TRIES} reads, no two in a row agree")
        READ_GLITCHES[0] += len(got) > 2
        out += got[-1]
    return bytes(out)


def sim_image(font: dict, start: int, words: int) -> bytes:
    return b"".join(bytes(font.get(a, [0, 0, 0])) for a in range(start, start + words))


# ---- OT-8: 24 x 36 cell mode (fw/test/testcmd.c AwtoOhwBig; docs/osd-hw-tests.md OT-8) ----
BG_ROWS, BG_COLS, BG_FONT, BG_WORDS = 4, 8, 37, 36           # map words 5..36, glyphs from 37, 36 words per glyph
BG_BUDGET_WORDS = 330 * BG_WORDS + 342                      # 12222 of 12288 words (docs/osd-hw-tests.md OT-8)
BG_HI = {226: 3, 227: 5, 328: 2, 329: 0}                    # glyph id -> pattern above the 8 base patterns (226 straddles word 8192)
BG_ROW2 = [226, 227, 328, 329, 3, 5, 2, 0]                  # row 2: cells 0..3 (high ids) must look like cells 4..7 (low ids)
BG_MASK = 0xFFFFFF


def big_word(p: int, k: int) -> int:
    """Pattern p word k (bit 23 = px 0 if row-major); twin of AwtoOhwBigWord."""
    return {0: 0xC00003 if k in (0, 35) else 0, 1: BG_MASK if k < 9 else 0, 2: 0x800000, 3: 1 << (23 - k % 24), 4: BG_MASK if k % 2 == 0 else 0,
            5: BG_MASK if k >= 23 else (BG_MASK << (23 - k)) & BG_MASK, 6: BG_MASK}.get(p, ((k & 0x3F) << 18) | 1)


def big_expected() -> dict:
    """Expected SRAM (word -> 3 bytes in port order) of the OT-8 screen: row commands, map, glyph words."""
    w = {r: bytes([0x80, 35, BG_COLS]) for r in range(BG_ROWS)}
    w[BG_ROWS] = bytes(3)
    for r in range(BG_ROWS):
        for c in range(BG_COLS):
            gid = BG_ROW2[c] if r == 2 else (4 if r == 3 else c)
            wd = 12 if r == 1 else 24
            fg = c + 1 if r == 3 else 2
            w[BG_ROWS + 1 + r * BG_COLS + c] = bytes([0x40 | wd | (gid >> 8) << 5, gid & 255, fg << 4 | 9])
    for gid, pat in {**{i: i for i in range(8)}, **BG_HI}.items():
        for k in range(BG_WORDS):
            v = big_word(pat, k)
            w[BG_FONT + BG_WORDS * gid + k] = bytes([v & 255, v >> 8 & 255, v >> 16])
    return w


def big_ranges() -> list:
    return [(0, BG_FONT + 8 * BG_WORDS)] + [(BG_FONT + BG_WORDS * g, 2 * BG_WORDS) for g in (226, 328)]


def big_compare(read, tag: str) -> list:
    """read(start, words) -> bytes. Differing words vs big_expected()."""
    exp, bad = big_expected(), []
    for start, n in big_ranges():
        img = read(start, n)
        for i in range(n):
            a = start + i
            if a in exp and img[i * 3:i * 3 + 3] != exp[a]:
                bad.append((a, img[i * 3:i * 3 + 3].hex(), exp[a].hex()))
    say(f"  {'PASS' if not bad else 'FAIL'} {tag}: {sum(n for _, n in big_ranges())} words read, {len(bad)} differ from the host twin"
        + "".join(f"\n    word {a}: got {g} want {e}" for a, g, e in bad[:6]))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--seed", type=int, default=0x3C)
    ap.add_argument("--no-rotate", action="store_true", help="sim without Rotate 180 (unit 3 stores Rotate 180)")
    ap.add_argument("--cal", action="store_true", help="calibration run: poll limits x 20, op times logged")
    ap.add_argument("tests", nargs="+")
    a = ap.parse_args()
    global CAL
    CAL = 20.0 if a.cal else 1.0
    import dbg_link
    import i2cbus
    i2cbus.require_unit(a.bus, a.serial)
    fails = 0
    with dbg_link.linked(a.bus, 10):
        dev = Unit(a.bus, a.map)
        try:
            for t in a.tests:
                say(f"== {t} ({a.map.name})")
                if t == "regs":
                    say("  " + regs_line(op(dev, OP_REGS, lim_read(0), label="regs")))
                elif t == "stop":
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                elif t in ("t1", "t2", "t3"):
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    say("  " + regs_line(op(dev, OP_REGS, lim_read(0), label="regs")))
                    cases = []
                    if t == "t1":
                        for nm in ("glyphs", "map"):
                            cases.append((f"t1 {nm} hidden", *RANGES[nm], M_SDK, 0))
                        cases.append(("t1 glyphs hidden repeat (timing)", *RANGES["glyphs"], M_SDK, F_REPEAT))
                    elif t == "t2":
                        for m in (M_DIRECT, M_TRIPLE):
                            for nm in ("glyphs", "map"):
                                cases.append((f"t2 {nm} hidden", *RANGES[nm], m, 0))
                                cases.append((f"t2 {nm} hidden repeat", *RANGES[nm], m, F_REPEAT))
                                cases.append((f"t2 {nm} hidden repeat EA off", *RANGES[nm], m, F_REPEAT | F_EA_OFF))
                    for c in cases:
                        r = write_verify(dev, *c, a.seed)
                        fails += not r["pass"]
                    if t == "t3":
                        for g in (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32):
                            r = write_verify(dev, "t3 gap", *RANGES["glyphs"], M_GAP, F_REPEAT, a.seed, gap=g)
                            fails += not r["pass"]
                elif t == "cycle":
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_CYCLE, lim_write(M_SDK, LD_IDS * BUF + 2 * BUF), n=1, label="cycle on")
                    t0 = dev.now()
                    while dev.now() - t0 < CYCLE_LOOK_S:            # one full round: writes per variant
                        dev.idle()
                    r = op(dev, OP_REGS, lim_read(0) + CYCLE_BAND_S, label="regs")
                    say(f"  cycle running: {r['bad']} writes after {CYCLE_LOOK_S:.0f} s (variants 2, 3, 4, 6 count glyphs / map passes / address sets)")
                elif t == "cyclestop":
                    op(dev, OP_CYCLE, lim_read(0) + CYCLE_BAND_S, n=0, label="cycle off")
                    img = dump(dev, 0, LD_END, 0)
                    bad = [g for g in range(LD_IDS) if img[(LD_FONT + LD_STRIDE * g) * WORD_B:(LD_FONT + LD_STRIDE * g + LD_STRIDE) * WORD_B] != LADDER_GLYPH]
                    fails += bool(bad)
                    say(f"  {'PASS' if not bad else 'FAIL'} cycle stopped; ladder glyphs in SRAM: {len(bad)} of {LD_IDS} differ {bad[:20]}")
                    for g in bad[:3]:
                        say(f"    glyph {g}: {img[(LD_FONT + LD_STRIDE * g) * WORD_B:(LD_FONT + LD_STRIDE * g + LD_STRIDE) * WORD_B].hex()}")
                elif t == "ladder":                             # T9 for a human: 2-bit ids 0..255 (16 x 16), plane A solid; left on screen
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_LADDER, lim_write(M_SDK, LD_IDS * BUF + 2 * BUF), label="ladder")
                    img = dump(dev, 0, LD_END, 0)
                    glyphs_ok = all(img[(LD_FONT + LD_STRIDE * g) * WORD_B:(LD_FONT + LD_STRIDE * g + LD_STRIDE) * WORD_B] == b"\xff" * 27 + b"\x00" * 27 for g in range(LD_IDS))
                    ids = [img[(17 + c) * WORD_B + 1] for c in range(256)]
                    say(f"  ladder stored: {'all 256 glyphs = plane A solid, plane B 0' if glyphs_ok else 'GLYPHS DIFFER'}; map ids {'0..255 (turned 180)' if ids == list(range(255, -1, -1)) else ids[:20]}")
                    sim = Sim(a.bin, a.map, not a.no_rotate)
                    try:
                        op(sim, OP_LADDER, 60.0, label="sim ladder")
                        import osd_render as R
                        st = sim.sess.snap()
                        png = OUT / "ladder_sim_viewer.png"
                        OUT.mkdir(parents=True, exist_ok=True)
                        R.render_snap(st, "black", 4).rotate(180).save(png)
                    finally:
                        sim.close()
                    say(f"  sim render: {png}")
                elif t in ("ot8", "ot8off"):                    # OT-8: 24 x 36 mode (3A43[6]) on / off; screen left on for a human
                    on = t == "ot8"
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_BIG, lim_write(M_SDK, 12 * BG_WORDS * WORD_B + 100), n=int(on), label="ot8")
                    bad = big_compare(lambda s_, n_: dump(dev, s_, n_, 0), "unit SRAM")
                    fails += bool(bad)
                    sim = Sim(a.bin, a.map, not a.no_rotate)
                    try:
                        op(sim, OP_BIG, 60.0, n=int(on), label="sim ot8")
                        sbad = big_compare(lambda s_, n_, sim=sim: sim_image(sim.font(), s_, n_), "sim SRAM")
                        fails += bool(sbad)
                        import osd_render as R
                        OUT.mkdir(parents=True, exist_ok=True)
                        im = R.render_snap(sim.sess.snap(), "black", 4)
                        im.save(OUT / f"{t}_sim.png")
                        im.rotate(180).save(OUT / f"{t}_sim_as_seen_unit3.png")
                    finally:
                        sim.close()
                    say(f"  sim pictures (row-major guess for the 24 x 36 layout): {OUT / (t + '_sim.png')} (as the OSD circuit draws), {OUT / (t + '_sim_as_seen_unit3.png')} (Rotate 180 stored: what unit 3 shows)")
                    say(f"  on screen: mode {'24 x 36' if on else 'OFF (12 x 18 reading of the same words)'}; read the picture per docs/osd-hw-tests.md OT-8")
                elif t == "ot8full":                            # OT-8 capacity: 12222 words (330 glyphs x 36 + map budget), M1 + M2
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    r = write_verify(dev, "ot8full 0..12221 direct", 0, BG_BUDGET_WORDS, M_DIRECT, F_HIDE, a.seed)
                    fails += not r["pass"]
                elif t == "t6":
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_PLANES, lim_read(BUF * 4), label="planes")
                    for g in range(4):                          # stored words of the 4 glyphs (font base 37)
                        r = op(dev, OP_READ, lim_read(BUF), addr=37 + 18 * g, n=18, label="planes glyph")
                        say(f"  glyph {g}: {r['buf'].hex()}")
                    say("  screen: SOLID = plane A only (first 9 words), BOXES = plane B only, PLUSES = both; palette c1 red, c2 green, c3 blue")
                else:
                    say(f"unknown test {t}")
                    fails += 1
        finally:
            dev.close()
    say(f"done: {fails} failing case(s); dump chunks whose first two reads differed: {READ_GLITCHES[0]}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
