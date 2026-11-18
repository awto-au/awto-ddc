#!/usr/bin/env python3
"""Boot splash check in the firmware simulator (docs/flash-screen.md "Boot splash"; registry row 122 boot_splash).

usage: splash_sim.py BIN MAP [--base BIN MAP] [--out DIR]
  - boot: splash starts at the first main pass (g_ucAwtoSaverRun = splash, Why = boot), is gone by the console; reports ACTIVE and first-OSD ms;
    --base = the same image without the splash: ACTIVE / console times must be equal (+- TIME_TOL_MS).
  - key: a front key during the splash ends it (run = off at once).
  - off: boot_splash = 0 -> no splash start line.
  - frames: VCP 0xEB = 7 (preview) rendered upright and Rotate 180 (PNG), turned = upright turned; title must differ from the flash screen's.
Log: ./tmp/logs/splash_sim.log
"""
import argparse
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import boot_sim as B  # noqa: E402
import ddc_sim as D  # noqa: E402
import key_sim_test as K  # noqa: E402
import osd_render as R  # noqa: E402
import saver_sim as V  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/splash_sim.log"
SET_ID_BOOT_SPLASH = 122        # registry id boot_splash
RUN_SPLASH, WHY_BOOT = 6, 4     # fw/test/saver.c AWTO_SAVER_SPLASH / AWTO_SAVER_WHY_BOOT
TIME_TOL_MS = 2                 # one main pass (~4 ms) is the resolution of a ring time; the splash must not move ACTIVE / console by more
KEY_AT_MS = 150                 # fw ms: the splash is running (the key is polled once the main loop passes again, ~0.4 s after the first pass)
VCP_PREVIEW = 7                 # screensaver_now option "Boot splash"
TURN_TOL_PX = 40                # the turned render sits 24 px higher than the mirror (sim display offset)
FRAME_S = 8.0                   # fw time for the flash drawing (as saver_sim RUN_S)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def ns(a, bin_, map_, splash=True):
    return SimpleNamespace(bin=bin_, map=map_, mode="1080p60", console="until", out=a.out)


def run_boot(a, bin_, map_, splash=True, key_at=None):
    """Boot to ACTIVE + 300 ms; returns times and the splash span (fw ms) from g_ucAwtoSaverRun / Why."""
    r = B.Run(ns(a, bin_, map_))
    if not splash:
        r.m.stub("set_get", lambda m_, q: {"val": 0} if (q["a1"] & 0xFF) == SET_ID_BOOT_SPLASH else None)
    run, why = r.m.addr("g_ucAwtoSaverRun"), r.m.addr("g_ucAwtoSaverWhy")
    first_osd = start = end = key_t = None
    active = None
    used = 0
    while used < B.BUDGET_INSTR:
        r.m.run(B.STEP)
        used += B.STEP
        t, st = r.ms(), r.state()
        on = r.m.rd(run)[0] == RUN_SPLASH and r.m.rd(why)[0] == WHY_BOOT
        if on and start is None:
            start = t
        if start is not None and not on and end is None:
            end = t
        if first_osd is None and st[4]:
            first_osd = t
        if key_at is not None and key_t is None and on and t >= key_at:
            key_t = t
            r.m.wr(K.A0, bytes([K.KEY_ADC["UP"][1]]))
        if key_t is not None and end is not None:
            break
        if st[0] == 3 and active is None:
            active = t
        if active is not None and t >= active + B.AFTER_MS:
            break
    h, lines = r.episode()
    txt = "\n".join(lines)
    ring = {"start": any("boot splash:run << 4 | why = 100" in ln for ln in lines), "end": any("boot splash:run << 4 | why = 0, 0 = ended" in ln for ln in lines)}
    ms = lambda key: next((int(ln.split(":", 1)[0]) for ln in lines if key in ln), None)  # noqa: E731
    out = dict(r=r, start=start, end=end, key_t=key_t, first_osd=first_osd, ring=ring, txt=txt,
               active=ms("->ACTIVE:"), console=ms("console opened"))
    return out


def check(ok, what, detail=""):
    say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
    return 0 if ok else 1


def centroid(m):
    ys, xs = np.nonzero(m)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (-1e9, -1e9)


def frames(a):
    """The flash screen drawn with the splash title: upright (Rotate 0) and Rotate 180 (registry default)."""
    fails = 0
    imgs = {}
    for name, rot in (("up", 0), ("rot", 1)):
        eng = D.DdcEngine()
        sess = R.Session(a.bin, a.map, "1080p60", devs=[eng])
        sess.boot()
        ddc = D.Mccs(sess.bus, eng)
        ddc.set(0xE0, V.ROW_DISP_ROTATE)
        ddc.set(0xE1, rot)
        sess.bus.wait(V.ROTATE_SETTLE_S)
        ddc.set(V.VCP_SAVER, VCP_PREVIEW)
        sess.bus.wait(FRAME_S)
        img = R.render_snap(sess.snap(), "black", 2)
        img.save(a.out / f"splash_{name}.png")
        imgs[name] = np.asarray(img.convert("RGB"))
        say(f"  png {a.out / f'splash_{name}.png'}")
        sess.bus.close()
    for what, mask in (("Pac-Man", lambda x: (x[..., 0] > 200) & (x[..., 1] > 180) & (x[..., 2] < 80)), ("title", lambda x: x.min(axis=2) > 200)):
        pu, pr = centroid(mask(imgs["up"])), centroid(mask(imgs["rot"]))
        want = (imgs["up"].shape[1] - pu[0], imgs["up"].shape[0] - pu[1])
        err = max(abs(pr[0] - want[0]), abs(pr[1] - want[1]))
        fails += check(err <= TURN_TOL_PX, f"Rotate 180: {what} centre mirrored", f"upright {pu}, turned {pr}, expected {want}, off {err:.0f} px")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--base", type=Path, nargs=2, metavar=("BIN", "MAP"))
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/splash_sim")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    fails = 0
    say(f"splash_sim {a.bin.name}")
    n = run_boot(a, a.bin, a.map)
    say(f"  splash on {n['start']} -> {n['end']} ms (fw), first OSD {n['first_osd']} ms, ACTIVE {n['active']} ms, console {n['console']} ms")
    fails += check(n["start"] is not None and n["ring"]["start"], "splash starts at power-on (run = splash, why = boot, ring line boot splash started)", f"{n['start']}")
    fails += check(n["end"] is not None and n["ring"]["end"], "splash ends before the console / after ACTIVE (ring line boot splash ended)", f"{n['end']}")
    fails += check(n["console"] is not None and n["txt"].count("console opened") == 1, "console opens once, over / after the splash", f"{n['console']}")
    if a.base:
        b = run_boot(a, *a.base)
        say(f"  base: first OSD {b['first_osd']} ms, ACTIVE {b['active']} ms, console {b['console']} ms (splash start {b['start']})")
        fails += check(b["start"] is None, "base image has no splash")
        fails += check(abs(n["active"] - b["active"]) <= TIME_TOL_MS, "ACTIVE not delayed", f"{n['active']} vs {b['active']} ms")
        fails += check(abs(n["console"] - b["console"]) <= TIME_TOL_MS, "console not delayed", f"{n['console']} vs {b['console']} ms")
        if n["first_osd"] is not None and b["first_osd"] is not None:
            say(f"  first OSD: {n['first_osd']} ms with the splash, {b['first_osd']} ms without")
    k = run_boot(a, a.bin, a.map, key_at=KEY_AT_MS)
    fails += check(k["key_t"] is not None and k["end"] is not None and k["end"] < n["active"], "a key ends the splash before the picture",
                   f"key at {k['key_t']}, end {k['end']}, ACTIVE {n['active']}")
    o = run_boot(a, a.bin, a.map, splash=False)
    fails += check(o["start"] is None and not o["ring"]["start"], "boot_splash = 0: no splash", f"start {o['start']}")
    fails += frames(a)
    say("FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
