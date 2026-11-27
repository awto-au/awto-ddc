#!/usr/bin/env python3
"""Decode the #139 sync / power-on log ring (firmware g_stAwtoSync) into the same lines the monitor shows.

usage: sync_log.py BUS --map MAP [--tsv TSV] [--serial SERIAL]      read over the debug slave 0x35 and print the episode
       (library) decode(raw, rows) -> (header dict, [lines]); load_rows(tsv); tsv_for(map)
- Texts and value formats: the firmware tree's fw/awto/sync.tsv (one file for screen and host; the console wraps a long line
  to a second row, the host prints it on one). Default TSV = the image's
  <map stem>.sync.tsv (dev.py build copies it beside the image), else $AWTO_SYNC_TSV.
- Ring layout (RL6449_Project.h StAwtoSync, bytes only): 14 B header, N x 8 B entries {id, arg, ms hi, ms lo, value BE x4}.
  Header byte 12 = N, byte 13 = seq wrap: read the header, then N x 8 B (read_ring); nothing is hardcoded here.
- Line = the console's columns: real time (host clock 'HH:MM:SS.mmm' of the line's boot with a host sync, else 'u' + uptime),
  +delta since the line above, text, then the raw times [fw 32-bit ms, ring ms16] (docs/sync-log-design.md).
- Full times: DRAM log images (version 4) carry 32-bit ms per entry (tail + DDR); version 3 rings are 16 bit, unwrapped from
  anchors (C0 fw ms bits 31..16, D8 full fw ms). A delta not known for certain is a red row "relative time reset: counter wrap".
- Groups of one call share a row as on the console (JOIN pairs: monitor, frame buffers + memory, frame rate + scaling + FRC width).
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

import sync_classes
from _log import shared
from _repo import ROOT

LOG = ROOT / "tmp/logs/sync_log.log"
NOTE_EV = 0xEE                            # RL6449_Project.h AWTO_SYNC_EV_NOTE: arg = length, value = note sequence (#273)
HDR, EV = 14, 8                           # header bytes, bytes per entry; N = header[12], seq wrap = header[13]
D0 = 3                                                   # _D0_INPUT_PORT
SRC = {2: "DVI", 3: "HDMI", 4: "DP"}
DP_RATE = {0x06: "RBR", 0x0A: "HBR", 0x14: "HBR2", 0x1E: "HBR3"}
KINDS = {1: "power on", 2: "switch", 3: "wake", 4: "power key on", 5: "picture lost"}
SYMBOLIZE = None                                         # set_map(): (bank, pc) -> "fn+0x.." for the pc fmt


def set_map(map_path: Path) -> None:
    """symbols for the pc fmt (boot reason line); rtd_crash's map reader"""
    global SYMBOLIZE
    import rtd_crash as C
    syms = C.load_syms(Path(map_path).read_text(errors="replace"))
    SYMBOLIZE = lambda bank, pc: C.symbolize(syms, bank, pc)


def log(s: str, shown: str | None = None):
    """s -> console + log file; shown = the console copy (class colour on a TTY), the file always gets the plain s"""
    shared(LOG).say(s, shown=shown)


def load_rows(tsv: Path) -> list[dict]:
    out = []
    for ln in tsv.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        i, a, f, t, *c = ln.split("\t")                  # optional 5th column: colour class (fw/awto/sync_classes.tsv)
        port = f.startswith("port")
        out.append({"id": int(i, 16), "arg": None if a == "*" else int(a, 16), "port": port, "fmt": f[4:] if port else f, "text": t,
                        "cls": sync_classes.check(c[0] if c else "")})
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


SD_KIND = ("DVI", "HDMI 1.4 (1:10)", "HDMI 2.0 (1:40)", "DP")     # sdone / slink arg bits 3:2 (RL6449_Project.h AWTO_SD_*)
SD_NONE12, SD_MAX12, SD_NONE8 = 0xFFF, 0xFFE, 0xFF
SD_NA = 0x80


def _t12(x: int) -> str:
    return "-" if x == SD_NONE12 else (f"+{x}+ms" if x == SD_MAX12 else f"+{x}ms")


def _sat(x: int, mx: int) -> str:
    return f"{x}+" if x >= mx else str(x)


def sync_done(a: int, v: int, ms: int) -> str:
    """fmt sdone (firmware copy: fw/osd/console.c AwtoPutSdone): arg = port idx | kind << 2 | scan retries << 4 | set-ups / trainings << 6,
    value = scan ok ms << 20 | timing ms << 8 | PHY / link ms (0xFF = none); scan ok / timing are ms since the search reached the port (+N), ms = the line's own time since the episode start (ACTIVE)"""
    kind, r, n, phy = (a >> 2) & 3, (a >> 4) & 3, a >> 6, v & 0xFF
    tries = "first try" if r == 0 else f"after {_sat(r, 3)} retr{'y' if r == 1 else 'ies'}"
    if kind == 3:
        what = f"link trained {'-' if phy == SD_NONE8 else f'{phy}ms'} ({_sat(n, 3)} training{'' if n == 1 else 's'})"
    else:
        what = f"PHY {'-' if phy == SD_NONE8 else f'{phy}ms'} ({_sat(n, 3)} set-up{'' if n == 1 else 's'})"
    return (f"D{(a & 3) + 1} {SD_KIND[kind]}, {tries}: {what}, scan ok {_t12(v >> 20)}, timing {_t12((v >> 8) & 0xFFF)}, ACTIVE {ms}ms")


def sync_link(a: int, v: int) -> str:
    """fmt slink: arg = port idx | kind << 2 | flags << 4 (HDMI bit 0 / 1 = SCDC 20h scrambling / ratio bits as the source left them (sources leave them 0, docs/input-sync-timeline.md section 5; the PHY mode in the head is the authority), bit 2 scrambled data seen; DP bits 2:0 lanes) | 0x80 n/a,
    value = ms after ACTIVE << 24 | HDMI errors ch0 / 1 / 2 (each 255 max) or DP rate / DPCD 202h / 203h"""
    kind, f, after = (a >> 2) & 3, (a >> 4) & 7, f"{v >> 24}ms after ACTIVE"
    head = f"D{(a & 3) + 1} {SD_KIND[kind]}"
    if a & SD_NA:
        return f"{head}: no link health on this input, {after}"
    if kind == 3:
        st = (v >> 8) & 0xFF, v & 0xFF                   # DPCD 202h lanes 0 / 1, 203h lanes 2 / 3: bit 0 CR, 1 EQ, 2 symbol lock per lane
        bits = [(st[i // 2] >> (4 * (i % 2))) for i in range(f)]
        cnt = [sum((b >> k) & 1 for b in bits) for k in range(3)]
        r = (v >> 16) & 0xFF
        return f"{head} {DP_RATE.get(r, f'{r:02X}')} x{f}: lanes CR {cnt[0]}/{f}, EQ {cnt[1]}/{f}, symbol lock {cnt[2]}/{f}, {after}"
    e = [_sat((v >> s) & 0xFF, 255) for s in (16, 8, 0)]
    return (f"{head}: {'scrambled data seen' if f & 4 else 'no scrambled data'}, SCDC 20h as the source left it: ratio bit {(f >> 1) & 1} "
            f"scrambling bit {f & 1}, errors {e[0]}/{e[1]}/{e[2]}, {after}")


def sync_visit(a: int, v: int) -> str:
    """fmt visit (firmware copy: fw/osd/console.c AwtoPutVisit): arg bit 7 = reached (bit 0 predetect on, bit 1 cable detected), else left
    (bit 2 predetect seen, bit 1 port disabled, bit 3 dwell re-armed); value = predetect edges << 24 | port << 16 | ms on the port"""
    port = f"D{((v >> 16) & 0xFF) - D0}"
    if a & 0x80:
        return f"reached {port}: predetect {'on' if a & 1 else 'off'}, {'cable detected' if a & 2 else 'no cable'}"
    out = f"left {port} after {v & 0xFFFF}ms: " + ("port disabled, skipped" if a & 2 else
                                                 f"{'predetect seen' if a & 4 else 'no signal'}, {_sat(v >> 24, 255)} edges")
    return out + (", dwell re-armed" if a & 8 else "")


INI_FLAGS = ("source", "mode", "OSD", "other")        # SDK change flags of the INITIAL exit check (fw/log/sync.c AwtoSyncInitial)


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
    if fmt == "visit":
        return sync_visit(arg, v)
    if fmt == "iniflg":                                  # #359 arg = flags seen, value = ms / 4 per flag from bit 31 (console AwtoPutIniFlg)
        return ",".join(f" {w} {((v >> (24 - 8 * k)) & 0xFF) << 2}ms" for k, w in enumerate(INI_FLAGS) if (arg >> k) & 1)
    if fmt == "pins":                                    # #359 value = changed mask << 8 | levels: "D1 low, D2 high" (console AwtoPutPins)
        return ", ".join(f"D{i + 1} {'high' if (v >> i) & 1 else 'low'}" for i in range(3) if (v >> (8 + i)) & 1)
    if fmt == "pms":                                     # #139 value = port << 16 | ms: "D2, 188ms"
        return f"D{((v >> 16) & 0xFF) - D0}, {v & 0xFFFF}ms"
    if fmt == "psrc":                                    # value = port << 8 | source type: "D2 HDMI"
        return f"D{((v >> 8) & 0xFF) - D0} {SRC.get(v & 0xFF, str(v & 0xFF))}"
    if fmt == "lim":                                     # value = width << 16 | limit
        return f"{(v >> 16) & 0xFFFF} of {v & 0xFFFF} px"
    if fmt == "rms":                                     # value = register / argument << 16 | ms: "71A4 40ms"
        return f"{(v >> 16) & 0xFFFF:04X} {v & 0xFFFF}ms"
    if fmt == "dly":                                     # fw/timer/delay.c: arg = bank | (N - 1) << 4, value = caller PC << 16 | us
        more = f" +{arg >> 4} more" if arg >> 4 else ""
        return f"{arg & 0x0F:02X}:{(v >> 16) & 0xFFFF:04X} took {v & 0xFFFF} us{more}"
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


ADC_NAMES = ("A0 key ladder", "A1 key ladder", "A2 pin 96 (unused)", "A3 DP HPD out (pin 97)")   # docs/monitoring.md (console AwtoPutMon)


def mon_text(arg: int, v: int) -> str:
    """health monitor rows, short: a group of one sample shares a row (firmware copy: fw/osd/console.c AwtoPutMon); gap in 0.1 ms"""
    if arg == 1:                                         # an ADC channel moved: channel << 16 | old << 8 | new
        ch = (v >> 16) & 0xFF
        return f"ADC {ADC_NAMES[ch] if ch < len(ADC_NAMES) else ch} {(v >> 8) & 0xFF:02X} -> {v & 0xFF:02X}"
    if arg == 2:
        return f"IOSC {v}"
    if arg == 3:
        return f"{v >> 16}/s gap {(v & 0xFFFF) // 10}.{(v & 0xFFFF) % 10}ms"
    if arg == 5:
        return f"free {v & 0xFFF}/s busy {v >> 24}% worst {(((v >> 12) & 0xFFF) * 1000 // 16) / 1000:.3f}ms"
    if arg == 4:
        return f"up {v >> 8}s stk {v & 0xFF:02X}"
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


# ---- #157 host time: g_stAwtoHt (RL6449_Project.h StAwtoHt, BE words) ----------------------------------------------------
HT_SIZE = 16
T2_READ_AT = None                                        # host datetime right after read_ht read usT2Isr (snapshot poll join)
DIAG_T2 = 0x16                                           # StAwtoDiag.usT2Isr (docs/diag-block.md)


def ht_decode(b: bytes) -> dict:
    return {"syncs": b[0], "ofs": b[1] - 256 if b[1] >= 128 else b[1], "frac": int.from_bytes(b[2:4], "big"),
                "epoch": int.from_bytes(b[4:8], "big"), "fw": int.from_bytes(b[8:12], "big"),
                "drift": int.from_bytes(b[12:14], "big", signed=True), "up_hi": int.from_bytes(b[14:16], "big")}


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


def signed32(x: int) -> int:
    return x - (1 << 32) if x >= 1 << 31 else x


def unwrap(evs: list, now32: int | None, ms32: list | None = None) -> list:
    """ring events (id, arg, ms16, v) -> [(fw32 or None, sure)]. Full times: the entry's 32-bit ms (ms32, DRAM log), C0 (fw ms
    bits 31..16 in the value), D8 (full fw ms), now32 after the last line. Others are chained by 16-bit steps from the anchor
    before; sure only when the chain lands exactly on the next full time (no wrap hidden between), else False"""
    def full(k):
        i, _a, ms, v = evs[k]
        if ms32 and ms32[k] is not None:
            return signed32(ms32[k])
        if i == 0xC0:
            hi = (v >> 8) & 0xFFFF
            return (hi << 16 | ms) - (0x10000 if hi == 0 and ms >= 0x8000 else 0)   # power-on lines before Timer2: < 0
        return v if i == 0xD8 else None
    out, cur, seg = [], None, []                         # seg: chained line indexes since the last anchor
    for k, ev in enumerate(evs):
        f = full(k)
        if f is not None:
            if cur is not None and cur + step(cur & 0xFFFF, ev[2]) == f:
                for j in seg:
                    out[j][1] = True
            cur, seg = f, []
            out.append([f, True])
            continue
        cur = None if cur is None else cur + step(cur & 0xFFFF, ev[2])
        seg.append(k)
        out.append([cur, False])
    if seg and cur is not None and now32 is not None and cur + step(cur & 0xFFFF, now32 & 0xFFFF) == now32:
        for j in seg:
            out[j][1] = True
    first = next((k for k, (t, _) in enumerate(out) if t is not None), None)
    if first is None and now32 is not None and evs:
        first, out[-1][0] = len(out) - 1, now32 - ((now32 - evs[-1][2]) & 0xFFFF)
    if first is not None:
        for k in range(first - 1, -1, -1):
            out[k][0] = out[k + 1][0] - step(evs[k][2], evs[k + 1][2])
    return [tuple(x) for x in out]


BOOT_EV, BEGIN_EV, K_POWER_ON, BEGIN_IN = 0xD0, 0xC0, 1, 0x01    # RL6449_Project.h AWTO_SYNC_EV_BOOT / _BEGIN, AWTO_SYNC_K_POWER_ON, AWTO_SYNC_BEGIN_IN


def is_start(ev: tuple) -> bool:
    """an episode start (console red row): the boot line, or a BEGIN that is not power-on / a switch inside an unsettled episode"""
    i, a, _, v = ev
    return i == BOOT_EV or (i == BEGIN_EV and a != K_POWER_ON and isinstance(v, int) and v >> 24 != BEGIN_IN)


def fmt_delta(d: int | None) -> str:
    """console time column (fw/osd/console.c AwtoPutDelta): 7 cells, "+xxx ms" / "+xx.x s" / "+xxxx s" / "+xxxx h"; None = blank"""
    if d is None:
        return " " * 7
    sg, u = ("-" if d < 0 else "+"), abs(d)
    if u <= 999:
        return f"{sg}{u:3d} ms"
    if u <= 99_999:
        return f"{sg}{u // 1000:2d}.{u // 100 % 10} s"
    return f"{sg}{u // 1000:4d} s" if u <= 9_999_999 else f"{sg}{u // 3_600_000:4d} h"


# Joined rows (fw/osd/console.c AWTO_LN_PAIR / AWTO_LN_JOIN_MS): the next line shares the row when the pair is listed and it came within JOIN_MS
JOIN_MS = 3
MON_EV = 0xEA                                            # AWTO_SYNC_EV_MON: a joined monitor line shows its values only
JOIN_PAIRS = {(MON_EV, MON_EV), (0xF5, 0xF6), (0xF7, 0xF8), (0xF8, 0xF9), (0xC7, 0xC8)}    # heartbeat rows (not an ADC move, arg 1), FBUF -> MCFG, DVF -> SCALE -> LIMIT, VFREQ -> PCLK (#359)
MON_ADC = 1
HOST_EV, HOSTFW_EV = 0xD7, 0xD8                          # AWTO_SYNC_EV_HOST / _HOSTFW
START_WORD = "started"                                  # after an episode start row's text, as the console (#358)
WRAP_TEXT = "relative time reset: counter wrap"          # a delta that is not known for certain (16-bit times only, Dan 2026-11-27)
REAL_W = 13                                              # real-time column: marker + 12 cells
S_PER_DAY = 86400


def joins(a: tuple, b: tuple) -> bool:
    """b (id, arg, ms16, ...) shares a's row"""
    if MON_ADC in ((a[1] if a[0] == MON_EV else None), (b[1] if b[0] == MON_EV else None)):
        return False
    return (a[0], b[0]) in JOIN_PAIRS and (b[2] - a[2]) & 0xFFFF <= JOIN_MS


INIT_EV, INIT_T2 = 0xD2, 2                               # AWTO_SYNC_EV_INIT arg 2: Timer2 start, value = ms from the MCU reset (fw ms 0)


def boot_bases(evs: list) -> list:
    """per event: its boot's ms from the MCU reset to fw ms 0 (the first Timer2 start line after its boot line), None if not in the ring"""
    out, cur = [], None
    for k, e in enumerate(evs):
        if e[0] == BOOT_EV:
            nb = next((j for j in range(k + 1, len(evs)) if evs[j][0] == BOOT_EV), len(evs))
            cur = next((evs[j][3] for j in range(k + 1, nb) if evs[j][0] == INIT_EV and evs[j][1] == INIT_T2 and isinstance(evs[j][3], int)), None)
        out.append(cur)
    return out


def real_col(t: int | None, ht: dict | None, wall: bool, base: int = 0) -> str:
    """console AwtoPutReal: ' ' + host clock HH:MM:SS.mmm (wall: the line's boot has the host sync), else 'u' + uptime of its boot
    (since the MCU reset: fw ms + base)"""
    if t is None:
        return " " * REAL_W
    if not (wall and ht and ht["syncs"]):
        t += base
    if wall and ht and ht["syncs"]:
        ms = t - ht["fw"] + ht["frac"]
        sec, r = divmod(ms, 1000)
        sod = (sec + ht["epoch"] + ht["ofs"] * 900) % S_PER_DAY
        return f" {sod // 3600:02d}:{sod // 60 % 60:02d}:{sod % 60:02d}.{r:03d}"
    if t < 0:
        return f"u-0:00:00.{-t:03d}"
    sec = t // 1000
    if sec // 3600 < 100:
        return f"u{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}.{t % 1000:03d}"
    return f"u{sec // 3600:4d}:{sec // 60 % 60:02d}:{sec % 60:02d}.{t // 100 % 10}"


def con_rows(evs: list, texts: list[str], ts: list, ht: dict | None = None, boots: list | None = None, cur_boot=None, join: bool = True,
             boot_base: int | None = None) -> list[dict]:
    """console rows: {i: entry indexes, real, delta, start, wrap (a wrap row goes before), text}. ts = [(fw ms or None, sure)].
    Host clock only for the current boot (boots: per entry boot, cur_boot; else the lines after the newest boot line).
    boot_base: g_usAwtoBootBase (this boot's reset -> fw ms 0), used when its Timer2 start line is not in evs"""
    last_boot = max((k for k, e in enumerate(evs) if e[0] == BOOT_EV), default=0)
    base = boot_bases(evs)
    out, k = [], 0
    while k < len(evs):
        g = [k]
        while join and g[-1] + 1 < len(evs) and joins(evs[g[-1]], evs[g[-1] + 1]):
            g.append(g[-1] + 1)
        ev, (t, sure) = evs[k], ts[k]
        cur = (boots[k] == cur_boot) if boots is not None else (k >= last_boot)
        b0 = base[k] if base[k] is not None else ((boot_base or 0) if cur else 0)    # any boot with its Timer2 line (the console: this boot)
        st, wrap, d = is_start(ev), False, None
        same_boot = boots is None or (k > 0 and boots[k - 1] == boots[k])
        if st:
            d = ((t if t is not None else ev[2] - (0x10000 if ev[2] >= 0x8000 else 0)) + b0) if ev[0] == BOOT_EV else 0   # boot: since the MCU reset
        elif k > 0 and same_boot:
            tp, sp = ts[k - 1]
            if t is not None and tp is not None and sure and sp:
                d = t - tp
            else:
                wrap = True
        txt = texts[k] + "".join(" | " + (texts[j].split("monitor: ", 1)[-1] if evs[j][0] == MON_EV else texts[j]) for j in g[1:])
        if evs[g[-1]][0] == HOST_EV and g[-1] + 1 < len(evs) and evs[g[-1] + 1][0] == HOSTFW_EV:
            g.append(g[-1] + 1)                          # as the console (AwtoConLogTail): the D8 fw line on the D7 host time row
            txt += " " + texts[g[-1]]
        out.append({"i": g, "real": real_col(t if sure else None, ht, cur, b0), "delta": d, "start": st, "wrap": wrap, "text": txt})
        k = g[-1] + 1
    return out


def row_lines(rs: list[dict], ts: list | None = None, evs: list | None = None) -> list[str]:
    """rows as text: the console columns, then the raw times [fw ms, ring ms16] of the row's first line"""
    out = []
    for r in rs:
        if r["wrap"]:
            out.append(f"{' ' * REAL_W} {fmt_delta(None)}:-- {WRAP_TEXT} --")
        raw = ""
        if ts is not None and evs is not None:
            t = ts[r["i"][0]][0]
            raw = f"  [fw {'?' if t is None else t} ms, ring {evs[r['i'][0]][2]}]"
        out.append(f"{r['real']} {fmt_delta(r['delta'])}:" + (f"-- {r['text']} {START_WORD} --" if r["start"] else r["text"]) + raw)
    return out


SYS_STATE, SYS_WHY, SYS_REQ, SYS_OUT = 0x15, 0x16, 0x17, 0x18    # #162 step 3 name tables (sync.tsv), read by the sys / sysreq fmts
SYS_MODE, PNL_BY = 0x1A, 0x1B            # #162 s3b: mode text per state (sys, why bit 7), panel requester (pby)
SYS_MS_MAX = 0xFFFFFF
WHY_CODE, WHY_MODE = 0x3F, 0x80          # RL6449_Project.h AWTO_SYS_WHY_CODE / AWTO_SYS_WHY_MODE


def name(rows: list[dict], i: int, a: int) -> str:
    row = next((r for r in rows if r["id"] == i and (r["arg"] is None or r["arg"] == a)), None)
    return row["text"] if row else f"{a:02X}"


PASS_SLOW = 0x96


def pass_names(header: Path | None = None) -> list[str]:
    """AWTO_PSTG_NAMES of RL6449_Project.h: stage names by id, then the line words from AWTO_PSTG_WORD0 (firmware: fw/osd/console.c tAwtoPassName)"""
    h = header or Path(__file__).resolve().parents[1] / "fw/sdk/Project/Header/RL6449_Project.h"
    txt = h.read_text()
    m = re.search(r"^#define AWTO_PSTG_NAMES\s+(.*)$", txt, re.MULTILINE)
    w = re.search(r"^#define AWTO_PSTG_WORD0\s+(\d+)", txt, re.MULTILINE)
    if not m or not w:
        raise SystemExit(f"AWTO_PSTG_NAMES / AWTO_PSTG_WORD0 not in {h.name}")
    return re.findall(r'"((?:[^"\\]|\\.)*)\\0"', m.group(1)), int(w.group(1))


def pass_value(rows: list[dict], i: int, a: int, v: int) -> str:
    """fmt pass (firmware copy: fw/osd/console.c AwtoPutPass): 96 slow stage (value = state << 24 | count << 16 | ms), 97 boot passes (state << 24 | ms)"""
    names, w0 = pass_names()
    st, stage, ms = name(rows, SYS_STATE, v >> 24), names[a] if a < w0 else f"{a:02X}", v & 0xFFFF
    if i == PASS_SLOW:
        return f"{names[w0]}{stage}{names[w0 + 1]}{ms}{names[w0 + 2]}{st}{names[w0 + 3]}{(v >> 16) & 0xFF})"
    return f"{names[w0 + 5]}{st}{names[w0 + 4]}{ms}{names[w0 + 2]}{names[w0 + 6]}{stage}"


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


NOTE_DDR = None                          # callable(seq) -> text | None: the DDR note store (docs/note-store.md), set by main() on an image that has it


def note_text(slot: bytes | None, length: int, seq: int, d: dict | None = None) -> str:
    """text of note `seq` from the slot bytes: explicit when a newer note took the slot (tag != seq) or the slot was not read"""
    d = d or note_defs()
    if slot is None:
        return f"text not read ({length} chars)"
    if int.from_bytes(slot[d["TAG"]:d["TAG"] + 2], "big") != seq & 0xFFFF:
        return (NOTE_DDR(seq) if NOTE_DDR else None) or "text overwritten"
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
    if row["fmt"] == "msn":                              # #359 value = number << 16 | ms: "took 0ms (HPD mask 6)"
        p0, p1, p2 = row["text"].split("%")
        return head + pre + f"{p0}{v & 0xFFFF}ms{p1}{v >> 16}{p2}"
    before, _, after = row["text"].partition("%")
    val = (sync_done(a, v, dt) if row["fmt"] == "sdone" else sync_link(a, v) if row["fmt"] == "slink" else
           v if row["fmt"] == "note" else pass_value(rows, i, a, v) if row["fmt"] == "pass" else sys_value(rows, row["fmt"], a, v) if row["fmt"] in ("sys", "sysreq") else
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


DDR_MEM = None                           # the sim's DDR content (fw_sim.DdrPort.mem: unit -> 16 B), for inject_lines
DDR_UNIT = None                          # callable(units) -> 16 B (memory order) | None: the DDR over a debug link or the sim's DDR model (DRAM log, scripts/dram_log.py)
V4_HDR, V4_TAIL, V4_TL = 24, 32, 10     # version 4 header (14 B + gen, boot, pend, lost, head, 32 bit write index, old), tail entries of 10 B (8 B entry + ms bits 31..16)


class Ring(bytes):
    """ring bytes (version 3 layout) + ms32: ring seq -> the entry's 32-bit fw ms (DRAM log images; bytes() drops it);
    entries: [(seq, 8 B entry, ms32)] oldest first when the episode is longer than a seq lap (decode uses them instead of the slots)"""
    def __new__(cls, b, ms32: dict | None = None, entries: list | None = None):
        o = super().__new__(cls, b)
        o.ms32, o.entries = ms32, entries
        return o


def _ring_v4(rd, addr: int, whole: bool = True, ep_abs: int | None = None):
    """DRAM log image (version 4) as the old version 3 ring bytes: the newest N lines from the XDATA tail and the DDR, entry of seq s at slot s % N.
    Lines the DDR cannot give (no reader, stalled, overwritten) stay all 0 = never written; `read_ring.dram_missing` counts them."""
    import dram_log as D
    b = rd(addr, V4_HDR + V4_TAIL * V4_TL)
    if b is None:
        return None
    b = bytes(b)
    seq, n, wrap, gen, pend, head, wr = b[3], b[12], b[13], b[14], b[16], b[18], int.from_bytes(b[19:23], "big")
    nxt = wr + pend                                          # index of the next line to be made
    n = n if whole else wrap                                 # one episode: all its lines from the DDR (up to wrap - 1; a boot is ~130), not the newest N
    ring = bytearray(HDR + n * EV)
    ring[:HDR] = b[:HDR]
    ring[2], ring[12] = 3, n
    missing, ms32, ents = 0, {}, []
    want = n if whole else min(wrap - 1, (seq - b[4]) % wrap)    # the current episode only: no DDR reads for older lines
    if not whole and ep_abs is not None and 0 < nxt - ep_abs <= D.C["AWTO_DLOG_SLOTS"]:
        want = nxt - ep_abs                                  # g_ulAwtoEpAbs: the episode from its start row, any length (#358)
    for d in range(1, min(want, nxt) + 1):
        a = nxt - d
        if d <= V4_TAIL:
            o = V4_HDR + V4_TL * ((head - d) & (V4_TAIL - 1))
            e = b[o:o + EV]
            m32 = int.from_bytes(b[o + 8:o + 10], "big") << 16 | e[2] << 8 | e[3]
        else:
            ent = D.entry(DDR_UNIT, a, gen) if DDR_UNIT else None
            if ent is None:
                missing += 1
                continue
            e = bytes([ent["id"], ent["arg"], (ent["ms"] >> 8) & 0xFF, ent["ms"] & 0xFF]) + ent["val"].to_bytes(4, "big")
            m32 = ent["ms"]
        s = (seq - d) % wrap
        ents.append((s, bytes(e), m32))
        if d < wrap:
            ring[HDR + EV * (s % n):HDR + EV * (s % n) + EV] = e
            ms32[s] = m32
    read_ring.dram_missing = missing
    return Ring(ring, ms32, ents[::-1] if want >= wrap else None)


def inject_lines(rd, wr, addr: int, evs, ms2: bytes, hi: int = 0) -> None:
    """sim tests: ring lines (id, arg, value) as AwtoSyncPush leaves them, at time ms2 (2 B BE), fw ms bits 31..16 = hi. Version 3: XDATA ring slots.
    Version 4: the XDATA tail and the sim's DDR (DDR_MEM) as a flushed line, so a burst of any size fits (no pending lines)."""
    h = bytes(rd(addr, V4_HDR))
    seq, n, wrap = h[3], h[12], h[13]
    for i, a, v in evs:
        if h[2] != 4:
            wr(addr + HDR + EV * (seq % n), bytes([i, a, *ms2]) + v.to_bytes(4, "big"))
        else:
            gen, boot, pend, head, w = h[14], h[15], h[16], h[18], int.from_bytes(h[19:23], "big")
            assert pend == 0 and DDR_MEM is not None, "inject into a DRAM log image needs a drained tail and the sim DDR"
            wr(addr + V4_HDR + V4_TL * (head % V4_TAIL), bytes([i, a, *ms2]) + v.to_bytes(4, "big") + hi.to_bytes(2, "big"))
            import dram_log as D
            ent = bytes([i, a, *hi.to_bytes(2, "big"), *ms2]) + v.to_bytes(4, "big") + (w & 0xFFFFFF).to_bytes(3, "big") + bytes([gen, boot, 0])
            ent = ent[:15] + bytes([D._sum(ent + b"\0")])
            u = D.C["AWTO_DLOG_UNITS0"] + (w % D.C["AWTO_DLOG_SLOTS"]) * D.C["AWTO_DLOG_ENTRY_UNITS"]
            DDR_MEM[u] = ent
            head, w = (head + 1) & 0xFF, w + 1
            h = h[:18] + bytes([head]) + w.to_bytes(4, "big")
            wr(addr + 18, h[18:23])
        seq = (seq + 1) % wrap
    wr(addr + 3, bytes([seq]))


def read_ring(rd, addr: int, whole: bool = True, ep_abs: int | None = None):
    """the whole ring at addr: header first, then HDR + N x EV (N from the header). rd(addr, n) -> bytes or None.
    Version 4 (DRAM log): the same bytes, older lines from the DDR through DDR_UNIT"""
    h = rd(addr, HDR)
    if h is None:
        return None
    h = bytes(h)
    if h[:2] != b"SY":
        return h
    if h[2] == 4:
        return _ring_v4(rd, addr, whole, ep_abs)
    return rd(addr, HDR + h[12] * EV)


read_ring.dram_missing = 0


def decode(raw: bytes, rows: list[dict], whole: bool = False, note: bytes | None = None, ms32: dict | None = None):
    """whole=True: every entry still in the ring (all episodes), times relative to the current episode's t0.
    ms32: ring seq -> 32-bit fw ms (DRAM log), default the Ring's own (bytes(raw) drops it: pass it on)"""
    h = {"magic": raw[0:2], "version": raw[2], "seq": raw[3], "ep_seq": raw[4], "kind": raw[5], "port": raw[6],
             "t0": raw[7] << 8 | raw[8], "done": raw[9], "open_req": raw[10]}
    if h["magic"] != b"SY":
        return h, []
    n_, wrap = raw[12], raw[13]
    n = n_ if whole else (h["seq"] - h["ep_seq"]) % wrap
    lost = max(0, n - n_)
    evs, seqs, raws = [], [], []
    big = getattr(raw, "entries", None) if not whole else None     # an episode longer than a seq lap, from the DDR
    if big:
        lost, n, n_ = 0, len(big), len(big)                         # seqs repeat past a lap: h["ms32"] by position
    for k in range(min(n, n_)):
        s = (h["seq"] - min(n, n_) + k) % wrap
        e = raw[HDR + EV * (s % n_):HDR + EV * (s % n_) + EV] if not big else big[k][1]
        if whole and e[0] == 0:
            continue                                     # never written (a young ring)
        seqs.append(s)                                   # ring seq + raw bytes per decoded line: the unit log saver (unit_log.py) dedupes on them
        raws.append(bytes(e))
        v = int.from_bytes(e[4:8], "big")
        evs.append((e[0], e[1], e[2] << 8 | e[3], note_text(note, e[1], v) if e[0] == NOTE_EV else v))   # #273: text via the slot
    h["lost"] = lost
    h["n"], h["wrap"] = raw[12], wrap
    h["events"], h["seqs"], h["raws"] = evs, seqs, raws
    m = ms32 if ms32 is not None else getattr(raw, "ms32", None)
    h["ms32"] = [x[2] for x in big] if big else ([m.get(s) for s in seqs] if m is not None else None)
    return h, [line(rows, ev, h["t0"]) for ev in evs]


def snapshot(h: dict, lines: list[str], ht: dict | None, t2: int | None, serial: str | None = None) -> dict:
    """machine form of one ring read (decode(..., whole=True)): per entry ring seq, raw bytes, decoded line, host time when synced"""
    evs = h.get("events", [])
    now32 = fw_now(ht, t2) if ht and t2 is not None else None
    ts = unwrap(evs, now32, h.get("ms32")) if (now32 is not None or h.get("ms32")) else [(None, False)] * len(evs)
    read_at = T2_READ_AT or dt.datetime.now().astimezone()
    synced = bool(ht and ht["syncs"])
    last_boot = max((k for k, e in enumerate(evs) if e[0] == BOOT_EV), default=0)
    ents = []
    for k, (s, r, ln, ev, (t, sure)) in enumerate(zip(h["seqs"], h["raws"], lines, evs, ts)):
        cur = k >= last_boot                             # older lines are another boot's: its fw clock, not this sync's / now's
        # poll join (#284): host time of the read minus the fw ms elapsed since the entry; exact to the read latency, needs no host sync
        poll = None if t is None or now32 is None or not cur else (read_at - dt.timedelta(milliseconds=now32 - t)).isoformat(timespec="milliseconds")
        ents.append({"seq": s, "raw": r.hex(), "text": ln, "id": ev[0], "fw": t, "poll_wall": poll,
                     "val": int.from_bytes(r[4:8], "big"), "wall": host_time(ht, t) if synced and cur and t is not None else None, "sure": bool(sure)})
    return {"serial": serial, "read": read_at.isoformat(timespec="milliseconds"), "fw_now": now32, "seq": h["seq"], "n": h["n"],
            "wrap": h["wrap"], "ep_seq": h["ep_seq"], "kind": KINDS.get(h["kind"], h["kind"]), "lost": h.get("lost", 0), "entries": ents}


def stamp(h: dict, lines: list[str], ht: dict | None, t2: int | None) -> list[str]:
    """#157: each line prefixed with its host ISO time, '~' = not sure (no sync yet: unchanged); 31 blanks = no time known"""
    if not ht or not ht["syncs"] or t2 is None:
        return lines
    ts = unwrap(h.get("events", []), fw_now(ht, t2), h.get("ms32"))
    return [(host_time(ht, t) + ("~ " if not sure else "  ") if t is not None else " " * 31) + ln for (t, sure), ln in zip(ts, lines)]


def ring_rows(h: dict, lines: list[str], ht: dict | None, t2: int | None, join: bool = True, rows: list[dict] | None = None) -> list[tuple[str, str]]:
    """decoded ring as the console shows it (con_rows / row_lines): real time, +delta, joined groups, wrap rows; raw times last.
    -> [(plain, painted)]: painted = class colour of the row's first line on a TTY (rows = sync.tsv rows), else plain"""
    evs = h.get("events", [])
    ts = unwrap(evs, fw_now(ht, t2) if ht and t2 is not None else None, h.get("ms32"))
    rs = con_rows(evs, [ln.split(":", 1)[1] for ln in lines], ts, ht, join=join, boot_base=h.get("boot_base"))
    out, classes = [], (sync_classes.load() if rows is not None and sync_classes.use_colour() else None)
    for r in rs:
        for ln in row_lines([r], ts, evs):
            cls = "error" if (r["wrap"] and WRAP_TEXT in ln) or r["start"] else row_class(rows, evs[r["i"][0]]) if rows is not None else None
            out.append((ln, sync_classes.paint(ln, cls, True, classes) if classes else ln))
    return out


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
    if " _g_stAwtoHt " not in mt:
        return None, None
    b = X.read_blocks(io, sym(map_path, "g_stAwtoHt"), HT_SIZE)
    d = X.read_blocks(io, 0xF6D0, DIAG_T2 + 2)           # diag block: fixed address (RL6449_Project.h)
    if b is None or d is None:
        return None, None
    global T2_READ_AT
    T2_READ_AT = dt.datetime.now().astimezone()          # host time right after the fw clock read: the join point of the poll
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
    ap.add_argument("--dram", action="store_true", help="DRAM log image: the history from the DDR ring (all boots), per boot ms since reset (scripts/dram_log.py)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, help="with --dram: the newest K entries (default 64)")
    g.add_argument("--all", action="store_true", help="with --dram: every entry in the DDR ring (77.7 entries/s over the debug link, unit 3 2026-11-27)")
    g.add_argument("--boot", type=int, help="with --dram: only the entries of this boot counter value")
    g.add_argument("--since", type=int, help="with --dram: the entries with absolute index >= N (the unit log saver)")
    ap.add_argument("--count", type=int, help="with --dram --since N: K entries from N on (a page of the history)")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    if a.serial:
        i2cbus.require_unit(a.bus, a.serial)
    rows = load_rows(a.tsv or tsv_for(a.map))
    io = B.Real(a.bus, allow_write=True, regread=True)
    global DDR_UNIT, NOTE_DDR
    dram_img = " _AwtoDlFlush " in a.map.read_text(errors="replace")
    stats: dict = {}
    if dram_img:                                         # DRAM log image: older ring lines and the whole history are in the DDR
        import ddr_frame_test as T
        import ddr_note_read as DN
        import dram_log as D
        dbg = T.Dbg.__new__(T.Dbg)
        dbg.io, dbg.bus, dbg.n_tx = io, None, 0
        DDR_UNIT = D.ddr_reader(dbg, DN.regs(), stats)
    if a.dram and not dram_img:
        io.close()
        log("sync: --dram needs an image with the DRAM log (_AWTO_DRAM_LOG=_ON)")
        return 3
    if a.dram:
        import ddr_note_read as DN2
        notes: dict = {}
        NOTE_DDR = lambda seq: notes.setdefault(seq, DN2.text_of(io, seq))      # note text from the DDR note store, as the ring path
        sys.modules.setdefault("sync_log", sys.modules[__name__])                # run as a script: dram_log's `import sync_log` must see this copy
        ht, t2 = read_ht(io, a.map)
        bb = X.read_blocks(io, sym(a.map, "g_usAwtoBootBase"), 2) if " _g_usAwtoBootBase " in a.map.read_text(errors="replace") else None
        read_at = T2_READ_AT or dt.datetime.now().astimezone()
        xh = X.read_blocks(io, sym(a.map, "g_stAwtoSync"), V4_HDR)
        wr = int.from_bytes(bytes(xh[19:23]), "big") if xh else None
        snap = D.snapshot(DDR_UNIT, rows, None if a.all or a.boot is not None else (a.last or 64), a.boot, a.serial,
                          fw_now(ht, t2) if ht and t2 is not None else None, read_at, a.since, wr, a.count,
                          lambda k, n: log(f"dram log: {k} of {n} entries read"))       # progress: a reader's stall guard
        io.close()
        if snap is None:
            log("sync: no valid DDR log header (a cold power-up, or the image never ran with the DRAM log)")
            return 2
        if a.json:
            print("SYNCJSON " + json.dumps({"dram": True, **snap}), flush=True)
            return 0
        log(f"dram log: gen {snap['gen']} boot {snap['boot']} next index {snap['next']} (wraps {snap['next'] // snap['slots']}), {len(snap['entries'])} entries, "
            f"{stats.get('bursts', 0)} DDR bursts in {stats.get('s', 0):.1f} s")
        for ln in D.con_lines(rows, snap["entries"], snap["boot"], ht, int.from_bytes(bytes(bb), "big") if bb is not None else None):
            log(ln)
        return 0
    ep_abs = None
    if dram_img and " _g_ulAwtoEpAbs " in a.map.read_text(errors="replace"):          # the episode's start row index (#358): read it whole
        b = X.read_blocks(io, sym(a.map, "g_ulAwtoEpAbs"), 4)
        ep_abs = int.from_bytes(bytes(b), "big") if b is not None else None
    raw = read_ring(lambda ad, n: X.read_blocks(io, ad, n), sym(a.map, "g_stAwtoSync"), a.whole, ep_abs)
    ht, t2 = read_ht(io, a.map) if raw is not None else (None, None)
    bb = X.read_blocks(io, sym(a.map, "g_usAwtoBootBase"), 2) if raw is not None and " _g_usAwtoBootBase " in a.map.read_text(errors="replace") else None
    note = read_note(io, a.map) if raw is not None else None
    if raw is not None and " _AwtoDdrNoteWrite " in a.map.read_text(errors="replace"):
        import ddr_note_read as DN
        cache: dict = {}
        NOTE_DDR = lambda seq: cache.setdefault(seq, DN.text_of(io, seq))
    try:
        h, lines = (decode(raw if isinstance(raw, Ring) else bytes(raw), rows, a.whole, note, getattr(raw, "ms32", None))
                    if raw is not None else (None, []))      # a Ring keeps ms32 + the long-episode entries
    finally:
        io.close()
    if raw is None:
        log("sync: read over 0x35 failed")
        return 1
    h["boot_base"] = int.from_bytes(bytes(bb), "big") if bb is not None else None
    if h["magic"] != b"SY":                              # #158: wrong map (not the running image) reads another address
        import flash_registry
        img = (flash_registry.current(a.serial).get("tag") or "?") if a.serial else "? (pass --serial)"
        log(f"sync: header {bytes(raw[:HDR]).hex(' ')} has no 'SY' magic at {a.map.name}'s g_stAwtoSync: the map is not the "
            f"running image's? flash-state image {img}")
        return 2
    if a.json:
        print("SYNCJSON " + json.dumps(snapshot(h, lines, ht, t2, a.serial)), flush=True)
        return 0
    log(ht_line(ht, t2))
    log(f"sync episode: {KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines" + (f", {h['lost']} older lines overwritten" if h.get("lost") else "")
        + ("; the boot and earlier episodes: --whole / --dram" if h["kind"] != K_POWER_ON and not a.whole else ""))
    for ln, pl in ring_rows(h, lines, ht, t2, rows=rows):
        log("  " + ln, "  " + pl)                         # as the console: real time, +delta, text; raw times last
    return 0


if __name__ == "__main__":
    sys.exit(main())
