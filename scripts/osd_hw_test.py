#!/usr/bin/env python3
"""OSD SRAM hardware tests on the test unit (docs/osd-hw-tests.md): write paths, read-back, Scope 2 SRAM vs the simulator.

usage: osd_hw_test.py --bus B --serial S --map MAP [--bin BIN] TEST [TEST ...]
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c g_stAwtoOsdHw). The host drives the firmware over debug slave 0x35:
  params + ucGo = op, the main loop runs the op and clears ucGo. Read-back = 0x3A33 sram_read_en with the overlay off (the op does it).
  TESTs (PASS/FAIL criteria: docs/osd-hw-tests.md):
    regs   OSD register snapshot
    t1     pattern write through ScalerOsdDataPort, read back M1 + M2: Scope 2 glyph range, Asteroids range, map range
    t2     the same through direct back-to-back stores (loop, unrolled triples), OSD hidden / Scope 2 shown, EA on / off
    t3     direct + gap sweep: the smallest gap with 0 errors (run only when t2 fails)
    t7     Scope 2 SRAM at the end of frame F on the unit vs the simulator (--bin needed): held from the start, and after a free run
    t4     t7 started on top of Asteroids (no stop between)
    t8     Scope 2 held mid-frame: every cell shows its tile of the frame before or of the frame in progress
    rd     read-back with Scope 2 shown: overlay off / on / scale-up off (rows 0..14 are known)
    freeze Scope 2 held at a frame end (left on screen) + the sim render of that frame for a photo (+ the 4096-wrap render)
    cycle  T10 for a human: the ladder with a blue digit 1..6, variants 8 s each, looping until `cyclestop` (docs/osd-hw-tests.md)
    cyclestop  stop the cycle; check the ladder glyphs in SRAM are still as written
    ladder 2-bit ids 0..255 as a 16 x 16 grid, plane A solid (left on screen) + sim renders (as built, if the fetch wraps at 4096)
    t6     plane / colour screen for a human (left on screen)
    stop   saver off, OSD closed
Log: ./tmp/logs/osd_hw_test.log ; SRAM dumps: ./tmp/osd_hw/
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/osd_hw_test.log"
OUT = ROOT / "tmp/osd_hw"
DEV8 = 0x6A
# StAwtoOsdHw (fw/test/testcmd.c), big-endian WORDs
O_GO, O_SEQ, O_STATE, O_MODE, O_GAP, O_FLAGS, O_SEED, O_OVL, O_ADDR, O_N = 0, 1, 2, 3, 4, 5, 6, 7, 8, 10
O_BAD, O_FIRST, O_CRC, O_MS, O_FRAME, O_REGS, O_BADB, O_BUF = 12, 14, 16, 18, 20, 22, 31, 39
N_REGS, BUF = 9, 54
O_RUN = O_BUF + BUF
SIZE = O_RUN + 1
RUN_SCOPE2 = 3                            # g_ucAwtoSaverRun of Scope 2 (saver.c AWTO_SAVER_SCOPE2)
REG_NAMES = ["3A02", "3A0B", "3A17", "3A33", "3A34", "3A41", "0093", "0094", "006C"]
OP_WRITE, OP_VERIFY, OP_READ, OP_CRC, OP_WRBUF, OP_PLANES, OP_S2FRAMES, OP_REGS, OP_SAVER, OP_LADDER, OP_CYCLE = range(1, 12)
M_SDK, M_DIRECT, M_GAP, M_TRIPLE = 0, 1, 2, 3
MODE_NAMES = {M_SDK: "ScalerOsdDataPort", M_DIRECT: "direct loop", M_GAP: "direct+gap", M_TRIPLE: "direct triples"}
F_EA_OFF, F_M2, F_HIDE, F_HOLD, F_REPEAT, F_RD_OVL, F_RD_SU = 1, 2, 4, 8, 16, 32, 64
ST_OK = 1
LFSR_POLY, LFSR_LOW, LFSR_STEPS = 0xB400, 0x5A, 8
WORD_B = 3
# SRAM ranges (words): Scope 2 = scope_saver2.c (15 rows, 40 x 15 map from 16, 256 2-bit glyphs of 18 words from 616);
# Asteroids = AwtoOsdMap1 32 x 12 (1-bit glyph per cell from 12 + 1 + 384 = 397); top = the unused end of the 12288-word SRAM
S2_ROWS, S2_FS, S2_FONT, S2_IDS, S2_STRIDE = 15, 16, 616, 256, 18
S2_END = S2_FONT + S2_IDS * S2_STRIDE
AST_FONT, AST_CELLS = 397, 384
RANGES = {"s2glyphs": (S2_FONT, S2_IDS * S2_STRIDE), "s2map": (0, S2_FONT), "ast": (AST_FONT, AST_CELLS * 9), "top": (0x2000, 0x1000)}
SAVER_SCOPE2, SAVER_AST, SAVER_OFF = 4, 8, 0
WRAP_WORDS = 4096                         # freeze: hypothesis render, 2-bit glyph fetch wraps at 4096 words
WRAP_ID_MIN = (WRAP_WORDS - S2_FONT + S2_STRIDE - 1) // S2_STRIDE + 8   # a frame where the map uses ids well past that word
# poll limits: 1.25 x the measured worst case on unit 3 (docs/osd-hw-tests.md "op times"); expiry = FAIL, logged with the elapsed time
US_PER_WRITE_BYTE = {M_SDK: 46.2, M_DIRECT: 46.2, M_GAP: 46.2, M_TRIPLE: 46.2}   # worst per byte incl. the pattern refill (all modes)
US_GAP_PASS = 1.0                         # not measured (t3 not needed: t2 passed); estimate 1 us per delay pass
US_PER_READ_BYTE = 200.0                  # verify: 13824 B in 2734 ms worst (circuit off, scale-up off, two 3-byte reads per word)
SAVER_OP_S = 0.25                         # saver request served in the op: Scope 2 start 214 ms
OP_FIXED_S = 0.25                         # one main-loop pass (max gap 20 ms, health) + the I2C of param write + polls
S2_FRAME_S = 0.26                         # Scope 2 frame with the poll held: 228 ms worst (end of frame 1 incl. the first show)
MARGIN = 1.25
SIM_SAVER_S = 5.0                         # sim: fw seconds for a saver start (the sim runs slower than the unit, not faster)
CYCLE_LOOK_S = 58.0                       # cycle: 7 variants x 8 s, then the write counter is read
CYCLE_BAND_S = 0.02                       # cycle: a main pass may hold one 8 ms band or one DVS wait (16.7 ms at 60 Hz)
LADDER_GLYPH = bytes([0xFF]) * 27 + bytes(27)   # plane A solid, plane B 0
CAL = 1.0                                 # --cal: limits x 20 for a calibration run that measures the op times above


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


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
        import rtd_i2c_bridge as B
        import sw_timeline as T
        import dbg_xdata as X
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
        import osd_render as R
        import ddc_sim as D
        self.eng = D.DdcEngine()
        self.sess = R.Session(binp, map_path, "2160p60", devs=[self.eng])
        self.sess.boot()
        ddc = D.Mccs(self.sess.bus, self.eng)
        ddc.set(0xE0, 32)                     # settings row 32 disp_rotate through the paged pair (saver_dirty_start.py)
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
    return dict(state=raw[O_STATE], ovl=raw[O_OVL], bad=be(O_BAD), first=be(O_FIRST), crc=be(O_CRC), ms=be(O_MS), frame=be(O_FRAME),
                regs=dict(zip(REG_NAMES, raw[O_REGS:O_REGS + N_REGS])), badb=raw[O_BADB:O_BADB + 8], buf=raw[O_BUF:O_BUF + BUF], run=raw[O_RUN],
                host_s=dev.now() - t0)


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
        rd = lambda: op(dev, OP_READ, lim_read(k * WORD_B), flags=hold, addr=a, n=k, label="dump")["buf"][:k * WORD_B]
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


def wait_scope2(dev) -> None:
    """The saver poll serves the request on its next pass (Scope 2 start ~214 ms): wait for it before a hold."""
    t0 = dev.now()
    lim = lim_saver() if isinstance(dev, Unit) else SIM_SAVER_S
    while op(dev, OP_REGS, lim, label="saver run?")["run"] != RUN_SCOPE2:
        if dev.now() - t0 > lim:
            raise TimeoutError(f"Scope 2 not running after {dev.now() - t0:.2f} s (limit {lim_saver():.2f} s)")


def run_frames(dev, frames: int, free_s: float) -> int:
    """Scope 2 on (saver request), free run free_s (0 = hold at once), hold, finish the current frame + `frames` more."""
    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_SCOPE2, label="scope2 on")
    wait_scope2(dev)
    t0 = dev.now()
    while dev.now() - t0 < free_s:
        dev.idle()
    set_flags(dev, F_HOLD)
    r = op(dev, OP_S2FRAMES, MARGIN * (OP_FIXED_S + (frames + 1) * S2_FRAME_S), n=frames, label="s2 frames")
    if r["state"] != ST_OK:
        raise RuntimeError(f"S2FRAMES state {r['state']}")
    return r["frame"]


def diff_regions(unit: bytes, sim: bytes, start: int) -> list:
    """Words that differ: (word, unit bytes, sim bytes)."""
    return [(start + i // WORD_B, unit[i:i + WORD_B], sim[i:i + WORD_B]) for i in range(0, len(unit), WORD_B) if unit[i:i + WORD_B] != sim[i:i + WORD_B]]


def describe(word: int) -> str:
    if word < S2_ROWS + 1:
        return f"row cmd {word}"
    if word < S2_FONT:
        c = word - S2_FS
        return f"map cell {c} (row {c // 40} col {c % 40})"
    g = word - S2_FONT
    return f"glyph {g // S2_STRIDE} plane {'AB'[g % S2_STRIDE // 9]} word {g % 9}"


def t7_compare(unit_dev, a, frame: int, tag: str, prior: int | None, rotate: bool) -> bool:
    us = dump(unit_dev, 0, S2_END, F_HOLD)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}_unit_f{frame}.bin").write_bytes(us)
    sim = Sim(a.bin, a.map, rotate)
    try:
        if prior is not None:
            op(sim, OP_SAVER, 5.0, flags=0, n=prior, label="sim prior")
            sim.sess.bus.wait(4.0)
        op(sim, OP_SAVER, 5.0, flags=0, n=SAVER_SCOPE2, label="sim scope2 on")
        wait_scope2(sim)
        set_flags(sim, F_HOLD)
        got = op(sim, OP_S2FRAMES, 600.0, n=0, label="sim frames")["frame"]
        while got < frame:
            got = op(sim, OP_S2FRAMES, 600.0, n=0, label="sim frames")["frame"]
        ss = sim_image(sim.font(), 0, S2_END)
    finally:
        sim.close()
    (OUT / f"{tag}_sim_f{got}.bin").write_bytes(ss)
    if got != frame:
        say(f"  FAIL {tag}: sim reached frame {got}, unit frame {frame}: not comparable")
        return False
    d = diff_regions(us, ss, 0)
    regions = {}
    for w, u, s in d:
        k = describe(w).split(" ")[0] + (" " + describe(w).split(" ")[1] if describe(w).startswith("row") else "")
        regions[k] = regions.get(k, 0) + 1
    say(f"  {'PASS' if not d else 'FAIL'} {tag}: frame {frame}, {S2_END} words, {len(d)} differ {regions}")
    for w, u, s in d[:40]:
        say(f"    0x{w:04X} {describe(w)}: unit {u.hex()} sim {s.hex()}")
    return not d


def cells(img: bytes) -> list:
    """Per map cell: (char command, the 18 glyph words it shows) from an SRAM image of words 0..S2_END."""
    w = lambda a: img[a * WORD_B:(a + 1) * WORD_B]
    out = []
    for c in range(S2_FONT - S2_FS):
        cmd = w(S2_FS + c)
        out.append((cmd, b"".join(w(S2_FONT + S2_STRIDE * cmd[1] + k) for k in range(S2_STRIDE))))
    return out


def sim_frame_end(a, frame: int, rotate: bool) -> bytes:
    sim = Sim(a.bin, a.map, rotate)
    try:
        op(sim, OP_SAVER, 5.0, flags=0, n=SAVER_SCOPE2, label="sim scope2 on")
        wait_scope2(sim)
        set_flags(sim, F_HOLD)
        got = 0
        while got < frame:
            got = op(sim, OP_S2FRAMES, 600.0, n=0, label="sim frames")["frame"]
        return sim_image(sim.font(), 0, S2_END)
    finally:
        sim.close()


def t8_midframe(dev, a, free_s: float, rotate: bool) -> bool:
    """Hold Scope 2 mid-frame (shown, running), dump; every cell must show its tile of the frame before or of the frame in progress."""
    set_flags(dev, 0)
    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_SCOPE2, label="scope2 on")
    wait_scope2(dev)
    t0 = dev.now()
    while dev.now() - t0 < free_s:
        dev.idle()
    set_flags(dev, F_HOLD)
    f = op(dev, OP_REGS, lim_read(0), label="regs")["frame"]
    mid = dump(dev, 0, S2_END, F_HOLD)
    e0, e1 = sim_frame_end(a, f - 1, rotate), sim_frame_end(a, f, rotate)
    cm, c0, c1 = cells(mid), cells(e0), cells(e1)
    bad = [c for c in range(len(cm)) if cm[c] not in (c0[c], c1[c])]
    say(f"  {'PASS' if not bad else 'FAIL'} t8 mid-frame (held after {free_s} s, frame {f} in progress): {len(bad)} of {len(cm)} cells show "
        f"neither their frame {f - 1} nor their frame {f} tile: {bad[:40]}")
    set_flags(dev, 0)
    return not bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--seed", type=int, default=0x3C)
    ap.add_argument("--frames", type=int, default=2, help="t7: frames driven after the hold")
    ap.add_argument("--free-s", type=float, default=6.0, help="t7: free-running seconds before the hold (second case)")
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
                        for nm in ("s2glyphs", "ast", "s2map"):
                            cases.append((f"t1 {nm} hidden", *RANGES[nm], M_SDK, 0))
                        cases.append(("t1 s2glyphs hidden repeat (timing)", *RANGES["s2glyphs"], M_SDK, F_REPEAT))
                    elif t == "t2":
                        for m in (M_DIRECT, M_TRIPLE):
                            for nm in ("s2glyphs", "s2map"):
                                cases.append((f"t2 {nm} hidden", *RANGES[nm], m, 0))
                                cases.append((f"t2 {nm} hidden repeat", *RANGES[nm], m, F_REPEAT))
                                cases.append((f"t2 {nm} hidden repeat EA off", *RANGES[nm], m, F_REPEAT | F_EA_OFF))
                    for c in cases:
                        r = write_verify(dev, *c, a.seed)
                        fails += not r["pass"]
                    if t == "t2":                           # with Scope 2 on screen (scaled, fetching): write the unused top of SRAM
                        run_frames(dev, 0, 0.0)
                        say("  shown: " + regs_line(op(dev, OP_REGS, lim_read(0), label="regs")))
                        for m in (M_SDK, M_DIRECT, M_TRIPLE):
                            for fl in (F_HOLD | F_REPEAT, F_HOLD | F_REPEAT | F_EA_OFF):
                                r = write_verify(dev, f"t2 top shown{' EA off' if fl & F_EA_OFF else ''}", *RANGES["top"], m, fl, a.seed)
                                fails += not r["pass"]
                        set_flags(dev, 0)
                        op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    if t == "t3":
                        for g in (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32):
                            r = write_verify(dev, "t3 gap", *RANGES["s2glyphs"], M_GAP, F_REPEAT, a.seed, gap=g)
                            fails += not r["pass"]
                elif t in ("t7", "t4"):
                    if not a.bin:
                        sys.exit("t7 / t4 need --bin (the same image runs in the simulator)")
                    prior = SAVER_AST if t == "t4" else None
                    cases = [("held", 0.0)] if t == "t4" else [("held", 0.0), ("free", a.free_s)]
                    for tag, free in cases:
                        set_flags(dev, 0)
                        op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                        if prior is not None:
                            op(dev, OP_SAVER, lim_saver(), flags=0, n=prior, label="asteroids on")
                            t0 = dev.now()
                            while dev.now() - t0 < 4.0:        # Asteroids runs (writes its glyphs over Scope 2's SRAM)
                                dev.idle()
                        fr = run_frames(dev, a.frames, free)
                        say(f"  unit {tag}: Scope 2 held at the end of frame {fr}")
                        fails += not t7_compare(dev, a, fr, f"{t}_{tag}", prior, not a.no_rotate)
                        set_flags(dev, 0)                       # saver runs on (shown) until the next case / stop
                elif t == "rd":                                 # read-back conditions with Scope 2 shown: row commands are known (80 11 28)
                    set_flags(dev, 0)
                    run_frames(dev, 0, 0.0)
                    for nm, fl in (("overlay off", 0), ("overlay on", F_RD_OVL), ("overlay off + scale-up off", F_RD_SU)):
                        r = op(dev, OP_READ, lim_read(BUF), flags=F_HOLD | fl, addr=0, n=18, label="rd rows")
                        ok = r["buf"][:S2_ROWS * WORD_B] == bytes([0x80, 0x11, 0x28]) * S2_ROWS
                        fails += not ok
                        say(f"  {'PASS' if ok else 'FAIL'} rd {nm}: words 0..17 = {r['buf'].hex()}")
                    set_flags(dev, 0)
                elif t == "t8":
                    if not a.bin:
                        sys.exit("t8 needs --bin")
                    for fs in (a.free_s, a.free_s + 1.37):
                        fails += not t8_midframe(dev, a, fs, not a.no_rotate)
                elif t == "freeze":                             # for a photo: Scope 2 held (static) at a frame end + the sim render of that frame
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    fr = run_frames(dev, 0, a.free_s)
                    us = dump(dev, 0, S2_END, F_HOLD)
                    while max(c[0][1] for c in cells(us)) < WRAP_ID_MIN:          # a frame that shows glyphs past word 4096 too
                        fr = op(dev, OP_S2FRAMES, MARGIN * (OP_FIXED_S + S2_FRAME_S), n=0, label="s2 frame")["frame"]
                        us = dump(dev, 0, S2_END, F_HOLD)
                    sim = Sim(a.bin, a.map, not a.no_rotate)
                    try:
                        op(sim, OP_SAVER, 5.0, flags=0, n=SAVER_SCOPE2, label="sim scope2 on")
                        wait_scope2(sim)
                        set_flags(sim, F_HOLD)
                        got = 0
                        while got < fr:
                            got = op(sim, OP_S2FRAMES, 600.0, n=0, label="sim frames")["frame"]
                        import osd_render as R
                        OUT.mkdir(parents=True, exist_ok=True)
                        png = OUT / f"freeze_sim_f{fr}_viewer.png"
                        st = sim.sess.snap()
                        R.render_snap(st, "black", 4).rotate(180).save(png)    # panel turned 180 for the viewer (Rotate 180)
                        for a_ in [x for x in st.font if S2_FONT <= x < S2_END and x >= WRAP_WORDS]:   # hypothesis render: glyph fetch wraps at 4096 words
                            st.font[a_] = list(st.font.get(a_ % WRAP_WORDS, [0, 0, 0]))
                        R.render_snap(st, "black", 4).rotate(180).save(png.with_name(png.stem + "_if_wrap4096.png"))
                        same = sim_image(sim.font(), 0, S2_END) == us
                    finally:
                        sim.close()
                    say(f"  frozen at the end of frame {fr} (shown, saver poll held); unit SRAM {'==' if same else '!='} sim SRAM; sim render as the viewer sees it: {png}")
                elif t == "cycle":
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_CYCLE, lim_write(M_SDK, S2_IDS * BUF + 2 * BUF), n=1, label="cycle on")
                    t0 = dev.now()
                    while dev.now() - t0 < CYCLE_LOOK_S:            # one full round: writes per variant
                        dev.idle()
                    r = op(dev, OP_REGS, lim_read(0) + CYCLE_BAND_S, label="regs")
                    say(f"  cycle running: {r['bad']} writes after {CYCLE_LOOK_S:.0f} s (variants 2, 3, 4, 6 count glyphs / map passes / address sets)")
                elif t == "cyclestop":
                    op(dev, OP_CYCLE, lim_read(0) + CYCLE_BAND_S, n=0, label="cycle off")
                    img = dump(dev, 0, S2_END, 0)
                    bad = [g for g in range(S2_IDS) if img[(S2_FONT + S2_STRIDE * g) * WORD_B:(S2_FONT + S2_STRIDE * g + S2_STRIDE) * WORD_B] != LADDER_GLYPH]
                    fails += bool(bad)
                    say(f"  {'PASS' if not bad else 'FAIL'} cycle stopped; ladder glyphs in SRAM: {len(bad)} of {S2_IDS} differ {bad[:20]}")
                    for g in bad[:3]:
                        say(f"    glyph {g}: {img[(S2_FONT + S2_STRIDE * g) * WORD_B:(S2_FONT + S2_STRIDE * g + S2_STRIDE) * WORD_B].hex()}")
                elif t == "ladder":                             # T9 for a human: 2-bit ids 0..255 (16 x 16), plane A solid; left on screen
                    set_flags(dev, 0)
                    op(dev, OP_SAVER, lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
                    op(dev, OP_LADDER, lim_write(M_SDK, S2_IDS * BUF + 2 * BUF), label="ladder")
                    img = dump(dev, 0, S2_END, 0)
                    glyphs_ok = all(img[(S2_FONT + S2_STRIDE * g) * WORD_B:(S2_FONT + S2_STRIDE * g + S2_STRIDE) * WORD_B] == b"\xff" * 27 + b"\x00" * 27 for g in range(S2_IDS))
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
                        for a_ in [x for x in st.font if S2_FONT <= x < S2_END and x >= WRAP_WORDS]:
                            st.font[a_] = list(st.font.get(a_ % WRAP_WORDS, [0, 0, 0]))
                        R.render_snap(st, "black", 4).rotate(180).save(png.with_name(png.stem + "_if_wrap4096.png"))
                    finally:
                        sim.close()
                    say(f"  sim renders: {png} and {png.stem}_if_wrap4096.png")
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
