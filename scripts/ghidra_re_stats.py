#!/usr/bin/env python3
"""Per-bank reversal progress: functions total (Ghidra export), named by status tag + verification verdict, typed globals.

usage: ghidra_re_stats.py          -> table on stdout + ./tmp/logs/ghidra_re_stats.log
Total = `/* @ 0x` function headers of ~/vendors/realtek/analysis/jxc-4k/bank<N>/decompiled_named.c (thunks and FUN_ included);
  bank 3 excludes 0x28C6-0xA7FF (table data mis-decoded as code).
Named = merged `func` rows of the bank program (scripts/ghidra_names_merge.py: own bank + common area) by status tag.
Typed globals = unique EXTMEM addresses of ghidra_globals*.tsv plus `var:<Type>` rows of the merged names (same map in every bank).
Verdicts = re/jxc-4k/phase2_verification.tsv (rows of the bank program).
"""
import os, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
VEND = Path.home() / "vendors/realtek/analysis/jxc-4k"
DATA = ROOT / "re" / "jxc-4k"


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghidra_names_merge as NM

DATA_REGION = (0x28C6, 0xA7FF)   # bank 3


def main():
    gl = {l.split("\t")[0].lower() for f in ("ghidra_globals.tsv",) for l in (DATA / f).read_text().splitlines() if l and not l.startswith("#")}
    typed = set(gl)
    for b in range(7):
        for a, r in NM.merged(b).items():
            if a.startswith("extmem:") and r["type"].startswith("var:") and not r["name"].startswith("DAT_"):
                typed.add(a)
    ver = {}
    p = DATA / "phase2_verification.tsv"
    for l in p.read_text().splitlines():
        if l and not l.startswith("#"):
            f = l.split("\t")
            ver[f[0]] = f[4]
    tags = ["[fw]", "[guess]", "[lib]", "[auto-sdk]", "[re-agent]", "[phase3]", "[?]"]
    out = ["bank  total  named  " + "  ".join(f"{t:>10}" for t in tags) + "  CONFIRMED  PLAUSIBLE  REFUTED"]
    tot, vt = Counter(), Counter()
    for b in range(7):
        heads = re.findall(r"^/\* @ 0x([0-9a-f]+)", (VEND / f"bank{b}" / "decompiled_named.c").read_text(errors="replace"), re.M)
        n = sum(1 for h in heads if not (b == 3 and DATA_REGION[0] <= int(h, 16) <= DATA_REGION[1]))
        c, v = Counter(), Counter()
        for a, r in NM.merged(b).items():
            if a.startswith("code:") and r["type"] == "func" and not r["name"].startswith("FUN_CODE_") \
                    and not (b == 3 and DATA_REGION[0] <= int(a[5:], 16) <= DATA_REGION[1]):
                c[r["status"]] += 1
                v[ver.get(f"{b if int(a[5:], 16) >= NM.COMMON_END else 0}:{a[5:]}", "-")] += 1
        named = sum(c.values())
        out.append(f"{b:>4}  {n:>5}  {named:>5}  " + "  ".join(f"{c[t]:>10}" for t in tags) + f"  {v['CONFIRMED']:>9}  {v['PLAUSIBLE']:>9}  {v['REFUTED']:>7}")
        tot.update(c); tot["n"] += n; vt.update(v)
    out.append(f" all  {tot['n']:>5}  {sum(x for k, x in tot.items() if k != 'n'):>5}  " + "  ".join(f"{tot[t]:>10}" for t in tags)
               + f"  {vt['CONFIRMED']:>9}  {vt['PLAUSIBLE']:>9}  {vt['REFUTED']:>7}")
    out.append(f"typed globals (same XDATA map in every bank): {len(typed)}  (ghidra_globals.tsv {len(gl)})")
    msg = "\n".join(out)
    print(msg)
    log = ROOT / "tmp" / "logs" / "ghidra_re_stats.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(msg + "\n")


if __name__ == "__main__":
    main()
