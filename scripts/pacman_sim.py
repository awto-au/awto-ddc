#!/usr/bin/env python3
"""Pac-Man demo with sound in the firmware simulator -> MP4 (video: OSD model render, audio: audio_sim tap). Nothing touches hardware.

usage: pacman_sim.py [BIN MAP] [--steps N] [--out DIR] [--k-hz HZ] [--fps F] [--scale S] [--tag TAG]
  - BIN / MAP default: tmp/fw/AWT26110003-simav-be.{bin,map} = `./dev.py build --tree . --serial AWT26110003 --tag simav -D _AWTO_AUDIO_TEST`.
  - Sequence (test cmds): 0xB7 maze + 0xBA intro at t = 0 (the other way round the draw kills the intro: it calls OsdFuncDisableOsd, which turns the generator off), then from the end of the intro 0xBB waka loop and one 0xB8 step per
    frame period (one cmd per main pass: a cmd sent right after another is lost, so they sit a pass or a frame apart) (--fps, default 8 = pacman_unit.py), 0xBE stop after the last step. Video frame k = OSD state at firmware time T0 + k / fps.
  - Audio = audio_sim.py model of the generator / amp writes over the same firmware clock (T0 .. end), so sound and picture stay in sync.
  - Output DIR (default tmp/pacman_sim): pacman.mp4 (H.264 yuv420p + AAC), pacman.wav, frames/f%04d.png, events.tsv (the recorded writes).
Log: ./tmp/logs/pacman_sim.log
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_sim as A
import card_shot as C
import osd_render as R
import pacman_sound as PS

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/pacman_sim.log"
TC_DRAW, TC_STEP, TC_OFF = 0xB7, 0xB8, 0xB9
TC_INTRO, TC_WAKA, TC_STOP = 0xBA, 0xBB, 0xBE
DEFAULT_BIN = ROOT / "tmp/fw/AWT26110003-simav-be.bin"
PASS_S = 0.1                    # fw time for the main loop to consume a test cmd (one cmd per pass; 0.5 s in card_shot.send, a pass is ~ms)
FFMPEG_LIMIT_S = 180            # x264 + aac of <= ~400 frames at 1080p: expected < 30 s; expiry = ffmpeg hung, error logged


def say(s: str) -> None:
    _log_line(s, LOG)


def send(s, cmd: int) -> None:
    """Test cmd without C.send's 0.5 s wait: the bus writes themselves advance firmware time."""
    addr = s.diag + C.T.TESTCMD_OFF
    ok = (s.bus.write(0x6A, 0x01, bytes([addr >> 8])) and s.bus.write(0x6A, 0x03, bytes([cmd]))
          and s.bus.write(0x6A, 0x3B, bytes([addr & 0xFF])))
    if not ok:
        say(f"  test cmd 0x{cmd:02X} NAK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=DEFAULT_BIN)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/pacman_sim")
    ap.add_argument("--k-hz", type=float, default=PS.PS_K_DEFAULT_HZ)
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--scale", type=int, default=2, help="panel 3840x2160 / scale = video size (2 = 1920x1080)")
    ap.add_argument("--bg", default="black")
    ap.add_argument("--game", action="store_true", help="the firmware plays the sounds itself from the game events (pacman_classic.c): only draw (0xB7), step (0xB8), off (0xB9)")
    a = ap.parse_args()
    binp, mapp = a.bin, a.map or a.bin.with_suffix(".map")
    if not binp.exists():
        sys.exit(f"{binp} missing: build it with dev.py build ... --tag simav -D _AWTO_AUDIO_TEST")
    frames_dir = a.out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    tap = A.AudioTap(lambda: sess.bus.now() if tap.armed else 0.0)
    tap.armed = False
    sess = R.Session(binp, mapp, "1080p60", devs=[tap])
    sess.boot()
    tap.armed = True
    say(f"booted {binp.name}; K = {a.k_hz:g} Hz, {a.steps} steps at {a.fps:g} fps")

    period = 1.0 / a.fps
    intro_s = sum(ms for _, ms in PS.steps("intro")) / 1000.0
    k_waka = math.ceil(intro_s / period)                # first frame after the intro
    total = (a.steps + 3) if a.game else (k_waka + a.steps + 2)
    t0 = sess.bus.now()
    for k in range(total):
        sess.bus.wait(max(0.0, t0 + k * period - sess.bus.now()))
        st = sess.snap()
        R.render_snap(st, a.bg, a.scale).save(frames_dir / f"f{k:04d}.png")
        if a.game:
            if k == 0:
                send(sess, TC_DRAW)
            elif k <= a.steps:
                send(sess, TC_STEP)
            elif k == a.steps + 1:
                send(sess, TC_OFF)
        elif k == 0:
            send(sess, TC_DRAW)                         # maze first: OsdFuncDisableOsd (inside the draw) switches the audio generator off
            sess.bus.wait(PASS_S)
            send(sess, TC_INTRO)
        elif k == k_waka:
            send(sess, TC_WAKA)
        elif k_waka < k <= k_waka + a.steps:
            send(sess, TC_STEP)
        elif k == k_waka + a.steps + 1:
            send(sess, TC_STOP)
        if k % 8 == 0:
            say(f"frame {k}/{total} fw t = {sess.bus.now() - t0:.3f} s, {len(tap.events)} audio events")
    t_end = t0 + total * period
    sess.bus.wait(0.05)

    model = {"k_hz": a.k_hz}
    wav = a.out / "pacman.wav"
    info = A.write_wav(wav, tap.events, t0, t_end, model=model)
    (a.out / "events.tsv").write_text("".join(f"{t - t0:.4f}\t{kind}\t{x}\t{v}\n" for t, kind, x, v in tap.events))
    say(f"wav {wav}: {info['samples'] / info['rate']:.2f} s, tone {info['tone_s']:.2f} s, {info['events']} events")
    if info["tone_s"] == 0:
        say("WARNING: no tone: the generator / amp writes never reached the tap (image without -D _AWTO_AUDIO_TEST?)")
    if not shutil.which("ffmpeg"):
        say("ffmpeg missing: frames + wav only")
        return 1
    mp4 = a.out / "pacman.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{a.fps:g}", "-i", str(frames_dir / "f%04d.png"), "-i", str(wav),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_LIMIT_S, check=False)
    except subprocess.TimeoutExpired:
        say(f"ffmpeg: no result within {FFMPEG_LIMIT_S} s (expected < 30 s)")
        return 1
    say(f"ffmpeg rc {r.returncode} {r.stderr.strip()[:300]} -> {mp4}")
    sess.bus.close()
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
