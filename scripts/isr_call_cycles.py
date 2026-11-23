#!/usr/bin/env python3
"""Cycles of ONE call of the DpRx1 link-training ISR checks in the DW8051 sim (#299 / #300): Tp1Check / Tp2Check / DFECheck _EXINT0.

usage: isr_call_cycles.py BIN MAP [--tree DIR] [--label L]
  Boots the image to ACTIVE (panel_sim Run, clock model at the running clock), then calls each function alone: return address
  = a stop pad, interrupts off, register / DPCD-port bytes preset, g_ucDpRx1LaneCount 1 / 2 / 4 x link rate HBR / HBR2.
  Cycle count = clk of the sim (first call = cold flash-fetch cache, third call = hot). us at the image's running CPU clock.
  Compare two images (base vs new) by running the script on each; same preset, same code path chosen by the data.
  Preset: EQ-CRC readback all lanes set, Vth 7, DPCD level bytes 0 (the path that writes a request per lane = most work), TP1 normal LT.
Log: ./tmp/logs/isr_call_cycles.log
"""

import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import panel_sim as P
from _repo import ROOT
from fw_sim import SimError

LOG = ROOT / "tmp/logs/isr_call_cycles.log"
RET_PAD = 0x0006          # never executed otherwise: the stub there stops the run (as delay_sim.replay)
FUNCS = (("Tp1Check", "ScalerDpRx1Tp1Check_EXINT0", 1), ("Tp2Check", "ScalerDpRx1Tp2Check_EXINT0", 1), ("DFECheck", "ScalerDpRx1DFECheck_EXINT0", 0))
REGS = {0xB014: 0xFF, 0x7AF1: 0x07, 0xBAC4: 0x00}      # EQ-CRC readback, Vth/Tap readback, DPCD data port
PST = 0
RATES = (("HBR", 0x0A), ("HBR2", 0x14))


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def call(run, bank, pc, arg, times=3):
    m, c, p = run.m, run.m.core, run.m.p
    ie = c.sfr[0x28]
    c.sfr[0x28] = 0
    sp = 0x70
    m.stubs.setdefault(RET_PAD, []).append((None, "replay", lambda m_, r: m_.request_stop()))
    c.pch[RET_PAD] |= 0xFFFF
    out = []
    for _ in range(times):
        c.xram[0xFFFF] = (bank or 0) & 15
        c.set_bank((bank or 0) & 15)
        c.iram[0x0F] = (bank or 0) & 15      # _d_isr_bs_cur: the bank stub restores it on return
        c.iram[sp + 1], c.iram[sp + 2] = RET_PAD & 0xFF, RET_PAD >> 8
        c.sfr[0x01] = sp + 2
        c.iram[0x07] = arg          # R7 = port 0 (#326) or the LT type of the older images; R5 = LT type 0 (normal), sdcccall 3 bank 0
        c.iram[0x05] = 0
        if PST:                      # pointer-to-state parameter (R7 low, R6 high)
            c.iram[0x07], c.iram[0x06] = PST & 0xFF, PST >> 8
        p.pc = pc
        for a, v in REGS.items():
            c.xram[a] = v
        k0 = p.clk
        m.run(50_000_000)
        out.append(p.clk - k0)
    c.sfr[0x28] = ie
    return out


def has(run, n):
    try:
        run.m.addr(n)
        return True
    except SimError:
        return False


def sym(run, new, old):
    """Port 0 entry of the per-port table (#326), or the single global of older images."""
    try:
        return run.m.addr(new)
    except SimError:
        return run.m.addr(old)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    im = L.Image(a.bin, a.map, str(Path(a.tree) / "fw/bank_layout.tsv"), 0x5000)
    run = P.Run(argparse.Namespace(bin=a.bin, map=a.map, mode="1080p60", report=True, tree=a.tree))
    try:
        run.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        mhz = run.m.clock.f_cpu / 1e6
        chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
        say(f"{a.label or a.bin.name}: CPU clock {mhz:.2f} MHz")
        for label, fn, has_arg in FUNCS:
            c = chunks.get(fn[:31]) or chunks[fn]
            bank = None if c["addr"] < im.common else c["addr"] >> 16
            for lanes in (1, 2, 4):
                for rn, rate in RATES:
                    try:
                        base = run.m.addr("isr_g_stDpRxHot" if has(run, "isr_g_stDpRxHot") else "isr_g_astDpRxPort")      # StructDpRxPort prototypes: rate at +0, lanes at +1
                        run.m.wr(base, bytes([rate, lanes]))
                        global PST
                        PST = 0
                        try:
                            pa = run.m.addr("isr_g_pstDpRx")
                            run.m.wr(pa, bytes([base >> 8, base & 0xFF]))
                        except SimError:
                            PST = 0 if has(run, "isr_g_stDpRxHot") else base
                    except SimError:
                        run.m.wr(sym(run, "g_pucDpRxLaneCount", "g_ucDpRx1LaneCount"), bytes([lanes]))
                        run.m.wr(sym(run, "g_pucDpRxLinkRate", "g_ucDpRx1LinkRate"), bytes([rate]))
                    cl = call(run, bank, c["addr"] & 0xFFFF, 0)
                    say(f"  {label:8s} lanes {lanes} {rn:4s}: cold {cl[0]:6d} clk, hot {cl[-1]:6d} clk = {cl[0] / mhz:6.2f} / {cl[-1] / mhz:6.2f} us")
    finally:
        run.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
