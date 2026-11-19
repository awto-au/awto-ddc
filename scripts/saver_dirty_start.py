#!/usr/bin/env python3
"""Every saver started on top of another one (no stop in between, stale OSD SRAM) must draw the same frames as from a clean start. Sim only.

usage: saver_dirty_start.py BIN [MAP] [--frames N] [--rotate] [--targets NAME ...]
  Per target saver T and prior saver P: boot, VCP 0xEB = P, run, VCP 0xEB = T (no 0 in between), hash the renders of the first N frames of T
  (the saver's own "frame complete" sync line); a clean start (nothing before) is the reference. Frame content depends on the frame number only.
  Priors: every saver, T itself included. Exit 1 on a difference. Log: ./tmp/logs/saver_dirty_start.log
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402

LOG = R.ROOT / "tmp/logs/saver_dirty_start.log"
SYNC_EV_ODEMO = 0xE9
SAVERS = {"pacman": (2, (0x74,)), "scope2": (4, (0x7B, 0x7C)), "asteroids": (8, (0x90, 0x91))}
ROW_DISP_ROTATE = 32
SETTLE_S = 6.0
PRIOR_RUN_S = 4.0               # fw time the prior saver runs (Scope 2 frame ~1.5 s)
CHUNK_S = 0.25
LIMIT_S = 60.0                  # per target: expiry = FAIL logged


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def frames(a, prior, target, n, rotate):
    vcp, args = SAVERS[target]
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1 if rotate else 0)
    sess.bus.wait(SETTLE_S)
    if prior:
        ddc.set(0xEB, SAVERS[prior][0])
        sess.bus.wait(PRIOR_RUN_S)
    rows, live = [], [False]

    def hook(m, r):
        if live[0] and (r["a1"] & 0xFF) == SYNC_EV_ODEMO and (r["a2"] & 0xFF) in args and len(rows) < n:
            rows.append(hashlib.md5(R.render_snap(sess.snap(), "black", 4).tobytes()).hexdigest())
        return None

    sess.bus.m.stub("AwtoSyncPush", hook)
    live[0] = True
    ddc.set(0xEB, vcp)
    t0 = sess.bus.now()
    while len(rows) < n and sess.bus.now() - t0 < LIMIT_S:
        sess.bus.wait(CHUNK_S)
    sess.bus.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--targets", nargs="*", default=list(SAVERS))
    a = ap.parse_args()
    fails = 0
    for t in a.targets:
        ref = frames(a, None, t, a.frames, a.rotate)
        for p in SAVERS:
            got = frames(a, p, t, a.frames, a.rotate)
            ok = len(ref) == a.frames and got == ref
            fails += not ok
            say(f"{'PASS' if ok else 'FAIL'} {p} -> {t}: {len(got)}/{a.frames} frames, {sum(x == y for x, y in zip(got, ref))} equal to the clean start")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
