#!/usr/bin/env python3
"""Main-loop cost per handler while a screensaver runs, in the firmware sim (docs/saver-mode.md).

usage: saver_loop_cost.py BIN [MAP] [--window S] [--case NAME ...] [--tsv PATH]
  - Hooks the entry of every per-pass call in main() (SysMain.c); a slot = instructions from its entry to the next hooked entry.
  - Cases: active (picture, no saver), pacman / scope / scope2 / asteroids (VCP 0xEB = 2 / 3 / 4 / 8 over the picture),
    nosig (test cmd 0x33: D3 fixed, no source), nosig_scope2 (scope 2 started by VCP 0xEB in no signal).
  - Per case: passes, mean instr and fw us per pass, slot table (instr per pass, share), saver rate (Pac-Man sub-steps/s,
    scope frames/s from the gaps between column calls).
Log: ./tmp/logs/saver_loop_cost.log
"""
import argparse
import collections
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402
import pacman_sim as P  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_loop_cost.log"
VCP_SAVER = 0xEB
SETTLE_S = 2.5                  # fw time after the start: scope frames draw hidden first (~1.5 s, saver_sim RUN_S)
NOSIG_S = 3.0                   # fw time for D3 fixed to reach NO SIGNAL (wake_sim waits up to 5 s)
TC_D3_FIXED = 0x33              # test cmd: input D3, fixed port (wake_sim)
D3_PIN = 0xFE2C                 # D3 cable-detect pin (wake_sim D3_PIN)
FRAME_GAP_US = 95_000           # scope column calls further apart than this = the pause between frames (100 ms; a pass is < 75 ms)
PC_EVERY = 500                  # --pcprof: instructions between PC samples (as sim_pcprofile.py)
PC_TOP = 15
PASS_FIRST = "AwtoStackCheck"   # first call of a pass (SysMain.c main)
SLOTS = ["AwtoStackCheck", "AwtoSwPoll", "AwtoDiagMainPass", "AwtoGpioPoll", "AwtoKeyPoll", "AwtoDiagTestCmd", "AwtoSaverPoll",
         "SysMachineHandler", "UserCommonInterfacePanelPowerTick", "AwtoSwFastPoll", "AwtoWakePoll", "SysAudioHandler",
         "SysTimerHandler", "SysSourceHandler", "SysMachineWork", "SysDpRxHandler", "SysTMDSRxHandler", "ScalerHdcp2Handler",
         "AwtoSetLoop", "UserCommonInterfaceOsdHandler", "AwtoDdcciPoll", "AwtoNetPoll", "UserCommonDdcciHandler",
         "SysColorHandler", "ScalerDebug"]
SAVER_FN = {"pacman": "AwtoPacmanClassic", "scope": "AwtoScopeSaver", "scope2": "AwtoScopeSaver2", "nosig_scope2": "AwtoScopeSaver2", "asteroids": "AwtoAsteroids"}


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def us_now(m) -> float:
    return m.wall_ms * 1000.0 if getattr(m, "dw", None) else m.ticks / 12 / 4      # dw8051 wall clock; else a rough 4 clk/instr


def measure(a, case: str) -> dict:
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map, "1080p60", devs=[eng])
    sess.boot()
    m = sess.bus.m
    ddc = D.Mccs(sess.bus, eng)
    if case.startswith("nosig"):
        m.wr(D3_PIN, b"\x00")                       # D3 cabled, no source there (as wake_sim)
        P.send(sess, TC_D3_FIXED)
        sess.bus.wait(NOSIG_S)
    vcp = {"pacman": 2, "scope": 3, "scope2": 4, "nosig_scope2": 4, "asteroids": 8}.get(case)
    if vcp:
        ddc.set(VCP_SAVER, vcp)
    sess.bus.wait(SETTLE_S)
    ev, on = [], [False]
    names = [n for n in SLOTS if "_" + n in m.sym]
    for n in names:
        m.stub(n, lambda mm, r, n=n: on[0] and ev.append((n, mm.p.instr, us_now(mm))) and None)
    fn = SAVER_FN.get(case)
    calls = []
    if fn:
        m.stub(fn, lambda mm, r: on[0] and calls.append(us_now(mm)) and None)
    mode0 = sess.bus.mode_state()
    on[0] = True
    hits = collections.Counter()
    if a.pcprof:
        t_end = sess.bus.now() + a.window
        while sess.bus.now() < t_end:
            m.run(PC_EVERY)
            hits[m.where(m.p.bank, m.p.pc)] += 1
    else:
        sess.bus.wait(a.window)
    on[0] = False
    starts = [i for i, e in enumerate(ev) if e[0] == PASS_FIRST]
    cost, cost_us, n_pass = collections.Counter(), collections.Counter(), 0
    tot_i, tot_us, worst = 0, 0.0, 0.0
    for s, e in zip(starts, starts[1:]):
        for k in range(s, e):
            cost[ev[k][0]] += ev[k + 1][1] - ev[k][1]
            cost_us[ev[k][0]] += ev[k + 1][2] - ev[k][2]
        n_pass += 1
        tot_i += ev[e][1] - ev[s][1]
        dt = ev[e][2] - ev[s][2]
        tot_us += dt
        worst = max(worst, dt)
    r = {"case": case, "passes": n_pass, "instr": tot_i / max(1, n_pass), "us": tot_us / max(1, n_pass), "worst_us": worst,
         "hits": hits, "cost": {k: v / max(1, n_pass) for k, v in cost.items()}, "cost_us": {k: v / max(1, n_pass) for k, v in cost_us.items()}, "mode": (mode0, sess.bus.mode_state())}
    if fn and calls:
        span = calls[-1] - calls[0]
        if case == "pacman":
            iv = [(calls[j] - calls[j - 1]) / 1000 for j in range(1, len(calls))]
            r["rate"] = (f"{(len(calls) - 1) / span * 1e6:.2f} sub-steps/s ({(len(calls) - 1) / span * 1e6 / 4:.3f} game steps/s) over {span / 1e6:.1f} s; "
                         f"sub-step interval {min(iv):.1f}..{max(iv):.1f} ms, 5..95 % {sorted(iv)[len(iv) // 20]:.1f}..{sorted(iv)[-1 - len(iv) // 20]:.1f} ms")
        else:
            gaps = [j for j in range(1, len(calls)) if calls[j] - calls[j - 1] > FRAME_GAP_US]
            if len(gaps) >= 2:
                per = (calls[gaps[-1]] - calls[gaps[0]]) / (len(gaps) - 1)
                cols = (gaps[-1] - gaps[0]) / (len(gaps) - 1)
                r["rate"] = f"{1e6 / per:.2f} frames/s ({per / 1000:.0f} ms per frame, {cols:.0f} column calls per frame)"
            else:
                r["rate"] = f"{len(gaps)} frame gaps in the window: too few"
    sess.bus.close()
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--window", type=float, default=2.0, help="fw seconds measured")
    ap.add_argument("--case", nargs="*", default=["active", "pacman", "scope", "scope2", "nosig", "nosig_scope2"])
    ap.add_argument("--tsv", type=Path, help="append one row per case and slot")
    ap.add_argument("--pcprof", action="store_true", help="also sample the PC every PC_EVERY instr: functions by share")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    for case in a.case:
        r = measure(a, case)
        say(f"{a.bin.name} {case}: mode {r['mode'][0]}->{r['mode'][1]}, {r['passes']} passes, {r['instr']:.0f} instr/pass, "
            f"{r['us']:.0f} us/pass mean, {r['worst_us']:.0f} us worst; saver: {r.get('rate', '-')}")
        for k, v in sorted(r["cost"].items(), key=lambda x: -x[1]):
            u = r["cost_us"][k]
            say(f"    {v:9.0f} instr {u:8.0f} us  {100 * u / max(1, r['us']):5.1f} %  {k}")
        n = sum(r["hits"].values())
        for f, c in r["hits"].most_common(PC_TOP):
            say(f"    pc {100 * c / n:5.1f} %  {f}")
        if a.tsv:
            with a.tsv.open("a") as t:
                for k, v in r["cost"].items():
                    t.write(f"{a.bin.name}\t{case}\t{k}\t{v:.0f}\t{r['cost_us'][k]:.0f}\t{r['instr']:.0f}\t{r['us']:.0f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
