#!/usr/bin/env python3
"""DRAM log (docs/dram-log-design.md): the sync ring's history in the DDR, read over the debug link or from the sim's DDR model.

usage: dram_log.py --unit N --bus B --map MAP [--last K | --boot N | --all] [--json]
  Reads the DDR header burst and the entries (16 B burst each, MCU_DC port A, as fw/log/hostnote.c) and prints the decoded lines
  per boot as the console: real time (uptime of that boot; host clock for the current boot when synced), +delta (32 bit, no wrap logic).
library: ddr_reader(dbg) -> read_burst(units) -> 16 B memory order; entry(read, abs, gen) -> dict | None;
         header(read) -> dict | None; newest(read, hdr) -> next absolute index; entries(read, hdr, nxt, count) -> [dict]
Log: ./tmp/logs/dram_log.log
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _log import log_line as _log_line
from _repo import ROOT

HDRH = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
LOG = ROOT / "tmp/logs/dram_log.log"
CHECK = 0x5A                      # fw/log/hostnote.c AWTO_DLOG_CHECK
HDR_ID, HDR_VER = b"DL", 1
POLL_S = 0.5                      # CMD idle / read flag: a burst is ~64 us on the MCU, one debug-link poll ~1 ms: 0.5 s = expiry is an error


def hdef(name: str) -> int:
    m = re.search(rf"^#define\s+{name}\s+\(?(0x[0-9A-Fa-f]+|\d+)", HDRH.read_text(), re.MULTILINE)
    if not m:
        raise SystemExit(f"{name} not in {HDRH.name}")
    return int(m.group(1), 0)


C = {n: hdef(n) for n in ("AWTO_DLOG_SLOTS", "AWTO_DLOG_UNITS0", "AWTO_DLOG_HDR_UNITS", "AWTO_DLOG_ENTRY_UNITS", "AWTO_DLOG_HINT_EVERY")} \
    if "AWTO_DLOG_SLOTS" in HDRH.read_text() else {}


def log(s: str) -> None:
    _log_line(s, LOG, stamp_stdout=False)


def _sum(b: bytes) -> int:
    x = CHECK
    for v in b[:15]:
        x ^= v
    return x


def header(read) -> dict | None:
    b = read(C["AWTO_DLOG_HDR_UNITS"])
    if b is None or b[:2] != HDR_ID or b[2] != HDR_VER or _sum(b) != b[15]:
        return None
    return {"gen": b[3], "boot": b[4], "hint": int.from_bytes(b[5:9], "big")}


def signed32(x: int) -> int:
    """fw ms of a line made before the Timer2 start is stored re-based below 0 (two's complement)"""
    return x - (1 << 32) if x >= 1 << 31 else x


def entry(read, a: int, gen: int) -> dict | None:
    """DDR entry with absolute index a of generation gen; None when the slot holds something else (or the read failed)"""
    b = read(C["AWTO_DLOG_UNITS0"] + (a % C["AWTO_DLOG_SLOTS"]) * C["AWTO_DLOG_ENTRY_UNITS"])
    if b is None or _sum(b) != b[15] or int.from_bytes(b[10:13], "big") != a & 0xFFFFFF or b[13] != gen:
        return None
    return {"abs": a, "id": b[0], "arg": b[1], "ms": int.from_bytes(b[2:6], "big"), "val": int.from_bytes(b[6:10], "big"), "boot": b[14]}


def newest(read, hdr: dict, ahead: int | None = None) -> int:
    """index of the next entry to be written: scan forward from the header hint over slots that carry the expected index"""
    a = hdr["hint"]
    for _ in range(ahead or 2 * C["AWTO_DLOG_HINT_EVERY"] + 2):
        if entry(read, a, hdr["gen"]) is None:
            break
        a += 1
    return a


PROGRESS_N = 100                  # entries between progress lines: ~1.3 s at the measured 77.7 entries/s (unit 3, 2026-11-27), a reader's stall guard sees them


def entries(read, hdr: dict, nxt: int, count: int, first: int | None = None, progress=None) -> list[dict]:
    """the newest `count` entries (oldest first), or `count` from abs index `first` on; fewer when the ring is young or an older slot
    no longer validates. progress(done, total): every PROGRESS_N entries"""
    a0 = max(0, nxt - min(count, C["AWTO_DLOG_SLOTS"])) if first is None else max(first, nxt - C["AWTO_DLOG_SLOTS"], 0)
    a1 = nxt if first is None else min(nxt, a0 + count)
    out = []
    for a in range(a0, a1):
        e = entry(read, a, hdr["gen"])
        if e is not None:
            out.append(e)
        if progress and (a - a0 + 1) % PROGRESS_N == 0:
            progress(a - a0 + 1, a1 - a0)
    return out


def ddr_reader(d, r: dict, stats: dict | None = None):
    """read_burst(units) over a Dbg-like object (rd / wr / block); the port registers `r` from AwtoRegs.h. A failed read returns None"""
    from ddr_note_read import hdef as ndef

    def read_burst(u: int) -> bytes | None:
        t0 = time.monotonic()
        try:
            while d.rd(r["AWTO_R_MCU_DC_CMD_A"]) & r["AWTO_F_MCU_DC_CMD_A_DDR_A_CMD"]:
                if time.monotonic() - t0 > POLL_S:
                    return None
            for reg, sh in (("AWTO_R_MCU_DC_ADDR_H_A", 24), ("AWTO_R_MCU_DC_ADDR_M_A", 16), ("AWTO_R_MCU_DC_ADDR_L_A", 8), ("AWTO_R_MCU_DC_ADDR_A", 0)):
                d.wr(r[reg], (u >> sh) & 0xFF)
            d.wr(r["AWTO_R_MCU_DC_CMD_A"], ndef("AWTO_DDRN_CMD_READ"))
            t1 = time.monotonic()
            while not d.rd(r["AWTO_R_MCU_DC_READ_FLAG_A"]) & ndef("AWTO_DDRN_READ_FLAG"):
                if time.monotonic() - t1 > POLL_S:
                    return None
            buf = d.block(r["AWTO_R_MCU_DC_DATABUF_R_00_A"], 16)                 # one block read, not 16 register reads (~3 debug-link transfers each)
        except OSError:
            return None
        if stats is not None:
            stats["bursts"] = stats.get("bursts", 0) + 1
            stats["s"] = stats.get("s", 0.0) + time.monotonic() - t0
        half = ndef("AWTO_DDRN_HALF")
        return bytes(buf[(j + half) % 16] for j in range(16))

    return read_burst


def decode(rows: list[dict], ents: list[dict]) -> list[str]:
    """one decoded line per entry, oldest first: `ms since boot` + sync_log.line's text; the episode time of `sync DONE` etc. is relative to the
    episode start (the BEGIN entry, 0 for a power-on episode) as on the console"""
    import sync_log as S
    out, t0, boot = [], 0, None
    for e in ents:
        if e["boot"] != boot:
            boot, t0 = e["boot"], 0
        if e["id"] == 0xC0:                                  # AWTO_SYNC_EV_BEGIN: arg = kind (1 power on: the episode prints ms since reset)
            t0 = 0 if e["arg"] == 1 else e["ms"]
        v = e["val"]
        ln = S.line(rows, (e["id"], e["arg"], e["ms"] & 0xFFFF, ((S.NOTE_DDR(v) if S.NOTE_DDR else None) or "text overwritten") if e["id"] == S.NOTE_EV else v), t0 & 0xFFFF)
        ms = e["ms"] - (1 << 32 if e["ms"] >= 1 << 31 else 0)          # lines made before the Timer2 start are re-based: a few ms below 0
        out.append(f"{ms / 1000:9.3f}s:{ln.split(':', 1)[1]}")
    return out


def snapshot(read, rows: list[dict], last: int | None, boot: int | None, serial: str | None, fw_now: int | None, read_at, since: int | None = None,
             wr: int | None = None, count: int | None = None, progress=None) -> dict | None:
    """machine form (unit_log.py): header, the entries asked for with abs index, boot, fw ms, text, host time of the read for the current boot.
    since + count: a page of `count` entries from abs index since (a history view); since alone: everything after it (the saver)"""
    import datetime as dt
    h = header(read)
    if h is None:
        return None
    # wr = the firmware's write index from its XDATA header (one block read): saves the forward scan from the header hint (up to 130 bursts)
    nxt = wr if wr is not None and (wr == 0 or entry(read, wr - 1, h["gen"]) is not None) else newest(read, h)
    page = count
    count = C["AWTO_DLOG_SLOTS"] if (last is None or boot is not None) else last
    if since is not None and page is not None:              # one page of the history
        ents = entries(read, h, nxt, page, since, progress)
    else:
        if since is not None:                                # the saver: only what came after the last entry it has
            count = max(0, nxt - since)
        ents = entries(read, h, nxt, count, None, progress)
    if boot is not None:
        ents = [e for e in ents if e["boot"] == boot]
    lines = decode(rows, ents)
    out = []
    for e, ln in zip(ents, lines):
        poll = None
        if fw_now is not None and e["boot"] == h["boot"]:
            poll = (read_at - dt.timedelta(milliseconds=fw_now - signed32(e["ms"]))).isoformat(timespec="milliseconds")   # before Timer2: < 0
        out.append({"abs": e["abs"], "boot": e["boot"], "ms": e["ms"], "id": e["id"], "arg": e["arg"], "val": e["val"], "text": ln, "poll_wall": poll})
    return {"serial": serial, "read": read_at.isoformat(timespec="milliseconds"), "gen": h["gen"], "boot": h["boot"], "next": nxt, "fw_now": fw_now,
            "slots": C["AWTO_DLOG_SLOTS"], "entries": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--map", type=Path, required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, default=64)
    g.add_argument("--all", action="store_true")
    g.add_argument("--boot", type=int, help="only the entries of this boot counter value (newest boot = header boot)")
    a = ap.parse_args()
    import ddr_frame_test as T
    import ddr_note_read as DN
    import sync_log as S

    d = T.Dbg(a.unit, a.bus)
    stats: dict = {}
    rd = ddr_reader(d, DN.regs(), stats)
    rows = S.load_rows(a.tsv if hasattr(a, "tsv") and a.tsv else S.tsv_for(a.map))
    h = header(rd)
    if h is None:
        log("dram log: no valid DDR header (an image without the DRAM log, or a cold power-up)")
        return 2
    nxt = newest(rd, h)
    count = C["AWTO_DLOG_SLOTS"] if (a.all or a.boot is not None) else a.last
    ents = entries(rd, h, nxt, count)
    if a.boot is not None:
        ents = [e for e in ents if e["boot"] == a.boot]
    log(f"dram log: gen {h['gen']} boot {h['boot']} next index {nxt} (wraps {nxt // C['AWTO_DLOG_SLOTS']}), {len(ents)} entries read, "
        f"{stats.get('bursts', 0)} bursts in {stats.get('s', 0):.1f} s")
    for ln in con_lines(rows, ents, h["boot"]):
        log(ln)
    return 0


def con_lines(rows: list[dict], ents: list[dict], cur_boot: int, ht: dict | None = None, boot_base: int | None = None) -> list[str]:
    """entries as the console shows them (sync_log.con_rows: real time, +delta, joined groups), "--- boot N" per boot, abs index first.
    boot_base: g_usAwtoBootBase of the current boot (its zero when its Timer2 start line is not among ents)"""
    import sync_log as S
    evs = [(e["id"], e["arg"], e["ms"] & 0xFFFF, e["val"]) for e in ents]
    ts = [(S.signed32(e["ms"]), True) for e in ents]
    lines = [e["text"] for e in ents] if all("text" in e for e in ents) else decode(rows, ents)   # snapshot texts: decoded while the link was open
    rs = S.con_rows(evs, [x.split(":", 1)[1] for x in lines], ts, ht, [e["boot"] for e in ents], cur_boot, boot_base=boot_base)
    out, boot = [], None
    for r, ln in zip(rs, S.row_lines(rs, ts, evs)):        # 32-bit times: no wrap row, one line per row
        e = ents[r["i"][0]]
        if e["boot"] != boot:
            boot = e["boot"]
            out.append(f"--- boot {boot}")
        out.append(f"  {e['abs']:6d} {ln}")
    return out


if __name__ == "__main__":
    sys.exit(main())
