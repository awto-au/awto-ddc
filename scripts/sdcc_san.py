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
SUPPRESS_ALL = {"attr"}                    # class -> nothing reported
SUPPRESS_A = {"volatile", "marked"}        # class -> only (b) lost update and (c) torn
LOG = HERE.parent / "tmp/logs/sdcc_san.log"


class Cand(ctypes.Structure):
    _fields_ = [("pc1", ctypes.c_uint32), ("pc2", ctypes.c_uint32), ("idx", ctypes.c_uint16), ("idx2", ctypes.c_uint16),
                ("cls", ctypes.c_uint8), ("ctx", ctypes.c_uint8), ("kind", ctypes.c_uint8), ("open", ctypes.c_uint8),
                ("did", ctypes.c_uint8), ("_p", ctypes.c_uint8 * 3), ("n", ctypes.c_uint32)]


def read_marks(path: Path) -> dict[str, dict]:
    """awto-sdcc isr-marks v1 TSV -> {symbol: {module, size, cls, contexts, reason}}; an unknown version is rejected."""
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0].strip() != MARKS_HDR:
        raise SystemExit(f"{path}: first line must be {MARKS_HDR!r} (unknown mark-list version)")
    out = {}
    for ln in lines[1:]:
        if not ln.strip() or ln.startswith(("#", "symbol\t")):
            continue
        f = ln.split("\t")
        if len(f) < 6 or f[3] not in ("attr", "volatile", "marked", "exempt", "unmarked"):
            raise SystemExit(f"{path}: bad row {ln!r}")
        out[f[0] if f[1] == "-" else f"{f[0]}@{f[1]}"] = {"symbol": f[0], "module": f[1], "size": int(f[2]), "cls": f[3], "contexts": f[4], "reason": f[5]}
    return out


def xdata_syms(map_text: str) -> tuple[list[int], list[str]]:
    """Sorted XDATA / data globals (map 'D:' lines)."""
    rows = sorted({(int(m.group(1), 16), m.group(2)) for m in re.finditer(r"^D:\s+([0-9A-F]{8})\s+(\w+)", map_text, re.MULTILINE)})
    return [r[0] for r in rows], [r[1] for r in rows]


class Namer:
    """Index / pc -> names. Symbols are the map's globals (statics are not in it: `~sym+off` = nearest global below)."""

    def __init__(self, m):
        import bisect
        self.m, self.bisect = m, bisect
        self.av, self.an = xdata_syms(m.map_text)
        self.ctx = list(CTX)
        code = m.core.code
        for i in range(1, 8):
            v = VEC[i]
            if code[v] == 0x02:
                t = code[v + 1] << 8 | code[v + 2]
                self.ctx[i] = m.where(0, t).lstrip("_")

    def addr(self, idx: int) -> tuple[int, str]:
        if idx < NX:
            a = 0xD000 + idx
            k = self.bisect.bisect_right(self.av, a) - 1
            if k < 0:
                return a, f"xdata:0x{a:04x}"
            off = a - self.av[k]
            nxt = self.av[k + 1] if k + 1 < len(self.av) else a + 1
            exact = off < max(1, nxt - self.av[k])
            return a, f"{'' if exact else '~'}{self.an[k]}{f'+{off}' if off else ''}"
        if idx < NX + NIR:
            return idx - NX, f"iram:0x{idx - NX:02x}"
        return idx - NX - NIR, f"bit:0x{idx - NX - NIR:02x}"

    def sym(self, idx: int) -> tuple[str, int, int]:
        """(symbol, offset, extent) of an index; extent = bytes to the next global."""
        if idx >= NX:
            return self.addr(idx)[1], 0, 1
        a = 0xD000 + idx
        k = self.bisect.bisect_right(self.av, a) - 1
        if k < 0:
            return f"xdata:0x{a:04x}", 0, 1
        nxt = self.av[k + 1] if k + 1 < len(self.av) else a + 1
        return self.an[k], a - self.av[k], nxt - self.av[k]

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
    nm = Namer(m)
    rows, seen = [], {}
    marks = marks or {}
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
        sym, _, ext = nm.sym(i)
        mk = marks.get(sym)
        mc = mk["cls"] if mk else "unlisted"
        if mc in SUPPRESS_ALL or mc == "exempt" or (e.cls == 1 and mc in SUPPRESS_A):
            continue
        if e.cls == 3 and (ext < 2 or nm.sym(j)[0] != sym):
            continue                       # adjacent bytes of two objects, not one multi-byte access
        a, an = nm.addr(i)
        rows.append({"level": "did" if did else "could", "cls": CLS[e.cls], "symbol": an, "addr": a if i < NX else an, "mark": mc,
                     "victim": nm.ctx[e.ctx], "could": names(could, nm.ctx), "did": names(did, nm.ctx), "rw": "W" if w else "R",
                     "func": nm.func(e.pc2 or e.pc1), "pc1": f"{e.pc1:#07x}", "func1": nm.func(e.pc1), "pc2": f"{e.pc2:#07x}" if e.pc2 else "",
                     "func2": nm.func(e.pc2) if e.pc2 else "", "n": e.n, "tag": m.tag})
    # exempt objects that the run saw from two contexts: a miss in the static analysis
    for mk in marks.values():
        if mk["cls"] != "exempt" or mk["module"] != "-" or mk["symbol"] not in m.sym_data():
            continue
        a0 = m.sym_data()[mk["symbol"]]
        ctxs = 0
        for a in range(a0, a0 + max(1, mk["size"])):
            if 0xD000 <= a < 0xF800:
                ctxs |= evr[a - 0xD000] | evw[a - 0xD000]
        if ctxs.bit_count() >= 2:
            rows.append({"level": "did", "cls": "MISS", "symbol": mk["symbol"], "addr": a0, "mark": "exempt", "victim": "", "could": "",
                         "did": names(ctxs, nm.ctx), "rw": "", "func": "", "pc1": "", "func1": "", "pc2": "", "func2": "", "n": 1, "tag": m.tag})
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
    av, an = xdata_syms(m.map_text)
    syms = dict(zip(an, av))
    m.sym_data = lambda: syms

    def dump():
        if m.core.h is None:
            return
        mp = os.environ.get("AWTO_SIM_SAN_MARKS")
        rows = finalise(m, read_marks(Path(mp)) if mp else None)
        f = out / f"{re.sub(r'[^A-Za-z0-9._-]', '_', str(m.tag))}-{os.getpid()}-{n}.san.tsv"
        write(rows, f)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as lg:
            lg.write(f"{f}: {len(rows)} findings ({sum(r['level'] == 'did' for r in rows)} did)\n")
    atexit.register(dump)


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
