#!/usr/bin/env python3
"""Decode the #139 sync / power-on log ring (firmware g_stAwtoSync) into the same lines the monitor shows.

usage: sync_log.py BUS --map MAP [--tsv TSV] [--serial SERIAL]      read over the debug slave 0x35 and print the episode
       (library) decode(raw, rows) -> (header dict, [lines]); load_rows(tsv); tsv_for(map)
- Texts and value formats: the firmware tree's fw/awto/sync.tsv (one file for screen and host; the console wraps a long line
  to a second row, the host prints it on one). Default TSV = the image's
  <map stem>.sync.tsv (dev.py build copies it beside the image), else $AWTO_SYNC_TSV.
- Ring layout (RL6449_Project.h StAwtoSync, bytes only): 14 B header, N x 8 B entries {id, arg, ms hi, ms lo, value BE x4}.
  Header byte 12 = N, byte 13 = seq wrap: read the header, then N x 8 B (read_ring); nothing is hardcoded here.
- Host time (#157): images with isr_g_stAwtoHt print every line with its host ISO 8601 time, from the latest DDC/CI time sync
  (scripts/host_time.py). Ring ms are 16 bit: unwrapped forward from anchors (episode start C0 carries fw ms bits 31..16,
  host-sync line D8 the full fw ms); `~` = forward and back-from-now disagree (a gap of 65.5 s or more hid a wrap).
Log: tmp/logs/sync_log.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import isostamp
import sync_classes

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/sync_log.log"
NOTE_EV = 0xEE                            # RL6449_Project.h AWTO_SYNC_EV_NOTE: arg = length, value = note sequence (#273)
HDR, EV = 14, 8                           # header bytes, bytes per entry; N = header[12], seq wrap = header[13]
D0 = 3                                                   # _D0_INPUT_PORT
SRC = {2: "DVI", 3: "HDMI", 4: "DP"}
DP_RATE = {0x06: "RBR", 0x0A: "HBR", 0x14: "HBR2", 0x1E: "HBR3"}
KINDS = {1: "power on", 2: "switch", 3: "wake", 4: "power key on"}
SYMBOLIZE = None                                         # set_map(): (bank, pc) -> "fn+0x.." for the pc fmt


def set_map(map_path: Path) -> None:
    """symbols for the pc fmt (boot reason line); rtd_crash's map reader"""
    global SYMBOLIZE
    import rtd_crash as C
    syms = C.load_syms(Path(map_path).read_text(errors="replace"))
    SYMBOLIZE = lambda bank, pc: C.symbolize(syms, bank, pc)


def log(s: str, shown: str | None = None):
    """s -> console + log file; shown = the console copy (class colour on a TTY), the file always gets the plain s"""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line if shown is None else f"{isostamp.now()} {shown}", flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def load_rows(tsv: Path) -> list[dict]:
    out = []
    for ln in tsv.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        i, a, f, t, *c = ln.split("\t")                  # optional 5th column: colour class (fw/awto/sync_classes.tsv)
        port = f.startswith("port")
        out.append(dict(id=int(i, 16), arg=None if a == "*" else int(a, 16), port=port, fmt=f[4:] if port else f, text=t,
                        cls=sync_classes.check(c[0] if c else "")))
    return out


def tsv_for(map_path: Path) -> Path:
    p = map_path.with_suffix(".sync.tsv")
    if p.exists():
        return p
    env = os.environ.get("AWTO_SYNC_TSV")
    if env:
        return Path(env)
    raise SystemExit(f"no sync.tsv beside {map_path} and no $AWTO_SYNC_TSV")


def milli(v: int) -> str:
    return f"{v // 1000}.{v % 1000:03d}"


def tenths(v: int) -> str:
    return f"{v // 10}.{v % 10}"


def value(fmt: str, arg: int, v: int) -> str:
    if fmt == "vport":
        return "auto" if (v & 0xFF) == 0xFF else f"D{(v & 0xFF) - D0}"
    if fmt == "res":
        return f"{v >> 16}x{v & 0xFFFF}"
    if fmt == "mhz1":
        return tenths(v) + "MHz"
    if fmt == "hz1":
        return tenths(v) + "Hz"
    if fmt == "hz3":
        return milli(v) + "Hz"
    if fmt == "mhz3":
        return milli(v) + "MHz"
    if fmt == "dp":
        r = (v >> 8) & 0xFF
        return f"{DP_RATE.get(r, f'{r:02X}')} x{v & 0xFF}"
    if fmt == "src":
        return SRC.get(v, str(v))
    if fmt == "pms":                                     # #139 value = port << 16 | ms: "D2, 188ms"
        return f"D{((v >> 16) & 0xFF) - D0}, {v & 0xFFFF}ms"
    if fmt == "psrc":                                    # value = port << 8 | source type: "D2 HDMI"
        return f"D{((v >> 8) & 0xFF) - D0} {SRC.get(v & 0xFF, str(v & 0xFF))}"
    if fmt == "lim":                                     # value = width << 16 | limit
        return f"{(v >> 16) & 0xFFFF} of {v & 0xFFFF} px"
    if fmt == "rms":                                     # value = register / argument << 16 | ms: "71A4 40ms"
        return f"{(v >> 16) & 0xFFFF:04X} {v & 0xFFFF}ms"
    if fmt == "harg":
        return f"{arg:02X}"
    if fmt == "ms":                                      # #150 NVRAM save timing
        return f"{v}ms"
    if fmt == "wdt":                                     # #162 watchdog run-time:warning ms << 16 | reset ms
        return f"warning {v >> 16}ms, reset {v & 0xFFFF}ms"
    if fmt == "n":                                       # #150 collapsed repeats
        return str(v)
    if fmt == "x":                                       # #150 wake-poll state (cable 2:0, EDID 5:3, AUX 6, DPCD 7, polls 23:8, TMDS 25:24)
        return (f"0x{v:06X}: polls {(v >> 8) & 0xFFFF}, cable {v & 7:03b}, EDID {(v >> 3) & 7:03b}, AUX {(v >> 6) & 1}, "
                f"DPCD D0 {(v >> 7) & 1}, TMDS D3D2 {(v >> 24) & 3:02b}")
    if fmt == "htime":                                   # #157 host unix s, arg = UTC offset (15 min, signed)
        return iso(v, arg - 256 if arg >= 128 else arg)
    if fmt == "sms":                                     # #157 signed ms
        return f"{v - (1 << 32) if v >= 1 << 31 else v:+d}ms"
    if fmt == "mon":                                     # fw/diag/monitor.c: arg 1 ADC, 2 IOSC trim, 3 loop + watchdog gap, 4 uptime + stack
        return mon_text(arg, v)
    if fmt == "nvw":                                     # #151 NVRAM flush result
        return nv_flush(v)
    if fmt == "cec":                                     # docs/cec.md (firmware copy: fw/osd/console.c AwtoPutCec)
        return cec_line(arg, v)
    if fmt == "pc":                                      # #29 boot reason: cause << 24 | bank << 16 | PC
        c, bank, pc = v >> 24, (v >> 16) & 0xFF, v & 0xFFFF
        where = f"{bank:02X}:{pc:04X}" if pc >= 0x5000 else f"C:{pc:04X}"
        sym = SYMBOLIZE(bank, pc) if SYMBOLIZE else ""
        return ("STALL TEST" if c & 0x80 else "STALL") + f", PC {where}" + (f" {sym}" if sym else "")
    return ""


CEC_NAMES = {int(ln.split("\t")[0], 16): ln.split("\t")[1] for ln in
             (Path(__file__).resolve().parents[1] / "fw/cec/opcodes.tsv").read_text().splitlines() if ln.strip() and not ln.startswith("#")}
CEC_TXRES = {1: "acked", 2: "line error", 3: "no ack (header)", 4: "no ack (data)"}
CEC_HOOKS = {1: "Standby", 2: "wake", 3: "Active Source", 4: "User Control"}


def cec_line(arg: int, v: int) -> str:
    """arg = flags | len << 3 | kind (RL6449_Project.h AWTO_CEC_*), v = header << 24 | opcode << 16 | operand 1 << 8 | operand 2"""
    kind, n = arg & 7, (arg >> 3) & 15
    if kind == 2:
        return "tx result:" + CEC_TXRES.get(v & 0xFF, "line error")
    if kind == 3:
        return "block on" if v & 0xFF else "block off"
    if kind == 4:
        return f"hook:{CEC_HOOKS.get(v & 0xFF, v & 0xFF)} (no action)"
    if kind == 5:
        return "rx reply dropped, the last reply is not sent"
    hdr = (v >> 24) & 0xFF
    dest = "?" if arg & 0x80 else f"{hdr & 15:X}"
    head = f"{'rx' if kind == 0 else 'tx'} {hdr >> 4:X}>{dest} "
    if n == 0:
        return head + "poll"
    op = (v >> 16) & 0xFF
    ops = [(v >> 8) & 0xFF, v & 0xFF][:max(0, min(n - 1, 2))]
    return head + CEC_NAMES.get(op, f"op {op:02X}") + "".join(f" {b:02X}" for b in ops) + ("+" if n > 3 else "")


def mon_text(arg: int, v: int) -> str:
    """health monitor rows (firmware copy: fw/osd/console.c case 23); the watchdog gap is already in ms"""
    if arg == 1:
        return f"ADC A0 {v >> 24:02X} A1 {(v >> 16) & 0xFF:02X} A2 {(v >> 8) & 0xFF:02X} A3 {v & 0xFF:02X}"
    if arg == 2:
        return f"IOSC trim count {v}"
    if arg == 3:
        return f"main loop {v >> 16} passes/s, longest watchdog gap {v & 0xFFFF}ms"
    if arg == 5:
        return f"headroom {v & 0xFFF} passes/s, busy {v >> 24} %, worst pass {(((v >> 12) & 0xFFF) * 1000 // 16) / 1000:.3f}ms"
    if arg == 4:
        return f"uptime {v >> 8} s, stack high {v & 0xFF:02X}"
    return f"{arg:02X} {v:08X}"


NV_GROUPS = ("system data", "OSD data", "colour", "panel time", "awto settings")    # RL6449_Project.h AWTO_NV_LOG_G_* bits 0..4


def nv_flush(v: int) -> str:
    """#151 fmt nvw (firmware copy: fw/osd/console.c AwtoPutNvFlush): groups << 27 | erases << 25 | programs << 19 |
    bytes << 9 | ms; each field saturates at its max ("+")"""
    def f(x, mx):
        return f"{x}+" if x >= mx else str(x)
    ms, by, pr, er, g = v & 0x1FF, (v >> 9) & 0x3FF, (v >> 19) & 0x3F, (v >> 25) & 3, v >> 27
    if v >> 19 == 0:
        return f"nothing changed, no flash write ({f(ms, 0x1FF)}ms)"
    grp = ", ".join(n for k, n in enumerate(NV_GROUPS) if g >> k & 1)
    return (f"wrote {f(by, 0x3FF)}B" + (f" ({grp})" if grp else "") + f" in {f(pr, 0x3F)} program{'' if pr == 1 else 's'}, "
            f"{f(er, 3)} erase{'' if er == 1 else 's'}, {f(ms, 0x1FF)}ms")


def iso(t: float, ofs15: int, ms: bool = False) -> str:
    tz = dt.timezone(dt.timedelta(minutes=15 * ofs15))
    return dt.datetime.fromtimestamp(t, tz).isoformat(timespec="milliseconds" if ms else "seconds")


# ---- #157 host time: isr_g_stAwtoHt (RL6449_Project.h StAwtoHt, BE words) ----------------------------------------------------
HT_SIZE = 16
DIAG_T2 = 0x16                                           # StAwtoDiag.usT2Isr (docs/diag-block.md)


def ht_decode(b: bytes) -> dict:
    return dict(syncs=b[0], ofs=b[1] - 256 if b[1] >= 128 else b[1], frac=int.from_bytes(b[2:4], "big"),
                epoch=int.from_bytes(b[4:8], "big"), fw=int.from_bytes(b[8:12], "big"),
                drift=int.from_bytes(b[12:14], "big", signed=True), up_hi=int.from_bytes(b[14:16], "big"))


def fw_now(ht: dict, t2: int) -> int:
    """32-bit fw ms now: high word bumped by the Timer2 ISR (AwtoMs) + a usT2Isr read after the struct"""
    return (ht["up_hi"] << 16) | t2


def host_time(ht: dict, fw32: int) -> str:
    """fw ms -> host ISO 8601 from the latest sync pair (offset of that sync)"""
    return iso(ht["epoch"] + (ht["frac"] + fw32 - ht["fw"]) / 1000.0, ht["ofs"], ms=True)


def step(a: int, b: int) -> int:
    """ms from 16-bit time a to b: forward, except a step back of < 256 ms (lines re-based at the Timer2 start, #29)"""
    d = (b - a) & 0xFFFF
    return d - 0x10000 if d >= 0xFF00 else d


def unwrap(evs: list, now32: int | None) -> list:
    """ring events (id, arg, ms16, v) -> [(fw32 or None, sure)]: forward from anchors, back from the first anchor / now"""
    out, cur = [], None
    for i, a, ms, v in evs:
        if i == 0xC0:                                    # episode start: value bits 23..8 = fw ms bits 31..16
            hi = (v >> 8) & 0xFFFF
            cur = (hi << 16 | ms) - (0x10000 if hi == 0 and ms >= 0x8000 else 0)   # power-on lines before Timer2: < 0
        elif i == 0xD8:
            cur = v
        elif cur is not None:
            cur += step(cur & 0xFFFF, ms)
        out.append([cur, True])
    first = next((k for k, (t, _) in enumerate(out) if t is not None), None)
    if first is None and now32 is not None and evs:
        first, out[-1][0] = len(out) - 1, now32 - ((now32 - evs[-1][2]) & 0xFFFF)
    if first is not None:
        for k in range(first - 1, -1, -1):
            out[k][0] = out[k + 1][0] - step(evs[k][2], evs[k + 1][2])
    if now32 is not None:
        back = now32
        for k in range(len(out) - 1, -1, -1):            # back from now down to the last anchor
            back -= step(evs[k][2], back & 0xFFFF)
            if out[k][0] is not None and out[k][0] != back:
                out[k][1] = False
            if evs[k][0] in (0xC0, 0xD8):
                break
    return [tuple(x) for x in out]


SYS_STATE, SYS_WHY, SYS_REQ, SYS_OUT = 0x15, 0x16, 0x17, 0x18    # #162 step 3 name tables (sync.tsv), read by the sys / sysreq fmts
SYS_MODE, PNL_BY = 0x1A, 0x1B            # #162 s3b: mode text per state (sys, why bit 7), panel requester (pby)
SYS_MS_MAX = 0xFFFFFF
WHY_CODE, WHY_MODE = 0x3F, 0x80          # RL6449_Project.h AWTO_SYS_WHY_CODE / AWTO_SYS_WHY_MODE


def name(rows: list[dict], i: int, a: int) -> str:
    row = next((r for r in rows if r["id"] == i and (r["arg"] is None or r["arg"] == a)), None)
    return row["text"] if row else f"{a:02X}"


def sys_value(rows: list[dict], fmt: str, a: int, v: int) -> str:
    """#162 step 3 system machine: transition (arg old << 4 | new, value why << 24 | ms) / request (value who << 8 | outcome)"""
    if fmt == "sys":
        old, why = name(rows, SYS_STATE, a >> 4), v >> 24
        mode = f"; {name(rows, SYS_MODE, a & 0x0F)}" if why & WHY_MODE else ""        # s3b: the SDK mode changed
        return f"in {old} for {v & SYS_MS_MAX}ms->{name(rows, SYS_STATE, a & 0x0F)}:{name(rows, SYS_WHY, why & WHY_CODE)}{mode}"
    return f"{name(rows, SYS_REQ, a)} by {name(rows, SYS_WHY, (v >> 8) & 0xFF)} ({name(rows, SYS_OUT, v & 0xFF)})"


def note_defs(header: Path | None = None) -> dict:
    """host note slot layout from RL6449_Project.h (one source with the firmware): chars, tag / length / text offsets"""
    h = header or ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
    txt = h.read_text()
    out = {}
    for k in ("CHARS", "TAG", "LEN", "TXT"):
        m = re.search(rf"^#define\s+AWTO_NOTE_{k}\s+(\d+)", txt, re.MULTILINE)
        if not m:
            raise SystemExit(f"AWTO_NOTE_{k} not in {h.name}")
        out[k] = int(m.group(1))
    out["SIZE"] = out["TXT"] + out["CHARS"]
    return out


def note_text(slot: bytes | None, length: int, seq: int, d: dict | None = None) -> str:
    """text of note `seq` from the slot bytes: explicit when a newer note took the slot (tag != seq) or the slot was not read"""
    d = d or note_defs()
    if slot is None:
        return f"text not read ({length} chars)"
    if int.from_bytes(slot[d["TAG"]:d["TAG"] + 2], "big") != seq & 0xFFFF:
        return "text overwritten"
    return "".join(chr(c) if 0x20 <= c <= 0x7E else "?" for c in slot[d["TXT"]:d["TXT"] + min(length, d["CHARS"])])


def line(rows: list[dict], ev: tuple, t0: int) -> str:
    i, a, ms, v = ev
    dt = (ms - t0) & 0xFFFF
    head = f"{dt:5d}:"
    row = next((r for r in rows if r["id"] == i and (r["arg"] is None or r["arg"] == a)), None)
    if row is None:
        return head + f"event {i:02X} {a:02X}"
    pre = f"D{a - D0} " if row["port"] else ""
    if row["fmt"] == "ms2":                              # #162 s3b: two values, two % (second ms << 16 | first ms)
        p0, p1, p2 = row["text"].split("%")
        return head + pre + f"{p0}{v & 0xFFFF}ms{p1}{v >> 16}ms{p2}"
    before, _, after = row["text"].partition("%")
    val = (v if row["fmt"] == "note" else sys_value(rows, row["fmt"], a, v) if row["fmt"] in ("sys", "sysreq") else
           name(rows, PNL_BY, v & 0xFF) if row["fmt"] == "pby" else
           name(rows, SYS_STATE, v & 0xFF) if row["fmt"] == "sname" else value(row["fmt"], a, v))     # sname: #95 LED line
    return head + pre + before + val + after


use_colour = sync_classes.use_colour


def row_class(rows: list[dict], ev: tuple) -> str:
    """colour class of a ring entry (the row `line` picks; an unlisted event is normal)"""
    row = next((r for r in rows if r["id"] == ev[0] and (r["arg"] is None or r["arg"] == ev[1])), None)
    return row["cls"] if row else sync_classes.DEFAULT


def paint_lines(h: dict, lines: list[str], rows: list[dict], tty: bool) -> list[str]:
    """one output line per decoded line, same order; class colour only on a TTY (a file or pipe gets the plain text)"""
    evs = h.get("events", [])
    if not tty or len(evs) != len(lines):
        return list(lines)
    classes = sync_classes.load()
    return [sync_classes.paint(ln, row_class(rows, ev), True, classes) for ev, ln in zip(evs, lines)]


def read_ring(rd, addr: int):
    """the whole ring at addr: header first, then HDR + N x EV (N from the header). rd(addr, n) -> bytes or None"""
    h = rd(addr, HDR)
    if h is None:
        return None
    h = bytes(h)
    return h if h[:2] != b"SY" else rd(addr, HDR + h[12] * EV)


def decode(raw: bytes, rows: list[dict], whole: bool = False, note: bytes | None = None):
    """whole=True: every entry still in the ring (all episodes), times relative to the current episode's t0"""
    h = dict(magic=raw[0:2], version=raw[2], seq=raw[3], ep_seq=raw[4], kind=raw[5], port=raw[6],
             t0=raw[7] << 8 | raw[8], done=raw[9], open_req=raw[10])
    if h["magic"] != b"SY":
        return h, []
    n_, wrap = raw[12], raw[13]
    n = n_ if whole else (h["seq"] - h["ep_seq"]) % wrap
    lost = max(0, n - n_)
    evs, seqs, raws = [], [], []
    for k in range(min(n, n_)):
        s = (h["seq"] - min(n, n_) + k) % wrap
        e = raw[HDR + EV * (s % n_):HDR + EV * (s % n_) + EV]
        if whole and e[0] == 0:
            continue                                     # never written (a young ring)
        seqs.append(s)                                   # ring seq + raw bytes per decoded line: the unit log saver (unit_log.py) dedupes on them
        raws.append(bytes(e))
        v = int.from_bytes(e[4:8], "big")
        evs.append((e[0], e[1], e[2] << 8 | e[3], note_text(note, e[1], v) if e[0] == NOTE_EV else v))   # #273: text via the slot
    h["lost"] = lost
    h["n"], h["wrap"] = n_, wrap
    h["events"], h["seqs"], h["raws"] = evs, seqs, raws
    return h, [line(rows, ev, h["t0"]) for ev in evs]


def snapshot(h: dict, lines: list[str], ht: dict | None, t2: int | None, serial: str | None = None) -> dict:
    """machine form of one ring read (decode(..., whole=True)): per entry ring seq, raw bytes, decoded line, host time when synced"""
    evs = h.get("events", [])
    ts = unwrap(evs, fw_now(ht, t2)) if ht and ht["syncs"] and t2 is not None else [(None, False)] * len(evs)
    ents = []
    for s, r, ln, ev, (t, sure) in zip(h["seqs"], h["raws"], lines, evs, ts):
        ents.append({"seq": s, "raw": r.hex(), "text": ln, "id": ev[0],
                     "val": int.from_bytes(r[4:8], "big"), "wall": None if t is None else host_time(ht, t), "sure": bool(sure)})
    return {"serial": serial, "read": dt.datetime.now().astimezone().isoformat(timespec="milliseconds"), "seq": h["seq"], "n": h["n"],
            "wrap": h["wrap"], "ep_seq": h["ep_seq"], "kind": KINDS.get(h["kind"], h["kind"]), "lost": h.get("lost", 0), "entries": ents}


def stamp(h: dict, lines: list[str], ht: dict | None, t2: int | None) -> list[str]:
    """#157: each line prefixed with its host time (no sync yet: unchanged)"""
    if not ht or not ht["syncs"] or t2 is None:
        return lines
    ts = unwrap(h.get("events", []), fw_now(ht, t2))
    return [(host_time(ht, t) + ("~ " if not sure else "  ") if t is not None else " " * 31) + ln for (t, sure), ln in zip(ts, lines)]


def read_note(io, map_path: Path) -> bytes | None:
    """the host note text slot over 0x35; None on an image without #273 or a failed read"""
    import dbg_xdata as X
    if " _g_aucAwtoNote " not in map_path.read_text(errors="replace"):
        return None
    b = X.read_blocks(io, sym(map_path, "g_aucAwtoNote"), note_defs()["SIZE"])
    return None if b is None else bytes(b)


def read_ht(io, map_path: Path):
    """(ht dict, usT2Isr read after it) over 0x35; (None, None) on an image without #157"""
    import dbg_xdata as X
    mt = map_path.read_text(errors="replace")
    if " _isr_g_stAwtoHt " not in mt:
        return None, None
    b = X.read_blocks(io, sym(map_path, "isr_g_stAwtoHt"), HT_SIZE)
    d = X.read_blocks(io, 0xF6D0, DIAG_T2 + 2)           # diag block: fixed address (RL6449_Project.h)
    if b is None or d is None:
        return None, None
    return ht_decode(bytes(b)), int.from_bytes(bytes(d[DIAG_T2:DIAG_T2 + 2]), "big")


def ht_line(ht: dict | None, t2: int | None) -> str:
    if ht is None:
        return "host time: image without #157 (or read failed)"
    if not ht["syncs"]:
        return "host time: no sync since boot (scripts/host_time.py)"
    now = fw_now(ht, t2)
    return (f"host time: {ht['syncs']} sync(s), last at fw {ht['fw']} ms = {iso(ht['epoch'] + ht['frac'] / 1000, ht['ofs'], True)}, "
            f"drift then {ht['drift']:+d} ms; fw now {now} ms = {host_time(ht, now)} (sync age {(now - ht['fw']) / 1000:.1f} s)")


def pin_line(raw8: bytes, rows: list[dict]) -> str | None:
    """#150: the pinned boot-reason entry (g_stAwtoSyncPin, 8 B, ring entry layout), time as stored (ms since reset)"""
    if not raw8 or len(raw8) < EV or raw8[0] == 0:
        return None
    return line(rows, (raw8[0], raw8[1], raw8[2] << 8 | raw8[3], int.from_bytes(raw8[4:8], "big")), 0)


def sym(map_path: Path, name: str) -> int:
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{name}\b", map_path.read_text(errors="replace"), re.MULTILINE)
    if not m:
        raise SystemExit(f"{name} not in {map_path}: image without the #139 sync log")
    return int(m.group(1), 16) & 0xFFFF


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--serial", help="EDID serial the bus must belong to (i2cbus.require_unit)")
    ap.add_argument("--whole", action="store_true", help="every entry still in the ring (all episodes), times vs the current episode")
    ap.add_argument("--json", action="store_true", help="one 'SYNCJSON {...}' line with every entry (ring seq, raw bytes, text, host time) for scripts/unit_log.py")
    ap.add_argument("--delta", action="store_true", help="add a +ms column: time since the previous line (#216 boot timing)")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    if a.serial:
        i2cbus.require_unit(a.bus, a.serial)
    rows = load_rows(a.tsv or tsv_for(a.map))
    io = B.Real(a.bus, allow_write=True, regread=True)
    raw = read_ring(lambda ad, n: X.read_blocks(io, ad, n), sym(a.map, "g_stAwtoSync"))
    ht, t2 = read_ht(io, a.map) if raw is not None else (None, None)
    note = read_note(io, a.map) if raw is not None else None
    io.close()
    if raw is None:
        log("sync: read over 0x35 failed")
        return 1
    h, lines = decode(bytes(raw), rows, a.whole, note)
    if h["magic"] != b"SY":                              # #158: wrong map (not the running image) reads another address
        st = ROOT / f"tmp/fw/{a.serial}-flash-state.json" if a.serial else None
        img = json.loads(st.read_text()).get("image") if st and st.exists() else "? (pass --serial)"
        log(f"sync: header {bytes(raw[:HDR]).hex(' ')} has no 'SY' magic at {a.map.name}'s g_stAwtoSync: the map is not the "
            f"running image's? flash-state image {img}")
        return 2
    if a.json:
        print("SYNCJSON " + json.dumps(snapshot(h, lines, ht, t2, a.serial)), flush=True)
        return 0
    log(ht_line(ht, t2))
    lines = stamp(h, lines, ht, t2)
    log(f"sync episode: {KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines" + (f", {h['lost']} older lines overwritten" if h.get("lost") else ""))
    prev = None
    painted = paint_lines(h, lines, rows, sync_classes.use_colour())
    for ln, pl in zip(lines, painted):
        m = re.match(r"^\s*(\d+):", ln) if a.delta else None
        pre = ""
        if m:
            ms = int(m.group(1))
            pre = f"{'+' + str(ms - prev) if prev is not None else '':>6} "
            prev = ms
        log("  " + pre + ln, "  " + pre + pl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
