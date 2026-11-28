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
PUBLICATION_MASK = (1 << 24) - 1
PUBLICATION_HALF = 1 << 23
HEADER_CRC_POLY = 0x1021
HEADER_CRC_INIT = 0xFFFF
ATTEMPTS = 3
RETRY_S = 0.01


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


class ReadError(OSError):
    """A bounded read could not establish a log boundary; never means cold boot."""


def _record(diag, key):
    if diag is not None:
        diag[key] = diag.get(key, 0) + 1


def _burst(read, unit):
    try:
        b = read(unit)
    except OSError:
        b = None
    return bytes(b) if b is not None and len(b) == 16 else None


def _header_crc(b):
    crc = HEADER_CRC_INIT
    for byte in b[:14]:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (HEADER_CRC_POLY if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def _header(b):
    if b is None or b[:2] != HDR_ID or b[2] not in (1, 2) or b[3] == 0:
        return None
    if (b[2] == 1 and _sum(b) != b[15]) or (b[2] == 2 and _header_crc(b) != int.from_bytes(b[14:16], "big")):
        return None
    h = {"gen": b[3], "boot": b[4], "hint": int.from_bytes(b[5:9], "big")}
    if b[2] == 2:
        h["publication"] = int.from_bytes(b[11:14], "big")
    return h


def header(read, diag=None) -> dict | None:
    """Bounded v1 retries; v2 selects the newest checksummed alternating copy.

    A valid primary v1 wins over v2 shadow (firmware downgrade). No read failure
    proves a cold boot. Callers can inspect diag['header_status'] on failure.
    """
    seen = []
    for attempt in range(ATTEMPTS):
        primary = _burst(read, C["AWTO_DLOG_HDR_UNITS"])
        h = _header(primary)
        if h is not None and "publication" not in h:
            if diag is not None:
                diag["header_status"] = "ok"
            return h
        shadow = _burst(read, C["AWTO_DLOG_HDR_UNITS"] - C["AWTO_DLOG_ENTRY_UNITS"])
        other = _header(shadow)
        if other is not None and "publication" not in other:
            other = None                       # only v2 is defined in the shadow slot
        if other is not None and (h is None or 0 < ((other["publication"] - h["publication"]) & PUBLICATION_MASK) < PUBLICATION_HALF):
            h = other
        if h is not None:
            if diag is not None:
                diag["header_status"] = "ok"
            if primary is None or _header(primary) is None:
                _record(diag, "header_fallbacks")
            return h
        seen.append((primary, shadow))
        _record(diag, "header_retries")
        if attempt + 1 < ATTEMPTS:
            time.sleep(RETRY_S)
    if diag is not None:
        # Stable blank DDR is absence, not evidence of its cause (power, init, image).
        blank = all(x in (bytes(16), bytes([255]) * 16) for pair in seen for x in pair)
        diag["header_status"] = ("absent" if blank else "io_failure" if any(x is None for pair in seen for x in pair)
                                 else "invalid" if len(set(seen)) == 1 else "transient_checksum")
    return None


def signed32(x: int) -> int:
    """fw ms of a line made before the Timer2 start is stored re-based below 0 (two's complement)"""
    return x - (1 << 32) if x >= 1 << 31 else x


def _entry(read, a, gen, diag=None):
    unit = C["AWTO_DLOG_UNITS0"] + (a % C["AWTO_DLOG_SLOTS"]) * C["AWTO_DLOG_ENTRY_UNITS"]
    reason = "io_failure"
    samples = []
    for attempt in range(ATTEMPTS):
        b = _burst(read, unit)
        samples.append(b)
        if b is None:
            reason = "io_failure"
        elif b in (bytes(16), bytes([255]) * 16):
            return None, "empty"
        elif _sum(b) != b[15]:
            reason = "checksum"
        elif b[13] != gen:
            reason = "generation"
        elif int.from_bytes(b[10:13], "big") != a & 0xFFFFFF:
            slot_index = int.from_bytes(b[10:13], "big")
            delta = (slot_index - a) & 0xFFFFFF
            reason = "overwritten" if 0 < delta < (1 << 23) else "index"
        else:
            return {"abs": a, "id": b[0], "arg": b[1], "ms": int.from_bytes(b[2:6], "big"),
                    "val": int.from_bytes(b[6:10], "big"), "boot": b[14]}, None
        # A different index / generation is a legitimate boundary, not a burst error.
        if reason in ("generation", "index", "overwritten"):
            return None, reason
        _record(diag, "entry_retries")
        if attempt + 1 < ATTEMPTS:
            time.sleep(RETRY_S)
    if reason == "checksum" and len(set(samples)) == 1 and b is not None and (
            b[13] != gen or int.from_bytes(b[10:13], "big") != a & 0xFFFFFF):
        return None, "uninitialized"
    return None, reason


def entry(read, a: int, gen: int) -> dict | None:
    """Compatible entry API, with bounded retries for transport / checksum failures."""
    return _entry(read, a, gen)[0]


def newest(read, hdr: dict, ahead: int | None = None, diag=None) -> int:
    """Find a fixed end boundary. An unread burst must never shorten the history."""
    a = hdr["hint"]
    for _ in range(ahead or 2 * C["AWTO_DLOG_HINT_EVERY"] + 2):
        e, reason = _entry(read, a, hdr["gen"], diag)
        if e is None:
            if reason in ("io_failure", "checksum", "overwritten"):
                raise ReadError(f"newest entry {a}: {reason}; boundary unknown")
            break
        a += 1
    else:
        if diag is not None:
            diag["scan_limit"] = True
    return a


PROGRESS_N = 100                  # entries between progress lines: ~1.3 s at the measured 77.7 entries/s (unit 3, 2026-11-27), a reader's stall guard sees them


def entries(read, hdr: dict, nxt: int, count: int, first: int | None = None, progress=None, diag=None) -> list[dict]:
    """the newest `count` entries (oldest first), or `count` from abs index `first` on; fewer when the ring is young or an older slot
    no longer validates. progress(done, total): every PROGRESS_N entries"""
    a0 = max(0, nxt - min(count, C["AWTO_DLOG_SLOTS"])) if first is None else max(first, nxt - C["AWTO_DLOG_SLOTS"], 0)
    a1 = nxt if first is None else min(nxt, max(first, 0) + count)
    out = []
    for a in range(a0, a1):
        e, reason = _entry(read, a, hdr["gen"], diag)
        if e is not None:
            out.append(e)
        elif diag is not None:
            missing = diag.setdefault("missing", [])
            if missing and missing[-1]["end"] == a and missing[-1]["reason"] == reason:
                missing[-1]["end"] = a + 1
            else:
                missing.append({"first": a, "end": a + 1, "reason": reason})
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
             wr: int | None = None, count: int | None = None, progress=None, expected_gen: int | None = None, clock_identity: tuple[int, int] | None = None) -> dict:
    """machine form (unit_log.py): header, the entries asked for with abs index, boot, fw ms, text, host time of the read for the current boot.
    since + count: a page of `count` entries from abs index since (a history view); since alone: everything after it (the saver)"""
    import datetime as dt
    diag = {}
    h = header(read, diag)
    base = {"serial": serial, "read": read_at.isoformat(timespec="milliseconds"), "slots": C["AWTO_DLOG_SLOTS"],
            "entries": [], "diagnostics": diag, "status": "unavailable", "next": None}
    if h is None:
        return base
    base.update(gen=h["gen"], boot=h["boot"])
    if clock_identity is not None and clock_identity != (h["gen"], h["boot"]):
        fw_now, wr = None, None
        diag["clock_identity_changed"] = True
    # Never trust XDATA wr=0: it may precede initialization while DDR still holds history.
    try:
        nxt = wr if wr is not None and wr > h["hint"] and entry(read, wr - 1, h["gen"]) is not None else newest(read, h, diag=diag)
    except ReadError as exc:
        diag["boundary_error"] = str(exc)
        return base
    if diag.get("scan_limit"):
        diag["boundary_error"] = "header hint scan limit reached; boundary unknown"
        return base
    if since is not None and (expected_gen is not None and expected_gen != h["gen"] or since > nxt):
        diag["cursor_reset"] = True
        since = 0
    page = count
    count = C["AWTO_DLOG_SLOTS"] if (last is None or boot is not None) else last
    if since is not None and page is not None:
        ents = entries(read, h, nxt, page, since, progress, diag)
    else:
        if since is not None:
            count = max(0, nxt - since)
        ents = entries(read, h, nxt, count, None, progress, diag)
    # Only identity changes invalidate the generation. Normal hint / publication
    # changes never restart a minutes-long read. Keep all validated old entries.
    end = header(read, diag)
    status = "ok"
    if end is None:
        status = "unverified"
    elif end["gen"] != h["gen"]:
        status = "generation_changed"
    elif end["boot"] != h["boot"]:
        status = "boot_changed"
    if status != "ok":
        fw_now = None                            # clock association no longer proved
    if end is not None and end["gen"] == h["gen"]:
        for m in diag.get("missing", []):
            if m["end"] <= end["hint"] - C["AWTO_DLOG_SLOTS"]:
                m["reason"] = "overwritten"
    if diag.get("missing") and status == "ok":
        status = "partial"
    if boot is not None:
        ents = [e for e in ents if e["boot"] == boot]
    # Revisit holes on a subsequent poll, deduplicating already saved later rows.
    retry_from = min((m["first"] for m in diag.get("missing", []) if m["reason"] in ("io_failure", "checksum")), default=nxt)
    if since is not None and page is not None:
        retry_from = min(retry_from, min(nxt, since + page))
    lines = decode(rows, ents)
    out = []
    for e, ln in zip(ents, lines):
        poll = None
        if fw_now is not None and e["boot"] == h["boot"]:
            poll = (read_at - dt.timedelta(milliseconds=fw_now - signed32(e["ms"]))).isoformat(timespec="milliseconds")   # before Timer2: < 0
        out.append({"abs": e["abs"], "boot": e["boot"], "ms": e["ms"], "id": e["id"], "arg": e["arg"], "val": e["val"], "text": ln, "poll_wall": poll})
    return {"serial": serial, "read": read_at.isoformat(timespec="milliseconds"), "gen": h["gen"], "boot": h["boot"], "next": nxt, "fw_now": fw_now,
            "slots": C["AWTO_DLOG_SLOTS"], "entries": out, "status": status, "diagnostics": diag, "resume": retry_from}


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
    log(f"dram log: {snap['status']}; diagnostics {snap['diagnostics']}")
    if snap["status"] == "unavailable":
        return 2
    log(f"dram log: gen {snap['gen']} boot {snap['boot']} next index {snap['next']}, {len(snap['entries'])} entries read")
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
