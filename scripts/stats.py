#!/usr/bin/env python3
"""Build + test statistics of firmware images as one table (thin client over speed_bench, fw_stack, loop_pacing_sim, unit_health).

usage: stats.py [--tree DIR] [--label TEXT] [--no-record] [--no-sim] [--unit N] STEM [STEM ...]
  STEM = tmp/fw/<serial>-<tag>-be (.bin + .map beside it; its build log tmp/logs/build_<tag>_<serial>.out gives IRAM / XDATA).
  Columns: flash (common + banked unique code bytes), direct IRAM used/free, XDATA used/free, stack (main + nested worst case in both IP
  states; needs tmp/sdcc-port/asm_bank of THAT build, so run right after the build), cycles/pass + work (speed_bench), busy % / worst pass ms /
  passes/s (loop_pacing_sim idle ACTIVE), estimated free-run passes/s = paced passes/s / busy fraction, headroom factor = 1 / busy fraction.
  --unit N: the unit's health `headroom` row (passes/s, busy %, worst pass ms) is printed too (the unit runs whatever is flashed).
  After the table: the common-region record (scripts/common_metrics.py: areas, slots, stubs, chunks, top 10; no threshold).
  Rows go to docs/speed-bench.tsv through speed_bench / loop_pacing_sim (--no-record: none). Log: tmp/logs/stats.log
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import isostamp
import chip_mem as CM

HERE = Path(__file__).resolve().parent
COMMON_END = CM.COMMON_END
BANK = CM.BANK_SIZE
CODE_BANKS = CM.CODE_BANKS
XDATA_POOL = 6665
LOG = None


def say(s):
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def sh(root, *cmd, timeout=900):
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout, check=False, env=dict(os.environ, AWTO_DDC_REPO=str(root), AWTO_SIM_CORE="fast"))
    return r.stdout + r.stderr


def flash_bytes(b: Path):
    d = b.read_bytes()
    common = sum(1 for x in d[:COMMON_END] if x != 0xFF)
    banked = sum(sum(1 for x in d[n * BANK + COMMON_END:(n + 1) * BANK] if x != 0xFF) for n in range(CODE_BANKS) if (n + 1) * BANK <= len(d))
    return common, banked


def ram(root, stem: Path):
    m = re.match(r"(AWT\d+)-(.+)-be$", stem.name)
    log = root / f"tmp/logs/build_{m.group(2)}_{m.group(1)}.out" if m else None
    if not log or not log.exists():
        return None, None, None
    t = log.read_text(errors="replace")
    fx = re.findall(r"XDATA free (\d+) B of (\d+) B", t)
    fi = re.findall(r"free_direct': (\[[^\]]*\])", t)
    used = re.findall(r"'used': (\[[^\]]*\])", t)
    free_i = sum(n for _a, n in eval(fi[-1])) if fi else None
    used_i = sum(n for _a, n in eval(used[-1])) if used else None
    return (int(fx[-1][0]) if fx else None, free_i, used_i)


def stack(root):
    o = sh(root, sys.executable, "scripts/fw_stack.py", timeout=120)
    try:
        j = json.loads(o[o.index("{"):o.rindex("}") + 1])
    except ValueError:
        return None
    isr = j["isr"]
    st = {}
    for name, high in (("normal", ("_SysTimerIntProc2", "_SysTimerWDIntProc")), ("ps", ("_SysEXINT0", "_SysTimerWDIntProc"))):
        hi = max((isr.get(h, 0) for h in high), default=0)
        lo = max((v for k, v in isr.items() if k not in high), default=0)
        st[name] = j["main"] + 2 + hi + lo + 2 + 2
    return j["main"], st["normal"], st["ps"]


def main():
    global LOG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stems", nargs="+")
    ap.add_argument("--tree", type=Path, default=Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent))
    ap.add_argument("--label", default="stats")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--unit")
    a = ap.parse_args()
    root = a.tree.resolve()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp/logs/stats.log").open("a")
    hdr = ["image", "flash_common", "flash_banked", "iram_used", "iram_free", "xdata_used", "xdata_free", "stack_main", "stack_nest_normal", "stack_nest_ps",
           "cycles_pass", "work", "busy_pct", "worst_ms", "passes_s", "freerun_est_s", "headroom_x"]
    say("\t".join(hdr))
    for s in a.stems:
        stem = Path(s)
        stem = (root / stem) if not stem.is_absolute() else stem
        b = stem.with_suffix(".bin") if stem.suffix != ".bin" else stem
        c, bk = flash_bytes(b)
        xf, fi, ui = ram(root, b.with_suffix(""))
        sk = stack(root) or (None, None, None)
        cyc = work = busy = worst = pps = free = head = None
        if not a.no_sim:
            o = sh(root, sys.executable, "scripts/speed_bench.py", str(b.with_suffix("")), "--label", a.label, *(["--no-record"] if a.no_record else []))
            row = [l for l in o.splitlines() if "\t" in l][-1].split("\t")
            cyc, work = row[5], row[6]
            o = sh(root, sys.executable, "scripts/loop_pacing_sim.py", str(b), str(b.with_suffix(".map")), *([] if a.no_record else ["--bench", a.label]))
            m = re.search(r"headroom \(last 1 s\): (\d+) passes, sleep [\d.]+ % \(busy ([\d.]+) %\), worst busy pass ([\d.]+) ms", o)
            if m:
                pps, busy, worst = int(m.group(1)), float(m.group(2)), float(m.group(3))
                free, head = round(pps / (busy / 100)), round(100 / busy, 2)
        say("\t".join(str(x) for x in [b.stem, c, bk, ui, fi, XDATA_POOL - xf if xf is not None else None, xf, sk[0], sk[1], sk[2], cyc, work, busy, worst, pps, free, head]))
    for s in a.stems:
        mp = Path(s).with_suffix(".map")
        mp = mp if mp.is_absolute() else root / mp
        if mp.is_file():
            import common_metrics
            for ln in common_metrics.lines(common_metrics.measure(mp, root / "fw/bank_layout.tsv")):
                say(ln)
    if a.unit:
        o = sh(root, "./dev.py", "health", "--unit", a.unit, timeout=200)
        for l in o.splitlines():
            if "headroom" in l and ("PASS" in l or "FAIL" in l):
                say(f"unit {a.unit} health: " + l.split("headroom", 1)[1].strip()[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
