#!/usr/bin/env python3
"""Why does a rebuild rewrite so many flash sectors? Offline compare of two built images (+ their linker maps).

usage: scripts/image_sector_diff.py OLD.bin NEW.bin [--old-map M] [--new-map M] [--grid] [--moves N] [--json]
(maps default to the .bin name with .map; images are tmp/fw/<serial>-<tag>-be.bin from ./dev.py build)
- Per 4 KiB sector (the flasher's erase/program unit): same / changed, bank grid (14-15 banks x 16 sectors, common = first
  --common-sectors of each bank).
- Each changed sector is classified from its differing bytes:
  - stamp : build-tag string (found by the tag in the file name)
  - X     : only `MOV DPTR,#imm16` (0x90) operands differ, old and new word inside the XDATA symbol range (variable moved)
  - C     : only LJMP/LCALL (0x02/0x12) operands differ, old/new word = the same code symbol before/after (code moved)
  - x     : single bytes whose change = low/high byte of a data/code symbol delta (address immediates, heuristic)
  - R     : bytes that are neither (real content / code change)
  - mixed X+C+R combinations are shown as the letters
- `floor_pin` = same, but XDATA keeps one fixed slot per module (a symbol only moves if its offset inside its module run changed)
- `floor` = sectors still changed after masking X, C and x = what a frozen XDATA + code layout would still rewrite.
- Map symbols: which code / data symbols moved and by how much; the first moved data symbol (origin of an XDATA shift).
- Free flash: all-0xFF sectors and 0xFF bytes per bank.
Log: ./tmp/logs/image_sector_diff.log
"""
import argparse
import bisect
import collections
import json
import re
import sys
from pathlib import Path

import chip_mem as CM

SECTOR = 4096
BANK = 65536


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_map(p: Path):
    """-> (code {name: addr}, data {name: addr}); area bases (s_/l_) kept only for s_CH_/s_ST_ as code."""
    code, data = {}, {}
    pat = re.compile(r"^([CD]):\s+([0-9A-Fa-f]{8})\s+(\S+)(?:\s+(\S+))?")
    mods = {}
    for ln in p.read_text(errors="replace").splitlines():
        m = pat.match(ln)
        if not m:
            continue
        kind, addr, name = m.group(1), int(m.group(2), 16), m.group(3)
        if name.startswith("l_") or (name.startswith("s_") and not name.startswith(("s_CH_", "s_ST_"))):
            continue
        (code if kind == "C" else data).setdefault(name, addr)
        if kind == "D":
            mods[name] = m.group(4) or "?"
    return code, data, mods


def sectors(b: bytes):
    return [b[i:i + SECTOR] for i in range(0, len(b), SECTOR)]


def classify(a: bytes, b: bytes, xlo: int, xhi: int, code_move: dict, bytedeltas: frozenset = frozenset(),
             pin_sym=lambda w: False, pin_deltas: frozenset = frozenset(), pin_bytes: frozenset = frozenset()):
    """-> (letters, masked_equal) for one sector pair. code_move: {old_addr: new_addr} of code symbols."""
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if not diff:
        return "", True, True
    explained = set()
    pinned_real = False
    letters = set()
    for p in range(len(a) - 2):
        op = a[p]
        if op != b[p] or op not in (0x90, 0x02, 0x12):
            continue
        if not (a[p + 1] != b[p + 1] or a[p + 2] != b[p + 2]):
            continue
        ow, nw = a[p + 1] << 8 | a[p + 2], b[p + 1] << 8 | b[p + 2]
        if op == 0x90 and xlo <= ow <= xhi and xlo <= nw <= xhi:
            letters.add("X")
            pinned_real |= pin_sym(ow)
        elif op in (0x02, 0x12) and code_move.get(ow) == nw:
            letters.add("C")
        else:
            continue
        explained.update((p + 1, p + 2))
    rest = [i for i in diff if i not in explained]
    # x: lone byte whose change equals the low / high byte of a symbol move (ADD A,#lo(addr), MOV Rn,#hi(addr), ...)
    lone = [i for i in rest if (b[i] - a[i]) & 0xFF in bytedeltas]
    if lone:
        letters.add("x")
        pinned_real |= any((b[i] - a[i]) & 0xFF in pin_deltas and a[i] in pin_bytes for i in lone)
        rest = [i for i in rest if i not in set(lone)]
    if rest:
        letters.add("R")
    return "".join(sorted(letters)), not rest, not rest and not pinned_real


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--old-map", type=Path)
    ap.add_argument("--new-map", type=Path)
    ap.add_argument("--common-sectors", type=int, default=-(-CM.COMMON_END // 4096), help="common area per bank in sectors (fw/rl6449_memory.toml common_end)")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--moves", type=int, default=6, help="moved symbols to list")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ob, nb = a.old.read_bytes(), a.new.read_bytes()
    log = (repo_root() / "tmp/logs/image_sector_diff.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    out = []

    def say(s=""):
        out.append(s)

    om = a.old_map or a.old.with_suffix(".map")
    nm = a.new_map or a.new.with_suffix(".map")
    ocode, odata, omods = parse_map(om) if om.exists() else ({}, {}, {})
    ncode, ndata, nmods = parse_map(nm) if nm.exists() else ({}, {}, {})
    dvals = sorted(set(odata.values()) | set(ndata.values()))
    xlo, xhi = (dvals[0], dvals[-1] + 0x100) if dvals else (0x8000, 0xFFFF)
    code_move = {ocode[k]: ncode[k] for k in ocode if k in ncode and ocode[k] != ncode[k]}
    deltas = set()
    for k in odata:
        if k in ndata and ndata[k] != odata[k]:
            d = ndata[k] - odata[k]
            deltas |= {d & 0xFF, (d >> 8) & 0xFF, ((d >> 8) + 1) & 0xFF}
    for o_, n_ in code_move.items():
        d = n_ - o_
        deltas |= {d & 0xFF, (d >> 8) & 0xFF, ((d >> 8) + 1) & 0xFF}
    deltas.discard(0)
    # pinned-XDATA simulation: each module keeps its old base; a symbol only moves if its offset inside the module changed
    def clusters(data, mods):
        """symbol -> (module#run, offset in the run): a run = consecutive symbols (address order) of one module"""
        res, cur, seen, base = {}, None, collections.Counter(), 0
        for v, k in sorted((v, k) for k, v in data.items()):
            if cur is None or mods[k] != cur[0]:
                seen[mods[k]] += 1
                cur, base = (mods[k], seen[mods[k]]), v
            res[k] = (cur, v - base)
        return res

    co, cn = clusters(odata, omods), clusters(ndata, nmods)
    intra = {k: cn[k][1] - co[k][1] for k in odata if k in ndata and co[k][0] == cn[k][0]}
    changed_syms = {k for k, d in intra.items() if d}
    gone_syms = set(odata) ^ set(ndata)
    pin_deltas = set()
    for k in changed_syms:
        d = intra[k]
        pin_deltas |= {d & 0xFF, (d >> 8) & 0xFF, ((d >> 8) + 1) & 0xFF}
    pin_deltas.discard(0)
    osyms = sorted((v, k) for k, v in odata.items())
    oaddrs = [v for v, _ in osyms]
    pin_words = set()          # old addresses of symbols that really move even when modules are pinned
    for k in changed_syms | (gone_syms & set(odata)):
        pin_words.add(odata[k])
    pin_bytes = {x for w in pin_words for o in range(8) for x in (((w + o) & 0xFF), ((w + o) >> 8) & 0xFF)}

    def pin_sym(w):
        j = bisect.bisect_right(oaddrs, w) - 1
        return j >= 0 and oaddrs[j] in pin_words and w - oaddrs[j] < 64

    n = min(len(ob), len(nb))
    os_, ns_ = sectors(ob[:n]), sectors(nb[:n])
    tag = re.sub(r"^AWT\d+-|-be\.bin$", "", a.new.name)
    stamp_secs = {m.start() // SECTOR for m in re.finditer(re.escape(tag.encode()), nb)} if tag else set()
    chg, kinds, per_bank = [], {}, collections.Counter()
    grid = [[" "] * 16 for _ in range(n // BANK)] if n % BANK == 0 else None
    floor = floor_pin = 0
    for i, (x, y) in enumerate(zip(os_, ns_)):
        if x == y:
            if grid:
                grid[i // 16][i % 16] = "."
            continue
        letters, masked_equal, pinned_equal = classify(x, y, xlo, xhi, code_move, frozenset(deltas), pin_sym, frozenset(pin_deltas), frozenset(pin_bytes))
        if i in stamp_secs and set(letters) <= {"R"}:
            letters = "stamp+" + letters if letters else "stamp"
        chg.append(i)
        kinds[i] = letters
        per_bank[i // 16] += 1
        if not masked_equal:
            floor += 1
        if not pinned_equal:
            floor_pin += 1
        if grid:
            grid[i // 16][i % 16] = ("R" if "R" in letters else letters[0]) if letters else "?"
    comm = sum(1 for i in chg if i % 16 < a.common_sectors)
    say(f"old {a.old.name}  new {a.new.name}  sectors {n // SECTOR}  (bank = {BANK // 1024} KiB, common = first {a.common_sectors} sectors)")
    say(f"changed {len(chg)} / {n // SECTOR}: common {comm}, banked {len(chg) - comm}")
    cnt = collections.Counter(kinds.values())
    for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]):
        say(f"  class {k or '-':<8} {v}")
    say(f"floor (changed after masking X, C, x): {floor}   [XDATA fully frozen]")
    say(f"floor_pin (module-pinned XDATA: only symbols whose offset inside their module changed still move): {floor_pin}"
        f"   [{len(changed_syms)} such symbols, {len(gone_syms)} added/removed]")
    if grid and a.grid:
        say("grid (rows = banks, cols = sectors; .=same, letter=class initial)")
        for r, row in enumerate(grid):
            say(f"  {r:2d} {''.join(row)}")
    # symbol moves
    if ocode and ncode:
        cm = {k: ncode[k] - ocode[k] for k in ocode if k in ncode and ncode[k] != ocode[k]}
        dm = {k: ndata[k] - odata[k] for k in odata if k in ndata and ndata[k] != odata[k]}
        say(f"code symbols: {len(ocode)} old / {len(ncode)} new, moved {len(cm)}; data symbols: {len(odata)} / {len(ndata)}, moved {len(dm)}")
        if dm:
            first = sorted(dm, key=lambda k: odata[k])[:a.moves]
            say("  first moved data symbols (old addr, delta): " + "; ".join(f"{k} {odata[k]:#06x} {dm[k]:+d}" for k in first))
            say("  data delta histogram: " + ", ".join(f"{d:+d}x{c}" for d, c in collections.Counter(dm.values()).most_common(5)))
        seq, prev = [], 0
        for k in sorted((k for k in odata if k in ndata), key=lambda k: (odata[k], k)):
            d = ndata[k] - odata[k]
            if d != prev:
                seq.append(f"{odata[k]:#06x} {prev:+d}->{d:+d} at {k}")
                prev = d
        if len(seq) > 1:
            say(f"  XDATA delta changes along the address order ({len(seq)}; each = a variable that grew/shrank/appeared before it): "
                + "; ".join(seq[:a.moves]))
        if cm:
            first = sorted(cm, key=lambda k: ocode[k])[:a.moves]
            say("  first moved code symbols: " + "; ".join(f"{k} {ocode[k]:#07x} {cm[k]:+d}" for k in first))
        added = sorted(set(ncode) - set(ocode))[:5], sorted(set(ndata) - set(odata))[:5]
        gone = sorted(set(ocode) - set(ncode))[:5], sorted(set(odata) - set(ndata))[:5]
        say(f"  added code/data: {added}; removed: {gone}")
    # free flash
    free_secs = sum(1 for s in ns_ if s.count(0xFF) == SECTOR)
    fb = [sum(s.count(0xFF) for s in ns_[b * 16:(b + 1) * 16]) for b in range(len(ns_) // 16)]
    say(f"free flash in new image: {free_secs} blank sectors; 0xFF bytes per bank KiB: {[x // 1024 for x in fb]} (sum {sum(fb) // 1024} KiB of {n // 1024})")
    if a.json:
        print(json.dumps({"changed": len(chg), "common": comm, "floor": floor, "classes": dict(cnt),
                          "free_sectors": free_secs}))
    txt = "\n".join(out)
    print(txt)
    with log.open("a") as fh:
        fh.write(txt + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
