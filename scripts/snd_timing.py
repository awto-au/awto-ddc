#!/usr/bin/env python3
"""Sound timing of a saver in the firmware sim (audio build): pitch change spacing, amp gate length, audible share. Docs: docs/pacman-sound.md "Timing".

usage: snd_timing.py BIN [MAP] [--saver asteroids|pacman] [--seconds S] [--max-gate-ms N] [--max-note-err-ms N]
  - Tap = scripts/audio_sim.py: every pitch latch (CMCR.dbdcb) is a note start; the amp mute pin is the gate.
  - Gate = note start to the amp opening (designed AWTO_PS_GAP_MS 4 ms, rests excluded). Redundant latch = same pitch as the one before.
  - Poll gap = time between AwtoPmSoundPoll calls: the bound on a note's start error. Exit 1 when the longest gate exceeds --max-gate-ms or the 99th percentile poll gap exceeds --max-poll-ms.
Log: ./tmp/logs/snd_timing.log
"""
import argparse
import os
import statistics
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import itertools

import audio_sim as A
import ddc_sim as D
import osd_render as R
from _log import log_line as _log_line

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/snd_timing.log"
VCP_SAVER = 0xEB
SAVERS = {"asteroids": 8, "pacman": 2}
SETTLE_S = 2.0                  # fw time for the saver to start and the first sounds
DEFAULT_GATE_MAX_MS = 8.5       # designed gate 4 ms (AWTO_PS_GAP_MS) + the longest unpolled stretch (one long osd_line, ~4 ms; an NV write is 20 ms, rare)
POLL_P99_MS = {"asteroids": 3.0, "pacman": 6.0}   # note start error bound: Asteroids polls between drawing steps (measured p99 2 ms); Pac-Man once per 4.4 ms sub-step (unchanged design)
MS = 1000.0


def say(s: str) -> None:
    _log_line(s, LOG)


def analyse(events, t0: float, t1: float):
    """-> dict of note spacing / gate statistics from tap events in [t0, t1)."""
    starts, gates, redundant = [], [], 0
    sc, last_sc, mute, pending = 0, None, 1, None
    for t, kind, a, v in sorted(events, key=lambda e: e[0]):
        if not t0 <= t < t1:
            continue
        if kind == "pin" and a == "amp_mute":
            if v == 0 and mute == 1 and pending is not None:
                gates.append((t - pending) * MS)
                pending = None
            mute = v
        elif kind == "reg" and a == A.IDX_SCAPR:
            sc = v & A.SCAPR_SC_MASK
        elif kind == "reg" and a == A.IDX_CMCR and v & A.CMCR_DBDCB:
            starts.append(t)
            redundant += 1 if sc == last_sc else 0
            last_sc = sc
            pending = t
    gaps = [(b - a) * MS for a, b in itertools.pairwise(starts)]
    return {"notes": len(starts), "per_s": len(starts) / (t1 - t0), "gaps": gaps, "gates": gates, "redundant": redundant}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--saver", choices=sorted(SAVERS), default="asteroids")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--max-gate-ms", type=float, default=DEFAULT_GATE_MAX_MS)
    ap.add_argument("--max-poll-ms", type=float, default=None)
    a = ap.parse_args()
    eng = D.DdcEngine()
    tap = A.AudioTap(lambda: sess.bus.now() if tap.armed else 0.0)
    tap.armed = False
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng, tap])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    tap.armed = True
    polls = []
    sess.bus.m.stub("AwtoPmSoundPoll", lambda mm, r: polls.append(sess.bus.now()) and None)
    ddc.set(VCP_SAVER, SAVERS[a.saver])
    sess.bus.wait(SETTLE_S)
    t0 = sess.bus.now()
    sess.bus.wait(a.seconds)
    t1 = sess.bus.now()
    ddc.set(VCP_SAVER, 0)
    r = analyse(tap.events, t0, t1)
    sess.bus.close()
    g, n = r["gates"], r["gaps"]
    if not g or not n:
        say(f"{a.bin.name} {a.saver}: no notes in {a.seconds} s (not an audio build?)")
        return 1
    say(f"{a.bin.name} {a.saver} {a.seconds:.0f} s: {r['notes']} pitch latches ({r['per_s']:.1f} / s), redundant (same pitch again) {r['redundant']}")
    say(f"  latch spacing ms: min {min(n):.1f} median {statistics.median(n):.1f} p95 {sorted(n)[int(len(n) * 0.95)]:.1f} max {max(n):.1f}")
    say(f"  gate (latch -> amp open) ms: min {min(g):.1f} median {statistics.median(g):.1f} p95 {sorted(g)[int(len(g) * 0.95)]:.1f} max {max(g):.1f}; designed 4")
    pg = sorted((y - x) * MS for x, y in itertools.pairwise(polls) if t0 <= x < t1)
    p99 = pg[int(len(pg) * 0.99)]
    say(f"  poll gap ms: median {statistics.median(pg):.2f} p99 {p99:.2f} max {pg[-1]:.1f} ({len(pg)} polls)")
    lim = a.max_poll_ms if a.max_poll_ms is not None else POLL_P99_MS[a.saver]
    ok = max(g) <= a.max_gate_ms and p99 <= lim
    say(f"  {'PASS' if ok else 'FAIL'}: longest gate {max(g):.1f} ms vs {a.max_gate_ms:.1f}, poll gap p99 {p99:.2f} ms vs {lim:.1f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
