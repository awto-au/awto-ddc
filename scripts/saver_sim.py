#!/usr/bin/env python3
"""Screensaver check in the firmware simulator (docs/screensaver.md): DDC/CI VCP 0xEB starts / stops Pac-Man, Scope 2, Asteroids; PNGs of each.

usage: saver_sim.py [BIN MAP] [--out DIR]
  - BIN / MAP default: tmp/fw/AWT26110003-sv1-be.{bin,map} (dev.py build --tree . --serial AWT26110003 --tag sv1; audio is in every build, #229).
  - Steps: boot; VCP 0xEB = 2 (Pac-Man), 4 (scope 2), 5 (flash), 8 (Asteroids): wait, render, then = 0 (stop), render.
    Asteroids is deterministic: its frames are compared at the same game tick (frozen where a frame is complete), not at the same time;
    Retired Scope 1: VCP 0xEB = 3 is ignored, a stored setting 119 = 2 runs Scope 2 (retired_check). PASS = font SRAM written and something on screen when started,
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
RUN_S = 8.0                     # fw time for the draw (Scope 2: tile uploads, ~1.5 s) plus one frame
ROW_DISP_ROTATE = 32            # registry row id of disp_rotate (fw/rtdfw/settings/registry.tsv)
ROTATE_SETTLE_S = 6.0           # fw time for the display re-set after Rotate changes
SHRINK = 8                      # box shrink factor before comparing
ROT_SAMPLES = 4                 # rotated renders (Pac-Man, Scope 2), 0.5 s of fw time apart: the best one counts; Asteroids compares one frame chosen by its number
ROT_SAMPLE_S = 0.5
ROT_MAX_DIFF = 8.0              # mean abs difference allowed between the turned upright render and the rotated render (of 255)
ROT_BETTER = 1.5               # the turned comparison must beat the unturned one by this factor
VCP_ALERT = 6                   # screensaver_now option "Alert tone"
ALERT_TONE_S = 0.9              # audible time: the 1 s track (pacman_sound.py ALERT) has 100 ms of rests between the notes
ALERT_TOL_S = 0.15              # one 10 ms tick per note plus the 1 ms firmware timer: well inside
ALERT_SETTLE_S = 3.0            # fw time after boot before the alert: the SDK's first HDMI audio init (it clears the generator) must have run
AUDIO_STATE_PLAYBACK = 2        # _AUDIO_STATUS_PLAYBACK (Global.h); g_stAudioInfo byte 0 bits 5:4 = b2AudioState
AUDIO_STATE_PLAYBACK_BYTE = AUDIO_STATE_PLAYBACK << 4
HOLD_SLICE_S = 0.005            # re-inject period: below one main-loop pass (< 75 ms), so the state never stays reset
ALERT_OBSERVE_S = 3.0          # fw time to observe: the tone must end by itself
ROW_SCREENSAVER = 119           # registry row id of screensaver
SET_VALUE = {"pacman": 1, "scope2": 3, "asteroids": 5}   # setting 119 values (registry.tsv)
SET_RETIRED = 2                 # its stored value of the retired Scope 1
VCP_RETIRED = 3                 # screensaver_now option of the retired Scope 1
VCP_SELECTED = 1                # screensaver_now option "Selected"
RUN_OFF, RUN_SCOPE2 = 0, 3      # g_ucAwtoSaverRun (fw/awto/savers.tsv)
SAVER_ROWS = (("pacman", 2, 1, "AwtoPacmanClassic"), ("scope2", 4, 3, "AwtoScopeSaver2"), ("asteroids", 8, 7, "AwtoAsteroids"))   # name, VCP 0xEB, run id, entry (fw/awto/savers.tsv)
IN_IMAGE = []                   # names of the savers this image has (build option _AWTO_SAVER_*, docs/saver-mode.md): found by their entry in the map
RETIRED_S = 1.0                 # fw time for the main loop to serve the request (a pass is < 75 ms; Scope 2 starts hidden)
VCP_ASTEROIDS = 8               # screensaver_now option "Asteroids" (7 is kept free)
AST_FREEZE_TICKS = 40           # game tick (g_usAwtoAstStep) whose complete frame is rendered: ~20 frames, ~8 s of fw time after the start
AST_FREEZE_LIMIT_S = 20.0       # 2.5x the expected 8 s (first hidden frame ~3 s + 20 frames at ~0.25 s); expiry = FAIL, logged
AST_POLL_S = 0.0005             # a frame is complete from the column wrap until the next main pass (a few ms)
AST_GREEN = (0, 255, 65)        # diagnostic console text colour (AWTO_RGB_PHOSPHOR_GREEN, palette AWTO_PAL_DIAG_TEXT): every lit pixel of Asteroids
GREEN_TOL = 40                  # R / B channel excess allowed over the diagnostic green (scale-up blends edges with the background)
INK_MIN = 128                   # channel value above which a pixel is ink (the background is ~(2, 2, 6))
AST_INFO_COLS = 9               # info overlay width in tile columns (AWTO_AST_INFO_COLS, lower left), of 30
AST_INFO_ROWS = 2               # its height in tile rows (AWTO_AST_INFO_ROWS), of 11
AST_GRID = (30, 11)             # Asteroids tile grid (AWTO_AST_COLS, AWTO_AST_ROWS)
AST_INFO_MIN_SHARE = 0.03       # lit share of the info box: 3 lines of 4 x 6 glyphs fill 8-15 %, the empty box is 0
AST_FILL = 0.97                 # Asteroids: full width, 97.8 % of the height (24 px bars of 2160: 30 x 11 tiles at 64 / 6)
SCOPE2_FILL = 0.99              # scope 2 must cover this share of the panel picture in each direction (it is one raster scaled to the whole panel)
SCOPE2_MIN_FPS = 5.0            # frames per second of scope 2 (measured 6.7 on the 480 x 270 raster; docs/screensaver.md): a slower draw fails
SCOPE2_FPS_S = 2.0              # fw time the frame counter is watched
SYNC_EV_ODEMO = 0xE9            # AWTO_SYNC_EV_ODEMO: the savers' frame-complete sync lines (as saver_frames_md5.py)
STOP_S = 3.0                    # fw time for the stop: served by the main loop after the frame in progress (scope 2: up to ~2 s)


def image_savers(mp: Path) -> list:
    txt = mp.read_text(errors="replace")
    return [n for n, _, _, sym in SAVER_ROWS if f" _{sym}" in txt or f"CH_{sym} " in txt]


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


def frame_hook(sess):
    """One AwtoSyncPush stub per session (a second stub on the same entry never runs): snapshot at the n-th frame-complete line of the armed saver."""
    h = {"args": (), "count": 0, "n": -1, "snap": None}

    def hook(m, r):
        if (r["a1"] & 0xFF) == SYNC_EV_ODEMO and (r["a2"] & 0xFF) in h["args"]:
            if h["count"] == h["n"]:
                h["snap"] = sess.snap()
            h["count"] += 1
        return None

    sess.bus.m.stub("AwtoSyncPush", hook)
    sess.frame = h


def wait_started(sess, name) -> bool:
    """Wait for a started saver to show its picture; Asteroids: until the complete frame of game tick AST_FREEZE_TICKS is on screen;
    False = limit hit."""
    if name != "asteroids":
        sess.bus.wait(RUN_S)
        return True
    step, col = sess.bus.m.addr("g_usAwtoAstStep"), sess.bus.m.addr("g_ucAwtoAstCol")
    t_end = sess.bus.now() + AST_FREEZE_LIMIT_S
    while sess.bus.now() < t_end:
        sess.bus.wait(AST_POLL_S)
        if int.from_bytes(sess.bus.m.rd(step, 2), "big") == AST_FREEZE_TICKS and sess.bus.m.rd(col, 1)[0] == 0:
            return True
    return False


def lit(st) -> int:
    return sum(1 for w in st.font.values() if any(w))


def rotated_check(a) -> int:
    """Display Rotate 180 (settings row 32 through the paged pair 0xE0 / 0xE1): each saver must draw the same picture turned 180 inside its box."""
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    frame_hook(sess)
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1)
    sess.bus.wait(ROTATE_SETTLE_S)
    fails = 0
    for name, val in ((n, v) for n, v, _, _ in SAVER_ROWS if n in IN_IMAGE):
        up = bbox_crop(Image.open(a.out / f"{name}_run.png"))
        ddc.set(VCP_SAVER, val)
        if not wait_started(sess, name):
            say(f"FAIL Rotate 180 {name}: frame to compare not reached (Asteroids tick {AST_FREEZE_TICKS} in {AST_FREEZE_LIMIT_S} s)")
            fails += 1
            continue
        best = None
        n_samples = 1 if name == "asteroids" else ROT_SAMPLES
        for _ in range(n_samples):
            img = R.render_snap(sess.snap(), "black", 2)
            rot = bbox_crop(img)
            d = (shrunk_diff(np.rot90(up, 2), rot), shrunk_diff(up, rot)) if rot.shape == up.shape else (float("inf"), 0.0)
            if best is None or d[0] < best[0]:
                best = d
                img.save(a.out / f"{name}_run_rot.png")
            sess.bus.wait(ROT_SAMPLE_S)
        d_turned, d_plain = best
        same = d_turned != float("inf") and up.size > 0 and d_turned <= ROT_MAX_DIFF and d_turned * ROT_BETTER <= d_plain
        fails += not same
        say(f"{'PASS' if same else 'FAIL'} Rotate 180 {name}: box {up.shape[:2]}, best of {n_samples} mean difference to the upright render turned {d_turned:.1f} (limit {ROT_MAX_DIFF}), not turned {d_plain:.1f} (turned must be {ROT_BETTER}x smaller)")
        ddc.set(VCP_SAVER, 0)
        sess.bus.wait(STOP_S)
    sess.bus.close()
    return fails


def scope2_check(sess, img) -> int:
    """Scope 2: the picture covers the whole panel (bounding box of the lit pixels) and the frame counter runs at >= SCOPE2_MIN_FPS."""
    box = bbox_crop(img)
    h, w = img.size[1], img.size[0]
    fill_ok = box.shape[0] >= SCOPE2_FILL * h and box.shape[1] >= SCOPE2_FILL * w
    addr = sess.bus.m.addr("g_usAwtoS2Frame")
    rd = lambda: int.from_bytes(sess.bus.m.rd(addr, 2), "big")
    f0, t0 = rd(), sess.bus.now()
    sess.bus.wait(SCOPE2_FPS_S)
    fps = (rd() - f0) / (sess.bus.now() - t0)
    say(f"{'PASS' if fill_ok else 'FAIL'} scope 2 fills the panel: box {box.shape[1]} x {box.shape[0]} of {w} x {h}")
    say(f"{'PASS' if fps >= SCOPE2_MIN_FPS else 'FAIL'} scope 2 speed: {fps:.2f} frames/s (min {SCOPE2_MIN_FPS})")
    return int(not fill_ok) + int(fps < SCOPE2_MIN_FPS)


def asteroids_info_check(img) -> int:
    """Asteroids: all lit pixels are the diagnostic green, and the info overlay (lower left tile box) has text while the mirrored box does not."""
    a = np.asarray(img.convert("RGB"))
    box = bbox_crop(img)
    lit = box[box.max(axis=2) > INK_MIN]
    off = int(np.sum((lit[:, 0] > GREEN_TOL) | (lit[:, 2] > GREEN_TOL + AST_GREEN[2])))
    h, w = box.shape[:2]
    ih, iw = h * AST_INFO_ROWS // AST_GRID[1], w * AST_INFO_COLS // AST_GRID[0]
    share = lambda b: float((b.max(axis=2) > INK_MIN).mean())
    s_info, s_far = share(box[h - ih:, :iw]), share(box[h - ih:, w - iw:])
    ok = off <= 0.02 * len(lit) and s_info >= AST_INFO_MIN_SHARE and s_info > 2 * s_far
    say(f"{'PASS' if ok else 'FAIL'} asteroids info overlay: {len(lit)} lit px, {off} not diagnostic green {AST_GREEN}; lower-left box {100 * s_info:.1f} % lit (min {100 * AST_INFO_MIN_SHARE:.0f} %), lower-right box {100 * s_far:.1f} %")
    return int(not ok)


def saver_run(sess) -> int:
    return sess.bus.m.rd(sess.bus.m.addr("g_ucAwtoSaverRun"), 1)[0]


def retired_check(sess, ddc) -> int:
    """Retired Scope 1 (run 2 / VCP 3 / setting 119 = 2): VCP 0xEB = 3 starts nothing; a stored 119 = 2 with VCP 0xEB = 1 runs Scope 2 (run 3)."""
    fails = 0
    ddc.set(VCP_SAVER, VCP_RETIRED)
    sess.bus.wait(RETIRED_S)
    run = saver_run(sess)
    fails += run != RUN_OFF
    say(f"{'PASS' if run == RUN_OFF else 'FAIL'} VCP 0x{VCP_SAVER:02X} = {VCP_RETIRED} (retired Scope 1): run id {run}, want {RUN_OFF}")
    ddc.set(0xE0, ROW_SCREENSAVER)
    ddc.set(0xE1, SET_RETIRED)
    ddc.set(VCP_SAVER, VCP_SELECTED)
    sess.bus.wait(RETIRED_S)
    run = saver_run(sess)
    want = RUN_SCOPE2 if "scope2" in IN_IMAGE else next(r for n, _, r, _ in SAVER_ROWS if n in IN_IMAGE)    # a saver left out of the image runs the first one that is in
    fails += run != want
    say(f"{'PASS' if run == want else 'FAIL'} setting 119 = {SET_RETIRED} + VCP 0x{VCP_SAVER:02X} = {VCP_SELECTED}: run id {run}, want {want} ({'Scope 2' if want == RUN_SCOPE2 else 'first saver in the image'})")
    ddc.set(VCP_SAVER, 0)
    ddc.set(0xE0, ROW_SCREENSAVER)
    ddc.set(0xE1, 0)
    sess.bus.wait(STOP_S)
    return fails


def absent_check(sess, ddc) -> int:
    """A saver left out of the image: its VCP 0xEB value starts nothing (run id stays off), the stored setting 119 of it runs the first saver that is in."""
    fails = 0
    first = next(r for n, _, r, _ in SAVER_ROWS if n in IN_IMAGE)
    for name, vcp, _, _ in SAVER_ROWS:
        if name in IN_IMAGE:
            continue
        ddc.set(VCP_SAVER, vcp)
        sess.bus.wait(RETIRED_S)
        run = saver_run(sess)
        fails += run != RUN_OFF
        say(f"{'PASS' if run == RUN_OFF else 'FAIL'} VCP 0x{VCP_SAVER:02X} = {vcp} ({name}, not in the image): run id {run}, want {RUN_OFF}")
        ddc.set(0xE0, ROW_SCREENSAVER)
        ddc.set(0xE1, next(m for n, m in SET_VALUE.items() if n == name))
        ddc.set(VCP_SAVER, VCP_SELECTED)
        sess.bus.wait(RETIRED_S)
        run = saver_run(sess)
        fails += run != first
        say(f"{'PASS' if run == first else 'FAIL'} setting 119 = {SET_VALUE[name]} ({name}, not in the image) + VCP 0x{VCP_SAVER:02X} = {VCP_SELECTED}: run id {run}, want {first} (first saver in the image)")
        ddc.set(VCP_SAVER, 0)
        ddc.set(0xE0, ROW_SCREENSAVER)
        ddc.set(0xE1, 0)
        sess.bus.wait(STOP_S)
    return fails


def alert_check(a, stream: bool = False) -> int:
    """VCP 0xEB = 6 plays the 1 s alert tone: the audio tap hears ~1 s of tone, and the generator is off afterwards.
    Amp model: P7.4 must be driven by the firmware (no assume_amp_en). stream: SysAudio state held at PLAYBACK (a PC host's HDMI audio, Dan 2026-11-19: the tone was skipped)."""
    eng = D.DdcEngine()
    tap = A.AudioTap(lambda: sess.bus.now() if tap.armed else 0.0)
    tap.armed = False
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng, tap])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    sess.bus.wait(ALERT_SETTLE_S)
    tap.armed = True
    t0 = sess.bus.now()
    st = sess.bus.m.addr("g_stAudioInfo")

    def hold():
        sess.bus.m.put(f"set memory xram 0x{st:x} 0x{AUDIO_STATE_PLAYBACK_BYTE:x}")
        sess.bus.m.flush()

    if stream:
        hold()
    ddc.set(VCP_SAVER, VCP_ALERT)
    for _ in range(int(ALERT_OBSERVE_S / HOLD_SLICE_S)):    # SysAudioHandler resets PLAYBACK without a real stream: a host stream re-asserts it
        if stream:
            hold()
        sess.bus.wait(HOLD_SLICE_S)
    info = A.write_wav(a.out / ("alert_stream.wav" if stream else "alert.wav"), tap.events, t0, sess.bus.now(), model={"assume_amp_en": False})
    ok = abs(info["tone_s"] - ALERT_TONE_S) <= ALERT_TOL_S
    order = A.order_violations(tap.events)          # pop-free order (#249): amp / mute / generator / DVC sequence
    for v in order:
        say(f"FAIL alert amp order: {v}")
    ok = ok and not order
    say(f"{'PASS' if ok else 'FAIL'} VCP 0xEB = {VCP_ALERT} (alert{', host stream state PLAYBACK' if stream else ''}): tone {info['tone_s']:.2f} s, amp driven by the firmware (expect {ALERT_TONE_S} +- {ALERT_TOL_S})")
    sess.bus.close()
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?", default=ROOT / "tmp/fw/AWT26110003-sv1-be.bin")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/saver_sim")
    ap.add_argument("--only-alert", action="store_true", help="just the alert tone + amp order check (the stream case is the same code path)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.only_alert:
        return alert_check(a)
    IN_IMAGE[:] = image_savers(a.map or a.bin.with_suffix(".map"))
    say(f"savers in the image: {IN_IMAGE}")
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    frame_hook(sess)
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)                  # the registry default is Rotate 180: the upright renders need Rotate 0
    ddc.set(0xE1, 0)
    sess.bus.wait(ROTATE_SETTLE_S)
    fails = 0
    for name, val in [x for x in (("pacman", 2), ("scope2", 4), ("flash", 5), ("asteroids", VCP_ASTEROIDS)) if x[0] in IN_IMAGE or x[0] == "flash"]:
        base = lit(sess.snap())
        ddc.set(VCP_SAVER, val)
        if not wait_started(sess, name):
            say(f"FAIL VCP 0x{VCP_SAVER:02X} = {val} ({name}): frame to compare not reached (Asteroids tick {AST_FREEZE_TICKS} in {AST_FREEZE_LIMIT_S} s)")
            fails += 1
        st = sess.snap()
        run_img = R.render_snap(st, "black", 2)
        run_img.save(a.out / f"{name}_run.png")
        shown = sum(1 for p in run_img.convert("L").resize((96, 54)).getdata() if p > 0)
        ok = shown > 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = {val} ({name}): font words lit {base} -> {lit(st)}, {shown} lit samples of 5184 on screen")
        if name == "scope2":
            fails += scope2_check(sess, run_img)
        if name == "asteroids":
            box = bbox_crop(run_img)
            ok = box.shape[0] >= AST_FILL * run_img.size[1] and box.shape[1] >= AST_FILL * run_img.size[0]
            fails += not ok
            say(f"{'PASS' if ok else 'FAIL'} asteroids fills the panel: box {box.shape[1]} x {box.shape[0]} of {run_img.size[0]} x {run_img.size[1]} ({100 * box.shape[1] / run_img.size[0]:.1f} % x {100 * box.shape[0] / run_img.size[1]:.1f} %, min {100 * AST_FILL:.0f} %)")
        if name == "asteroids":
            fails += asteroids_info_check(run_img)
        ddc.set(VCP_SAVER, 0)
        sess.bus.wait(STOP_S)
        st = sess.snap()
        img = R.render_snap(st, "black", 2)
        img.save(a.out / f"{name}_stop.png")
        bright = sum(1 for p in img.convert("L").resize((96, 54)).getdata() if p > 0)
        ok = bright == 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} VCP 0x{VCP_SAVER:02X} = 0: screen after stop has {bright} lit samples of 5184")
    fails += retired_check(sess, ddc)
    fails += absent_check(sess, ddc)
    sess.bus.close()
    fails += rotated_check(a)
    fails += alert_check(a)
    fails += alert_check(a, stream=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
