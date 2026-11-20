#!/usr/bin/env python3
"""Backlight on-delay sweep for a filmed video test (docs/bl-delay-sweep.md). Internal module behind `./dev.py bl-sweep`.

usage: bl_sweep.py --unit N [--values 0,50,100,150,200,300,400] [--runs 3] [--gap-s 8]
  Per run (interleaved order, repeated --runs times): write the TEST knob (4 B no-init XDATA, kept over the warm reset,
  RL6449_Project.h AWTO_BLK_*), read it back, ISP reset, wait QUIET_S without bus traffic, read the sync log until the
  'backlight on' lines (11 E2 knob, 11 E1 times) and the ACTIVE line are in, check knob == planned, host note on the unit's
  console, gap. The knob is cleared at the end (and on any exit). Default image behaviour without the knob is unchanged.
Output: START / RUN / DONE lines (ISO time with ms), summary table, ./tmp/logs/bl_sweep.tsv, ./tmp/logs/bl_sweep.log.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import unit_lock

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/bl_sweep.log"
TSV = ROOT / "tmp/logs/bl_sweep.tsv"
HEADER = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
DEFAULT_VALUES = (0, 50, 100, 150, 200, 300, 400)       # Dan's sweep, ms after panel video ready
# Warm reset to ACTIVE ~1.3 s (boot_loop.py), + the largest delay 0.4 s = 1.7 s; x1.25 = 2.1 s without bus traffic (the film
# must not see debug-link swaps in the boot). Expiry: reads start anyway.
QUIET_S = 2.1
# Whole run wait (reset to the lines read) = the brief's 5 s; expiry: run marked NO-ACTIVE / NO-BL, sweep goes on.
ACTIVE_WAIT_S = 5.0
STOP_AFTER_FAILS = 3                                     # consecutive runs with a wrong / missing knob row: the knob path is broken
RUN_S = 6.5                                              # one run without the gap: knob write 2.2 + reset + quiet 2.1 + sync read + note (dry run 2026-11-20)
BROKEN = ("KNOB", "NO-KNOB", "NO-BL", "RESET")             # verdict prefixes: the knob path / reset does not work
COLS = ("run", "of", "kind", "planned_ms", "knob_seen_ms", "reset_at", "active_ms", "bl_boot_ms", "bl_after_video_ms", "bl_at_est",
        "late", "verdict")
_WAIT = threading.Event()                                # never set: Event.wait(t) = a pause with a name


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now_ms()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def pause(seconds: float, why: str) -> None:
    say(f"pause {seconds:g} s: {why}")
    _WAIT.wait(seconds)


def knob_defs() -> dict:
    """AWTO_BLK_* from the firmware header: one source for address, magic, seed, range"""
    txt = HEADER.read_text()
    d = {k: int(re.search(rf"#define\s+AWTO_BLK_{k}\s+(0x[0-9A-Fa-f]+|\d+)", txt).group(1), 0)
         for k in ("ADDR", "MAGIC", "SEED", "MAX_MS")}
    return d


def knob_bytes(ms: int, d: dict | None = None) -> bytes:
    d = d or knob_defs()
    lo, hi = ms & 0xFF, ms >> 8
    return bytes([d["MAGIC"], lo, hi, d["SEED"] ^ d["MAGIC"] ^ lo ^ hi])


def order(values: list[int], runs: int) -> list[int]:
    """Fixed interleaved order: values sorted, taken with a stride coprime to n (0,4,1,5,2,6,3 for 7), the round repeated"""
    v = sorted(values)
    n = len(v)
    stride = next(s for s in range(max(1, round(n * 0.57)), n + 2) if _gcd(s, n) == 1) if n > 1 else 1
    rnd = [v[(k * stride) % n] for k in range(n)]
    return rnd * runs


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def dev(*args: str) -> tuple[int, str]:
    """./dev.py <cmd>. synclog / note are thin clients of the GUI port: --direct here (no app, no headless auto-start), see main()"""
    direct = ["--direct"] if args[0] in ("synclog", "note") else []
    r = subprocess.run([str(ROOT / "dev.py"), *args, *direct], capture_output=True, text=True, cwd=ROOT, check=False)
    return r.returncode, r.stdout + r.stderr


def set_knob(unit: str, ms: int | None) -> bool:
    """write the 4 knob bytes (ms None = clear: magic 0) and read them back; True = read back equal"""
    d = knob_defs()
    want = knob_bytes(ms, d) if ms is not None else bytes(4)
    pairs = [f"{d['ADDR'] + i:X}={b:02X}" for i, b in enumerate(want)]
    rc, out = dev("dbg-write", "--unit", unit, *pairs)
    if rc != 0:
        say(f"knob write failed rc={rc}: {out.strip()[-200:]}")
        return False
    rc, out = dev("dbg-read", "--unit", unit, f"{d['ADDR']:X}:4")
    m = re.search(rf"@{d['ADDR']:#x}: ((?:[0-9A-Fa-f]{{2}} ?){{4}})", out)
    ok = rc == 0 and m is not None and bytes.fromhex(m.group(1)) == want
    if not ok:
        say(f"knob read back differs: want {want.hex(' ')}, dbg-read says: {out.strip()[-200:]}")
    return ok


RE_E1 = re.compile(r"backlight on, (\d+)ms after MCU boot, (\d+)ms after video ready \(test knob\)")
RE_E2 = re.compile(r"test knob backlight on delay (\d+) ?ms")
RE_E3 = re.compile(r"test knob: no video ready in (\d+) ?ms")
RE_ACTIVE = re.compile(r"(\d+):system:in DISPLAY SETTING for \d+ms->ACTIVE:display set, panel video ready")


def parse(out: str) -> dict:
    """measured values from a sync log text; missing = None"""
    r: dict = {"knob": None, "boot": None, "ref": None, "late": None, "active": None}
    for ln in out.splitlines():
        if m := RE_E2.search(ln):
            r["knob"] = int(m.group(1))
        if m := RE_E1.search(ln):
            r["boot"], r["ref"] = int(m.group(1)), int(m.group(2))
        if m := RE_E3.search(ln):
            r["late"] = int(m.group(1))
        if m := RE_ACTIVE.search(ln):
            r["active"] = int(m.group(1))
    return r


def verdict(planned: int, m: dict) -> str:
    if m["knob"] is None:
        return "NO-KNOB-ROW"
    if m["knob"] != planned:
        return f"KNOB-MISMATCH({m['knob']})"
    if m["ref"] is None:
        return "NO-BL-ROW"
    if m["late"] is not None:
        return "LATE(no video ready)"
    return "OK" if m["ref"] >= planned else "EARLY"


def one_run(unit: str, k: int, n: int, planned: int, gap_s: float) -> dict:
    row = {"run": k, "of": n, "kind": "reset", "planned_ms": planned}
    say(f"run {k}/{n} delay {planned} ms: knob write")
    if not set_knob(unit, planned):
        return {**row, "verdict": "KNOB-WRITE-FAIL"}
    t_reset = time.monotonic()
    say(f"RESET {k}/{n} delay {planned} ms")
    rc, out = dev("reset", "--unit", unit)
    reset_at = isostamp.now_ms()
    wall0 = time.time()
    if rc != 0:
        return {**row, "reset_at": reset_at, "verdict": f"RESET-FAIL rc={rc}"}
    pause(QUIET_S, "no bus traffic while the panel comes up (the film)")
    m: dict = {}
    while time.monotonic() - t_reset < ACTIVE_WAIT_S:
        _, out = dev("synclog", "--unit", unit)
        m = parse(out)
        if m["active"] is not None and (m["ref"] is not None or m["late"] is not None):
            break
    v = verdict(planned, m) if m else "NO-SYNCLOG"
    if m and m["active"] is None and v == "OK":
        v = "NO-ACTIVE"
    est = (isostamp.datetime.fromtimestamp(wall0 + (m["boot"] or 0) / 1000).astimezone().isoformat(timespec="milliseconds")
           if m.get("boot") is not None else "")
    res = {**row, "knob_seen_ms": m.get("knob"), "reset_at": reset_at, "active_ms": m.get("active"), "bl_boot_ms": m.get("boot"),
           "bl_after_video_ms": m.get("ref"), "bl_at_est": est, "late": m.get("late"), "verdict": v}
    say(f"RUN {k}/{n} delay {planned} ms  reset {reset_at}  ACTIVE at {m.get('active')} ms  backlight on {m.get('boot')} ms after boot "
        f"= {m.get('ref')} ms after video ready  (host ~{est})  knob seen {m.get('knob')}  {v}")
    dev("note", "--unit", unit, f"run {k}/{n} delay {planned} ms")      # console shows it after the backlight is on
    pause(gap_s, "gap between runs (Dan's film: one clear picture per run)")
    return res


def summary(rows: list[dict]) -> str:
    out = ["", f"{'delay ms':>9} {'runs':>4} {'ok':>3} {'after video ready ms (min / mean / max)':>42}"]
    for p in sorted({r["planned_ms"] for r in rows}):
        rs = [r for r in rows if r["planned_ms"] == p]
        ms = [r["bl_after_video_ms"] for r in rs if r.get("bl_after_video_ms") is not None]
        stat = f"{min(ms)} / {sum(ms) / len(ms):.0f} / {max(ms)}" if ms else "-"
        out.append(f"{p:>9} {len(rs):>4} {sum(r['verdict'] == 'OK' for r in rs):>3} {stat:>42}")
    return "\n".join(out)


def write_tsv(rows: list[dict]) -> None:
    TSV.parent.mkdir(parents=True, exist_ok=True)
    with TSV.open("w") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)) for c in COLS) + "\n")


def camera_hook(enabled: bool) -> bool:
    """--camera: record the whole sweep and analyse each run via scripts/cam_frames.py (branch cam-lcd-frames, not on main yet).
    TODO: when cam_frames.py is on main, start the recording (-c copy) before run 1, and per run call its analysis with the
    TSV's reset_at + planned_ms (first-light frame, flash frames, picture frame) and add its columns to COLS. No camera code here."""
    if not enabled:
        return False
    if not (ROOT / "scripts/cam_frames.py").is_file():
        say("--camera: scripts/cam_frames.py not on this branch yet (TODO stub): no recording; match the video by the TSV reset_at times")
        return False
    say("--camera: scripts/cam_frames.py exists but the hook is a TODO stub: no recording yet")
    return False


def banner(text: str) -> None:
    bar = "#" * 78
    say(bar)
    for ln in text.splitlines():
        say(f"#  {ln}")
    say(bar)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="3")
    ap.add_argument("--values", default=",".join(map(str, DEFAULT_VALUES)))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--gap-s", type=float, default=8.0)
    ap.add_argument("--camera", action="store_true", help="record the bench camera for the whole sweep and analyse each run (needs scripts/cam_frames.py)")
    a = ap.parse_args()
    values = [int(x) for x in a.values.split(",")]
    d = knob_defs()
    if any(not 0 <= v <= d["MAX_MS"] for v in values) or a.runs < 1:
        raise SystemExit(f"values 0..{d['MAX_MS']} ms, runs >= 1; nothing done")
    import gui_client
    if gui_client.app_live():       # direct bus access: its own reset + sync-log timing loop; reset / dbg-write are not ported
        raise SystemExit("bl-sweep: the GUI app is running and owns the unit buses; stop it first (./dev.py gui ...); nothing done")
    serial = json.loads((ROOT / "scripts/devices.json").read_text())["units"][a.unit]["serial"]
    seq = order(values, a.runs)
    camera_hook(a.camera)
    est_s = len(seq) * (a.gap_s + RUN_S)                          # RUN_S measured in the dry run
    rows: list[dict] = []
    with unit_lock.held(serial, "bl_sweep"):
        banner(f"START bl-sweep unit {a.unit}: {len(seq)} runs, order {seq[:len(values)]} x {a.runs}\n"
               f"host clock now {isostamp.now_ms()}  (compare with the phone clock; RUN lines carry the reset time)\n"
               f"about {est_s / 60:.0f} min, unattended until the DONE banner; match a camera recording by the RUN reset times")
        bad = 0
        try:
            for k, p in enumerate(seq, 1):
                r = one_run(a.unit, k, len(seq), p, a.gap_s)
                rows.append(r)
                write_tsv(rows)
                bad = bad + 1 if r["verdict"].startswith(BROKEN) else 0
                if bad >= STOP_AFTER_FAILS:
                    say(f"ABORT: {bad} runs in a row without the planned knob value ({r['verdict']}): the knob path is broken")
                    break
        finally:
            cleared = set_knob(a.unit, None)
            say("knob cleared: ok" if cleared else f"knob clear FAILED (power-cycle, or write 0 at {d['ADDR']:#X})")
        say(summary(rows))
        n_ok = sum(r["verdict"] == "OK" for r in rows)
        banner(f"DONE bl-sweep unit {a.unit}: {n_ok} of {len(seq)} runs OK, {isostamp.now_ms()}\nTSV {TSV.relative_to(ROOT)}")
    return 0 if n_ok == len(seq) else 1


if __name__ == "__main__":
    sys.exit(main())
