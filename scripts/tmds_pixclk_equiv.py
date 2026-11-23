#!/usr/bin/env python3
"""Sim proof for #325: per-port TMDS pixel clock + ungated DDC-detect == the single-global version, for single-port behaviour.

usage: tmds_pixclk_equiv.py --base BIN MAP --new BIN MAP
  Same driver for both images (dw8051 sim, booted to ACTIVE as phy_budget_sim.py).
  The register page 0x7000-0x7CFF is filled from one seeded random file; per-port TMDS xdata, the bit variables and ClkIRQ are
  set to one known state (the images reach the boot stop in different states: hidden flags decide the retry path).
  Case = ScalerTMDSRx{2,3}PhySetDeferred, pending set, pixel clock of the port preset (0.1 MHz), 8 clocks x 3 CDR sequences x 2 ports,
  repeated from 4 return-pad snapshots (after Rx2 / Rx3 warm-up calls). The state is restored per case; a start state from which
  the call never reaches its return pad is not a result (reported as not compared; every case must be compared from >= 1 state).
  Compared: every changed register byte of the called port's MAC + PHY pages (no MAC status block 0xC0-0xDF, no other port: timer events and sim device models write those on sim time) and PhyPend,
  captured at the return pad (the sim runs on to its next stop check afterwards). OLD presets isr_g_usTMDSRxPhyClk[port] and refreshes
  isr_g_usInputPixelClk from it; NEW presets isr_g_usTMDSRxPixClk[port] and must leave g_usInputPixelClk alone.
  Needs an OLD image whose map has isr_g_usInputPixelClk: the sims look up g_usInputPixelClk, so give fastmachine.Machine.addr
  the isr_ spelling as fallback by hand for that run.
  Not run here: the EXINT0 handler (called alone it runs on into the main loop) and the main-thread scan copy.
Log: ./tmp/logs/tmds_pixclk_equiv.log
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import panel_sim as P
import phy_budget_sim as B
from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/tmds_pixclk_equiv.log"
REG_RANGES = ((0x7000, 0x7D00),)
MAX_TRIES = 5
WARMUPS = (
    2,
    3,
    2,
    3,
)  # return-pad snapshots after these warm-up calls (Rx2 / Rx3 PhySetDeferred)
PORT_STATE = (  # per-port xdata the set-up reads, zeroed so both images start from the same state
    ("isr_g_usTMDSRxClkCount", 4),
    ("isr_g_usTMDSRxPhyCount", 4),
    ("g_pucTMDSRxLEMax", 6),
    ("g_pucTMDSRxLEMin", 6),
    ("g_pucTMDSRxTap0Min", 6),
    ("g_pucTMDSRxTap0Max", 6),
    ("g_ucTMDSRxTap0Init", 2),
    ("g_pucTMDSRxTap1Max", 6),
    ("g_ucTMDSRxZ0Status", 2),
)
PATHS = (750, 1485, 2000, 2500, 3000, 3400, 3401, 5940)
CDR_SEQS = ((0, 1, 1), (0, 0, 1), (1, 1, 1))
STUBS = (
    ("ScalerTMDSRxMeasureClk_EXINT0", {"val": 0x0A00}),
    ("ScalerTMDSRxCheckDataDFE", {"carry": 0}),
)


def say(s):
    log_line(s, LOG, stamp_stdout=False)


def mac_status(addr, port):
    """HDMI MAC status block (offsets C0-DF: packet / SR flags): timer events of the firmware write it while a delay runs"""
    return addr >> 8 == 0x71 + port and 0xC0 <= (addr & 0xFF) <= 0xDF


def base_bytes(m):
    return bytes(m.core.xram[REG_RANGES[0][0] : REG_RANGES[0][1]])


def regs(m):
    return {a: m.rd(a, 1)[0] for lo, hi in REG_RANGES for a in range(lo, hi)}


def fill_state(m, rng):
    lo, hi = REG_RANGES[0]
    return bytes(rng.randrange(256) for _ in range(hi - lo))


SP_PAD = 0xE0  # return-pad stack: above the firmware's stack high-water mark; the 0x70 of phy_budget_sim can sit in live IRAM data


def run_call(run, chunk, im):
    m, c, p = run.m, run.m.core, run.m.p
    bank = None if chunk["addr"] < im.common else chunk["addr"] >> 16
    c.sfr[0x28] = 0
    c.xram[0xFFFF] = (bank or 0) & 15
    c.set_bank((bank or 0) & 15)
    c.iram[SP_PAD + 1], c.iram[SP_PAD + 2] = B.RET_PAD & 0xFF, B.RET_PAD >> 8
    c.sfr[0x01] = SP_PAD + 2
    m.stubs.setdefault(B.RET_PAD, []).append(
        (None, "replay", lambda m_, r: m_.request_stop())
    )
    c.pch[B.RET_PAD] |= 0xFFFF
    p.pc = chunk["addr"] & 0xFFFF
    m.run(50_000_000)


def collect(bin_, map_, tree):
    im = L.Image(bin_, map_, str(L.layout_of(bin_, tree)), 0x5000)
    run = P.Run(
        argparse.Namespace(bin=bin_, map=map_, mode="1080p60", report=True, tree=tree)
    )
    out = {}
    try:
        run.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        m = run.m
        chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
        for fn, ret in STUBS:
            m.stub(fn, lambda m_, r, ret=ret: ret)
        seq, nset = [0, 1, 1], [0]
        m.stub(
            "ScalerTMDSRxCheckCDRStable_EXINT0",
            lambda m_, r: (
                nset.__setitem__(0, nset[0] + 1),
                {"val": seq[min(nset[0], 2)]},
            )[1],
        )
        cap = {}
        lo, hi = REG_RANGES[0]

        def at_return(
            m_, r
        ):  # the state at the return pad, before the sim runs on to its next stop check
            x = m_.core.xram
            cap["regs"] = bytes(x[lo:hi])
            cap["mem"] = {k: bytes(x[a : a + n]) for k, (a, n) in cap_spec.items()}
            if cap.get(
                "want_snap"
            ):  # the warm-up's return: IE = 0, no run-up state of the boot stop
                cap["snap"] = m_.core.snap()
                cap["scal"] = {k: getattr(m_, k) for k in m_._SCALARS}

        cap_spec = {}
        m.stubs.setdefault(B.RET_PAD, []).append((None, "capture", at_return))
        m.core.pch[B.RET_PAD] |= 0xFFFF
        new = "_isr_g_usTMDSRxPixClk" in m.map_text
        sym = lambda s: m.addr(s)
        pix = sym("isr_g_usTMDSRxPixClk") if new else sym("isr_g_usTMDSRxPhyClk")
        glob = sym("g_usInputPixelClk" if new else "isr_g_usInputPixelClk")
        for var, wu in enumerate(
            WARMUPS
        ):  # the call only reaches its return pad from some boot-stop states: several start states
            cap["want_snap"] = True
            cap.pop("snap", None)
            for _ in range(
                MAX_TRIES
            ):  # the first calls after boot can be stale run-ups
                run_call(run, chunks[f"ScalerTMDSRx{wu}PhySetDeferred"], im)
                if "snap" in cap:
                    break
            cap["want_snap"] = False
            if "snap" not in cap:
                continue
            snap, scal = cap["snap"], cap["scal"]
            for port in (0, 1):
                rng = random.Random(325 + port)
                for pclk in PATHS:
                    for cdrs in CDR_SEQS:
                        state = fill_state(m, rng)
                        cap_spec.clear()
                        cap_spec.update(
                            pend=(sym("isr_g_ucTMDSRxPhyPend") + port, 1),
                            pix=(pix + 2 * port, 2),
                            glob=(glob, 2),
                        )
                        for attempt in range(
                            MAX_TRIES
                        ):  # a stale call never reaches the return pad: same start state, again
                            m.core.restore(snap)
                            m.core.sfr[0x07] &= (
                                0xFC  # PCON (0x87) idle / power-down off: the snapshot can sit in the main loop's idle wait
                            )
                            for k, v in scal.items():
                                setattr(m, k, v)
                            m.wr(lo, state)
                            m.core.iram[0x20:0x30] = bytes(
                                16
                            )  # bit variables (PHY_SET, high speed, ...): one known start state
                            for name, size in PORT_STATE:
                                m.wr(sym(name), bytes(size))
                            m.wr(sym("isr_g_ucTMDSRxClkIRQ"), bytes([1, 1]))
                            base = regs(m)
                            seq[:] = cdrs
                            nset[0] = 0
                            cap.clear()
                            m.wr(sym("isr_g_ucTMDSRxPhyPend") + port, bytes([1]))
                            m.wr(pix + 2 * port, pclk.to_bytes(2, "big"))
                            m.wr(glob, (0x3333).to_bytes(2, "big"))
                            run_call(
                                run, chunks[f"ScalerTMDSRx{port + 2}PhySetDeferred"], im
                            )
                            if "regs" in cap and cap["mem"]["pend"] == b"\x00":
                                break
                        else:
                            cap.setdefault("regs", base_bytes(m))
                            cap.setdefault(
                                "mem", {"pend": b"\xff", "pix": b"", "glob": b""}
                            )
                        pages = (
                            0x71 + port,
                            0x7B + port,
                        )  # this port's MAC + PHY pages, no status block: timer events and sim device models write the rest on sim time
                        got = {
                            lo + i: v
                            for i, v in enumerate(cap["regs"])
                            if (lo + i) >> 8 in pages and not mac_status(lo + i, port)
                        }
                        ok = cap["mem"]["pend"] == b"\x00"
                        out[f"v{var} phy p{port} {pclk} {cdrs}"] = (
                            sorted((a, v) for a, v in got.items() if base[a] != v),
                            cap["mem"]["pend"].hex(),
                            int.from_bytes(cap["mem"]["pix"], "big"),
                            int.from_bytes(cap["mem"]["glob"], "big"),
                            (ok, attempt),
                        )
    finally:
        run.bus.close()
    return out, new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", nargs=2, type=Path, required=True)
    ap.add_argument("--new", nargs=2, type=Path, required=True)
    ap.add_argument("--tree", default=str(ROOT))
    a = ap.parse_args()
    old, o_new = collect(*a.base, a.tree)
    new, n_new = collect(*a.new, a.tree)
    assert not o_new and n_new, "--base must be the old image, --new the per-port one"
    bad = compared = 0
    cases = {k.split(" ", 1)[1] for k in old}
    covered = set()
    for k, ov in old.items():
        nv = new.get(k)
        if nv is None or not (ov[4][0] and nv[4][0]):
            continue  # that start state never reached the return pad in one of the images: not a result
        compared += 1
        covered.add(k.split(" ", 1)[1])
        pclk = int(k.split()[3])
        # regs + Pend equal; OLD refreshed the shared clock from the port's, NEW leaves it alone (3333 preset)
        same = (
            ov[0] == nv[0]
            and ov[1] == nv[1]
            and ov[3] == pclk
            and nv[3] == 0x3333
            and nv[2] == pclk
        )
        if not same:
            bad += 1
            d = [i for i, (x, y) in enumerate(zip(ov, nv)) if x != y]
            say(
                f"MISMATCH {k}: fields {d}; only in old {sorted(set(ov[0]) - set(nv[0]))[:6]}, only in new {sorted(set(nv[0]) - set(ov[0]))[:6]}; old {ov[1:]} new {nv[1:]}"
            )
    say(
        f"{len(cases)} cases (2 ports x {len(PATHS)} clocks x {len(CDR_SEQS)} CDR sequences) x {len(WARMUPS)} start states: "
        f"{compared} compared, {len(cases - covered)} cases never compared, {bad} mismatches"
    )
    bad += len(cases - covered)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
