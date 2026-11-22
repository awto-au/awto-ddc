#!/usr/bin/env python3
"""Production-image checks of the flash clock default on the test unit (docs/clock-sweep.md "Default flash clock"). Only ./dev.py touches the unit.

usage: flash_soak.py MODE [N] [--unit 3] [--map MAP] [--tag T]
  soak MIN   every PERIOD_S: `dev.py health` (diag stage, main loop rate, mode / power state, input timing, delay cal, monitor row), next saver
             (VCP 0xEB 3 / 4 / 8 / 2, then 0), uptime check (a WDT reset shows as the Timer2 heartbeat going backwards / a boot in the sync log); TSV per period
  wakes N    N x host DPMS off (Mutter PowerSaveMode 3) -> on (0): firmware must be ACTIVE again (health) within WAKE_S
  nv N       N x (brightness VCP 0x10 changed and restored: wait for the flush gate, read back); g_stAwtoNv deltas: items programmed, flash ops, erases, bytes
  fps        Scope 2 (g_usAwtoS2Frame) and Asteroids (g_usAwtoAstStep) per second over FPS_S, each saver on, then off
Logs: ./tmp/logs/flash_soak.log, ./tmp/logs/flash_soak.tsv
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
from _log import log_line as _log_line

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/flash_soak.log"
TSV = ROOT / "tmp/logs/flash_soak.tsv"
PERIOD_S = 60            # one health run is ~4 s; a saver runs ~1 min each: 30 periods cover the savers 7 x
SAVERS = (4, 8, 2, 0)  # Scope 2, Asteroids, Pac-Man, off (VCP 0xEB)
WAKE_S = 15              # host DPMS on -> ACTIVE: wake_time.py measures ~2 s; 15 s = a failed wake, not a slow one
FPS_S = 10               # counter delta window: +-1 frame of ~300
S2, AST = "0xF038", "0xE95C"


def say(s: str) -> None:
    _log_line(s, LOG)


def dev(*a: str, timeout: float = 90) -> tuple[int, str]:
    r = subprocess.run([str(ROOT / "dev.py"), *a], capture_output=True, text=True, timeout=timeout, check=False)
    return r.returncode, r.stdout + r.stderr


def health(unit: str, mp: str) -> tuple[bool, str]:
    rc, out = dev("health", "--unit", unit, "--map", mp)
    m = re.search(r"HEALTH \S+ (\d+)/(\d+) PASS", out)
    fails = [l.split("FAIL", 1)[1].strip()[:120] for l in out.splitlines() if " FAIL " in l]
    return rc == 0 and bool(m) and m.group(1) == m.group(2), (m.group(0) if m else "no HEALTH line") + ("; " + " | ".join(fails) if fails else "")


def uptime_ms(unit: str) -> int | None:
    """Firmware ms since reset (dev.py synclog 'fw now N ms'): going backwards = a reset (WDT or crash)."""
    m = re.search(r"fw now (\d+) ms", dev("synclog", "--unit", unit)[1])
    return int(m.group(1)) if m else None


def word(unit: str, mp: str, addr: str) -> int | None:
    _rc, out = dev("dbg-read", "--unit", unit, "--map", mp, f"{addr}:2")
    m = re.search(rf"{addr} @0x[0-9a-f]+: ([0-9a-f]{{2}}) ([0-9a-f]{{2}})", out)
    return int(m.group(1) + m.group(2), 16) if m else None


NV = "0xE09A"            # g_stAwtoNv (RL6449_Project.h StAwtoNv): flush +6, items +8, ops +10, erases +16, bytes +18
GATE_S = 6.5             # nv_test.py: gate = debounce 2 s + stable 3 s, x1.25


def nv_counters(unit: str, mp: str) -> dict | None:
    _rc, out = dev("dbg-read", "--unit", unit, "--map", mp, f"{NV}:20")
    m = re.search(rf"{NV} @0x[0-9a-f]+: ((?:[0-9a-f]{{2}} ?){{20}})", out, re.IGNORECASE)
    if not m:
        return None
    b = bytes(int(x, 16) for x in m.group(1).split())
    w = lambda o: b[o] << 8 | b[o + 1]
    return {"flush": w(6), "items": w(8), "ops": w(10), "erase": w(16), "bytes": w(18)}


def vcp_get(unit: str, code: str) -> int | None:
    m = re.search(r"VCP [0-9A-Fa-f]+ C (\d+) \d+", dev("ddc", "--unit", unit, "get", code)[1])
    return int(m.group(1)) if m else None


def vcp(unit: str, code: str, v: int) -> bool:
    return dev("ddc", "--unit", unit, "set", code, str(v))[0] == 0


def dpms(mode: int) -> bool:
    r = subprocess.run(["busctl", "--user", "set-property", "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                        "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", "i", str(mode)], capture_output=True, text=True, check=False)
    return r.returncode == 0


def row(f: str, *c) -> None:
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as t:
        if new:
            t.write("time\tmode\tn\tok\tdetail\n")
        t.write("\t".join([isostamp.now(), f, *map(str, c)]) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("soak", "wakes", "fps", "nv"))
    ap.add_argument("n", nargs="?", type=int, default=30)
    ap.add_argument("--unit", default="3")
    ap.add_argument("--map", required=True)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    bad = 0
    if a.mode == "soak":
        t_end = time.time() + a.n * 60
        n = 0
        up0, tup0 = uptime_ms(a.unit), time.time()
        while time.time() < t_end:
            t0 = time.time()
            s = SAVERS[n % len(SAVERS)]
            vcp(a.unit, "0xEB", s)
            ok, d = health(a.unit, a.map)
            up, tup = uptime_ms(a.unit), time.time()
            if up is None or up0 is None or up < up0 + (tup - tup0) * 1000 * 0.5:
                ok, d = False, d + f"; RESET or no uptime (fw ms {up0} -> {up} in {tup - tup0:.0f} s)"
            up0, tup0 = up, tup
            bad += not ok
            say(f"{a.tag} period {n} saver {s}: {'PASS' if ok else 'FAIL'} {d}")
            row("soak", n, int(ok), d)
            n += 1
            time.sleep(max(0.0, PERIOD_S - (time.time() - t0)))
        vcp(a.unit, "0xEB", 0)
        say(f"{a.tag} SUMMARY soak {n} periods, {bad} failed")
    elif a.mode == "wakes":
        for n in range(a.n):
            dpms(3)
            time.sleep(6)
            dpms(0)
            t0 = time.time()
            ok = False
            d = ""
            while time.time() - t0 < WAKE_S and not ok:
                ok, d = health(a.unit, a.map)
            if not ok:
                (LOG.parent / f"wake_fail_{a.tag}_{n}.txt").write_text(dev("synclog", "--unit", a.unit)[1])    # last events of the failing wake
            bad += not ok
            say(f"{a.tag} wake {n}: {'PASS' if ok else 'FAIL'} after {time.time() - t0:.1f} s {d}")
            row("wake", n, int(ok), d)
        say(f"{a.tag} SUMMARY wakes {a.n}, {bad} failed")
    elif a.mode == "nv":
        base = vcp_get(a.unit, "0x10")
        c0 = nv_counters(a.unit, a.map)
        say(f"{a.tag} nv start: brightness {base}, counters {c0}")
        for n in range(a.n):
            ok = True
            d = ""
            for want in ((base or 50) - 5, base or 50):
                vcp(a.unit, "0x10", want)
                time.sleep(GATE_S)
                got = vcp_get(a.unit, "0x10")
                if got != want:
                    ok, d = False, d + f" wrote {want} read back {got};"
            bad += not ok
            say(f"{a.tag} nv cycle {n}: {'PASS' if ok else 'FAIL'}{d}")
            row("nv", n, int(ok), d)
        c1 = nv_counters(a.unit, a.map)
        say(f"{a.tag} SUMMARY nv {a.n} cycles, {bad} failed; counters {c0} -> {c1}; brightness now {vcp_get(a.unit, '0x10')}")
    else:
        for name, code, addr in (("scope2", 4, S2), ("asteroids", 8, AST)):
            vcp(a.unit, "0xEB", code)
            time.sleep(3)
            t0, c0 = time.time(), word(a.unit, a.map, addr)
            time.sleep(FPS_S)
            t1, c1 = time.time(), word(a.unit, a.map, addr)
            if c0 is None or c1 is None:
                say(f"{a.tag} fps {name}: counter unreadable")
                bad += 1
                continue
            fps = ((c1 - c0) & 0xFFFF) / (t1 - t0)
            say(f"{a.tag} fps {name}: {fps:.2f} / s (counter {c0} -> {c1} in {t1 - t0:.1f} s)")
            row("fps", name, 1, f"{fps:.2f}")
        vcp(a.unit, "0xEB", 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
