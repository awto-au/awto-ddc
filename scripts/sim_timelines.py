#!/usr/bin/env python3
"""Sim timelines of two images, side by side (#162): boot_sim, wake_sim, sync_sim, key_sim_test.

usage: sim_timelines.py BIN_A BIN_B [--tol-ms 1] [--sims boot_sim wake_sim ...]
- Runs each sim on both images (fast core), keeps the ring lines "+ NNN ms <text>" per sim and compares them in order.
- OK = same lines in the same order, every time within --tol-ms (default 1: integer-ms truncation at a tick edge).
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--tol-ms", type=int, default=1)
    ap.add_argument("--sims", nargs="*", default=list(SIMS))
    a = ap.parse_args()
    bad = 0
    for sim in a.sims:
        la, lb = lines(sim, a.a), lines(sim, a.b)
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
