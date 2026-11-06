#!/usr/bin/env python3
"""Merge [lib] names (~/vendors/realtek/analysis/lib_match_names_bank<N>.tsv, from rtk_libsig.py) into re/jxc-4k/ghidra_names_bank<N>.tsv.
Priority: hand names (any status except [auto-sdk]/[lib]) > [lib] > [auto-sdk]. A [lib] line replaces an [auto-sdk] line at the
same address or with the same name; hand-named addresses/names are never touched. Idempotent. Log: ./tmp/logs/ghidra_merge_lib_names.log
"""
import os
from pathlib import Path
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
SRC = Path.home() / "vendors/realtek/analysis"
log = []
for b in range(7):
    p = ROOT / "re/jxc-4k" / f"ghidra_names_bank{b}.tsv"
    lines = p.read_text().splitlines()
    ent = lambda l: l.split("\t") if l and not l.startswith("#") else None
    hand_a = {e[0].lower() for l in lines if (e := ent(l)) and not (len(e) > 4 and e[4] in ("[auto-sdk]", "[lib]"))}
    hand_n = {e[1] for l in lines if (e := ent(l)) and not (len(e) > 4 and e[4] in ("[auto-sdk]", "[lib]"))}
    new = [l for l in (SRC / f"lib_match_names_bank{b}.tsv").read_text().splitlines() if ent(l)]
    take = {}
    for l in new:
        e = l.split("\t")
        if e[0].lower() in hand_a or e[1] in hand_n:
            continue
        take.setdefault(e[0].lower(), l); 
    names = {l.split("\t")[1] for l in take.values()}
    keep = [l for l in lines if not ((e := ent(l)) and len(e) > 4 and e[4] in ("[auto-sdk]", "[lib]")
                                     and (e[0].lower() in take or e[1] in names))]
    have = {e[0].lower() for l in keep if (e := ent(l))}
    add = [l for a, l in take.items() if a not in have or True]
    out = keep + [l for l in add if l.split("\t")[0].lower() not in {e[0].lower() for x in keep if (e := ent(x))}]
    p.write_text("\n".join(out) + "\n")
    log.append(f"bank{b}: {len(new)} lib names, {len(take)} merged ({len(new)-len(take)} blocked by hand names)")
print("\n".join(log))
(ROOT / "tmp/logs/ghidra_merge_lib_names.log").write_text("\n".join(log) + "\n")
