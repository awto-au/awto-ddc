#!/usr/bin/env python3
"""Unit-2 MCU state in ACTIVE vs power saving (awto-ddc#144): clock / cache XFRs, main-loop heartbeat vs Timer2 rate.

usage: ps_probe.py --unit 2 --map MAP [--secs 2] [--ps-n 3] [--regs FFE9,...] [--syms NAME:n,...] [--lp-s S] [--trace-s S] [--no-ps]
- ACTIVE sample, then test cmd 0x39 (#78 short levels) + host outputs off (Mutter PowerSaveMode 3) -> mode 6 -> power status
  SAVING (g_ucAwtoSyncPwr 3; one SDK search round later), optional loop profile / trace, --ps-n samples, sync ring;
  host outputs on, cmd 0x36 (levels back). Host always woken (finally).
- Sample = listed XDATA regs + map symbols (read-only, over 0x35) + diag heartbeat (0x14), Timer2 ISR (0x16), EXINT1 ISR (0x18)
  over --secs. Mode 6 is not power status SAVING: the wake poll runs only in the latter.
- --lp-s: power-saving-only loop profile (loop_prof.arm ps_only; -D_AWTO_LOOP_PROF=_ON image), no 0x35 traffic in the window.
Log: tmp/logs/ps_probe.log; JSON: tmp/regs/<serial>-ps-<YYYYMMDD-HHMMSS>.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
import wdt_test as W  # noqa: E402

ROOT = W.ROOT
LOG = ROOT / "tmp/logs/ps_probe.log"
# regdb RTD2795T-CG: MCU_CLK_DIV_R, MCU_CLK_CONTROL_1, MCU_CONTROL (flash div), MCU_CLOCK_CONTROL (mcu div), CACHE_FUNCTION / OPTION,
# SCA_WR_INTRVL, SCA_INF_PERIOD
REGS = "FFBD,FFE9,FFED,FFEE,FDA0,FDA1,FFF1,FFFB"
SYMS = "g_usAwtoPsPolls:2,g_usAwtoPsGap:2,g_ucAwtoPsWakeCon,g_ucAwtoSyncPwr,g_stPowerInfo:2"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="2")
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--secs", type=float, default=2.0)
    ap.add_argument("--regs", default=REGS)
    ap.add_argument("--syms", default=SYMS, help="map symbols NAME[:bytes], big-endian")
    ap.add_argument("--no-ps", action="store_true")
    ap.add_argument("--ps-n", type=int, default=3, help="PS samples of --secs each")
    ap.add_argument("--trace-s", type=float, default=0.0, help="fast power-status / pass / poll trace after power SAVING "
                    "(its 0x35 traffic slows the PS passes: debug-slave ISR)")
    ap.add_argument("--lp-s", type=float, default=0.0, help="power-saving-only loop profile over this window (LP image)")
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = LOG.open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); lf.write(line + "\n")

    t = W.UnitTarget(a.unit, a.map, say)
    regs = [int(x, 16) for x in a.regs.split(",")]
    syms = [s for s in a.syms.split(",") if s]

    def u16(off):
        b = X.read_bytes(t.io, t.diag + off, 2)
        return None if b is None else b[0] << 8 | b[1]

    def read_syms():
        sv = {}
        for s in syms:
            name, n = s.split(":") if ":" in s else (s, "1")
            ad = W.C.site_addr(t.map_text, name)
            b = None if ad is None else X.read_bytes(t.io, ad, int(n))
            sv[name] = None if b is None else b.hex()
        return sv

    def sample(tag):
        rv = {}
        for r in regs:
            b = X.read_bytes(t.io, r, 1)
            rv[f"{r:04X}"] = None if b is None else b[0]
        s0 = read_syms()
        c0, h0 = [u16(o) for o in (0x14, 0x16, 0x18)], time.monotonic()
        time.sleep(a.secs)                       # sample window; the firmware counts on its own
        c1, h1 = [u16(o) for o in (0x14, 0x16, 0x18)], time.monotonic()
        s1 = read_syms()
        d = [None if None in (x, y) else (y - x) & 0xFFFF for x, y in zip(c0, c1)]
        hms = round((h1 - h0) * 1000)
        say(f"{tag}: mode {t.mode()} regs " + " ".join(f"{k}={'--' if v is None else f'{v:02X}'}" for k, v in rv.items()))
        say(f"{tag}: syms " + " ".join(f"{k}={s0[k]}->{s1[k]}" for k in s0))
        say(f"{tag}: in {hms} ms host: heartbeat +{d[0]}, Timer2 ISR +{d[1]}, EXINT1 ISR +{d[2]}"
            + (f" -> {d[0] * 1000 / hms:.1f} passes/s" if d[0] is not None else ""))
        return {"mode": t.mode(), "regs": rv, "syms": [s0, s1], "host_ms": hms, "heartbeat": d[0], "t2": d[1], "exint1": d[2]}

    def trace(pa):
        """rows (host ms, power status, heartbeat, Timer2 ms, wake polls) as fast as 0x35 allows, for --trace-s;
        rates over row pairs that are both in power status SAVING (3) within one episode (polls not reset)"""
        ppa = W.C.site_addr(t.map_text, "g_usAwtoPsPolls")
        rows, h0 = [], time.monotonic()
        while time.monotonic() - h0 < a.trace_s:
            p = X.read_bytes(t.io, pa, 1)
            d = X.read_blocks(t.io, t.diag + 0x14, 4)
            n = X.read_bytes(t.io, ppa, 2)
            if None in (p, d, n):
                continue
            rows.append((round((time.monotonic() - h0) * 1000), p[0], d[0] << 8 | d[1], d[2] << 8 | d[3], n[0] << 8 | n[1]))
        hb = pl = ms = 0
        for r0, r1 in zip(rows, rows[1:]):
            if r0[1] == r1[1] == 3 and r1[4] >= r0[4]:
                hb += (r1[2] - r0[2]) & 0xFFFF; pl += r1[4] - r0[4]; ms += (r1[3] - r0[3]) & 0xFFFF
        say(f"trace: {len(rows)} rows in {a.trace_s} s; power SAVING rows {sum(r[1] == 3 for r in rows)}")
        say(f"trace: in SAVING {ms} fw ms: passes {hb} ({ms / hb if hb else 0:.2f} ms/pass), wake polls {pl} "
            f"({ms / pl if pl else 0:.2f} ms/poll)")
        prev = None
        for r in rows:
            if r[1] != prev:
                say(f"  trace +{r[0]} ms host: power {r[1]}, T2 {r[3]}, polls {r[4]}")
                prev = r[1]
        return rows

    def dpms(on):
        import host_dpms as H                  # off arms the guard (#159)
        H.on() if on else H.off(W.HOST_OFF_GUARD_S)

    out = {"serial": t.serial, "time": time.strftime('%Y-%m-%dT%H:%M:%S%z'), "map": str(a.map)}
    out["active"] = sample("ACTIVE")
    if not a.no_ps:
        try:
            t.cmd(0x39)
            dpms(False)
            t0, md = time.monotonic(), None
            while time.monotonic() - t0 < W.PS_S and md != 6:
                try:
                    md = t.mode()
                except OSError:
                    md = None
                time.sleep(0.2)                  # mode poll; PS_S bounds the wait
            say(f"mode {md} after {time.monotonic() - t0:.1f} s")
            # mode 6 -> power status SAVING after one search round (SysMode GET_SOURCE_SWITCH_FINISH): D1 DP 3 s + D2 / D3 2 s
            # dwell (RL6449_Project.h) = 7 s x 1.25 -> 9 s
            pa, pw, t1 = W.C.site_addr(t.map_text, "g_ucAwtoSyncPwr"), None, time.monotonic()
            while md == 6 and pa is not None and time.monotonic() - t1 < 9.0 and pw != 3:
                b = X.read_bytes(t.io, pa, 1)
                pw = None if b is None else b[0]
                time.sleep(0.05)                 # 50 ms: power status poll
            say(f"power status {pw} {time.monotonic() - t1:.2f} s after mode 6")
            if md == 6 and a.lp_s:
                import loop_prof as LP
                lb = LP.base_of(t.map_text)
                if lb is None:
                    say("loop profile: image without -D_AWTO_LOOP_PROF=_ON")
                elif LP.arm(t.io, lb, ps_only=True):
                    time.sleep(a.lp_s)           # no 0x35 traffic: the debug-slave ISR would load the PS passes
                    LP.report(t.io, lb, say, t.serial, "power saving only", a.lp_s)
                    say("after loop profile: " + " ".join(f"{k}={v}" for k, v in read_syms().items()))
            if md == 6 and a.trace_s:
                out["trace"] = trace(pa)
            if md == 6:
                out["ps"] = [sample(f"PS{i}") for i in range(a.ps_n)]
                import re
                import sync_log as SL
                ring = int(re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stAwtoSync\b", t.map_text, re.M).group(1), 16) & 0xFFFF
                raw = X.read_blocks(t.io, ring, SL.HDR + SL.N * SL.EV)
                out["ring"] = SL.decode(raw, SL.load_rows(SL.tsv_for(a.map)), whole=True)[1] if raw else []
                for ln in out["ring"]:
                    say(f"  ring {ln}")
        finally:
            dpms(True)
            t.cmd(0x36)
    p = ROOT / f"tmp/regs/{t.serial}-ps-{time.strftime('%Y%m%d-%H%M%S')}.json"
    p.write_text(json.dumps(out, indent=1))
    say(f"-> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
