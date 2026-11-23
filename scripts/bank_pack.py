#!/usr/bin/env python3
"""Plan a bank repack (awto-ddc#333 follow-up): run sdcc_bank --repack alone on tmp/sdcc-port/asm_ovl and print the numbers.

usage: bank_pack.py [--banks N] [--headroom BYTES] [--keep]   (needs a finished build: tmp/sdcc-port/asm_ovl)
  Prints per bank: fn / const / stub bytes, free; cross-bank call pairs; stubs. Writes tmp/scratch/bank_pack/<N>-<H>.{layout,map}.tsv
  --keep: copy the new map over fw/bank_map.tsv (the one-time relocation; commit it).
Log: tmp/logs/bank_pack.log
"""
import argparse
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_build as FB
import msg_table as MT
import sdcc_bank as SB
from sdcc_overlay import repo_root

ROOT = repo_root()
OUT = ROOT / "tmp/scratch/bank_pack"


def report(path, nbanks, cap, msg):
    rows = [ln.split("\t") for ln in Path(path).read_text().splitlines() if not ln.startswith("#")]
    use = defaultdict(Counter)
    for k, nm, r, off, sz in (x for x in rows if len(x) == 5 and x[0] != "area"):
        use[r][k] += int(sz)
        use[r][k + "_n"] += 1
    print("region  fn_B  const_B  stub_B  total  free   stubs")
    tot_free = 0
    for r in ["C", *map(str, range(nbanks))]:
        u = use[r]
        t = u["fn"] + u["const"] + u["stub"]
        capb = cap - (msg if r == str(nbanks - 1) else 0) if r != "C" else 0
        free = capb - t if r != "C" else None
        tot_free += free or 0
        print(f"{r:>5} {u['fn']:6} {u['const']:7} {u['stub']:7} {t:6} {free if free is not None else '':>6} {u['stub_n']:6}")
    print(f"banked free total {tot_free} B; stubs total {sum(use[r]['stub_n'] for r in use)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", type=int, default=10)
    ap.add_argument("--headroom", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--msg-size", type=lambda x: int(x, 0), default=MT.MSG_SIZE, help="debug-message block reserved at the top of the last bank")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fa = FB.parse_args(["--serial", "x", "--repack", "--headroom", str(a.headroom), "--cluster-weights", "fw/cluster_weights.json"])
    lay = OUT / f"{a.banks}-{a.headroom}.layout.tsv"
    argv = FB.bank_args(fa, lay) + ["--banks", str(a.banks), "--out", str(OUT / "asm_bank")]
    SB.MSG_RESERVE = {a.banks - 1: a.msg_size}                 # the message block sits at the top of the last bank
    sys.argv = [str(x) for x in argv]
    rc = SB.main()
    (OUT / f"{a.banks}-{a.headroom}.map.tsv").write_text(lay.with_name("bank_map.new.tsv").read_text())
    report(lay, a.banks, SB.BANK_SIZE - fa.common, a.msg_size)
    if a.keep:
        shutil.copy(lay.with_name("bank_map.new.tsv"), ROOT / "fw/bank_map.tsv")
        toml = ROOT / "fw/rl6449_memory.toml"
        t = re.sub(r"^code_banks\s*=\s*\d+", f"code_banks  = {a.banks}", toml.read_text(), flags=re.MULTILINE)
        t = re.sub(r"^addr = 0x[0-9A-Fa-f]+(\s*)", f"addr = 0x{a.banks * SB.BANK_SIZE - a.msg_size:X}\\1", t, flags=re.MULTILINE)
        t = re.sub(r"^size = 0x[0-9A-Fa-f]+", f"size = 0x{a.msg_size:X}", t, flags=re.MULTILINE)
        toml.write_text(t)
    return rc


if __name__ == "__main__":
    sys.exit(main())
