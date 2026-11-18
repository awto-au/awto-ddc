#!/usr/bin/env python3
"""Where a saver frame's CPU time goes: flash-cache stalls, XDATA / register MOVX, compute (docs/saver-code-placement.md).

usage: saver_code_profile.py BIN [--case scope|scope2|asteroids|pacman ...] [--window S] [--every N] [--top K] [--sets N] [--tsv OUT]
  Same start as saver_frame_cost.py (VCP 0xEB, hidden first frame skipped). Over --window fw seconds, from the core counters
  (scripts/mcs51_core.c, tools only) and PC samples every --every instr:
  - per frame: fw ms, instr, cycles, flash fetch stall (ms, % of time), line fills, bytes fetched, bank-switch writes (0xFFFF),
    MOVX split XRAM / registers (>= 0xF000: scaler, OSD port) with their cycles, cycles by opcode class (databook table 2-4)
  - per function: clk, stall, line fills (from the per-line miss counter, attributed to the function holding the line start)
  - cache: lines touched, lines holding 90 % of the fetches, sets with more hot lines than ways (conflicts), miss share by set
  --sets N: cache sets for this run (sensitivity; sets in AWTO_SIM_FETCH_SETS, default the JSON).
Log: ./tmp/logs/saver_code_profile.log
"""
import argparse
import bisect
import collections
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402
import saver_frame_cost as F  # noqa: E402

LOG = R.ROOT / "tmp/logs/saver_code_profile.log"
SC1_COLS = 32                   # Scope 1: one ScColumn call per column, AWTO_SC_COLS columns per frame (scope_saver.c)
LINE = 16
COMMON_END = 0x5000
WAYS = 2
CLK_PER_CYCLE = 4
# opcode classes (DW8051 databook table 2-4, p. 2-18..2-23: cycles per opcode are in scripts/dw8051_model.json)
_RI = {0x06, 0x07, 0x16, 0x17, 0x26, 0x27, 0x36, 0x37, 0x46, 0x47, 0x56, 0x57, 0x66, 0x67, 0x76, 0x77, 0x86, 0x87,
       0x96, 0x97, 0xA6, 0xA7, 0xB6, 0xB7, 0xC6, 0xC7, 0xD6, 0xD7, 0xE6, 0xE7, 0xF6, 0xF7}
_DIR = {0x05, 0x15, 0x25, 0x35, 0x45, 0x55, 0x65, 0x95, 0xE5, 0xF5, 0xC5, 0xD5, 0x85, 0x75, 0x42, 0x52, 0x62, 0x43, 0x53, 0x63,
        0xC0, 0xD0, 0xB5, *range(0x88, 0x90), *range(0xA8, 0xB0)}
_BIT = {0xC2, 0xD2, 0xB2, 0x10, 0x20, 0x30, 0xA2, 0x92, 0x72, 0x82, 0xB0, 0xA0}
_DPTR = {0x90, 0xA3}
_MOVX = {0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3}
_MOVC = {0x83, 0x93}
_BR = {0x11, 0x31, 0x51, 0x71, 0x91, 0xB1, 0xD1, 0xF1, 0x12, 0x22, 0x32, 0x01, 0x21, 0x41, 0x61, 0x81, 0xA1, 0xC1, 0xE1, 0x02, 0x80,
       0x40, 0x50, 0x60, 0x70, 0x73, 0xB4, 0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF, *range(0xB8, 0xC0)}
CLASSES = ["IRAM direct", "IRAM @Ri", "bit", "MOV/INC DPTR", "MOVX", "MOVC", "branch / call / ret", "reg / acc / imm ALU"]


def op_class(op: int) -> str:
    for name, s in (("MOVX", _MOVX), ("MOV/INC DPTR", _DPTR), ("MOVC", _MOVC), ("IRAM @Ri", _RI), ("IRAM direct", _DIR), ("bit", _BIT),
                    ("branch / call / ret", _BR)):
        if op in s:
            return name
    return "reg / acc / imm ALU"


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def func_table(m):
    """(sorted starts, [(end, name)]) of the physical code map: key = bank << 16 | addr (bank 0 / common = addr).
    Chunks (CH_ / ST_) end at their size (map l_CH_ / l_ST_); a line past every end is `(const / gap)`."""
    txt = m.map_text
    size = {mm.group(2): int(mm.group(1), 16) for mm in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(l_(?:CH|ST)_\w+)", txt, re.M)}
    ents = {}
    for k, v in m.sym.items():
        if v >= 0x200000 or not k.startswith("_"):
            continue
        ents[v] = (None, k[1:])
    for mm in re.finditer(r"^(CH|ST)_(\w+?)\s+([0-9A-F]{8})\s+([0-9A-F]{8})\s*=", txt, re.M):
        a_, n_ = int(mm.group(3), 16), int(mm.group(4), 16)
        ents[a_] = (a_ + n_, ("_bs_" if mm.group(1) == "ST" else "") + mm.group(2))
    keys = sorted(ents)
    tab = []
    for i, k in enumerate(keys):
        end, nm = ents[k]
        tab.append((end if end is not None else (keys[i + 1] if i + 1 < len(keys) else k + 16), nm))
    return keys, tab


def xdata_syms(mp: Path):
    """[(addr, size, name)] of the XDATA variables, statics and locals included: the linked listings tmp/sdcc-port/asm_bank/*.rst
    (label followed by `.ds N` at an address in the XDATA pool) of the LAST build; saved beside the map as .xsyms.json
    (run this right after the build: a later build overwrites the listings)."""
    js = mp.with_suffix(".xsyms.json")
    if js.exists():
        return [tuple(x) for x in json.loads(js.read_text())]
    out = []
    lab = re.compile(r"^\s+([0-9A-F]{6})\s+\d+\s+(\w+):{1,2}\s*$")
    ds = re.compile(r"^\s+(?:[0-9A-F]{6})?\s*\d+\s+\.ds\s+(\d+)")
    for f in sorted((R.ROOT / "tmp/sdcc-port/asm_bank").glob("*.rst")):
        lines = f.read_text(errors="replace").split("\n")
        for i, l in enumerate(lines):
            m = lab.match(l)
            if m and 0xD000 <= int(m.group(1), 16) < 0xF800:
                for l2 in lines[i + 1:i + 4]:
                    d = ds.match(l2)
                    if d:
                        out.append((int(m.group(1), 16), int(d.group(1)), m.group(2)))
                        break
    out.sort()
    js.write_text(json.dumps(out))
    return out


def line_func(keys, tab, ph: int) -> str:
    """Function holding a 16 B line: the one covering its first byte, else the first chunk starting inside it."""
    i = bisect.bisect_right(keys, ph) - 1
    if i >= 0 and ph < tab[i][0]:
        return tab[i][1]
    if i + 1 < len(keys) and keys[i + 1] < ph + LINE:
        return tab[i + 1][1]
    return "(const / gap)"


def measure(a, case: str) -> dict:
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    m, bus = sess.bus.m, sess.bus
    core = m.core
    ddc = D.Mccs(bus, eng)
    ddc.set(0xE0, F.ROW_DISP_ROTATE)
    ddc.set(0xE1, 1 if a.rotate else 0)
    bus.wait(F.ROTATE_SETTLE_S)
    ddc.set(F.VCP_SAVER, F.VCP[case])
    bus.wait(F.SETTLE_S[case])
    where = F.wherer(m)
    in_saver = [False]
    m.stub("AwtoSaverPoll", lambda mm, r: in_saver.__setitem__(0, True) and None)
    m.stub("SysMachineHandler", lambda mm, r: in_saver.__setitem__(0, False) and None)
    calls = collections.Counter()
    for fn in ("ScPass", "ScColumn", "AwtoPacmanClassic", "AwtoStackCheck"):
        if "_" + fn in m.sym:
            m.stub(fn, lambda mm, r, fn=fn: calls.update([fn]) and None)
    rd16 = lambda n: int.from_bytes(m.rd(m.addr(n), 2), "big")
    rd8 = lambda n: m.rd(m.addr(n), 1)[0]
    frames = 0
    last = rd16("g_usAwtoS2Frame") if case == "scope2" else rd8("g_ucAwtoAstCol") if case == "asteroids" else 0
    xcalls = collections.Counter()
    if a.calls:                                           # cross-bank call counts: hook every stub, caller from the return address
        def hook(mm, r, nm):
            c = mm.core
            sp = c.sfr[1]
            ret = (c.iram[sp] << 8 | c.iram[(sp - 1) & 0xFF]) - 3
            xcalls[(where(c.p.bank, ret), nm)] += 1
        for k in m.sym:
            if k.startswith("__bs_") and k not in ("__bs_call", "__bs_ret", "__bs_call_sw", "__bs_ret_sw", "__bs_keil"):
                m.stub(k[1:], lambda mm, r, nm=k[5:]: hook(mm, r, nm))
    calls.clear()
    clk, stall = collections.Counter(), collections.Counter()
    cyc0, op0, cnt0, xacc0 = list(core.cycop), list(core.opcount), list(core.cnt), list(core.xacc)
    lacc0, lmiss0 = list(core.lacc), list(core.lmiss)
    i0, c0, w0, s0, f0 = m.p.instr, m.p.cycles, m.wall_ms, m.p.fm_stall, m.p.fm_miss
    saver_clk = [0, 0]
    kp, sp = m.p.clk, m.p.fm_stall
    t_end = bus.now() + a.window
    while bus.now() < t_end:
        m.run(a.every)
        k = m.p.clk
        fn = where(m.p.bank, m.p.pc)
        clk[(fn, in_saver[0])] += k - kp
        stall[(fn, in_saver[0])] += m.p.fm_stall - sp
        sp = m.p.fm_stall
        saver_clk[0 if in_saver[0] else 1] += k - kp
        kp = k
        if case == "scope2":
            v = rd16("g_usAwtoS2Frame")
            frames += (v - last) & 0xFFFF
            last = v
        elif case == "asteroids":
            v = rd8("g_ucAwtoAstCol")
            frames += v == 0 and last != 0
            last = v
    if case == "scope":
        frames = calls["ScColumn"] / SC1_COLS if calls["ScColumn"] else calls["ScPass"] / F.SC1_PASSES_PER_FRAME
    elif case == "pacman":
        frames = calls["AwtoPacmanClassic"]
    r = {"case": case, "frames": max(frames, 1e-9), "wall": m.wall_ms - w0, "instr": m.p.instr - i0, "cycles": m.p.cycles - c0,
         "stall_clk": m.p.fm_stall - s0, "fills": m.p.fm_miss - f0, "clk": clk, "stall": stall, "saver_clk": saver_clk,
         "passes": calls["AwtoStackCheck"], "f_cpu": m.clock.f_cpu,
         "cycop": [x - y for x, y in zip(core.cycop, cyc0)], "opcount": [x - y for x, y in zip(core.opcount, op0)],
         "cnt": [x - y for x, y in zip(core.cnt, cnt0)],
         "lacc": [x - y for x, y in zip(core.lacc, lacc0)], "lmiss": [x - y for x, y in zip(core.lmiss, lmiss0)]}
    r["xcalls"] = xcalls
    r["xacc"] = [x - y for x, y in zip(core.xacc, xacc0)]
    r["xsyms"] = xdata_syms(a.bin.with_suffix(".map"))
    r["oplen"] = a.oplen
    r["sets"] = a.sets
    keys, names = func_table(m)
    r["keys"], r["names"] = keys, names
    r["total_clk"] = sum(clk.values())
    bus.close()
    return r


def report(a, r: dict) -> None:
    case, f, wall = r["case"], r["frames"], r["wall"]
    ms_clk = wall / max(r["total_clk"], 1)
    ms = lambda clk_: clk_ * ms_clk / f
    tot_clk = r["total_clk"]
    fetched = sum(n * l for n, l in zip(r["opcount"], r["oplen"]))
    cn = r["cnt"]
    movx_cyc = r["cycop"][0xE0] + r["cycop"][0xE2] + r["cycop"][0xE3] + r["cycop"][0xF0] + r["cycop"][0xF2] + r["cycop"][0xF3]
    dptr_cyc = r["cycop"][0x90] + r["cycop"][0xA3]
    tag = f"{a.bin.name} {case}{' rot180' if a.rotate else ''} sets {a.sets}"
    say(f"{tag}: {f:.1f} frames in {wall / 1000:.2f} s fw at {r['f_cpu'] / 1e6:.2f} MHz -> {wall / f:.2f} ms / frame "
        f"({f / (wall / 1000):.2f} / s); {r['instr'] / f:.0f} instr, {r['cycles'] / f:.0f} cycles / frame")
    st_ms = ms(r["stall_clk"])
    say(f"    flash fetch stall {st_ms:.2f} ms / frame = {100 * r['stall_clk'] / tot_clk:.1f} % of time; {r['fills'] / f:.0f} line fills / frame "
        f"({st_ms * 1000 / max(r['fills'] / f, 1e-9):.2f} us each), {fetched / f:.0f} B fetched / frame ({fetched / max(r['fills'], 1):.1f} B per fill)")
    say(f"    compute (cycles x 4 clk, no stall) {ms(r['cycles'] * CLK_PER_CYCLE):.2f} ms / frame; saver slot {ms(r['saver_clk'][0]):.1f} ms, rest of main loop {ms(r['saver_clk'][1]):.1f} ms")
    say(f"    bank-switch writes (0xFFFF) {cn[4] / f:.0f} / frame; MOVX XRAM rd {cn[0] / f:.0f} wr {cn[1] / f:.0f}; "
        f"MOVX outside the XRAM pool 0xD000..0xF7FF (scaler registers, OSD port) rd {cn[2] / f:.0f} wr {cn[3] / f:.0f}; "
        f"MOVX cycles {movx_cyc / f:.0f} ({ms(movx_cyc * CLK_PER_CYCLE):.2f} ms), MOV/INC DPTR cycles {dptr_cyc / f:.0f} ({ms(dptr_cyc * CLK_PER_CYCLE):.2f} ms)")
    cls_cyc, cls_n = collections.Counter(), collections.Counter()
    for op in range(256):
        cls_cyc[op_class(op)] += r["cycop"][op]
        cls_n[op_class(op)] += r["opcount"][op]
    for c_ in CLASSES:
        say(f"      class {c_:22s} {cls_n[c_] / f:9.0f} instr {cls_cyc[c_] / f:9.0f} cycles {ms(cls_cyc[c_] * CLK_PER_CYCLE):7.2f} ms ({100 * cls_cyc[c_] / max(r['cycles'], 1):4.1f} % of cycles)")
    # per function, with misses from the per-line fill counter
    fn_miss, fn_acc = collections.Counter(), collections.Counter()
    sets_miss, sets_acc = collections.Counter(), collections.Counter()
    for line, n in enumerate(r["lacc"]):
        if n:
            ph = line * LINE
            fnm = line_func(r["keys"], r["names"], ph)
            fn_acc[fnm] += n
            fn_miss[fnm] += r["lmiss"][line]
            sets_miss[line % r["sets"]] += r["lmiss"][line]
            sets_acc[line % r["sets"]] += n
    per = collections.defaultdict(lambda: [0, 0])
    for (fn, s_), c in r["clk"].items():
        per[fn][0] += c
        per[fn][1] += r["stall"][(fn, s_)]
    for fn, (c, s) in sorted(per.items(), key=lambda x: -x[1][0])[:a.top]:
        say(f"      fn {ms(c):7.2f} ms (stall {ms(s):6.2f}, {100 * s / max(c, 1):3.0f} %) fills {fn_miss.get(fn, 0) / f:6.1f} / frame  {fn}")
    # cache footprint
    lines = [(n, l) for l, n in enumerate(r["lacc"]) if n]
    lines.sort(reverse=True)
    tot_acc = sum(n for n, _ in lines)
    acc, hot = 0, []
    for n, l in lines:
        hot.append(l)
        acc += n
        if acc >= 0.9 * tot_acc:
            break
    per_set = collections.Counter(l % r["sets"] for l in hot)
    over = sum(1 for s, c in per_set.items() if c > WAYS)
    fills_top = sorted(((r["lmiss"][l], l) for l in range(len(r["lmiss"])) if r["lmiss"][l]), reverse=True)[:a.top // 2]
    say(f"    cache: {len(lines)} lines touched ({len(lines) * LINE / 1024:.1f} KB), {len(hot)} lines hold 90 % of fetches ({len(hot) * LINE} B; capacity {r['sets'] * WAYS} lines), "
        f"{over} of {r['sets']} sets have > {WAYS} hot lines; fills {sum(sets_miss.values()) / f:.0f} / frame, top 8 sets take {100 * sum(c for _, c in sets_miss.most_common(8)) / max(sum(sets_miss.values()), 1):.0f} % of the fills")
    for n, l in fills_top:
        say(f"      line fills {n / f:6.1f} / frame  set {l % r['sets']:3d}  {line_func(r['keys'], r['names'], l * LINE)}  @0x{l * LINE:06x}  (fetches {r['lacc'][l] / f:.0f})")
    if a.xdata:
        by = collections.Counter()
        for ad, sz, nm in r["xsyms"]:
            by[(nm, sz)] += sum(r["xacc"][ad:ad + sz])
        tot_x = sum(r["xacc"][0xD000:0xF800])
        import bisect as _b
        ks = [x[0] for x in r["xsyms"]]
        hot = sorted(range(0xD000, 0xF800), key=lambda i: -r["xacc"][i])[:a.top * 2]
        say("    hottest XRAM bytes: " + ", ".join(f"0x{i:04x} {r['xsyms'][_b.bisect_right(ks, i) - 1][2]}+{i - r['xsyms'][_b.bisect_right(ks, i) - 1][0]} {r['xacc'][i] / f:.0f}" for i in hot))
        say(f"    XRAM MOVX accesses {tot_x / f:.0f} / frame; per variable (name, bytes: accesses / frame, cycles saved / frame if in direct IRAM = 3 per access (MOV DPTR 3 + MOVX 2 -> MOV direct 2), ms, per byte):")
        cum = 0
        for (nm, sz), n in by.most_common(a.top * 2):
            cum += n
            say(f"      {nm:40s} {sz:5d} B {n / f:8.0f} acc {3 * n / f:8.0f} cyc {ms(3 * n * CLK_PER_CYCLE):6.3f} ms  {3 * n / f / sz:7.0f} cyc/B  cum {100 * cum / max(tot_x, 1):4.1f} %")
    if a.calls:
        tot = sum(r["xcalls"].values())
        say(f"    cross-bank calls {tot / f:.0f} / frame (via stubs), top callers -> callees:")
        for (cl, ce), n in r["xcalls"].most_common(a.top * 2):
            say(f"      {n / f:7.1f} / frame  {cl} -> {ce}")
    if a.tsv:
        with a.tsv.open("a") as t:
            t.write("\t".join(str(x) for x in (a.bin.name, case, a.sets, f"{wall / f:.2f}", f"{r['instr'] / f:.0f}", f"{r['cycles'] / f:.0f}", f"{st_ms:.2f}",
                                               f"{r['fills'] / f:.0f}", f"{fetched / f:.0f}", f"{cn[4] / f:.0f}", f"{(cn[0] + cn[1]) / f:.0f}", f"{(cn[2] + cn[3]) / f:.0f}")) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--case", nargs="*", default=["scope", "scope2", "asteroids", "pacman"])
    ap.add_argument("--window", type=float, default=10.0, help="fw seconds measured")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--every", type=int, default=200, help="instructions between PC samples")
    ap.add_argument("--top", type=int, default=16)
    ap.add_argument("--sets", type=int, help="cache sets (default: JSON, 64)")
    ap.add_argument("--xdata", action="store_true", help="XRAM MOVX accesses per variable (candidates for __data)")
    ap.add_argument("--calls", action="store_true", help="count cross-bank calls by caller -> callee (hooks every stub)")
    ap.add_argument("--tsv", type=Path)
    a = ap.parse_args()
    mdl = json.load(open(Path(__file__).resolve().parent / "dw8051_model.json"))
    a.oplen = mdl["oplen"]
    if a.sets:
        os.environ["AWTO_SIM_FETCH_SETS"] = str(a.sets)
    a.sets = a.sets or mdl["flash_fetch"]["sets"]
    for c in a.case:
        report(a, measure(a, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
