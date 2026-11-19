#!/usr/bin/env python3
"""Clock matrix of the timing gates (extensive tier): each gate on the 350 / 175 / 87 MHz image of one source state.

usage: gate_matrix.py BASE_STEM [--gates delays,wdt,...] [--clocks 350,175,87] [--tree WORKTREE] [--build]
  BASE_STEM = tmp/fw/<serial>-<tag>-be, the default-clock (350) image. Siblings: <serial>-<tag>-clk175-be, -clk87-be
  (the names the delays gate already uses). --build: build a missing sibling (dev.py build -D AWTO_CLOCK_MHZ=n; the build keeps its
  default flash clock: 117 MHz at 350, 70 MHz below). Images are reused when present: the tag names the source state.
  Runs fw_gates.gates() commands per image (gates of one image in parallel, images in turn), writes no gates.json record.
Output: one table, gate x clock (PASS / FAIL / SKIP + seconds); a cell that passes at 350 and fails at 175 / 87 is the bug class of
  DP training at 350.8 vs 87.7. Log: tmp/logs/gate_matrix.log; per-cell gate logs: tmp/logs/gate_matrix/<image>.<gate>.log
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_gates as G

ROOT = G.ROOT
TIMING = ["delays", "wdt_full", "wake_full", "inputrate", "monitor_full", "deadport", "panel", "sysm", "htime", "keys_full"]
LOG = ROOT / "tmp/logs/gate_matrix.log"
BUILD_LIMIT_S = 300      # one build 40 s cold at load 15 (2026-11-19) x 7; stall guard of the build is its own


def log(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def sibling(base: Path, mhz: int) -> Path:
    return base if mhz == 350 else base.with_name(base.name.replace("-be.bin", f"-clk{mhz}-be.bin"))


def build(base: Path, mhz: int) -> None:
    serial, rest = base.name.split("-", 1)
    tag = rest[:-len("-be.bin")] + f"-clk{mhz}"
    log(f"build {serial}-{tag} (AWTO_CLOCK_MHZ={mhz})")
    subprocess.run([sys.executable, str(ROOT / "dev.py"), "build", "--serial", serial, "--tag", tag, "-D", f"AWTO_CLOCK_MHZ={mhz}"],
                   check=True, timeout=BUILD_LIMIT_S, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--gates", default=",".join(TIMING))
    ap.add_argument("--clocks", default="350,175,87")
    ap.add_argument("--tree", default=str(ROOT))
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    stem = Path(a.stem)
    base = stem if stem.suffix == ".bin" else stem.with_suffix(".bin")
    clocks = [int(x) for x in a.clocks.split(",")]
    want = a.gates.split(",")
    table, fails = {}, 0
    for mhz in clocks:
        b = sibling(base, mhz)
        if not b.is_file():
            if not a.build:
                log(f"{mhz} MHz: {b.name} missing (--build)")
                table[mhz] = {g: ("MISSING", 0.0) for g in want}
                continue
            build(base, mhz)
        m = b.with_suffix(".map")
        st = b.with_name(b.stem + ".settings_table.py")
        import os
        if st.is_file():
            os.environ["AWTO_SETTINGS_TABLE"] = str(st.resolve())
        cmds = G.gates(b, m, None, a.tree)
        skip = G.skips(b, m, a.tree)
        res, th = {}, []
        outdir = ROOT / "tmp/logs/gate_matrix"
        outdir.mkdir(parents=True, exist_ok=True)
        for g in want:
            if g in skip or g not in cmds:
                continue
            t = threading.Thread(target=G.run, args=(g, cmds[g], outdir / f"{b.stem}.{g}.log", res, log))
            t.start()
            th.append(t)
        for t in th:
            t.join()
        table[mhz] = {g: (("SKIP", 0.0) if g in skip or g not in cmds else ("PASS" if res[g][0] == 0 else "FAIL", res[g][1])) for g in want}
        fails += sum(1 for v in table[mhz].values() if v[0] == "FAIL")
    log("gate".ljust(11) + "".join(f"{c:>12} MHz" for c in clocks))
    for g in want:
        log(g.ljust(11) + "".join(f"{table[c][g][0] + ' ' + format(table[c][g][1], '.0f') + 's':>16}" for c in clocks))
    log(f"matrix: {fails} FAIL cell(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
