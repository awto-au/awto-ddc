#!/usr/bin/env python3
"""Name a rtd_reg_dump.py capture with the regdb: list registers whose value != reset (or all with --all).

usage: rtd_reg_decode.py <dump.json> [--chip RTD2795T-CG] [--pages 9E,38] [--all] [--fields]
  --fields  also print bit-field breakdown (field=value) for each listed register
Log: ./tmp/logs/rtd_reg_decode.log
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regdb_query as Q  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--chip", default="RTD2795T-CG")
    ap.add_argument("--pages")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fields", action="store_true")
    a = ap.parse_args()
    d = json.loads(Path(a.dump).read_text())
    rows = Q.load(a.chip)
    regs = {(r["page"].upper(), int(r["address"], 0) & 0xFF): r for r in rows if r["kind"] == "REG" and not r["port_idx"]}
    fields = {}
    for r in rows:
        if r["kind"] == "FIELD":
            fields.setdefault(r["register"], []).append(r)
    root = Q.ROOT
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/rtd_reg_decode.log").open("a")
    want = set(a.pages.upper().split(",")) if a.pages else None
    for page, vals in d["pages"].items():
        if want and page not in want:
            continue
        for i, v in enumerate(vals):
            r = regs.get((page, i))
            rst = int(r["reset"], 16) if r and r["reset"] not in ("", None) and r["reset"].startswith("0x") else None
            if not a.all and (r is None or rst == v):
                continue
            name = r["register"] if r else "?"
            line = f"{page}:{i:02X} = 0x{v:02X}  {name}" + (f" (reset 0x{rst:02X})" if rst is not None else "")
            if a.fields and r:
                fl = []
                for f in fields.get(name, []):
                    hi, lo = int(f["bit_high"]), int(f["bit_low"])
                    fl.append(f"{f['field']}={(v >> lo) & ((1 << (hi - lo + 1)) - 1):#x}")
                line += "  [" + " ".join(fl) + "]"
            print(line); log.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
