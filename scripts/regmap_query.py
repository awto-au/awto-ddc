#!/usr/bin/env python3
"""Query the register knowledge base re/regmap (regs.tsv, fields.tsv, obs/).

usage: regmap_query.py 06A4 [KEY ...]            one register: all columns + its field rows + tests
       regmap_query.py --page A7                 every row of a page
       regmap_query.py --undocumented-nonzero    regdb has no named field, an observation was nonzero
       regmap_query.py --undocumented-nonzero --changing   ... and it differs within one (unit, label, state) group
       regmap_query.py --changing                any register that differs within one state group (documented ones too)
       regmap_query.py --varying                 any register with more than one distinct value (any state)
       regmap_query.py --candidates [sensor]     status candidate (optionally one class)
       regmap_query.py --status unknown | --class counter | --grep TEXT   filters (combine freely)
       regmap_query.py --tests                   status candidate / unknown rows (and fields) whose test is not done, by test id (tests.tsv state; OT / T ids: docs/osd/open-items.md)
       regmap_query.py --i2c [TEXT]              device / command / SCDC rows of i2c.tsv (optionally those containing TEXT)
       regmap_query.py --no-test                 status candidate / unknown with no test_id (needs a test written)
       regmap_query.py --obs 06A4               every observation of a key (source, unit, label, time, method, value)
Options: --tsv (raw rows), --limit N (default 200, 0 = all)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regmap_lib as L


def line(r):
    obs = f"n={r['obs_n']} {r['obs_hist']}" if r.get("obs_n") else "never read"
    nm = r["regdb_name"] or r["sdk_name"].split(",")[0] or "-"
    tag = {"documented": "doc", "blank-reserved": "blank", "no-row": "norow"}[r["regdb_status"]]
    hand = " ".join(x for x in (r["class"], r["status"], r["test_id"]) if x)
    return f"{r['key']:8} {nm[:34]:34} {tag:5} {obs[:44]:44} {hand:28} {r['role'][:60]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--page")
    ap.add_argument("--undocumented-nonzero", action="store_true")
    ap.add_argument("--changing", action="store_true")
    ap.add_argument("--varying", action="store_true")
    ap.add_argument("--candidates", nargs="?", const="")
    ap.add_argument("--status")
    ap.add_argument("--class", dest="cls")
    ap.add_argument("--grep")
    ap.add_argument("--tests", action="store_true")
    ap.add_argument("--obs")
    ap.add_argument("--i2c", nargs="?", const="")
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--tsv", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args()
    if a.obs:
        k = a.obs.upper()
        n = 0
        for o in L.load_obs():
            if k in o.vals:
                n += 1
                m = o.meta
                print(f"{k}\t{o.vals[k]:02X}\t{o.sid}\tunit {m.get('unit')}\t{m.get('label')}\t{m.get('state')}\t{m.get('time')}\t{m.get('method')}")
        print(f"{n} observation(s)", file=sys.stderr)
        return 0
    if a.i2c is not None:
        for r in L.read_tsv(L.I2C)[1]:
            if a.i2c.lower() in " ".join(r.values()).lower():
                print(f"{r['key']:9} {r['status'] or '-':9} {r['test_id'] or '-':9} {r['role'][:70]}")
        return 0
    _, rows = L.read_tsv(L.REGS)
    _, flds = L.read_tsv(L.FIELDS)
    if a.keys:
        want = {k.upper() for k in a.keys}
        sel = [r for r in rows if r["key"] in want]
        for r in sel:
            for c in L.REG_COLS:
                if r.get(c):
                    print(f"  {c:15} {r[c]}")
            for f in (x for x in flds if x["key"] == r["key"]):
                print("  field " + "  ".join(f"{c}={f[c]}" for c in L.FLD_COLS if f.get(c) and c not in ("key", "fkey")) + f"  [{f['fkey']}]")
            print()
        if not sel:
            print("no such row", file=sys.stderr)
            return 1
        return 0
    sel = rows
    if a.page:
        sel = [r for r in sel if r["page"] == a.page.upper().zfill(2)]
    if a.undocumented_nonzero:
        sel = [r for r in sel if r["regdb_status"] != "documented" and r["obs_nonzero"] == "1"]
    if a.changing:
        sel = [r for r in sel if r["obs_vary_state"] == "1"]
    if a.varying:
        sel = [r for r in sel if r["obs_distinct"] not in ("", "0", "1")]
    if a.candidates is not None:
        sel = [r for r in sel if r["status"] == "candidate" and (not a.candidates or r["class"] == a.candidates)]
    if a.status:
        sel = [r for r in sel if r["status"] == a.status]
    if a.cls:
        sel = [r for r in sel if r["class"] == a.cls]
    if a.grep:
        g = a.grep.lower()
        sel = [r for r in sel if g in " ".join([r["regdb_name"], r["sdk_name"], r["our_name"], r["role"], r["notes"], r["regdb_fields"]]).lower()]
    if a.no_test:
        sel = [r for r in sel if r["status"] in ("candidate", "unknown") and not r["test_id"]]
    if a.tests:
        for r in L.read_tsv(L.I2C)[1]:
            if r["status"] in ("candidate", "unknown"):
                print(f"i2c   {r['key']:9} {r['status']:9} {r['test_id']:8} {r['role'][:60]}")
        done = {t["id"] for t in L.read_tsv(L.TESTS)[1] if t["state"] == "done"}
        sel = [r for r in sel if r["status"] in ("candidate", "unknown") and not (r["test_id"] and set(r["test_id"].replace(",", " ").split()) <= done)]
        sel.sort(key=lambda r: (r["test_id"] or "~", r["key"]))
        for f in flds:
            if f["status"] in ("candidate", "unknown"):
                print(f"field {f['fkey']:12} {f['name'][:30]:30} {f['status']:9} {f['test_id']:8} {f['role'][:60]}")
    if not any([a.page, a.undocumented_nonzero, a.changing, a.varying, a.candidates is not None, a.status, a.cls, a.grep, a.tests, a.no_test]):
        ap.print_help()
        return 2
    if a.tsv:
        print("\t".join(L.REG_COLS))
    for i, r in enumerate(sel):
        if a.limit and i >= a.limit:
            print(f"... {len(sel) - a.limit} more (--limit 0)", file=sys.stderr)
            break
        print("\t".join(r.get(c, "") for c in L.REG_COLS) if a.tsv else line(r))
    print(f"{len(sel)} register(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
