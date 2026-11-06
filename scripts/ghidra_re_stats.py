#!/usr/bin/env python3
"""Per-bank reversal progress: functions total (Ghidra export), named by status tag, typed globals.

usage: ghidra_re_stats.py          -> table on stdout + ./tmp/logs/ghidra_re_stats.log
Total = `/* @ 0x` function headers of ~/vendors/realtek/analysis/jxc-4k/bank<N>/decompiled_named.c (thunks and FUN_ included).
Named = `func` rows of re/jxc-4k/ghidra_names_bank<N>.tsv by status tag; globals = rows of ghidra_globals*.tsv (same for all banks).
"""
import os, re
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
VEND = Path.home() / "vendors/realtek/analysis/jxc-4k"
DATA = ROOT / "re" / "jxc-4k"


def main():
    g = sum(1 for f in ("ghidra_globals.tsv",) for l in (DATA / f).read_text().splitlines() if l and not l.startswith("#"))
    tags = ["[fw]", "[guess]", "[lib]", "[auto-sdk]", "[re-agent]", "[?]"]
    out = ["bank  total  named  " + "  ".join(f"{t:>10}" for t in tags) + "  typed_globals"]
    tot = Counter()
    for b in range(7):
        n = len(re.findall(r"^/\* @ 0x", (VEND / f"bank{b}" / "decompiled_named.c").read_text(errors="replace"), re.M))
        c = Counter()
        for l in (DATA / f"ghidra_names_bank{b}.tsv").read_text().splitlines():
            f = l.split("\t")
            if not l.startswith("#") and len(f) >= 5 and f[2] == "func":
                c[f[4]] += 1
        named = sum(c.values())
        out.append(f"{b:>4}  {n:>5}  {named:>5}  " + "  ".join(f"{c[t]:>10}" for t in tags) + f"  {g:>6}")
        tot.update(c); tot["n"] += n
    out.append(f" all  {tot['n']:>5}  {sum(v for k, v in tot.items() if k != 'n'):>5}  " + "  ".join(f"{tot[t]:>10}" for t in tags))
    msg = "\n".join(out)
    print(msg)
    log = ROOT / "tmp" / "logs" / "ghidra_re_stats.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(msg + "\n")


if __name__ == "__main__":
    main()
