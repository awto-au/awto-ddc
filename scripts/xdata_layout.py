#!/usr/bin/env python3
"""Pinned XDATA layout: fw/xdata_layout.tsv = one fixed slot per module (module, hole, offset, slot), like fw/bank_layout.tsv for code.

usage (library): place(old, sizes, holes, reserved, compact=False) -> (rows, info)
       xdata_layout.py check --tree T --map fw.map     the tracked file matches the linked map (gate xlayout)
- Slot kept while the module's XDATA size <= slot and the slot is still free; else the module alone is re-homed (first fit in the gaps).
- Fragmented (free bytes enough, no single gap) -> compaction (every module moves) with a loud log; none fit -> error.
- Explicit compaction: fw_build.py --xdata-compact (full-churn build).
Log: ./tmp/logs/xdata_layout.log
"""
import argparse, re, sys
from pathlib import Path

PREFIX = "XS_"           # area name = XS_<module>; the map prints area names cut to 32 chars
MAPW = 32
HEAD = "# module\thole\toffset\tslot   (scripts/xdata_layout.py; one fixed XDATA slot per module, fw/xdata_layout.tsv)"


def load(p: Path) -> dict:
    rows = {}
    if p.is_file():
        for ln in p.read_text().splitlines():
            f = ln.split("\t")
            if ln and not ln.startswith("#") and len(f) == 4:
                rows[f[0]] = (int(f[1], 0), int(f[2], 0), int(f[3], 0))
    return rows


def dump(rows: dict) -> str:
    return "\n".join([HEAD] + [f"{m}\t0x{h:04x}\t{o}\t{s}" for m, (h, o, s) in sorted(rows.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0]))]) + "\n"


def addr(row) -> int:
    return row[0] + row[1]


def gaps(holes, taken):
    """Free (lo, hi) intervals of every hole after the taken (lo, hi) ranges."""
    out = []
    for a, b in holes:
        cur = a
        for lo, hi in sorted(t for t in taken if t[0] < b and t[1] > a):
            if lo > cur:
                out.append((cur, lo))
            cur = max(cur, hi)
        if cur < b:
            out.append((cur, b))
    return out


def place(old: dict, sizes: dict, holes, reserved, compact: bool = False):
    """-> (rows {mod: (hole, offset, slot)}, info {moved, kept, compacted, free, largest, per_hole}); SystemExit if it does not fit."""
    taken = list(reserved)
    rows, moved = {}, []
    hole_of = {a: b for a, b in holes}
    if not compact:
        for m in sorted(sizes):
            if m not in old:
                continue
            h, o, s = old[m]
            lo, hi = h + o, h + o + s
            if h in hole_of and s >= sizes[m] and hi <= hole_of[h] and not any(lo < t[1] and hi > t[0] for t in taken):
                rows[m] = old[m]
                taken.append((lo, hi))
    todo = sorted((m for m in sizes if m not in rows), key=lambda m: (-sizes[m], m))
    def find(tk, n):
        return next(((lo, hi) for lo, hi in gaps(holes, tk) if hi - lo >= n), None)

    def put(m, g, tk):
        h = next(a for a, b in holes if a <= g[0] < b)
        rows[m] = (h, g[0] - h, sizes[m])
        tk.append((g[0], g[0] + sizes[m]))
        moved.append(m)

    for m in todo:
        g = find(taken, sizes[m])
        if g is None and not compact:                        # evict one kept module (smallest first) so that both fit
            for k in sorted((k for k in rows if k not in moved), key=lambda k: (rows[k][2], k)):
                tk = [t for t in taken if t != (addr(rows[k]), addr(rows[k]) + rows[k][2])]
                g1 = find(tk, sizes[m])
                if g1 and (lambda tk2: find(tk2, sizes[k]))(tk + [(g1[0], g1[0] + sizes[m])]):
                    old_k = rows.pop(k)
                    taken[:] = tk
                    put(m, g1, taken)
                    put(k, find(taken, sizes[k]), taken)
                    log(f"XDATA: {m} ({sizes[m]} B) re-homed, {k} (slot {old_k[2]} B) evicted to make room")
                    break
            else:
                g = None
            if m in rows:
                continue
        if g is None:
            free = sum(hi - lo for lo, hi in gaps(holes, taken))
            if not compact and free >= sizes[m]:
                log(f"XDATA fragmented: {m} needs {sizes[m]} B, {free} B free in no single gap -> compaction (every module moves, full-churn flash)")
                rows, info = place(old, sizes, holes, reserved, compact=True)
                info["compacted"] = True
                return rows, info
            sys.exit(f"XDATA does not fit holes {[(hex(a), hex(b)) for a, b in holes]}: {m} needs {sizes[m]} B, "
                     f"free {free} B in gaps {[hi - lo for lo, hi in gaps(holes, taken)]}")
        put(m, g, taken)
    gp = gaps(holes, taken)
    per = [(a, b - a, sum(hi - lo for lo, hi in gp if a <= lo < b), max([hi - lo for lo, hi in gp if a <= lo < b], default=0)) for a, b in holes]
    return rows, {"moved": moved, "kept": len(rows) - len(moved), "compacted": compact, "free": sum(p[2] for p in per),
                  "largest": max((p[3] for p in per), default=0), "per_hole": per}


def check(layout: Path, mp: str) -> list:
    """Problems between the tracked layout and the linked map (empty = current)."""
    want = load(layout)
    got = {}
    for m in re.finditer(r"^(XS_\S+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =", mp, re.M):
        if int(m.group(3), 16):
            got.setdefault(m.group(1), (int(m.group(2), 16), int(m.group(3), 16)))
    bad = []
    wn = {(PREFIX + k)[:MAPW]: k for k in want}
    if len(wn) != len(want):
        bad.append("module names collide in the map's 32-char area names")
    for n, (a, s) in sorted(got.items()):
        k = wn.get(n)
        if k is None:
            bad.append(f"{n} in the map, not in the layout")
        elif addr(want[k]) != a or s > want[k][2]:
            bad.append(f"{k}: map 0x{a:04x}+{s}, layout 0x{addr(want[k]):04x}+{want[k][2]}")
    bad += [f"{k} in the layout, not in the map" for n, k in sorted(wn.items()) if n not in got]
    return bad


def log(s):
    import isostamp
    line = f"{isostamp.now()} {s}"
    print(line)
    p = Path(__file__).resolve().parents[1] / "tmp/logs/xdata_layout.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--tree", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--map", required=True)
    a = ap.parse_args()
    bad = check(Path(a.tree) / "fw/xdata_layout.tsv", Path(a.map).read_text(errors="replace"))
    for b in bad[:20]:
        log(f"xlayout FAIL: {b}")
    log(f"xlayout: {'FAIL, ' + str(len(bad)) + ' problems' if bad else 'PASS, layout matches the map'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
