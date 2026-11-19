#!/usr/bin/env python3
"""DDR PLL clock sweep on the test unit (docs/osd-write-sweep.md "Phase C"). Memory clock only: never the display PLL, panel timing or dclk.

usage: ddr_clk_sweep.py --bus B --serial S --map MAP [--max-pct P] [--ddr-override] [--max-fail N] [--no-health] [--dry] [read | run]
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c: g_stAwtoDdr). `read` = stock N / F / pdiv of both channels + the modelled MHz, writes nothing.
  `run` = control step -0.5 %, stock, then +0.5 % rungs up to --max-pct (default 5, the envelope; 10 needs --ddr-override, which the firmware also needs).
  Model [regdb 0x882B text, SDK ScalerPLLSetDDR2PLLFreq]: F_pll = F_xtal / (pdiv + 1) x (N + 2 + F / 8192). One code unit = F_xtal / 8192 / (pdiv + 1).
  Per rung: the firmware writes F then N on both channels (hold limit restores by itself), settle SETTLE_S, then DDR read-path flags (ddr_sweep.py Phy:
  VALID_WIN_DET + INT_STATUS1 per channel), the firmware's disp / cap FIFO flags, heartbeat, link reads, `./dev.py health` (picture path). A failing rung is
  reverted, retried once from stock; a second failure is reproducible; stop after --max-fail of them, or at the first picture loss (health / link lost).
Log ./tmp/logs/ddr_clk_sweep.log, TSV ./tmp/logs/ddr_clk_sweep.tsv.
"""
from __future__ import annotations

import argparse
import copy
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import osd_hw_test as H

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/ddr_clk_sweep.log"
TSV = ROOT / "tmp/logs/ddr_clk_sweep.tsv"

# StAwtoDdr (fw/test/testcmd.c), big endian
(D_GO, D_SEQ, D_STATE, D_REFUSE, D_FLAGS, D_PDIV, D_DELTA, D_HOLD, D_ENV, D_NOW_NA, D_NOW_NB, D_NOW_FA, D_NOW_FB, D_STK_NA, D_STK_NB, D_STK_FA,
 D_STK_FB, D_FIFO_PRE, D_FIFO_POST, D_NOWMS) = (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 13, 14, 16, 18, 19, 20, 22, 24, 29, 34)
D_SIZE = 36
OP_SET, OP_REVERT = 1, 2
ST_HELD, ST_REFUSED, ST_REVERTED, ST_AUTO = 1, 2, 3, 4
REFUSE = {0: "none", 1: "outside the envelope / N range", 2: "hold limit", 3: "stock N of A and B differ"}
F_OVERRIDE = 1
XTAL_MHZ = 14.318                                    # _EXT_XTAL 14318 kHz (docs/clock-sweep.md)
CODE_BITS, N_BIAS, UNIT = 13, 2, 8
STEP_PCT = 0.5                                       # largest step between two held levels
ENVELOPE_PCT, OVERRIDE_PCT = 5.0, 10.0
SETTLE_S = 0.5                                       # ddr_sweep.py: flags return within ~0.5 s of a clear
RUNG_SETTLE_S = 0.3                                  # unmeasured walk rungs
HOLD_MS = 30000                                      # fw restores by itself this long after the last set: one rung incl. health (~10 s) x 2
FW_LIMIT_S = 1.5                                     # one main pass (<= 20 ms) + link: expiry = FAIL
REPEATS = 3                                          # flag measures per rung (worst counts)
POLL_PACE_S = 0.05
FIFO_MASK = [0x03, 0x03, 0x03, 0x03, 0x63]
FIFO_NAMES = ["dispM1", "dispM2", "capM1", "capM2", "status0"]
HB_WINDOW_S, HB_TOL_PCT = 2.0, 1.5
LINK_READS = 30


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def be(raw: bytes, o: int, n: int = 2) -> int:
    return int.from_bytes(raw[o:o + n], "big")


def code(n: int, f: int) -> int:
    return ((n + N_BIAS) << CODE_BITS) + f


def mhz(n: int, f: int, pdiv: int) -> float:
    return XTAL_MHZ / (pdiv + 1) * code(n, f) / (1 << CODE_BITS)


def delta8_for(pct: float, stock_code: int) -> int:
    return round(stock_code * pct / 100.0 / UNIT)


def pct_of(d8: int, stock_code: int) -> float:
    return d8 * UNIT * 100.0 / stock_code


class Ctx:
    def __init__(self, dev, sw, phy, bus, serial, map_path, health):
        self.dev, self.sw, self.phy, self.bus, self.serial, self.map, self.health = dev, sw, phy, bus, serial, map_path, health
        self.stock = None            # (NA, NB, FA, FB, pdiv)
        self.base = None             # worst flags at stock
        self.level = 0.0             # pct of stock currently held
        self.fifo0 = None            # FIFO / STATUS0 bytes at stock
        self.override = False


def pace(sw) -> None:
    if not isinstance(sw, H.Unit):
        sw.idle()
        return
    t0 = time.monotonic()
    while time.monotonic() - t0 < POLL_PACE_S:
        pass


def send(ctx, go: int, label: str, d8: int = 0, hold_ms: int = HOLD_MS) -> bytes | None:
    sw = ctx.sw
    if go == OP_SET:
        sw.wr(D_FLAGS, bytes([F_OVERRIDE if ctx.override else 0, 0]))
        sw.wr(D_DELTA, (d8 & 0xFFFF).to_bytes(2, "big") + hold_ms.to_bytes(2, "big"))
    seq0 = sw.rd(D_SEQ, 1)[0]
    sw.wr(D_GO, bytes([go]))
    t0 = sw.now()
    while True:
        pace(sw)
        try:
            h = sw.rd(D_GO, 2)
        except RuntimeError:
            h = None
        if h is not None and h[0] == 0 and h[1] != seq0:
            return sw.rd(0, D_SIZE)
        if sw.now() - t0 > FW_LIMIT_S:
            say(f"  FAIL {label}: no answer after {sw.now() - t0:.2f} s (limit {FW_LIMIT_S} s)")
            return None


def stock_info(raw: bytes) -> tuple:
    return (raw[D_STK_NA], raw[D_STK_NB], be(raw, D_STK_FA), be(raw, D_STK_FB), raw[D_PDIV] & 3)


def wait(dev, s: float) -> None:
    t0 = dev.now()
    while dev.now() - t0 < s:
        dev.idle()


def flags(ctx) -> dict:
    """Worst of REPEATS measures per channel (ddr_sweep.py Phy.measure: clear, settle, read)."""
    out = {}
    for ch in "AB":
        ms = [ctx.phy.measure(ch, settle=SETTLE_S, clear=True) for _ in range(REPEATS)]
        if any("err" in m for m in ms):
            out[ch] = {"err": True}
            continue
        out[ch] = {"vw": max(m["vw"] for m in ms), "calint": max(m["calint"] for m in ms)}
    return out


def fifo_new(pre: bytes, post: bytes) -> str:
    return ",".join(f"{n}:{post[i] & FIFO_MASK[i] & ~pre[i]:02X}" for i, n in enumerate(FIFO_NAMES) if post[i] & FIFO_MASK[i] & ~pre[i])


FIFO_REGS = [0x05B0, 0x45B0, 0x052B, 0x452B, 0x0002]     # disp M1 / M2, cap M1 / M2 FIFO status, STATUS0 (AWTO_R_*); read only, never cleared


def fifo_regs(ctx) -> bytes:
    from p037_test import rd
    return bytes((rd(ctx.dev.io, a) or 0) for a in FIFO_REGS)


def health(ctx) -> bool:
    """./dev.py health switches the debug link off at its end: switch it on again."""
    if not ctx.health:
        return True
    r = subprocess.run(["./dev.py", "health", "--unit", "3"], cwd=ROOT, capture_output=True, text=True)
    import dbg_link
    try:
        dbg_link.on(ctx.bus, 10)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        say(f"  link on after health: {e}")
    ok = r.returncode == 0
    say(f"  health rc={r.returncode}: " + next((ln.split('] ')[-1][:100] for ln in r.stdout.splitlines()[::-1] if 'HEALTH' in ln), "no HEALTH line"))
    return ok


def tsv(row: dict) -> None:
    keys = ["pct", "label", "NA", "FA", "NB", "FB", "mhz", "vwA", "calA", "vwB", "calB", "fifo_new", "heartbeat", "link", "health", "pass", "note"]
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(["time"] + keys) + "\n")
        f.write("\t".join([isostamp.now()] + [("%.4g" % row[k]) if isinstance(row.get(k), float) else str(row.get(k, "")) for k in keys]) + "\n")


def goto(ctx, pct: float, label: str) -> bytes | None:
    """Walk from the held level to pct in rungs of at most STEP_PCT (unmeasured), the last one is returned."""
    raw = None
    cur = ctx.level
    n = max(1, int(abs(pct - cur) / STEP_PCT + 0.999))
    for i in range(1, n + 1):
        lvl = cur + (pct - cur) * i / n
        raw = send(ctx, OP_SET, f"{label} rung {lvl:+.2f} %", delta8_for(lvl, code(ctx.stock[0], ctx.stock[2])))
        if raw is None or raw[D_STATE] != ST_HELD:
            return raw
        ctx.level = lvl
        if i < n:
            wait(ctx.sw, RUNG_SETTLE_S)
    return raw


def measure_level(ctx, pct: float, label: str) -> dict:
    row = {"pct": f"{pct:+.2f}", "label": label, "pass": False}
    raw = goto(ctx, pct, label)
    if raw is None:
        row["note"] = "no answer: the firmware did not take the step"
        row["fatal"] = True
        return row
    if raw[D_STATE] != ST_HELD:
        row["note"] = f"fw state {raw[D_STATE]} refuse {REFUSE.get(raw[D_REFUSE], raw[D_REFUSE])}"
        row["fatal"] = raw[D_STATE] != ST_REFUSED
        return row
    na, nb, fa, fb = raw[D_NOW_NA], raw[D_NOW_NB], be(raw, D_NOW_FA), be(raw, D_NOW_FB)
    pdiv = ctx.stock[4]
    row.update(NA=na, NB=nb, FA=fa, FB=fb, mhz=mhz(na, fa, pdiv))
    notes = []
    want_a = code(ctx.stock[0], ctx.stock[2]) + delta8_for(pct, code(ctx.stock[0], ctx.stock[2])) * UNIT
    if code(na, fa) != want_a:
        notes.append(f"A code {code(na, fa)} want {want_a}")
    wait(ctx.sw, SETTLE_S)
    fl = flags(ctx)
    for ch in "AB":
        if fl[ch].get("err"):
            notes.append(f"ch{ch} i2c error")
            row["vw" + ch] = row["cal" + ch] = "ERR"
        else:
            row["vw" + ch], row["cal" + ch] = fl[ch]["vw"], fl[ch]["calint"]
            if ctx.base and (fl[ch]["vw"] > ctx.base[ch]["vw"] or fl[ch]["calint"] > ctx.base[ch]["calint"]):
                notes.append(f"ch{ch} flags VW {fl[ch]['vw']}/8 CALINT {fl[ch]['calint']}/8 above stock {ctx.base[ch]['vw']}/{ctx.base[ch]['calint']}")
    a0, t0 = be(ctx.sw.rd(D_NOWMS, 2), 0), ctx.sw.now()
    wait(ctx.sw, HB_WINDOW_S)
    a1, t1 = be(ctx.sw.rd(D_NOWMS, 2), 0), ctx.sw.now()
    ratio = ((a1 - a0) & 0xFFFF) / (1000 * (t1 - t0))
    row["heartbeat"] = round(ratio, 4)
    if abs(ratio - 1) * 100 > HB_TOL_PCT:
        notes.append(f"heartbeat {ratio:.4f}")
    link_ok = True
    for _ in range(LINK_READS):
        try:
            ctx.sw.rd(0, D_SIZE)
        except RuntimeError:
            link_ok = False
            break
        pace(ctx.sw)
    row["link"] = link_ok
    if not link_ok:
        notes.append("debug link reads failed")
        row["fatal"] = True
    else:
        now = fifo_regs(ctx)
        row["fifo_new"] = fifo_new(ctx.fifo0, now) if ctx.fifo0 is not None else ""
        if row["fifo_new"]:
            notes.append("FIFO flag set: " + row["fifo_new"])
    send(ctx, OP_SET, label + " re-arm", delta8_for(pct, code(ctx.stock[0], ctx.stock[2])))        # same level: restarts the hold timer before the slow health run
    # health last: it takes seconds and switches the link
    hok = health(ctx)
    row["health"] = hok
    if not hok:
        notes.append("health FAIL (picture path / mode / timing)")
        row["fatal"] = True
    row["note"] = "; ".join(notes)
    row["pass"] = not notes
    say(f"  {'PASS' if row['pass'] else 'FAIL'} {label} {pct:+.2f} %: A N {na} F {fa} / B N {nb} F {fb} = {row['mhz']:.2f} MHz modelled; "
        f"VW A {row.get('vwA')} B {row.get('vwB')} CALINT A {row.get('calA')} B {row.get('calB')}; heartbeat {ratio:.4f}; link {link_ok}; health {hok}"
        + (f"; {row['note']}" if row["note"] else ""))
    return row


def revert(ctx, label: str = "revert") -> None:
    raw = send(ctx, OP_REVERT, label)
    ctx.level = 0.0
    if raw is None:
        say(f"  {label}: no answer; the firmware restores at its hold limit ({HOLD_MS} ms), the WDT resets a stalled loop")
    else:
        say(f"  {label}: state {raw[D_STATE]}, A N {raw[D_NOW_NA]} F {be(raw, D_NOW_FA)}, B N {raw[D_NOW_NB]} F {be(raw, D_NOW_FB)} (stock A {raw[D_STK_NA]}/{be(raw, D_STK_FA)})")


def do_read(ctx) -> int:
    raw = send(ctx, OP_SET, "read stock (delta 0)", 0, 5000)
    if raw is None or raw[D_STATE] != ST_HELD:
        say("FAIL: the stock read did not run")
        return 1
    ctx.stock = stock_info(raw)
    na, nb, fa, fb, pdiv = ctx.stock
    say(f"stock A N {na} F {fa}, B N {nb} F {fb}, pdiv code {pdiv} (Div{pdiv + 1}): modelled {mhz(na, fa, pdiv):.3f} / {mhz(nb, fb, pdiv):.3f} MHz; "
        f"1 code unit = {XTAL_MHZ / (pdiv + 1) * 1000 / (1 << CODE_BITS):.3f} kHz = {100.0 / code(na, fa):.6f} %; 0.5 % = {delta8_for(0.5, code(na, fa)) * UNIT} units; envelope word {be(raw, D_ENV)} x 8")
    revert(ctx, "revert after read")
    return 0


def do_run(ctx, max_pct: float, max_fail: int) -> int:
    if do_read(ctx):
        return 1
    steps = [0.0, -STEP_PCT] + [STEP_PCT * k for k in range(1, int(max_pct / STEP_PCT + 1e-9) + 1)]
    reproducible = 0
    highest = None
    for pct in steps:
        say(f"##### {pct:+.2f} %")
        row = measure_level(ctx, pct, "step" if pct else "stock")
        if pct == 0.0 and row["pass"]:
            ctx.base = {ch: {"vw": max(row["vw" + ch], 0), "calint": max(row["cal" + ch], 0)} for ch in "AB"}
            ctx.fifo0 = fifo_regs(ctx)
        if pct == 0.0 and not row["pass"]:
            say("stock rung itself failed: nothing to compare against; reverting and stopping")
            tsv(row)
            revert(ctx)
            return 1
        tsv(row)
        if row["pass"]:
            highest = pct if highest is None or pct > highest else highest
            continue
        revert(ctx, "revert after failure")
        if row.get("fatal"):
            say("picture loss / link loss / no answer: stopped at the first one")
            return 1
        say(f"retry {pct:+.2f} % once from stock")
        row2 = measure_level(ctx, pct, "retry")
        tsv(row2)
        if row2["pass"]:
            say(f"retry passed: {pct:+.2f} % not reproducible (counted as a pass)")
            continue
        revert(ctx, "revert after retry")
        reproducible += 1
        say(f"reproducible failure {reproducible} of {max_fail} at {pct:+.2f} %")
        if row2.get("fatal") or reproducible >= max_fail:
            break
    revert(ctx, "final revert")
    say(f"sweep done: highest passing step {highest if highest is None else format(highest, '+.2f') + ' %'}, {reproducible} reproducible failure(s)")
    return 1 if reproducible else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--max-pct", type=float, default=ENVELOPE_PCT)
    ap.add_argument("--ddr-override", action="store_true", help=f"allow up to {OVERRIDE_PCT} %% (the envelope is {ENVELOPE_PCT} %%)")
    ap.add_argument("--max-fail", type=int, default=3)
    ap.add_argument("--no-health", action="store_true")
    ap.add_argument("cmd", choices=["read", "run"])
    a = ap.parse_args()
    limit = OVERRIDE_PCT if a.ddr_override else ENVELOPE_PCT
    if a.max_pct > limit:
        raise SystemExit(f"--max-pct {a.max_pct} above the envelope {limit} % (--ddr-override raises it to {OVERRIDE_PCT} %); nothing done")
    import dbg_link
    import ddr_sweep as DS
    import i2cbus
    import sync_log as S
    i2cbus.require_unit(a.bus, a.serial)
    with dbg_link.linked(a.bus, 15):
        dev = H.Unit(a.bus, a.map)
        sw = copy.copy(dev)
        sw.base = S.sym(a.map, "g_stAwtoDdr")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        phy = DS.Phy(dev.io, LOG.open("a"))
        ctx = Ctx(dev, sw, phy, a.bus, a.serial, a.map, not a.no_health)
        ctx.override = a.ddr_override
        try:
            rc = do_read(ctx) if a.cmd == "read" else do_run(ctx, a.max_pct, a.max_fail)
        finally:
            try:
                revert(ctx, "exit revert")
            except Exception as e:  # noqa: BLE001
                say(f"exit revert: {e}")
            dev.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
