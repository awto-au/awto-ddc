#!/usr/bin/env python3
"""Diff two tmp/regs dumps register-by-register with regdb names (awto-ddc#26).

usage: regs_diff4k.py A.json B.json [--pages 00,31,...] [--skip-pages FD,FE,FF,9F]
  Prints `PPRR a b name` per differing register (-1 = unread). Skips pages absent from either dump.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regdb_query as Q  # noqa: E402


def main() -> int:
    a, b = (json.load(open(x))["pages"] for x in sys.argv[1:3])
    opt = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    only = opt("--pages", "")
    skip = set(opt("--skip-pages", "FD,FE,FF,9F").upper().split(","))
    names = {}
    for r in Q.load("RTD2795T-CG"):
        if r["kind"] == "REG":
            try:
                names.setdefault((r["page"].upper().zfill(2), int(r["address"], 0) & 0xFF), r["register"])
            except ValueError:
                pass
    n = 0
    for pg in sorted(set(a) & set(b)):
        if pg in skip or (only and pg not in only.upper().split(",")):
            continue
        for i, (x, y) in enumerate(zip(a[pg], b[pg])):
            if x != y:
                n += 1
                print(f"{pg}{i:02X} {x:3d}/{x:02x} {y:3d}/{y:02x}  {names.get((pg, i), '')}")
    print(f"# {n} differing registers", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
