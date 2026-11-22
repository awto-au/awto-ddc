#!/usr/bin/env python3
"""A/B of the TMDS ISR diet on a unit (#256): per run reset, sample the Timer2 tick counter through the lock, read the sync log.

usage: tmds_ab.py --unit 1 --map MAP [--runs 5] [--label TEXT]
- Per run: ISP reset, then DDC/CI debug-link on (VCP 0xE3) retried until 0x35 answers, then back-to-back [hb, t2] reads
  (diag block) until SAMPLE_S after the reset.
- deficit_ms = host wall ms since the reset write - Timer2 ms at the last sample (boot offset constant, so only A-B counts);
  tick_loss_ms = same over the sampled span after the lock (should be ~0); lock = predetect on -> scan done (sync log ms).
Log: tmp/logs/tmds_ab.log; TSV row per run: tmp/logs/tmds_ab.tsv
"""
import argparse
import itertools
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import isostamp
from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link
import i2cbus
import kvm
import rtd_i2c_bridge as B
import unit_health as U
from rtd_flash_sector import Rtd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/tmds_ab.log"
TSV = ROOT / "tmp/logs/tmds_ab.tsv"
ISP_EN, ISP_EN_VAL, RESET, RESET_VAL = 0x6F, 0x80, 0xEE, 0x02
SAMPLE_S = 2.4          # reset -> end of sampling: boot to ACTIVE is ~1.03 s fw time (sync log), + 0.5 s margin
LINK_TRY_S = 0.004      # one raw 6-byte write at 100 kHz is ~1 ms; retry until DDC/CI ACKs after the reset
LINK_AFTER_S = 1.2      # 0x35 link set before ~1 s fw time is lost (DDC slave re-init at INITIAL / ACTIVE); after the picture it holds


def say(s: str) -> None:
    _log_line(s, LOG)


def one_run(bus: int, base: int, mapp: Path, serial: str) -> dict:
    isp = Rtd(bus)
    isp.write(ISP_EN, ISP_EN_VAL)
    try:
        isp.write(RESET, RESET_VAL)
    except OSError:
        pass                                        # the MCU resets mid-transfer: the write may NAK; first_t2 shows the reset happened
    t0 = time.monotonic()
    time.sleep(LINK_AFTER_S)
    linked = False
    while not linked and time.monotonic() - t0 < SAMPLE_S:
        try:
            dbg_link._setvcp(bus, dbg_link.VCP_LINK, dbg_link.MAGIC, 0x0A)
        except OSError:
            time.sleep(LINK_TRY_S)
            continue
        time.sleep(LINK_TRY_S)
        linked = dbg_link.dbg_ok(bus)
    dbg = U.Dbg(B.Real(bus, allow_write=True))
    dbg.block = True                                # diag version 2: one 0x3C transaction per read
    samples = []
    while time.monotonic() - t0 < SAMPLE_S:
        a = time.monotonic()
        try:
            b = dbg.read(base + U.DIAG_OFF["hb"], 4)
        except U.DbgError as e:
            say(f'read fail at {(a - t0) * 1000:.0f} ms: {e}')
            continue
        samples.append(((a + time.monotonic()) / 2, U.be16(b, 2), U.be16(b, 0)))
    out = subprocess.run([sys.executable, str(ROOT / "scripts/sync_log.py"), str(bus), "--map", str(mapp), "--serial", serial],
                         capture_output=True, text=True, check=False).stdout
    ev = {}
    for key, pat in (("pre", r"TMDS predetect on"), ("meas", r"TMDS clock .* measured"), ("scan", r"scan done"),
                     ("active", r"->ACTIVE")):
        m = re.search(rf"\s(\d+):[^\n]*{pat}", out)
        ev[key] = int(m.group(1)) if m else None
    r = {"n": len(samples), "linked": linked, **ev}
    if len(samples) >= 2:
        (w0, t0_, _), (w1, t1_, _) = samples[0], samples[-1]
        dt2 = (t1_ - t0_) & 0xFFFF
        r.update(first_t2=t0_, first_ms=round((w0 - t0) * 1000), tick_loss_ms=round(dt2 - (w1 - w0) * 1000, 1), span_ms=dt2,
                 deficit_ms=round((w1 - t0) * 1000 - t1_, 1))
        # worst single-interval deficit (ISR stall seen between two reads)
        worst = 0.0
        for (wa, ta, _), (wb, tb, _) in itertools.pairwise(samples):
            worst = min(worst, ((tb - ta) & 0xFFFF) - (wb - wa) * 1000)
        r["worst_gap_ms"] = round(worst, 1)
    if ev["pre"] is not None and ev["scan"] is not None:
        r["lock_ms"] = ev["scan"] - ev["pre"]
    if ev["pre"] is not None and ev["meas"] is not None:
        r["meas_ms"] = ev["meas"] - ev["pre"]
    if ev["pre"] is not None and ev["active"] is not None:
        r["active_ms"] = ev["active"]
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="1")
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    u = kvm.units()[a.unit]
    bus = kvm.find_bus(u)
    if bus is None:
        say(f"no bus for unit {a.unit}")
        return 1
    i2cbus.require_unit(bus, u["serial"])
    base = U.load_maps(a.map.read_text(errors="replace"))["isr_g_stAwtoDiag"]
    rows = []
    for k in range(a.runs):
        if k:
            time.sleep(3.0)                         # lets the boot console / info card finish: runs start from the same state
        r = one_run(bus, base, a.map, u["serial"])
        rows.append(r)
        say(f"{a.label} run {k + 1}: {r}")
        with TSV.open("a") as f:
            f.write(f"{isostamp.now()}\t{a.label}\t{k + 1}\t{r}\n")
    for key in ("lock_ms", "meas_ms", "deficit_ms", "tick_loss_ms", "worst_gap_ms", "first_t2", "active_ms"):
        v = [r[key] for r in rows if key in r]
        if v:
            say(f"{a.label} {key}: n={len(v)} mean {statistics.mean(v):.1f} min {min(v)} max {max(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
