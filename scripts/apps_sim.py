#!/usr/bin/env python3
"""Extra-app hooks in the firmware simulator (docs/extra-apps.md): start / stop by VCP 0xEB and by the debug byte, step and key forward.

usage: apps_sim.py BIN MAP [--app NAME]
  BIN: image built with ./dev.py build --extra-fw fw/apps/example (app `hello`; counters g_usHelloSteps / g_ucHelloKeys / g_ucHelloState)
  Checks: nothing runs before the start; VCP 0xEB = 0x20 starts the app and its step runs once per pass; a front key reaches the key hook
  and not the menu; MENU (the app's quit key) stops it; VCP 0 stops it and the steps end; the debug byte g_ucAwtoAppReq starts / stops;
  a VCP value past the table is dropped (no saver starts).
Exit 1 on a failed check. Log: ./tmp/logs/apps_sim.log
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/apps_sim.log"
VCP_SAVER = 0xEB                    # fw/apps/AwtoApps.h: screensaver_now row, values AWTO_APPS_VCP_BASE + index start an app
VCP_BASE = 0x20                     # AWTO_APPS_VCP_BASE
REQ_STOP = 0xFF                     # AWTO_APPS_REQ_STOP
STATE_RUN, STATE_STOPPED = 1, 2     # hello_app.c HELLO_STATE_*
SETTLE_S = 0.3                      # fw time for a main pass to serve a request (a pass is ~4 ms; limit = ~75 passes)
RUN_S = 0.3                         # fw time the app runs between two step readings (>= 1 pass)


def say(s):
    _log_line(s, LOG)


def check(ok, what, detail=""):
    say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
    return 0 if ok else 1


def index_of(binp: Path, name: str) -> int:
    """App index from the apps table beside the image (<stem>.apps.tsv: index, name, source)."""
    tsv = binp.with_name(binp.stem + ".apps.tsv")
    for ln in tsv.read_text().splitlines() if tsv.is_file() else []:
        f = ln.split("\t")
        if len(f) >= 2 and f[1] == name:
            return int(f[0])
    return 0


class Probe:
    def __init__(self, sess):
        self.m = sess.bus.m
        self.sess = sess
        self.sym = {n: self.m.addr(n) for n in ("g_ucAwtoAppRun", "g_ucAwtoAppReq", "g_usHelloSteps", "g_ucHelloState", "g_ucHelloKeys",
                                                 "g_ucAwtoSaverRun")}

    def byte(self, name):
        return self.m.rd(self.sym[name])[0]

    def word(self, name):
        b = self.m.rd(self.sym[name], 2)
        return (b[0] << 8) | b[1]                     # big-endian image


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--app", default="hello")
    a = ap.parse_args()
    idx = index_of(a.bin, a.app)
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map, "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    p = Probe(sess)
    fails = 0
    wait = sess.bus.wait

    fails += check(p.byte("g_ucAwtoAppRun") == 0 and p.word("g_usHelloSteps") == 0, "nothing runs before the start")
    ddc.set(VCP_SAVER, VCP_BASE + idx)
    wait(SETTLE_S)
    s1 = p.word("g_usHelloSteps")
    wait(RUN_S)
    s2 = p.word("g_usHelloSteps")
    fails += check(p.byte("g_ucAwtoAppRun") == idx + 1 and p.byte("g_ucHelloState") == STATE_RUN, "VCP 0xEB = 0x20 starts the app",
                   f"run {p.byte('g_ucAwtoAppRun')} state {p.byte('g_ucHelloState')}")
    fails += check(s1 > 0 and s2 > s1, "step runs every pass", f"steps {s1} -> {s2} in {RUN_S} s")
    sess.act("right")                                  # test cmd key inject: UP key (osd_test KEYS right)
    wait(SETTLE_S)
    fails += check(p.byte("g_ucHelloKeys") > 0 and p.byte("g_ucAwtoAppRun") == idx + 1, "a front key reaches the key hook", f"keys {p.byte('g_ucHelloKeys')}")
    sess.act("exit")                                   # MENU key
    wait(SETTLE_S)
    fails += check(p.byte("g_ucAwtoAppRun") == 0 and p.byte("g_ucHelloState") == STATE_STOPPED, "the app's quit key stops it (stop hook ran)")
    ddc.set(VCP_SAVER, VCP_BASE + idx)
    wait(SETTLE_S)
    ddc.set(VCP_SAVER, 0)
    wait(SETTLE_S)
    s3 = p.word("g_usHelloSteps")
    wait(RUN_S)
    fails += check(p.byte("g_ucAwtoAppRun") == 0 and p.word("g_usHelloSteps") == s3, "VCP 0xEB = 0 stops it and the steps end")
    sess.bus.m.wr(p.sym["g_ucAwtoAppReq"], bytes([idx + 1]))
    wait(SETTLE_S)
    on = p.byte("g_ucAwtoAppRun") == idx + 1
    sess.bus.m.wr(p.sym["g_ucAwtoAppReq"], bytes([REQ_STOP]))
    wait(SETTLE_S)
    fails += check(on and p.byte("g_ucAwtoAppRun") == 0, "the debug byte starts and stops it")
    ddc.set(VCP_SAVER, VCP_BASE + 0x0F)
    wait(SETTLE_S)
    fails += check(p.byte("g_ucAwtoAppRun") == 0 and p.byte("g_ucAwtoSaverRun") == 0, "a value past the table is dropped, no saver starts")
    say("PASS apps_sim" if not fails else f"FAIL apps_sim: {fails} check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
