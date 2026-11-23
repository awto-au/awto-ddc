#!/usr/bin/env python3
"""eDP link training in the firmware sim with a DPCD sink model (#295): AUX transactions, iteration counts, instructions.

usage: dptx_lt_sim.py BIN MAP [--scenario ramp|fast|steps] [--json OUT]
  Boots the image to ACTIVE with the panel_sim stubs, but ScalerDisplayDPTxLinkSequence runs for real: the two AUX
  functions are replaced by a sink model (DPCD read / write on pData), the register-only DPTx helpers by no-ops.
  Records per image: every AUX transaction (addr, len, data), TrainPattern1/2 calls, lane Adjust calls (old per-lane or new
  generic names), instructions + cycles from LinkSequence entry to exit. Equal transcripts on two images = same call sequence.
  Scenarios (sink): fast = request vol 2 pre 0, CR done once it is written, EQ at once; ramp = requests 1, 2, then 2 / pre 1 ...
Log: ./tmp/logs/dptx_lt_sim.log
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S
from _log import log_line as _log_line

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/dptx_lt_sim.log"
NOOP = (
    "ScalerDisplayDPTxPhyInitial",
    "ScalerDisplayDPTxAnalogPhyConrol",
    "ScalerDisplayDPTxSSCSet",
    "ScalerDisplayDPTxStreamHanlder",
)
REG_RANGES = (
    (0x3800, 0x3C00),
    (0x9C00, 0x9E00),
)  # DPTx PHY / controller pages: the register writes of the training path
WATCH = (
    "ScalerDisplayDPTx1LinkTraining",
    "ScalerDisplayDPTx1TrainPattern1",
    "ScalerDisplayDPTx1TrainPattern2",
    "ScalerDisplayDPTx1TrainPatternEnd",
    "ScalerDisplayDPTx1TP1LaneAdjust",
    "ScalerDisplayDPTx1TP2LaneAdjust",
    "ScalerDisplayDPTx1TP1Lane0Adjust",
    "ScalerDisplayDPTx1TP1Lane1Adjust",
    "ScalerDisplayDPTx1TP1Lane2Adjust",
    "ScalerDisplayDPTx1TP1Lane3Adjust",
    "ScalerDisplayDPTx1TP2Lane0Adjust",
    "ScalerDisplayDPTx1TP2Lane1Adjust",
    "ScalerDisplayDPTx1TP2Lane2Adjust",
    "ScalerDisplayDPTx1TP2Lane3Adjust",
)
SINK_CAPS = bytes([0x12, 0x14, 0x84, 0x01, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


class Sink:
    """DPCD model. Lane n written level (103h + n): bits 0-1 vol, 3-4 pre. Requests per scenario."""

    def __init__(self, scenario):
        self.scenario, self.dpcd, self.tp, self.n_reads = scenario, {}, 0, 0
        self.lanes = [0, 0, 0, 0]

    def need(self):
        return {"fast": (2, 0), "ramp": (3, 1), "steps": (2, 1)}[self.scenario]

    def write(self, addr, data):
        for i, b in enumerate(data):
            self.dpcd[addr + i] = b
        if addr <= 0x102 < addr + len(data):
            self.tp = self.dpcd[0x102] & 3
        for n in range(4):
            if addr <= 0x103 + n < addr + len(data):
                self.lanes[n] = self.dpcd[0x103 + n]

    def read(self, addr, n):
        if addr == 0x600:
            return bytes([self.dpcd.get(0x600, 1)])
        if addr == 0x000:
            return SINK_CAPS[:n]
        if addr == 0x007 or addr == 0x107:
            return bytes([0] * n)
        if addr == 0x202:
            return self.status()
        return bytes(n)

    def status(self):
        nv, npre = self.need()
        cr = [1 if (self.lanes[k] & 3) >= min(nv, 3) else 0 for k in range(4)]
        eq = [
            1 if cr[k] and self.tp == 2 and ((self.lanes[k] >> 3) & 3) >= npre else 0
            for k in range(4)
        ]
        lane = [(cr[k] | (eq[k] * 6)) for k in range(4)]
        st01, st23 = lane[0] | lane[1] << 4, lane[2] | lane[3] << 4
        align = 0x81 if all(eq) else 0x80
        # adjust request: ask for the target level until the lane holds it, step one level per read in "ramp"
        req = []
        for k in range(4):
            v = min(nv, (self.lanes[k] & 3) + 1) if self.scenario == "ramp" else nv
            p = (
                min(npre, ((self.lanes[k] >> 3) & 3) + 1)
                if self.scenario == "ramp"
                else npre
            )
            req.append(v | p << 2)
        r01, r23 = req[0] | req[1] << 4, req[2] | req[3] << 4
        return bytes([st01, st23, align, 0, r01, r23])


class RegLog(S.Dev):
    """Register writes in the DPTx pages while the training window is open: (addr, value) in order."""

    def __init__(self, on):
        self.writes = tuple(a for lo, hi in REG_RANGES for a in range(lo, hi))
        self.on, self.log = on, []

    def on_write(self, m, a):
        if self.on():
            self.log.append(f"reg {a:04x} <- {m.rd(a)[0]:02x}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--scenario", default="fast", choices=("fast", "ramp", "steps"))
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--json", type=Path)
    ap.add_argument(
        "--nodelay",
        action="store_true",
        help="skip the delay routines: clk = code time only (cache fills included)",
    )
    a = ap.parse_args()
    w1c = S.W1C({0xFE69: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, 0xBADC: 0x01})
    win = {"open": False}
    rlog = RegLog(lambda: win["open"])
    bus = S.SimBus(
        a.bin,
        a.map,
        "dptxlt-" + a.bin.stem,
        None,
        boot=False,
        devs=[w1c, rlog],
        video=a.mode,
        ffwd=a.nodelay,
    )
    m = bus.m
    if a.nodelay:
        for fn in ("AwtoDelayXus", "AwtoDelayLoops", "AwtoDelayCnt"):
            if "_" + fn in m.sym:
                m.stub(fn, lambda m_, r: {})
    sink = Sink(a.scenario)
    tl = []
    ev, mark = [], {"t0": None, "c0": None, "t1": None, "c1": None, "tp1": 0, "tp2": 0}
    pdata = m.addr("pData")

    syms = sorted(
        int(x, 16) & 0xFFFF
        for x in re.findall(
            r"^D:\s+([0-9A-F]{8})\s+_ScalerDisplayDPTx1Nati\w*",
            m.map_text,
            re.MULTILINE,
        )
    )
    len_at = {
        "W": syms[0],
        "R": syms[2],
    }  # PARM_4 (length) of Write / Read; the pointer is pData in the training path

    def aux(kind):
        def fn(m_, r):
            addr = (r["r"][7] << 16) | (r["r"][5] << 8) | r["r"][3]
            ln = m.rd(len_at[kind])[0]
            if kind == "W":
                data = bytes(m.rd(pdata, ln))
                sink.write(addr, data)
            else:
                data = sink.read(addr, ln)
                m.wr(pdata, data)
            ev.append(f"{kind} {addr:05x} {ln:2d} {data.hex()}")
            tl.append((ev[-1], m.p.clk))
            return {"carry": 1}

        return fn

    m.stub("ScalerDisplayDPTx1NativeAuxWrite", aux("W"))
    m.stub("ScalerDisplayDPTx1NativeAuxRead", aux("R"))
    for fn in NOOP:
        if "_" + fn in m.sym:
            m.stub(fn, lambda m_, r: {"carry": 1})

    def seq(m_, r):
        mark["t0"], mark["c0"] = m.p.instr, m.p.clk
        win["open"] = True
        ev.append("LinkSequence")

    def seq_end(m_, r):
        pass

    m.stub("ScalerDisplayDPTxLinkSequence", seq)
    counts = {}
    for name in WATCH:
        if "_" + name in m.sym:

            def w(m_, r, name=name):
                counts[name] = counts.get(name, 0) + 1
                ev.append(name)
                if name == "ScalerDisplayDPTx1TrainPatternEnd":
                    mark["t1"], mark["c1"] = m.p.instr, m.p.clk
                    win["open"] = False

            m.stub(name, w)
    ok = bus.run_until_mode(3, 160_000_000)
    res = {
        "image": a.bin.name,
        "scenario": a.scenario,
        "active": ok,
        "counts": counts,
        "instr_seq_to_end": (mark["t1"] - mark["t0"])
        if mark["t0"] and mark["t1"]
        else None,
        "clk_seq_to_end": (mark["c1"] - mark["c0"])
        if mark["c0"] and mark["c1"]
        else None,
        "events": ev,
        "regs": rlog.log,
        "timeline": tl,
    }
    say(
        f"{a.bin.name} {a.scenario}: active={ok} counts={counts} instr={res['instr_seq_to_end']} clk={res['clk_seq_to_end']}"
    )
    say(f"   {len(rlog.log)} register writes in the window")
    for e in ev[:80]:
        say("   " + e)
    if a.json:
        a.json.write_text(json.dumps(res, indent=1))
    m.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
