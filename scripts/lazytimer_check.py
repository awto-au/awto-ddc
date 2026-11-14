#!/usr/bin/env python3
"""Differential fuzz of mcs51_core.c timers: an old core revision vs the working-tree core, dw8051 mode (awto-ddc#183).

usage: lazytimer_check.py [--old REV] [--seeds 200] [--chunks 200] [--seed0 0] [--cpu dw8051|8052]
- Builds `git show REV:scripts/mcs51_core.c` and scripts/mcs51_core.c into tmp/lazytimer/{old,new}.so (gcc -O2).
- Random images: timer SFR writes / reads / bit ops (TCON TMOD TLx THx CKCON T2CON T2MOD RCAP2 P1 P3 IE IP), DJNZ delay
  loops, MOVX / MUL / DIV fillers, ISRs on every vector that count entries and snapshot timer registers to IRAM.
- Both cores run the same chunks (random length, host sfr_write between some); after each chunk: pub fields, IRAM, SFRs
  must match. Seeds alternate the flash fetch-stall model on / off. First mismatch: seed, chunk, differing fields.
Log: tmp/logs/lazytimer_check.log
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sdcc_overlay import repo_root  # noqa: E402
from fastmachine import Pub  # noqa: E402

ROOT = repo_root()
LOG = ROOT / "tmp/logs/lazytimer_check.log"
OUT = ROOT / "tmp/lazytimer"
GCC_TIMEOUT_S = 60          # gcc -O2 of the core: < 2 s; 60 s = project host-process stall limit
MODEL = json.loads((HERE / "dw8051_model.json").read_text())

TSFR = [0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0x90, 0xB0]
VEC = [0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B, 0x43]


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def build(src: bytes, name: str) -> ctypes.CDLL:
    OUT.mkdir(parents=True, exist_ok=True)
    c, so = OUT / f"{name}.c", OUT / f"{name}.so"
    c.write_bytes(src)
    subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(c)], check=True, timeout=GCC_TIMEOUT_S)
    L = ctypes.CDLL(str(so))
    vp = ctypes.c_void_p
    L.core_new.restype, L.core_new.argtypes = vp, [ctypes.c_char_p, ctypes.c_uint32]
    L.core_free.argtypes = [vp]
    L.core_reset.argtypes = [vp]
    L.core_pub.restype, L.core_pub.argtypes = ctypes.POINTER(Pub), [vp]
    L.core_mem.restype, L.core_mem.argtypes = vp, [vp, ctypes.c_int]
    L.core_sfr_write.argtypes = [vp, ctypes.c_int, ctypes.c_int]
    L.core_set_dw.argtypes = [vp, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    L.core_set_fetch.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
    L.core_run.restype, L.core_run.argtypes = ctypes.c_int, [vp, ctypes.c_uint64]
    return L


def sfr_val(r: random.Random, a: int, quiet: bool) -> int:
    """Value for a timer SFR write; `quiet` seeds mostly avoid the per-instruction fallback (counter mode, level INTx)."""
    v = r.randrange(256)
    if a == 0x89 and quiet:
        v &= 0xBB                                  # timer mode, gate allowed
    if a == 0xB0 and quiet:
        v |= 0x0C                                  # INT0/INT1 pins high (no level IRQ)
    if a == 0x88 and quiet and r.random() < 0.7:
        v |= 0x05                                  # edge-triggered INTx
    if a == 0x88 and r.random() < 0.6:
        v |= 0x50                                  # TR0 TR1
    if a == 0xC8 and r.random() < 0.6:
        v |= 0x04                                  # TR2
    if a == 0xC8 and quiet:
        v &= ~0x02 & 0xFF
    if a == 0xC9:
        v &= 0x03
    if a in (0xCB, 0xCD, 0x8C, 0x8D) and r.random() < 0.5:
        v |= 0xF0 if r.random() < 0.5 else 0xFF    # short periods: many overflows
    return v


def gen(r: random.Random) -> bytes:
    quiet = r.random() < 0.6
    wts = [r.random() ** 3 for _ in TSFR]          # per-seed SFR mix: rare T2CON writes let T2MOD modes persist
    code = bytearray([0xFF] * 0x10000)
    code[0:3] = bytes([0x02, 0x01, 0x00])          # LJMP main
    isr = 0x7000
    for i, v in enumerate(VEC):
        code[v:v + 3] = bytes([0x02, isr >> 8, isr & 0xFF])
        body = bytearray([0x05, 0x30 + i])         # INC 30h+i
        src = r.choice([0x8A, 0x8C, 0x8B, 0x8D, 0xCC, 0xCD, 0x88, 0xC8])
        body += bytes([0x85, src, 0x38 + i])       # MOV 38h+i, timer reg
        if i == 5 and r.random() < 0.8:
            body += bytes([0x53, 0xC8, 0x3F])      # ANL T2CON, #3Fh (clear TF2 / EXF2)
        if i == 6:
            body += bytes([0x53, 0x91, 0xEF])      # ANL EXIF, #EFh
        if r.random() < 0.3:
            a = r.choice(TSFR)
            body += bytes([0x75, a, sfr_val(r, a, quiet)])
        body += bytes([0x32])                      # RETI
        code[isr:isr + len(body)] = body
        isr += 0x40
    pc, prog = 0x0100, bytearray()
    prog += bytes([0x90, 0x40, 0x00])              # MOV DPTR, #4000h
    k = 0
    while len(prog) < 0x5000:
        x = r.random()
        if x < 0.25:
            a = r.choice([0xA8, 0xB8, 0x8E]) if r.random() < 0.2 else r.choices(TSFR, wts)[0]
            v = sfr_val(r, a, quiet) if a in TSFR else (0x80 | r.randrange(128) if a == 0xA8 else r.randrange(256))
            if a == 0x8E:
                v = r.randrange(256)
            prog += bytes([0x75, a, v])
        elif x < 0.40:
            b = r.choice([0x88, 0xC8, 0xB0, 0x90]) + r.randrange(8)
            if quiet and b in (0xB2, 0xB3, 0xC9):
                b = 0x8C
            prog += bytes([r.choice([0xD2, 0xC2, 0xB2]), b])          # SETB / CLR / CPL bit
        elif x < 0.55:
            a = r.choice(TSFR)
            prog += bytes([0x85, a, 0x40 + (k & 0x3F)])               # MOV iram, timer reg
            k += 1
        elif x < 0.60:
            prog += bytes([0x10, r.choice([0x8D, 0x8F, 0xCF, 0xCE]), 0x00])   # JBC TFx, +0
        elif x < 0.65:
            a = r.choice(TSFR)
            prog += bytes([r.choice([0x05, 0x15]), a])                # INC / DEC dir
        elif x < 0.80:
            prog += bytes([0x7F, r.randrange(1, 256), 0xDF, 0xFE])    # MOV R7,#n; DJNZ R7,$
        elif x < 0.85:
            prog += bytes([0x75, 0xF0, r.randrange(1, 256), r.choice([0x84, 0xA4])])
        elif x < 0.90:
            prog += bytes([r.choice([0xE0, 0xF0])])                    # MOVX
        else:
            prog += bytes([0x00])
    prog += bytes([0x02, 0x01, 0x00])
    code[pc:pc + len(prog)] = prog
    return bytes(code)


class Core:
    def __init__(self, L, img: bytes, fetch: bool, cache: int, dw: bool = True):
        self.L, self.h = L, L.core_new(img, len(img))
        L.core_set_dw(self.h, int(dw), bytes(MODEL["cycles"]), MODEL["movx"]["base_cycles"], MODEL["irq_cycles"],
                      MODEL["clk_per_cycle"], MODEL["timer_clk_div"]["slow"], MODEL["timer_clk_div"]["fast"])
        if fetch and dw:
            ff = MODEL["flash_fetch"]
            L.core_set_fetch(self.h, ff["line_bytes"], ff["sets"], ff["ways"], ff["cmd_flash_clk"], ff["byte_flash_clk"],
                             ff["common_end"], bytes(MODEL["oplen"]))
        L.core_reset(self.h)
        self.p = L.core_pub(self.h).contents
        mv = lambda sp, n: (ctypes.c_uint8 * n).from_address(L.core_mem(self.h, sp))
        self.iram, self.sfr, self.xram = mv(0, 256), mv(1, 128), mv(2, 65536)
        self.xram[0xFDA0] = cache
        self.hooks = (ctypes.c_uint8 * (4 * 8192)).from_address(L.core_mem(self.h, 4))

    def state(self):
        p = self.p
        return {"instr": p.instr, "cycles": p.cycles, "nirq": p.nirq, "pc": p.pc, "clk": p.clk, "nlvl": p.nlvl,
                "irq_tail": p.irq_tail, "reason": p.reason, "nev": p.nev, "iram": bytes(self.iram), "sfr": bytes(self.sfr)}


def one(Lo, Ln, seed: int, chunks: int, dw: bool) -> str | None:
    r = random.Random(seed)
    img = gen(r)
    fetch, cache = seed % 2 == 1, r.choice([0, 1])
    a, b = Core(Lo, img, fetch, cache, dw), Core(Ln, img, fetch, cache, dw)
    hook = r.choice([None, 0x90, 0xB0])            # SFR write hook: event stops inside a run
    for c in (a, b):
        if hook:
            c.hooks[3 * 8192 + (hook >> 3)] |= 1 << (hook & 7)
    try:
        for i in range(chunks):
            n = r.choice([1, r.randrange(1, 50), r.randrange(1, 5000), r.randrange(1, 100000)])
            if r.random() < 0.1:
                ad = r.choice(TSFR)
                v = r.randrange(256)
                a.L.core_sfr_write(a.h, ad, v)
                b.L.core_sfr_write(b.h, ad, v)
            ra, rb = a.L.core_run(a.h, n), b.L.core_run(b.h, n)
            sa, sb = a.state(), b.state()
            if ra != rb or sa != sb:
                diff = [k for k in sa if sa[k] != sb[k]]
                det = []
                for k in diff:
                    if isinstance(sa[k], bytes):
                        j = next(j for j in range(len(sa[k])) if sa[k][j] != sb[k][j])
                        det.append(f"{k}[0x{j + (0x80 if k == 'sfr' else 0):02x}] old 0x{sa[k][j]:02x} new 0x{sb[k][j]:02x}")
                    else:
                        det.append(f"{k} old {sa[k]} new {sb[k]}")
                return f"seed {seed} chunk {i} (n {n}, fetch {fetch}): ret {ra}/{rb}; " + "; ".join(det)
        return None
    finally:
        a.L.core_free(a.h)
        b.L.core_free(b.h)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", default="main", help="git revision of the reference core")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--chunks", type=int, default=200)
    ap.add_argument("--cpu", choices=("dw8051", "8052"), default="dw8051")
    a = ap.parse_args()
    old = subprocess.run(["git", "-C", str(ROOT), "show", f"{a.old}:scripts/mcs51_core.c"], check=True, capture_output=True).stdout
    Lo, Ln = build(old, "old"), build((HERE / "mcs51_core.c").read_bytes(), "new")
    say(f"=== lazytimer_check {a.cpu} old {a.old} vs working tree: seeds {a.seed0}..{a.seed0 + a.seeds - 1}, {a.chunks} chunks")
    t0, bad, instr = time.time(), 0, 0
    for s in range(a.seed0, a.seed0 + a.seeds):
        e = one(Lo, Ln, s, a.chunks, a.cpu == "dw8051")
        if e:
            say("MISMATCH " + e)
            bad += 1
            if bad >= 5:
                break
    say(f"{'FAIL' if bad else 'PASS'}: {a.seeds} seeds, {bad} mismatching, {time.time() - t0:.1f} s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
