#!/usr/bin/env python3
"""Input-monitor scan rates in the firmware sim (fw/awto/inputs.tsv `rate`, docs/saver-mode.md D7).

usage: input_rate_sim.py BIN [MAP] [--pulses N]
  - Calibrates: reads of each tested row (hook on AwtoInRow) over CAL_S; the worst gap between two reads (idle window + DPS17 pulses at the sweep's phases) x WIDTH_MARGIN is the test pulse width.
  - Drives a pulse of that width at N start phases and checks every one is seen:
    slow row GPIO65 (ring entry), pass row DPS17 (edge counter, the #139 selector pulse rate), pass row ADC0 (ring entry, a key-ladder spike
    shorter than the key debounce, so no key action).
  - Also: the DPS17 pulse of #110 (PULSE_DPS17_US) and a pulse of half that width on the slow row (informational: slow rows may miss it).
Log: tmp/logs/input_rate_sim.log
"""
import argparse
import os
import sys
from pathlib import Path

import isostamp

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/input_rate_sim.log"
CAL_S = 6.0                       # calibration window: covers the periodic worst pass (~every second in the idle loop; the slowest periodic pass recurs every 3..5 s at 350.8 MHz)
PULSES = 40                       # start phases per case
PHASE_STEP_US = 777               # added to the idle gap between pulses: walks the start phase over the scan period
SETTLE_US = 1_000_000             # before a sweep: the SDK cable / source handling a pin pulse started has finished
IDLE_GAP_US = 60_000              # between pulses (> any worst gap x 1.25)
RUN_CHUNK = 100                   # instructions per step while timing a pulse (~30 us)
# The next gap exceeds the max of N calibration gaps with p = 1 / (N + 1): 40 test pulses meet one in 63 % of runs. Width = worst gap x 1.25 (repo timeout rule).
WIDTH_MARGIN = 1.25
PULSE_DPS17_US = 4000             # DPS17 pulse measured on unit 2 (#110, fw/awto/portsig.tsv)
ROW = {"GPIO65": 0, "DPS17": 28, "ADC0": 8}
PIN_GPIO65, PIN_DPS17, ADC0 = 0xFFE2, 0xFE33, 0xFF09      # GPIO65 = P1.2 (bit 2 of 0xFFE2): a spare pad, no SDK consumer
GPIO65_BIT = 4
ADC_IDLE, ADC_UP = 0xF8, 0x30     # key ladder idle (regdb reset) / inside the UP band 0x28..0x48
RING_HDR, RING_ENTRY, RING_N, SEQ_OFF = 16 + 44, 5, 32, 5   # StAwtoGpio: 16 B header, 44 values, then the 5 B ring; ucSeq at byte 5


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


class Rig:
    def __init__(self, a):
        self.s = R.Session(a.bin, a.map, "1080p60")
        self.s.boot()
        self.m = self.s.bus.m
        self.gpio = self.m.addr("g_stAwtoGpio")
        self.cnt = self.m.addr("g_pucAwtoInCnt")
        self.fails = 0

    def us(self) -> float:
        return self.m.wall_ms * 1000.0

    def run_us(self, us: float) -> None:
        """Run to wall time +us: big steps while far from the target (a step is a fixed instruction count, same machine state at any
        step size), RUN_CHUNK instructions near it, so the end lands within one RUN_CHUNK of the target as before."""
        t = self.us() + us
        while True:
            left_clk = (t - self.us()) * self.m.clock.f_cpu / 1e6
            if left_clk <= 0:
                return
            far = int(left_clk / self.m._avg_clk * 0.5)
            self.m.run(far if far > 4 * RUN_CHUNK else RUN_CHUNK)

    def calibrate(self) -> dict:
        reads = {k: [] for k in ROW.values()}
        on = [True]

        def hook(mm, r):
            if on[0] and (r["a1"] & 255) in reads:
                reads[r["a1"] & 255].append(self.us())

        def hook_poll(mm, r):                          # images before the rate column: every row is read in every AwtoGpioPoll
            if on[0]:
                for i in reads:
                    reads[i].append(self.us())

        if "_AwtoInRow" in self.m.sym:
            self.m.stub("AwtoInRow", hook)
        else:
            self.m.stub("AwtoGpioPoll", hook_poll)
        self.run_us(CAL_S * 1_000_000)                 # idle: the periodic worst pass
        for k in range(PULSES):                        # a DPS17 pulse walks the start phase like the sweep: the pass a pulse starts is part of the worst gap, at every phase
            self.run_us(IDLE_GAP_US + k * PHASE_STEP_US)
            self.pulse(PIN_DPS17, 1, 0, PULSE_DPS17_US)
        on[0] = False
        out = {}
        for n, i in ROW.items():
            g = [b - a for a, b in zip(reads[i], reads[i][1:])]
            out[n] = (len(reads[i]), max(g) if g else 0.0, sum(g) / max(1, len(g)))
            say(f"  calibrate {n} (row {i}): {out[n][0]} reads in {CAL_S:.0f} s, mean gap {out[n][2] / 1000:.2f} ms, worst gap {out[n][1] / 1000:.2f} ms")
        return out

    def ring(self) -> tuple:
        raw = self.m.rd(self.gpio + SEQ_OFF, 1)[0]
        return raw, self.m.rd(self.gpio + RING_HDR, RING_N * RING_ENTRY)

    def ring_new(self, seq0: int, ident: int) -> list:
        seq1, data = self.ring()
        out = []
        for q in range(seq0, seq0 + ((seq1 - seq0) & 0xFF)):
            e = data[(q & (RING_N - 1)) * RING_ENTRY:][:RING_ENTRY]
            if e[3] == ident:
                out.append(e[4])
        return out

    def pulse(self, addr: int, hi: int, lo: int, width_us: float) -> None:
        if addr == PIN_GPIO65:                       # a port byte: change only the pad's bit
            cur = self.m.rd(addr, 1)[0]
            hi, lo = cur | GPIO65_BIT, cur & ~GPIO65_BIT & 0xFF
        self.m.wr(addr, bytes([hi]))
        self.run_us(width_us)
        self.m.wr(addr, bytes([lo]))

    def sweep(self, name: str, addr: int, hi: int, lo: int, width_us: float, ident: int, count: bool, n: int) -> int:
        seen, deltas = 0, []
        self.run_us(SETTLE_US)
        self.pulse(addr, hi, lo, width_us)                 # warm-up pulse, not scored: the first pulse after a settle meets a one-off long pass
        for k in range(n):
            self.run_us(IDLE_GAP_US + k * PHASE_STEP_US)
            c0 = self.m.rd(self.cnt, 1)[0]
            seq0 = self.m.rd(self.gpio + SEQ_OFF, 1)[0]
            self.pulse(addr, hi, lo, width_us)
            self.run_us(IDLE_GAP_US)                       # let the scan see the falling edge too
            if count:
                deltas.append((self.m.rd(self.cnt, 1)[0] - c0) & 0xFF)
                seen += deltas[-1] == 1
            else:
                seen += self.ring_new(seq0, ident) == [hi, lo]
        say(f"  {name}: width {width_us / 1000:.2f} ms, {n} start phases: {seen} seen" + (f" (edge counter deltas {sorted(set(deltas))}: {[deltas.count(d) for d in sorted(set(deltas))]})" if deltas else ""))
        return seen

    def check(self, ok: bool, what: str) -> None:
        say(f"  {'PASS' if ok else 'FAIL'} {what}")
        self.fails += 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--pulses", type=int, default=PULSES)
    ap.add_argument("--info", action="store_true", help="also the two informational sweeps (the #110 pulse on DPS17, half the worst gap on the slow row): they assert nothing")
    ap.add_argument("--margin", type=float, default=WIDTH_MARGIN, help="test pulse width = worst gap x this (default 1.25; below 1 the gate must FAIL: tests/test_gate_mutations.py)")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    say(f"input_rate_sim {a.bin.name}")
    r = Rig(a)
    try:
        cal = r.calibrate()
        r.s.bus.close()
        r = Rig(a)                    # fresh boot without the hook: a breakpoint on AwtoInRow disturbs the pulse timing
        n = a.pulses
        w = cal["DPS17"][1] * a.margin
        r.check(r.sweep("pass row DPS17, worst gap x 1.25", PIN_DPS17, 1, 0, w, ROW["DPS17"], True, n) == n, "pass row DPS17: a pulse of 1.25 x the worst read gap is counted at every phase")
        if a.info:
            r.sweep("pass row DPS17, the #110 pulse (informational)", PIN_DPS17, 1, 0, PULSE_DPS17_US, ROW["DPS17"], True, n)
        w = cal["ADC0"][1] * a.margin
        r.check(r.sweep("pass row ADC0, worst gap x 1.25", ADC0, ADC_UP, ADC_IDLE, w, ROW["ADC0"], False, n) == n, "pass row ADC0: a pulse of 1.25 x the worst read gap is logged at every phase")
        w = cal["GPIO65"][1] * a.margin
        r.check(r.sweep("slow row GPIO65, worst gap x 1.25", PIN_GPIO65, 1, 0, w, ROW["GPIO65"], False, n) == n, "slow row: a pulse of 1.25 x the worst read gap is seen at every phase")
        if a.info:
            r.sweep("slow row GPIO65, half the worst gap (informational)", PIN_GPIO65, 1, 0, w / 2, ROW["GPIO65"], False, n)
        r.check(r.m.rd(r.gpio + 16 + ROW["ADC0"], 1)[0] == ADC_IDLE, "ADC0 back at idle")
    finally:
        r.s.bus.close()
    say(f"input_rate_sim: {'ALL PASS' if r.fails == 0 else str(r.fails) + ' FAIL'}")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
