#!/usr/bin/env python3
"""Stale-first-read rate on the read-behind pages (awto-ddc read-behind, re/regmap/README.md "Read-behind").

usage: rb_stale_probe.py --unit N [--label TEXT]      (debug link on, read-only reads, link off after)
  Per page: truth of 64 dword candidates (read 4x, last 3 equal), then a walk over up to RB_SEQ dwords of distinct value;
  every step = read A (first read of a new dword) then read A again. stale = first != repeat; eligible = the previous
  dword's value differs, so a stale read is visible. Raw image: the debug-slave ISR read is raw; helper image: primed.
  Also used per step by clk_sweep.py --rb-probe. Log: tmp/logs/rb_stale_probe.log
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/rb_stale_probe.log"
PAGES = (0xA0, 0xA3, 0xA4, 0xA8, 0xAB, 0x88, 0x8E, 0x8F, 0xC8, 0xCE, 0xCF)   # read-behind pages with stable registers (re/regmap/read_behind.tsv)
CAND = range(0, 0x100, 4)             # candidate dword offsets per page (lane 0)
REPS = 40                             # passes over the walk
SEQ = 6                               # dwords per walk: every read is the first read of a new dword


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def rd(io, addr: int):
    """One raw single-byte read over the debug slave (no double read: the point is the first read)."""
    import dbg_xdata as X
    if not (io.write(X.DEV8, X.CMD_HI, bytes([addr >> 8])) and io.write(X.DEV8, X.CMD_READ, bytes([addr & 0xFF]))):
        return None
    r = io.read(X.DEV8, X.READ_SUB, 1)
    return r[0] if r else None


def probe(io, name: str, res: dict, log=say) -> None:
    tot_el = tot_st = tot_bad = 0
    per = []
    for pg in PAGES:
        truth = {}
        for off in CAND:
            a = (pg << 8) | off
            rd(io, a)
            v1, v2, v3 = rd(io, a), rd(io, a), rd(io, a)
            if v1 is not None and v1 == v2 == v3:
                truth[a] = v2
        seq = []
        for a, v in truth.items():
            if all(truth[x] != v for x in seq):
                seq.append(a)
            if len(seq) >= SEQ:
                break
        if len(seq) < 2:
            per.append(f"{pg:02X}:n/a")
            continue
        el = st = bad = 0
        prev = seq[-1]
        for _ in range(REPS):
            for a in seq:
                v1 = rd(io, a)
                v2 = rd(io, a)
                if v1 is None or v2 is None or v2 != truth[a]:
                    bad += 1
                elif truth[prev] != truth[a]:
                    el += 1
                    st += v1 != v2
                prev = a
        tot_el, tot_st, tot_bad = tot_el + el, tot_st + st, tot_bad + bad
        per.append(f"{pg:02X}:{st}/{el}")
    log(f"  info read-behind {name}: stale first reads {tot_st} of {tot_el} eligible ({tot_bad} unusable); per page stale/eligible {' '.join(per)}")
    res.update(rb_stale=tot_st, rb_elig=tot_el, rb_bad=tot_bad)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit")
    ap.add_argument("--bus", type=int)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    import dbg_link
    import reg_live_scan as S
    import rtd_i2c_bridge
    u = S.unit_info(a.unit)
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    try:
        dbg_link.on(bus, 60)
    except SystemExit as e:
        say(f"no link: {e}")
        return 1
    io = rtd_i2c_bridge.Real(bus, allow_write=False, regread=True)
    res: dict = {}
    try:
        probe(io, a.label or u["serial"], res)
    finally:
        io.close()
        dbg_link.off(bus)
    say(f"RESULT {a.label} stale {res.get('rb_stale')} of {res.get('rb_elig')} unusable {res.get('rb_bad')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
