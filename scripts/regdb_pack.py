#!/usr/bin/env python3
"""Pack decoded register tables (vendor store) into the repo as gzip: re/regdb/<chip>.tsv.gz.

usage: regdb_pack.py            (all chips found in ~/vendors/realtek/analysis/regdb)
Source TSVs come from scripts/rtd_db_parse.py. Repo must stay PRIVATE (see CLAUDE.md exception).
Log: ./tmp/logs/regdb_pack.log
"""
import gzip, os, shutil
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
SRC = Path.home() / "vendors/realtek/analysis/regdb"
DST = ROOT / "re" / "regdb"
DST.mkdir(parents=True, exist_ok=True)
(ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
log = (ROOT / "tmp" / "logs" / "regdb_pack.log").open("w")
for p in sorted(SRC.glob("*.tsv")):
    out = DST / (p.name + ".gz")
    with p.open("rb") as f, out.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as g:
        shutil.copyfileobj(f, g)   # mtime=0: reproducible bytes, no spurious git diffs
    line = f"{p.name}: {p.stat().st_size} -> {out.stat().st_size} B"
    print(line); log.write(line + "\n")
