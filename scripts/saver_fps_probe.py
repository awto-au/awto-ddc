#!/usr/bin/env python3
"""Per-frame work of a saver in the firmware sim (docs/saver-fps-plan.md): frames/s, OSD data port bytes, tile uploads, calls per frame,
and the cost of one call of a burst function (gap between back-to-back calls). Nothing touches hardware.

usage: saver_fps_probe.py BIN --saver scope|scope2|asteroids|pacman [--window S] [--fn NAME ...] [--rotate]
  - Starts the saver by DDC/CI VCP 0xEB, waits SETTLE_S (hidden first frame), then counts over --window s of fw time.
  - Frames = the saver's own "frame complete" sync pushes (as saver_frames_md5.py).
  - Port bytes = calls of ScalerOsdDataPort (every byte goes through it: docs/saver-library.md data port rule).
  - Per --fn: calls per frame; median gap between consecutive calls closer than BURST_US (= cost of one call in a loop of them).
Log: ./tmp/logs/saver_fps_probe.log
"""
import argparse
import collections
import os
import statistics
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402
import saver_frames_md5 as F  # noqa: E402

LOG = R.ROOT / "tmp/logs/saver_fps_probe.log"
SETTLE_S = 3.0                  # fw time after the start: the hidden first frame is drawn (Scope 2, Asteroids ~2 s)
BURST_US = 3000                 # consecutive calls closer than this belong to one loop (a tile upload is ~0.1-0.5 ms)
PORT_FN = "ScalerOsdDataPort"
ROW_DISP_ROTATE = 32


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--saver", choices=sorted(F.SAVERS), required=True)
    ap.add_argument("--window", type=float, default=3.0)
    ap.add_argument("--fn", nargs="*", default=[])
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--no-port", action="store_true", help="do not count port bytes (a stop per byte: slow)")
    a = ap.parse_args()
    vcp, args = F.SAVERS[a.saver]
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    m = sess.bus.m
    ddc = D.Mccs(sess.bus, eng)
    if a.rotate:
        ddc.set(0xE0, ROW_DISP_ROTATE)
        ddc.set(0xE1, 1)
        sess.bus.wait(F.ROTATE_SETTLE_S)
    ddc.set(F.VCP_SAVER, vcp)
    sess.bus.wait(SETTLE_S)
    on = [False]
    frames = []
    calls = collections.defaultdict(list)
    port = [0]

    def sync(mm, r):
        if on[0] and (r["a1"] & 0xFF) == F.SYNC_EV_ODEMO and (r["a2"] & 0xFF) in args:
            frames.append(mm.wall_ms * 1000.0)
        return None

    m.stub("AwtoSyncPush", sync)
    for n in a.fn:
        if "_" + n in m.sym:
            m.stub(n, lambda mm, r, n=n: on[0] and calls[n].append(mm.wall_ms * 1000.0) and None)
        else:
            say(f"{n}: not in the map")
    if not a.no_port:
        m.stub(PORT_FN, lambda mm, r: on[0] and port.__setitem__(0, port[0] + 1))
    t0 = sess.bus.now()
    on[0] = True
    sess.bus.wait(a.window)
    on[0] = False
    span = sess.bus.now() - t0
    nf = max(1, len(frames) - 1)
    fspan = (frames[-1] - frames[0]) / 1e6 if len(frames) >= 2 else span
    say(f"{a.bin.name} {a.saver}{' rotate' if a.rotate else ''}: {len(frames)} frames in {span:.2f} s fw -> {len(frames) / span:.2f} frames/s"
        f"{(f', {1000 * fspan / nf:.1f} ms per frame (first..last)') if len(frames) >= 2 else ''}")
    if not a.no_port:
        say(f"    port bytes: {port[0]} -> {port[0] / max(1, len(frames)):.0f} per frame")
    for n in a.fn:
        t = calls.get(n, [])
        gaps = [t[i] - t[i - 1] for i in range(1, len(t)) if t[i] - t[i - 1] < BURST_US]
        med = f"{statistics.median(gaps):.0f} us per call in bursts ({len(gaps)} gaps)" if gaps else "no bursts"
        say(f"    {n}: {len(t)} calls, {len(t) / max(1, len(frames)):.1f} per frame; {med}")
    sess.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
