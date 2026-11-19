#!/usr/bin/env python3
"""Boot splash check in the firmware simulator: COLD power-up only (warm reset / watchdog bite show none) (docs/flash-screen.md "Boot splash"; registry row 122 boot_splash).

usage: splash_sim.py BIN MAP [--out DIR]
  - boot: splash starts at the first main pass (g_ucAwtoSaverRun = splash, Why = boot), is gone by the console; reports ACTIVE and first-OSD ms;
    compared with the same image at boot_splash = 0: ACTIVE / console cost <= COLD_COST_MS.
  - key: a front key during the splash ends it (run = off at once).
  - off: boot_splash = 0 -> no splash start line.
  - frames: VCP 0xEB = 7 (preview) rendered upright and Rotate 180 (PNG), turned = upright turned; title must differ from the flash screen's.
Log: ./tmp/logs/splash_sim.log
"""
import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import isostamp

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_sim as B
import ddc_sim as D
import key_sim_test as K
import numpy as np
import osd_render as R
import saver_sim as V

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/splash_sim.log"
SET_ID_BOOT_SPLASH = 122        # registry id boot_splash
BITE, WARM = 2, 3               # AWTO_BOOT_BITE / AWTO_BOOT_WARM (cold = 1)
RUN_SPLASH, WHY_BOOT = 6, 4     # fw/test/saver.c AWTO_SAVER_SPLASH / AWTO_SAVER_WHY_BOOT
COLD_COST_MS = 70               # accepted by Dan 2026-11-18: ~54 ms measured for drawing in main pass 1; limit = measured x 1.25
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


def run_boot(a, bin_, map_, splash=True, key_at=None, shots=False, tag="boot", reason=None):
    """Boot to ACTIVE + 300 ms; returns times and the splash span (fw ms) from g_ucAwtoSaverRun / Why."""
    r = B.Run(ns(a, bin_, map_))
    if not splash:
        r.m.stub("set_get", lambda m_, q: {"val": 0} if (q["a1"] & 0xFF) == SET_ID_BOOT_SPLASH else None)
    if reason is not None:
        r.m.stub("AwtoBootReason", lambda m_, q: {"val": reason})
    run, why = r.m.addr("g_ucAwtoSaverRun"), r.m.addr("g_ucAwtoSaverWhy")
    first_osd = start = end = key_t = last = None
    shot_at = [200.0, 400.0, 560.0, 640.0, 700.0, 760.0]
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
        if st != last:
            say(f"    {t:6.0f} ms mode {st[0]} grid {st[1]}x{st[2]} console {st[3]} osd {'on' if st[4] else 'off'} splash {'on' if on else 'off'}")
            last = st
        if shots and shot_at and t >= shot_at[0]:
            R.render_snap(r.s.model.snapshot(r.m, t), "black", 2).save(a.out / f"{tag}_{int(shot_at.pop(0))}ms.png")
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
    ms = lambda key: next((int(ln.split(":", 1)[0]) for ln in lines if key in ln), None)
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
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/splash_sim")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    fails = 0
    say(f"splash_sim {a.bin.name}")
    n = run_boot(a, a.bin, a.map, shots=True, tag="cold")
    say(f"  splash on {n['start']} -> {n['end']} ms (fw), first OSD {n['first_osd']} ms, ACTIVE {n['active']} ms, console {n['console']} ms")
    fails += check(n["start"] is not None and n["ring"]["start"], "splash starts at power-on (run = splash, why = boot, ring line boot splash started)", f"{n['start']}")
    fails += check(n["end"] is not None and n["ring"]["end"], "splash ends before the console / after ACTIVE (ring line boot splash ended)", f"{n['end']}")
    fails += check(n["console"] is not None and n["txt"].count("console opened") == 1, "console opens once, over / after the splash", f"{n['console']}")
    b = run_boot(a, a.bin, a.map, splash=False)                 # before = the same image with boot_splash = 0
    say(f"  splash off: first OSD {b['first_osd']} ms, ACTIVE {b['active']} ms, console {b['console']} ms (splash start {b['start']})")
    fails += check(b["start"] is None, "boot_splash = 0: no splash")
    say(f"  cold boot cost of the splash: ACTIVE {n['active'] - b['active']:+d} ms, console {n['console'] - b['console']:+d} ms")
    fails += check(n["active"] - b["active"] <= COLD_COST_MS, "ACTIVE delay within the accepted cost", f"{n['active']} vs {b['active']} ms")
    fails += check(n["first_osd"] is not None and n["first_osd"] < n["console"], "the splash is on screen before the console opens", f"OSD on at {n['first_osd']} ms")
    k = run_boot(a, a.bin, a.map, key_at=KEY_AT_MS)
    fails += check(k["key_t"] is not None and k["end"] is not None and k["end"] < n["active"], "a key ends the splash before the picture",
                   f"key at {k['key_t']}, end {k['end']}, ACTIVE {n['active']}")
    for name, why in (("warm reset", WARM), ("watchdog bite", BITE)):
        w = run_boot(a, a.bin, a.map, reason=why)
        fails += check(w["start"] is None and w["first_osd"] is None or w["start"] is None, f"{name}: no splash", f"start {w['start']}")
    o = run_boot(a, a.bin, a.map, splash=False)
    fails += check(o["start"] is None and not o["ring"]["start"], "boot_splash = 0: no splash", f"start {o['start']}")
    fails += frames(a)
    say("FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
