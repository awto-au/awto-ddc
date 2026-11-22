#!/usr/bin/env python3
"""AUX poll window of the DPTx AuxRead / AuxWrite per image in the sim (#295): time from DELAY_XUS(400) to the next retry.

usage: aux_window_sim.py BIN MAP [--n 40]
  The AUX done bit never comes (no sink): the real AuxRead / AuxWrite run their retry loops; PC hooks on _AwtoDelayXus and
  _AwtoDelayLoops give per window: the 400 us delay (clk) and the delay + 25 polls (clk). Window in us = 400 x window / delay.
  A reply later than the window costs one more window per transaction on the unit: the window is the margin.
Log: ./tmp/logs/aux_window_sim.log
"""

import argparse
import statistics
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itertools

import fw_sim as S

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/aux_window_sim.log"
NOOP = (
    "ScalerDisplayDPTxPhyInitial",
    "ScalerDisplayDPTxAnalogPhyConrol",
    "ScalerDisplayDPTxSSCSet",
    "ScalerDisplayDPTxStreamHanlder",
)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class NoReply(S.Dev):
    """P9D_B1 (AUX IRQ event) reads 0 and P9D_AE (FIFO pointer) 0: the sink never answers."""

    reads = (0x9DB1, 0x9DAE)
    writes = ()

    def init(self, m):
        for a in self.reads:
            m.wr(a, b"\x00")

    def on_read(self, m, a):
        m.wr(a, b"\x00")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--n", type=int, default=40, help="windows to collect")
    a = ap.parse_args()
    w1c = S.W1C({0xFE69: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, 0xBADC: 0x01})
    bus = S.SimBus(
        a.bin,
        a.map,
        "auxwin-" + a.bin.stem,
        None,
        boot=False,
        devs=[w1c, NoReply()],
        video="1080p60",
    )
    m = bus.m
    for fn in NOOP:
        if "_" + fn in m.sym:
            m.stub(fn, lambda m_, r: {"carry": 1})
    st = {"on": False, "xus": [], "loops": [], "seq": []}

    def seq(m_, r):
        st["on"] = True

    def xus(m_, r):
        if st["on"]:
            st["seq"].append(("X", m.p.clk))

    def loops(m_, r):
        if st["on"]:
            st["seq"].append(("L", m.p.clk))
        if len(st["seq"]) > 6000:
            m.request_stop()

    m.stub("ScalerDisplayDPTxLinkSequence", seq)
    m.stub("AwtoDelayXus", xus)
    m.stub("AwtoDelayLoops", loops)
    used = 0
    while used < 150_000_000 and len(st["seq"]) <= 6000:
        m.run(1_000_000)
        used += 1_000_000
    xs = [i for i, (k, _) in enumerate(st["seq"]) if k == "X"]
    win, dly = [], []
    for i, j in itertools.pairwise(xs):
        t0, t1 = st["seq"][i][1], st["seq"][j][1]
        loops_between = sum(1 for k, _ in st["seq"][i + 1 : j] if k == "L")
        if loops_between == 25:
            win.append(t1 - t0)
            first = next(c for k, c in st["seq"][i + 1 : j] if k == "L")
            dly.append(first - t0)
    if not win:
        say(f"{a.bin.name}: no window seen")
        return 1
    us = [400 * w / d for w, d in zip(win, dly)]
    say(
        f"{a.bin.name}: {len(win)} windows, delay400 {statistics.median(dly):.0f} clk, window {statistics.median(win):.0f} clk"
        f" = {statistics.median(us):.0f} us (min {min(us):.0f}, max {max(us):.0f})"
    )
    m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
