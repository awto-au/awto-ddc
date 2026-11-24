#!/usr/bin/env python3
"""Soak of one clock step on the test unit with the savers cycling (docs/clock-sweep.md "Soak").

usage: clk_soak.py --bus B --serial S --map MAP [--bin BIN] STEP MINUTES
  Image built with -D _AWTO_OSD_HWTEST. STEP = a name from clk_sweep.STEPS (stock = the control run).
  The step is held by the firmware for HOLD_S and kept alive by a KEEP op every KEEP_S: the host's silence or a firmware stall = revert / WDT reset.
  Every PERIOD_S: firmware checks again (CRC passes, XDATA, delays), link reads, heartbeat vs the host clock, IOSC trim registers, next saver
  (Scope 2, Asteroids, Pac-Man = VCP 0xEB 4 / 8 / 2). A reset is logged, the unit relinked, the step applied again.
  Log ./tmp/logs/clk_soak.log, one TSV line per period ./tmp/logs/clk_soak.tsv.
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_sweep as C
import isostamp
import osd_hw_test as H
from _log import shared
from _repo import ROOT

LOG = ROOT / "tmp/logs/clk_soak.log"
TSV = ROOT / "tmp/logs/clk_soak.tsv"
SAVERS = (4, 8, 2)                         # Scope 2, Asteroids, Pac-Man (VCP 0xEB values)
PERIOD_S = 30.0                            # Dan's brief: checks every 30 s
KEEP_S = 4.0                               # KEEP op period; HOLD_S / KEEP_S = 5 missed keeps before the firmware reverts
HOLD_S = 20.0
LINK_READS = 100                           # block reads per period
MAX_RESETS = 3                             # stop after this many resets: the step is not stable


def say(s: str) -> None:
    shared(LOG, echo=None).say(s)
    C.say(s)


def apply_step(ctx, name: str) -> bytes | None:
    f, f2, m, fl = C.STEPS[name]
    scale = max(1.0, C.STOCK_MHZ / (350.8 / (f * m)), 43.85 / (350.8 / (f * f2)))
    r = C.send(ctx, C.OP_APPLY, C.APPLY_LIMIT_S * scale, f, f2, m, fl, hold_s=HOLD_S, label=f"apply {name}", name_=name)
    if r is None or (C.be(r, C.C_PLL, 4) == 0 and r[C.C_STATE] == 0):
        return None
    return r if r[C.C_STATE] == C.ST_HELD else None


def keep_alive(ctx) -> bool:
    return C.send(ctx, C.OP_KEEP, 2.0, label="keep") is not None


def period_check(ctx, n: int, t_s: float, name: str, stats: dict) -> None:
    """One period: firmware checks again, link reads, heartbeat; failures are counted, not fatal (a reset is)."""
    ck = ctx.ck
    r = C.send(ctx, C.OP_CHECK, 6.0 * (350.8 / 87.7 if name == "stock" else 1), label="check")
    if r is None or (C.be(r, C.C_PLL, 4) == 0 and r[C.C_STATE] == 0):
        raise TimeoutError("no answer to the check op")
    crc = r[C.C_CRC:C.C_CRC + 4].hex()
    d5, dx = C.be(r, C.C_D5P, 2), C.be(r, C.C_DXP, 2)
    bad = []
    if crc != ctx.stock_crc or r[C.C_CRCBAD] != 0:
        bad.append(f"crc {crc} want {ctx.stock_crc} differing passes {r[C.C_CRCBAD]}")
    if C.be(r, C.C_XDBAD, 2) != 0:
        bad.append(f"xdata bad bytes {C.be(r, C.C_XDBAD, 2)}")
    if not (C.DELAY_PCT_MIN <= d5 <= C.DELAY_PCT_MAX and C.DELAY_PCT_MIN <= dx <= C.DELAY_PCT_MAX):
        bad.append(f"delay {d5} / {dx} %")
    if r[C.C_STATE] != C.ST_HELD:
        bad.append(f"state {r[C.C_STATE]} (step not held)")
    n_fail, seen = 0, {}
    for _ in range(LINK_READS):
        try:
            b = ck.rd(C.C_CRC, 24)
        except RuntimeError:
            n_fail += 1
            continue
        seen[b] = seen.get(b, 0) + 1
    link_bad = n_fail + sum(seen.values()) - max(seen.values(), default=0)
    if link_bad:
        bad.append(f"link {link_bad} of {LINK_READS} reads failed / differing")
    a0, t0 = C.be(ck.rd(C.C_NOW, 2), 0, 2), ck.now()
    C.wait(ck, C.WALL_S)
    a1, t1 = C.be(ck.rd(C.C_NOW, 2), 0, 2), ck.now()
    ratio = ((a1 - a0) & 0xFFFF) / 1000.0 / (t1 - t0)
    if abs(ratio - 1) * 100 > C.WALL_TOL_PCT:
        bad.append(f"heartbeat {ratio:.4f}")
    io = C.iosc(ctx, f"{name} t={t_s:.0f}s")
    stats["checks"] += 1
    stats["bad"] += bool(bad)
    stats["iosc"].append((t_s, io["cnt"] if io else None))
    say(f"  period {n} t={t_s:.0f}s {name}: {'PASS' if not bad else 'FAIL ' + '; '.join(bad)} (crc {crc}, {C.be(r, C.C_CRCMS, 2)} ms/pass, delay {d5}/{dx} %, link {LINK_READS - link_bad}/{LINK_READS}, heartbeat {ratio:.4f}, savers frames Ast {C.be(r, C.C_AST, 2)} Sc1 {C.be(r, C.C_SC, 2)})")
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("time\tstep\tperiod\tt_s\tpass\tcrc_ms\td5\tdx\tlink_bad\theartbeat\tiosc_cnt\n")
        f.write("\t".join([isostamp.now(), name, str(n), f"{t_s:.0f}", str(not bad), str(C.be(r, C.C_CRCMS, 2)), str(d5), str(dx), str(link_bad), f"{ratio:.4f}", str(io["cnt"] if io else "")]) + "\n")


NV_FIELDS = {"flush": 6, "item_wr": 8, "ops": 10, "erase": 16, "bytes": 18}      # StAwtoNv (RL6449_Project.h), big endian
NV_SETTLE_S = 4.0                          # the save command commits at once (no debounce); one flush = <= ~0.5 s of halts, x 8


def nv_counters(ctx, base: int) -> dict:
    b = ctx.rdabs(base, 20)
    return {k: int.from_bytes(b[o:o + 2], "big") for k, o in NV_FIELDS.items()}


def nvram_test(ctx, name: str, a) -> bool:
    """Production settings write path at the held step: change a harmless setting through the firmware mailbox, save, read back, restore, save."""
    import settings_cli as SC
    import sync_log as S
    nvb = S.sym(a.map, "g_stAwtoNv")
    wrap_addr = S.sym(a.map, "g_ucAwtoFlCk")
    C.xwr(ctx, wrap_addr, a.nvram)
    say(f"  NVRAM test at {name}: MOVX cycles around FF60 = {'9 (SDK wrapper)' if a.nvram else '2 (default, as the production build)'}")
    box = SC.Box(ctx.dev.io, Path(a.map).read_text(errors="replace"))
    row = SC.row_of("sharpness")
    ok = True
    try:
        v0 = box.get_row(row)
        for step, v in (("change", v0 + 1 if v0 < row["max"] else v0 - 1), ("restore", v0)):
            n0 = nv_counters(ctx, nvb)
            got = box.set_row(row, v)
            box.call(2, SC.CMD, 2)
            t0 = time.monotonic()
            while time.monotonic() - t0 < NV_SETTLE_S:
                keep_alive(ctx)
                C.pace(ctx.ck)
            n1 = nv_counters(ctx, nvb)
            back = box.get_row(row)
            d = {k: n1[k] - n0[k] for k in n0}
            good = got == v and back == v and d["item_wr"] > 0 and d["erase"] + d["ops"] > 0
            ok &= good
            say(f"  NVRAM {step}: sharpness {v0} -> set {v} read back {back}; flash since: {d['flush']} flush, {d['item_wr']} items programmed, {d['ops']} halt ops ({d['erase']} erases), {d['bytes']} bytes: {'PASS' if good else 'FAIL'}")
    finally:
        C.xwr(ctx, wrap_addr, 0)
    return ok


def soak(ctx, name: str, minutes: float, a) -> dict:
    stats = {"checks": 0, "bad": 0, "resets": 0, "iosc": []}
    t_end = time.monotonic() + minutes * 60
    t_start = time.monotonic()
    if apply_step(ctx, name) is None:
        say("FAIL initial apply")
        stats["resets"] += 1
        return stats
    say(f"soak {name} {minutes} min: held, savers {SAVERS}, check every {PERIOD_S:.0f} s")
    if a.nvram is not None:
        stats["nvram"] = nvram_test(ctx, name, a)
    n, nxt_check, nxt_keep, si = 0, time.monotonic(), time.monotonic(), 0
    while time.monotonic() < t_end:
        now = time.monotonic()
        try:
            if now >= nxt_check:
                H.op(ctx.dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVERS[si % len(SAVERS)], label="saver")
                say(f"  saver {SAVERS[si % len(SAVERS)]} on")
                si += 1
                n += 1
                period_check(ctx, n, now - t_start, name, stats)
                nxt_check = now + PERIOD_S
                nxt_keep = time.monotonic() + KEEP_S
            elif now >= nxt_keep:
                if not keep_alive(ctx):
                    raise TimeoutError("no answer to keep")
                nxt_keep = time.monotonic() + KEEP_S
            else:
                C.pace(ctx.ck)
        except (TimeoutError, RuntimeError) as e:
            stats["resets"] += 1
            say(f"  RESET / comm lost at t={time.monotonic() - t_start:.0f}s: {e}")
            if stats["resets"] > MAX_RESETS or not ctx.relink():
                say("stop: unit did not come back or too many resets")
                break
            if apply_step(ctx, name) is None:
                say("stop: re-apply after the reset failed")
                break
            nxt_check = time.monotonic() + 1.0
            nxt_keep = time.monotonic() + KEEP_S
    try:
        H.op(ctx.dev, H.OP_SAVER, H.lim_saver(), flags=0, n=H.SAVER_OFF, label="saver off")
    except (TimeoutError, RuntimeError):
        pass
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--nvram", type=int, choices=(0, 7), help="before the soak: settings write through the firmware mailbox + save at the held step, MOVX cycles 0 default / 7 SDK wrapper")
    ap.add_argument("step")
    ap.add_argument("minutes", type=float)
    a = ap.parse_args()
    if a.step not in C.STEPS:
        raise SystemExit(f"unknown step {a.step}")
    binp = a.bin or a.map.with_suffix(".bin")
    img = binp.read_bytes() if binp.exists() else b""
    want = f"{zlib.crc32(img[C.CRC_FROM:C.CRC_TO]):08x}" if img else None
    import dbg_link
    import dbg_xdata
    import i2cbus
    import sync_log as S
    i2cbus.require_unit(a.bus, a.serial)
    C.OPTS["fps"] = False
    with dbg_link.linked(a.bus, int(a.minutes) + 5):
        dev = H.Unit(a.bus, a.map)
        ck = copy.copy(dev)
        ck.base = S.sym(a.map, "g_stAwtoClk")

        def rdabs(addr, n):
            for _ in range(dev.RD_TRIES):
                r = dbg_xdata.read_blocks(dev.io, addr, n)
                if r is not None:
                    return r
            return None
        ctx = C.Ctx(dev, ck, rdabs, S.sym(a.map, "g_stAwtoSync"), want)
        ctx.relink = lambda: C.relink(a.bus)
        try:
            ref = C.run_step(ctx, "stock")                                # CRC reference of the session + IOSC sample at the start
            if not ref or not ref.get("pass"):
                say("stock reference step failed: no soak")
                return 1
            C.iosc(ctx, "soak start")
            t0 = time.monotonic()
            st = soak(ctx, a.step, a.minutes, a)
            C.send(ctx, C.OP_REVERT, 2.0, label="revert")
            C.iosc(ctx, "soak end (stock clock)")
            cnts = [c for _, c in st["iosc"] if c is not None]
            say(f"SOAK {a.step} {(time.monotonic() - t0) / 60:.1f} min: {st['checks']} checks, {st['bad']} with a failure, {st['resets']} reset(s); IOSC trim_cnt first {cnts[0] if cnts else None} last {cnts[-1] if cnts else None} min {min(cnts) if cnts else None} max {max(cnts) if cnts else None}")
            return 1 if (st["bad"] or st["resets"]) else 0
        finally:
            try:
                C.send(ctx, C.OP_REVERT, 2.0, label="final revert")
            except Exception as e:  # noqa: BLE001
                say(f"final revert: {e}")
            dev.close()


if __name__ == "__main__":
    sys.exit(main())
