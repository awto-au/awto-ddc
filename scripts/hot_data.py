#!/usr/bin/env python3
"""Rank small XSEG / XISEG objects by `mov dptr,#sym` loads: candidates for `__data` (awto-ddc#335).

usage: hot_data.py [--asm DIR] [--max-size 8] [--budgets 16,22,48] [--top 40] [--params]
- Source: the final banked asm (tmp/sdcc-port/asm_bank); size from `.ds`, accesses = `mov dptr,#(sym[+off])` in all modules.
- Gain model: 2 B per access (3 B `mov dptr` + 1 B movx -> 2 B direct); an upper bound, dptr reuse lowers it.
- `addr` = the symbol is also used as an address (not only `mov dptr` + movx): cannot move without a pointer check.
- --params: rank `<func>_PARM_n` overflow parameters per callee instead (#336).
Log: tmp/logs/hot_data.log
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import Logger
from sdcc_overlay import repo_root

ROOT = repo_root()
AREA = re.compile(r"^\s+\.area\s+(\w+)")
LABEL = re.compile(r"^(_\w+)::?")
DS = re.compile(r"^\s*\.ds\s+(\w+)")
DPTR = re.compile(r"^\s+mov\s+dptr,#\(?(_\w+)(?:\s*\+\s*(0x[0-9a-fA-F]+|\d+))?\)?\s*$")
REF = re.compile(r"(?<![\w])(_\w+)(?![\w])")
GAIN = 2                                                  # bytes per access: 3 B mov dptr + 1 B movx -> 2 B mov direct
LOG = None


def scan(asm_dir: Path):
    size, area_of, loads, other = {}, {}, defaultdict(int), defaultdict(int)
    files = sorted(asm_dir.glob("*.asm"))
    for p in files:
        area, lab = None, None
        for l in p.read_text(errors="replace").split("\n"):
            m = AREA.match(l)
            if m:
                area, lab = m.group(1), None
                continue
            m = LABEL.match(l)
            if m and area in ("XSEG", "XISEG"):
                lab = m.group(1)
                area_of[lab] = area
                size.setdefault(lab, 0)
                continue
            m = DS.match(l)
            if m and lab and area in ("XSEG", "XISEG"):
                size[lab] += int(m.group(1), 0)
    for p in files:
        lines = [x.split(";")[0].rstrip() for x in p.read_text(errors="replace").split("\n")]
        for i, l in enumerate(lines):
            if not l or l.startswith("\t.") or LABEL.match(l):
                continue
            m = DPTR.match(l)
            if m:
                loads[m.group(1)] += 1
                nxt = [x.strip() for x in lines[i + 1 : i + 7] if x.strip()]
                for x in nxt:
                    if x.startswith("movx"):
                        break
                    if x.startswith(("lcall", "ljmp", "ret", "sjmp", "acall")) or x.endswith(":"):
                        other[m.group(1)] += 1
                        break
                else:
                    other[m.group(1)] += 1
                continue
            for s in REF.findall(l):
                if s in size:
                    other[s] += 1
    return size, area_of, loads, other


def params(loads):
    rows = defaultdict(lambda: [0, 0])
    for s, n in loads.items():
        m = re.match(r"^_(\w+)_PARM_(\d+)$", s)
        if m:
            rows[m.group(1)][0] += n
            rows[m.group(1)][1] += 1
    return sorted(((n, k, f) for f, (n, k) in rows.items()), reverse=True)


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_bank"))
    ap.add_argument("--max-size", type=int, default=8)
    ap.add_argument("--budgets", default="16,22,48")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--params", action="store_true")
    a = ap.parse_args()
    LOG = Logger(ROOT / "tmp/logs/hot_data.log")
    size, area_of, loads, other = scan(Path(a.asm))
    if a.params:
        rows = params(loads)
        tot = sum(r[0] for r in rows)
        LOG.say(f"_PARM_n: {len(rows)} callees, {tot} loads")
        for n, k, f in rows[: a.top]:
            LOG.say(f"{n:5d} loads  {k} parms  {f}")
        return 0
    cand = []
    for s, sz in size.items():
        if 0 < sz <= a.max_size and not re.search(r"_PARM_\d+$|_sloc\d+", s):
            n = loads.get(s, 0)
            cand.append((n * GAIN / sz, n, sz, s, other.get(s, 0) > 0))
    cand.sort(reverse=True)
    LOG.say(f"{len(cand)} objects <= {a.max_size} B; ranked by gain per byte (gain = {GAIN} B x loads)")
    for g, n, sz, s, ad in cand[: a.top]:
        LOG.say(f"{g:6.1f} B/B  {n:4d} loads  {sz:2d} B  {area_of[s]:5s} {s}{'  addr' if ad else ''}")
    for b in (int(x) for x in a.budgets.split(",")):
        used, gain, k = 0, 0, 0
        for g, n, sz, s, ad in cand:
            if used + sz <= b and not ad:
                used, gain, k = used + sz, gain + n * GAIN, k + 1
        LOG.say(f"budget {b:3d} B: {k} objects, {used} B, est. {gain} B flash (no addr-taken)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
