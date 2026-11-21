#!/usr/bin/env python3
"""Linked-object names for sdcc_san: XDATA / IRAM / bit objects of one build, from its .map and (optional) the linked listings.

- map: globals (`D:` rows, placed ABS rows), area table (BSEG_BYTES, BIT_BANK, DSEG, DDOVLn, per-module XS_*).
- listings (`tmp/sdcc-port/asm_bank/*.rst`, set AWTO_SIM_SAN_RST): every data label with its linked address and `.ds` size, statics included.
  Used only if every global label in them has the map's address (the listings of another build are ignored).
- Marks: mark list rows (symbol, module, space) resolved to address ranges of this build.
Log: tmp/logs/sdcc_san.log
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path

XD = (0xD000, 0xF800)
SPACE_OF_AREA = {"XSEG": "xdata", "XISEG": "xdata", "DSEG": "data", "ISEG": "idata", "BSEG": "bit", "PSEG": "pdata"}
LABEL = re.compile(r"^\s+([0-9A-F]{6})\s+\d+ (_\w+)(::?)\s*$")
DS = re.compile(r"^\s+[0-9A-F]{6}\s+\d+\s+\.ds\s+(\d+)")
AREA = re.compile(r"\.area\s+(\w+)")


class Placed:
    def __init__(self, map_text: str, rst_dir: Path | None = None):
        self.objs = {"xdata": [], "iram": [], "bit": []}      # (addr, size, name, module); iram = data + idata
        self.areas = {"xdata": [], "iram": []}                # (addr, size, area name)
        self.by_name: dict[tuple[str, str], tuple[str, int, int]] = {}     # (symbol, module) -> (space, addr, size)
        self.source = "map"
        self._map(map_text)
        if rst_dir and Path(rst_dir).is_dir():
            self._rst(Path(rst_dir), map_text)
        for k in self.objs:
            self.objs[k].sort()
        self._keys = {k: [o[0] for o in v] for k, v in self.objs.items()}
        for k in self.areas:
            self.areas[k].sort()
        self._akeys = {k: [o[0] for o in v] for k, v in self.areas.items()}

    def _map(self, t: str):
        rows = {(int(m.group(1), 16), m.group(2)) for m in re.finditer(r"^D:\s+([0-9A-F]{8})\s+(\w+)", t, re.MULTILINE)}
        rows |= {(int(m.group(1), 16), m.group(2)) for m in re.finditer(r"^ +([0-9A-F]{8})  (\w+) +\S+$", t, re.MULTILINE)}
        xall = sorted(r[0] for r in rows if r[0] >= XD[0])
        self._xall = xall
        for a, n in sorted(rows):
            if XD[0] <= a < XD[1]:
                self.objs["xdata"].append((a, 0, n, "-"))
                self.by_name[(n, "-")] = ("xdata", a, 0)
            elif 0x08 <= a < 0x80:
                self.objs["iram"].append((a, 0, n, "-"))
                self.by_name[(n, "-")] = ("data", a, 0)
        for m in re.finditer(r"^(\w+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =", t, re.MULTILINE):
            n, a, s = m.group(1), int(m.group(2), 16), int(m.group(3), 16)
            if s and XD[0] <= a < XD[1] and n.startswith("X"):
                self.areas["xdata"].append((a, s, n))
            elif s and a < 0x100 and re.match(r"(DSEG|ISEG|BSEG_BYTES|BIT_BANK|DDOVL\w*|SSEG|REG_BANK_\d)$", n):
                self.areas["iram"].append((a, s, n))
        # sizes of map-only objects: up to the next object (any XDATA row, registers included), inside the IRAM area
        for k in ("xdata", "iram"):
            o = self.objs[k]
            for i, (a, _, n, md) in enumerate(o):
                if k == "xdata":
                    j = bisect.bisect_right(xall, a)
                    nxt = xall[j] if j < len(xall) else a + 1
                else:
                    nxt = o[i + 1][0] if i + 1 < len(o) else a + 1
                    for s0, sz, an in self.areas["iram"]:
                        if s0 <= a < s0 + sz:
                            nxt = min(nxt, s0 + sz)
                o[i] = (a, max(1, nxt - a), n, md)

    def _rst(self, d: Path, map_text: str):
        glob_map = {n: a for (n, md), (sp, a, _) in self.by_name.items() if md == "-"}
        found: dict[str, list] = {"xdata": [], "iram": [], "bit": []}
        bad = ok = 0
        for p in sorted(d.glob("*.rst")):
            area, lab = None, None
            for ln in p.read_text(errors="replace").splitlines():
                m = AREA.search(ln)
                if m:
                    area, lab = m.group(1), None
                    continue
                sp = SPACE_OF_AREA.get(area or "")
                if not sp:
                    continue
                m = LABEL.match(ln)
                if m:
                    lab = (int(m.group(1), 16), m.group(2), m.group(3) == "::")
                    continue
                m = DS.match(ln)
                if m and lab:
                    a, n, g = lab
                    lab = None
                    if g and n in glob_map:
                        if glob_map[n] == a:
                            ok += 1
                        else:
                            bad += 1
                    found["xdata" if sp == "xdata" else "bit" if sp == "bit" else "iram"].append((a, int(m.group(1)), n, "-" if g else p.stem, sp))
        if not ok or bad > max(2, (ok + bad) // 50):       # a few map names are cut at 32 chars and clash
            self.source = f"map (listings do not match: {bad} of {ok + bad} globals differ)"
            return
        self.source = f"map + listings ({ok} globals match)"
        for k, rows in found.items():
            have = {(r[2], r[3]) for r in self.objs[k]}
            for a, s, n, md, sp in rows:
                if k == "xdata" and not XD[0] <= a < XD[1]:
                    continue
                if k == "iram" and a >= 0x100:
                    continue
                if (n, md) in have and md == "-":
                    self.objs[k] = [o for o in self.objs[k] if not (o[2] == n and o[3] == "-")]
                self.objs[k].append((a, s, n, md))
                self.by_name[(n, md)] = (sp, a, s)

    def find(self, space: str, a: int) -> tuple[str, int, str]:
        """(name, offset, module) of the object holding byte / bit a; area name when no object does."""
        k = "iram" if space in ("data", "idata", "iram") else space
        keys, objs = self._keys[k], self.objs[k]
        i = bisect.bisect_right(keys, a) - 1
        best = None
        j = i
        while j >= 0 and a - objs[j][0] < 4096 and best is None:
            if objs[j][0] <= a < objs[j][0] + max(1, objs[j][1]):
                best = objs[j]
            j -= 1
        if best:
            return best[2], a - best[0], best[3]
        if k in self.areas:
            ai = bisect.bisect_right(self._akeys[k], a) - 1
            while ai >= 0:
                s, sz, n = self.areas[k][ai][0], self.areas[k][ai][1], self.areas[k][ai][2]
                if s <= a < s + sz:
                    return f"[{n}]", a - s, "-"
                ai -= 1
                if a - s > 4096:
                    break
        return f"[{space}:0x{a:04x}]", 0, "-"
