#!/usr/bin/env python3
"""Read-behind probe: does a read at a NEW address return the previous read's data (awto-ddc register read artifact)?

usage: reg_behind_probe.py --unit N [--pages all|00,38-3A,..] [--no-block] [--out FILE]
         reg_behind_probe.py --tsv FILE.json [FILE2.json ..]     (write re/regmap/read_behind.tsv from probe results)
  Per page, byte path through the debug slave 0x35, every non-excluded address A (EXCLUDE of reg_live_scan.py):
    d1 d2 d3 = three reads of A in a row. d1 follows a read of another address (A-1); d2 / d3 repeat A.
    truth[A] = d2, stable if d2 == d3. rev = a reverse pass, far = read of B (37 positions on) then A.
    A read is 'clean' if it equals truth[A], 'stale' if it equals the truth of the previous read's address (and not
    truth[A]), 'ambig' if both truths are equal, 'skip' if a truth is unstable / unknown, else 'other'.
  Block path (0x3C, 24 bytes): each chunk read twice in a row; every byte position compared with truth[A+i] (clean) and
    truth[A+i-1] (shifted by one).
  Read-only: the bus is rtd_i2c_bridge.Real(allow_write=False, regread=True). Abort: 3 failed reads in a row, failed
  heartbeat (0x0000 != 0xCF every 256 reads), wall bound. Log: tmp/logs/reg_behind_probe.log (one line per read).
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
from _repo import ROOT

LOG = ROOT / "tmp/logs/reg_behind_probe.log"
TSV = ROOT / "re/regmap/read_behind.tsv"
CTXS = ("d1", "d2", "d3", "rev", "far", "far2")
DEP_MAX = 64
EVENTS_MAX = 40                # stale / other events kept per page in the JSON
FAR = 37                       # distance (positions in the page list) of the 'far' pre-read
HB_EVERY = 256
MAX_CONSEC_FAIL = 3
MAX_BLOCK_FAIL = 40            # failed checksum blocks in a row (single try; firmware RAM pages race the ISR)
TSV_COLS = ["page", "live", "isp", "live_byte", "live_block", "isp_byte", "wrong_by_lane", "tool", "date"]


class Probe:
    """Byte-path reader with the previous-read bookkeeping; every read logged."""

    def __init__(self, io, log, rdfn=None):
        self.io, self.log, self.rdfn = io, log, rdfn   # rdfn(addr) -> int: ISP path (rtd_osd.Osd.rd) instead of the debug slave
        self.hi = None
        self.last: int | None = None       # address of the previous read (any path)
        self.consec = 0
        self.bfail = 0
        self.n = 0
        self.since_hb = 0

    def byte(self, a: int, tag: str) -> int | None:
        if self.rdfn is not None:
            try:
                v = self.rdfn(a)
            except OSError:
                return self._fail(a, tag)
            self.consec = 0
            self.n += 1
            self.log(f"{a:04X} {v:02X} {tag} prev={'----' if self.last is None else f'{self.last:04X}'}")
            self.last = a
            self.since_hb += 1
            return v
        if a >> 8 != self.hi:
            self.hi = None
            if not self.io.write(X.DEV8, X.CMD_HI, bytes([a >> 8])):
                return self._fail(a, tag)
            self.hi = a >> 8
        if not self.io.write(X.DEV8, X.CMD_READ, bytes([a & 0xFF])):
            self.hi = None
            return self._fail(a, tag)
        r = self.io.read(X.DEV8, X.READ_SUB, 1)
        if r is None:
            self.hi = None
            return self._fail(a, tag)
        self.consec = 0
        self.n += 1
        self.log(f"{a:04X} {r[0]:02X} {tag} prev={'----' if self.last is None else f'{self.last:04X}'}")
        self.last = a
        self.since_hb += 1
        return r[0]

    def _fail(self, a: int, tag: str):
        self.consec += 1
        self.log(f"{a:04X} -- NAK {tag}")
        self.last = a
        if self.consec >= MAX_CONSEC_FAIL:
            raise S.Aborted(f"{MAX_CONSEC_FAIL} consecutive failed reads ending at 0x{a:04X}")

    def heartbeat(self, tag: str) -> None:
        v = self.byte(S.ID_ADDR, f"HB-{tag}")
        if v != S.ID_VALUE:                 # one stale read after a page change was seen (0x00 once in 4112): confirm before aborting
            v = self.byte(S.ID_ADDR, f"HB-{tag}-confirm")
        self.since_hb = 0
        if v != S.ID_VALUE:
            raise S.Aborted(f"heartbeat {tag}: ID_REG read {v!r}, want 0x{S.ID_VALUE:02X}")

    def block(self, a: int, n: int, tag: str) -> bytes | None:
        d = X.read_chunk(self.io, a, n, tries=1)
        self.log(f"{a:04X} {'--' if d is None else d.hex()} {tag} blk{n} prev={'----' if self.last is None else f'{self.last:04X}'}")
        self.last = a + n - 1
        self.hi = None                      # the block path does not touch the staged hi byte, but be safe
        if d is None:
            self.bfail += 1
            if self.bfail >= MAX_BLOCK_FAIL:
                raise S.Aborted(f"{MAX_BLOCK_FAIL} consecutive failed block reads at 0x{a:04X}")
            return None
        self.bfail = 0
        return d


def lane_addr(prev, a):
    """The byte the read would return if the previous read's 32-bit dword were still latched: same lane, previous dword."""
    return None if prev is None else (prev & ~3) | (a & 3)


def judge(v, a, prev, truth, stable):
    """ok | stale | lane | both | other | skip for one read v of address a that followed a read of `prev`.
    stale = v is truth[prev] (previous byte); lane = v is truth[lane_addr] (same lane of the previous dword);
    both = matches both; other = wrong, matches neither; skip = no stable truth of a."""
    if v is None or a not in truth or not stable.get(a):
        return "skip"
    if v == truth[a]:
        return "ok"
    s = prev is not None and prev in truth and stable.get(prev) and v == truth[prev]
    la = lane_addr(prev, a)
    ln = la is not None and la in truth and stable.get(la) and v == truth[la]
    return "both" if s and ln else "stale" if s else "lane" if ln else "other"


def informative(a, prev, truth):
    """The read can tell clean from stale: the true value differs from the lane byte and the previous byte."""
    la = lane_addr(prev, a)
    if prev is None or prev not in truth or la not in truth or truth[a] == truth[prev]:
        return False
    return (prev >> 2) == (a >> 2) or truth[a] != truth[la]


KINDS = ("ok", "stale", "lane", "both", "other", "skip")
WRONG = ("stale", "lane", "both", "other")


def _tally(items) -> dict:
    t = dict.fromkeys(KINDS, 0)
    for k in items:
        t[k] += 1
    return t


def _agg(d: dict) -> dict:
    allr = [x for w in d for x in d[w]]
    inf = [k for k, i in allr if i]
    return {"n": len(allr), "ok": sum(1 for k, _ in allr if k == "ok"),
            "wrong": sum(1 for k, _ in allr if k in WRONG),
            "inf": len(inf), "inf_ok": sum(1 for k in inf if k == "ok"),
            "kinds": _tally(k for k, _ in allr)}


def probe_page(pb: Probe, p: int, truth: dict, stable: dict, block: bool, log) -> dict:
    addrs = [(p << 8) | o for o in range(256) if S.excluded((p << 8) | o) is None]
    rec: dict = {"page": f"{p:02X}", "addrs": len(addrs)}
    reads: list = []                       # (pass, addr, prev addr, value) for every first read after an address change
    prev0 = pb.last
    pc_v = pb.byte(addrs[0], "pagechange")
    d1s = {}
    for a in addrs:                         # d1 = read after the neighbour; d2 d3 = repeats of the same address
        prev = pb.last
        d1s[a] = (pb.byte(a, "d1"), prev)
        d2 = pb.byte(a, "d2")
        d3 = pb.byte(a, "d3")
        if d2 is not None:
            truth[a] = d2
            stable[a] = d2 == d3
        if pb.since_hb >= HB_EVERY:
            pb.heartbeat(f"{a:04X}")
    for a in addrs:
        reads.append(("fwd", a, d1s[a][1], d1s[a][0]))
    for a in reversed(addrs):
        prev = pb.last
        reads.append(("rev", a, prev, pb.byte(a, "rev")))
        if pb.since_hb >= HB_EVERY:
            pb.heartbeat(f"{a:04X}")
    n = len(addrs)
    far2 = []
    for i, a in enumerate(addrs):
        pb.byte(addrs[(i + FAR) % n], "farpre")
        prev = pb.last
        reads.append(("far", a, prev, pb.byte(a, "far")))
        far2.append((a, pb.byte(a, "far2")))
        if pb.since_hb >= HB_EVERY:
            pb.heartbeat(f"{a:04X}")
    tv = set()                              # time-varying: the settled value (two reads in a row) changed during the probe
    for a in addrs:
        pb.byte(a, "end1")                  # first read after the neighbour: may be stale, discarded
        e2, e3 = pb.byte(a, "end2"), pb.byte(a, "end3")
        if a in truth and (e2 != e3 or e2 != truth[a]):
            tv.add(a)
    events: list = []
    new = {k: [] for k in ("fwd", "rev", "far")}
    same = {k: [] for k in ("fwd", "rev", "far")}
    wrong_pos = [0, 0, 0, 0]
    for w, a, prev, v in reads:
        if a in tv:
            continue
        k = judge(v, a, prev, truth, stable)
        newdw = prev is not None and (prev >> 2) != (a >> 2)
        (new if newdw else same)[w].append((k, informative(a, prev, truth)))
        if k in WRONG:
            if newdw:
                wrong_pos[a & 3] += 1
            if len(events) < EVENTS_MAX:
                events.append([w, f"{a:04X}", "----" if prev is None else f"{prev:04X}", k, f"{v:02X}", f"{truth[a]:02X}",
                               f"{truth[prev]:02X}" if prev in truth else "--"])
    rec["new_dword"], rec["same_dword"] = _agg(new), _agg(same)
    rec["wrong_by_lane"] = wrong_pos        # new-dword wrong reads by byte lane (a & 3) of the read address
    rec["far2"] = _tally(judge(v, a, a, truth, stable) for a, v in far2 if a not in tv)
    rec["tv"] = len(tv)
    rec["tv_offsets"] = sorted(a & 0xFF for a in tv)[:32]
    rec["stable"] = sum(1 for a in addrs if stable.get(a))
    rec["pagechange"] = (judge(pc_v, addrs[0], prev0, truth, stable)
                         if prev0 is not None and prev0 >> 8 != p and addrs[0] not in tv else "none")
    rec["events"] = events                  # [pass, addr, prev addr, kind, got, truth(addr), truth(prev)]
    if block:
        rec["block"] = probe_blocks(pb, p, truth, stable, tv)
    pb.heartbeat(f"end{p:02X}")
    return rec


BPOS = ("first", "dwstart", "inside")      # block byte positions: chunk byte 0 / aligned dword start / inside a dword
BKIND = ("ok", "lane", "stale", "other", "skip")


def probe_blocks(pb: Probe, p: int, truth: dict, stable: dict, tv: set) -> dict:
    """Each chunk read twice in a row: b1 follows another address, b2 repeats the chunk.
    Per byte: ok / lane (previous dword, same lane) / stale (previous byte) / other; skip = uninformative or no truth."""
    out = {f"{w}_{pos}_{k}": 0 for w in ("b1", "b2") for pos in BPOS for k in BKIND}
    out["chunks"] = out["failed"] = 0
    for a, n in S.runs(p, maxlen=X.BLK_MAX):
        for w in ("b1", "b2"):
            last = pb.last
            d = pb.block(a, n, w)
            if d is None:
                out["failed"] += 1
                continue
            for i in range(n):
                ad = a + i
                pos = "first" if i == 0 else ("dwstart" if ad & 3 == 0 else "inside")
                prev = last if i == 0 else ad - 1
                if ad in tv or not stable.get(ad) or ad not in truth or not informative(ad, prev, truth):
                    k = "skip"
                elif d[i] == truth[ad]:
                    k = "ok"
                elif d[i] == truth.get(lane_addr(prev, ad)):
                    k = "lane"
                elif prev in truth and d[i] == truth[prev]:
                    k = "stale"
                else:
                    k = "other"
                out[f"{w}_{pos}_{k}"] += 1
        out["chunks"] += 1
    out["targeted"] = probe_blocks_targeted(pb, p, truth, stable, tv)
    return out


TARGET_N = 16                               # informative dword starts per page for the targeted block test


def probe_blocks_targeted(pb: Probe, p: int, truth: dict, stable: dict, tv: set) -> dict:
    """Block reads placed so that a dword start whose old-lane byte differs from its own value is read in the block:
    in_block = block(A-4, 8): byte 4 is A; first_after_far = byte read far away, then block(A, 4): byte 0 is A."""
    out = {f"{w}_{k}": 0 for w in ("in_block", "first_after_far") for k in BKIND if k != "skip"}
    cands = [a for a in range(p << 8, (p << 8) + 256) if a & 3 == 0 and a - 4 >= p << 8 and a + 3 < (p + 1) << 8
             and all(x in truth and stable.get(x) and x not in tv for x in (a, a - 4)) and truth[a] != truth[a - 4]]
    out["cands"] = len(cands)
    step = max(1, len(cands) // TARGET_N)
    for a in cands[::step][:TARGET_N]:
        if any(S.excluded(x) for x in range(a - 4, a + 4)):
            continue
        for w, start, n, i in (("in_block", a - 4, 8, 4), ("first_after_far", a, 4, 0)):
            if w == "first_after_far":
                far = a - 64 if a - 64 >= p << 8 else a + 64
                if S.excluded(far) or far not in truth:
                    continue
                pb.byte(far, "tgt-far")
            d = pb.block(start, n, f"tgt-{w}")
            if d is None:
                continue
            v, prev = d[i], (a - 1 if w == "in_block" else pb.last)
            prevd = a - 4 if w == "in_block" else far
            k = ("ok" if v == truth[a] else "lane" if v == truth.get((prevd & ~3) | 0) else
                 "stale" if prev in truth and v == truth[prev] else "other")
            out[f"{w}_{k}"] += 1
    return out


def verdict(rec: dict) -> tuple[str, str]:
    """(read_behind, byte-path text). Informative reads only.
    latch = first read in a new dword is wrong (>= 3 reads) and >= half of those equal the previous dword's byte of that lane;
    other = same-dword / repeat reads differ from the settled value (>= 3): read-sensitive or port-like registers, not the latch.
    yes = latch only, yes+other = both, other = other only, no = neither (<= 2 wrong reads = a register that moved),
    unknown = too few informative reads."""
    nd, sd, f2 = rec["new_dword"], rec["same_dword"], rec["far2"]
    rep_wrong = sum(f2[k] for k in WRONG)
    k = nd["kinds"]
    explained = k["stale"] + k["lane"] + k["both"]
    txt = (f"new dword: wrong {nd['wrong']} of {nd['n']} (latch-explained {explained}, informative {nd['inf']}, ok {nd['inf_ok']}); "
           f"same dword: wrong {sd['wrong']} of {sd['n']}; repeat: wrong {rep_wrong} of {sum(f2.values()) - f2['skip']}; "
           f"time-varying {rec['tv']}")
    latch = nd["wrong"] >= 3 and explained >= 0.5 * nd["wrong"]
    other = (sd["wrong"] >= 3 or rep_wrong >= 3) and not (latch and sd["wrong"] < 3 and rep_wrong <= 0.1 * nd["wrong"])
    if latch and other:
        return "yes+other", txt
    if latch:
        return "yes", txt
    if other:
        return "other", txt
    if nd["inf"] < 4:
        return "unknown", txt
    return "no", txt


def block_text(rec: dict) -> str:
    b = rec.get("block")
    if not b:
        return "unknown"
    parts = []
    t = b.get("targeted")
    if t:
        parts.append(f"targeted in-block dword start ok {t['in_block_ok']} wrong {t['in_block_lane'] + t['in_block_stale'] + t['in_block_other']}; "
                     f"first byte after far read ok {t['first_after_far_ok']} wrong "
                     f"{t['first_after_far_lane'] + t['first_after_far_stale'] + t['first_after_far_other']}")
    for w in ("b1", "b2"):
        for pos in BPOS:
            ok, bad = b[f"{w}_{pos}_ok"], sum(b[f"{w}_{pos}_{k}"] for k in ("lane", "stale", "other"))
            parts.append(f"{w} {pos} ok {ok} wrong {bad}")
    return "; ".join(parts)


def run_probe(io, pages: list[int], block: bool, log, save, wall_s: float, clock=time.monotonic, rdfn=None) -> dict:
    pb = Probe(io, log, rdfn)
    res: dict = {"pages": {}, "result": "ok", "abort": None, "path": "isp" if rdfn else ("block+byte" if block else "byte")}
    truth: dict = {}
    stable: dict = {}
    t0 = clock()
    try:
        pb.heartbeat("before")
        for p in pages:
            if clock() - t0 > wall_s:
                raise S.Aborted(f"wall bound {wall_s} s exceeded before page {p:02X}")
            res["pages"][f"{p:02X}"] = probe_page(pb, p, truth, stable, block, log)
            save(res)
    except S.Aborted as e:
        res["result"], res["abort"] = "aborted", e.reason
        log(f"ABORT {e.reason}")
    res["reads"] = pb.n
    res["elapsed_s"] = round(clock() - t0, 1)
    return res


def write_tsv(files: list[str]) -> None:
    """One row per page. live = debug slave 0x35 (MCU running; byte path + block path), isp = ISP F4/F5 (MCU halted).
    Later files override earlier ones per page and path."""
    live: dict = {}
    isp: dict = {}
    meta: dict = {}
    for fn in files:
        d = json.loads(Path(fn).read_text())
        dst = isp if d.get("path") == "isp" else live
        for pg, rec in d["pages"].items():
            dst[pg] = rec
            meta[(pg, d.get("path") == "isp")] = (d.get("unit", "?"), d["start"][:10])
    rows = []
    for pg in sorted(set(live) | set(isp)):
        lv, ltxt = verdict(live[pg]) if pg in live else ("-", "")
        iv, itxt = verdict(isp[pg]) if pg in isp else ("-", "")
        wl = live[pg]["wrong_by_lane"] if pg in live else isp[pg]["wrong_by_lane"]
        when = max(m[1] for k, m in meta.items() if k[0] == pg)
        rows.append({"page": pg, "live": lv, "isp": iv, "live_byte": ltxt or "-", "live_block": block_text(live[pg]) if pg in live else "-",
                     "isp_byte": itxt or "-", "wrong_by_lane": "/".join(str(x) for x in wl),
                     "tool": "scripts/reg_behind_probe.py (unit 3)", "date": when})
    TSV.parent.mkdir(parents=True, exist_ok=True)
    with TSV.open("w") as f:
        f.write("\t".join(TSV_COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in TSV_COLS) + "\n")


def main_isp(a) -> int:
    """ISP read path: MCU halted by ISP enter, reset at the end (the monitor reboots into its default image)."""
    import i2cbus
    from rtd_osd import Osd
    u = S.unit_info(a.unit)
    if not u.get("test"):
        raise SystemExit("ISP probe halts + resets the MCU: only on the test unit (devices.json test=true)")
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    i2cbus.require_unit(bus, u["serial"])
    out = Path(a.out) if a.out else ROOT / f"tmp/regs/live/{u['serial']}-behind-isp-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = LOG.open("a")

    def log(s: str) -> None:
        lf.write(f"{isostamp.now()} u{a.unit}/behind-isp {s}\n")

    meta = {"serial": u["serial"], "unit": a.unit, "bus": bus, "start": isostamp.now(), "fw_note": "isp"}
    import rtd_isp_probe
    import rtd_proto
    rtd_isp_probe.LOG = rtd_proto.setup_logs("reg_behind_probe_isp").main
    o = Osd(bus)
    o.enter()
    try:
        pages = S.parse_pages(a.pages, S.known_pages(ROOT))
        res = run_probe(None, pages, False, log, lambda r: out.write_text(json.dumps({**meta, **r, "partial": True})), a.wall_s, rdfn=o.rd)
    finally:
        o.reset()
        lf.flush()
    meta["end"] = isostamp.now()
    out.write_text(json.dumps({**meta, **res}))
    print(f"{res.get('result')} {res.get('abort') or ''} reads={res.get('reads')} elapsed={res.get('elapsed_s')} s {out}")
    lf.close()
    return 0 if res.get("result") == "ok" else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit")
    ap.add_argument("--pages", default="all")
    ap.add_argument("--no-block", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--bus", type=int)
    ap.add_argument("--wall-s", type=float, default=3600.0, help="wall bound (full probe ~5 reads x 3 ms x 65 k)")
    ap.add_argument("--isp", action="store_true", help="ISP path (F4/F5, MCU halted, reset at the end) instead of the debug slave; unit 3 only")
    ap.add_argument("--tsv", nargs="+", help="write re/regmap/read_behind.tsv from these probe JSON files")
    a = ap.parse_args()
    if a.tsv:
        write_tsv(a.tsv)
        return 0
    if a.isp:
        return main_isp(a)
    import dbg_link
    import rtd_i2c_bridge
    u = S.unit_info(a.unit)
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    out = Path(a.out) if a.out else ROOT / f"tmp/regs/live/{u['serial']}-behind-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = LOG.open("a")

    def log(s: str) -> None:
        lf.write(f"{isostamp.now()} u{a.unit}/behind {s}\n")

    meta = {"serial": u["serial"], "unit": a.unit, "bus": bus, "start": isostamp.now()}
    try:
        meta["link"] = dbg_link.on(bus, 60)
    except SystemExit as e:
        print(f"no link: {e}")
        return 1
    io = rtd_i2c_bridge.Real(bus, allow_write=False, regread=True)
    res: dict = {}
    try:
        hdr = X.read_bytes(io, S.DIAG_BASE, 3)
        meta["diag_header"] = hdr.hex() if hdr else None
        block = bool(hdr) and X.block_supported(hdr) and not a.no_block
        known = S.known_pages(ROOT)
        pages = S.parse_pages(a.pages, known)
        res = run_probe(io, pages, block, log, lambda r: out.write_text(json.dumps({**meta, **r, "partial": True})), a.wall_s)
    finally:
        io.close()
        meta["link_off"] = dbg_link.off(bus)
        lf.flush()
    meta["end"] = isostamp.now()
    out.write_text(json.dumps({**meta, **res}))
    print(f"{res.get('result')} {res.get('abort') or ''} reads={res.get('reads')} elapsed={res.get('elapsed_s')} s link off={meta['link_off']} {out}")
    lf.close()
    return 0 if res.get("result") == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
