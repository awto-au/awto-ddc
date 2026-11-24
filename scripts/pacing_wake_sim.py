#!/usr/bin/env python3
"""Loop pacing after a wake (awto-ddc#313 observation): does the busy hook (AwtoLoopBusy) stay on after a fast wake?

usage: AWTO_SIM_CORE=fast pacing_wake_sim.py BIN MAP [--case fast|slow|boot|all] [--after 30] [--mode 1080p60]
- Boots to ACTIVE, 6 s idle (the boot console closes), then per case:
  fast = signal lost 1.5 s (L1 hold) and back (fast wake), slow = lost past L2 (SDK search path) and back, boot = no event.
- Samples the 1 s headroom window (g_stAwtoHead) every second for --after s of firmware time after the picture is back.
- FAIL: the busy hook is on in more than HEAD_HOLD_MAX_PM per mille of passes in the last 1 s window, 12 s after the picture
  (unit_health's own limit; 12 s = 4 health windows + the 6 s info pop-up). Log: tmp/logs/pacing_wake_sim.log
"""

import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sysm_sim as Y
import unit_health as H
from _repo import ROOT

LOG = ROOT / "tmp/logs/pacing_wake_sim.log"
IDLE_S = 6.0  # boot console closes 3 s after the picture
CHECK_AFTER_S = 12  # the hook must be off by then
L2_EXTRA_S = (
    2.0  # slow case: past usL2Sec (60 s default, test cmd 0x36..0x39) by this much
)
SYNC_DONE, SYNC_OPEN = 9, 10  # StAwtoSync byte offsets (RL6449_Project.h)


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


class Probe(Y.Run):
    def __init__(self, a):
        super().__init__(a)
        self.head = self.m.addr("g_stAwtoHead")
        self.sync = self.m.addr("g_stAwtoSync")
        self.names = {
            n: self.m.addr(n)
            for n in (
                "g_ucAwtoMenuOn",
                "g_ucAwtoSaverRun",
                "g_ucAwtoDdcDef",
                "g_ucAwtoHold",
            )
        }

    def window(self):
        raw = bytes(self.m.rd(self.head, 12))
        return [
            int.from_bytes(raw[2 * i : 2 * i + 2], "big" if self.bus.be else "little")
            for i in range(6)
        ]

    def row(self, t):
        w = self.window()
        extra = " ".join(f"{k[8:]}={self.m.rd(v)[0]}" for k, v in self.names.items())
        sy = self.m.rd(self.sync, 16)
        say(
            f"    t+{t:2d}s mode {self.bus.mode_state()} {w[0]} passes/s busy {100 - w[1] / 10:.1f} % hook {w[3] / 10:.1f} % idles {w[4]} "
            f"wake {w[5]} | sync done={sy[SYNC_DONE]} openreq={sy[SYNC_OPEN]} {extra}"
        )
        return w

    def boot(self):
        if not self.bus.run_until_mode(Y.MODE_ACTIVE, Y.BOOT_INSTR):
            return False
        self.bus.dbg_link_on()
        self.bus.wait(IDLE_S)
        return True

    def case(self, name, after):
        self.phase = name
        say(f"  case {name}")
        if name != "boot":
            self.signal = False
            self.stable_detect(False)
            self.bus.wait(1.5 if name == "fast" else 60 + L2_EXTRA_S)
            self.signal = True
            self.stable_detect(True)
            self.until(lambda: self.bus.mode_state() == Y.MODE_ACTIVE, Y.ON_MS * 4)
        late = None
        for t in range(after):
            self.bus.wait(1.0)
            w = self.row(t + 1)
            if t + 1 == CHECK_AFTER_S:
                late = w
        ok = late is not None and late[3] <= H.HEAD_HOLD_MAX_PM
        self.check(
            ok,
            f"{name}: busy hook off by {CHECK_AFTER_S} s after the picture",
            f"hook {late[3] / 10 if late else -1:.1f} % of passes",
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", default="all", choices=("fast", "slow", "boot", "all"))
    ap.add_argument("--after", type=int, default=30)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    a.report = False
    cases = ("boot", "fast", "slow") if a.case == "all" else (a.case,)
    fails = 0
    for c in cases:  # one image boot per case: each starts from the same settled ACTIVE
        r = Probe(a)
        try:
            if not r.boot():
                say(f"FAIL {c}: never ACTIVE")
                fails += 1
                continue
            r.case(c, a.after)
            fails += r.fails
        finally:
            r.bus.close()
    say(
        f"{'PASS' if fails == 0 else 'FAIL'} pacing_wake_sim {a.bin.name}: {fails} failed"
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
