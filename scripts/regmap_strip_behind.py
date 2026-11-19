#!/usr/bin/env python3
"""One-shot: remove known-wrong read-behind values from the observation files of old (unfixed) scans (re/regmap/README.md "Read-behind").

usage: regmap_strip_behind.py [--dry-run]
  Per file without header #read_fix: drops every value of the read-behind pages (live / regdump: regmap_lib.read_behind_pages("live"),
  isp: the isp set) and stamps #read_behind_stripped=pages=..; N values. A page added to read_behind.tsv later is stripped on the next run.
  Idempotent. Derived artifacts have no legacy: the importer applies the same rule to a re-import of the source JSON.
Log: ./tmp/logs/regmap.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regmap_lib as L


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    total = files = 0
    for o in L.load_obs():
        vals, n = L.strip_behind(o.meta, dict(o.vals))
        line = f"{o.sid}: {n} values dropped"
        if n:
            files += 1
            total += n
            if not a.dry_run:
                L.write_obs(o.path, o.meta, vals)
        L.log("regmap_strip_behind " + line)
        if n:
            print(line)
    print(f"{total} values in {files} files{' (dry run)' if a.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
