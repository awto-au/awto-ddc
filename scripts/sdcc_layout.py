#!/usr/bin/env python3
"""Sticky flash layout for the banked SDCC build (awto-ddc#12): fixed per-chunk slots, reused between builds.

Layout file (fw/bank_layout.tsv): `kind name region offset slot`
- kind: fn | const | stub (one slot each), area (pinned residual area: name region offset reserve)
- region: C = common, address = offset; <n> = bank n, address = n*0x10000 + COMMON + offset
- A chunk keeps (region, offset) while its size fits the slot; a grown chunk first extends into free space
  after its slot, else moves to a hole (own bank first, other banks by free space); a fragmented bank is
  compacted, only that bank. Order within a bank at creation: consts first, then by module, then name.
Used by sdcc_bank.py (--layout); fw_build.py pins every slot with `-a<area>=<addr>` (one area per chunk).
"""
from collections import defaultdict
from pathlib import Path

BANK_SIZE = 0x10000


def pad_slot(size, div=32, minpad=4):
    """Slot size = size + minpad + size/div, rounded up to 4 B (room for a typical small edit)."""
    return (size + minpad + size // div + 3) & ~3


class Layout:
    def __init__(self):
        self.rows = {}                      # (kind, name) -> (region, offset, slot); region 'C' or int
        self.areas = {}                     # residual area name -> (offset, reserve), region C
        self.header = {}                    # key -> value string (common, resid_end, ...)

    @classmethod
    def load(cls, path):
        lay = cls()
        p = Path(path)
        if not p.exists():
            return lay
        for ln in p.read_text().splitlines():
            if ln.startswith("#"):
                f = ln[1:].split()
                if len(f) >= 2 and not ln.startswith("# "):
                    lay.header[f[0]] = f[1]
                continue
            f = ln.split("\t")
            if len(f) != 5:
                continue
            kind, name, reg, off, slot = f
            reg = reg if reg == "C" else int(reg)
            if kind == "area":
                lay.areas[name] = (int(off, 0), int(slot, 0))
            else:
                lay.rows[(kind, name)] = (reg, int(off, 0), int(slot, 0))
        return lay

    def text(self):
        out = [f"#{k} {v}" for k, v in sorted(self.header.items())]
        out.append("# kind\tname\tregion\toffset\tslot    (scripts/sdcc_layout.py; region C = common)")
        for n, (off, res) in sorted(self.areas.items(), key=lambda kv: kv[1][0]):
            out.append(f"area\t{n}\tC\t0x{off:04x}\t0x{res:x}")
        rk = lambda kv: (-1 if kv[1][0] == "C" else kv[1][0], kv[1][1])
        for (kind, name), (reg, off, slot) in sorted(self.rows.items(), key=rk):
            out.append(f"{kind}\t{name}\t{reg}\t0x{off:04x}\t{slot}")
        return "\n".join(out) + "\n"

    def save(self, path):
        p = Path(path)
        t = self.text()
        if not p.exists() or p.read_text() != t:
            p.write_text(t)


class Item:
    def __init__(self, kind, name, size, region, module, slot=None):
        self.key, self.size, self.region, self.module = (kind, name), size, region, module
        self.slot = slot if slot is not None else pad_slot(size)
        self.is_const = kind == "const"
        self.fixed = False                  # never re-homed to another region


class Region:
    def __init__(self, rid, lo, hi):
        self.rid, self.lo, self.hi = rid, lo, hi
        self.placed = {}                    # key -> (offset, slot)

    def spans(self):
        return sorted((o, o + s) for o, s in self.placed.values())

    def holes(self):
        cur, out = self.lo, []
        for a, b in self.spans():
            if a > cur:
                out.append((cur, a - cur))
            cur = max(cur, b)
        if cur < self.hi:
            out.append((cur, self.hi - cur))
        return out

    def free(self):
        return sum(n for _, n in self.holes())

    def place(self, key, slot):
        """Best-fit hole (smallest that fits, lowest offset on ties); returns offset or None."""
        best = None
        for o, n in self.holes():
            if n >= slot and (best is None or n < best[1]):
                best = (o, n)
        if best is None:
            return None
        self.placed[key] = (best[0], slot)
        return best[0]

    def compact(self, order):
        """Re-pack every slot of this region back to back, in `order` (keys)."""
        cur = self.lo
        for k in sorted(self.placed, key=order):
            self.placed[k] = (cur, self.placed[k][1])
            cur += self.placed[k][1]


def assign(items, layout, common_lo, common_hi, nbanks, bank_cap, log=print, fill_target=0.80):
    """Place every item; returns (placed: key -> (region, offset, slot), moved: key -> new region).
    items: list[Item] with .region = wanted region (C or bank). A kept row needs the same region."""
    regs = {"C": Region("C", common_lo, common_hi)}
    for b in range(nbanks):
        regs[b] = Region(b, 0, bank_cap)
    order = lambda it: (it.is_const is False, it.module, it.key[1])
    by_key = {it.key: it for it in items}
    korder = lambda k: (by_key[k].is_const is False, by_key[k].module, k[1])
    pending, grow, kept = [], [], 0
    for it in sorted(items, key=order):
        row = layout.rows.get(it.key)
        if (row and row[0] == it.region and regs[it.region].lo <= row[1] and row[1] + row[2] <= regs[it.region].hi
                and all(not (a < row[1] + row[2] and b > row[1]) for a, b in regs[it.region].spans())):
            regs[it.region].placed[it.key] = (row[1], row[2])
            if it.size > row[2]:
                grow.append(it)
            kept += 1
        else:
            pending.append(it)
    extended = 0
    for it in grow:                         # grown chunk: extend in place if the bytes after the slot are free
        r = regs[it.region]
        off, slot = r.placed[it.key]
        del r.placed[it.key]
        want = it.slot
        if all(not (a < off + want and b > off) for a, b in r.spans()) and off + want <= r.hi:
            r.placed[it.key] = (off, want)
            extended += 1
        else:
            pending.append(it)
    moved, repacked = {}, set()
    if pending:
        pending.sort(key=lambda it: (not it.fixed,) + order(it))
    for it in pending:
        cands = [it.region] if (it.region == "C" or it.fixed) else [it.region] + sorted(
            (b for b in regs if b not in ("C", it.region)), key=lambda b: -regs[b].free())
        done = None
        for rid in cands:
            r = regs[rid]
            if rid != it.region and rid != "C" and r.free() - it.slot < (1 - fill_target) * bank_cap * 0.25:
                continue                    # foreign bank: keep some slack there too
            off = r.place(it.key, it.slot)
            if off is None and r.free() >= it.slot and rid not in repacked:
                r.compact(korder)
                repacked.add(rid)
                log(f"layout: compacted region {rid} (fragmented) for {it.key[1]} ({it.slot} B)")
                off = r.place(it.key, it.slot)
            if off is not None:
                done = rid
                break
        if done is None:
            raise SystemExit(f"layout: no room for {it.key} ({it.slot} B) in any region; free: "
                             f"{ {k: v.free() for k, v in regs.items()} }")
        if done != it.region:
            moved[it.key] = done
    placed = {}
    for rid, r in regs.items():
        for k, (o, s) in r.placed.items():
            placed[k] = (rid, o, s)
    log(f"layout: {len(items)} slots: kept {kept - len(grow)}, extended {extended}, "
        f"new/moved {len(pending)} (re-homed to another bank: {len(moved)}); compacted: {sorted(map(str, repacked))}")
    return placed, moved


def stats(placed, nbanks, common_lo, common_hi, bank_cap):
    used = defaultdict(int)
    for k, (rid, o, s) in placed.items():
        used[rid] += s
    out = {"C": (used["C"], common_hi - common_lo)}
    for b in range(nbanks):
        out[b] = (used[b], bank_cap)
    return out
