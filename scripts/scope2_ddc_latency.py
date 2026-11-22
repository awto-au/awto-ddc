#!/usr/bin/env python3
"""DDC/CI Get-VCP reply latency and the longest main-loop pass (= longest gap between watchdog-feeding passes) while Scope 2 runs, in the sim.

usage: scope2_ddc_latency.py BIN [--n N]
  Starts Scope 2 (VCP 0xEB = 4); N Get VCP 0x10 requests at staggered phases; latency = request injected -> complete reply in the engine FIFO.
  Pass gap = time between heartbeat changes (one per main-loop pass; the pass pokes the watchdog) over 3 s.
Log: ./tmp/logs/scope2_ddc_latency.log
"""
import argparse
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import osd_render as R

LOG = R.ROOT / "tmp/logs/scope2_ddc_latency.log"
HB = 0xF6D0 + 0x14              # diag block heartbeat (scripts/fw_profile.py)
POLL_S = 0.0005                 # 0.5 ms resolution
REPLY_LIMIT_S = 0.3             # a reply later than this counts as lost (the host retries)
STAGGER_S = 0.0137              # phase step between requests (prime-ish vs the 3 ms pass and 8 ms band)
GAP_WINDOW_S = 3.0


def say(s):
    _log_line(s, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    ddc.set(0xE0, 32)
    ddc.set(0xE1, 0)
    sess.bus.wait(6.0)
    ddc.set(0xEB, 4)
    sess.bus.wait(3.0)
    pkt = bytes([0x51, 0x82, 0x01, 0x10])
    chk = 0x6E
    for b in pkt:
        chk ^= b
    pkt += bytes([chk])
    lat, lost = [], 0
    for k in range(a.n):
        sess.bus.wait(STAGGER_S * (1 + k % 7))
        eng.request(sess.bus.m, pkt)
        t0 = sess.bus.now()
        while len(eng.tx) < 11 and sess.bus.now() - t0 < REPLY_LIMIT_S:
            sess.bus.wait(POLL_S)
        if len(eng.tx) < 11:
            lost += 1
        else:
            lat.append((sess.bus.now() - t0) * 1000.0)
    rd = lambda: int.from_bytes(sess.bus.m.rd(HB, 2), "big")
    gaps, last, t_last, t_end = [], rd(), sess.bus.now(), sess.bus.now() + GAP_WINDOW_S
    while sess.bus.now() < t_end:
        sess.bus.wait(POLL_S)
        if rd() != last:
            now = sess.bus.now()
            gaps.append((now - t_last) * 1000.0)
            last, t_last = rd(), now
    sess.bus.close()
    lat.sort()
    say(f"{a.bin.name}: DDC/CI Get VCP latency over {len(lat)} replies ({lost} lost): mean {sum(lat) / len(lat):.1f} ms, median {lat[len(lat) // 2]:.1f}, max {lat[-1]:.1f}; "
        f"main-loop pass gap over {len(gaps)} passes: mean {sum(gaps) / len(gaps):.1f} ms, max {max(gaps):.1f} ms (watchdog period 586 ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
