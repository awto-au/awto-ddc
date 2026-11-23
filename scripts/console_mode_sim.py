#!/usr/bin/env python3
"""console_mode (registry id 110, awto-ddc#218) in fw_sim: Off / Until signal / Always, the 3 s close, key dismissal.

usage: console_mode_sim.py BIN MAP
  Until signal: the console that opened itself is up at ACTIVE, closes AWTO_CON_HOLD_MS after it (ring event E0 0C once);
                a key (UP) closes it at once, event E0 0B, nothing else happens (no menu, no backlight bar).
  Always: still open long after the hold, no close event.   Off: never opens.
Exit 1 on any failed check. Log: ./tmp/logs/console_mode_sim.log
"""
import argparse
import re
import sys
from pathlib import Path

from _log import Logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S

LOG = S.ROOT / "tmp/logs/console_mode_sim.log"
SET_ID_CONSOLE_MODE = 110
OFF, UNTIL, ALWAYS = 0, 1, 2
EV_SEL, EV_CON_KEY, EV_CON_DONE = 0xE0, 0x0B, 0x0C
A0, IDLE = 0xFF09, 0xF8                   # key ADC cells (deadport_sim.py)
KEY_UP = (A0, 0x38)
STEP_S = 0.1                              # poll step for the ACTIVE edge: the hold is 3 s, so 0.1 s resolves it
SRC = (S.ROOT / "fw/osd/console.c", S.ROOT / "fw/sdk/Project/Header/RL6449_Project.h")


def const(name: str) -> int:
    for f in SRC:
        m = re.search(rf"^#define {name}\s+(\d+)", f.read_text(), re.MULTILINE)
        if m:
            return int(m.group(1))
    raise SystemExit(f"{name} not found in {[p.name for p in SRC]}")


HOLD_S = const("AWTO_CON_HOLD_MS") / 1000.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = Logger(LOG)
    fails = []

    say = lf.say

    def check(name, ok, detail=""):
        say(f"{'PASS' if ok else 'FAIL'} {name}{(': ' + detail) if detail else ''}")
        if not ok:
            fails.append(name)

    def run(mode: int):
        """one boot with the registry forced to `mode`; returns (bus, events [(arg, fw s)], open(), tap)"""
        bus = S.SimBus(a.bin, a.map, video="1080p60", port="D3", boot=False)
        m = bus.m
        evs = []

        def set_get(m_, r):
            return {"val": mode} if (r["a1"] & 0xFF) == SET_ID_CONSOLE_MODE else None

        def push(m_, r):
            if (r["a1"] & 0xFF) == EV_SEL:
                evs.append(((r["a2"] & 0xFF), round(bus.now(), 3)))

        m.stub("set_get", set_get)
        m.stub("AwtoSyncPush", push)
        bus.boot()
        gpio = bus.addr("g_stAwtoGpio") + 3

        def is_open():
            return m.rd(gpio)[0] != 0

        def tap(key, ms=150, gap=0.4):
            m.wr(key[0], bytes([key[1]])); bus.wait(ms / 1000.0)
            m.wr(key[0], bytes([IDLE])); bus.wait(gap)

        def active_at(limit_s=40.0):
            t0 = bus.now()
            while bus.now() - t0 < limit_s:
                if bus.mode_state() == 3:
                    return bus.now()
                bus.wait(STEP_S)
            return None

        return bus, evs, is_open, tap, active_at

    say(f"console_mode_sim {a.bin.name}: hold {HOLD_S:.1f} s")

    bus, evs, is_open, tap, active_at = run(UNTIL)
    t_act = active_at()
    check("until: reaches ACTIVE", t_act is not None)
    if t_act is not None:
        bus.wait(1.0)
        check("until: console open 1 s after ACTIVE", is_open())
        bus.wait(HOLD_S + 1.5)
        done = [t for ev, t in evs if ev == EV_CON_DONE]
        check("until: console closed after the hold", not is_open(), f"events {evs}")
        check("until: one close event, hold..hold+1 s after ACTIVE", len(done) == 1 and HOLD_S - 0.1 <= done[0] - t_act <= HOLD_S + 1.0,
              f"ACTIVE at {t_act:.2f} s, events {evs}")

    bus, evs, is_open, tap, active_at = run(UNTIL)
    t_act = active_at()
    if t_act is not None:
        bus.wait(0.8)
        check("key: console open before the key", is_open())
        tap(KEY_UP)
        check("key: UP closed the console at once", not is_open(), f"events {evs}")
        check("key: event 'closed by a key', not the 3 s one", [ev for ev, _ in evs if ev in (EV_CON_KEY, EV_CON_DONE)] == [EV_CON_KEY],
              f"events {evs}")
        bus.wait(HOLD_S + 1.0)
        check("key: no second close event", [ev for ev, _ in evs if ev in (EV_CON_KEY, EV_CON_DONE)] == [EV_CON_KEY])

    bus, evs, is_open, tap, active_at = run(ALWAYS)
    t_act = active_at()
    if t_act is not None:
        bus.wait(HOLD_S * 3)
        check("always: console still open 3 holds after ACTIVE", is_open(), f"events {evs}")
        check("always: no close event", not [ev for ev, _ in evs if ev in (EV_CON_KEY, EV_CON_DONE)])
        tap(KEY_UP)
        check("always: a key does not close it", is_open())

    bus, evs, is_open, tap, active_at = run(OFF)
    t_act = active_at()
    if t_act is not None:
        bus.wait(1.0)
        check("off: console never opened by itself", not is_open())

    say(f"{'FAIL' if fails else 'PASS'} console_mode_sim {a.bin.name}: {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
