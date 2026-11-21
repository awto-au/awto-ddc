#!/usr/bin/env python3
"""TMDS Rx2 freq-stable handshake in the firmware sim (docs/main-loop-pacing.md ISR diet; the sim has no PHY / freq-detect IRQs,
so this raises EX0 with the P71 registers set and stubs the clock measure, CDR check and PHY set-up).

usage: tmds_phy_defer_test.py BIN [MAP]
- isr:   stable IRQ -> handler only sets the pending flag; SetPhy_EXINT0 not called, the unstable IRQ enable still off.
         (PHY_SET is a `bit` since #281 step 2: not in the map, not read here.)
- main:  next main-loop pass (SysTMDSRxHandler) -> set-up runs once with EX0 masked, unstable IRQ enabled first, pending cleared,
         EX0 restored. The scan-start call is the same function (not reached in sim: scan is stubbed).
- once:  no second set-up without a new IRQ.
Log: tmp/logs/tmds_phy_defer_test.log
"""
import os
import sys
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")
import fw_sim as S

LOG = ROOT / "tmp/logs/tmds_phy_defer_test.log"
EF, E6, E8, E9, EA_, EB = 0x71EF, 0x71E6, 0x71E8, 0x71E9, 0x71EA, 0x71EB
COUNT = 0x0A00
ISR_STEP_INSTR, ISR_STEPS = 20, 500           # the EXINT0 handler is a few hundred instructions; stop at the first pend, not at a fixed time
fails = 0


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = isostamp.now() + " " + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def check(name: str, ok: bool, detail: str) -> None:
    global fails
    fails += 0 if ok else 1
    say(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def main() -> int:
    bin_ = Path(sys.argv[1])
    mapp = Path(sys.argv[2]) if len(sys.argv) > 2 else bin_.with_suffix(".map")
    bus = S.SimBus(bin_, mapp, "tpd-" + bin_.stem, None, video="1080p60")
    if not bus.run_until_mode(3):
        say("FAIL never reached ACTIVE")
        return 1
    m = bus.m
    pend, info, clk_irq = m.addr("isr_g_ucTMDSRx2PhyPend"), m.addr("g_stTMDSRx2CtrlInfo"), m.addr("isr_g_ucTMDSRx2ClkIRQ")
    ev = {"phy": [], "cdr": []}

    def ex0():
        return (m.rd(0xA8, 1, "sfr")[0] >> 0) & 1

    def phy(m_, r):
        ev["phy"].append({"ex0": ex0(), "pend": m_.rd(pend)[0], "e6": m_.rd(E6)[0]})
        return {}

    def cdr(m_, r):
        ev["cdr"].append({"info": m_.rd(info)[0], "ex0": ex0()})
        return {"val": 0}                       # not stable: scan takes its failure path and returns

    for fn, f in (("ScalerTMDSRx2SetPhy_EXINT0", phy), ("ScalerTMDSRx2CheckCDRStable", cdr),
                  ("ScalerTMDSRx2CheckCDRStable_EXINT0", lambda m_, r: {"val": 0}),
                  ("ScalerTMDSRx2MeasureClk_EXINT0", lambda m_, r: {"val": COUNT}),
                  ("ScalerTMDSRx2CheckDataDFE", lambda m_, r: {"carry": 0})):
        m.stub(fn, f)

    m.wr(0x71EC, bytes([0x00]))
    m.wr(clk_irq, bytes([1]))
    m.wr(pend, bytes([0]))
    m.wr(E6, bytes([m.rd(E6)[0] & ~0x06 & 0xFF]))
    m.wr(EF, bytes([0xC0]))
    m.wr(0x71ED, bytes([0x0A, 0x00]))            # popped counter: 0x0A00
    m.wr(0x88, bytes([m.rd(0x88, 1, "sfr")[0] | 0x02]), "sfr")      # TCON.IE0: EXINT0
    for _ in range(ISR_STEPS):                   # step until the handler has returned (pend set): main must not have run the set-up yet
        m.run(ISR_STEP_INSTR)
        if m.rd(pend)[0] or ev["phy"]:
            break
    b = ev["phy"]
    check("isr", m.rd(pend)[0] == 1 and not b and (m.rd(E6)[0] & 0x02) == 0,
          f"pend {m.rd(pend)[0]} (1), SetPhy calls {len(b)} (0), "
          f"E6 {m.rd(E6)[0]:02x} unstable enable {(m.rd(E6)[0] >> 1) & 1} (0)")
    bus.wait(0.3)                                # SysTMDSRxHandler runs the deferred set-up
    b = ev["phy"]
    ok = len(b) == 1 and b[0]["ex0"] == 0 and b[0]["e6"] & 0x02 and m.rd(pend)[0] == 0 and ex0() == 1
    check("main", ok, f"SetPhy calls {len(b)} (1), EX0 inside {b[0]['ex0'] if b else '-'} (0), unstable enable before it "
          f"{bool(b and b[0]['e6'] & 2)} (True), pend after {m.rd(pend)[0]} (0), EX0 after {ex0()} (1)")
    check("once", len(b) == 1, f"no second set-up without a new IRQ after 300 ms of scans: {len(b)} (1)")
    say(f"{'FAIL' if fails else 'PASS'} tmds_phy_defer_test {bin_.name}: {fails} failed")
    m.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
