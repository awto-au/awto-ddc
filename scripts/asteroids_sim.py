#!/usr/bin/env python3
"""Asteroids screensaver (fw/test/asteroids.c) in the firmware simulator -> PNG frames + MP4 (+ WAV of the sounds). Nothing touches hardware.

usage: asteroids_sim.py [BIN MAP] [--seconds S] [--out DIR] [--fps F] [--scale N] [--rotate] [--bg black]
  - BIN / MAP default: tmp/fw/AWT26110003-sv1-be.{bin,map} (dev.py build --serial AWT26110003 --tag sv1 -D _AWTO_AUDIO_TEST; a default build has no sound).
  - DDC/CI VCP 0xEB = 8 starts the saver; frame k = OSD state at T0 + k / fps of firmware time. --rotate: display Rotate 180 first (docs/osd/rotation.md).
  - Output: DIR/frames/f%04d.png, DIR/asteroids.mp4 (with the sound when the image has the audio generator), DIR/asteroids.wav, DIR/steps.tsv (game step per frame).
Log: ./tmp/logs/asteroids_sim.log
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import isostamp

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_sim as A
import ddc_sim as D
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/asteroids_sim.log"
VCP_SAVER = 0xEB
VCP_ASTEROIDS = 8               # screensaver_now option "Asteroids" (7 is kept free)
ROW_DISP_ROTATE = 32            # registry row id of disp_rotate
ROTATE_SETTLE_S = 6.0           # fw time for the display re-set after Rotate changes
FFMPEG_LIMIT_S = 240            # x264 + aac of <= ~600 frames at 1080p: expected < 60 s; expiry = ffmpeg hung


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=ROOT / "tmp/fw/AWT26110003-sv1-be.bin")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/asteroids_sim")
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--bg", default="black")
    ap.add_argument("--rotate", action="store_true")
    a = ap.parse_args()
    frames_dir = a.out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    eng = D.DdcEngine()
    clock = lambda: sess.bus.now() if tap.armed else 0.0
    tap = A.AudioTap(clock)
    tap.armed = False
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng, tap])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1 if a.rotate else 0)
    sess.bus.wait(ROTATE_SETTLE_S)
    tap.armed = True
    addr = sess.bus.m.addr("g_usAwtoAstStep")
    rd = lambda: int.from_bytes(sess.bus.m.rd(addr, 2), "big")
    t0 = sess.bus.now()
    ddc.set(VCP_SAVER, VCP_ASTEROIDS)
    n = int(a.seconds * a.fps)
    steps = []
    for k in range(n):
        sess.bus.wait(max(0.0, t0 + k / a.fps - sess.bus.now()))
        R.render_snap(sess.snap(), a.bg, a.scale).save(frames_dir / f"f{k:04d}.png")
        steps.append(rd())
    t1 = sess.bus.now()
    ddc.set(VCP_SAVER, 0)
    sess.bus.wait(3.0)
    info = A.write_wav(a.out / "asteroids.wav", tap.events, t0, t1)
    sess.bus.close()
    (a.out / "steps.tsv").write_text("frame\tstep\n" + "".join(f"{k}\t{s}\n" for k, s in enumerate(steps)))
    say(f"{n} frames over {t1 - t0:.1f} s fw time, game steps {steps[0]} -> {steps[-1]} ({(steps[-1] - steps[0]) / (t1 - t0):.1f} steps/s), sound {info['tone_s']:.2f} s of tone, {info['events']} audio events")
    if not shutil.which("ffmpeg"):
        say("ffmpeg missing: frames + wav only")
        return 1
    mp4 = a.out / "asteroids.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{a.fps:g}", "-i", str(frames_dir / "f%04d.png")]
    cmd += (["-i", str(a.out / "asteroids.wav"), "-c:a", "aac", "-shortest"] if info["tone_s"] > 0 else [])
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_LIMIT_S, check=False)
    except subprocess.TimeoutExpired:
        say(f"ffmpeg: no result within {FFMPEG_LIMIT_S} s (expected < 60 s)")
        return 1
    say(f"ffmpeg rc {r.returncode} {r.stderr.strip()[:300]} -> {mp4}")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
