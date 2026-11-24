#!/usr/bin/env python3
"""Flash-cache sets with more than `ways` hot lines in the DpRx1 link-training ISR checks (awto-ddc#335).

usage: isr_cache_sets.py BIN MAP [--tree DIR] [--label L]
- Same setup as scripts/isr_call_cycles.py (Tp1Check / Tp2Check / DFECheck _EXINT0, lanes 1 / 2 / 4 x HBR / HBR2); the third (hot) call is stepped
  one instruction at a time, every fetched physical line is recorded with its function.
- Output per case: clk, line fills (fm_miss), stall clk (fm_stall), lines, sets holding more than `ways` distinct lines (each with its lines / functions).
- Cache geometry comes from scripts/dw8051_model.json (flash_fetch): 16 B lines, 64 sets, 2 ways. It is ASSUMED, not verified on hardware
  (cache_source in dw8051_model.py), so the numbers describe the sim model only. No limit is applied; exit code 0.
Log: ./tmp/logs/isr_cache_sets.log
"""

import argparse
import bisect
import json
import sys
from collections import defaultdict
from pathlib import Path

import chip_mem as CM
from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import isr_call_cycles as I
import panel_sim as P
from _repo import ROOT

LOG = ROOT / "tmp/logs/isr_cache_sets.log"
STEP_LIMIT = 200_000                                      # instructions of one call; the longest check is about 2,000


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def hot_trace(run, bank, pc, names, keys, common):
    """Third call of the function at pc, one instruction per step: [(physical address, function)], clk, fills, stall clk."""
    m, c, p = run.m, run.m.core, run.m.p
    I.call(run, bank, pc, 0, times=2)                      # warm: the third call is the hot one
    sp = 0x80
    c.xram[0xFFFF] = (bank or 0) & 15
    c.set_bank((bank or 0) & 15)
    c.iram[run.m.addr("d_isr_bs_cur") & 0xFF] = (bank or 0) & 15
    c.iram[sp + 1], c.iram[sp + 2] = I.RET_PAD & 0xFF, I.RET_PAD >> 8
    c.sfr[0x01] = sp + 2
    c.iram[0x07], c.iram[0x05] = 0, 0
    p.pc = pc
    for a, v in I.REGS.items():
        c.xram[a] = v
    k0, f0, s0, out = p.clk, p.fm_miss, p.fm_stall, []
    for _ in range(STEP_LIMIT):
        cur = p.pc
        ph = cur if cur < common else ((bank or 0) << 16) | cur
        i = bisect.bisect_right(keys, ph) - 1
        out.append((ph, names[i][1] if i >= 0 else "?"))
        m.run(1)
        if p.pc == I.RET_PAD:
            break
    return out, p.clk - k0, p.fm_miss - f0, p.fm_stall - s0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    ff = json.loads((ROOT / "scripts/dw8051_model.json").read_text())["flash_fetch"]
    line, sets, ways = ff["line_bytes"], ff["sets"], ff["ways"]
    say(f"{a.label or a.bin.name}: cache {sets} sets x {ways} ways x {line} B lines (ASSUMED, unverified on hardware: {ff['cache_source']})")
    im = L.Image(a.bin, a.map, str(L.layout_of(a.bin, a.tree)), CM.COMMON_END)
    run = P.Run(argparse.Namespace(bin=a.bin, map=a.map, mode="1080p60", report=True, tree=a.tree))
    try:
        run.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
        names = sorted((c["addr"], c["name"]) for c in im.chunks if c["kind"] == "fn")
        keys = [x for x, _ in names]
        for label, fn, _ in I.FUNCS:
            c = chunks.get(fn[:31]) or chunks[fn]
            bank = None if c["addr"] < im.common else c["addr"] >> 16
            for lanes in (1, 2, 4):
                for rn, rate in I.RATES:
                    run.m.wr(I.sym(run, "g_pucDpRxLaneCount", "g_ucDpRx1LaneCount"), bytes([lanes]))
                    run.m.wr(I.sym(run, "g_pucDpRxLinkRate", "g_ucDpRx1LinkRate"), bytes([rate]))
                    tr, clk, fills, stall = hot_trace(run, bank, c["addr"] & 0xFFFF, names, keys, im.common)
                    fn_of = {}
                    for ph, f in tr:
                        fn_of[ph // line] = f
                    bys = defaultdict(list)
                    for ln in fn_of:
                        bys[ln % sets].append(ln)
                    over = {s_: v for s_, v in bys.items() if len(v) > ways}
                    say(f"  {label:8s} lanes {lanes} {rn:4s}: hot {clk:6d} clk, {fills:3d} line fills, {stall:5d} stall clk, {len(tr):5d} instr, "
                        f"{len(fn_of):3d} lines, {len(over)} sets over {ways} lines")
                    for s_, v in sorted(over.items()):
                        say(f"      set {s_:2d}: " + ", ".join(f"0x{ln * line:x} {fn_of[ln]}" for ln in sorted(v)))
    finally:
        run.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
