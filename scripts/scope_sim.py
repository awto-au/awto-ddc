#!/usr/bin/env python3
"""Scope screensaver (fw/test/scope_saver.c) in the firmware simulator -> PNG frames + MP4. Nothing touches hardware.

usage: scope_sim.py [BIN MAP] [--frames N] [--out DIR] [--fps F] [--scale S]
  - BIN / MAP default: tmp/fw/AWT26110003-sc1-be.{bin,map} (dev.py build --tree . --serial AWT26110003 --tag sc1).
  - Test cmds: 0xB4 draw, then 0xB5 per frame (one cmd per main pass), 0xB6 off.
Log: ./tmp/logs/scope_sim.log
"""
import argparse
import os
import shutil
import subprocess
import sys
import isostamp  # noqa: E402
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import pacman_sim as P  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/scope_sim.log"
TC_DRAW, TC_FRAME, TC_OFF = 0xB4, 0xB5, 0xB6
DEFAULT_BIN = ROOT / "tmp/fw/AWT26110003-sc1-be.bin"
FFMPEG_LIMIT_S = 120            # x264 of <= ~100 frames at 1080p: expected < 15 s; expiry = ffmpeg hung


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=DEFAULT_BIN)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scope_sim")
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--bg", default="black")
    a = ap.parse_args()
    binp, mapp = a.bin, a.map or a.bin.with_suffix(".map")
    frames_dir = a.out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    sess = R.Session(binp, mapp, "1080p60")
    sess.boot()
    period = 1.0 / a.fps
    t0 = sess.bus.now()
    for k in range(a.frames + 2):
        sess.bus.wait(max(0.0, t0 + k * period - sess.bus.now()))
        R.render_snap(sess.snap(), a.bg, a.scale).save(frames_dir / f"f{k:04d}.png")
        if k == 0:
            P.send(sess, TC_DRAW)
        elif k <= a.frames:
            P.send(sess, TC_FRAME)
        else:
            P.send(sess, TC_OFF)
        say(f"frame {k} fw t = {sess.bus.now() - t0:.3f} s")
    sess.bus.close()
    if not shutil.which("ffmpeg"):
        say("ffmpeg missing: frames only")
        return 1
    mp4 = a.out / "scope.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{a.fps:g}", "-i", str(frames_dir / "f%04d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_LIMIT_S)
    except subprocess.TimeoutExpired:
        say(f"ffmpeg: no result within {FFMPEG_LIMIT_S} s (expected < 15 s)")
        return 1
    say(f"ffmpeg rc {r.returncode} {r.stderr.strip()[:300]} -> {mp4}")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
