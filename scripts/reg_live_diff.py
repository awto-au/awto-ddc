#!/usr/bin/env python3
"""Join live scans (reg_live_scan.py, tmp/regs/live/*.json) with the regdb, SDK names and the ISP dumps (tmp/regs/*.json).

usage: reg_live_diff.py [--out tmp/scratch] [--prefix live]
  Pass columns are <unit><label>, e.g. 1A 1B 1C 2A 2B 2C ('probe' scans are ignored; the newest scan per unit+label wins).
  Out (TSV): <prefix>_all, _changing_AB (same unit, passes A vs B differ), _undoc_nonzero, _neverread_nonzero (pages in no ISP dump),
  _unit_diff (units differ), _highlights (named addresses), _pagesummary (00/FF counts), plus a summary line on stdout.
  Read-only: no device access.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import gzip
import json
import re
import sys
from pathlib import Path

from _repo import ROOT

SDK_HDR = ROOT / "fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h"
RESERVED = re.compile(r"^(reserved|dummy|rsvd|res|resv|reserve|unused)\w*$", re.IGNORECASE)

# name, lo, hi inclusive
HIGHLIGHTS = [("ADC results", 0xFF09, 0xFF0C), ("IOSC trim counter", 0x06A4, 0x06A5), ("DSS status A", 0xA750, 0xA757),
              ("DSS status B", 0xAF50, 0xAF57), ("DC_PHY BIST_DETAIL A", 0xA7E0, 0xA7E3), ("DC_PHY BIST_DETAIL B", 0xAFE0, 0xAFE3)]


def load_regdb() -> dict[int, list[dict]]:
    by: dict[int, list[dict]] = collections.defaultdict(list)
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            by[int(r["address"], 0)].append(r)
    return by


def dbinfo(rows: list[dict] | None) -> tuple[str, str, str]:
    """(documented | blank | norow, register name, field summary)."""
    if not rows:
        return "norow", "", ""
    reg = [r for r in rows if r["kind"] == "REG"]
    named = [r for r in rows if r["kind"] == "FIELD" and r["field"].strip() and not RESERVED.match(r["field"].strip())]
    name = reg[0]["register"] if reg else ""
    if named:
        return "documented", name, ";".join(f"{r['field']}[{r['bit_high']}:{r['bit_low']}]" for r in named)
    return "blank", name, ""


def sdk_names() -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        for ln in SDK_HDR.read_text(errors="replace").splitlines():
            m = re.match(r"#define\s+P[0-9A-F]+_[0-9A-F]{2}_(\w+)\s+0x([0-9A-F]{4})\b", ln)
            if m:
                out[int(m.group(2), 16)] = m.group(1)
    except OSError:
        pass
    return out


def load_live(root: Path) -> dict[str, dict[int, int | None]]:
    """column '<unit><label>' -> {addr: value}; newest file per column."""
    cols: dict[str, tuple[str, dict[int, int | None]]] = {}
    for fn in sorted(glob.glob(str(root / "tmp/regs/live/*.json"))):
        with open(fn) as _f:
            d = json.load(_f)
        # no label = a read-behind probe file (reg_behind_*), not a scan pass
        if d.get("label") in ("probe", None) or d.get("result") != "ok" or "pages" not in d:
            continue
        col = f"{d['unit']}{d['label']}"
        vals = {(int(p, 16) << 8) | i: v for p, arr in d["pages"].items() for i, v in enumerate(arr)}
        if col not in cols or fn > cols[col][0]:
            cols[col] = (fn, vals)
    return {c: v for c, (_, v) in sorted(cols.items())}


def load_isp(root: Path) -> tuple[dict[int, list[int]], set[int]]:
    """addr -> all ISP-dump values (every unit/state); set of pages ever dumped."""
    vals: dict[int, list[int]] = collections.defaultdict(list)
    pages: set[int] = set()
    for fn in sorted(glob.glob(str(root / "tmp/regs/*.json"))):
        try:
            with open(fn) as _f:
                d = json.load(_f)
        except ValueError:
            continue
        for p, arr in (d.get("pages") or {}).items():
            pages.add(int(p, 16))
            for i, v in enumerate(arr):
                vals[(int(p, 16) << 8) | i].append(int(v, 16) if isinstance(v, str) else v)
    return vals, pages


def fmt(v) -> str:
    return "" if v is None else f"{v:02X}"


def write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "tmp/scratch"))
    ap.add_argument("--prefix", default="live")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    live = load_live(ROOT)
    if not live:
        raise SystemExit("no live scans in tmp/regs/live")
    cols = list(live)
    isp, isp_pages = load_isp(ROOT)
    db, sdk = load_regdb(), sdk_names()
    dbpages = {a >> 8 for a in db}
    header = ["addr", "regdb", "reg", "sdk_name", *cols, "isp_distinct", "flags"]
    allrows, chg, undoc, never, unitdiff, hl = [], [], [], [], [], []
    page = collections.defaultdict(lambda: collections.Counter())
    for addr in range(0x10000):
        vs = {c: live[c].get(addr) for c in cols}
        got = {c: v for c, v in vs.items() if v is not None}
        if not got:
            continue                                  # excluded / failed everywhere
        st, reg, _fields = dbinfo(db.get(addr))
        by_unit: dict[str, dict[str, int]] = collections.defaultdict(dict)
        for c, v in got.items():
            by_unit[c[0]][c[1:]] = v
        ab = any(len({u.get("A"), u.get("B")} - {None}) > 1 for u in by_unit.values())
        drift = any(len(set(u.values())) > 1 for u in by_unit.values())
        udiff = len(by_unit) > 1 and len({v for u in by_unit.values() for v in u.values()}) > 1
        nz = any(got.values())
        p = addr >> 8
        flags = ",".join(f for f, on in (("changing_AB", ab), ("drift_ABC", drift), ("unit_diff", udiff), ("nonzero", nz),
                                         ("never_read_page", p not in isp_pages), ("no_regdb_page", p not in dbpages)) if on)
        isp_d = " ".join(f"{v:02X}" for v in sorted(set(isp.get(addr, []))))
        row = [f"{addr:04X}", st, reg, sdk.get(addr, ""), *(fmt(vs[c]) for c in cols), isp_d, flags]
        allrows.append(row)
        page[p]["n"] += 1
        vals = set(got.values())
        page[p]["all00"] += vals == {0}
        page[p]["allFF"] += vals == {0xFF}
        page[p]["nz_undoc"] += st != "documented" and nz
        page[p]["chg"] += ab
        if ab:
            chg.append(row)
        if st != "documented" and nz:
            undoc.append(row)
        if p not in isp_pages and nz:
            never.append(row)
        if udiff:
            unitdiff.append(row)
        for name, lo, hi in HIGHLIGHTS:
            if lo <= addr <= hi:
                hl.append([name, *row])
    write(out / f"{a.prefix}_all.tsv", header, allrows)
    write(out / f"{a.prefix}_changing_AB.tsv", header, chg)
    write(out / f"{a.prefix}_undoc_nonzero.tsv", header, undoc)
    write(out / f"{a.prefix}_neverread_nonzero.tsv", header, never)
    write(out / f"{a.prefix}_unit_diff.tsv", header, unitdiff)
    write(out / f"{a.prefix}_highlights.tsv", ["group", *header], hl)
    write(out / f"{a.prefix}_pagesummary.tsv", ["page", "read", "all00", "allFF", "nonzero_undoc", "changing_AB", "in_isp_dump", "in_regdb"],
          [[f"{p:02X}", c["n"], c["all00"], c["allFF"], c["nz_undoc"], c["chg"], int(p in isp_pages), int(p in dbpages)]
           for p, c in sorted(page.items())])
    print(json.dumps({"columns": cols, "addresses_read": len(allrows), "changing_AB": len(chg), "undoc_nonzero": len(undoc),
                      "neverread_nonzero": len(never), "unit_diff": len(unitdiff),
                      "all00": sum(c["all00"] for c in page.values()), "allFF": sum(c["allFF"] for c in page.values()),
                      "neverread_pages": sorted(f"{p:02X}" for p in page if p not in isp_pages)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
