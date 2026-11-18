#!/usr/bin/env python3
"""Read-behind cause experiments (read-only, debug slave 0x35 byte path): what does the latch depend on?

usage: reg_behind_cause.py --unit N [--pages A0,A8,8E,88,CE] [--pairs 24] [--out FILE]
  Per page: truth of 4 lanes of sampled dwords (3 reads each: d1 d2 d3, truth = d2 if d2 == d3). Pairs X -> Y of sampled
  dwords, settled X (two reads of X0), then:
    order : Y lanes read asc 0123 / desc 3210 / 1023 / 2301: per step, value == truth (ok) or == X same lane (stale)
    gap   : Y0 after a busy-wait gap of 0, 1, 10, 100, 1000 ms (stale rate per gap); Y0 re-read after the gap
    cross : X, Z (another page: fast page 01..10 or the mirror page A0 <-> A8), Y0: is Y0 X-lane, Z-lane or ok
    unmap : X, then an unmapped address (88C0): value vs X lane
  Gaps are busy-waited (perf_counter), no sleep. Read-only: rtd_i2c_bridge.Real(allow_write=False, regread=True); the
  link is switched on / off by dbg_link (the only writes). Log: tmp/logs/reg_behind_cause.log, one line per read.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import isostamp
import reg_live_scan as S

ROOT = S.ROOT
LOG = ROOT / "tmp/logs/reg_behind_cause.log"
GAPS_MS = (0, 1, 10, 100, 1000)
ORDERS = ("0123", "3210", "1023", "2301")
FAST_PAGES = (0x01, 0x06, 0x0A, 0x10)          # no read-behind (read_behind.tsv: no)
MIRROR = {0xA0: 0xA8, 0xA8: 0xA0, 0x88: 0xC8, 0xC8: 0x88, 0x8E: 0xCE, 0xCE: 0x8E, 0xA6: 0xAE, 0xAE: 0xA6}
GROUPS = ((0x88, 0x8A, 0x8B, 0x8E, 0x8F, 0x90), (0xA0, 0xA3, 0xA4, 0xA6, 0xA7), (0xA8, 0xAB, 0xAC, 0xAE, 0xAF),
          (0xC8, 0xCA, 0xCB, 0xCE, 0xCF, 0xD0))
UNMAPPED = 0x88C0


class Rd:
    def __init__(self, io, lf):
        self.io, self.lf, self.hi, self.last, self.n = io, lf, None, None, 0

    def rd(self, a: int, tag: str) -> int:
        if a >> 8 != self.hi:
            self.hi = None
            if not self.io.write(X.DEV8, X.CMD_HI, bytes([a >> 8])):
                raise OSError(f"stage {a:04X}")
            self.hi = a >> 8
        if not self.io.write(X.DEV8, X.CMD_READ, bytes([a & 0xFF])):
            self.hi = None
            raise OSError(f"cmd {a:04X}")
        r = self.io.read(X.DEV8, X.READ_SUB, 1)
        if r is None:
            self.hi = None
            raise OSError(f"read {a:04X}")
        self.lf.write(f"{isostamp.now()} {a:04X} {r[0]:02X} {tag} prev={'----' if self.last is None else f'{self.last:04X}'}\n")
        self.last = a
        self.n += 1
        return r[0]


    def blk(self, a: int, n: int, tag: str):
        d = X.read_chunk(self.io, a, n, tries=1)
        self.lf.write(f"{isostamp.now()} {a:04X} {'--' if d is None else d.hex()} {tag} blk{n} prev={'----' if self.last is None else f'{self.last:04X}'}\n")
        self.last = a + n - 1
        self.hi = None
        return d


def wait_ms(ms: float) -> None:
    """Busy-wait: the gap between two reads is the measured quantity."""
    t = time.perf_counter() + ms / 1000
    while time.perf_counter() < t:
        pass


def truth_dword(r: Rd, base: int) -> list | None:
    """Four settled lane bytes of the dword at `base`, None if any lane is unstable."""
    out = []
    for i in range(4):
        r.rd(base + i, "t1")
        d2, d3 = r.rd(base + i, "t2"), r.rd(base + i, "t3")
        if d2 != d3:
            return None
        out.append(d2)
    return out


def sample_dwords(r: Rd, p: int, want: int) -> dict:
    """base -> 4 truth bytes, evenly spread over the page, usable dwords only (no excluded address, stable)."""
    bases = [(p << 8) | o for o in range(0, 256, 4) if all(S.excluded(((p << 8) | o) + i) is None for i in range(4))]
    step = max(1, len(bases) // (want * 2))
    res = {}
    for b in bases[::step]:
        t = truth_dword(r, b)
        if t is not None:
            res[b] = t
        if len(res) >= want * 2:
            break
    return res


def pairs_of(d: dict, want: int) -> list:
    """(X, Y) with the most lanes where Y differs from X."""
    ks = sorted(d)
    out = []
    for i, x in enumerate(ks):
        for y in ks[i + 1:] + ks[:i]:
            nd = sum(1 for k in range(4) if d[x][k] != d[y][k])
            if nd >= 3:
                out.append((nd, x, y))
                break
    out.sort(reverse=True)
    return [(x, y) for _, x, y in out[:want]]


def settle(r: Rd, x: int) -> None:
    r.rd(x, "settle1")
    r.rd(x, "settle2")


class Tally(dict):
    def add(self, key, ok: bool, stale: bool) -> None:
        t = self.setdefault(key, [0, 0, 0])          # informative n, ok, stale (= X same lane)
        t[0] += 1
        t[1] += ok
        t[2] += stale


def run_page(r: Rd, p: int, want: int, res: dict) -> None:
    d = sample_dwords(r, p, want)
    prs = pairs_of(d, want)
    rec = {"dwords": len(d), "pairs": len(prs), "order": Tally(), "gap": Tally(), "gap_re": Tally(), "cross": {}, "unmap": []}
    res[f"{p:02X}"] = rec
    for x, y in prs:
        tx, ty = d[x], d[y]
        for order in ORDERS:
            settle(r, x)
            for step, ch in enumerate(order):
                ln = int(ch)
                v = r.rd(y + ln, f"order{order}.{step}")
                if tx[ln] != ty[ln]:
                    rec["order"].add(f"{order}:{step}:L{ln}", v == ty[ln], v == tx[ln])
        for g in GAPS_MS:
            settle(r, x)
            wait_ms(g)
            v = r.rd(y, f"gap{g}")
            if tx[0] != ty[0]:
                rec["gap"].add(f"{g}ms", v == ty[0], v == tx[0])
            wait_ms(g)
            v2 = r.rd(y, f"gap{g}.re")
            if tx[0] != ty[0]:
                rec["gap_re"].add(f"{g}ms", v2 == ty[0], v2 == tx[0])
        # cross: X, Z (other page), Y0
        zs = []
        if (p in MIRROR):
            m = MIRROR[p]
            zs.append(("mirror", x ^ ((p ^ m) << 8)))   # same offset on the mirror page
        for fp in FAST_PAGES[:2]:
            zs.append((f"fast{fp:02X}", (fp << 8) | (x & 0xFC)))
        for name, z in zs:
            if S.excluded(z) is not None:
                continue
            tz = truth_dword(r, z & ~3)
            if tz is None:
                continue
            settle(r, x)
            vz = r.rd(z & ~3, f"cross-{name}-Z")
            v = r.rd(y, f"cross-{name}-Y0")
            if tx[0] != ty[0]:
                kind = "ok" if v == ty[0] else "X" if v == tx[0] else "Z" if v == tz[0] else "other"
                c = rec["cross"].setdefault(name, {"ok": 0, "X": 0, "Z": 0, "other": 0, "n": 0})
                c[kind] += 1
                c["n"] += 1
                c["Z_distinct"] = c.get("Z_distinct", 0) + (tz[0] not in (tx[0], ty[0]))
                c["Zread_ok"] = c.get("Zread_ok", 0) + (vz == tz[0])
        # same page, third dword W between X and Y; sibling page (same block group), same offset
        others = [b for b in d if b not in (x, y)]
        cands = [("samepage", others[0])] if others else []
        for g in GROUPS:
            if p in g:
                cands += [(f"sib{q:02X}", (q << 8) | (x & 0xFC)) for q in g if q != p][:2]
        for name, z in cands:
            if S.excluded(z) is not None:
                continue
            tz = d[z] if z in d else truth_dword(r, z)
            if tz is None:
                continue
            settle(r, x)
            r.rd(z, f"cross-{name}-Z")
            v = r.rd(y, f"cross-{name}-Y0")
            if tx[0] != ty[0]:
                kind = "ok" if v == ty[0] else "X" if v == tx[0] else "Z" if v == tz[0] else "other"
                c = rec["cross"].setdefault(name, {"ok": 0, "X": 0, "Z": 0, "other": 0, "n": 0})
                c[kind] += 1
                c["n"] += 1
                c["Z_distinct"] = c.get("Z_distinct", 0) + (tz[0] not in (tx[0], ty[0]))
        # block path: 4 bytes at Y after X; then primed by a read of Y2 first
        for w in ("blk", "blk_primed"):
            settle(r, x)
            if w == "blk_primed":
                r.rd(y + 2, "prime")
            b = r.blk(y, 4, w)
            if b is not None:
                c = rec["cross"].setdefault(w, {"lane_ok": [0] * 4, "lane_stale": [0] * 4, "lane_n": [0] * 4})
                for ln in range(4):
                    if tx[ln] != ty[ln]:
                        c["lane_n"][ln] += 1
                        c["lane_ok"][ln] += b[ln] == ty[ln]
                        c["lane_stale"][ln] += b[ln] == tx[ln]
        # unmapped address after X
        settle(r, x)
        u = [r.rd(UNMAPPED, "unmap1"), r.rd(UNMAPPED, "unmap2"), r.rd(UNMAPPED, "unmap3")]
        rec["unmap"].append({"X": f"{x:04X}", "tx0": tx[0], "reads": u})


def fmt(res: dict) -> str:
    out = []
    for pg, rec in res.items():
        out.append(f"page {pg}: dwords {rec['dwords']} pairs {rec['pairs']}")
        for k in ("order", "gap", "gap_re"):
            out.append(f"  {k}: " + "  ".join(f"{a}={v[1]}/{v[0]}ok,{v[2]}stale" for a, v in sorted(rec[k].items())))
        for k, v in rec["cross"].items():
            out.append(f"  cross {k}: {v}")
        out.append("  unmap " + " ".join(f"{u['tx0']:02X}->{'/'.join(f'{q:02X}' for q in u['reads'])}" for u in rec["unmap"][:6]))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--pages", default="A0,A8,8E,88,CE")
    ap.add_argument("--pairs", type=int, default=24)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--out")
    ap.add_argument("--minutes", type=int, default=15, help="link lifetime if the firmware has to be told")
    a = ap.parse_args()
    import dbg_link
    import rtd_i2c_bridge
    u = S.unit_info(a.unit)
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    out = Path(a.out) if a.out else ROOT / f"tmp/regs/live/{u['serial']}-behind-cause-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    res: dict = {}
    meta = {"serial": u["serial"], "unit": a.unit, "bus": bus, "start": isostamp.now()}
    meta["link"] = dbg_link.on(bus, a.minutes)
    io = rtd_i2c_bridge.Real(bus, allow_write=False, regread=True)
    try:
        with LOG.open("a") as lf:
            r = Rd(io, lf)
            for ps in a.pages.split(","):
                run_page(r, int(ps, 16), a.pairs, res)
                out.write_text(json.dumps({**meta, "pages": res, "partial": True}))
            meta["reads"] = r.n
    finally:
        io.close()
        meta["link_off"] = dbg_link.off(bus)
    meta["end"] = isostamp.now()
    out.write_text(json.dumps({**meta, "pages": res}))
    print(fmt(res))
    print(f"reads={meta['reads']} link off={meta['link_off']} {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
