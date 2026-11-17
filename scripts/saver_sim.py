#!/usr/bin/env python3
"""Screensaver check in the firmware simulator (docs/screensaver.md): DDC/CI VCP 0xEB starts / stops Pac-Man and the scope; PNGs of each.

usage: saver_sim.py [BIN MAP] [--out DIR]
  - BIN / MAP default: tmp/fw/AWT26110003-sv1-be.{bin,map} (wb_build.py --tree . --serial AWT26110003 --tag sv1 -D _AWTO_AUDIO_TEST).
  - Steps: boot; VCP 0xEB = 3 (scope), 2 (Pac-Man), 4 (scope 2): wait, render, then = 0 (stop), render. PASS = font SRAM written and something on screen when started,
    OSD closed (no window cells drawn) after stop. Exit 1 on a FAIL.
Log: ./tmp/logs/saver_sim.log
"""
import argparse
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path
from PIL import Image

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402
import audio_sim as A  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_sim.log"
VCP_SAVER = 0xEB
RUN_S = 8.0                     # fw time for the draw (scope: 64 passes of tile uploads, ~1.5 s) plus one frame
ROW_DISP_ROTATE = 32            # registry row id of disp_rotate (fw/rtdfw/settings/registry.tsv)
ROTATE_SETTLE_S = 6.0           # fw time for the display re-set after Rotate changes
SHRINK = 8                      # box shrink factor before comparing
ROT_MAX_DIFF = 8.0              # mean abs difference allowed between the turned upright render and the rotated render (of 255); the scope 1 trace is animated, its phase differs between the two runs
ROT_BETTER = 1.5               # the turned comparison must beat the unturned one by this factor
VCP_ALERT = 6                   # screensaver_now option "Alert tone"
ALERT_TONE_S = 0.9              # audible time: the 1 s track (pacman_sound.py ALERT) has 100 ms of rests between the notes
ALERT_TOL_S = 0.15              # one 10 ms tick per note plus the 1 ms firmware timer: well inside
ALERT_OBSERVE_S = 3.0           # fw time to observe: the tone must end by itself
STOP_S = 3.0                    # fw time for the stop: served by the main loop after the frame in progress (scope 2: up to ~2 s)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def bbox_crop(img):
    """The non-black box of a render (the OSD area) as an array."""
    a = np.asarray(img.convert("RGB"))
    ys, xs = np.nonzero(a.sum(axis=2))
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else a[:0, :0]


def shrunk_diff(a, b) -> float:
    """Mean absolute difference (0..255) of two equal-size renders after shrinking 8x (the scale-up rounds edges by a pixel)."""
    h, w = (a.shape[0] // SHRINK) * SHRINK, (a.shape[1] // SHRINK) * SHRINK
    sa = a[:h, :w].astype(float).reshape(h // SHRINK, SHRINK, w // SHRINK, SHRINK, 3).mean(axis=(1, 3))
    sb = b[:h, :w].astype(float).reshape(h // SHRINK, SHRINK, w // SHRINK, SHRINK, 3).mean(axis=(1, 3))
    return float(np.abs(sa - sb).mean())


def lit(st) -> int:
    return sum(1 for w in st.font.values() if any(w))


def rotated_check(a) -> int:
    """Display Rotate 180 (settings row 32 through the paged pair 0xE0 / 0xE1): each saver must draw the same picture turned 180 inside its box."""
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1)
    sess.bus.wait(ROTATE_SETTLE_S)
    fails = 0
    for name, val in (("scope", 3), ("pacman", 2), ("scope2", 4)):
        up = bbox_crop(Image.open(a.out / f"{name}_run.png"))
        ddc.set(VCP_SAVER, val)
        sess.bus.wait(RUN_S)
        img = R.render_snap(sess.snap(), "black", 2)
        img.save(a.out / f"{name}_run_rot.png")
        rot = bbox_crop(img)
        d_turned, d_plain = shrunk_diff(np.rot90(up, 2), rot), shrunk_diff(up, rot)
        same = up.shape == rot.shape and up.size > 0 and d_turned <= ROT_MAX_DIFF and d_turned * ROT_BETTER <= d_plain
        fails += not same
        say(f"{'PASS' if same else 'FAIL'} Rotate 180 {name}: box {up.shape[:2]}, mean difference to the upright render turned {d_turned:.1f} (limit {ROT_MAX_DIFF}), not turned {d_plain:.1f} (turned must be {ROT_BETTER}x smaller)")
        ddc.set(VCP_SAVER, 0)
        sess.bus.wait(STOP_S)
    sess.bus.close()
    return fails


def alert_check(a) -> int:
    """VCP 0xEB = 6 plays the 1 s alert tone: the audio tap hears ~1 s of tone, and the generator is off afterwards."""
    eng = D.DdcEngine()
    tap = A.AudioTap(lambda: sess.bus.now() if tap.armed else 0.0)
    tap.armed = False
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng, tap])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    tap.armed = True
    t0 = sess.bus.now()
    ddc.set(VCP_SAVER, VCP_ALERT)
    sess.bus.wait(ALERT_OBSERVE_S)
    info = A.write_wav(a.out / "alert.wav", tap.events, t0, sess.bus.now())
    ok = abs(info["tone_s"] - ALERT_TONE_S) <= ALERT_TOL_S
    say(f"{'PASS' if ok else 'FAIL'} VCP 0xEB = {VCP_ALERT} (alert): tone {info['tone_s']:.2f} s (expect {ALERT_TONE_S} +- {ALERT_TOL_S})")
    sess.bus.close()
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=ROOT / "tmp/fw/AWT26110003-sv1-be.bin")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/saver_sim")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)                  # the registry default is Rotate 180: the upright renders need Rotate 0
    ddc.set(0xE1, 0)
    sess.bus.wait(ROTATE_SETTLE_S)
    fails = 0
    for name, val in (("scope", 3), ("pacman", 2), ("scope2", 4), ("flash", 5)):
        base = lit(sess.snap())
        ddc.set(VCP_SAVER, val)
        sess.bus.wait(RUN_S)
        st = sess.snap()
        run_img = R.render_snap(st, "black", 2)
        run_img.save(a.out / f"{name}_run.png")
        shown = sum(1 for p in run_img.convert("L").resize((96, 54)).getdata() if p > 0)
        ok = shown > 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = {val} ({name}): font words lit {base} -> {lit(st)}, {shown} lit samples of 5184 on screen")
        ddc.set(VCP_SAVER, 0)
        sess.bus.wait(STOP_S)
        st = sess.snap()
        img = R.render_snap(st, "black", 2)
        img.save(a.out / f"{name}_stop.png")
        bright = sum(1 for p in img.convert("L").resize((96, 54)).getdata() if p > 0)
        ok = bright == 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = 0: screen after stop has {bright} lit samples of 5184")
    sess.bus.close()
    fails += rotated_check(a)
    fails += alert_check(a)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
