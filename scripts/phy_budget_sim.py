#!/usr/bin/env python3
"""EX0-masked time of one TMDS PHY set-up (ScalerTMDSRx{2,3}PhySetDeferred) in the DW8051 sim, per pixel-clock path (#329, M057).

usage: phy_budget_sim.py BIN MAP [--tree DIR] [--label L]
  Boots the image to ACTIVE, then calls ScalerTMDSRx2PhySetDeferred / Rx3 alone (return pad as isr_call_cycles.py):
  pending flag set, isr_g_usTMDSRxPhyClk preset to the path's pixel clock (0.1 MHz), interrupts off (EX0 is masked inside anyway).
  Register pages read back what firmware wrote (xram model); CheckCDRStable_EXINT0 / MeasureClk_EXINT0 / CheckDataDFE are HLE stubs
  (hardware waits, counted per call and costed from docs/delays.md static rows, not run).
  Cycles = clk of the sim at the image's running CPU clock; delay loops are real instructions, so the delay sum is in the number.
  Paths: DCDR 1080p60 (1485), ACDR 2000-3400 (3000), ACDR > 3400 4K60 (5940), 4K60 retry = second SetPhy with the 2.9 ms long block.
  Two set-ups back to back = the sum of two single calls: EX0 is restored at each return, so a pending AUX request is served in the gap.
Log: ./tmp/logs/phy_budget_sim.log
"""

import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import panel_sim as P
from _repo import ROOT

LOG = ROOT / "tmp/logs/phy_budget_sim.log"
RET_PAD = 0x0006  # never executed otherwise: the stub there stops the run
# (name, pixel clock 0.1 MHz, CDR-stable results of the successive CheckCDRStable_EXINT0 calls: pre-check, after SetPhy, after the retry)
PATHS = (
    ("DCDR 1080p60", 1485, (0, 1, 1)),
    ("ACDR 2000-3400", 3000, (0, 1, 1)),
    ("ACDR 4K60 first try ok", 5940, (0, 1, 1)),
    ("ACDR 4K60 first try fails, retry", 5940, (0, 0, 1)),
)
STUBS = (
    ("ScalerTMDSRxMeasureClk_EXINT0", {"val": 0x0A00}),
    ("ScalerTMDSRxCheckDataDFE", {"carry": 0}),
)


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def run_call(run, chunk, im, times=3):
    m, c, p = run.m, run.m.core, run.m.p
    bank = None if chunk["addr"] < im.common else chunk["addr"] >> 16
    ie = c.sfr[0x28]
    sp = 0x70
    m.stubs.setdefault(RET_PAD, []).append(
        (None, "replay", lambda m_, r: m_.request_stop())
    )
    c.pch[RET_PAD] |= 0xFFFF
    out = []
    for _ in range(times):
        c.sfr[0x28] = 0
        c.xram[0xFFFF] = (bank or 0) & 15
        c.set_bank((bank or 0) & 15)
        c.iram[sp + 1], c.iram[sp + 2] = RET_PAD & 0xFF, RET_PAD >> 8
        c.sfr[0x01] = sp + 2
        p.pc = chunk["addr"] & 0xFFFF
        k0 = p.clk
        m.run(50_000_000)
        out.append(p.clk - k0)
        yield out[-1]
    c.sfr[0x28] = ie


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    im = L.Image(a.bin, a.map, str(Path(a.tree) / "fw/bank_layout.tsv"), 0x5000)
    run = P.Run(
        argparse.Namespace(
            bin=a.bin, map=a.map, mode="1080p60", report=True, tree=a.tree
        )
    )
    try:
        run.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        m = run.m
        mhz = m.clock.f_cpu / 1e6
        chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
        say(f"{a.label or a.bin.name}: CPU clock {mhz:.2f} MHz")
        calls = {}
        for fn, ret in STUBS:
            m.stub(
                fn,
                lambda m_, r, fn=fn, ret=ret: (
                    calls.__setitem__(fn, calls.get(fn, 0) + 1),
                    ret,
                )[1],
            )
        seq, nset = [0, 1, 1], [0]

        def cdr(m_, r):
            calls["ScalerTMDSRxCheckCDRStable_EXINT0"] = (
                calls.get("ScalerTMDSRxCheckCDRStable_EXINT0", 0) + 1
            )
            return {"val": seq[min(nset[0], 2)]}

        m.stub("ScalerTMDSRxCheckCDRStable_EXINT0", cdr)
        sp_chunk = chunks["ScalerTMDSRxSetPhy_EXINT0"]
        sp_pc, sp_bank = (
            sp_chunk["addr"] & 0xFFFF,
            (None if sp_chunk["addr"] < im.common else sp_chunk["addr"] >> 16),
        )

        def on_setphy(m_, r):
            nset[0] += 1
            calls["SetPhy"] = nset[0]

        m.stubs.setdefault(sp_pc, []).append((sp_bank, "probe", on_setphy))
        m.core.pch[sp_pc] |= 0xFFFF if sp_bank is None else 1 << sp_bank
        pend, clk = m.addr("isr_g_ucTMDSRxPhyPend"), m.addr("isr_g_usTMDSRxPhyClk")
        for port in (2, 3):
            ch = chunks[f"ScalerTMDSRx{port}PhySetDeferred"]
            for name, pclk, cdrs in PATHS:
                res = []
                want = 2 if cdrs[1] == 0 else 1
                while len(res) < 5:
                    calls.clear()
                    seq[:] = cdrs
                    nset[0] = 0
                    m.wr(pend + port - 2, bytes([1]))
                    m.wr(clk + 2 * (port - 2), bytes([pclk >> 8, pclk & 255]))
                    k = list(run_call(run, ch, im, times=1))
                    if (
                        nset[0] == want
                    ):  # a call that did not run the set-up (stale stop of the sim) is not counted
                        res.append(k[0])
                us = sorted(
                    x / mhz for x in res[1:]
                )  # rep 1 = warm-up (cold flash-fetch cache, sim run-up)
                say(
                    f"  Rx{port} {name:34s}: min {us[0]:8.1f} median {us[len(us) // 2]:8.1f} max {us[-1]:8.1f} us (4 reps), stubs {dict(calls)}"
                )
    finally:
        run.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
