#!/usr/bin/env python3
"""Plan a bank layout (awto-ddc#333): run sdcc_bank.py in dev or release mode alone and print the numbers. Writes nothing tracked.

usage: bank_pack.py [--mode release|dev] [--headroom BYTES] [--banks N]   (needs a finished build: tmp/sdcc-port/asm_ovl)
  release: fewest banks <= --banks (default code_banks) that fit at --headroom. dev: all --banks, 5 % spread, slots with slack.
  Prints per bank: fn / const / stub bytes, free, stub copies. Output tmp/scratch/bank_pack/<mode>-<H>.{layout,map}.tsv.
Log: tmp/logs/sdcc_bank.log
"""
import argparse
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_mem as CM
import fw_build as FB
import msg_table as MT
import sdcc_layout as SL
from sdcc_overlay import repo_root

ROOT = repo_root()
OUT = ROOT / "tmp/scratch/bank_pack"


def report(path, cap):
    rows = [ln.split("\t") for ln in Path(path).read_text().splitlines() if not ln.startswith("#")]
    use = defaultdict(Counter)
    for k, _nm, r, _off, sz in (x for x in rows if len(x) == 5 and x[0] != "area"):
        use[r][k] += int(sz)
        use[r][k + "_n"] += 1
    banks = sorted(int(r) for r in use if r != "C")
    print("region  fn_B  const_B  stub_B  total  free   stub_copies")
    free_total = 0
    for r in ["C", *map(str, banks)]:
        u = use[r]
        t = u["fn"] + u["const"] + u["stub"]
        free = None if r == "C" else cap - (MT.MSG_SIZE if int(r) == MT.MSG_BANK else 0) - t
        free_total += free or 0
        print(f"{r:>5} {u['fn']:6} {u['const']:7} {u['stub']:7} {t:6} {free if free is not None else '':>6} {u['stub_n']:6}")
    print(f"banks used {max(banks) + 1}; banked free total {free_total} B; min free per bank "
          f"{min(cap - (MT.MSG_SIZE if b == MT.MSG_BANK else 0) - sum(v for k, v in use[str(b)].items() if not k.endswith('_n')) for b in banks)} B; "
          f"stubs {sum(use[r]['stub_n'] for r in use)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["release", "dev"], default="release")
    ap.add_argument("--banks", type=int, default=CM.CODE_BANKS)
    ap.add_argument("--headroom", type=lambda x: int(x, 0), default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FB.LOG = (ROOT / "tmp/logs/bank_pack.log").open("a")
    fa = FB.parse_args(["--serial", "x", "--layout-mode", a.mode, "--headroom", str(a.headroom)])
    lay = OUT / f"{a.mode}.layout.tsv"
    py = sys.executable
    if a.mode == "release":
        _, hr = FB.release_bank_step(fa, py, lay, OUT / "asm_bank")
        a.headroom = hr
    else:
        rc = subprocess.run([str(x) for x in [py, *FB.bank_args(fa, lay), "--banks", a.banks, "--out", OUT / "asm_bank"]], cwd=ROOT, check=False).returncode
        if rc:
            return rc
    rc = 0
    (OUT / f"{a.mode}.map.tsv").write_text(lay.with_name("bank_map.new.tsv").read_text())
    report(lay, SL.BANK_SIZE - fa.common)
    return rc


if __name__ == "__main__":
    sys.exit(main())
