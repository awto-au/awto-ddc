#!/usr/bin/env python3
"""OSD write-rate sweep on the test unit or in the firmware sim (docs/osd-write-sweep.md).

usage: osd_sweep.py --bus B --serial S --map MAP [--bin BIN] [--sim] [--continue-on-fail] GROUP|CASE [...]
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c: g_stAwtoOsw, AwtoOswRun). Per case the firmware sets FFF1 / FFFB / FFBC
  (legal ranges only), times N bytes x reps through one write path into the unused top of the OSD SRAM, restores the three registers
  before the op returns (a stalled main loop = WDT reset); the host then reads M1 and M2 back (circuit off, scale-up off, overlay off,
  0x3A33[4], two reads) at the restored values and compares with the pattern. Pass = 0 bad bytes, registers read back as requested and
  restored, no new FIFO flag, op finished inside its limit.
  GROUPS: base fff1 fffb ffbc burst state size combo (combo reads the best passing values from the TSV) hold (setting held while the savers run)
  Log ./tmp/logs/osd_sweep.log, TSV ./tmp/logs/osd_sweep.tsv.
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import osd_hw_test as H
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/osd_sweep.log"
TSV = ROOT / "tmp/logs/osd_sweep.tsv"

# StAwtoOsw (fw/test/testcmd.c), big endian
(W_GO, W_SEQ, W_STATE, W_REFUSE, W_APPLY, W_FFF1, W_FFFB, W_FFBC, W_MODE, W_FLAGS, W_SEED, W_REPS, W_ADDR, W_N, W_CHUNK, W_HOLD, W_MS,
 W_NOW_F1, W_NOW_FB, W_NOW_BC, W_STK_F1, W_STK_FB, W_STK_BC, W_PASSES, W_RESTARTS, W_FIFO_PRE, W_FIFO_POST, W_NOWMS) = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 35, 40)
FIFO_N = 5
W_SIZE = 42
OP_RUN, OP_HOLD, OP_RESTORE = 1, 2, 3
ST_DONE, ST_REFUSED, ST_TIMEOUT, ST_HELD, ST_AUTO, ST_RESTORED = 1, 2, 3, 4, 5, 6
REFUSE = {0: "none", 1: "range", 2: "hold active", 3: "address outside the SRAM top", 4: "burst chunk / N"}
M_SDK, M_DIRECT, M_TRIPLE, M_BURST, M_B1, M_ADDR, M_MASK = range(7)
MODE_NAMES = {M_SDK: "ScalerOsdDataPort", M_DIRECT: "direct loop", M_TRIPLE: "direct triples", M_BURST: "burst XRAM->port", M_B1: "B1 only",
              M_ADDR: "address set only", M_MASK: "triples + bit_block"}
A_F1, A_FB, A_BC = 1, 2, 4
F_EA_OFF, F_SU_OFF, F_OVL_OFF, F_DB_ON = 1, 2, 4, 8
FFF1_MASK, FFBC_MASK = 0x8F, 0x1F                    # regdb: FFF1 bit 7 + [3:0], FFBC [4:0]; the rest reserved
ADDR_TOP, ADDR_END = 0x2000, 0x3000                  # words: unused top of the 12288-word SRAM
N_MAX, N_DEF, N_BURST = 8192, 1848, 1782             # 1848 = 616 words (as clk_sweep); 1782 = 11 x 162 = 33 x 54
GLYPH, BUF = 54, 54                              # XDATA allows one glyph of XRAM burst source
FIFO_NAMES = ["dispM1", "dispM2", "capM1", "capM2", "status0"]
FIFO_MASK = [0x03, 0x03, 0x03, 0x03, 0x63]           # underflow / overflow bits; STATUS0 also ivs_error / ihs_error
# timing: target time of the timed section (ms resolution of AwtoMs: 0.7 % at 150 ms); fw guard AWTO_OSW_MAX_MS
TARGET_MS = 150.0
FW_MAX_MS = 1000.0
PASS_WORST_S = 0.045                                 # one pass of N_MAX at the slowest path (ScalerOsdDataPort 3.79 us/B at stock 87.7 MHz = 31 ms) x 1.4
OP_FIXED_S = 0.25                                    # main-loop pass + I2C of the param write
LIMIT_S = 1.25 * (FW_MAX_MS / 1000 + PASS_WORST_S) + OP_FIXED_S   # fw stops after the pass that passes 1000 ms: expiry = FAIL with the elapsed time
EST_US = {M_SDK: 3.8, M_DIRECT: 1.1, M_TRIPLE: 1.1, M_BURST: 1.0, M_B1: 1.1, M_ADDR: 6.0, M_MASK: 1.1}   # us per byte (per set for ADDR): reps estimate only
POLL_PACE_S = 0.05                                   # between polls of a running op (as clk_sweep: back-to-back I2C polls load the DDC ISRs)
HB_WINDOW_S = 2.0
HB_TOL_PCT = 1.5
HOLD_FW_MS = 25000                                   # fw-side restore of a held setting; host normally restores first
SAVER_SCOPE2 = H.SAVER_SCOPE2


def say(s: str) -> None:
    _log_line(s, LOG)


@dataclass(frozen=True)
class Case:
    name: str
    mode: int = M_TRIPLE
    fff1: int | None = None
    fffb: int | None = None
    ffbc: int | None = None
    flags: int = 0
    chunk: int = 0
    n: int = 0                                       # 0 = default for the mode
    verify: bool = True

    @property
    def apply(self) -> int:
        return (A_F1 if self.fff1 is not None else 0) | (A_FB if self.fffb is not None else 0) | (A_BC if self.ffbc is not None else 0)

    @property
    def nbytes(self) -> int:
        return self.n or (N_BURST if self.mode == M_BURST else N_DEF)


def check_case(c: Case) -> str | None:
    """Host-side mirror of the firmware's refusal rules: nothing outside the envelope is ever sent."""
    if c.fff1 is not None and (c.fff1 & ~FFF1_MASK & 0xFF):
        return f"FFF1 0x{c.fff1:02X} outside 0x{FFF1_MASK:02X}"
    if c.fffb is not None and not 0 <= c.fffb <= 0xFF:
        return "FFFB outside 0..255"
    if c.ffbc is not None and not 0 <= c.ffbc <= FFBC_MASK:
        return f"FFBC outside 0..{FFBC_MASK}"
    if not 0 < c.nbytes <= N_MAX or (c.mode != M_ADDR and c.nbytes % 3):
        return "N out of range / not a multiple of 3"
    if c.mode == M_BURST and (c.chunk != GLYPH or c.nbytes % c.chunk):
        return "burst chunk must be 54 or 162 and divide N"
    if ADDR_TOP + (c.nbytes + 2) // 3 > ADDR_END:
        return "outside the SRAM top"
    return None


def cases() -> dict[str, list[Case]]:
    g: dict[str, list[Case]] = {}
    g["base"] = ([Case(f"base_{k}", m) for k, m in (("sdk", M_SDK), ("direct", M_DIRECT), ("triple", M_TRIPLE), ("b1", M_B1), ("mask", M_MASK))]
                 + [Case("base_addr", M_ADDR, verify=False, n=N_DEF)]
                 + [Case("base_burst54", M_BURST, chunk=GLYPH)])
    g["fff1"] = ([Case(f"fff1_sel{k}", fff1=k) for k in range(16)] + [Case("fff1_int1", fff1=0x80)])
    g["fffb"] = [Case(f"fffb_{k}", fffb=k) for k in (0, 1, 2, 3, 4, 6, 8, 16, 32, 64, 128, 255)]
    g["ffbc"] = [Case(f"ffbc_{k}", ffbc=k) for k in (15, 16, 24, 31, 8, 4, 2, 1, 0)]        # reset value 0x0F first, 0 last (its meaning is not documented)
    g["burst"] = [Case(f"burst{ch}_gap{k}", M_BURST, fffb=k, chunk=ch) for ch in (GLYPH,) for k in (1, 2, 3, 4, 6, 8, 9, 10, 11, 12, 14, 16, 24, 32, 40)]
    g["burstrep"] = [Case(f"burstrep{i}_gap{k}", M_BURST, fffb=k, chunk=GLYPH, flags=fl) for k in (9, 10, 11, 12) for i, fl in enumerate((0, 0, F_EA_OFF))]
    g["state"] = ([Case("st_ea_off", flags=F_EA_OFF), Case("st_su_off", flags=F_SU_OFF), Case("st_ovl_off", flags=F_OVL_OFF),
                   Case("st_db_on", flags=F_DB_ON), Case("st_all_off", flags=F_EA_OFF | F_SU_OFF | F_OVL_OFF)]
                  + [Case("st_sdk_ea_off", M_SDK, flags=F_EA_OFF), Case("st_burst54_ea_off", M_BURST, chunk=BUF, flags=F_EA_OFF)])
    g["size"] = ([Case(f"size_triple_{n}", n=n) for n in (1848, 3696, 8184)] + [Case(f"size_sdk_{n}", M_SDK, n=n) for n in (1848, 8184)]
                 + [Case(f"size_burst54_{n}", M_BURST, chunk=BUF, n=n) for n in (1782, 8100)]
                 + [Case("size_addr_100", M_ADDR, n=100, verify=False), Case("size_addr_1000", M_ADDR, n=1000, verify=False)])
    return g


GROUPS = list(cases()) + ["combo", "hold", "holdbc", "autorevert"]


def reps_for(c: Case, sim: bool) -> int:
    if sim:
        return 2
    return max(1, min(255, int(TARGET_MS * 1000 / (c.nbytes * EST_US[c.mode]))))


def be(raw: bytes, o: int, n: int = 2) -> int:
    return int.from_bytes(raw[o:o + n], "big")


class Ctx:
    def __init__(self, dev, sw, sim: bool):
        self.dev, self.sw, self.sim = dev, sw, sim
        self.stock = None


def pace(sw) -> None:
    if isinstance(sw, H.Unit):
        t0 = time.monotonic()
        while time.monotonic() - t0 < POLL_PACE_S:
            pass
    else:
        sw.idle()


def send(ctx, go: int, limit_s: float, label: str, params: bytes | None = None) -> bytes | None:
    sw = ctx.sw
    if params is not None:
        sw.wr(W_APPLY, params)
    seq0 = sw.rd(W_SEQ, 1)[0]
    sw.wr(W_GO, bytes([go]))
    t0 = sw.now()
    while True:
        pace(sw)
        try:
            h = sw.rd(W_GO, 2)
        except RuntimeError:
            h = None
        if h is not None and h[0] == 0 and h[1] != seq0:
            return sw.rd(0, W_SIZE)
        if sw.now() - t0 > limit_s:
            say(f"  FAIL {label}: no answer after {sw.now() - t0:.2f} s (limit {limit_s:.2f} s)")
            return None


def params(c: Case, reps: int, seed: int, hold_ms: int = 0) -> bytes:
    """W_APPLY .. W_HOLD (bytes 4..19)."""
    head = bytes([c.apply, (c.fff1 or 0) & 0xFF, (c.fffb or 0) & 0xFF, (c.ffbc or 0) & 0xFF, c.mode, c.flags, seed, reps])
    return head + (ADDR_TOP).to_bytes(2, "big") + c.nbytes.to_bytes(2, "big") + c.chunk.to_bytes(2, "big") + hold_ms.to_bytes(2, "big")


def tsv(row: dict) -> None:
    keys = ["case", "mode", "fff1", "fffb", "ffbc", "flags", "n", "reps", "ms", "us_per_b", "bad_m1", "bad_m2", "fifo_new", "restart_max", "pass", "note"]
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(["time"] + keys) + "\n")
        f.write("\t".join([isostamp.now()] + [("%.4g" % row[k]) if isinstance(row.get(k), float) else str(row.get(k, "")) for k in keys]) + "\n")


def fifo_new(pre: bytes, post: bytes) -> str:
    out = []
    for i, name in enumerate(FIFO_NAMES):
        d = post[i] & FIFO_MASK[i] & ~pre[i]
        if d:
            out.append(f"{name}:{d:02X}")
    return ",".join(out)


def run_case(ctx, c: Case, seed: int = 0x3C) -> dict:
    row = {"case": c.name, "mode": MODE_NAMES[c.mode], "fff1": c.fff1, "fffb": c.fffb, "ffbc": c.ffbc, "flags": c.flags, "n": c.nbytes, "pass": False}
    bad = check_case(c)
    if bad:
        row["note"] = "host refused: " + bad
        say(f"  FAIL {c.name}: {row['note']}")
        return row
    reps = reps_for(c, ctx.sim)
    row["reps"] = reps
    raw = send(ctx, OP_RUN, LIMIT_S, c.name, params(c, reps, seed))
    if raw is None:
        row["note"] = "no answer"
        return row
    st = raw[W_STATE]
    ms = be(raw, W_MS)
    if st == ST_REFUSED:
        row["note"] = "fw refused: " + REFUSE.get(raw[W_REFUSE], str(raw[W_REFUSE]))
        say(f"  FAIL {c.name}: {row['note']}")
        return row
    passes = raw[W_PASSES]
    row["ms"] = ms
    per = c.nbytes * passes
    row["us_per_b"] = ms * 1000.0 / per if per else float("nan")
    row["restart_max"] = raw[W_RESTARTS]
    row["fifo_new"] = fifo_new(raw[W_FIFO_PRE:W_FIFO_PRE + FIFO_N], raw[W_FIFO_POST:W_FIFO_POST + FIFO_N])
    want = (raw[W_STK_F1] & ~FFF1_MASK & 0xFF | (c.fff1 if c.fff1 is not None else raw[W_STK_F1] & FFF1_MASK),
            c.fffb if c.fffb is not None else raw[W_STK_FB],
            raw[W_STK_BC] & ~FFBC_MASK & 0xFF | (c.ffbc if c.ffbc is not None else raw[W_STK_BC] & FFBC_MASK))
    got = (raw[W_NOW_F1], raw[W_NOW_FB], raw[W_NOW_BC])
    # burst without FFFB: the burst sets FFFB itself (gap 3), read back is taken before it
    regs_ok = got == want
    note = []
    if not regs_ok:
        note.append(f"regs applied FFF1/FFFB/FFBC {got} want {want}")
    if st == ST_TIMEOUT:
        note.append(f"TIMEOUT after {passes} of {reps} passes")
    r1 = r2 = 0
    if c.verify:
        for mem, fl in (("M1", 0), ("M2", H.F_M2)):
            v = H.op(ctx.dev, H.OP_VERIFY, H.lim_read(c.nbytes), flags=H.F_REPEAT | fl, seed=seed, addr=ADDR_TOP, n=c.nbytes, label=c.name + " verify")
            if mem == "M1":
                r1 = v["bad"]
            else:
                r2 = v["bad"]
            if v["bad"]:
                note.append(f"{mem} first bad {v['first']} {v['badb'].hex()}")
    row["bad_m1"], row["bad_m2"] = r1, r2
    chk = send(ctx, OP_RUN, LIMIT_S, c.name + " revert-check", params(Case("chk", M_ADDR, n=3, verify=False), 1, seed))
    revert_ok = chk is not None and (chk[W_NOW_F1], chk[W_NOW_FB], chk[W_NOW_BC]) == (raw[W_STK_F1], raw[W_STK_FB], raw[W_STK_BC])
    if not revert_ok:
        note.append("registers NOT restored: " + (chk[W_NOW_F1:W_NOW_BC + 1].hex() if chk else "no answer"))
    row["pass"] = bool(regs_ok and st in (ST_DONE,) and r1 == 0 and r2 == 0 and revert_ok and not row["fifo_new"])
    row["note"] = "; ".join(note)
    say(f"  {'PASS' if row['pass'] else 'FAIL'} {c.name}: {MODE_NAMES[c.mode]} {c.nbytes} B x {passes} = {ms} ms = {row['us_per_b']:.3f} us/B"
        f"{' (' + ('%.2f' % (row['us_per_b'] * 3)) + ' us/word)' if c.mode != M_ADDR else ''}; "
        f"FFF1/FFFB/FFBC {got[0]:02X}/{got[1]:02X}/{got[2]:02X} (stock {raw[W_STK_F1]:02X}/{raw[W_STK_FB]:02X}/{raw[W_STK_BC]:02X}); "
        f"bad M1 {r1} M2 {r2}; fifo new [{row['fifo_new']}]; burst restarts {raw[W_RESTARTS]}" + (f"; {row['note']}" if row["note"] else ""))
    return row


def best_values(rows: list[dict]) -> dict[str, int]:
    """Lowest us/B passing value per register from the rows of the sweeps (direct triples)."""
    best: dict[str, tuple[float, int]] = {}
    for r in rows:
        if not r.get("pass") or r.get("mode") != MODE_NAMES[M_TRIPLE]:
            continue
        for reg in ("fff1", "fffb", "ffbc"):
            v = r.get(reg)
            if v not in (None, "", "None") and sum(r.get(k) not in (None, "", "None") for k in ("fff1", "fffb", "ffbc")) == 1:
                us = float(r["us_per_b"])
                if reg not in best or us < best[reg][0]:
                    best[reg] = (us, int(v))
    return {k: v[1] for k, v in best.items()}


def read_tsv_rows() -> list[dict]:
    if not TSV.exists():
        return []
    lines = TSV.read_text().splitlines()
    keys = lines[0].split("\t")
    last: dict[str, dict] = {}                         # latest row per case
    for ln in lines[1:]:
        d = dict(zip(keys, ln.split("\t")))
        d["pass"] = d.get("pass") == "True"
        last[d.get("case", "")] = d
    return list(last.values())


def combo_cases(best: dict[str, int]) -> list[Case]:
    ks = [k for k in ("fff1", "fffb", "ffbc") if k in best]
    out = []
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            out.append(Case(f"combo_{ks[i]}_{ks[j]}", **{ks[i]: best[ks[i]], ks[j]: best[ks[j]]}))
    if len(ks) == 3:
        out.append(Case("combo_all3", **{k: best[k] for k in ks}))
        out.append(Case("combo_all3_burst54", M_BURST, chunk=BUF, **{k: best[k] for k in ks}))
    return out


def wait(dev, s: float) -> None:
    t0 = dev.now()
    while dev.now() - t0 < s:
        dev.idle()


def hold_case(ctx, c: Case, hold_ms: int = HOLD_FW_MS) -> dict:
    """Setting held while the main loop runs: heartbeat vs the host clock, link reads, Scope 2 frames per second; then restore."""
    row = {"case": c.name, "mode": "held", "fff1": c.fff1, "fffb": c.fffb, "ffbc": c.ffbc, "pass": False}
    raw = send(ctx, OP_HOLD, LIMIT_S, row["case"], params(c, 1, 0, hold_ms))
    if raw is None or raw[W_STATE] != ST_HELD:
        row["note"] = f"not held: state {raw[W_STATE] if raw else None} refuse {raw[W_REFUSE] if raw else None}"
        say(f"  FAIL {row['case']}: {row['note']}")
        return row
    notes = []
    sw = ctx.sw
    a0, t0 = be(sw.rd(W_NOWMS, 2), 0), sw.now()
    wait(sw, HB_WINDOW_S)
    a1, t1 = be(sw.rd(W_NOWMS, 2), 0), sw.now()
    ratio = ((a1 - a0) & 0xFFFF) / (1000 * (t1 - t0))
    hb_ok = abs(ratio - 1) * 100 <= HB_TOL_PCT or ctx.sim
    reads_ok = True
    for _ in range(100):
        try:
            sw.rd(0, W_SIZE)
        except RuntimeError:
            reads_ok = False
            break
        pace(sw)
    fps = None
    if not ctx.sim:
        try:
            fps = fps_scope2(ctx.dev)
        except (TimeoutError, RuntimeError) as e:
            notes.append(f"scope2 fps: {e}")
    end = send(ctx, OP_RESTORE, LIMIT_S, row["case"] + " restore")
    ok_rest = end is not None and end[W_STATE] == ST_RESTORED
    row["pass"] = bool(hb_ok and reads_ok and ok_rest)
    row["note"] = "; ".join(notes)
    say(f"  {'PASS' if row['pass'] else 'FAIL'} {row['case']}: heartbeat {ratio:.4f}, 100 link reads {'ok' if reads_ok else 'FAILED'}, Scope 2 "
        f"{('%.2f' % fps) if fps is not None else 'n/a'} frames/s, restored {ok_rest}" + (f"; {row['note']}" if row["note"] else ""))
    return row


AUTO_HOLD_MS = 1500                                  # autorevert: firmware limit (the status read-back after the op takes up to ~0.5 s on the link); the host never sends a restore
AUTO_WAIT_S = 3.0                                    # 2 x the limit: the main loop (<= 20 ms per pass) must have restored by then


def autorevert_case(ctx, c: Case) -> dict:
    """The held setting must restore by itself at the hold limit (host silent): proves the firmware-side revert."""
    row = {"case": c.name, "mode": "autorevert", "fff1": c.fff1, "fffb": c.fffb, "ffbc": c.ffbc, "pass": False}
    raw = send(ctx, OP_HOLD, LIMIT_S, c.name, params(c, 1, 0, AUTO_HOLD_MS))
    if raw is None or raw[W_STATE] != ST_HELD:
        row["note"] = "not held"
        say(f"  FAIL {c.name}: {row['note']}")
        return row
    applied = (raw[W_NOW_F1], raw[W_NOW_FB], raw[W_NOW_BC])
    wait(ctx.sw, AUTO_WAIT_S)
    end = send(ctx, OP_RUN, LIMIT_S, c.name + " check", params(Case("chk", M_ADDR, n=3, verify=False), 1, 0))
    back = end is not None and end[W_STATE] == ST_DONE and (end[W_NOW_F1], end[W_NOW_FB], end[W_NOW_BC]) == (raw[W_STK_F1], raw[W_STK_FB], raw[W_STK_BC])
    row["pass"] = bool(back)
    say(f"  {'PASS' if back else 'FAIL'} {c.name}: applied FFF1/FFFB/FFBC {applied[0]:02X}/{applied[1]:02X}/{applied[2]:02X}, host silent {AUTO_WAIT_S} s "
        f"after a {AUTO_HOLD_MS} ms hold, registers {'back to stock' if back else 'NOT restored'}")
    return row


FPS_SETTLE_S, FPS_WINDOW_S = 2.5, 6.0                # first Scope 2 frame hidden (clk_sweep.py)


def fps_scope2(dev) -> float:
    """Scope 2 frames per second from the firmware frame counter over a 6 s window; saver off afterwards."""
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_SCOPE2, label="scope2 on")
    H.wait_scope2(dev)
    wait(dev, FPS_SETTLE_S)
    r0 = H.op(dev, H.OP_REGS, H.lim_read(0), label="frame0")
    t0 = dev.now()
    wait(dev, FPS_WINDOW_S)
    r1 = H.op(dev, H.OP_REGS, H.lim_read(0), label="frame1")
    t1 = dev.now()
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=H.SAVER_OFF, label="saver off")
    return ((r1["frame"] - r0["frame"]) & 0xFFFF) / (t1 - t0)


class _CkCtx:
    def __init__(self, dev):
        self.dev = dev
        self.sim = False
        self.stock_crc = None
        self.stock_tick = None
        self.pll_khz = None


def types_ctx(ctx):
    return _CkCtx(ctx.dev)


def run(ctx, names: list[str], cont: bool) -> int:
    table = cases()
    fails = 0
    for n in names:
        say(f"##### {n}")
        if n == "combo":
            todo = combo_cases(best_values(read_tsv_rows() if not getattr(ctx, "rows", None) else ctx.rows))
            if not todo:
                say("  no passing single-register rows in the TSV: run base fff1 fffb ffbc first")
        elif n == "hold":
            best = best_values(read_tsv_rows())
            todo = [Case(f"hold_{k}", **{k: v}) for k, v in best.items()] + ([Case("hold_all", **best)] if len(best) > 1 else [])
        elif n == "holdbc":
            todo = [Case(f"holdbc_{k}", ffbc=k) for k in (14, 12, 10, 8, 6, 5)]
        elif n == "autorevert":
            todo = [Case("autorevert", fffb=0x05)]
        elif n in table:
            todo = table[n]
        else:
            todo = [c for lst in table.values() for c in lst if c.name == n]
            if not todo:
                raise SystemExit(f"unknown group / case {n}; groups {GROUPS}")
        for c in todo:
            try:
                row = hold_case(ctx, c, 6000 if n == "holdbc" else HOLD_FW_MS) if n in ("hold", "holdbc") else autorevert_case(ctx, c) if n == "autorevert" else run_case(ctx, c)
            except (TimeoutError, RuntimeError) as e:
                row = {"case": c.name, "pass": False, "note": f"comm: {e}"}
                say(f"  FAIL comm lost at {c.name}: {e}")
            tsv(row)
            if not row["pass"]:
                fails += 1
                if not cont:
                    say(f"stop after the first failed case ({c.name}); the firmware restored the registers (or the WDT reset the unit)")
                    return fails
    say(f"sweep done: {fails} failed")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--serial")
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--continue-on-fail", action="store_true")
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    binp = a.bin or a.map.with_suffix(".bin")
    if a.sim:
        import clk_sweep as C
        global TSV
        TSV = ROOT / "tmp/logs/osd_sweep_sim.tsv"          # the sim does not model the registers: its numbers are not the unit's
        dev, _ck, _rd, _sa = C.make_sim(binp, a.map)
        sw = copy.copy(dev)
        sw.base = dev.m.addr("g_stAwtoOsw")
        ctx = Ctx(dev, sw, True)
        return 1 if run(ctx, a.names, a.continue_on_fail) else 0
    import dbg_link
    import i2cbus
    import sync_log as S
    i2cbus.require_unit(a.bus, a.serial)
    with dbg_link.linked(a.bus, 10):
        dev = H.Unit(a.bus, a.map)
        sw = copy.copy(dev)
        sw.base = S.sym(a.map, "g_stAwtoOsw")
        ctx = Ctx(dev, sw, False)
        try:
            fails = run(ctx, a.names, a.continue_on_fail)
        finally:
            try:
                send(ctx, OP_RESTORE, LIMIT_S, "final restore")
            except Exception as e:  # noqa: BLE001
                say(f"final restore: {e}")
            dev.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
