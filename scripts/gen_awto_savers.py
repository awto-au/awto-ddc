#!/usr/bin/env python3
"""Generate the saver run-id / VCP 0xEB defines in fw/test/saver.c from fw/awto/savers.tsv.

usage: gen_awto_savers.py [--check]
  Rewrites the block between `GENERATED-BEGIN awto_savers` / `GENERATED-END awto_savers` in fw/test/saver.c.
  --check: exit 1 when the block is out of date (gate `gensavers`).
Log: ./tmp/logs/gen_awto_savers.log
"""
import argparse
import sys
from pathlib import Path

import isostamp
import saver_names

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "fw/test/saver.c"
LOG = ROOT / "tmp/logs/gen_awto_savers.log"
BEGIN, END = "// GENERATED-BEGIN awto_savers", "// GENERATED-END awto_savers"
PAD = 40  # column of the value, as the hand-written defines


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def block():
    out = [BEGIN + " (fw/awto/savers.tsv; edit the TSV, not this block)"]
    for r in saver_names.load(saver_names.TSV):
        if r["run"] is not None:
            out.append(f"{'#define AWTO_SAVER_' + r['macro']:<{PAD}}{r['run']}")
    for r in saver_names.load(saver_names.TSV):
        if r["vcp"] is not None:
            out.append(f"{'#define AWTO_SAVER_NOW_' + r['macro']:<{PAD}}{r['vcp']}")
    out.append(END)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    txt = TARGET.read_text()
    i, j = txt.find(BEGIN), txt.find(END)
    if i < 0 or j < 0:
        log(f"FAIL: markers missing in {TARGET}")
        return 2
    new = txt[:i] + block() + txt[j + len(END):]
    if new == txt:
        log("saver defines up to date")
        return 0
    if a.check:
        log("FAIL: saver defines out of date: run scripts/gen_awto_savers.py")
        return 1
    TARGET.write_text(new)
    log(f"rewrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
