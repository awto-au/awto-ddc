#!/usr/bin/env python3
"""Run every regression image on two awto-ddc cores (dw8051 mode) and require byte-identical output (awto-ddc#183).

usage: sim_core_compare.py GEN_DIR --old OLD_REPO [--new NEW_REPO] [--runner DW8051_RUN] [--jobs 8]
- GEN_DIR: awto-sdcc tmp/build/support/regression/gen/<port> (.ihx images)
- Each image: awto-sdcc scripts/dw8051_run.py with AWTO_DDC_REPO = OLD_REPO, then NEW_REPO (default: this checkout);
  the whole stdout (test output, instruction count, clocks, stop reason) must match byte for byte.
- Prints identical / differing counts, the first differences, and summed host seconds per core.
Log: tmp/logs/sim_core_compare.log
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
LOG = ROOT / "tmp/logs/sim_core_compare.log"
RUN_TMO_S = 300     # one image: longest regression image runs ~15 s on ucsim (awto-sdcc sim_xcheck.py); same backstop there


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def run(runner: Path, repo: Path, ihx: Path) -> tuple[bytes, float]:
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, str(runner), str(ihx)], stdin=subprocess.DEVNULL, capture_output=True,
                       timeout=RUN_TMO_S, env={**os.environ, "AWTO_DDC_REPO": str(repo)})
    return r.stdout + b"\n--stderr--\n" + r.stderr + f"\nrc {r.returncode}".encode(), time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gen", type=Path)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, default=ROOT)
    ap.add_argument("--runner", type=Path, default=Path("/mnt/2tb/git/awto-sdcc-next/scripts/dw8051_run.py"))
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    imgs = sorted(a.gen.glob("*.ihx"))
    if not imgs:
        say(f"FAIL: no .ihx in {a.gen}")
        return 1
    run(a.runner, a.old, imgs[0])                  # build each core's .so once before the parallel runs
    run(a.runner, a.new, imgs[0])
    say(f"=== {len(imgs)} images in {a.gen}: old {a.old} vs new {a.new}, {a.jobs} jobs")

    def one(ihx):
        (o, to), (n, tn) = run(a.runner, a.old, ihx), run(a.runner, a.new, ihx)
        return ihx.stem, o, n, to, tn

    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, imgs))
    bad = [(s, o, n) for s, o, n, _, _ in res if o != n]
    for s, o, n in bad[:10]:
        say(f"  DIFF {s}:\n    old {o[-300:]!r}\n    new {n[-300:]!r}")
    say(f"{'FAIL' if bad else 'PASS'}: {len(res) - len(bad)} of {len(res)} identical; host s old {sum(r[3] for r in res):.1f}, "
        f"new {sum(r[4] for r in res):.1f}; wall {time.time() - t0:.1f} s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
