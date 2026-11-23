#!/usr/bin/env python3
"""Flash layout for the banked SDCC build (awto-ddc#12, #44): tracked bank map + compact packing every build.

- `fw/bank_map.tsv` (tracked): `kind name region` per fn / const = the bank decision, kept so an edit does not reshuffle banks.
- build output `tmp/sdcc-port/bank_layout.new.tsv` (frozen as `tmp/fw/<stem>.bank_layout.tsv`): `kind name region offset size`,
  every region packed back to back in the order fixed / consts / module / name; no padding, no holes, no stored offsets.
- region: C = common, address = offset; <n> = bank n, address = n*0x10000 + COMMON + offset
Used by sdcc_bank.py (--layout = the map); fw_build.py pins every chunk with `-a<area>=<addr>` (one area per chunk).
"""
from collections import defaultdict
from pathlib import Path

import chip_mem as CM

BANK_SIZE = CM.BANK_SIZE


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
            if len(f) == 3:                 # tracked bank map: kind name region (offsets are build output)
                f += ["0", "0"]
            if len(f) != 5:
                continue
            kind, name, reg, off, slot = f
            reg = reg if reg == "C" else int(reg)
            if kind == "area":
                lay.areas[name] = (int(off, 0), int(slot, 0))
            else:
                lay.rows[(kind, name)] = (reg, int(off, 0), int(slot, 0))
        return lay

    def check_header(self, common, resid_end, path="layout"):
        """SystemExit if the file's recorded common / resid_end differ from this build's (every slot offset would shift)."""
        for key, want in (("common", common), ("resid_end", resid_end)):
            have = self.header.get(key)
            if key == "resid_end" and have is not None and want < int(have, 0):
                continue                        # a lower resid_end only frees common below the first row: no slot moves (#44)
            if have is not None and int(have, 0) != want:
                raise SystemExit(f"layout: {path} was made with {key}={have}, this build has {key}={hex(want)}; "
                                 f"refusing (slots would shift). Rebuild with the matching args or delete the layout.")

    def text(self):
        out = [f"#{k} {v}" for k, v in sorted(self.header.items())]
        out.append("# kind\tname\tregion\toffset\tslot    (scripts/sdcc_layout.py; region C = common)")
        for n, (off, res) in sorted(self.areas.items(), key=lambda kv: kv[1][0]):
            out.append(f"area\t{n}\tC\t0x{off:04x}\t0x{res:x}")
        rk = lambda kv: (-1 if kv[1][0] == "C" else kv[1][0], kv[1][1])
        for (kind, name), (reg, off, slot) in sorted(self.rows.items(), key=rk):
            out.append(f"{kind}\t{name}\t{reg}\t0x{off:04x}\t{slot}")
        return "\n".join(out) + "\n"

    def map_text(self):
        """The tracked part: which region each fn / const lives in (offsets are recomputed every build)."""
        out = [f"#{k} {v}" for k, v in sorted(self.header.items())]
        out.append("# kind\tname\tregion    (bank map: scripts/sdcc_layout.py; region C = common, n = bank n)")
        out += [f"{k}\t{n}\t{r[0]}" for (k, n), r in sorted(self.rows.items(), key=lambda kv: (kv[0][0], kv[0][1])) if k != "stub"]
        return "\n".join(out) + "\n"

    def save(self, path):
        p = Path(path)
        t = self.text()
        if not p.exists() or p.read_text() != t:
            p.write_text(t)


class Item:
    def __init__(self, kind, name, size, region, module, slot=None):
        self.key, self.size, self.region, self.module = (kind, name), size, region, module
        self.slot = slot if slot is not None else size
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


def assign(items, layout, common_lo, common_hi, nbanks, bank_cap, log=print, reserve=None, labels=None):
    """Pack every item back to back; returns (placed: key -> (region, offset, size), moved: key -> new region).
    items: list[Item] with .region = wanted region (C or bank); `layout` (the tracked bank map) tells which chunks are known.
    Order: fixed items first (consts, residual-bound), then consts, module, name. No padding, no holes.
    A non-fixed fn whose region is full goes to the bank with most room; a new chunk to the bank holding most of its module;
    a fixed const whose bank is full falls back to common (reachable from every bank).
    reserve: {bank: bytes} kept free at the top of that bank (fixed data block, scripts/msg_table.py).
    labels: {key: why it is fixed} (#pragma place rules), named when a fixed item finds no room."""
    regs = {"C": Region("C", common_lo, common_hi)}
    for b in range(nbanks):
        regs[b] = Region(b, 0, bank_cap - (reserve or {}).get(b, 0))
    by_key = {it.key: it for it in items}
    moved = {}
    for it in sorted(items, key=lambda it: (not it.fixed, it.is_const is False, it.module, it.key[1])):
        if it.region == "C" or it.fixed:
            cands = [it.region] + (["C"] if it.is_const and it.region != "C" else [])
        elif it.key not in layout.rows:      # new chunk: bank holding most of its module's code first
            mb = {rid: sum(by_key[k].size for k in r.placed if k in by_key and by_key[k].module == it.module)
                  for rid, r in regs.items() if rid != "C"}
            home = sorted((b for b in mb if mb[b]), key=lambda b: (-mb[b], b))
            cands = home + sorted((b for b in regs if b != "C" and b not in home), key=lambda b: -regs[b].free())
        else:
            cands = [it.region] + sorted((b for b in regs if b not in ("C", it.region)), key=lambda b: -regs[b].free())
        done = next((rid for rid in cands if regs[rid].place(it.key, it.slot) is not None), None)
        if done is None:
            why = (labels or {}).get(it.key)
            raise SystemExit(f"{why + ': ' if why else 'layout: '}no room for {it.key[1]} ({it.slot} B) in "
                             f"{'common' if it.region == 'C' else 'bank %s' % it.region}: {regs[it.region].free()} B free; "
                             f"free per region { {k: v.free() for k, v in regs.items()} }")
        if done != it.region:
            moved[it.key] = done
    placed = {k: (rid, o, s) for rid, r in regs.items() for k, (o, s) in r.placed.items()}
    log(f"layout: {len(items)} chunks packed, {len(moved)} moved to another region")
    return placed, moved


def stats(placed, nbanks, common_lo, common_hi, bank_cap, reserve=None):
    used = defaultdict(int)
    for rid, o, s in placed.values():
        used[rid] += s
    out = {"C": (used["C"], common_hi - common_lo)}
    for b in range(nbanks):
        out[b] = (used[b], bank_cap - (reserve or {}).get(b, 0))
    return out
