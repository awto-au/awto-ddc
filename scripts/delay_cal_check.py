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
import argparse, os, re, select, struct, sys, time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d8051  # noqa: E402
import fw_link_check as L  # noqa: E402
import fw_sim as F  # noqa: E402

ROOT = F.ROOT
VENDOR = Path.home() / "vendors/realtek/analysis/dumps/jxc-4k-flash-AWT26110003-20261104-201610.bin"
CYCLES_PER_US = 87.7 / 4            # DW8051: MCU clock 87.7 MHz (M2PLL 350.8 / 4), 4 clocks per machine cycle
# TOL_REF: the same loop in Keil's code must cost the same: any difference is a codegen change, 5 % covers rounding only.
# TOL_NOM: the cycle model runs ~20 % fast against hardware (unit 3, 2026-11-06: N=26 loop 5.47 us incl. ISR, model 4.1 us),
#   so the model time may sit between 70 % and 110 % of nominal; refine from a clean hardware run.
# TOL_STAGE / TOL_ACTIVE: sim stage times shift by <= 1 tick when code moves (2 ms); the ACTIVE time is polled every 20 k instr (~5 ms).
TOL_REF, TOL_NOM, TOL_STAGE, TOL_ACTIVE = 0.05, (0.70, 1.10), 2, 5
MAX_STEPS = 400_000                 # DELAY_XUS(1000) is 250 x 21 iterations = 5.3 k steps; guard against a runaway
DELAY_VARS = {"base5": "d_isr_g_ucDelay5usN_Base", "basex": "d_isr_g_ucDelayXusN_Base", "i5": "d_isr_g_ucDelay5usI", "i5e": "d_isr_g_ucDelay5usI_EXINT",
              "cx": "d_isr_g_ucDelayXus_Counter", "cxe": "d_isr_g_ucDelayXus_Counter_EXINT"}
ALLOW_FN = ("ScalerMcu5usDelayCalc", "AwtoDiag", "GSINIT")     # writes the bases / the calibration test / C initialisers
LOG = None


def log(s):
    print(s, flush=True)
    LOG.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n"); LOG.flush()


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
        m = re.search(rf"^\s+([0-9A-F]{{8}})\s+_{name}\s", map_text, re.M)
        if not m:
            raise SystemExit(f"_{name} not in the map")
        out[k] = int(m.group(1), 16)
    return out


def shapes(v: dict) -> dict:
    """name -> (regex over code bytes, ...). Single loop: mov counter,base; djnz counter,$. Nest: DELAY_XUS."""
    h = lambda x: re.escape(bytes([x]))
    S = {}
    for tag, base, cnt in (("5us", "base5", "i5"), ("5us_exint", "base5", "i5e"), ("xus_base", "basex", "i5"), ("xus_base_exint", "basex", "i5e")):
        S[tag] = re.compile(b"\x85" + h(v[base]) + h(v[cnt]) + b"\xd5" + h(v[cnt]) + b"\xfd", re.S)
    for tag, base, cnt in (("5us_dec", "base5", "i5"), ("5us_dec_exint", "base5", "i5e"), ("xus_base_dec", "basex", "i5"), ("xus_base_dec_exint", "basex", "i5e")):
        # SDCC form inside a polling `while(flag && ...)`: mov v,base; L: dec v; mov a,v; jz out; sjmp L  (8 cycles/iteration)
        S[tag] = re.compile(b"\x85" + h(v[base]) + h(v[cnt]) + b"\x15" + h(v[cnt]) + b"\xe5" + h(v[cnt]) + b"\x60(.)\x80\xf8", re.S)
    for tag, outer, cnt in (("xus", "cx", "i5"), ("xus_exint", "cxe", "i5e")):
        S[tag] = re.compile(b"\x75" + h(v[outer]) + b"(.)\x85" + h(v["basex"]) + h(v[cnt]) + b"\xd5" + h(v[cnt]) + b"\xfd\xd5" + h(v[outer]) + b"\xf7", re.S)
    return S


def vendor_shapes(img: bytes) -> Counter:
    """Keil's loops in the vendor image: same shapes with its own addresses. Counter of (kind, imm)."""
    c = Counter()
    for m in re.finditer(rb"\x75(.)(.)\x85(.)(.)\xd5\4\xfd\xd5\1\xf7", img, re.S):
        c[("xus", m.group(2)[0])] += 1
    for m in re.finditer(rb"\x85(.)(.)\xd5\2\xfd", img, re.S):
        c[("single", 0)] += 1
    return c


def pattern_cycles(kind: str, n_single: int, n_base: int, imm: int) -> int:
    """Model cycles of the shape from its instruction costs: single = mov d,d (3) + N x djnz (3); nest = mov d,#i (3) +
    imm x (mov d,d (3) + Nb x djnz (3) + djnz (3))."""
    if kind == "single":
        return 3 + 3 * n_single
    return 3 + imm * (3 + 3 * n_base + 3)


def scan(im: "L.Image", v: dict, S: dict):
    """(sites {tag: [(chunk, addr16, imm, end offset from the site start)]}, bad [(chunk name, addr, text)])."""
    sites = defaultdict(list)
    bad = []
    counters = {v["i5"], v["i5e"], v["cx"], v["cxe"]}
    for c in im.chunks:
        if c["kind"] != "fn":
            continue
        code, base = im.code(c), c["addr"] & 0xFFFF
        cover = set()
        for tag, rx in sorted(S.items(), key=lambda kv: not kv[0].startswith("xus") or kv[0].startswith("xus_base")):
            for m in rx.finditer(code):
                if tag.startswith("xus_base") and "dec" not in tag and any(x in cover for x in range(m.start(), m.end())):
                    continue                                      # the inner loop of a nest
                imm = m.group(1)[0] if tag in ("xus", "xus_exint") else 0
                if "dec" in tag:
                    rel = m.group(1)[0]
                    end = 9 + (rel - 256 if rel > 127 else rel)       # JZ at +7 leaves the loop; its target is the end
                elif tag.startswith("xus") and "base" not in tag:
                    end = 12
                else:
                    end = 6
                sites[tag].append((c, base + m.start(), imm, end))
                cover.update(range(m.start(), m.end()))
        insns = [item[1] for item in L.sweep(code, base) if item[0] == "i"]
        for k, ins in enumerate(insns):                   # `mov v,base`, a few straight-line moves, then `djnz v,$` (code motion)
            if ins.off in cover or ins.raw[0] != 0x85 or ins.raw[2] not in (v["i5"], v["i5e"]) or ins.raw[1] not in (v["base5"], v["basex"]):
                continue
            for j in range(k + 1, min(k + 12, len(insns))):
                nx = insns[j]
                if nx.raw[0] == 0xD5 and nx.raw[1] == ins.raw[2] and nx.target == nx.addr:
                    five = ins.raw[1] == v["base5"]
                    tag = ("5us" if five else "xus_base") + ("_exint" if ins.raw[2] == v["i5e"] else "") + "_moved"
                    sites[tag].append((c, ins.addr, 0, nx.addr + nx.n - ins.addr))
                    cover.update(range(ins.off, nx.off + nx.n))
                    break
                if nx.target is not None or nx.raw[0] in (0x22, 0x32, 0x73):
                    break
        for ins in insns:
            if ins.off in cover or any(ins.off <= x < ins.off + ins.n for x in cover):
                continue
            ops = [o.strip() for o in ins.text.split(" ", 1)[-1].split(",")] if " " in ins.text else []
            hit = [o for o in ops if re.fullmatch(r"0?[0-9A-F]{2}h", o) and int(o[:-1], 16) in counters]
            if hit and not c["name"].lstrip("_").startswith(ALLOW_FN):
                bad.append((c["name"], ins.addr, ins.text))
    return sites, bad


def boot(img: bytes, mapp: Path, be: bool, tag: str, cal: bool = True):
    """ucsim booted to diag stage 8 and, with cal, past the panel T3 wait (usT3Wait64 set). Returns (session, diag dict, iram bases)."""
    import rtd_diag
    sym, where = F.parse_map(mapp.read_text(errors="replace"), img)
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
    m = re.search(r"0x[0-9a-f]+\s+((?:[0-9a-f]{2} ){%d})" % n, out or "")
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
            cyc, nst = run_site(s, img, bank, addr, addr + endoff, setup, steps)
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
    a, ta, da = sim_times(binp, mapp)
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
    ap.add_argument("--common", type=lambda x: int(x, 0), default=0x5000)
    ap.add_argument("--layout", default=str(ROOT / "fw/bank_layout.tsv"), help="fn/const classification of the chunks (fw_link_check)")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/delay_cal_check.log").open("a")
    be = a.be or "-be" in a.bin.name
    log(f"delay_cal_check {a.bin.name} (vendor ref {a.vendor.name if a.vendor and a.vendor.exists() else 'none'})")
    im = L.Image(a.bin, a.map, a.layout, a.common)
    vend = a.vendor.read_bytes() if a.vendor and a.vendor.exists() else b""
    ok = check_shapes(im, a.bin.read_bytes(), a.map, be, vend, None)
    if a.stages:
        ok &= check_stages(a.bin, a.map, a.stages[0], a.stages[1])
    log(f"RESULT {'PASS' if ok else 'FAIL'} delay_cal_check {a.bin.name}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
