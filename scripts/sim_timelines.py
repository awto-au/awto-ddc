#!/usr/bin/env python3
"""Sim timelines of two images, side by side (#162): boot_sim, wake_sim, sync_sim, key_sim_test.

usage: sim_timelines.py BIN_A BIN_B [--tol-ms 1] [--sims boot_sim wake_sim ...] [--table]
- Runs each sim on both images (fast core), keeps the ring lines "+ NNN ms <text>" per sim and compares them in order.
- OK = same lines in the same order, every time within --tol-ms (default 1: integer-ms truncation at a tick edge).
- --table (#162 step 2, intended changes): no verdict; each sim's lines go to tmp/sim_timelines/<image>.<sim>.lines.txt and
  a milestone table (first line matching each MILESTONES pattern, ms) A vs B is printed.
Log: tmp/logs/sim_timelines.log
"""
import argparse, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/sim_timelines.log"
SIMS = ("boot_sim", "wake_sim", "sync_sim", "key_sim_test")
LINE = re.compile(r"^\s*\+\s*(\d+) ms (.*)$")
TEXT_MASK = re.compile(r"^(watchdog run-time:|MCU init: crystal clock, watchdog N).*")      # texts #162 step 1 made live: compare by prefix
SIM_LIMIT_S = 300          # one sim: gates run each in 5-25 s; 12x margin, expiry = FAIL
# old | #162 s3b texts (stage / mode / pin-edge lines folded into the machine lines): either side of an A/B
MILESTONES = (("panel VDD on", r"panel VDD switched on|^panel: OFF -> VDD"), ("first main-loop pass", r"first main-loop pass"),
              ("console opened", r"console opened"), ("eDP link trained", r"eDP-1 panel link trained|-> VIDEO \(\d+ ms\): eDP-1 link trained"),
              ("stream running", r"video stream to the panel running|-> VIDEO \(\d+ ms\): eDP-1 link trained"),
              ("backlight on (pin)", r"^backlight on$|-> BL_PWM \("), ("mode INITIAL", r"^mode INITIAL|^system: .* -> INITIAL \("),
              ("mode SEARCH", r"^mode SEARCH|^system: .* -> SEARCH \("),
              ("display setting", r"^display setting$|^system: .* -> DISPLAY SETTING \("),
              ("mode ACTIVE", r"^mode ACTIVE|^system: .* -> ACTIVE \("), ("backlight pin edges", None))
PIN_EDGE = re.compile(r"^backlight (on|off)$|backlight pin (on|off)")


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def lines(sim, binp: Path):
    mp = binp.with_suffix(".map")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{sim}.py"), str(binp), str(mp), "--out", str(ROOT / "tmp/sim_timelines" / f"{binp.stem}.{sim}")]
                       if sim != "key_sim_test" else [sys.executable, str(ROOT / "scripts" / f"{sim}.py"), str(binp), str(mp)],
                       capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, AWTO_SIM_CORE="fast", PYTHONHASHSEED="0"), timeout=SIM_LIMIT_S)
    out = []
    for ln in (r.stdout + r.stderr).splitlines():
        m = LINE.match(ln.split(" ", 1)[1] if re.match(r"^\d{4}-\d\d-\d\dT", ln) else ln)
        if m:
            out.append((int(m.group(1)), TEXT_MASK.sub(lambda x: x.group(1), m.group(2).strip())))
    return out


def table(sim, pa: Path, la, pb: Path, lb):
    import re as _re
    for p, ls in ((pa, la), (pb, lb)):
        out = ROOT / "tmp/sim_timelines" / f"{p.stem}.{sim}.lines.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(f"+{t:6d} ms {x}\n" for t, x in ls))
        say(f"  {sim}: {len(ls)} lines -> {out}")
    say(f"  {sim} milestones (first match, ms): {pa.stem} | {pb.stem}")
    for name, pat in MILESTONES:
        if pat is None:
            f = lambda ls: sum(1 for _, x in ls if PIN_EDGE.search(x))
            say(f"    {name:22s} {f(la):>6} | {f(lb):>6}")
            continue
        f = lambda ls: next((t for t, x in ls if _re.search(pat, x)), None)
        va, vb = f(la), f(lb)
        say(f"    {name:22s} {'-' if va is None else va:>6} | {'-' if vb is None else vb:>6}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--tol-ms", type=int, default=1)
    ap.add_argument("--sims", nargs="*", default=list(SIMS))
    ap.add_argument("--table", action="store_true", help="intended changes: dump lines + milestone table, no verdict")
    a = ap.parse_args()
    bad = 0
    for sim in a.sims:
        la, lb = lines(sim, a.a), lines(sim, a.b)
        if a.table:
            table(sim, a.a, la, a.b, lb)
            continue
        diffs = []
        if [t for _, t in la] != [t for _, t in lb]:
            diffs.append(f"event order / text differs ({len(la)} vs {len(lb)} lines)")
            for (ta, xa), (tb, xb) in zip(la, lb):
                if xa != xb:
                    diffs.append(f"  first: +{ta} {xa!r} | +{tb} {xb!r}")
                    break
        else:
            worst = max((abs(x - y) for (x, _), (y, _) in zip(la, lb)), default=0)
            if worst > a.tol_ms:
                diffs.append(f"time differs by {worst} ms (> {a.tol_ms})")
            say(f"  {sim}: {len(la)} lines, worst time difference {worst} ms")
        bad += bool(diffs)
        for d in diffs:
            say(f"  {sim}: {d}")
        say(f"{'FAIL' if diffs else 'OK  '} {sim}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
