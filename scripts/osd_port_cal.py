#!/usr/bin/env python3
"""OSD data port write cost: the unit-3 hardware write tests (docs/osd-hw-tests.md) replayed in the sim (docs/saver-fps-budget.md).

usage: osd_port_cal.py BIN [--mhz F]
  BIN built with -D _AWTO_OSD_HWTEST. Runs OP_WRITE (F_REPEAT: one 54 B chunk refilled once, then pure port writes) on the
  Scope 2 glyph range (13824 B, OSD hidden) per write mode, EA on / off, as `osd_hw_test.py t1 t2` does on the unit.
  Per case: the firmware's own ms (AwtoMs, as the unit reports it) and the precise sim time per byte between AwtoOhwPut
  entries (one 54 B chunk + its WDT kick + loop), instructions, CPU clocks and flash-fetch stall clocks per byte.
  HW = unit 3 values (osd_hw_test.log 2026-11-18, image ohw6) for the side-by-side ratio.
Log: ./tmp/logs/osd_port_cal.log
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import itertools

import osd_hw_test as H
from _log import log_line as _log_line

LOG = H.ROOT / "tmp/logs/osd_port_cal.log"
CHUNK = H.BUF
OP_LIMIT_S = 5.0                # fw time for one 13824 B write: unit worst 57 ms; sim generous, expiry = TimeoutError
HW_S2_FRAME = ((6.0, 31), (7.37, 37))    # osd_hw_test t8 on unit 3 (ohw6): host seconds of free run -> frame in progress
HW_US_PER_B = {(H.M_SDK, 0): 4.12, (H.M_DIRECT, 0): 2.60, (H.M_DIRECT, 1): 2.39, (H.M_TRIPLE, 0): 2.75, (H.M_TRIPLE, 1): 2.46}


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    a = ap.parse_args()
    dev = H.Sim(a.bin, a.bin.with_suffix(".map"), False)
    m = dev.m
    marks = []
    m.stub("AwtoOhwPut", lambda mm, r: marks.append((mm.wall_ms, mm.p.instr, mm.p.clk, mm.p.fm_stall)) and None)
    addr, words = H.RANGES["s2glyphs"]
    say(f"{a.bin.name}: f_cpu {m.clock.f_cpu / 1e6:.2f} MHz ({m.clock.src}); 13824 B per case, chunk {CHUNK} B")
    for mode in (H.M_SDK, H.M_DIRECT, H.M_TRIPLE):
        for ea_off in (0, 1):
            marks.clear()
            r = H.op(dev, H.OP_WRITE, OP_LIMIT_S, mode=mode, flags=H.F_REPEAT | (H.F_EA_OFF if ea_off else 0), seed=0x3C,
                     addr=addr, n=words * H.WORD_B, label="cal")
            d = [(b[0] - a_[0], b[1] - a_[1], b[2] - a_[2], b[3] - a_[3]) for a_, b in itertools.pairwise(marks)]   # skip chunk 0 (refill)
            n = len(d) * CHUNK
            us = sum(x[0] for x in d) * 1000.0 / n
            hw = HW_US_PER_B.get((mode, ea_off))
            say(f"  {H.MODE_NAMES[mode]:18s} EA {'off' if ea_off else 'on '}: fw {r['ms']} ms ({r['ms'] * 1000.0 / (words * H.WORD_B):.2f} us/B); "
                f"sim {us:.2f} us/B, {sum(x[1] for x in d) / n:.1f} instr/B, {sum(x[2] for x in d) / 4 / n:.1f} cycles/B "
                f"(fetch stall {sum(x[3] for x in d) / 4 / n:.1f}); hw {hw if hw else '-'} us/B"
                + (f" -> hw / sim {hw / us:.2f}" if hw else ""))
    dev.close()
    for free_s, hw_frame in HW_S2_FRAME:                                  # whole-saver check: Scope 2 frame in progress after a free run
        dev = H.Sim(a.bin, a.bin.with_suffix(".map"), True)               # unit 3 stores Rotate 180
        H.op(dev, H.OP_SAVER, OP_LIMIT_S, flags=0, n=H.SAVER_SCOPE2, label="scope2 on")
        t0 = dev.now()
        while dev.now() - t0 < free_s:
            dev.idle()
        H.set_flags(dev, H.F_HOLD)
        f = H.op(dev, H.OP_REGS, OP_LIMIT_S, label="regs")["frame"]
        say(f"  Scope 2 free run {free_s} s (Rotate 180): sim frame {f} in progress, unit 3 frame {hw_frame}")
        dev.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
