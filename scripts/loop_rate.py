#!/usr/bin/env python3
"""Main-loop rate of a unit: N `dev.py health` runs (unit logs fill), only the loop line + PASS count kept.

Use: loop_rate.py --unit 3 [--runs 3] [--boots 1] [--label TEXT]
- Window 1 of each run reads low while the previous run's OSD info pop-up draws: summary = median of windows 2..3.
- --boots K: `dev.py reset` before each group of runs (steady rate differs per boot); first run after a reset discarded.
- Log: tmp/logs/loop_rate.log; one TSV row per call in tmp/logs/loop_rate.tsv.
"""
import argparse, os, re, statistics, subprocess, sys, time
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


ROOT = repo_root()
SETTLE_TRIES = 5    # boot to ACTIVE ~1.2 s (#63 cold-boot table); 5 health runs (~20 s) then measure anyway
HEALTH_S = 60       # one health run takes ~4 s; 60 s = stall guard (awto-dan#53), expiry -> run counted as failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="3")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--boots", type=int, default=0, help="reset the unit before each group (0 = no reset, one group)")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    logs = ROOT / "tmp" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    rates = []
    with (logs / "loop_rate.log").open("a") as log:
        def out(s):
            line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()
        def health(tag, keep):
            try:
                r = subprocess.run([sys.executable, str(ROOT / "dev.py"), "health", "--unit", a.unit], capture_output=True,
                                   text=True, timeout=HEALTH_S, check=False)
            except subprocess.TimeoutExpired:
                out(f"{tag}: health exceeded {HEALTH_S} s")
                return False
            txt = r.stdout + r.stderr
            m = re.search(r"main loop\s+([\d.]+)/s mean of 3 x 1 s windows \(([^)]*)\)", txt)
            h = re.search(r"HEALTH \S+: (\d+)/(\d+) PASS", txt)
            wins = [float(x) for x in m.group(2).split(",")] if m else []
            out(f"{tag}: windows {wins}; health {h.group(1) + '/' + h.group(2) if h else '?'}" + ("" if keep else "  (discarded)"))
            if keep:
                rates.extend(wins[1:])
            return bool(h) and h.group(1) == h.group(2)

        for b in range(max(a.boots, 1)):
            if a.boots:
                rr = subprocess.run([sys.executable, str(ROOT / "dev.py"), "reset", "--unit", a.unit], capture_output=True,
                                    text=True, timeout=HEALTH_S, check=False)
                out(f"boot {b + 1}: reset rc={rr.returncode}")
                # after a reset: logo, search and first ACTIVE take a few s; settle until 11/11, then one more discard
                for k in range(SETTLE_TRIES):
                    if health(f"boot {b + 1} settle {k + 1}", False):
                        break
                health(f"boot {b + 1} settle +1", False)
            for i in range(a.runs):
                health(f"boot {b + 1} run {i + 1}", True)
        warm = rates
        med = statistics.median(warm) if warm else float("nan")
        spread = f"{min(warm):.1f}..{max(warm):.1f}" if warm else "-"
        out(f"SUMMARY unit {a.unit} {a.label}: steady median {med:.1f}/s, range {spread}, n={len(warm)} windows")
    with (logs / "loop_rate.tsv").open("a") as t:
        t.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\t{a.unit}\t{a.label}\t{med:.1f}\t{warm}\n")
    return 0 if warm else 1


if __name__ == "__main__":
    sys.exit(main())
