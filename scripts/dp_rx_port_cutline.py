#!/usr/bin/env python3
"""Cut-line for a second DP Rx port (#326 / #318): every Rx1-named global of the linked SDK, its class, and the functions that touch it.

usage: dp_rx_port_cutline.py [--check | --write] [--tree DIR]
  Data: docs/dp-rx-port-state.tsv (hand column `class`, generated column `functions`).
  Classes: lt-hot (lane-loop / ISR link-training state: per-port table first), lt-cold (other link-training / AUX state),
           rx-other (HDCP, colour, infoframe, MST, PHY CTS: per-port by nature, no ISR lane loop), shared (one instance by design).
  --check: fail when an lt-hot global is declared or used outside the DPRX_T / NAME_P accessors,
           or when a defined Rx1-named global is not in the TSV (classify it; lt-* state goes through the per-port accessors),
           or a TSV row has no definition. --write: add new rows as `unclassified`, refresh `functions`.
Log: ./tmp/logs/dp_rx_port_cutline.log
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/dp_rx_port_cutline.log"
TSV = ROOT / "docs/dp-rx-port-state.tsv"
TREE = ROOT
CLASSES = {"lt-hot", "lt-cold", "rx-other", "shared"}
DEF = re.compile(r"^(?:volatile |__xdata |bit |BYTE |WORD |_Bool |Struct\w+ |Enum\w+ )+\**(\w*[Dd][Pp][Rr]x1\w*)(?:\[[^\]]*\])*\s*(?:=|;)")
TAB = re.compile(r"^DPRX_T[134]\([^,]+,\s*\w+,\s*(\w+)\)")      # per-port state declared through the accessor macros: old name = single-port name
TP1 = re.compile(r"^#define DPRX_TP1INIT_DEF\s+(?:volatile )?bit (\w+)")
FUNC = re.compile(r"^(?:static )?\w[\w ]*?\**\s*(\w+)\(")


def say(s):
    log_line(s, LOG, stamp_stdout=True)


def sources():
    out = subprocess.run(["git", "ls-files", "-z", "fw/sdk"], capture_output=True, text=True, check=True, cwd=TREE).stdout.split("\0")
    return [TREE / f for f in out if f.endswith((".c", ".h")) and "/Lib/" not in f]


def scan():
    defs, uses, bare = {}, {}, {}
    via = set()
    files = sources()
    for f in files:
        if f.suffix != ".c":
            continue
        for ln in f.read_text(errors="replace").split("\n"):
            m = DEF.match(ln) or TAB.match(ln)
            if m and "extern" not in ln:
                defs[m.group(1)] = f.name
                if TAB.match(ln):
                    via.add(m.group(1))
    for f in files:
        for ln in f.read_text(errors="replace").split("\n"):
            m = TP1.match(ln)
            if m:
                defs[m.group(1)] = f.name
    alias = {}
    for f in files:
        for ln in f.read_text(errors="replace").split("\n"):
            m = re.match(r"^#define (\w+)_P\(p\)\s+(\w+)\s*$", ln)
            if m:
                alias[m.group(1)] = m.group(2)
    names = sorted(defs)
    rx = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    for f in files:
        if f.suffix != ".c":
            continue
        cur = None
        for ln in f.read_text(errors="replace").split("\n"):
            if TAB.match(ln) or ln.startswith("extern "):
                continue
            m = FUNC.match(ln)
            if m and not ln.rstrip().endswith(";"):
                cur = m.group(1)
            old = set(rx.findall(ln))
            for n in {alias.get(x, x) for x in re.findall(r"\b(\w+)_P\(", ln)} & set(defs) | old:
                if cur and not DEF.match(ln):
                    uses.setdefault(n, set()).add(cur)
            for n in old & via:
                if cur and not ln.startswith("#define"):
                    bare.setdefault(n, set()).add(f.name + ":" + cur)
    return defs, uses, via, bare


def load():
    rows = {}
    if TSV.exists():
        for ln in TSV.read_text().split("\n")[1:]:
            c = ln.split("\t")
            if len(c) >= 3 and c[0]:
                rows[c[0]] = c
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tree", default=str(ROOT))
    a = ap.parse_args()
    global TREE, TSV
    TREE = Path(a.tree)
    TSV = TREE / "docs/dp-rx-port-state.tsv"
    defs, uses, via, bare = scan()
    rows = load()
    new = sorted(set(defs) - set(rows))
    gone = sorted(set(rows) - set(defs))
    bad = sorted(n for n, c in rows.items() if c[1] not in CLASSES and c[1] != "unclassified")
    if a.write:
        out = ["name\tclass\tfile\tfunctions"]
        for n in sorted(defs):
            cls = rows[n][1] if n in rows else "unclassified"
            out.append(f"{n}\t{cls}\t{defs[n]}\t{' '.join(sorted(uses.get(n, [])))}")
        TSV.write_text("\n".join(out) + "\n")
        say(f"wrote {TSV.name}: {len(defs)} rows, {len(new)} new")
        return 0
    for n in new:
        say(f"FAIL new Rx1 global not in {TSV.name}: {n} ({defs[n]}); classify it, lt-* state goes through the per-port accessors")
    for n in gone:
        say(f"FAIL {TSV.name} row without a definition: {n}")
    for n in bad:
        say(f"FAIL unknown class for {n}: {rows[n][1]}")
    for n, c in sorted(rows.items()):
        if c[1] == "lt-hot" and n in defs and n not in via and not n.startswith("d_g_bDpRx1Tp1"):
            say(f"FAIL lt-hot {n} not declared through DPRX_T1/3/4")
            bad.append(n)
        if c[1] == "lt-hot" and n in bare:
            say(f"FAIL lt-hot {n} used by its bare name in {' '.join(sorted(bare[n]))}; use NAME_P(port)")
            bad.append(n)
    unc = [n for n, c in rows.items() if c[1] == "unclassified"]
    say(f"{len(defs)} Rx1 globals, {len(unc)} unclassified, {len(new)} new, {len(gone)} stale")
    return 1 if (new or gone or bad or unc) else 0


if __name__ == "__main__":
    sys.exit(main())
