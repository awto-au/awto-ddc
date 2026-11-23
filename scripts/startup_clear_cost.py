#!/usr/bin/env python3
"""Startup cost in the sim: reset -> __sdcc_program_startup (external startup + RAM clear + XINIT copy), DW8051 clock model.

usage: AWTO_SIM_CORE=fast startup_clear_cost.py BIN MAP [--mhz 350.8]
- Prints instructions, CPU clocks and microseconds at --mhz (flash fetch stalls modelled). Used for flash-sector-churn rec 1.
Log: tmp/logs/startup_clear_cost.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S
import isostamp
from _repo import ROOT

LOG = ROOT / "tmp/logs/startup_clear_cost.log"
BUDGET = 200_000         # instr: clear + copy ~ 25k; expiry = FAIL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mhz", type=float, default=350.8)
    a = ap.parse_args()
    m = S.Machine(a.bin.read_bytes(), a.map, "startup")
    end = m.addr("_sdcc_program_startup")
    n = 0
    while m.core.p.pc != end and n < BUDGET:
        m.core.run(1); n += 1
    if n >= BUDGET:
        sys.exit(f"startup_clear_cost: no __sdcc_program_startup in {BUDGET} instr")
    clk = m.core.p.clk
    line = f"{isostamp.now()} {a.bin.name}: {n} instr, {clk} CPU clocks = {clk / a.mhz:.1f} us at {a.mhz} MHz"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
