#!/usr/bin/env python3
"""ISR and interrupt-masked stretches of an image in the simulator, longest per site at 0.1 ms (docs/delays.md, #281).

usage: stall_sim.py BIN MAP [--mode 1080p60] [--top 12] [--scenario panel|sync|wake|wake-quick|wdt|all]
  Runs the panel_sim scenario on the DW8051 core with the clock model. PC hooks (no firmware change, nothing on hardware):
  - ISR: entry at each vector (0x03 + 8 n) -> the RETI that ends it (nested ISRs on a stack); keyed by vector.
  - masked: `clr EX0` / `clr EA` -> the next `setb` / `mov bit,c` of the same bit; keyed by bit and the function holding the clr.
  --scenario runs another sim script (sync_sim, wake_sim, wdt_sim events) with the same hooks on every SimBus it builds; `all` = every scenario, the max per site.
  The result is the sim's worst case for the scenarios (paths they do not reach are absent; the flash erase halt is not modelled: docs/irq-masks.md).
Log: tmp/logs/stall_sim.log; table tmp/logs/stall_sim.tsv
"""
import argparse
import collections
import sys
import types
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import panel_sim as P
from _repo import ROOT

LOG = ROOT / "tmp/logs/stall_sim.log"
TSV = ROOT / "tmp/logs/stall_sim.tsv"
VECTORS = {0x03: "EXINT0", 0x0B: "Timer0", 0x13: "EXINT1", 0x1B: "Timer1", 0x23: "Serial", 0x2B: "Timer2", 0x33: "EXINT2", 0x3B: "EXINT3", 0x43: "EXINT4", 0x4B: "EXINT5"}
RETI = 0x32
CLR_EX0, SET_EX0, CLR_EA, SET_EA = (bytes([0xC2, 0xA8]), bytes([0xD2, 0xA8]), bytes([0xC2, 0xAF]), bytes([0xD2, 0xAF]))
MASK_OPS = {CLR_EX0: ("EX0", 1), SET_EX0: ("EX0", 0), CLR_EA: ("EA", 1), SET_EA: ("EA", 0),
            bytes([0x92, 0xA8]): ("EX0", 0), bytes([0x92, 0xAF]): ("EA", 0)}     # mov EX0,c / mov EA,c restore a saved value: ends the section


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def attach(run, im, worst):
    m = run.m
    stack, open_mask = [], {}

    def hook(bank, pc, fn):
        m.stubs.setdefault(pc, []).append((bank, "probe", fn))
        m.core.pch[pc] |= 0xFFFF if bank is None else 1 << bank

    def enter(name):
        def f(m_, r):
            stack.append((name, m_.wall_ms))
        return f

    def leave(m_, r):
        if stack:
            name, t0 = stack.pop()
            worst[("isr", name)] = max(worst[("isr", name)], m_.wall_ms - t0)

    def mask(bit, on, site):
        def f(m_, r):
            if on:
                open_mask.setdefault(bit, (site, m_.wall_ms))
            elif bit in open_mask:
                s, t0 = open_mask.pop(bit)
                worst[("masked " + bit, s)] = max(worst[("masked " + bit, s)], m_.wall_ms - t0)
        return f

    for pc, name in VECTORS.items():
        hook(None, pc, enter(name))
    for c in im.chunks:
        if c["kind"] != "fn":
            continue
        code, base = im.code(c), c["addr"] & 0xFFFF
        bank = None if c["addr"] < im.common else c["addr"] >> 16
        site = c["name"].lstrip("_")
        for it in L.sweep(code, base):
            if it[0] != "i":
                continue
            ins = it[1]
            if ins.raw[0] == RETI:
                hook(bank, ins.addr, leave)
            elif bytes(ins.raw[:2]) in MASK_OPS:
                bit, on = MASK_OPS[bytes(ins.raw[:2])]
                hook(bank, ins.addr, mask(bit, on, site))


SCENARIOS = {"sync": ("sync_sim", []), "wake": ("wake_sim", []), "wake-quick": ("wake_sim", ["--quick"]), "wdt": ("wdt_sim", ["events"])}


def run_other(name, a, im, worst):
    """run another sim script's main() with the hooks attached to every SimBus it creates"""
    import runpy

    import fw_sim as S
    mod, extra = SCENARIOS[name]
    orig = S.SimBus.__init__

    def init(self, *args, **kw):
        orig(self, *args, **kw)
        attach(types.SimpleNamespace(m=self.m), im, worst)
    S.SimBus.__init__ = init
    argv = sys.argv
    try:
        sys.argv = [mod + ".py", *([extra[0]] if mod == "wdt_sim" else []), str(a.bin), str(a.map), *([e for e in extra if mod != "wdt_sim"])]
        runpy.run_path(str(Path(__file__).resolve().parent / (mod + ".py")), run_name="__main__")
    except SystemExit:
        pass
    except (S.SimError, TypeError, OSError) as e:                 # the scenario's own end checks (crash block read) may fail under the hooks; the stretches seen so far count
        say(f"scenario {name} ended with {type(e).__name__}: {e}")
    finally:
        sys.argv = argv
        S.SimBus.__init__ = orig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--scenario", default="panel", choices=["panel", *SCENARIOS, "all"])
    a = ap.parse_args()
    P.panel_times(a.tree)
    im = L.Image(a.bin, a.map, str(Path(a.tree) / "fw/bank_layout.tsv"), 0x5000)
    worst = collections.defaultdict(float)
    todo = ["panel", *SCENARIOS] if a.scenario == "all" else [a.scenario]
    for sc in todo:
        say(f"scenario {sc}")
        if sc == "panel":
            run = P.Run(argparse.Namespace(bin=a.bin, map=a.map, mode=a.mode, report=True, tree=a.tree))
            try:
                attach(run, im, worst)
                run.scenario()
            finally:
                run.bus.close()
        else:
            run_other(sc, a, im, worst)
    rows = sorted(worst.items(), key=lambda kv: -kv[1])
    TSV.parent.mkdir(parents=True, exist_ok=True)
    with TSV.open("w") as f:
        f.write("class\tsite\tlongest_ms_x10\n")
        for (cls, site), ms in rows:
            f.write(f"{cls}\t{site}\t{ms * 10:.1f}\n")
    say(f"stall_sim {a.bin.name}: {len(rows)} sites with a stretch; longest first (0.1 ms units)")
    for (cls, site), ms in rows[:a.top]:
        say(f"  {cls:11s} {site:40s} {ms * 10:8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
