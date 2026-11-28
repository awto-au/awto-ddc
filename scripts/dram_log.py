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
READ_ATTEMPTS = 3
RETRY_S = 0.005                    # only after an invalid / interrupted burst; never restart a full read


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


def _burst(read, units, valid, diagnostics=None, initial=None):
    """Bounded retries of one burst, including short transfers and checksum / identity failures."""
    for attempt in range(READ_ATTEMPTS):
        try:
            b = initial if attempt == 0 and initial is not None else read(units)
        except OSError:
            b = None
        if b is not None and len(b) == 16 and valid(b):
            return b
        if attempt + 1 < READ_ATTEMPTS:
            if diagnostics is not None:
                diagnostics["retries"] = diagnostics.get("retries", 0) + 1
            time.sleep(RETRY_S)
    return None


def header(read, diagnostics=None) -> dict | None:
    b = _burst(read, C["AWTO_DLOG_HDR_UNITS"],
               lambda b: b[:2] == HDR_ID and b[2] == HDR_VER and _sum(b) == b[15], diagnostics)
    if b is None:
        return None
    return {"gen": b[3], "boot": b[4], "hint": int.from_bytes(b[5:9], "big")}


def signed32(x: int) -> int:
    """fw ms of a line made before the Timer2 start is stored re-based below 0 (two's complement)"""
    return x - (1 << 32) if x >= 1 << 31 else x


def _entry_bytes(b, a, gen):
    return _sum(b) == b[15] and int.from_bytes(b[10:13], "big") == a & 0xFFFFFF and b[13] == gen


def entry(read, a: int, gen: int, diagnostics=None, *, initial=None) -> dict | None:
    """Validated copy of exactly index a; a failed read never substitutes a slot from another lap."""
    b = _burst(read, C["AWTO_DLOG_UNITS0"] + (a % C["AWTO_DLOG_SLOTS"]) * C["AWTO_DLOG_ENTRY_UNITS"],
               lambda b: _entry_bytes(b, a, gen), diagnostics, initial)
    if b is None:
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
    from ddr_note_read import port_wait_s

    lim = port_wait_s()

    def expired(op: str, u: int, t: float) -> None:
        if stats is not None:
            stats["expired"] = stats.get("expired", 0) + 1
        log(f"DDR read unit {u:#x}: {op} not seen in {lim * 1000:.1f} ms (limit), {(time.monotonic() - t) * 1000:.1f} ms elapsed: entry unread")

    def read_burst(u: int) -> bytes | None:
        t0 = time.monotonic()
        if stats is not None:
            stats["attempts"] = stats.get("attempts", 0) + 1
        try:
            while d.rd(r["AWTO_R_MCU_DC_CMD_A"]) & r["AWTO_F_MCU_DC_CMD_A_DDR_A_CMD"]:
                if time.monotonic() - t0 > lim:
                    expired("CMD idle", u, t0)
                    return None
            for reg, sh in (("AWTO_R_MCU_DC_ADDR_H_A", 24), ("AWTO_R_MCU_DC_ADDR_M_A", 16), ("AWTO_R_MCU_DC_ADDR_L_A", 8), ("AWTO_R_MCU_DC_ADDR_A", 0)):
                d.wr(r[reg], (u >> sh) & 0xFF)
            d.wr(r["AWTO_R_MCU_DC_CMD_A"], ndef("AWTO_DDRN_CMD_READ"))
            t1 = time.monotonic()
            while not d.rd(r["AWTO_R_MCU_DC_READ_FLAG_A"]) & ndef("AWTO_DDRN_READ_FLAG"):
                if time.monotonic() - t1 > lim:
                    expired("READ_FLAG", u, t1)
                    return None
            buf = d.block(r["AWTO_R_MCU_DC_DATABUF_R_00_A"], 16)                 # one block read, not 16 register reads (~3 debug-link transfers each)
        except OSError:
            return None
        if buf is None or len(buf) != 16:
            if stats is not None:
                stats["short"] = stats.get("short", 0) + 1
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
             wr: int | None = None, count: int | None = None, progress=None, since_gen: int | None = None,
             wr_identity: tuple | None = None) -> dict:
    """Copy a bounded index range, then validate its generation / boot. A hint advance is normal.

    Errors carry no publishable entries and never masquerade as an empty log. No whole-range
    retries: the caller retains its cursor and can retry later. `end` is the consumed page end;
    `next` is the ring boundary (these differ for a bounded follow page).
    """
    import datetime as dt
    diag = {"retries": 0}
    base = {"serial": serial, "read": read_at.isoformat(timespec="milliseconds"),
            "slots": C["AWTO_DLOG_SLOTS"], "entries": [], "diagnostics": diag}

    def failed(code, message, **extra):
        return {**base, "status": "error", "complete": False, "retryable": True,
                "error": {"code": code, "message": message}, **extra}

    h = header(read, diag)
    if h is None:
        return failed("header_unavailable", "DDR log header unreadable or invalid after bounded retries")
    identity = h["gen"], h["boot"]
    if wr_identity is not None and wr_identity != identity:
        fw_now = None                     # clock sample belongs to another boot / generation
    # The XDATA sample precedes the DDR header. Only use its optimization with matching
    # identity, a non-regressing index, and an actual entry at wr-1. A torn/stale XDATA
    # index may otherwise skip thousands of records. Never trust an unverified zero.
    reach = 2 * C["AWTO_DLOG_HINT_EVERY"] + 2
    if (wr is not None and wr > 0 and h["hint"] <= wr <= h["hint"] + reach and wr_identity == identity
            and entry(read, wr - 1, h["gen"], diag) is not None):
        nxt = wr
    else:
        nxt = h["hint"]
        for _ in range(reach):
            u = C["AWTO_DLOG_UNITS0"] + (nxt % C["AWTO_DLOG_SLOTS"]) * C["AWTO_DLOG_ENTRY_UNITS"]
            # An unreadable slot cannot establish the boundary. An unwritten slot
            # can have arbitrary bytes; validate/retry it before accepting the end.
            b = _burst(read, u, lambda b: True, diag)
            if b is None:
                return failed("boundary_unavailable", f"cannot establish DDR log boundary at index {nxt}")
            if not _entry_bytes(b, nxt, h["gen"]):
                # The unwritten end normally has no checksum at all. Retry this slot
                # before accepting the boundary; never advance a cursor past it.
                if entry(read, nxt, h["gen"], diag, initial=b) is None:
                    break
            nxt += 1
        else:
            return failed("hint_stale", "DDR log hint is beyond the bounded forward scan")
    reset = since_gen is not None and (since_gen != h["gen"] or (since is not None and since > nxt))
    if reset:
        since = 0                         # a new generation can reuse every absolute index
    amount = C["AWTO_DLOG_SLOTS"] if last is None or boot is not None else last
    bottom = max(0, nxt - C["AWTO_DLOG_SLOTS"])
    start = min(nxt, max(bottom, since if since is not None else nxt - amount, 0))
    end = min(nxt, since + count) if since is not None and count is not None else nxt
    end = max(start, end)
    ents, missing = [], []
    for a in range(start, end):
        e = entry(read, a, h["gen"], diag)
        if e is None:
            missing.append(a)
            break                          # a powered-down / failed port must not cost 3 attempts for every slot
        ents.append(e)
        if progress and (a - start + 1) % PROGRESS_N == 0:
            progress(a - start + 1, end - start)
    after = header(read, diag)
    if after is None:
        return failed("header_unavailable", "DDR log final header unreadable or invalid after bounded retries")
    if (after["gen"], after["boot"]) != identity or after["hint"] < h["hint"]:
        return failed("generation_changed", "DDR log generation, boot or index changed during read; retry with the saved cursor")
    diag["hint_advanced"] = after["hint"] != h["hint"]
    if missing:
        return failed("entries_unavailable", f"DDR log entry {missing[0]} unreadable, interrupted or overwritten; cursor retained",
                      missing=missing)
    if boot is not None:
        ents = [e for e in ents if e["boot"] == boot]
    lines = decode(rows, ents)
    out = []
    for e, ln in zip(ents, lines):
        poll = None
        if fw_now is not None and e["boot"] == h["boot"]:
            poll = (read_at - dt.timedelta(milliseconds=fw_now - signed32(e["ms"]))).isoformat(timespec="milliseconds")
        out.append({**e, "text": ln, "poll_wall": poll})
    gaps = [{"start": since, "end": bottom, "reason": "ring_overwritten"}] if since is not None and since < bottom else []
    return {**base, "status": "ok" if out else "empty", "complete": True, "gen": h["gen"], "boot": h["boot"],
            "next": nxt, "start": start, "end": end, "fw_now": fw_now, "entries": out, "gaps": gaps, "cursor_reset": reset}


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
    import datetime as dt
    snap = snapshot(rd, rows, None if a.all or a.boot is not None else a.last, a.boot, None, None, dt.datetime.now().astimezone())
    if not snap["complete"]:
        log("dram log: " + snap["error"]["message"])
        return 2
    log(f"dram log: gen {snap['gen']} boot {snap['boot']} next index {snap['next']}, {len(snap['entries'])} entries read, "
        f"{stats.get('bursts', 0)} bursts in {stats.get('s', 0):.1f} s; {snap['diagnostics']}")
    for ln in con_lines(rows, snap["entries"], snap["boot"]):
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
