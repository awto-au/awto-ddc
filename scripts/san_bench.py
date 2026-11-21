#!/usr/bin/env python3
"""sdcc_san overhead: raw core throughput (instructions / CPU s) of an image, normal build vs -DSDCC_SAN build (sanitizer off / on).

usage: san_bench.py IMAGE.bin [--instr 20000000] [--reps 3]
- Core only (dw8051 timing + flash fetch model, no devices): same instruction stream in the three modes; best of --reps (CPU time).
Log: tmp/logs/san_bench.log
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE.parent / "tmp/logs/san_bench.log"
CHILD_TMO = 300       # 20 M instr at >= 5 M/s = 4 s; 300 s = host-process stall backstop on a loaded box


def child(img: str, n: int, on: bool):
    sys.path.insert(0, str(HERE))
    import fastmachine as FM
    mdl = json.loads(FM.MODEL_JSON.read_text())
    c = FM.Core(Path(img).read_bytes())
    c.set_dw(mdl)
    c.set_fetch(mdl)
    c.reset()
    if on:
        c.san_enable()
    t = time.process_time()
    c.run(n)
    print(f"{c.p.instr / (time.process_time() - t) / 1e6:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img")
    ap.add_argument("--instr", type=int, default=20_000_000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--child", choices=["normal", "off", "on"])
    a = ap.parse_args()
    if a.child:
        child(a.img, a.instr, a.child == "on")
        return 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    res = {}
    for mode in ("normal", "off", "on"):
        env = {**os.environ, **({"AWTO_SIM_SAN": "1"} if mode != "normal" else {})}
        best = max(float(subprocess.run([sys.executable, __file__, a.img, "--instr", str(a.instr), "--child", mode], env=env, capture_output=True,
                                        text=True, timeout=CHILD_TMO, check=True).stdout) for _ in range(a.reps))
        res[mode] = best
    line = f"{a.img}: Minstr/s normal {res['normal']:.2f} | san build, off {res['off']:.2f} ({res['off'] / res['normal']:.3f}x) | on {res['on']:.2f} ({res['on'] / res['normal']:.3f}x)"
    print(line)
    LOG.open("a").write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
