#!/usr/bin/env python3
"""Offline guard: do the busy-wait delay loops of a built image still have the cycle counts they were calibrated for? (#53.6, #54)

usage: delay_cal_check.py BIN MAP [--vendor IMG] [--stages REF_BIN REF_MAP]
  The SDK delay macros (DELAY_5US / DELAY_XUS and the _EXINT copies, ScalerDelay5us) are counted loops: N (set by
  ScalerMcu5usDelayCalc) was calibrated by Realtek against Keil's code. A compiler that emits a different loop silently
  changes every delay in the image (and the ISR ones: DELAY_XUS_EXINT in the EXINT0 PHY set, DELAY_30US_EXINT in EXINT1).
  1. Scan: linear sweep of every code chunk (fw_link_check.Image); each use of the delay variables must sit inside a known
     loop shape (`mov v,base; djnz v,$` and the DELAY_XUS nest). Another modification of a counter = FAIL (shape changed).
  2. Count: each distinct shape is executed in ucsim (real bytes of the image, bank loaded, IE off) with the booted N; cycles =
     sum over the executed instructions of the DW8051 cycle model below, cross-checked against a static sum.
  3. Compare: against the same shape in the vendor Keil image (--vendor, default the unit-3 dump): equal cycles per
     iteration and per entry, tolerance TOL_REF; and the model time against the nominal (5 us / 4*imm us), TOL_NOM.
  --stages: boot both images in ucsim and compare diag stage times (the T3-wait test must not move any stage), TOL_STAGE.
Cycle model [likely, docs/reversing/realtek-rtd/mcu-8051.md]: DW8051, 4 clocks per cycle, 87.7 MHz MCU clock; cycles =
  instruction bytes (djnz d,r = 3 as in the SDK delay formula 12 clocks per iteration), MOVX = 2, LCALL/RET = 4.
Log: tmp/logs/delay_cal_check.log   Exit 1 on any FAIL.
"""
import argparse
import os
import re
import select
import sys
from collections import Counter, defaultdict
from pathlib import Path

import chip_mem as CM
from _log import Logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d8051
import fw_link_check as L
import fw_sim as F

ROOT = F.ROOT
VENDOR = Path.home() / "vendors/realtek/analysis/dumps/jxc-4k-flash-AWT26110003-20261104-201610.bin"
CYCLES_PER_US = 87.7 / 4            # DW8051: MCU clock 87.7 MHz (M2PLL 350.8 / 4), 4 clocks per machine cycle
# TOL_REF: the same loop in Keil's code must cost the same: any difference is a codegen change, 5 % covers rounding only.
# TOL_NOM: the cycle model runs ~20 % fast against hardware (unit 3, 2026-11-06: N=26 loop 5.47 us incl. ISR, model 4.1 us),
#   so the model time may sit between 70 % and 110 % of nominal; refine from a clean hardware run.
# TOL_STAGE / TOL_ACTIVE: sim stage times shift by <= 1 tick when code moves (2 ms); the ACTIVE time is polled every 20 k instr (~5 ms).
TOL_REF, TOL_NOM, TOL_STAGE, TOL_ACTIVE = 0.05, (0.70, 1.10), 2, 5
MAX_STEPS = 400_000                 # DELAY_XUS(1000) is 250 x 21 iterations = 5.3 k steps; guard against a runaway
DELAY_VARS = {"base5": "d_g_ucDelay5usN_Base", "basex": "d_isr_g_ucDelayXusN_Base"}
ALLOW_FN = ("AwtoDelayLoops", "AwtoDelayXus")     # the only code allowed to loop on the delay bases
LOG = None


def log(s):
    LOG.say(s)


def dw_cycles(op: int, n: int) -> int:
    if op in (0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3):
        return 2
    if op in (0x12, 0x22, 0x32) or op & 0x1F == 0x11:
        return 4
    return n


def static_cycles(code: bytes) -> int:
    off, tot = 0, 0
    while off < len(code):
        ins = d8051.decode(code, off, 0)
        tot += dw_cycles(code[off], ins.n); off += ins.n
    return tot


def var_addrs(map_text: str) -> dict:
    out = {}
    for k, name in DELAY_VARS.items():
        m = re.search(rf"^\s+([0-9A-F]{{8}})\s+_{name[:31]}\w*\s", map_text, re.MULTILINE)      # the map cuts the symbol at 32 chars incl. the underscore
        if not m:
            raise SystemExit(f"_{name} not in the map")
        out[k] = int(m.group(1), 16)
    return out


def shapes(v: dict) -> dict:
    """name -> regex over code bytes. Every loop counter is a register Rn (12 clk per count): single loop `mov Rn,base; djnz Rn,$`;
    polling form `mov Rn,base; L: dec Rn; mov a,Rn; jz out; sjmp L`; nest (DELAY_XUS): `mov Rm,#i; mov Rn,base; djnz Rn,$; djnz Rm,nest`."""
    h = lambda x: re.escape(bytes([x]))
    r8 = range(8)
    e = lambda *x: re.escape(bytes(x))
    S = {}
    for tag, base in (("5us", "base5"), ("xus_base", "basex")):
        S[tag] = re.compile(b"|".join(e(0xA8 + n) + h(v[base]) + e(0xD8 + n, 0xFE) for n in r8), re.DOTALL)
        S[tag + "_dec"] = re.compile(b"|".join(e(0xA8 + n) + h(v[base]) + e(0x18 + n, 0xE8 + n, 0x60) + b"(.)\\x80\\xf8" for n in r8), re.DOTALL)
    S["xus"] = re.compile(b"|".join(e(0x78 + m) + b"(.)" + e(0xA8 + n) + h(v["basex"]) + e(0xD8 + n, 0xFE, 0xD8 + m, 0xFA)
                                    for n in r8 for m in r8 if n != m), re.DOTALL)
    return S


def vendor_shapes(img: bytes) -> Counter:
    """Keil's loops in the vendor image: same shapes with its own addresses. Counter of (kind, imm)."""
    c = Counter()
    for m in re.finditer(rb"\x75(.)(.)\x85(.)(.)\xd5\4\xfd\xd5\1\xf7", img, re.DOTALL):
        c[("xus", m.group(2)[0])] += 1
    for m in re.finditer(rb"\x85(.)(.)\xd5\2\xfd", img, re.DOTALL):
        c[("single", 0)] += 1
    return c


def pattern_cycles(kind: str, n_single: int, n_base: int, imm: int) -> int:
    """Model cycles of the shape from its instruction costs: single = mov Rn,d (2) + N x djnz Rn (3); nest = mov Rm,#i (2) +
    imm x (mov Rn,d (2) + Nb x djnz Rn (3) + djnz Rm (3))."""
    if kind == "single":
        return 2 + 3 * n_single
    return 2 + imm * (2 + 3 * n_base + 3)


def scan(im: "L.Image", v: dict, S: dict):
    """(sites {tag: [(chunk, addr16, imm, end offset from the site start)]}, bad [(chunk name, addr, text)]).
    bad = a counted loop on a delay base outside AwtoDelayLoops / AwtoDelayXus."""
    sites = defaultdict(list)
    bad = []
    for c in im.chunks:
        if c["kind"] != "fn":
            continue
        code, base = im.code(c), c["addr"] & 0xFFFF
        cover = set()
        for tag, rx in sorted(S.items(), key=lambda kv: not kv[0].startswith("xus") or kv[0].startswith("xus_base")):
            for m in rx.finditer(code):
                if any(x in cover for x in range(m.start(), m.end())):
                    continue
                grp = m.lastindex and m.group(m.lastindex)[0]
                if tag == "xus":
                    imm, end = grp, len(m.group(0))
                elif tag.endswith("_dec"):
                    imm, end = 0, 6 + (grp - 256 if grp > 127 else grp)       # JZ at +4 leaves the loop; its target is the end
                else:
                    imm, end = 0, 4
                sites[tag].append((c, base + m.start(), imm, end))
                cover.update(range(m.start(), m.end()))
        insns = [item[1] for item in L.sweep(code, base) if item[0] == "i"]
        for k, ins in enumerate(insns):                   # `mov Rn,base`, a few straight-line moves, then `djnz Rn,$` (code motion)
            if ins.off in cover or not 0xA8 <= ins.raw[0] <= 0xAF or ins.raw[1] not in (v["base5"], v["basex"]):
                continue
            for j in range(k + 1, min(k + 12, len(insns))):
                nx = insns[j]
                if nx.raw[0] == 0xD8 + ins.raw[0] - 0xA8 and nx.target == nx.addr:
                    tag = ("5us" if ins.raw[1] == v["base5"] else "xus_base") + "_moved"
                    sites[tag].append((c, ins.addr, 0, nx.addr + nx.n - ins.addr))
                    cover.update(range(ins.off, nx.off + nx.n))
                    break
                if nx.target is not None or nx.raw[0] in (0x22, 0x32, 0x73):
                    break
    for tag, grp in sites.items():                        # every counted loop lives in fw/timer/delay.c: an inline copy is a bypass
        bad += [(c["name"], addr, f"inline {tag} loop") for c, addr, _imm, _end in grp if not c["name"].lstrip("_").startswith(ALLOW_FN)]
    return sites, bad


def boot(img: bytes, mapp: Path, be: bool, tag: str, cal: bool = True):
    """ucsim booted to diag stage 8 and, with cal, past the panel T3 wait (usT3Wait64 set). Returns (session, diag dict, iram bases)."""
    import rtd_diag
    _sym, _where = F.parse_map(mapp.read_text(errors="replace"), img)
    flash = F.FlashPort(img)
    s = F.open_native(img, ROOT / "tmp/fwsim" / tag, F._Null(), flash, [])
    d = None
    for _ in range(80):
        F.run_chunk(s, flash, 1_000_000)
        blk = F.read_diag(s)
        d = rtd_diag.decode(blk, be) if blk else None
        if d and d["stage"] >= 8 and (not cal or d["t3_64"]):      # stage 8 is marked before the T3 wait
            return s, d
    raise SystemExit(f"{tag}: boot did not reach stage 8")


def sync(s, cmd: str = "") -> str:
    """Send cmd, then wait for an echo marker: everything the command printed (stale output is dropped first)."""
    s.send("echo @@SYNC0"); s.read_until(rb"(?:^|\n)@@SYNC0\n", 10); s.buf = b""
    if cmd:
        s.send(cmd)
    s.send("echo @@SYNC1")
    return s.read_until(rb"(?:^|\n)@@SYNC1\n", 30) or ""


def iram(s, a: int, n: int) -> bytes:
    out = sync(s, f"dump iram 0x{a:x} 0x{a + n - 1:x}")
    m = re.search(rf"0x[0-9a-f]+\s+((?:[0-9a-f]{{2}} ){{{n}}})", out or "")
    if not m:
        raise SystemExit(f"iram dump 0x{a:x}+{n} unreadable: {out!r}")
    return bytes.fromhex(m.group(1).replace(" ", ""))


def run_site(s, img: bytes, bank: int, pc: int, end: int, setup: dict, expect_steps: int) -> tuple[int, int]:
    """Execute [pc, end) in ucsim: setup = {iram addr: value}. Returns (model cycles, steps)."""
    sync(s, "delete")
    s.send("set memory sfr 0xa8 0")                      # IE: no interrupt inside the measured loop
    s.send(f"set memory xram 0xffff {bank}")
    for a, val in setup.items():
        s.send(f"set memory iram 0x{a:x} 0x{val:x}")
    sync(s, f"pc 0x{pc:x}")
    cyc, steps, cur = 0, 0, pc
    raw = b""
    s.buf = b""
    batch = max(8, min(2000, expect_steps + 4))
    while cur != end:
        s.buf = b""
        s.p.stdin.write(("step 1\n" * batch).encode()); s.p.stdin.flush()
        got = 0
        while got < batch:
            r, _, _ = select.select([s.p.stdout], [], [], 20)
            if not r:
                raise SystemExit("ucsim stopped answering")
            raw += os.read(s.p.stdout.fileno(), 1 << 20)
            got = raw.count(b"\nF 0x")
        pcs = [int(x, 16) for x in re.findall(rb"Stop at 0x([0-9a-f]+)", raw)]
        raw = b""
        for nxt in pcs:
            op = img[bank * F.BANK + cur] if cur >= 0 else 0
            n = d8051.decode(img, bank * F.BANK + cur, 0).n
            cyc += dw_cycles(op, n); steps += 1
            cur = nxt
            if cur == end:
                break
            if steps > MAX_STEPS:
                raise SystemExit(f"site 0x{pc:04x} did not reach 0x{end:04x} in {MAX_STEPS} steps")
    return cyc, steps


def known_deviations() -> dict:
    f = ROOT / "re/delay_cal_known.tsv"
    return {l.split("\t")[0]: l.split("\t", 1)[1] for l in f.read_text().splitlines() if l and not l.startswith("#")} if f.exists() else {}


def check_shapes(im, img, mapp, be, vend: bytes, rep) -> bool:
    v = var_addrs(mapp.read_text(errors="replace"))
    S = shapes(v)
    sites, bad = scan(im, v, S)
    known = known_deviations()
    ok = True
    log("sites found: " + ", ".join(f"{t} {len(x)}" for t, x in sorted(sites.items())) + f"; unrecognised counter uses: {len(bad)}")
    for name, addr, text in bad[:20]:
        log(f"FAIL unrecognised use of a delay counter in {name} at 0x{addr:04x}: {text}")
    ok &= not bad
    s, d = boot(img, mapp, be, mapp.stem + "-dcc", cal="_AwtoDiagPanelT3Wait" in mapp.read_text(errors="replace"))
    bases = iram(s, min(v["base5"], v["basex"]), 2)                # a 1-byte dump prints nothing
    n5, nx = bases[v["base5"] - min(v["base5"], v["basex"])], bases[v["basex"] - min(v["base5"], v["basex"])]
    log(f"booted N: DELAY_5US base {n5}, DELAY_XUS base {nx} (diag ucDelay5usN {d['d5']})")
    vc = vendor_shapes(vend) if vend else Counter()
    if vc:
        log(f"vendor Keil image: nest shapes {sum(n for (k, _), n in vc.items() if k == 'xus')}, single loops {vc[('single', 0)]} "
            f"(same byte shapes as ours: mov d,d; djnz d,$ / mov d,#i; mov d,d; djnz d,$; djnz d,nest)")
    log(f"{'shape':20s} {'imm':>4s} {'sites':>5s} {'sim cyc':>8s} {'static':>7s} {'keil ref':>8s} {'model us':>9s} {'nominal':>8s} {'ratio':>6s}  verdict")
    for tag in sorted(sites):
        for imm in sorted({x[2] for x in sites[tag]}):
            grp = [x for x in sites[tag] if x[2] == imm]
            c, addr, _, endoff = grp[0]
            bank = 0 if c["addr"] < im.common else c["addr"] >> 16
            five = tag.startswith("5us")
            N = n5 if five else nx
            nest = tag.startswith("xus") and "base" not in tag
            setup = {v["base5" if five else "basex"]: N}
            steps = imm * (N + 2) + 2 if nest else (N + 2) * (3 if "dec" in tag else 1)
            cyc, _nst = run_site(s, img, bank, addr, addr + endoff, setup, steps)
            ref = pattern_cycles("nest" if nest else "single", N, N, imm)
            simple = not nest and "dec" not in tag
            stat = static_cycles(im.img[bank * F.BANK + addr: bank * F.BANK + addr + endoff]) + 3 * (N - 1) if simple else None
            us = cyc / CYCLES_PER_US
            nom = 5.0 if five else (imm * 4.0 if nest else 4.0)
            ratio = us / nom
            good = abs(cyc - ref) <= TOL_REF * ref and TOL_NOM[0] <= ratio <= TOL_NOM[1] and (stat is None or stat == cyc)
            verdict = "ok"
            if not good:
                names = sorted({x[0]["name"].lstrip("_") for x in grp})
                unk = [n for n in names if n not in known]
                verdict = "FAIL" if unk else "known"
                ok &= not unk
            log(f"{tag:20s} {imm:4d} {len(grp):5d} {cyc:8d} {stat if stat is not None else '-':>7} {ref:8d} {us:9.2f} {nom:8.1f} {ratio:6.2f}  {verdict}")
            if not good:
                for n in names:
                    log(f"    {'KNOWN' if n in known else 'FAIL '} {n}: {known.get(n, 'not in re/delay_cal_known.tsv')}")
    s.send("quit")
    return ok


def sim_times(binp: Path, mapp: Path):
    """(stage ms 1..8, firmware ms at mode ACTIVE, diag) from the HDMI-source sim (fw_sim.SimBus, 20 k instr steps)."""
    bus = F.SimBus(binp, mapp, video="1080p60")
    try:
        used = 0
        while bus.mode_state() != 3 and used < 150_000_000:
            bus.m.run(20_000); used += 20_000
        if bus.mode_state() != 3:
            raise SystemExit(f"{binp.name}: never reached ACTIVE in the sim")
        d = bus.diag()
        return d["ts"], bus.diag_t2(), d
    finally:
        bus.close()


def check_stages(binp: Path, mapp: Path, refb: Path, refm: Path) -> bool:
    a, ta, _da = sim_times(binp, mapp)
    b, tb, _ = sim_times(refb, refm)
    ok = True
    log(f"{'sim ms':>8s} {binp.name[:34]:>36s} {refb.name[:34]:>36s}  diff (limit {TOL_STAGE} ms)")
    for i, (x, y) in enumerate(zip(a, b), 1):
        good = abs(x - y) <= TOL_STAGE
        ok &= good
        log(f"stage {i:2d} {x:36d} {y:36d} {x - y:+5d}  {'ok' if good else 'FAIL'}")
    good = abs(ta - tb) <= TOL_ACTIVE
    ok &= good
    log(f"ACTIVE   {ta:36d} {tb:36d} {ta - tb:+5d}  {'ok' if good else 'FAIL'}  (limit {TOL_ACTIVE} ms: 20 k-instr polling step)")
    return ok


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--vendor", type=Path, default=VENDOR, help="Keil vendor flash dump (shape reference); '' = skip")
    ap.add_argument("--stages", nargs=2, type=Path, metavar=("REF_BIN", "REF_MAP"))
    ap.add_argument("--be", action="store_true", help="diag block big-endian (default: '-be' in the name)")
    ap.add_argument("--common", type=lambda x: int(x, 0), default=CM.COMMON_END)
    ap.add_argument("--layout", default="", help="fn/const classification of the chunks (default: the image's own bank_layout.tsv, fw_link_check.layout_of)")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = Logger(ROOT / "tmp/logs/delay_cal_check.log", stamp_echo=False)
    be = a.be or "-be" in a.bin.name
    log(f"delay_cal_check {a.bin.name} (vendor ref {a.vendor.name if a.vendor and a.vendor.exists() else 'none'})")
    im = L.Image(a.bin, a.map, a.layout or str(L.layout_of(a.bin, ROOT)), a.common)
    vend = a.vendor.read_bytes() if a.vendor and a.vendor.exists() else b""
    ok = check_shapes(im, a.bin.read_bytes(), a.map, be, vend, None)
    if a.stages:
        ok &= check_stages(a.bin, a.map, a.stages[0], a.stages[1])
    log(f"RESULT {'PASS' if ok else 'FAIL'} delay_cal_check {a.bin.name}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
