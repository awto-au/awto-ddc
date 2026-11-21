#!/usr/bin/env python3
"""sdcc_san: ISR race sanitizer, host side of the core's -DSDCC_SAN build (scripts/mcs51_core.c; docs/sanitizer.md; awto-sdcc#176).

usage: AWTO_SIM_SAN=<outdir> [AWTO_SIM_SAN_MARKS=<marks.tsv>] <any sim script>      one <tag>-<pid>-<n>.san.{tsv,json} per Machine at exit
       sdcc_san.py merge <outdir-or-files...> [-o FILE]                             combine runs, rank, print the table
Log: tmp/logs/sdcc_san.log
"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

NX, NIR, NBT = 0x2800, 256, 128
NIDX = NX + NIR + NBT
CLS = {1: "A-conflict", 2: "B-lost-update", 3: "C-torn", 4: "D-clobber"}
CTX = ["main", "EXINT0", "T0", "EXINT1", "T1", "SERIAL", "T2", "WDT"]       # fallback names; ISR function names come from the vectors
VEC = [None, 0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B, 0x43]
MARKS_HDR = "# awto-sdcc isr-marks v1"
MARKS_HDR11 = "# awto-sdcc isr-marks v1.1"
SPACES = ("data", "idata", "xdata", "pdata", "bit", "code")
SUPPRESS_ALL = {"attr"}                    # class -> nothing reported
SUPPRESS_A = {"volatile", "marked"}        # class -> only (b) lost update and (c) torn
LOG = HERE.parent / "tmp/logs/sdcc_san.log"


class Cand(ctypes.Structure):
    _fields_ = [("pc1", ctypes.c_uint32), ("pc2", ctypes.c_uint32), ("idx", ctypes.c_uint16), ("idx2", ctypes.c_uint16),
                ("cls", ctypes.c_uint8), ("ctx", ctypes.c_uint8), ("kind", ctypes.c_uint8), ("open", ctypes.c_uint8),
                ("did", ctypes.c_uint8), ("_p", ctypes.c_uint8 * 3), ("n", ctypes.c_uint32)]


def read_marks(path: Path) -> dict[tuple[str, str], dict]:
    """awto-sdcc isr-marks v1 / v1.1 TSV -> {(symbol, module): {size, cls, contexts, reason, space}}; v1.1 adds the last column `space`."""
    lines = Path(path).read_text().splitlines()
    ver = {MARKS_HDR: 1, MARKS_HDR11: 2}.get(lines[0].strip() if lines else "")
    if not ver:
        raise SystemExit(f"{path}: first line must be {MARKS_HDR!r} or {MARKS_HDR11!r} (unknown mark-list version)")
    out = {}
    for ln in lines[1:]:
        if not ln.strip() or ln.startswith(("#", "symbol\t")):
            continue
        f = ln.split("\t")
        if len(f) < 5 + ver or f[3] not in ("attr", "volatile", "marked", "exempt", "unmarked") or (ver == 2 and f[6] not in SPACES):
            raise SystemExit(f"{path}: bad row {ln!r}")
        out[(f[0], f[1])] = {"symbol": f[0], "module": f[1], "size": int(f[2]), "cls": f[3], "contexts": f[4], "reason": f[5],
                             "space": f[6] if ver == 2 else ""}
    return out


class Namer:
    """Index / pc -> names. Objects from san_names.Placed (map, + linked listings when AWTO_SIM_SAN_RST matches this build)."""

    def __init__(self, m, marks: dict | None = None):
        from san_names import Placed
        self.m = m
        rst = os.environ.get("AWTO_SIM_SAN_RST")
        self.pl = Placed(m.map_text, Path(rst) if rst else None)
        self.cend = getattr(m.where, "cend", 0)
        self.ctx = list(CTX)
        code = m.core.code
        for i in range(1, 8):
            v = VEC[i]
            if code[v] == 0x02:
                t = code[v + 1] << 8 | code[v + 2]
                self.ctx[i] = m.where(0, t).lstrip("_")
        self.mark_at: dict[tuple[str, int], dict] = {}          # (xdata|iram|bit, address) -> mark row
        self.unresolved = []
        for (sym, mod), mk in (marks or {}).items():
            r = self.pl.by_name.get((sym, mod))
            if not r:
                self.unresolved.append(f"{sym}@{mod}")
                continue
            sp, a, _ = r
            k = "xdata" if sp == "xdata" else "bit" if sp == "bit" else "iram"
            for x in range(a, a + max(1, mk["size"] if k != "bit" else 1)):
                self.mark_at[(k, x)] = mk

    def space(self, idx: int) -> tuple[str, int]:
        return ("xdata", 0xD000 + idx) if idx < NX else ("iram", idx - NX) if idx < NX + NIR else ("bit", idx - NX - NIR)

    def obj(self, idx: int) -> tuple[str, int, int]:
        """(name, offset in it, object size) of an index; bits are named by their bit object, else byte + bit."""
        sp, a = self.space(idx)
        if sp == "bit":
            n, off, _ = self.pl.find("bit", a)
            if not n.startswith("["):
                return n, off, 1
            n, off, _ = self.pl.find("iram", 0x20 + (a >> 3))
            return f"{n}+{off}.bit{a & 7}", 0, 1
        n, off, md = self.pl.find(sp, a)
        sz = next((o[1] for o in self.pl.objs[sp] if o[2] == n and o[3] == md), 1)
        return n, off, sz

    def label(self, idx: int) -> str:
        n, off, _ = self.obj(idx)
        return n + (f"+{off}" if off and "bit" not in n.rsplit(".", 1)[-1] else "")

    def mark(self, idx: int) -> str:
        sp, a = self.space(idx)
        mk = self.mark_at.get((sp, a))
        return mk["cls"] if mk else "unlisted"

    def norm(self, pc: int) -> int:
        """Code in the common area is the same in every bank: drop the bank so one site is one pc."""
        return pc & 0xFFFF if (pc & 0xFFFF) < self.cend else pc

    def func(self, pc: int) -> str:
        return self.m.where(pc >> 16, pc & 0xFFFF)


def names(mask: int, ctxn: list[str], skip: int = -1) -> str:
    return ",".join(ctxn[i] for i in range(8) if mask >> i & 1 and i != skip)


def finalise(m, marks: dict | None) -> list[dict]:
    """Join the core's candidates with the per-address contexts that ever read / wrote: could (mask allowed it) vs did (it ran inside the window)."""
    core, L = m.core, m.core.L
    n = (ctypes.c_uint64 * 6)()
    L.core_san_stats(core.h, ctypes.addressof(n))
    tab = (Cand * n[4]).from_address(L.core_san_ptr(core.h, 0))
    evr = (ctypes.c_uint8 * NIDX).from_address(L.core_san_ptr(core.h, 1))
    evw = (ctypes.c_uint8 * NIDX).from_address(L.core_san_ptr(core.h, 2))
    marks = marks or {}
    nm = Namer(m, marks)
    rows, seen = [], {}
    for e in tab:
        if not e.cls:
            continue
        i, j, w = e.idx, e.idx2, e.kind
        if e.cls == 1:
            conf = evw[i] | (evr[i] if w else 0)
        elif e.cls == 3:
            conf = evw[i] | evw[j] | ((evr[i] | evr[j]) if w else 0)
        else:
            conf = evw[i]
        could = e.open & conf & ~(1 << e.ctx)
        did = e.did & ~(1 << e.ctx)
        if not (could or did):
            continue
        sym, _, ext = nm.obj(i)
        mc = nm.mark(i)
        if mc in SUPPRESS_ALL or mc == "exempt" or (e.cls == 1 and mc in SUPPRESS_A):
            continue
        if e.cls == 3 and (ext < 2 or nm.obj(j)[0] != sym):
            continue                       # adjacent bytes of two objects, not one multi-byte access
        an = nm.label(i)
        a = nm.space(i)[1]
        e.pc1, e.pc2 = nm.norm(e.pc1), nm.norm(e.pc2) if e.pc2 else 0
        rows.append({"level": "did" if did else "could", "cls": CLS[e.cls], "symbol": an, "addr": f"{nm.space(i)[0]}:{a:#x}", "mark": mc,
                     "victim": nm.ctx[e.ctx], "could": names(could, nm.ctx), "did": names(did, nm.ctx), "rw": "W" if w else "R",
                     "func": nm.func(e.pc2 or e.pc1), "pc1": f"{e.pc1:#07x}", "func1": nm.func(e.pc1), "pc2": f"{e.pc2:#07x}" if e.pc2 else "",
                     "func2": nm.func(e.pc2) if e.pc2 else "", "n": e.n, "tag": m.tag})
    # exempt objects that the run saw from two contexts: a miss in the static analysis
    for mk in marks.values():
        r = nm.pl.by_name.get((mk["symbol"], mk["module"]))
        if mk["cls"] != "exempt" or not r or r[0] == "bit":
            continue
        base = 0 if r[0] == "xdata" else NX
        lo = r[1] - (0xD000 if r[0] == "xdata" else 0)
        ctxs = 0
        for x in range(lo, lo + max(1, mk["size"])):
            ctxs |= evr[base + x] | evw[base + x]
        if ctxs.bit_count() >= 2:
            rows.append({"level": "did", "cls": "MISS", "symbol": mk["symbol"], "addr": f"{r[0]}:{r[1]:#x}", "mark": "exempt", "victim": "", "could": "",
                         "did": names(ctxs, nm.ctx), "rw": "", "func": "", "pc1": "", "func1": "", "pc2": "", "func2": "", "n": 1, "tag": m.tag})
    if nm.unresolved:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.open("a").write(f"{m.tag}: {len(nm.unresolved)} mark rows not resolved to an address (statics need AWTO_SIM_SAN_RST): {nm.unresolved[:5]}\n")
    LOG.open("a").write(f"{m.tag}: names from {nm.pl.source}\n")
    for r in rows:
        k = (r["level"], r["cls"], r["symbol"], r["victim"], r["pc1"], r["pc2"])
        if k not in seen:
            seen[k] = r
    return list(seen.values())


RANK_CLS = {"MISS": 0, "B-lost-update": 1, "C-torn": 2, "D-clobber": 3, "A-conflict": 4}


def rank_key(r: dict):
    return (r["level"] != "did", RANK_CLS.get(r["cls"], 9), r["mark"] == "unlisted", -int(r["n"]))


COLS = ["level", "cls", "symbol", "addr", "mark", "victim", "could", "did", "rw", "func", "pc1", "func1", "pc2", "func2", "n", "tag"]


def write(rows: list[dict], path: Path):
    rows = sorted(rows, key=rank_key)
    path.write_text("\t".join(COLS) + "\n" + "".join("\t".join(str(r[c]) for c in COLS) + "\n" for r in rows))
    path.with_suffix(".json").write_text(json.dumps(rows, indent=1))


_N = [0]


def attach(m):
    """FastMachine hook (AWTO_SIM_SAN set): enable the core's sanitizer; findings are written at exit."""
    if not m.core.san_enable():
        raise SystemExit("AWTO_SIM_SAN set but the core was built without -DSDCC_SAN")
    out = Path(os.environ["AWTO_SIM_SAN"])
    out.mkdir(parents=True, exist_ok=True)
    _N[0] += 1
    n = _N[0]
    done = []

    def dump():
        if m.core.h is None or done:
            return
        done.append(1)
        mp = os.environ.get("AWTO_SIM_SAN_MARKS")
        rows = finalise(m, read_marks(Path(mp)) if mp else None)
        f = out / f"{re.sub(r'[^A-Za-z0-9._-]', '_', str(m.tag))}-{os.getpid()}-{n}.san.tsv"
        write(rows, f)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as lg:
            lg.write(f"{f}: {len(rows)} findings ({sum(r['level'] == 'did' for r in rows)} did)\n")
    atexit.register(dump)
    free = m.core.free

    def free_dump():                       # most sims close the machine (core freed) before exit
        dump()
        free()
    m.core.free = free_dump


def merge(paths: list[str], outp: str | None):
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob("*.san.json")) if p.is_dir() else [p]
    seen = {}
    for f in files:
        for r in json.loads(f.read_text()):
            k = (r["cls"], r["symbol"], r["victim"], r["pc1"], r["pc2"])
            o = seen.get(k)
            if o is None:
                seen[k] = dict(r, tags={r["tag"]})
            else:
                o["tags"].add(r["tag"])
                o["n"] = int(o["n"]) + int(r["n"])
                if r["level"] == "did":
                    o["level"] = "did"
                for fld in ("could", "did"):
                    o[fld] = ",".join(sorted(set(filter(None, (o[fld] + "," + r[fld]).split(",")))))
    rows = sorted(seen.values(), key=rank_key)
    for r in rows:
        r["tag"] = ",".join(sorted(r.pop("tags")))
    txt = "\t".join(COLS) + "\n" + "".join("\t".join(str(r[c]) for c in COLS) + "\n" for r in rows)
    if outp:
        Path(outp).write_text(txt)
        Path(outp).with_suffix(".json").write_text(json.dumps(rows, indent=1))
    print(txt, end="")
    return rows


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "merge":
        a = sys.argv[2:]
        o = None
        if "-o" in a:
            k = a.index("-o")
            o = a[k + 1]
            a = a[:k] + a[k + 2:]
        merge(a, o)
    else:
        raise SystemExit(__doc__)
