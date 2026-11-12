#!/usr/bin/env python3
"""Power LED on unit 2 (awto-ddc#95): LED mode + P3 pin levels per power state, read over the debug slave.

usage: led_unit.py TAG          (TAG = tmp/fw/AWT26110002-<tag>-be; image already flashed; caller holds unit_lock)
- Reads g_ucAwtoLedMode and g_ucAwtoLedPins (MCU_FFE3 copy per main-loop pass; the debug slave reads 0 at FFE3 itself).
- States: ACTIVE; power saving (ddcutil VCP D6 = 4 on bus 11); wake (VCP D6 = 1); POWER off / on (test cmd 0x3E).
- --host-off: host outputs off (host_dpms.py, guarded) around the power-saving sample: the host's live TMDS clock wakes the
  unit about 0.4 s after D6 = 4 (#144 wake by TMDS clock), so without it the sample lands in WAKE SEARCH.
- Per state: SAMPLES reads SAMPLE_S apart (breathing shows as P3.6 varying), expected colour (led_check.STATE_LED).
- Ends: ring text (sync_log.py) to tmp/logs/led_unit/<tag>.txt; debug link off. Log: tmp/logs/led_unit.log
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "tmp/logs/led_unit.log"
OUT = ROOT / "tmp/logs/led_unit"
BUS, SERIAL = 11, "AWT26110002"                  # unit 2 HDMI-2 (scripts/devices.json); units 1 / 3 hands off
TESTCMD, POWER_KEY = 0xF6F8, 0x3E                # g_stAwtoDiag + 0x28 (dbg_link.py TESTCMD), test cmd POWER key
PWR_OFF, PWR_NORMAL, PWR_SAVING = 1, 2, 3        # Global.h EnumPowerStatus
MODE_ACTIVE = 3
POLL_S = 0.3                                     # one xdata read ~0.1 s
SAMPLES, SAMPLE_S = 6, 0.25                      # 1.5 s: a breathe ramp step is 16 ms, so P3.6 must change between reads
# State waits = sysm_sim bounds x1.25: power saving 3 s, off 1.5 s, on 3 s, wake 5.5 s; expiry: logged, the state is sampled anyway
WAIT_PS_S, WAIT_OFF_S, WAIT_ON_S, WAIT_WAKE_S = 3.75, 1.9, 3.75, 6.9
HOST_GUARD_S = 15                                # host off -> D6 = 4 -> PS wait 3.75 s -> sample 1.5 s -> link ~1 s = ~8 s; x1.25 + margin for ddcutil
DDC_LIMIT_S = 10                                 # ddcutil setvcp: ~1 s with retries; 10 s = stall


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def xsym(mp: Path, name: str) -> int:
    m = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", mp.read_text(errors="replace"))
    return int(m.group(1), 16) & 0xFFFF


class Unit:
    def __init__(self, mp: Path):
        import dbg_xdata as X
        import rtd_i2c_bridge as B
        self.X, self.B = X, B
        self.a = {n: xsym(mp, n) for n in ("g_stPowerInfo", "g_stModeInfo", "g_ucAwtoLedMode", "g_ucAwtoLedPins")}

    def rd(self, rio, n):
        v = self.X.read_bytes(rio, self.a[n], 1)
        return None if v is None else v[0]

    def session(self, fn):
        import dbg_link
        with dbg_link.linked(BUS, 2):
            rio = self.B.Real(BUS, allow_write=True, regread=True)
            try:
                return fn(rio)
            finally:
                rio.close()

    def press(self, rio):
        X = self.X
        return (rio.write(X.DEV8, 0x01, bytes([TESTCMD >> 8])) and rio.write(X.DEV8, 0x03, bytes([POWER_KEY])) and
                rio.write(X.DEV8, 0x3B, bytes([TESTCMD & 0xFF])))

    def wait(self, rio, pwr, mode, limit, what):
        t0 = time.monotonic()
        while time.monotonic() - t0 < limit:
            p, m = self.rd(rio, "g_stPowerInfo"), self.rd(rio, "g_stModeInfo")
            if p is not None and m is not None and p >> 4 == pwr and (mode is None or m & 0x1F == mode):
                say(f"  {what}: reached after {time.monotonic() - t0:.1f} s")
                return True
            time.sleep(POLL_S)
        say(f"  {what}: NOT reached within {limit} s (power {p}, mode {m})")
        return False

    def sample(self, rio, state, table):
        import led_check as LED
        pins = []
        for _ in range(SAMPLES):
            v = self.rd(rio, "g_ucAwtoLedPins")
            pins.append(None if v is None else (v >> 5 & 1, v >> 6 & 1))
            time.sleep(SAMPLE_S)
        mode = LED.MODE_LED.get(self.rd(rio, "g_ucAwtoLedMode"), "?")
        want = LED.STATE_LED[state]
        p35 = sorted({p[0] for p in pins if p})
        p36 = sorted({p[1] for p in pins if p})
        ok = mode == want and {LED.ON: (p35 == [1] and p36 == [0]), LED.OFF: (p35 == [0] and p36 == [0]),
                               LED.BREATHE: (p35 == [0] and p36 == [0, 1])}[want]
        table.append((state, want, mode, p35, p36, ok))
        say(f"  {'PASS' if ok else 'FAIL'} {state}: want {want}; g_ucAwtoLedMode {mode}, P3.5 {p35}, P3.6 {p36} ({SAMPLES} reads)")


def ddc(vcp: str, val: str):
    r = subprocess.run(["ddcutil", "--bus", str(BUS), "setvcp", vcp, val], capture_output=True, text=True, timeout=DDC_LIMIT_S)
    say(f"  ddcutil --bus {BUS} setvcp {vcp} {val}: rc {r.returncode} {r.stderr.strip()[:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--host-off", action="store_true", help="host outputs off during the power-saving sample (host_dpms.py)")
    a = ap.parse_args()
    stem = ROOT / "tmp/fw" / f"{SERIAL}-{a.tag}-be"
    mp = stem.with_suffix(".map")
    if not mp.exists():
        mp = Path(f"/mnt/2tb/git/awto-ddc/tmp/fw/{SERIAL}-{a.tag}-be.map")
    u, table = Unit(mp), []
    say(f"led_unit {a.tag} (map {mp})")
    u.session(lambda rio: (u.wait(rio, PWR_NORMAL, MODE_ACTIVE, WAIT_ON_S, "ACTIVE"), u.sample(rio, "ACTIVE", table)))
    import host_dpms as HD
    host_off = False
    if a.host_off:
        try:
            host_off = HD.off(HOST_GUARD_S)
        except HD.UserPresent as e:
            say(f"  host_dpms off refused ({e}): power saving sampled with the host signal on")
    ddc("D6", "04")
    try:
        u.session(lambda rio: (u.wait(rio, PWR_SAVING, None, WAIT_PS_S, "power saving"), u.sample(rio, "POWER SAVING", table)))
    finally:
        if host_off:
            HD.on()
            say(f"  host outputs on: {HD.status()}")
    ddc("D6", "01")
    u.session(lambda rio: (u.wait(rio, PWR_NORMAL, MODE_ACTIVE, WAIT_WAKE_S, "wake: ACTIVE"), u.sample(rio, "ACTIVE", table)))
    u.session(lambda rio: (u.press(rio), u.wait(rio, PWR_OFF, None, WAIT_OFF_S, "POWER off"), u.sample(rio, "OFF", table)))
    u.session(lambda rio: (u.press(rio), u.wait(rio, PWR_NORMAL, MODE_ACTIVE, WAIT_ON_S, "POWER on: ACTIVE"),
                           u.sample(rio, "ACTIVE", table)))
    import dbg_link
    dbg_link.on(BUS, 2)
    txt = subprocess.run([sys.executable, str(ROOT / "scripts/sync_log.py"), str(BUS), "--serial", SERIAL, "--map", str(mp), "--whole"],
                         capture_output=True, text=True, timeout=30).stdout
    dbg_link.off(BUS)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.tag}.txt").write_text(txt)
    say("  ring LED / system lines:")
    for ln in txt.splitlines():
        if "LED:" in ln or "system:" in ln and " -> " in ln:
            say(f"    {ln.strip()}")
    fails = sum(1 for *_, ok in table if not ok)
    say(f"{'PASS' if not fails else 'FAIL'} led_unit {a.tag}: {len(table) - fails}/{len(table)} states")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
