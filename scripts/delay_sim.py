#!/usr/bin/env python3
"""Every timed wait of an image measured in the simulator against its intended wall-clock time (docs/delay-audit.md).

usage: delay_sim.py BIN MAP [--tree DIR] [--other BIN MAP] [--audit] [--report]
  Runs the panel_sim scenario (cold boot, POWER off / on, signal loss, power saving = IOSC clock, wake) on the in-process DW8051 core
  with the clock model (scripts/sim_clock.py: f_cpu from the registers the firmware writes) and records, in wall ms (cycles / f_cpu):
  - class A (timer waits): entry -> return of ScalerTimerDelayXms / ScalerTimerPollingFlagProc / ScalerTimerWaitForEvent
    (every RET of the function is hooked), against the argument; Timer2 ms per wall ms over the whole run.
  - class B (micro-delays): every compiled DELAY_5US / DELAY_XUS loop site (scripts/delay_cal_check.py shapes), entry -> exit of the loop,
    min over its executions (hot loop: ISR time and the cold fetch of the first pass inflate the others), against the nominal
    (5 us, 4 us x outer count).
  - clock states seen (sim_clock log): the loop counts are per state (AWTO_DELAY_CNT), the min per site is judged at its state.
Judged (FAIL): Timer2 / wall outside TICK_TOL; a class A wait outside [arg - 1, arg + A_SLACK_MS] (timeouts: the bound); a class B site whose hot
  time is below LO x nominal or above HI x nominal (per clock state); a hooked site never executed is only listed.
Log: ./tmp/logs/delay_sim.log   Exit 1 on any FAIL.
"""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delay_cal_check as D
import fw_link_check as L
import panel_sim as P

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/delay_sim.log"
# Timer2 reload is a compile-time integer count of f_cpu / 12 / 1000: rounding is <= 0.01 %; 0.5 % = the sweep's tick limit (clk_sweep.py)
TICK_TOL = 0.005
# DelayXms counts ms-clock deadlines from a random phase: [n - 1, n] ms; + 2 ms for ISRs / the DDC wait pump inside the wait
A_SLACK_MS = 2.0
# Hot 5 us / 4 us loops: never below nominal (a wait is a minimum). Upper bound: one count (16 clk) + the entry clk, in % of nominal, by state.
LO = 0.99                         # float / 1 clk rounding of the wall clock
HI_PASS_CLK = 4 * 16              # per loop pass: one count of ceil() rounding + 3 for the nest's outer pass / entry / flash stall (sim 30..57 clk over the formula's 22)
A_EVENT_BOUND_MS = 91 + 1         # ScalerTimerWaitForEvent: _TIMER_WAIT_EVENT_TIMEOUT ticks, <= bound runs bound + 1 (SDK source [sdk-hypothesis], checked here)
STEADY_S = 2.0                    # Timer2 / wall window after the scenario: no clock switch inside
DDC_DEBOUNCE_US = 263.6           # ScalerSyncDdcDetectDebounce_EXINT1 at the stock clock: 230 passes x 100.5 clk / 87.7 MHz [emu]; kept equal at the fast clock


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class Probe:
    """Watch-only PC hooks on the fast machine (fastmachine.stub): entry / exit of a code range, wall ms from the clock model."""

    def __init__(self, m):
        self.m, self.t0, self.dur = m, {}, collections.defaultdict(list)
        self.states = {}

    def hook(self, bank, pc, fn):
        self.m.stubs.setdefault(pc, []).append((bank, "probe", fn))
        self.m.core.pch[pc] |= 0xFFFF if bank is None else 1 << bank

    def range(self, key, bank, pc, end, extra=None):
        def enter(m, r):
            self.t0[key] = (m.wall_ms, m.clock.f_cpu, m.clock.src, extra(m, r) if extra else None)

        def leave(m, r):
            s = self.t0.pop(key, None)
            if s:
                self.dur[key].append((m.wall_ms - s[0], s[1], s[2], s[3]))
        self.hook(bank, pc, enter)
        for e in (end if isinstance(end, (list, tuple)) else [end]):
            self.hook(bank, e, leave)


def chunk_bank(im, c):
    return None if c["addr"] < im.common else c["addr"] >> 16


def class_b_sites(im, mapp):
    v = D.var_addrs(mapp.read_text(errors="replace"))
    sites, _ = D.scan(im, v, D.shapes(v))
    out = []
    for tag, lst in sites.items():
        for c, addr, imm, endoff in lst:
            if c["name"].lstrip("_") in B_FUNCS:         # the routines' own loops: judged as routines (F probes)
                continue
            nom = 5.0 if tag.startswith("5us") else (imm * 4.0 if tag.startswith("xus") and "base" not in tag else 4.0)
            out.append((tag, c["name"].lstrip("_"), chunk_bank(im, c), addr, addr + endoff, nom))
    return out


def rets(im, c):
    code, base = im.code(c), c["addr"] & 0xFFFF
    return [it[1].addr for it in L.sweep(code, base) if it[0] == "i" and it[1].raw[0] == 0x22]


def attach(run, im, mapp):
    pr = Probe(run.m)
    nb = 0
    for tag, fn, bank, a, e, nom in class_b_sites(im, mapp):
        pr.range(("B", tag, fn, a, nom), bank, a, e)
        nb += 1
    chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
    na = 0
    for fn in ("ScalerTimerDelayXms", "ScalerTimerPollingFlagProc", "ScalerTimerWaitForEvent"):
        c = chunks.get(fn)
        if c is None:
            continue
        pr.range(("A", fn, 0, 0, 0), chunk_bank(im, c), c["addr"] & 0xFFFF, rets(im, c), extra=lambda m, r: r["a1"])
        na += 1
    nf = 0
    for fn in B_FUNCS:                                       # main-context micro-delays run in one routine each (fw/timer/delay.c)
        c = chunks.get(fn)
        if c is None:
            continue
        cnt = R6_ADDR                                                     # the outer passes: R6, set by the caller's inline asm
        pr.range(("F", fn, 0, 0, 0), chunk_bank(im, c), c["addr"] & 0xFFFF, rets(im, c),
                 extra=(lambda m, r, cnt=cnt: m.core.iram[cnt]) if fn == "AwtoDelayXus" else (lambda m, r: 0))
        nf += 1
    say(f"probes: {nb} inline class B loop sites, {nf} class B routines, {na} class A functions")
    return pr


B_FUNCS = ("AwtoDelayLoops", "AwtoDelayXus")      # Loops runs d_isr_g_ucDelay5usN_Call; Xus R6 outer passes of the 4 us base (AwtoDelayCnt: gap runs, no nominal)
R6_ADDR = 0x06                                   # bank 0 direct (fw/timer/delay.c)
HOT_CALLS = 20                    # a routine group is judged against the upper bound from this many calls on (fewer = cold code fetch after another state)


def call_clk() -> int:
    """clk the probe window leaves out: the caller's lcall and the routine's ret"""
    mdl = json.loads((ROOT / "scripts/dw8051_model.json").read_text())
    return sum(mdl["cycles"][op] for op in (0x12, 0x22)) * mdl["clk_per_cycle"]


RET_PAD = 0x0006     # code address never executed in the replay: the hook there stops the run (the replayed function returns to it)


def replay(run, bank, pc, times=2):
    """Execute one function in isolation on the finished sim (interrupts off, hot cache after the first pass): clk of the last pass."""
    m, c, p = run.m, run.m.core, run.m.p
    ie = c.sfr[0x28]
    c.sfr[0x28] = 0
    sp = 0x70
    m.stubs.setdefault(RET_PAD, []).append((None, "replay", lambda m_, r: m_.request_stop()))
    c.pch[RET_PAD] |= 0xFFFF
    last = 0
    for _ in range(times):
        c.xram[0xFFFF] = (bank or 0) & 15
        c.set_bank((bank or 0) & 15)
        c.iram[sp + 1], c.iram[sp + 2] = RET_PAD & 0xFF, RET_PAD >> 8
        c.sfr[0x01] = sp + 2
        p.pc = pc
        k0 = p.clk
        m.run(50_000_000)
        last = p.clk - k0
    c.sfr[0x28] = ie
    return last


def replays(run, im, mapp, fails):
    """C-class loops whose count is a compile-time number: wall time of the loop at the image's clock, hot."""
    out = []
    chunks = {c["name"].lstrip("_"): c for c in im.chunks if c["kind"] == "fn"}
    c = chunks.get("ScalerSyncDdcDetectDebounce_EXINT1"[:31])      # the map cuts names at 32 chars with the underscore
    if c is not None:
        cnt_a = run.m.addr("isr_g_usDDCDebounceCnt")
        xr = run.m.core.xram
        n = xr[cnt_a] << 8 | xr[cnt_a + 1]                                   # big-endian image
        clk = replay(run, chunk_bank(im, c), c["addr"] & 0xFFFF)
        us = clk / (run.m.clock.f_cpu / 1e6)
        out.append(("ScalerSyncDdcDetectDebounce_EXINT1", f"count {n}", us, DDC_DEBOUNCE_US, clk / max(n, 1)))
    for name, what, us, nom, per in out:
        ok = 0.95 * nom <= us <= 1.05 * nom
        say(f"  {'PASS' if ok else 'FAIL'} C {name} ({what}): {us:.1f} us hot, stock value {nom:g} us (SDK comment says 300 us [sdk-hypothesis], not what the stock count gives), {per:.1f} clk per pass at {run.m.clock.f_cpu / 1e6:.2f} MHz")
        fails += 0 if ok else 1
    return fails, out


def replay_sites(run, im, mapp, fails):
    """Every inline class B loop site, executed or not, run alone and hot at the finished sim's clock state (interrupts off, 3 passes,
    the last timed): [99 %, nominal + HI_PASS_CLK per pass]. Replaces 'the fastest executed site of the shape' (a loop that only an
    ISR ran, cold, in the scenario could not be judged that way)."""
    m, c, p = run.m, run.m.core, run.m.p
    ie = c.sfr[0x28]
    c.sfr[0x28] = 0
    mhz, bad, n = m.clock.f_cpu / 1e6, [], 0
    for tag, fn, bank, a, e, nom in class_b_sites(im, mapp):
        m.stubs[e] = [(None, "replay", lambda m_, r: m_.request_stop())]
        c.pch[e] |= 0xFFFF
        last = 0
        for _ in range(3):
            c.set_bank((bank or 0) & 15)
            p.pc = a
            k0 = p.clk
            m.run(50_000_000)
            last = p.clk - k0
        m.stubs.pop(e, None)
        c.pch[e] = 0
        us = last / mhz
        passes = max(1, round(nom / 4.0)) if tag.startswith("xus") and "base" not in tag else 1
        n += 1
        if not (LO * nom <= us <= nom + passes * HI_PASS_CLK / mhz):
            bad.append(f"{tag} {fn} 0x{a:04x}: {us:.2f} us (nominal {nom:g})")
    c.sfr[0x28] = ie
    say(f"  {'PASS' if not bad else 'FAIL'} B replay: {n} inline loop sites alone and hot at {m.clock.src} {mhz:.2f} MHz in [{LO * 100:.0f} %, nominal + {HI_PASS_CLK} clk per pass]" + (": " + "; ".join(bad[:6]) if bad else ""))
    return fails + (1 if bad else 0)


def judge(pr, run, fails):
    f = []
    wall = run.m.wall_ms
    t2 = run.bus._t2()
    ratio = None
    cl = run.m.clock.log
    dwell = collections.defaultdict(float)       # wall ms spent per (source, MHz); the steady states, not the 4 ms switch steps
    for (t0_, x, n), (t1_, _, _) in zip(cl, cl[1:] + [(wall, 0, "")]):
        dwell[(n, round(x / 1e6, 2))] += t1_ - t0_
    say("clock states (wall ms spent): " + ", ".join(f"{n} {mhz:g} MHz {ms:.0f}" for (n, mhz), ms in sorted(dwell.items(), key=lambda kv: -kv[1])) + f"; {len(cl)} changes")
    # class A
    a = collections.defaultdict(list)
    for k, v in pr.dur.items():
        if k[0] == "A":
            for d, fh, src, arg in v:
                a[k[1]].append((d, arg))
    for fn, v in sorted(a.items()):
        say(f"  A {fn}: {len(v)} calls, wall ms min {min(d for d, _ in v):.3f} max {max(d for d, _ in v):.3f}")
    bad = []
    for d, arg in a.get("ScalerTimerDelayXms", []):
        if not (arg - 1.0 - 0.05 <= d <= arg + A_SLACK_MS):
            bad.append((arg, round(d, 3)))
    f.append(("A DelayXms wall ms within [arg-1, arg+%g]" % A_SLACK_MS, not bad, f"{len(a.get('ScalerTimerDelayXms', []))} calls; outside: {bad[:6]}"))
    bad = [(arg, round(d, 3)) for d, arg in a.get("ScalerTimerPollingFlagProc", []) if d > arg + 1.0 + A_SLACK_MS]
    f.append(("A PollingFlagProc wall ms <= timeout + 1 + %g" % A_SLACK_MS, not bad, f"{len(a.get('ScalerTimerPollingFlagProc', []))} calls; outside (timeout, ms): {bad[:6]}"))
    bad = [round(d, 3) for d, _ in a.get("ScalerTimerWaitForEvent", []) if d > A_EVENT_BOUND_MS + A_SLACK_MS]
    f.append(("A WaitForEvent wall ms <= %d + %g" % (A_EVENT_BOUND_MS, A_SLACK_MS), not bad, f"{len(a.get('ScalerTimerWaitForEvent', []))} calls; outside: {bad[:6]}"))
    # class B routines (main-context DELAY_5US / DELAY_XUS): hot min per (clock state, routine, argument) against the nominal of the argument
    grp = collections.defaultdict(list)
    for k, v in pr.dur.items():
        if k[0] == "F":
            for d, fh, src, arg in v:
                grp[(src, round(fh / 1e6, 2), k[1], arg)].append(d * 1000.0)
    wrong, ovh = [], call_clk()
    for (src, mhz, fn, arg), us in sorted(grp.items()):
        nom, passes = (5.0, 1) if fn == "AwtoDelayLoops" else (arg * 4.0, max(arg, 1))
        tot = [u + ovh / mhz for u in us]                  # + the call's own clk: what a call site waits
        lo, hi = LO * nom, nom + (ovh + passes * HI_PASS_CLK) / mhz
        say(f"  F {fn}({arg}) {src:8s} {mhz:7.2f} MHz: {len(us):6d} calls, hot min {min(tot):.2f} us incl. the call = {min(tot) / nom * 100:.0f} % of {nom:g} us (allowed {lo:.2f}..{hi:.2f})")
        if min(tot) < lo or (len(us) >= HOT_CALLS and min(tot) > hi):
            wrong.append(f"{fn}({arg}) {src} {mhz:g} MHz: {min(tot):.2f} us not in {lo:.2f}..{hi:.2f}")
    f.append((f"B routines: {sum(len(v) for v in grp.values())} calls in {len(grp)} (state, routine, argument) groups, hot min in [{LO * 100:.0f} %, nominal + call + {HI_PASS_CLK} clk per pass]", not wrong and bool(grp), "; ".join(wrong[:6]) or ("" if grp else "no call ran")))
    # class B: per site min, judged at the clock state of the shortest pass
    rows, worst, grp = [], [], collections.defaultdict(list)
    by_state = collections.defaultdict(list)
    for k, v in pr.dur.items():
        if k[0] != "B":
            continue
        _, tag, fn, addr, nom = k
        d, fh, src, _ = min(v, key=lambda x: x[0])
        us = d * 1000.0
        passes = max(1, round(nom / 4.0)) if tag.startswith("xus") and "base" not in tag else 1
        hi = nom + passes * HI_PASS_CLK / (fh / 1e6)
        ok = LO * nom <= us                                      # per site: a wait is a minimum
        by_state[(src, round(fh / 1e6, 2), tag)].append(us / nom)
        grp[(src, round(fh / 1e6, 2), tag, nom)].append(us)
        rows.append((tag, fn, addr, nom, us, len(v), src, fh, ok))
        if not ok:
            worst.append(f"{tag} {fn} 0x{addr:04x} {us:.2f} us (nominal {nom:g}, {src} {fh / 1e6:.2f} MHz, {len(v)} runs)")
    for (src, mhz, tag), r in sorted(by_state.items()):
        say(f"  B {tag:14s} {src:8s} {mhz:7.2f} MHz: {len(r):3d} sites, hot min/median/max = {min(r) * 100:.0f} / {statistics.median(r) * 100:.0f} / {max(r) * 100:.0f} % of nominal")
    f.append((f"B {len(rows)} executed loop sites in [{LO * 100:.0f} %, nominal + {HI_PASS_CLK} clk per pass]", not worst, "; ".join(worst[:6])))
    seen = {k for k in pr.dur if k[0] == "B"}
    say(f"  B sites executed {len(seen)} of {len([k for k in pr.t0]) + len(seen)} seen-or-open (the rest of the compiled sites did not run in this scenario)")
    # tick
    all_t2, all_w = (t2 - run.t2_0) & 0xFFFFFFFF, wall - run.wall_0
    say(f"  info Timer2 ms per wall ms over the whole scenario: {all_t2} / {all_w:.1f} = {all_t2 / all_w:.5f} (clock switches: {len(run.m.clock.log)}; Timer2 runs slow while the CPU is on the 7 MHz crystal clock between states)")
    t2a, wa = run.bus._t2(), run.m.wall_ms
    run.bus.wait(STEADY_S)
    t2ms, wms = (run.bus._t2() - t2a) & 0xFFFFFFFF, run.m.wall_ms - wa
    ratio = t2ms / wms if wms else 0
    f.append((f"Timer2 ms per wall ms within +-{TICK_TOL * 100:.1f} % (steady {STEADY_S:g} s, {run.m.clock.src} {run.m.clock.f_cpu / 1e6:.2f} MHz)", abs(ratio - 1) <= TICK_TOL, f"{t2ms} ms Timer2 / {wms:.1f} ms wall = {ratio:.5f}"))
    import delay_audit as DA
    khz = round(run.m.clock.f_cpu / 1000.0)
    want = DA.counts(khz)
    ia, ib = run.m.addr("d_g_ucDelay5usN_Base"), run.m.addr("d_isr_g_ucDelayXusN_Base")
    have = (run.m.core.iram[ia] if ia < 256 else None, run.m.core.iram[ib] if ib < 256 else None)
    f.append((f"loop counts in the image = AWTO_DELAY_CNT of the running clock ({khz} kHz)", have == want, f"image {have}, formula {want}"))
    for name, ok, det in f:
        say(f"  {'PASS' if ok else 'FAIL'} {name}: {det}")
        fails += 0 if ok else 1
    return fails, rows, ratio


def measure(binp, mapp, tree, mode):
    """One image: the scenario with probes + the replays. Returns (fails, {'mhz', 'ratio', 'debounce_us'})."""
    im = L.Image(binp, mapp, str(Path(tree) / "fw/bank_layout.tsv"), 0x5000)
    say(f"delay_sim {binp.name}")
    run = P.Run(argparse.Namespace(bin=binp, map=mapp, mode=mode, report=True, tree=tree))
    try:
        pr = attach(run, im, mapp)
        run.t2_0, run.wall_0 = run.bus._t2(), run.m.wall_ms
        run.scenario()
        fails, rows, ratio = judge(pr, run, 0)
        mhz = run.m.clock.f_cpu / 1e6
        fails, crows = replays(run, im, mapp, fails)
        fails = replay_sites(run, im, mapp, fails)
    finally:
        run.bus.close()
    say(f"{'PASS' if fails == 0 else 'FAIL'} delay_sim {binp.name}: {fails} failed")
    return fails, {"mhz": mhz, "ratio": ratio, "debounce_us": crows[0][2] if crows else None, "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--other", nargs=2, type=Path, metavar=("BIN", "MAP"), help="second image at another clock (build -D AWTO_CLOCK_MHZ=87): measured too, and compared with the first")
    ap.add_argument("--variant", choices=("", "hwtest"), default="", help="with --audit: the image's variant (docs/delay-audit-<variant>.tsv holds its extra sites)")
    ap.add_argument("--audit", action="store_true", help="also delay_audit.py --check (every linked delay site is in docs/delay-audit.tsv)")
    ap.add_argument("--json", type=Path, help="write the per-image result here")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    P.panel_times(a.tree)
    fails, res = 0, []
    for b, m in [(a.bin, a.map)] + ([tuple(a.other)] if a.other else []):
        f, r = measure(b, m, a.tree, a.mode)
        fails += f
        res.append(r)
    if len(res) == 2:
        x, y = res
        dx = abs(x["debounce_us"] - y["debounce_us"]) / x["debounce_us"] if x["debounce_us"] else 1
        ok = dx <= 0.02 and x["mhz"] != y["mhz"]
        say(f"  {'PASS' if ok else 'FAIL'} both clocks ({x['mhz']:.1f} / {y['mhz']:.1f} MHz): DDC debounce wall time equal within 2 %: {x['debounce_us']:.1f} / {y['debounce_us']:.1f} us")
        fails += 0 if ok else 1
    if a.audit:
        import delay_audit as DA
        say("delay_audit --check")
        fails += DA.check(Path(a.tree), a.map, a.variant)
    if a.json:
        a.json.write_text(json.dumps([{k: v for k, v in r.items() if k != "rows"} for r in res]))
    say(f"{'PASS' if fails == 0 else 'FAIL'} delay_sim total: {fails} failed")
    return 1 if fails and not a.report else 0


if __name__ == "__main__":
    sys.exit(main())
