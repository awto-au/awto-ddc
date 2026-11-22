#!/usr/bin/env python3
"""How many main-loop passes do nothing? (exact fast-forward potential of a tick-paced idle, for the gate plan)

usage: AWTO_SIM_CORE=fast idle_passes.py BIN MAP [--secs 10] [--mode 1080p60] [--top 12]
- Boots to ACTIVE, then watches AwtoDiagMainPass (one call per main-loop pass) for --secs of simulated time.
- At each pass entry the firmware-visible state (IRAM + the XDATA pool 0xD000..0xF7FF, registers excluded) is compared with the last
  pass. Cells that change in more than COUNTER_SHARE of the passes are counters (heartbeat, Timer2 time, loop stats): ignored.
  A pass whose other cells are all unchanged = no-work pass.
- Reports: passes, no-work share, instructions and simulated ms in no-work passes (= what a halted CPU until the next tick would skip),
  the counters found, and the cells that make the work passes.
Log: tmp/logs/idle_passes.log
"""
import argparse
import collections
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S

ROOT = S.ROOT
LOG = ROOT / "tmp/logs/idle_passes.log"
XLO, XHI = 0xD000, 0xF800
COUNTER_SHARE = 0.5          # a cell changing in more passes than this is a free-running counter


def say(s: str) -> None:
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--secs", type=float, default=10.0)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    bus = S.SimBus(a.bin, a.map, "idle-" + a.bin.stem, None, boot=False, video=a.mode)
    m = bus.m
    try:
        if not bus.run_until_mode(3):
            say("FAIL never reached ACTIVE")
            return 1
        bus.dbg_link_on()
        core = m.core
        passes = []                                    # (changed cells frozenset, instr, wall_ms) per pass interval
        last = {"x": None, "i": None, "instr": m.p.instr, "ms": m.wall_ms}

        def hit(mm, r):
            x, i = bytes(core.xram[XLO:XHI]), bytes(core.iram)
            if last["x"] is not None:
                ch = frozenset([("x", XLO + k) for k in range(len(x)) if x[k] != last["x"][k]] +
                               [("i", k) for k in range(256) if i[k] != last["i"][k]])
                passes.append((ch, m.p.instr - last["instr"], m.wall_ms - last["ms"]))
            last.update(x=x, i=i, instr=m.p.instr, ms=m.wall_ms)
        m.stub("AwtoDiagMainPass", hit)
        bus.wait(a.secs)
    finally:
        bus.close()
    n = len(passes)
    cnt = collections.Counter(c for ch, _, _ in passes for c in ch)
    counters = {c for c, k in cnt.items() if k > COUNTER_SHARE * n}
    idle = [(i, ms) for ch, i, ms in passes if not (ch - counters)]
    work = collections.Counter(c for ch, _, _ in passes for c in ch - counters)
    ti, tm = sum(i for _, i, _ in passes), sum(ms for _, _, ms in passes)
    say(f"{a.bin.name}: {n} passes in {tm / 1000:.2f} s simulated ({n / (tm / 1000):.0f} passes/s), {ti / 1e6:.1f} M instr")
    say(f"  no-work passes: {len(idle)} = {100 * len(idle) / max(n, 1):.1f} % of passes, {100 * sum(i for i, _ in idle) / max(ti, 1):.1f} % of instructions, "
        f"{100 * sum(ms for _, ms in idle) / max(tm, 1):.1f} % of simulated time")
    say(f"  counters (changing in > {COUNTER_SHARE * 100:.0f} % of passes): {len(counters)} cells: " +
        ", ".join(f"{sp}[0x{ad:04X}]" for sp, ad in sorted(counters)[:16]))
    say("  cells that make a pass a work pass: " + ", ".join(f"{sp}[0x{ad:04X}] x{k}" for (sp, ad), k in work.most_common(a.top)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
