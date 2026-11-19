#!/usr/bin/env python3
"""OSD data port byte-loss experiments on the test unit or in the firmware sim (docs/osd-port-loss.md).

usage: osd_port_loss.py --bus B --serial S --map MAP [--bin BIN] [--sim] GROUP|CASE [...]
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c: g_stAwtoOsw mode M_GAP, g_stAwtoOsdHw verify counters).
  One case = prefill the region with pattern A (slow safe stores), one pass of pattern B with the chosen delays between the stores
  (address set -> B0 -> B1 -> B2), read back M1 (+ M2) by the firmware verify against B: bad bytes, per byte position, doubled bytes.
  One pass only: a lost store of a repeated pass would leave the same value and hide.
  States: hidden = saver off; shown = Scope 2 running, saver poll held (OSD fetching the map / glyph SRAM).
  Log ./tmp/logs/osd_port_loss.log, TSV ./tmp/logs/osd_port_loss.tsv.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import osd_hw_test as H
import osd_sweep as W

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/osd_port_loss.log"
TSV = ROOT / "tmp/logs/osd_port_loss.tsv"
M_GAP = 7
M_RAW3, M_RAW1, M_TRIPLE_NOP, M_SDK = 8, 9, 2, 0
F_READDR = 0x10
F_SHUF = 0x20
NONE = 0xFF
W_KA, W_K0, W_K1, W_TARGET, W_SYNC, W_SIZE = 42, 43, 44, 45, 46, 47
O_POS = H.SIZE                                       # aucPos[3], ucDupPrev after the StAwtoOsdHw of osd_hw_test
SEED_A, SEED_B = 0x11, 0x3C
# regions (words): Scope 2 map, Scope 2 glyphs, unused top; 8184 B max per pass (N_MAX)
REGIONS = {"map": (0, 616), "glyph": (616, 2728), "top": (0x2000, 2728)}
SLOW_K = 40                                          # prefill delays (known clean: 24 nops pass)
CYCLES_PER_K = 2                                     # djnz = 2 machine cycles

W.LOG = LOG


def say(s: str) -> None:
    W.say(s)


@dataclass
class Case:
    name: str
    region: str = "map"
    shown: bool = True
    ka: int = NONE
    k0: int = NONE
    k1: int = NONE
    readdr: bool = False
    ea_off: bool = False
    sync: int = 0
    nops: int = 0
    dbon: bool = False
    mode: int = M_GAP
    shuf: bool = False
    rep: int = 1
    timing: int = 0                                  # reps of a timed (unverified) run on the unused top, instead of the verify case
    fff1: int | None = None
    fffb: int | None = None
    words: int = 0                                   # 0 = whole region
    memories: tuple = ("M1",)
    extra: dict = field(default_factory=dict)


class Ctx:
    def __init__(self, dev, sw, sim):
        self.dev, self.sw, self.sim = dev, sw, sim
        self.state = None
        self.tsv_keys = None


def wait(ctx, s: float) -> None:
    t0 = ctx.dev.now()
    while ctx.dev.now() - t0 < s:
        ctx.dev.idle()


def set_state(ctx, shown: bool) -> None:
    if ctx.state == shown:
        return
    dev = ctx.dev
    H.set_flags(dev, 0)
    if shown:
        H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=H.SAVER_SCOPE2, label="scope2 on")
        H.wait_scope2(dev)
        wait(ctx, 1.0)
        H.set_flags(dev, H.F_HOLD)
    else:
        H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=H.SAVER_OFF, label="saver off")
        wait(ctx, 0.3)
    ctx.state = shown


def osw(ctx, c: Case, seed: int, ka: int, k0: int, k1: int, readdr: bool, reps: int, nbytes: int, addr: int, apply: bool, sync: int) -> bytes | None:
    sw = ctx.sw
    fl = (F_READDR if readdr else 0) | (F_SHUF if c.shuf else 0) | (W.F_DB_ON if c.dbon else 0) | (W.F_EA_OFF if c.ea_off else 0)
    ap = (W.A_F1 if (apply and c.fff1 is not None) else 0) | (W.A_FB if (apply and c.fffb is not None) else 0)
    head = bytes([ap, (c.fff1 or 0) & 0xFF, (c.fffb or 0) & 0xFF, 0, c.mode, fl, seed, reps])
    p = head + addr.to_bytes(2, "big") + nbytes.to_bytes(2, "big") + (0).to_bytes(2, "big") + (0).to_bytes(2, "big")
    sw.wr(W.W_APPLY, p)
    sw.wr(W_KA, bytes([ka, k0, k1, 1, sync, c.nops if apply else 0]))
    return W.send(ctx_w(ctx), W.OP_RUN, W.LIMIT_S, c.name)


def ctx_w(ctx):
    return ctx


def verify(ctx, c: Case, addr: int, nbytes: int, mem: str) -> dict:
    dev = ctx.dev
    fl = H.F_REPEAT | (H.F_M2 if mem == "M2" else 0) | (H.F_HOLD if c.shown else 0)
    v = H.op(dev, H.OP_VERIFY, H.lim_read(nbytes), flags=fl, seed=SEED_B, addr=addr, n=nbytes, label=c.name + " verify " + mem)
    pos = list(dev.rd(O_POS, 4))
    return {"bad": v["bad"], "first": v["first"], "badb": v["badb"], "pos": pos[:3], "dup": pos[3]}


def run_case(ctx, c: Case) -> dict:
    a0, nw = REGIONS[c.region]
    if c.words:
        nw = min(nw, c.words)
    nb = nw * 3
    row = {"case": c.name, "region": c.region, "state": "shown" if c.shown else "hidden", "ka": c.ka, "k0": c.k0, "k1": c.k1,
           "readdr": int(c.readdr), "ea_off": int(c.ea_off), "sync": c.sync, "fff1": c.fff1, "words": nw, **c.extra}
    set_state(ctx, c.shown)
    if c.timing:
        r = osw(ctx, c, SEED_B, c.ka, c.k0, c.k1, c.readdr, c.timing, nb, a0, True, c.sync)
        ms, passes = W.be(r, W.W_MS), r[W.W_PASSES]
        row.update(ms=ms, passes=passes, us_word=ms * 1000.0 / (passes * nw))
        row["pass"] = True
        say(f"  TIME {c.name}: {passes} passes x {nw} words in {ms} ms = {row['us_word']:.4f} us/word ({row['us_word'] * 1000 / 3:.1f} ns per byte) Ka/K0/K1 {c.ka:02X}/{c.k0:02X}/{c.k1:02X} nops {c.nops}{' readdr' if c.readdr else ''}")
        return row
    tot = {"M1": 0, "M2": 0}
    pos = [0, 0, 0]
    dup = 0
    first = None
    badb = b""
    for _ in range(c.rep):
        r = osw(ctx, c, SEED_A, SLOW_K, SLOW_K, SLOW_K, False, 1, nb, a0, False, 0)
        if r is None or r[W.W_STATE] != W.ST_DONE:
            row["note"] = f"prefill failed state {r[W.W_STATE] if r else None} refuse {r[W.W_REFUSE] if r else None}"
            say(f"  FAIL {c.name}: {row['note']}")
            return row
        r = osw(ctx, c, SEED_B, c.ka, c.k0, c.k1, c.readdr, 1, nb, a0, True, c.sync)
        if r is None or r[W.W_STATE] != W.ST_DONE:
            row["note"] = f"test pass failed state {r[W.W_STATE] if r else None} refuse {r[W.W_REFUSE] if r else None}"
            say(f"  FAIL {c.name}: {row['note']}")
            return row
        row["fff1_now"] = r[W.W_NOW_F1]
        for mem in c.memories:
            v = verify(ctx, c, a0, nb, mem)
            tot[mem] += v["bad"]
            if mem == "M1":
                pos = [a + b for a, b in zip(pos, v["pos"])]
                dup += v["dup"]
                if v["bad"] and first is None:
                    first, badb = v["first"], v["badb"]
    bad = {m: {"bad": tot[m]} for m in c.memories}
    m1 = {"bad": tot["M1"], "pos": pos, "dup": dup, "first": first if first is not None else 0xFFFF, "badb": badb or bytes(8)}
    row.update(bad_m1=m1["bad"], pos0=pos[0], pos1=pos[1], pos2=pos[2], dup_prev=dup, rep=c.rep)
    if "M2" in bad:
        row["bad_m2"] = bad["M2"]["bad"]
    ok = all(b["bad"] == 0 for b in bad.values())
    row["pass"] = ok
    say(f"  {'PASS' if ok else 'FAIL'} {c.name}: {c.region} {'shown' if c.shown else 'hidden'} {nw} words, Ka/K0/K1 {c.ka:02X}/{c.k0:02X}/{c.k1:02X}"
        f"{' readdr' if c.readdr else ''}{' EAoff' if c.ea_off else ''}{' sync' if c.sync else ''}{' nops %d' % c.nops if c.nops else ''}{' shuf' if c.shuf else ''} x{c.rep}"
        f"{' FFF1 %02X' % c.fff1 if c.fff1 is not None else ''}: M1 bad {m1['bad']} (B0/B1/B2 {m1['pos']}, doubled {m1['dup']}) first {m1['first']} {m1['badb'].hex()}"
        + (f"; M2 bad {bad['M2']['bad']}" if "M2" in bad else ""))
    return row


def tsv(row: dict) -> None:
    keys = ["case", "region", "state", "words", "ka", "k0", "k1", "readdr", "ea_off", "sync", "nops", "shuf", "rep", "ms", "passes", "us_word", "fff1", "fff1_now", "bad_m1", "bad_m2", "pos0", "pos1", "pos2", "dup_prev", "pass", "note"]
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(["time"] + keys) + "\n")
        f.write("\t".join([isostamp.now()] + [str(row.get(k, "")) for k in keys]) + "\n")


KS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24)


def groups() -> dict[str, list[Case]]:
    g: dict[str, list[Case]] = {}
    g["base"] = [Case(f"base_{rg}_{'shown' if sh else 'hidden'}_{'readdr' if ra else 'cont'}", rg, sh, readdr=ra, memories=("M1", "M2"))
                 for sh in (True, False) for rg in ("map", "glyph", "top") for ra in (True, False)]
    g["gap"] = [Case(f"gap_{rg}_k{k}", rg, True, k, k, k, readdr=True) for rg in ("map", "glyph", "top") for k in KS]
    g["gapcont"] = [Case(f"gapcont_{rg}_k{k}", rg, True, NONE, k, k, readdr=False) for rg in ("map", "glyph") for k in KS]
    g["pos"] = [Case(f"pos_{n}_k{k}", "map", True, *kk, readdr=True)
                for k in (2, 4, 8, 12) for n, kk in (("ka", (k, NONE, NONE)), ("k0", (NONE, k, NONE)), ("k1", (NONE, NONE, k)))]
    g["hidden"] = [Case(f"hid_{rg}_k{k}", rg, False, k, k, k, readdr=True) for rg in ("map", "glyph") for k in (1, 3, 5, 7, 9)]
    g["fff1"] = ([Case(f"fff1_raw_{x:02X}", "map", True, readdr=True, fff1=x, rep=3, words=612) for x in list(range(16)) + [0x80, 0x87, 0x8F]]
                 + [Case(f"fff1_n8_{x:02X}", "map", True, nops=8, readdr=True, fff1=x, rep=3, words=612) for x in (0, 7, 15)])
    g["fffb"] = [Case(f"fffb_{v}", "map", True, readdr=True, fffb=v, rep=3, words=612) for v in (0, 1, 2, 4, 8, 16, 40, 128)]
    g["ea"] = [Case("ea_off_raw", "map", True, readdr=True, ea_off=True), Case("ea_off_k4", "map", True, 4, 4, 4, readdr=True, ea_off=True)]
    g["sync"] = [Case(f"sync_{rg}_{'k' + str(k) if k else 'raw'}", rg, True, *(([k] * 3) if k else [NONE] * 3), readdr=True, sync=1)
                 for rg in ("map", "glyph") for k in (0, 2, 4, 8)]
    g["raw"] = [Case(f"raw_{rg}_n{n}{'_shuf' if sh else ''}", rg, True, nops=n, readdr=True, shuf=sh) for rg in ("map", "glyph") for sh in (False, True) for n in range(7)]
    g["rare"] = [Case(f"rare_map_k{k}_shuf", "map", True, k, k, k, readdr=True, shuf=True, rep=20, words=612) for k in (1, 2, 3, 4, 6, 8)]
    g["rare0"] = [Case(f"rare0_map_n{n}_shuf", "map", True, nops=n, readdr=True, shuf=True, rep=10, words=612) for n in (3, 4, 5, 6)]
    g["tim"] = ([Case(f"tim_n{n}", "top", False, nops=n, timing=40) for n in range(7)] + [Case(f"tim_k{k}", "top", False, k, k, k, timing=40) for k in (1, 2, 4, 8, 16)]
                + [Case(f"tim_ka_k{k}", "top", False, k, NONE, NONE, timing=40) for k in (1, 2, 4)] + [Case("tim_raw_readdr", "top", False, readdr=True, timing=20)])
    NL = (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 40)
    g["tim2"] = [Case(f"tim2_n{n}", "top", False, nops=n, timing=40) for n in NL]
    g["ladder"] = [Case(f"ladder_{rg}_n{n}", rg, True, nops=n, readdr=True, rep=3, words=612) for rg in ("map", "glyph") for n in NL]
    g["ladderc"] = [Case(f"ladderc_{rg}_n{n}", rg, True, nops=n, readdr=False, rep=3, words=612) for rg in ("map",) for n in NL]
    g["ladderh"] = [Case(f"ladderh_{rg}_n{n}", rg, False, nops=n, readdr=True, rep=3, words=612) for rg in ("map",) for n in NL]
    g["dbon"] = [Case(f"dbon_map_n{n}", "map", True, nops=n, readdr=True, rep=3, words=612, dbon=True) for n in (0, 4, 8, 12, 16, 24, 32)]
    g["n22"] = [Case(f"n22_{i}", "map", True, nops=22, readdr=True, rep=3, words=612) for i in range(3)] + [Case("n7", "map", True, nops=7, readdr=True, rep=3, words=612)]
    g["stat"] = [Case(f"stat_map_n{n}", "map", True, nops=n, readdr=True, rep=30, words=612) for n in (8, 9, 10, 11, 12, 14, 16, 20, 24)]
    g["statg"] = [Case(f"statg_glyph_n{n}", "glyph", True, nops=n, readdr=False, rep=8, words=2700) for n in (8, 10, 12, 16, 20, 24)]
    g["timf"] = ([Case(f"timf_raw3_s{x:02X}", "top", False, mode=M_RAW3, fff1=x, timing=60) for x in (0, 4, 8, 10, 11, 12, 15)]
                 + [Case(f"timf_raw1_s{x:02X}", "top", False, mode=M_RAW1, fff1=x, timing=60) for x in (0, 10, 12)]
                 + [Case("timf_triple24", "top", False, mode=M_TRIPLE_NOP, timing=60), Case("timf_sdk", "top", False, mode=M_SDK, timing=30)]
                 + [Case(f"timf_triple24_s{x:02X}", "top", False, mode=M_TRIPLE_NOP, fff1=x, timing=60) for x in (10, 15)])
    g["rawv"] = ([Case(f"rawv_raw3_s{x:02X}", "map", True, mode=M_RAW3, fff1=x, rep=30, words=612) for x in (9, 10, 11, 12, 13, 14, 15)]
                 + [Case(f"rawv_raw1_s{x:02X}", "glyph", True, mode=M_RAW1, fff1=x, rep=6, words=2700) for x in (0, 9, 10, 11, 12, 14, 15)]
                 + [Case("rawv_raw3_s00", "map", True, mode=M_RAW3, rep=3, words=612), Case("rawv_triple24_s00", "map", True, mode=M_TRIPLE_NOP, rep=30, words=612)])
    g["smoke"] = [Case("smoke_raw", "map", False, readdr=True, words=60), Case("smoke_k8", "map", False, 8, 8, 8, readdr=True, words=60)]
    return g


def run(ctx, names: list[str]) -> int:
    table = groups()
    fails = 0
    for n in names:
        say(f"##### {n}")
        todo = table.get(n) or [c for lst in table.values() for c in lst if c.name == n]
        if not todo:
            raise SystemExit(f"unknown group / case {n}; groups {list(table)}")
        for c in todo:
            try:
                row = run_case(ctx, c)
            except (TimeoutError, RuntimeError) as e:
                row = {"case": c.name, "pass": False, "note": f"comm: {e}"}
                say(f"  FAIL comm lost at {c.name}: {e}")
            tsv(row)
            fails += not row.get("pass")
    say(f"done: {fails} case(s) with bad bytes or failed (loss cases are data, not errors)")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--serial")
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    binp = a.bin or a.map.with_suffix(".bin")
    global TSV
    if a.sim:
        import clk_sweep as C
        TSV = ROOT / "tmp/logs/osd_port_loss_sim.tsv"
        dev, _ck, _rd, _sa = C.make_sim(binp, a.map)
        sw = copy.copy(dev)
        sw.base = dev.m.addr("g_stAwtoOsw")
        W.pace = lambda s: s.idle()
        ctx = Ctx(dev, sw, True)
        return 1 if run(ctx, a.names) else 0
    import dbg_link
    import i2cbus
    import sync_log as S
    i2cbus.require_unit(a.bus, a.serial)
    with dbg_link.linked(a.bus, 10):
        dev = H.Unit(a.bus, a.map)
        sw = copy.copy(dev)
        sw.base = S.sym(a.map, "g_stAwtoOsw")
        ctx = Ctx(dev, sw, False)
        try:
            fails = run(ctx, a.names)
        finally:
            try:
                H.set_flags(dev, 0)
                W.send(ctx, W.OP_RESTORE, W.LIMIT_S, "final restore")
                H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=H.SAVER_OFF, label="saver off")
            except Exception as e:  # noqa: BLE001
                say(f"final cleanup: {e}")
            dev.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
