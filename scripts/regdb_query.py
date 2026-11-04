#!/usr/bin/env python3
"""Compact queries over the decoded Realtek register tables (re/regdb or ~/vendors/realtek/analysis/regdb).

usage: regdb_query.py <chip> regs  [--name REGEX] [--addr 0xLO-0xHI] [--page 00] [--limit N]
       regdb_query.py <chip> fields --reg NAME           (bit-fields + descriptions of one register)
       regdb_query.py <chip> port  --addr 0x92           (indexed port registers behind an address)
<chip> e.g. RTD2795T-CG. Prints one line per register: page addr[port_idx] name reset.
"""
import csv, gzip, os, re, sys
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
CANDIDATES = [ROOT / "re" / "regdb", Path.home() / "vendors/realtek/analysis/regdb"]


def load(chip):
    for d in CANDIDATES:
        for name, opener in ((f"{chip}.tsv", open), (f"{chip}.tsv.gz", gzip.open)):
            p = d / name
            if p.exists():
                return list(csv.DictReader(opener(p, "rt", newline=""), delimiter="\t"))
    sys.exit(f"no table for {chip} in {CANDIDATES}")


def main():
    chip, cmd, a = sys.argv[1], sys.argv[2], sys.argv[3:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    rows = load(chip)
    limit = int(opt("--limit", 60))
    if cmd == "regs":
        rx = re.compile(opt("--name", "."), re.I)
        lo, hi = (int(x, 0) for x in opt("--addr", "0-0xffff").split("-"))
        n = 0
        for r in rows:
            if r["kind"] != "REG" or not rx.search(r["register"]):
                continue
            if opt("--page") and r["page"] != opt("--page"):
                continue
            if not lo <= int(r["address"], 0) <= hi:
                continue
            idx = f"[{r['port_idx']}]" if r["port_idx"] else ""
            print(f"{r['page']} {r['address']}{idx} {r['register']} reset={r['reset']}")
            n += 1
            if n >= limit:
                print(f"... (limit {limit})"); break
    elif cmd == "fields":
        for r in rows:
            if r["kind"] == "FIELD" and r["register"] == opt("--reg"):
                print(f"[{r['bit_high']}:{r['bit_low']}] {r['field']} {r['access']} rst={r['reset']}  {r['description']}")
    elif cmd == "port":
        addr = int(opt("--addr"), 0)
        seen = set()
        for r in rows:
            if r["kind"] == "REG" and r["port_idx"] and int(r["address"], 0) == addr and r["register"] not in seen:
                seen.add(r["register"])
                print(f"idx={r['port_idx']} {r['register']} reset={r['reset']}")
                if len(seen) >= limit:
                    print(f"... (limit {limit})"); break


if __name__ == "__main__":
    main()
