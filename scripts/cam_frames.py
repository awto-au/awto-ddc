#!/usr/bin/env python3
"""Bench camera: count video frames from a monitor restart to a good LCD picture (docs/camera-lcd-timing.md).

usage (via ./dev.py camframes):
  capture --unit N [--action reset|sleepwake] [--pre S] [--post S] [--main]   record clip(s) + trigger, then analyse
  runs    --unit N [--action A] [--n 5] [--main]                              capture n times, medians at the end
  analyse CLIP.mkv [--roi x0,y0,x1,y1] [--sheet PNG]                          events + frame counts of one clip
Camera login: env AWTO_CAM_USER / AWTO_CAM_PASS, else the `camera` section of ~/.config/awto/secrets.yaml. Never logged.
Counts are frames inside the video (stream PTS); host and camera clocks are not synchronised.
Log: tmp/logs/cam_frames.log
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

CAM_HOST = "192.168.25.240"
RTSP_PORT = 554
FRAME_MS = 40.0                  # 25 fps stream (camera encoder setting)
TILE_W, TILE_H = 352, 264        # analysis size for both streams (ROIs are fractions of the frame)
ROI_BG = (0.62, 0.56, 0.96, 0.78)    # flat desktop area right of the console, clear of the VLC window and the head
ROI_TXT = (0.04, 0.24, 0.58, 0.73)   # diag console text area
ROI_SCR = (0.03, 0.12, 0.97, 0.9)    # whole screen: structure (std of luminance) tells a picture from a uniform flash
TINT_MIN = 0.05          # (B-G)/Y of the desktop picture, even overexposed; a white flash is neutral (|.| < 0.03)
TINT_PRE = 0.15          # the desktop must be at least this tinted before the reset, else the std of the screen decides
SD_FLAT = 0.5            # fallback (neutral desktop): std below this x the pre-reset std = uniform field
PIC_STEP = 1.8           # picture appears as a brightness step of at least this over the preceding 8 frames
PIC_KEEP = 0.8           # and stays above this fraction of that level for the hold (auto exposure ramps down slowly)
DARK_FRAC = 0.6          # Y below this fraction of the pre-reset level = screen dark
GLOW_FRAC = 0.1          # first light = Y step over 2 frames above this fraction of (pre-reset level - dark floor)
FLASH_MIN_Y = 140.0      # a white flash saturates the sensor (Y 180-225 measured); a dark screen lifted by auto exposure stays below (Y ~ 95)
FLASH_RATIO = 1.25       # Y above this x pre-reset level, with no picture colour = flash (white / garbage)
GOOD_TOL = 0.12          # |Y - pre| / pre below this = the pre-reset picture level
GLOW_MIN = 8.0           # Y steps below this above the dark floor are sensor noise (8-bit units)
ONSET_GAP_S = 3.0        # restarts closer than this in one clip are one (the boot itself dips and flashes for ~2 s)
PRE_FRAMES = 10          # frames kept before a restart's dark onset: the pre-reset level for the detector
STABLE_HOLD = 5          # frames (200 ms) the picture must hold for the stable boot picture
SETTLED_HOLD = 10        # frames (400 ms) for the settled picture
PRE_ROLL_S = 3.0         # GOP 50 at 25 fps = 2 s to the first IDR, +1 s margin: the clip starts clean before the trigger
POST_ROLL_S = 10.0       # boot to picture ~ 3 s on the unit, x3 for the console to settle
SLEEP_HOLD_S = 3.0       # DDC/CI sleep held this long before wake: the panel has time to blank
START_TRIES = 4          # the camera sometimes answers a spurious RTSP 401: retry
START_WAIT_S = 12.0       # first byte in the clip or the try is dropped (RTSP setup measured 1-5 s, 12 s when other clients load the camera)

from _log import shared
from _repo import ROOT

LOG = ROOT / "tmp" / "logs" / "cam_frames.log"


def now_iso_ms() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def log(msg: str) -> None:
    shared(LOG, ms=True).say(msg)


def credentials() -> tuple[str, str]:
    u, p = os.environ.get("AWTO_CAM_USER"), os.environ.get("AWTO_CAM_PASS")
    if u and p:
        return u, p
    try:
        import yaml
        sec = yaml.safe_load((Path.home() / ".config/awto/secrets.yaml").read_text()).get("camera") or {}
        if sec.get("username") and sec.get("password"):
            return sec["username"], sec["password"]
    except (OSError, ImportError, AttributeError):
        pass
    raise SystemExit("camera login: set AWTO_CAM_USER and AWTO_CAM_PASS (or a camera section in secrets.yaml)")


def rtsp_url(sub: int) -> str:
    u, p = credentials()
    return f"rtsp://{u}:{p}@{CAM_HOST}:{RTSP_PORT}/cam/realmonitor?channel=1&subtype={sub}"


# ---------------------------------------------------------------- analysis

@dataclass
class Events:
    """Frame indices (None = not found); ms = stream PTS."""
    n_frames: int = 0
    last_good: int | None = None
    dark: int | None = None
    first_light: int | None = None
    stable: int | None = None
    console: int | None = None
    settled: int | None = None
    flash: list[int] = field(default_factory=list)
    pts_ms: list[float] = field(default_factory=list)
    level_pre: float = 0.0
    level_dark: float = 0.0
    level_settled: float = 0.0
    note: str = ""

    def ms(self, i: int | None) -> float | None:
        return None if i is None else self.pts_ms[i]

    def span(self, a: int | None, b: int | None) -> tuple[int, float] | None:
        if a is None or b is None:
            return None
        return b - a, self.pts_ms[b] - self.pts_ms[a]


def iter_frames(clip: Path):
    """Decoded frames (H, W, 3) uint8 at TILE size, every frame (none dropped or duplicated), streamed."""
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(clip), "-vf", f"scale={TILE_W}:{TILE_H}",
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    size = TILE_W * TILE_H * 3
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as p:
        while len(buf := p.stdout.read(size)) == size:
            yield np.frombuffer(buf, np.uint8).reshape(TILE_H, TILE_W, 3)


def clip_pts(clip: Path, n: int) -> list[float]:
    """Stream PTS in ms from the first frame; frame index * 40 ms if the container has none."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                            "-of", "csv=p=0", str(clip)], capture_output=True, text=True, check=True).stdout
    pts = []
    for ln in probe.split():
        try:
            pts.append(float(ln.split(",")[0]) * 1000.0)
        except ValueError:
            pass
    if len(pts) != n:
        pts = [i * FRAME_MS for i in range(n)]
    return [p - pts[0] for p in pts] if pts else pts


def clip_metrics(clip: Path, roi) -> tuple[dict[str, np.ndarray], list[float]]:
    """Per-frame ROI metrics of the whole clip (frames are not kept) + PTS."""
    parts, batch = [], []
    for f in iter_frames(clip):
        batch.append(f)
        if len(batch) == 64:
            parts.append(metrics(np.stack(batch), roi))
            batch = []
    if batch:
        parts.append(metrics(np.stack(batch), roi))
    m = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]} if parts else {k: np.zeros(0) for k in ("Y", "R", "G", "B", "txt")}
    return m, clip_pts(clip, len(m["Y"]))


def grab(clip: Path, idxs: set[int]) -> dict[int, np.ndarray]:
    return {i: f.copy() for i, f in enumerate(iter_frames(clip)) if i in idxs}


def _crop(frames: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    x0, y0, x1, y1 = roi
    return frames[:, int(y0 * TILE_H):int(y1 * TILE_H), int(x0 * TILE_W):int(x1 * TILE_W), :]


def _screen_sd(frames: np.ndarray) -> np.ndarray:
    c = _crop(frames, ROI_SCR).astype(np.float32)
    return (0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]).std(axis=(1, 2))


def metrics(frames: np.ndarray, roi: tuple[float, float, float, float], roi_txt=ROI_TXT) -> dict[str, np.ndarray]:
    c = _crop(frames, roi).astype(np.float32)
    y = 0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]
    t = _crop(frames, roi_txt).astype(np.int16)
    text = (t.max(axis=-1) > 150) & (t[..., 1] - t[..., 0] >= 30)      # bright green / cyan console text
    return {"Y": y.mean(axis=(1, 2)), "R": c[..., 0].mean(axis=(1, 2)), "G": c[..., 1].mean(axis=(1, 2)),
            "B": c[..., 2].mean(axis=(1, 2)), "txt": text.mean(axis=(1, 2)),
            "sd": _screen_sd(frames)}


def _first_hold(ok: np.ndarray, start: int, hold: int) -> int | None:
    for i in range(start, len(ok) - hold + 1):
        if ok[i:i + hold].all():
            return i
    return None


def find_events(m: dict[str, np.ndarray], pts_ms: list[float]) -> Events:
    """Camera auto exposure drifts for seconds after a dark phase, so levels are compared inside one restart only:
    first light = a brightness step; flash = bright and neutral (white; the desktop stays tinted even when
    overexposed); picture = a step to the tinted desktop that keeps its level."""
    y, sd, n = m["Y"], m["sd"], len(m["Y"])
    ev = Events(n_frames=n, pts_ms=pts_ms)
    if n < 30:
        ev.note = "clip too short"
        return ev
    pre, pre_sd = float(np.median(y[:10])), float(np.median(sd[:10]))
    chroma = (m["B"] - m["G"]) / np.maximum(y, 1.0)
    tinted = chroma >= TINT_MIN if float(np.median(chroma[:10])) >= TINT_PRE else sd >= SD_FLAT * pre_sd
    ev.level_pre = pre
    dark_idx = np.nonzero(y < DARK_FRAC * pre)[0]
    if not len(dark_idx):
        ev.note = "no blackout found in the ROI (reset not visible)"
        return ev
    ev.dark = int(dark_idx[0])
    good = np.nonzero(np.abs(y[:ev.dark] - pre) <= GOOD_TOL * pre)[0]
    ev.last_good = int(good[-1]) if len(good) else None
    floor = float(np.min(y[ev.dark:ev.dark + 10]))
    ev.level_dark = floor
    thr = max(GLOW_MIN, GLOW_FRAC * (pre - floor))
    step = y[ev.dark + 2:] - y[ev.dark:-2]               # a step, not the slow auto-exposure ramp of a dark screen
    lit = np.nonzero(step > thr)[0]
    if not len(lit):
        ev.note = "never lit again"
        return ev
    ev.first_light = ev.dark + 2 + int(lit[0])
    if y[ev.first_light - 1] - y[ev.first_light - 2] > thr / 2:      # the step started one frame earlier (rolling shutter)
        ev.first_light -= 1
    pic = np.zeros(n, bool)
    for i in range(8, n - STABLE_HOLD):
        pic[i] = (bool(np.median(tinted[i:i + STABLE_HOLD])) and y[i] >= PIC_STEP * float(np.min(y[i - 8:i]))
                  and bool((y[i + 1:i + STABLE_HOLD] >= PIC_KEEP * y[i]).all()))
    cand = np.nonzero(pic[ev.first_light:])[0]
    ev.stable = ev.first_light + int(cand[0]) if len(cand) else None
    end = ev.stable if ev.stable is not None else n
    ev.flash = [i for i in range(ev.first_light, end) if y[i] > max(FLASH_RATIO * pre, FLASH_MIN_Y) and not tinted[i]]
    if ev.flash and ev.flash[0] == ev.first_light + 1:       # the wipe frame (rolling shutter) that starts the flash
        ev.flash.insert(0, ev.first_light)
    txt = np.convolve(m["txt"], np.ones(3) / 3, mode="same")
    txt_final = float(np.median(m["txt"][-15:]))
    if txt_final > 0.002:
        c = np.nonzero(txt[ev.first_light:] > 0.5 * txt_final)[0]
        ev.console = ev.first_light + int(c[0]) if len(c) else None
        if ev.stable is not None:
            ev.settled = _first_hold(txt > 0.5 * txt_final, ev.stable, SETTLED_HOLD)
    ev.level_settled = float(np.median(y[-15:]))
    return ev


def table(ev: Events) -> list[str]:
    rows = [("last good picture", ev.last_good), ("screen dark", ev.dark), ("first light", ev.first_light),
            ("picture present (stable)", ev.stable), ("console text visible", ev.console), ("settled", ev.settled)]
    out = [f"frames {ev.n_frames}  level pre/dark/end Y = {ev.level_pre:.1f} / {ev.level_dark:.1f} / {ev.level_settled:.1f}"
           + (f"  NOTE {ev.note}" if ev.note else ""),
           f"{'event':<26}{'frame':>6}{'t ms':>9}{'+frames':>9}{'+ms':>8}"]
    prev = None
    rows.sort(key=lambda r: (r[1] is None, r[1]))     # time order (the console can precede the picture)
    for name, i in rows:
        if i is None:
            out.append(f"{name:<26}{'-':>6}")
            continue
        d = f"{i - prev:>9}{ev.pts_ms[i] - ev.pts_ms[prev]:>8.0f}" if prev is not None else ""
        out.append(f"{name:<26}{i:>6}{ev.pts_ms[i]:>9.0f}{d}")
        prev = i
    out.append(f"flash frames (first light to stable, Y > {FLASH_RATIO} x pre, neutral): {len(ev.flash)}  {ev.flash}")
    return out


def sheet_indices(ev: Events, off: int = 0) -> set[int]:
    return {min(max(i - 1 + c, 0), ev.n_frames - 1) + off for _n, i in _marks(ev) for c in range(4)}


def _marks(ev: Events) -> list[tuple[str, int]]:
    marks = [("last good", ev.last_good), ("dark", ev.dark), ("first light", ev.first_light), ("stable", ev.stable),
             ("console", ev.console), ("settled", ev.settled)]
    marks = [(k, i) for k, i in marks if i is not None]
    if ev.flash and ev.flash[0] != ev.first_light:
        marks.insert(3, ("flash", ev.flash[0]))
    return marks


def contact_sheet(frames: dict[int, np.ndarray], ev: Events, y: np.ndarray, roi, path: Path, off: int = 0, title: str = "") -> None:
    """Rows = events, 4 columns = frame before, the event frame (marked <), 2 after. Frame numbers are clip frames (off + local)."""
    from PIL import Image, ImageDraw
    marks = _marks(ev)
    cols = 4
    sheet = Image.new("RGB", (cols * TILE_W, max(1, len(marks)) * TILE_H), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    x0, y0, x1, y1 = roi
    for r, (name, i) in enumerate(marks):
        for c in range(cols):
            j = min(max(i - 1 + c, 0), ev.n_frames - 1)
            ox, oy = c * TILE_W, r * TILE_H
            sheet.paste(Image.fromarray(frames[j + off]), (ox, oy))
            d.rectangle([ox + x0 * TILE_W, oy + y0 * TILE_H, ox + x1 * TILE_W, oy + y1 * TILE_H], outline=(255, 0, 0))
            d.rectangle([ox, oy, ox + TILE_W, oy + 13], fill=(0, 0, 0))
            d.text((ox + 3, oy + 1), f"{title}{name} f{j} {ev.pts_ms[j]:.0f}ms Y{y[j]:.0f}{' <' if j == i else ''}", fill=(255, 255, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def analyse(clip: Path, roi=ROI_BG, sheet: Path | None = None) -> Events:
    m, pts = clip_metrics(clip, roi)
    ev = find_events(m, pts)
    for ln in table(ev):
        log(ln)
    if sheet is not None and ev.dark is not None:
        contact_sheet(grab(clip, sheet_indices(ev)), ev, m["Y"], roi, sheet)
        log(f"contact sheet {sheet}")
    return ev


def run_onsets(m: dict[str, np.ndarray]) -> list[int]:
    """First dark frame of each restart in a long clip: Y < DARK_FRAC x the median of the 1 s before, >= ONSET_GAP_S apart."""
    y, out = m["Y"], []
    for i in range(25, len(y)):
        if y[i] < DARK_FRAC * np.median(y[i - 25:i]) and (not out or i - out[-1] >= int(ONSET_GAP_S * 25)):
            out.append(i)
    return out


def analyse_sweep(clip: Path, roi=ROI_BG, sheet_dir: Path | None = None, expect: int | None = None) -> list[tuple[int, Events]]:
    """One clip holding many restarts: split at the dark onsets (frame counts stay inside the video), events per restart."""
    m, pts = clip_metrics(clip, roi)
    on = run_onsets(m)
    log(f"sweep clip {clip.name}: {len(m['Y'])} frames, {len(on)} restarts found" + (f", {expect} expected" if expect else ""))
    res: list[tuple[int, Events]] = []
    for k, o in enumerate(on):
        a, b = max(0, o - PRE_FRAMES), (on[k + 1] - PRE_FRAMES if k + 1 < len(on) else len(m["Y"]))
        seg = {key: v[a:b] for key, v in m.items()}
        ev = find_events(seg, [t - pts[a] for t in pts[a:b]])
        res.append((a, ev))
    if sheet_dir is not None:
        want: set[int] = set()
        for a, ev in res:
            want |= sheet_indices(ev, a) if ev.dark is not None else set()
        got = grab(clip, want)
        for k, (a, ev) in enumerate(res, 1):
            if ev.dark is not None:
                contact_sheet(got, ev, m["Y"][a:], roi, sheet_dir / f"run-{k:02d}.png", a, f"r{k} ")
    return res


# ---------------------------------------------------------------- capture

def start_recording(sub: int, out: Path) -> subprocess.Popen:
    """ffmpeg -c copy (no re-encode); retried on the camera's spurious RTSP 401."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-rtsp_transport", "tcp", "-buffer_size", "8000000",
           "-i", rtsp_url(sub), "-c:v", "copy", "-an", str(out)]
    for attempt in range(1, START_TRIES + 1):
        out.unlink(missing_ok=True)
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        t0 = time.monotonic()
        while time.monotonic() - t0 < START_WAIT_S:
            if p.poll() is not None:
                break
            if out.exists() and out.stat().st_size > 0:
                log(f"recording subtype={sub} started (try {attempt}) {out.name}")
                return p
            time.sleep(0.05)       # poll: first clip byte, bounded by START_WAIT_S
        p.kill()
        log(f"recording subtype={sub} try {attempt} failed ({START_WAIT_S:.0f} s limit), retry")
    raise SystemExit(f"camera stream subtype={sub} did not start in {START_TRIES} tries")


def stop_recording(p: subprocess.Popen) -> None:
    p.send_signal(signal.SIGINT)         # ffmpeg finalises the mkv on SIGINT
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
        log("ffmpeg did not stop in 5 s: killed")


def run_dev(*args: str) -> int:
    r = subprocess.run([sys.executable, str(ROOT / "dev.py"), *args], cwd=ROOT, capture_output=True, text=True, check=False)
    log(f"dev.py {' '.join(args)} rc={r.returncode}")
    return r.returncode


def capture(unit: str, action: str, pre: float, post: float, main: bool, label: str = "") -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = ROOT / "tmp" / "cam"
    outdir.mkdir(parents=True, exist_ok=True)
    clips = {"sub": outdir / f"{stamp}-u{unit}-{action}-sub.mkv"}
    procs = {"sub": start_recording(1, clips["sub"])}
    if main:
        clips["main"] = outdir / f"{stamp}-u{unit}-{action}-main.mkv"
        procs["main"] = start_recording(0, clips["main"])
    time.sleep(pre)                       # PRE_ROLL_S: first IDR within 2 s, clean good picture before the trigger
    t_trig = now_iso_ms()
    if action == "reset":
        rc = run_dev("reset", "--unit", unit)
    elif action == "sleepwake":
        rc = run_dev("ddc", "--unit", unit, "sleep")
        time.sleep(SLEEP_HOLD_S)
        rc = max(rc, run_dev("ddc", "--unit", unit, "wake"))
    else:
        raise SystemExit(f"unknown action {action}")
    t_done = now_iso_ms()
    time.sleep(post)                      # POST_ROLL_S: boot + console settle
    for p in procs.values():
        stop_recording(p)
    meta = {"unit": unit, "action": action, "trigger_start": t_trig, "trigger_done": t_done, "rc": rc,
            "clips": {k: str(v) for k, v in clips.items()}}
    for v in clips.values():
        v.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    log(f"capture {label}{action} unit {unit}: trigger {t_trig} -> {t_done} rc={rc}")
    return meta


def summarise(results: list[Events]) -> list[str]:
    def col(f) -> list[float]:
        return [v for v in (f(e) for e in results) if v is not None]

    def row(name: str, vals: list[float], unit: str) -> str:
        if not vals:
            return f"{name:<34} n/a"
        return f"{name:<34} median {statistics.median(vals):7.0f}  min {min(vals):7.0f}  max {max(vals):7.0f} {unit}  (n={len(vals)})"

    def ms(e: Events, a: str, b: str) -> float | None:
        s = e.span(getattr(e, a), getattr(e, b))
        return None if s is None else s[1]

    return [row("dark -> first light", col(lambda e: ms(e, "dark", "first_light")), "ms"),
            row("first light -> stable picture", col(lambda e: ms(e, "first_light", "stable")), "ms"),
            row("first light -> console text", col(lambda e: ms(e, "first_light", "console")), "ms"),
            row("dark -> stable picture", col(lambda e: ms(e, "dark", "stable")), "ms"),
            row("flash frames", [float(len(e.flash)) for e in results], "frames")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "runs"):
        s = sub.add_parser(name)
        s.add_argument("--unit", required=True)
        s.add_argument("--action", default="reset", choices=("reset", "sleepwake"))
        s.add_argument("--pre", type=float, default=PRE_ROLL_S)
        s.add_argument("--post", type=float, default=POST_ROLL_S)
        s.add_argument("--main", action="store_true", help="also record + analyse the main stream")
        s.add_argument("--roi", default=",".join(map(str, ROI_BG)))
        if name == "runs":
            s.add_argument("--n", type=int, default=5)
    a = sub.add_parser("analyse")
    a.add_argument("clips", nargs="+")
    a.add_argument("--roi", default=",".join(map(str, ROI_BG)))
    a.add_argument("--sheet")
    args = ap.parse_args(argv)
    roi = tuple(float(v) for v in args.roi.split(","))
    if args.cmd == "analyse":
        for c in args.clips:
            analyse(Path(c), roi, Path(args.sheet) if args.sheet else None)
        return 0
    results: dict[str, list[Events]] = {}
    for i in range(args.n if args.cmd == "runs" else 1):
        meta = capture(args.unit, args.action, args.pre, args.post, args.main, f"run {i + 1} ")
        for k, c in meta["clips"].items():
            sheet = ROOT / "tmp" / "scratch" / "cam" / (Path(c).stem + ".png")
            results.setdefault(k, []).append(analyse(Path(c), roi, sheet))
    for k, evs in results.items():
        log(f"--- {args.action} unit {args.unit} stream {k}: {len(evs)} runs")
        for ln in summarise(evs):
            log(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
