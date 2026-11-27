#!/usr/bin/env python3
"""Console delta column + episode-start rules in fw_sim (Dan 2026-11-27): snapshots of a boot and a wake, checked against the ring.

usage: AWTO_SIM_CORE=fast con_delta_sim.py BIN [--map MAP] [--out tmp/len/con_delta]
Scenario: cold boot 1080p60 with the console opened at the first main-loop passes (test cmd 0x26), shot at DISPLAY SETTING and
at ACTIVE; power saving (VCP D6 = 4), SOURCE-key wake, console again, shot (the sim's wake goes on searching: power NORMAL
is the check, as con_wrap_sim); then a host time sync, the fw clock jumped 131 s (a gap over the 16-bit ring time), a monitor
pair injected, console reopened, shot.
Also: 200 lines added to the boot episode, console reopened: the red boot row is still the first row ("(N lines not shown)").
#358: settled boot reopened = boot row first; AUTO key (switch + judge reset) and a lost picture (ScalerTMDSStableDetect 0, then 1):
exactly one episode start each (raw entries, rule from RL6449_Project.h), one red row = the first log row, FAILED:signal lost then DONE;
the newest rows' deltas checked against the raw entries' 32-bit ms by ring index (seq_deltas: not sync_log, not text-keyed).
FAIL: a shown row whose real-time column or delta is not the ring's (sync_log.con_rows); a ring episode start in view that is not a red rule row
(`-- text ---`, palette AWTO_PAL_DIAG_ALERT); a rule row that is no episode start; no rule in the boot and wake shots.
Out: <name>.txt / .png per shot, host.txt = sync_log's decoded ring (same delta column and rules). Log: tmp/logs/con_delta_sim.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import con_wrap_sim as W
import host_time as HT
import osd_model as M
import osd_render as R
import sync_log as SL
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/con_delta_sim.log"
CMD_CON = 0x26                          # test cmd: console open
CMD_CLOSE = 0x27                        # test cmd: console closed, holds cleared
MODE_DISPLAY, MODE_ACTIVE = 2, 3        # SysModeGetModeState (fw_sim.SimBus.mode_state)
FIRST_LINES_S = 0.4                     # cold boot -> a few ring lines (MCU set-up, INITIAL): sim s, the 0x26 open follows
UP_HI_OFF = 14                          # StAwtoHt.usUpHi (RL6449_Project.h; sync_log.ht_decode b[14:16])
GAP_UNITS = 2                           # the gap: 2 x 65.536 s = 131.072 s, over the 16-bit ring time
OFS = 44                                # +11:00, 15 min units
T0 = dt.datetime(2026, 11, 27, 15, 18, 14, 833000, dt.timezone(dt.timedelta(hours=11)))
FILLER = (0xE7, 3, 0)                   # "D1 EDID read" (AWTO_SYNC_EV_EDID): a plain row, never joined
OVERFLOW_N = 200                        # lines added to the boot episode: past the console map (57 rows), the 88-line window and a seq wrap (176)
JOIN_PAIR = ((0xEA, 2, 2001), (0xEA, 4, 1150 << 8 | 0xD4))     # monitor IOSC + uptime rows (AWTO_MON_EV_TRIM / _UP)
ALERT = int(re.search(r"^#define AWTO_PAL_DIAG_ALERT\s+(\d+)", (ROOT / "fw/osd/console.c").read_text() + (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text(), re.MULTILINE).group(1))


def say(s: str):
    _log_line(s, LOG)


def shot(s: W.Sim, name: str, out: Path) -> int:
    """save the shown page; check each row's real-time column, delta and rule state against the ring rows (sync_log.con_rows with
    the firmware's host-time state); return the rule rows shown"""
    t = s.text()
    st = s.model.snapshot(s.m, 0)
    (out / f"{name}.txt").write_text("\n".join(r.rstrip() for r in t) + "\n")
    R.render_snap(st, "black", 1).save(out / f"{name}.png")
    want: dict[str, set] = {}
    for r in s.con_rows(ht(s)):
        want.setdefault(W.norm(r["text"]), set()).add((r["real"], SL.fmt_delta(r["delta"]), r["start"]))
    lay = M.layout_rows(st, M.frame_geometry(st))
    bad, rules, n = [], 0, 0
    for r, lr in zip(t[1:], lay[1:]):
        r = r[W.LOG_COL:]
        m = W.HEAD.match(r)
        if not m:
            continue
        body = r[m.end():].rstrip()
        rule = W.RULE.match(body)
        txt = W.norm(rule.group(1) if rule else body)
        if txt not in want:
            continue                                     # a wrapped first row (its text is a prefix): con_wrap_sim checks those
        n += 1
        if (m.group("real"), m.group(2), bool(rule)) not in want[txt]:
            bad.append(f"{m.group('real')!r} {m.group(2)!r} rule {bool(rule)} vs ring {sorted(want[txt])}: {txt[:50]}")
        if rule:
            rules += 1
            fg = {c["fg"] for c, ch in zip(lr["chars"], t[lay.index(lr)]) if c["kind"] == "1bit" and ch != " "}
            if fg != {ALERT}:
                bad.append(f"rule row colours {sorted(fg)}, want palette {ALERT} (AWTO_PAL_DIAG_ALERT): {txt[:40]}")
    s.check(not bad and n > 0, f"{name}: real time, delta column and episode-start rules match the ring ({n} rows)", "; ".join(bad[:3]))
    say(f"  {name}: {rules} rule row(s); page {out / name}.txt")
    return rules


def reopen(s: W.Sim):
    """console closed and opened again: drawn anew from the ring"""
    s.cmd(CMD_CLOSE)
    s.bus.wait(W.DRAW_S)
    s.cmd(CMD_CON)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], W.DRAW_S)
    s.bus.wait(W.DRAW_S)


def ht(s: W.Sim) -> dict:
    return SL.ht_decode(bytes(s.m.rd(s.m.addr("g_stAwtoHt"), SL.HT_SIZE)))


def jump(s: W.Sim, units: int):
    """fw clock + units x 65.536 s at once (g_stAwtoHt.usUpHi = AwtoMs bits 31..16): a gap over the 16-bit ring time without the sim time"""
    a = s.m.addr("g_stAwtoHt") + UP_HI_OFF
    hi = int.from_bytes(bytes(s.m.rd(a, 2)), "big")
    s.m.wr(a, (hi + units).to_bytes(2, "big"))
    return hi + units


H = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
HDEF = {k: int(re.search(rf"^#define {k}\s+(0x[0-9A-Fa-f]+|\d+)", H, re.MULTILINE).group(1), 0) for k in (
    "AWTO_SYNC_EV_BOOT", "AWTO_SYNC_EV_BEGIN", "AWTO_SYNC_EV_SDONE", "AWTO_SYNC_EV_SFAIL", "AWTO_SD_WHY_LOST",
    "AWTO_SYNC_K_POWER_ON", "AWTO_SYNC_K_SWITCH", "AWTO_SYNC_K_LOST", "AWTO_SYNC_BEGIN_IN")}
K_AUTO = 0x01                           # test cmd: key message 0 = the AUTO key (fw/test/testcmd.c): AwtoSourceAuto, K_SWITCH + reset to search
MODE_SEARCH_S = 1.0                     # ACTIVE -> leaves ACTIVE after the key / the unstable judge: one judge pass, x ~10
TAIL_N, TAIL_B, HDR_B = 32, 10, 24      # DRAM log XDATA tail: 32 x (8 B entry + ms bits 31..16), after the 24 B version-4 header


def raw_entries(s: W.Sim, a0: int) -> tuple[int, list[tuple]]:
    """(next abs index, [(abs, id, arg, fw ms 32, value)] from abs a0 on): the XDATA tail + the sim DDR read here, not through sync_log"""
    import dram_log as DL
    b = bytes(s.m.rd(s.a_sync, HDR_B + TAIL_N * TAIL_B))
    gen, pend, head, wr = b[14], b[16], b[18], int.from_bytes(b[19:23], "big")
    nxt, out = wr + pend, []
    for a in range(a0, nxt):
        d = nxt - a
        if d <= TAIL_N:
            o = HDR_B + TAIL_B * ((head - d) & (TAIL_N - 1))
            e = b[o:o + TAIL_B]
            out.append((a, e[0], e[1], int.from_bytes(e[8:10], "big") << 16 | e[2] << 8 | e[3], int.from_bytes(e[4:8], "big")))
        else:
            e = DL.entry(SL.DDR_UNIT, a, gen)
            if e is not None:
                out.append((a, e["id"], e["arg"], e["ms"], e["val"]))
    return nxt, out


def starts_of(ents: list[tuple]) -> list[tuple]:
    """episode starts by the firmware's rule (fw/osd/console.c AwtoLnDelta), from RL6449_Project.h: boot line, BEGIN not power-on / IN"""
    return [e for e in ents if e[1] == HDEF["AWTO_SYNC_EV_BOOT"] or (e[1] == HDEF["AWTO_SYNC_EV_BEGIN"] and e[2] != HDEF["AWTO_SYNC_K_POWER_ON"]
                                                                     and e[4] >> 24 != HDEF["AWTO_SYNC_BEGIN_IN"])]


def rule_rows(s: W.Sim) -> list[str]:
    """console rule rows (episode starts) in view, text only, top first"""
    out = []
    for r in s.text()[1:]:
        r = r[W.LOG_COL:]
        m = W.HEAD.match(r)
        if m and W.RULE.match(r[m.end():].rstrip()):
            out.append(W.RULE.match(r[m.end():].rstrip()).group(1))
    return out


def first_row(s: W.Sim) -> str:
    first = next((r[W.LOG_COL:] for r in s.text()[1:] if W.HEAD.match(r[W.LOG_COL:])), "")
    return first[W.HEAD.match(first).end():].rstrip() if first else ""


def seq_deltas(s: W.Sim, name: str, a0: int):
    """#358 independent of sync_log: the newest console rows, bottom up, against the raw entries' 32-bit ms by absolute index.
    A row = one entry, or a joined group (' | ' per joined line); its delta must be ms(entry) - ms(entry above), within the column's rounding."""
    nxt, ents = raw_entries(s, a0)
    by = {e[0]: e for e in ents}
    rows = []
    for r in s.text()[1:]:
        r = r[W.LOG_COL:]
        m = W.HEAD.match(r)
        if m:
            rows.append((m.group(2), r[m.end():].rstrip()))
    def txt(e):                                          # the entry's text (sync.tsv): aligns rows to indexes, never their times
        return W.norm(SL.line(s.rows, (e[1], e[2], e[3] & 0xFFFF, e[4]), 0).split(":", 1)[1])[:20]
    def same(t, h):                                      # a row's first 20 cells vs the entry's text (either may be the shorter)
        return t.startswith(h) or h.startswith(t)
    a, bad, n = nxt - 1, [], 0
    for col, body in reversed(rows[-20:]):
        rb = W.RULE.match(body)
        head = W.norm((rb.group(1) if rb else body).split(" | ")[0])[:20]
        for k in range(body.count(" | ") + 1):            # a joined row: its first entry is k lines up (a text may hold " | " itself)
            if a - k in by and same(txt(by[a - k]), head):
                a -= k
                break
        while a in by and a > nxt - 8 and not same(txt(by[a]), head) and n == 0:
            a -= 1                                       # the newest lines may not be drawn yet (the bottom row is one of the last few)
        e, ep = by.get(a), by.get(a - 1)
        if e is None or ep is None or not same(txt(e), head):
            say(f"    {name}: alignment stops at abs {a}: row {head!r}, entry {txt(e) if e else None!r}; rows {[b[:25] for _, b in rows[-8:]]}; "
                f"entries {[(x[0], txt(x)) for x in ents[-8:]]}")
            break
        st = bool(starts_of([e]))
        want = (0 if e[1] == HDEF["AWTO_SYNC_EV_BEGIN"] else None) if st else SL.signed32(e[3]) - SL.signed32(ep[3])
        mt = re.fullmatch(r"([+-]) *(\d+(?:\.\d)?) (ms|s|h)", col.strip())
        if want is not None and mt:
            got = float(mt.group(2)) * {"ms": 1, "s": 1000, "h": 3_600_000}[mt.group(3)] * (-1 if mt.group(1) == "-" else 1)
            step = {"ms": 1, "s": 100 if "." in mt.group(2) else 1000, "h": 3_600_000}[mt.group(3)]
            if not (got <= want < got + step if want >= 0 else got - step < want <= got):
                bad.append(f"abs {a}: {col!r} vs {want} ms: {body[:40]}")
        n += 1
        a -= 1
    s.check(not bad and n >= 10, f"{name}: newest {n} rows' deltas = the raw entries' 32-bit ms steps, keyed by ring index (not text)", "; ".join(bad[:3]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/len/con_delta")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    out = a.out / a.bin.stem
    out.mkdir(parents=True, exist_ok=True)
    say(f"=== con_delta_sim {a.bin.name} ===")
    s = W.Sim(a.bin, mapp)
    s.bus.wait(FIRST_LINES_S)
    s.cmd(CMD_CON)
    s.check(s.until(lambda: s.bus.mode_state() == MODE_DISPLAY, W.ON_S + W.PS_S), "cold boot: DISPLAY SETTING")
    s.check(shot(s, "1-boot-display-setting", out) >= 1, "boot: the boot line is a red rule in view")
    s.check(s.until(lambda: s.bus.mode_state() == MODE_ACTIVE, W.ON_S), "cold boot: ACTIVE")
    s.bus.wait(W.DRAW_S)
    shot(s, "2-boot-active", out)
    reopen(s)                                                            # the settled episode drawn anew: the boot row first
    s.check(first_row(s).startswith("-- boot:"), "settled boot, console reopened: the first log row is the red boot row", first_row(s)[:80])
    seq_deltas(s, "2-boot-active", 0)
    hi = int.from_bytes(bytes(s.m.rd(s.m.addr("g_stAwtoHt") + UP_HI_OFF, 2)), "big")
    SL.inject_lines(s.m.rd, s.m.wr, s.a_sync, [FILLER] * OVERFLOW_N, bytes(s.m.rd(0xF6D0 + SL.DIAG_T2, 2)), hi)
    reopen(s)
    first = next((r[W.LOG_COL:] for r in s.text()[1:] if W.HEAD.match(r[W.LOG_COL:])), "")
    body = first[W.HEAD.match(first).end():] if first else ""
    s.check(body.startswith("-- boot:") and "lines not shown)" in body,
            f"boot overflowing the console ({OVERFLOW_N} more lines): the red boot row is still the first row", body.strip()[:90])
    shot(s, "2b-boot-overflow", out)
    seq_deltas(s, "2b-boot-overflow", 0)
    s.check(s.until(lambda: any(e[1] == HDEF["AWTO_SYNC_EV_SDONE"] for e in raw_entries(s, 0)[1]), W.ON_S), "boot: sync DONE")

    # AUTO key = a switch (K_SWITCH) plus its judge reset to search (K_LOST inside the unsettled switch): ONE red row
    s.cmd(CMD_CLOSE)
    s.bus.wait(W.DRAW_S)
    a0 = raw_entries(s, 0)[0]
    s.cmd(K_AUTO)
    s.until(lambda: s.bus.mode_state() != MODE_ACTIVE, MODE_SEARCH_S)
    s.check(s.until(lambda: any(e[1] == HDEF["AWTO_SYNC_EV_SDONE"] for e in raw_entries(s, a0)[1]), W.ON_S), "AUTO key: sync DONE again")
    ents = raw_entries(s, a0)[1]
    st = starts_of(ents)
    s.check(len(st) == 1 and st[0][2] == HDEF["AWTO_SYNC_K_SWITCH"], "AUTO key (switch + judge reset): exactly one episode start, the switch",
            str([(hex(e[1]), e[2], hex(e[4])) for e in st]))
    reopen(s)
    rr = rule_rows(s)
    s.check(len(rr) == 1 and rr[0].startswith("switch to") and first_row(s).startswith("-- switch to"),
            "AUTO key: one red row on the reopened console, the first log row", str(rr))

    # picture lost while ACTIVE and settled: the judge sees the source unstable, then the source is back
    a0 = raw_entries(s, 0)[0]
    s.m.patch_const("ScalerTMDSStableDetect", 0)
    s.check(s.until(lambda: any(e[1] == HDEF["AWTO_SYNC_EV_BEGIN"] and e[2] == HDEF["AWTO_SYNC_K_LOST"] for e in raw_entries(s, a0)[1]), MODE_SEARCH_S),
            "source unstable in ACTIVE: a picture-lost BEGIN")
    s.m.patch_const("ScalerTMDSStableDetect", 1)
    s.check(s.until(lambda: any(e[1] == HDEF["AWTO_SYNC_EV_SDONE"] for e in raw_entries(s, a0)[1]), W.ON_S), "picture lost -> resync: sync DONE written")
    ents = raw_entries(s, a0)[1]
    for e in ents:                                  # the episode as decoded lines (abs, fw ms, text): the log keeps the evidence
        say(f"    lost {e[0]} {SL.signed32(e[3])}:{SL.line(s.rows, (e[1], e[2], e[3] & 0xFFFF, e[4]), 0).split(':', 1)[1]}")
    st = starts_of(ents)
    k = [e[1] for e in ents]
    fail = next((i for i, e in enumerate(ents) if e[1] == HDEF["AWTO_SYNC_EV_SFAIL"] and e[2] == HDEF["AWTO_SD_WHY_LOST"]), None)
    done = next((i for i, e in enumerate(ents) if e[1] == HDEF["AWTO_SYNC_EV_SDONE"]), None)
    s.check(len(st) == 1 and st[0][2] == HDEF["AWTO_SYNC_K_LOST"], "picture lost: exactly one episode start", str([(hex(e[1]), e[2]) for e in st]))
    s.check(fail is not None and done is not None and fail < done, "picture lost: FAILED:signal lost, then DONE after the resync", str([hex(x) for x in k[:12]]))
    reopen(s)
    rr = rule_rows(s)
    s.check(len(rr) == 1 and rr[0].startswith("picture lost") and first_row(s).startswith("-- picture lost"),
            "picture lost: one red row on the reopened console, the first log row", str(rr))
    shot(s, "2c-picture-lost", out)
    s.mccs.set(0xD6, 4)
    s.check(s.until(lambda: s.power() == W.PWR_SAVING, W.PS_S), "VCP D6 = 4: power saving")
    s.cmd(W.K_SOURCE)
    s.check(s.until(lambda: s.power() == W.PWR_NORMAL, W.WAKE_S), "SOURCE key: woke (power NORMAL)")
    s.cmd(CMD_CON)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], W.DRAW_S)
    s.bus.wait(W.DRAW_S)
    s.check(shot(s, "3-wake", out) >= 1, "wake: the wake BEGIN is a red rule in view")
    s.mccs.tx(HT.packet(T0.timestamp(), OFS)[1:-1], reply=False)      # host time sync mid-run (host_time.py encoding)
    s.check(s.until(lambda: ht(s)["syncs"] == 1, W.DRAW_S), "host time sync 1 taken")
    hi = jump(s, GAP_UNITS)
    ms2 = bytes(s.m.rd(0xF6D0 + SL.DIAG_T2, 2))
    SL.inject_lines(s.m.rd, s.m.wr, s.a_sync, JOIN_PAIR, ms2, hi)        # a monitor pair after the gap: one joined row
    say(f"  fw clock + {GAP_UNITS} x 65.536 s, then {len(JOIN_PAIR)} monitor lines (one call) injected")
    reopen(s)                                                            # every row drawn with the host sync known
    shot(s, "4-gap-host-time", out)
    seq_deltas(s, "4-gap-host-time", 0)
    rs = s.con_rows(ht(s))
    gap = [r for r in rs if r["delta"] is not None and r["delta"] >= GAP_UNITS * 0x10000]
    s.check(len(gap) == 1 and not any(r["wrap"] for r in rs), "host: one row after the gap shows the full delta (32-bit ms), no wrap row",
            str([(SL.fmt_delta(r["delta"]), r["text"][:30]) for r in gap]))
    s.check(any(r["text"].startswith("monitor: IOSC 2001 | ") for r in rs), "host: the injected monitor pair is one row")
    txt = s.text()
    s.check(any(re.search(r"[ ]\d\d:\d\d:\d\d\.\d{3} \+ 13\d s:", x) for x in txt), "console: a row with host clock and the > 65 s delta (+ 13x s)")
    s.check(any("monitor: IOSC 2001 | " in x for x in txt), "console: the monitor pair on one row")
    h, lines = SL.decode(SL.read_ring(s.m.rd, s.a_sync), s.rows, whole=True)
    host = [ln for ln, _ in SL.ring_rows(h, lines, ht(s), int.from_bytes(ms2, "big"))]
    (out / "host.txt").write_text("\n".join(host) + "\n")
    say(f"{'PASS' if s.fails == 0 else 'FAIL'} con_delta_sim {a.bin.name}: {s.fails} failed (pages: {out})")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
