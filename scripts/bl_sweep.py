#!/usr/bin/env python3
"""Backlight on-delay sweep for a filmed video test (docs/bl-delay-sweep.md). Internal module behind `./dev.py bl-sweep`.

usage: bl_sweep.py --unit N [--values 0,50,100,150,200,300,400] [--runs 3] [--gap-s 8] [--ref active|stream|powerup]
                  [--kind reset|wake] [--camera]
  Per run (interleaved order, repeated --runs times): write the TEST knob (5 B no-init XDATA, kept over the warm reset,
  RL6449_Project.h AWTO_BLK_*), read it back, ISP reset, wait QUIET_S without bus traffic, read the sync log until the
  'backlight on' lines (11 E2 knob, 11 E1 times) and the ACTIVE line are in, check knob == planned, host note on the unit's
  console, gap. The knob is cleared at the end (and on any exit). Default image behaviour without the knob is unchanged.
Output: START / RUN / DONE lines (ISO time with ms), summary table, ./tmp/logs/bl_sweep.tsv, ./tmp/logs/bl_sweep.log.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import unit_lock
from _repo import ROOT

LOG = ROOT / "tmp/logs/bl_sweep.log"
TSV = ROOT / "tmp/logs/bl_sweep.tsv"
HEADER = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
DEFAULT_VALUES = (0, 50, 100, 150, 200, 300, 400)       # Dan's sweep, ms after the reference event
REFS = {"active": 0, "stream": 1, "powerup": 2}          # AWTO_BLK_REF_* (RL6449_Project.h)
SLEEP_HOLD_S = 3.0           # wake kind: DDC/CI sleep held this long (panel blank, MCU idle) before the wake; expiry: wake anyway
CAM_STOP_WAIT_S = 5.0
# Warm reset to ACTIVE ~1.3 s (boot_loop.py), + the largest delay 0.4 s = 1.7 s; x1.25 = 2.1 s without bus traffic (the film
# must not see debug-link swaps in the boot). Expiry: reads start anyway.
QUIET_S = 2.1
# Whole run wait (reset to the lines read) = the brief's 5 s; expiry: run marked NO-ACTIVE / NO-BL, sweep goes on.
ACTIVE_WAIT_S = 5.0
STOP_AFTER_FAILS = 3                                     # consecutive runs with a wrong / missing knob row: the knob path is broken
RUN_S = 6.5                                              # one run without the gap: knob write 2.2 + reset + quiet 2.1 + sync read + note (dry run 2026-11-20)
BROKEN = ("KNOB", "NO-KNOB", "NO-BL", "RESET")             # verdict prefixes: the knob path / reset does not work
COLS = ("run", "of", "kind", "planned_ms", "knob_seen_ms", "reset_at", "active_ms", "bl_boot_ms", "bl_after_video_ms", "bl_at_est",
        "late", "ref", "cam_dark_light_ms", "cam_flash_frames", "cam_light_picture_ms", "cam_dark_picture_ms", "cam_sheet", "verdict")
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
    d["REFS"] = {n: int(re.search(rf"#define\s+AWTO_BLK_REF_{n.upper()}\s+(\d+)", txt).group(1)) for n in REFS}
    return d


def knob_bytes(ms: int, d: dict | None = None, ref: str = "active") -> bytes:
    """magic, ms lo, ms hi, reference, check (covers all of them)"""
    d = d or knob_defs()
    lo, hi, r = ms & 0xFF, ms >> 8, d["REFS"][ref]
    return bytes([d["MAGIC"], lo, hi, r, d["SEED"] ^ d["MAGIC"] ^ lo ^ hi ^ r])


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


def set_knob(unit: str, ms: int | None, ref: str = "active") -> bool:
    """write the 5 knob bytes (ms None = clear: magic 0) and read them back; True = read back equal"""
    d = knob_defs()
    want = knob_bytes(ms, d, ref) if ms is not None else bytes(5)
    pairs = [f"{d['ADDR'] + i:X}={b:02X}" for i, b in enumerate(want)]
    rc, out = dev("dbg-write", "--unit", unit, *pairs)
    if rc != 0:
        say(f"knob write failed rc={rc}: {out.strip()[-200:]}")
        return False
    rc, out = dev("dbg-read", "--unit", unit, f"{d['ADDR']:X}:5")
    m = re.search(rf"@{d['ADDR']:#x}: ((?:[0-9A-Fa-f]{{2}} ?){{5}})", out)
    ok = rc == 0 and m is not None and bytes.fromhex(m.group(1)) == want
    if not ok:
        say(f"knob read back differs: want {want.hex(' ')}, dbg-read says: {out.strip()[-200:]}")
    return ok


RE_E1 = re.compile(r"backlight on, (\d+)ms after MCU boot, (\d+)ms after the knob's reference \(test knob\)")
RE_E2 = re.compile(r"test knob backlight on delay (\d+) ?ms, counts from ([a-z -]+)")
RE_E3 = re.compile(r"test knob: no reference event in (\d+) ?ms")
REF_TEXT = {"active": "video ready", "stream": "stream on", "powerup": "power-up"}
RE_ACTIVE = re.compile(r"(\d+):system:in DISPLAY SETTING for \d+ms->ACTIVE:display set, panel video ready")


def parse(out: str) -> dict:
    """measured values from a sync log text; missing = None"""
    r: dict = {"knob": None, "boot": None, "ref": None, "late": None, "active": None}
    for ln in out.splitlines():
        if m := RE_E2.search(ln):
            r["knob"], r["ref_text"] = int(m.group(1)), m.group(2)
        if m := RE_E1.search(ln):
            r["boot"], r["ref"] = int(m.group(1)), int(m.group(2))
        if m := RE_E3.search(ln):
            r["late"] = int(m.group(1))
        if m := RE_ACTIVE.search(ln):
            r["active"] = int(m.group(1))
    return r


def verdict(planned: int, m: dict, ref: str = "active") -> str:
    if m["knob"] is None:
        return "NO-KNOB-ROW"
    if not m.get("ref_text", "").startswith(REF_TEXT[ref]):
        return f"REF-MISMATCH({m.get('ref_text')})"
    if m["knob"] != planned:
        return f"KNOB-MISMATCH({m['knob']})"
    if m["ref"] is None:
        return "NO-BL-ROW"
    if m["late"] is not None:
        return "LATE(no video ready)"
    return "OK" if m["ref"] >= planned else "EARLY"


def restart(unit: str, kind: str) -> int:
    """reset = ISP warm reset; wake = DDC/CI sleep, held SLEEP_HOLD_S, then wake (the other start-up path)"""
    if kind == "reset":
        return dev("reset", "--unit", unit)[0]
    rc = dev("ddc", "--unit", unit, "sleep")[0]
    pause(SLEEP_HOLD_S, "DDC/CI sleep held: panel blank before the wake")
    return rc


def one_run(unit: str, k: int, n: int, planned: int, gap_s: float, ref: str = "active", kind: str = "reset") -> dict:
    row = {"run": k, "of": n, "kind": kind, "planned_ms": planned, "ref": ref}
    say(f"run {k}/{n} {kind} delay {planned} ms from {ref}: knob write")
    if not set_knob(unit, planned, ref):
        return {**row, "verdict": "KNOB-WRITE-FAIL"}
    t_reset = time.monotonic()
    say(f"RESTART {k}/{n} {kind} delay {planned} ms from {ref}")
    rc = restart(unit, kind)
    if kind == "wake":
        rc = max(rc, dev("ddc", "--unit", unit, "wake")[0])
        t_reset = time.monotonic()
    reset_at = isostamp.now_ms()
    wall0 = time.time()
    if rc != 0 and kind != "reset":
        return {**row, "reset_at": reset_at, "verdict": f"RESTART-FAIL rc={rc}"}
    if rc != 0:
        return {**row, "reset_at": reset_at, "verdict": f"RESET-FAIL rc={rc}"}
    pause(QUIET_S, "no bus traffic while the panel comes up (the film)")
    m: dict = {}
    while time.monotonic() - t_reset < ACTIVE_WAIT_S:
        _, out = dev("synclog", "--unit", unit)
        m = parse(out)
        if m["active"] is not None and (m["ref"] is not None or m["late"] is not None):
            break
    v = verdict(planned, m, ref) if m else "NO-SYNCLOG"
    if m and m["active"] is None and v == "OK":
        v = "NO-ACTIVE"
    est = (isostamp.datetime.fromtimestamp(wall0 + (m["boot"] or 0) / 1000).astimezone().isoformat(timespec="milliseconds")
           if m.get("boot") is not None else "")
    res = {**row, "knob_seen_ms": m.get("knob"), "reset_at": reset_at, "active_ms": m.get("active"), "bl_boot_ms": m.get("boot"),
           "bl_after_video_ms": m.get("ref"), "bl_at_est": est, "late": m.get("late"), "verdict": v}
    say(f"RUN {k}/{n} {kind} delay {planned} ms from {ref}  restart {reset_at}  ACTIVE at {m.get('active')} ms  backlight on {m.get('boot')} ms after boot "
        f"= {m.get('ref')} ms after the reference  (host ~{est})  knob seen {m.get('knob')}  {v}")
    dev("note", "--unit", unit, f"run {k}/{n} {kind} delay {planned} ms from {ref}")      # console shows it after the backlight is on
    pause(gap_s, "gap between runs (Dan's film: one clear picture per run)")
    return res


def summary(rows: list[dict]) -> str:
    """per planned delay: runs, OK, pin-on after the reference (fw), camera: flash frames per run, first light -> picture (ms)"""
    out = ["", f"{'delay ms':>9} {'runs':>4} {'ok':>3} {'pin after ref ms (min/mean/max)':>32} {'cam flash frames':>18} {'dark->picture ms (min/med/max)':>31}"]
    for p in sorted({r["planned_ms"] for r in rows}):
        rs = [r for r in rows if r["planned_ms"] == p]
        ms = [r["bl_after_video_ms"] for r in rs if r.get("bl_after_video_ms") is not None]
        stat = f"{min(ms)} / {sum(ms) / len(ms):.0f} / {max(ms)}" if ms else "-"
        fl = [r["cam_flash_frames"] for r in rs if r.get("cam_flash_frames") is not None]
        dp = sorted(r["cam_dark_picture_ms"] for r in rs if r.get("cam_dark_picture_ms") is not None)
        dps = f"{dp[0]} / {dp[len(dp) // 2]} / {dp[-1]}" if dp else "-"
        out.append(f"{p:>9} {len(rs):>4} {sum(r['verdict'] == 'OK' for r in rs):>3} {stat:>32} {','.join(map(str, fl)) or '-':>18} {dps:>31}")
    return "\n".join(out)


def write_tsv(rows: list[dict], path: Path = TSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)) for c in COLS) + "\n")


class Camera:
    """--camera: the bench camera records the whole sweep (-c copy, sub stream) from before run 1; afterwards scripts/cam_frames.py
    splits the clip at the restarts and counts frames inside the video (first light, flash, picture) per run."""

    def __init__(self) -> None:
        import cam_frames
        self.cf = cam_frames
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.clip = ROOT / "tmp" / "cam" / f"{stamp}-sweep-sub.mkv"
        self.clip.parent.mkdir(parents=True, exist_ok=True)
        self.proc = cam_frames.start_recording(1, self.clip)
        pause(cam_frames.PRE_ROLL_S, "camera: first IDR (GOP 50 = 2 s) before the first restart")
        say(f"camera recording {self.clip.relative_to(ROOT)} started {isostamp.now_ms()}")

    def stop_and_analyse(self, rows: list[dict]) -> None:
        pause(self.cf.POST_ROLL_S, "camera: last boot settles")
        self.cf.stop_recording(self.proc)
        add_camera_columns(rows, self.clip)


def add_camera_columns(rows: list[dict], clip: Path) -> None:
    """frames counted inside the clip, one restart per row (split at the dark onsets); also re-run offline: --reanalyse"""
    import cam_frames as cf
    sheets = ROOT / "tmp" / "scratch" / "cam" / ("sweep-" + clip.stem[:15])
    res = cf.analyse_sweep(clip, sheet_dir=sheets, expect=len(rows))
    if len(res) != len(rows):
        say(f"camera: {len(res)} restarts in the video, {len(rows)} runs: video not matched to runs (clip kept)")
        return
    for n, (r, (_a, ev)) in enumerate(zip(rows, res, strict=True), 1):
        def ms(a, b, ev=ev):
            sp = ev.span(getattr(ev, a), getattr(ev, b))
            return None if sp is None else round(sp[1])
        r.update(cam_dark_light_ms=ms("dark", "first_light"), cam_flash_frames=len(ev.flash),
                 cam_light_picture_ms=ms("first_light", "stable"), cam_dark_picture_ms=ms("dark", "stable"),
                 cam_sheet=str(sheets / f"run-{n:02d}.png"))


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
    ap.add_argument("--camera", action="store_true", help="record the bench camera for the whole sweep and count frames per run (scripts/cam_frames.py)")
    ap.add_argument("--ref", default="active", choices=sorted(REFS), help="what the delay counts from: ACTIVE (video ready), eDP stream on, panel power-up")
    ap.add_argument("--app-live-ok", action="store_true", help="run although a (shared, idle) GUI app is live: direct access to this unit only")
    ap.add_argument("--reanalyse", nargs=2, metavar=("CLIP", "TSV"), help="re-count the frames of a recorded sweep clip into its TSV (no hardware)")
    ap.add_argument("--kind", default="reset", choices=("reset", "wake"), help="restart path: ISP warm reset or DDC/CI sleep + wake")
    a = ap.parse_args()
    if a.reanalyse:
        rows = [dict(zip(COLS, ln.split("\t"), strict=False)) for ln in Path(a.reanalyse[1]).read_text().splitlines()[1:]]
        for r in rows:
            for c in ("planned_ms", "bl_after_video_ms"):
                r[c] = int(r[c]) if r.get(c) not in (None, "") else None
        add_camera_columns(rows, Path(a.reanalyse[0]))
        write_tsv(rows, Path(a.reanalyse[1]).with_suffix(".reanalysed.tsv"))
        say(summary(rows))
        return 0
    values = [int(x) for x in a.values.split(",")]
    d = knob_defs()
    if any(not 0 <= v <= d["MAX_MS"] for v in values) or a.runs < 1:
        raise SystemExit(f"values 0..{d['MAX_MS']} ms, runs >= 1; nothing done")
    import gui_client
    if gui_client.app_live():       # direct bus access: its own reset + sync-log timing loop; reset / dbg-write are not ported
        if not a.app_live_ok:
            raise SystemExit("bl-sweep: the GUI app is running and owns the unit buses; stop it (./dev.py gui quit) or pass --app-live-ok "
                             "when it is another agent's idle app (its stale job blocks quit); nothing done")
        say("GUI app is live: --app-live-ok, direct bus access on this unit only (unit lock held)")
    serial = json.loads((ROOT / "scripts/devices.json").read_text())["units"][a.unit]["serial"]
    seq = order(values, a.runs)
    est_s = len(seq) * (a.gap_s + RUN_S)                          # RUN_S measured in the dry run
    rows: list[dict] = []
    with unit_lock.held(serial, "bl_sweep"):
        banner(f"START bl-sweep unit {a.unit}: {len(seq)} runs, order {seq[:len(values)]} x {a.runs}\n"
               f"host clock now {isostamp.now_ms()}  (compare with the phone clock; RUN lines carry the reset time)\n"
               f"about {est_s / 60:.0f} min, unattended until the DONE banner; match a camera recording by the RUN reset times")
        bad = 0
        cam = Camera() if a.camera else None
        try:
            for k, p in enumerate(seq, 1):
                r = one_run(a.unit, k, len(seq), p, a.gap_s, a.ref, a.kind)
                rows.append(r)
                write_tsv(rows)
                bad = bad + 1 if r["verdict"].startswith(BROKEN) else 0
                if bad >= STOP_AFTER_FAILS:
                    say(f"ABORT: {bad} runs in a row without the planned knob value ({r['verdict']}): the knob path is broken")
                    break
        finally:
            cleared = set_knob(a.unit, None)
            if cam is not None:
                cam.stop_and_analyse(rows)
                write_tsv(rows)
            say("knob cleared: ok" if cleared else f"knob clear FAILED (power-cycle, or write 0 at {d['ADDR']:#X})")
        say(summary(rows))
        n_ok = sum(r["verdict"] == "OK" for r in rows)
        banner(f"DONE bl-sweep unit {a.unit}: {n_ok} of {len(seq)} runs OK, {isostamp.now_ms()}\nTSV {TSV.relative_to(ROOT)}")
    return 0 if n_ok == len(seq) else 1


if __name__ == "__main__":
    sys.exit(main())
