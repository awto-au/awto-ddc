#!/usr/bin/env python3
"""Main-loop host speed of the fast sim core on one image (awto-ddc#183): boot to ACTIVE, then a fixed simulated window.

usage: sim_loop_speed.py BIN [MAP] [--window 10] [--runs 2] [--repo PATH] [--perf]
- --repo: take fw_sim / fastmachine / mcs51_core.c from that checkout (old core A/B); default this one.
- Reports per run: host seconds for the window only (boot excluded), instructions/s, sim-time / host-time.
- --perf: wrap one extra window in `perf record` (needs perf); report in tmp/logs/sim_loop_speed.perf.txt.
Log: tmp/logs/sim_loop_speed.log
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/sim_loop_speed.log"
BOOT_INSTR = 160_000_000      # boot to ACTIVE budget, as the gates (boot_sim BUDGET_INSTR)
MODE_ACTIVE = 3


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def one(S, binp: Path, mapp: Path, window: float) -> tuple:
    bus = S.SimBus(binp, mapp, "loopspeed-" + binp.stem, None, boot=False, devs=[], video="1080p60")
    if not bus.run_until_mode(MODE_ACTIVE, BOOT_INSTR):
        raise SystemExit("never reached ACTIVE")
    m = bus.m
    i0, s0, t0 = m.p.instr, bus.now(), time.perf_counter()
    bus.wait(window)
    host = time.perf_counter() - t0
    p = m.p                                              # exactness: these must match between cores
    stubs = sum(m.stub_hits.values())                   # incl. observer hooks: a stub that starts doing work shows here
    return host, m.p.instr - i0, bus.now() - s0, (f"cycles {p.cycles} clk {p.clk} nirq {p.nirq} fm_miss {p.fm_miss} "
                                                  f"fm_stall {p.fm_stall} stub_hits {stubs}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--window", type=float, default=10.0, help="simulated seconds measured after ACTIVE")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--repo", type=Path, help="checkout whose sim core is measured (default: this one)")
    a = ap.parse_args()
    binp = a.bin.resolve()
    mapp = (a.map or a.bin.with_suffix(".map")).resolve()
    core = (a.repo or ROOT).resolve()
    sys.path.insert(0, str(core / "scripts"))
    os.environ["AWTO_SIM_CORE"] = "fast"
    import fw_sim as S                                    # noqa: E402  (the measured checkout's core)
    say(f"=== {binp.name}: core {core}, window {a.window} s sim, {a.runs} runs")
    for n in range(a.runs):
        host, ins, sim, cnt = one(S, binp, mapp, a.window)
        say(f"run {n + 1}: window host {host:.2f} s, {ins} instr, {ins / host / 1e6:.2f} M instr/s, "
            f"sim {sim:.2f} s, sim/host {sim / host:.3f}; {cnt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
