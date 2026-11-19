#!/usr/bin/env python3
"""A/B of two firmware images over the savers in the sim: ms per frame + frames md5 identity (docs/saver-fps-plan.md).

usage: saver_port_ab.py A.bin B.bin [--frames N] [--tag T] [--savers scope scope2 ...] [--upright-too]
  - per saver, Rotate 180 (unit 3 setting; --upright-too adds upright): saver_frames_md5.py on both images, all jobs in parallel;
    compares the shared frames' hashes. TSVs ./tmp/scratch/ab_<tag>_*.tsv. Log: ./tmp/logs/saver_port_ab.log
"""
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/saver_port_ab.log"
JOB_LIMIT_S = 900          # one saver run: 40 frames of Scope 2 at ~0.17 s fw each take ~2-3 min wall; stall limit x3


def run(cmd):
    return subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True, timeout=JOB_LIMIT_S, check=False)


def job(args):
    img, sv, rot, frames, t = args
    p = run(["scripts/saver_frames_md5.py", str(img), "--saver", sv, "--frames", str(frames), *([rot] if rot else []), "--tsv", str(t)])
    hit = [x for x in (p.stdout + p.stderr).splitlines() if "ms per frame" in x]
    return hit[-1].split(",")[-1].split("->")[0].strip() if hit else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--tag", default="ab")
    ap.add_argument("--savers", nargs="*", default=["scope2", "asteroids", "pacman"])
    ap.add_argument("--upright-too", action="store_true")
    a = ap.parse_args()
    (ROOT / "tmp/scratch").mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    cases = [(sv, rot) for sv in a.savers for rot in (("--rotate", "") if a.upright_too else ("--rotate",))]
    jobs = []
    for sv, rot in cases:
        for k, img in (("A", a.a), ("B", a.b)):
            jobs.append((img, sv, rot, a.frames, ROOT / f"tmp/scratch/ab_{a.tag}_{k}_{sv}{rot}.tsv"))
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(job, jobs))
    out = []
    for i, (sv, rot) in enumerate(cases):
        ta, tb = jobs[2 * i][4], jobs[2 * i + 1][4]
        c = run(["scripts/saver_frames_md5.py", "--compare", str(ta), str(tb)])
        out.append(f"{sv}{' rot180' if rot else ' upright'}: A {res[2 * i]} | B {res[2 * i + 1]} | md5 {'IDENTICAL' if c.returncode == 0 else 'DIFFER'}")
    LOG.write_text("\n".join(out) + "\n")
    print("\n".join(out))


main()
