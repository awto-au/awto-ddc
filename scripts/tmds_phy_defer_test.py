#!/usr/bin/env python3
"""TMDS Rx2 / Rx3 freq-stable handshake (shared body, #rx-share) in the firmware sim (docs/main-loop-pacing.md ISR diet; the sim has no PHY / freq-detect IRQs,
so this raises EX0 with the P71 registers set and stubs the clock measure, CDR check and PHY set-up).

usage: tmds_phy_defer_test.py BIN [MAP] [--port 2|3]   (default: both ports)
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

from _log import log_line as _log_line
from _repo import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")
import fw_sim as S

LOG = ROOT / "tmp/logs/tmds_phy_defer_test.log"
PAGE_BASE = 0x7100                             # D2 page; D3 = +0x100 (RX_CHK_REG)
EF, E6 = 0xEF, 0xE6
COUNT = 0x0A00
ISR_STEP_INSTR, ISR_STEPS = 20, 500           # the EXINT0 handler is a few hundred instructions; stop at the first pend, not at a fixed time
fails = 0


def say(s: str) -> None:
    _log_line(s, LOG)


def check(name: str, ok: bool, detail: str) -> None:
    global fails
    fails += 0 if ok else 1
    say(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in ("2", "3")]
    ports = [int(sys.argv[sys.argv.index("--port") + 1])] if "--port" in sys.argv else [2, 3]
    bin_ = Path(args[0])
    mapp = Path(args[1]) if len(args) > 1 else bin_.with_suffix(".map")
    rc = 0
    for port in ports:
        rc |= run_port(bin_, mapp, port)
    return rc


def run_port(bin_: Path, mapp: Path, port: int) -> int:
    global fails
    fails = 0
    pg = PAGE_BASE + 0x100 * (port - 2)
    ef, e6 = pg + EF, pg + E6
    bus = S.SimBus(bin_, mapp, "tpd-" + bin_.stem, None, video="1080p60")
    if not bus.run_until_mode(3):
        say("FAIL never reached ACTIVE")
        return 1
    m = bus.m
    pend, info, clk_irq = m.addr("isr_g_ucTMDSRxPhyPend") + port - 2, m.addr(f"g_stTMDSRx{port}CtrlInfo"), m.addr("isr_g_ucTMDSRxClkIRQ") + port - 2
    ev = {"phy": [], "cdr": []}
    port_addr = m.addr("d_isr_g_ucTMDSRxPort")

    def ex0():
        return (m.rd(0xA8, 1, "sfr")[0] >> 0) & 1

    def phy(m_, r):
        if m_.rd(port_addr, 1, "iram")[0] != port - 2:      # the D2 scan runs in the sim too: count only this port's set-ups
            return {}
        ev["phy"].append({"ex0": ex0(), "pend": m_.rd(pend)[0], "e6": m_.rd(e6)[0]})
        return {}

    def cdr(m_, r):
        ev["cdr"].append({"info": m_.rd(info)[0], "ex0": ex0()})
        return {"val": 0}                       # not stable: scan takes its failure path and returns

    for fn, f in (("ScalerTMDSRxSetPhy_EXINT0", phy), ("ScalerTMDSRxCheckCDRStable", cdr),
                  ("ScalerTMDSRxCheckCDRStable_EXINT0", lambda m_, r: {"val": 0}),
                  ("ScalerTMDSRxMeasureClk_EXINT0", lambda m_, r: {"val": COUNT}),
                  ("ScalerTMDSRxCheckDataDFE", lambda m_, r: {"carry": 0})):
        m.stub(fn, f)

    m.wr(pg + 0xEC, bytes([0x00]))
    m.wr(clk_irq, bytes([1]))
    m.wr(pend, bytes([0]))
    m.wr(e6, bytes([m.rd(e6)[0] & ~0x06 & 0xFF]))
    m.wr(ef, bytes([0xC0]))
    m.wr(pg + 0xED, bytes([0x0A, 0x00]))            # popped counter: 0x0A00
    m.wr(0x88, bytes([m.rd(0x88, 1, "sfr")[0] | 0x02]), "sfr")      # TCON.IE0: EXINT0
    for _ in range(ISR_STEPS):                   # step until the handler has returned (pend set): main must not have run the set-up yet
        m.run(ISR_STEP_INSTR)
        if m.rd(pend)[0] or ev["phy"]:
            break
    b = ev["phy"]
    check("isr", m.rd(pend)[0] == 1 and not b and (m.rd(e6)[0] & 0x02) == 0,
          f"pend {m.rd(pend)[0]} (1), SetPhy calls {len(b)} (0), "
          f"E6 {m.rd(e6)[0]:02x} unstable enable {(m.rd(e6)[0] >> 1) & 1} (0)")
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
