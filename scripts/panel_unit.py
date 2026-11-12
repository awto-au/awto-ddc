#!/usr/bin/env python3
"""Panel machine on unit 2 (awto-ddc#162 step 2): cold boots and POWER-key off / on, ring per run, panel facts per run.

usage: panel_unit.py TAG [--cold 3] [--power-key 1] [--switch 0] [--no-flash]      (TAG = tmp/fw/AWT26110002-<tag>-be.bin, gated images only)
- Flash: ./dev.py flash --unit 2 <bin> (refuses an ungated image). Debug link off first (dbg_link.py off 11).
- Cold boot: hass_power.py cycle --unit 2; ring polled (dbg_link on, sync_log.py, dbg_link off) until 'mode ACTIVE'.
- POWER key: test cmd 0x3E (soft off), OFF_S, 0x3E (soft on); ring polled until 'mode ACTIVE' of the power-key episode.
- Switch (#162 step 3): kvm.py D1 then D2 (DDC/CI VCP 0x60, unit 2 only); ring polled until the switch episode shows a picture
  ('mode ACTIVE' or the fast path's 'FAST SWITCH -> ACTIVE'). D1 = the DP-1 mirror (host layout untouched). On D1 the debug
  slave follows the DP port, so that episode is read back whole from D2 (<tag>-switchN-whole.txt).
- Per run (ring ms of the episode): POWER OFF / SEARCH / ACTIVE, predetect flaps, backlight pin lines, blinks (a backlight off
  then on again in one episode), link trainings, stream -> backlight on, lines 'outside the panel machine'.
Ring text per run: tmp/logs/panel_unit/<tag>-<run>.txt. Log: tmp/logs/panel_unit.log
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "tmp/logs/panel_unit.log"
OUT = ROOT / "tmp/logs/panel_unit"
BUS, SERIAL, UNIT = 11, "AWT26110002", 2      # unit 2 (scripts/devices.json); units 1 / 3 are hands off
BOOT_WAIT_S = 6.0      # cold boot -> ACTIVE: s1-5 2.47 s worst with HDMI predetect flaps (#162), x2.4 = 6 s; expiry = run FAIL
KEY_WAIT_S = 6.0       # POWER-key on -> ACTIVE: s1-5 sim / unit < 2.5 s (#144 boot profile), x2.4; expiry = run FAIL
SWITCH_WAIT_S = 4.0    # input switch -> picture: full path ~1 s (#60 / #83), DP search time 3 s worst x1.25 ~ 4 s; expiry = run FAIL
OFF_S = 1.0            # soft off -> 'mode POWER OFF': PWM->BL 50 + T4 250 + T5 20 + NVRAM flush (<= 216 ms stall, #150) = 0.54 s
                       # + one ring poll 0.2 s = 0.74 s, x1.25 ~ 1 s; expiry = press again
T6_S = 1.4             # then the panel's T6 (1.1 s, registry PANEL_T6) x1.25, so the soft on meets a panel past T6
PRESSES = 3            # a press with the console open can go to closing it (AwtoKeyRoute); 3 = at most two such
POLL_S = 0.5           # ring poll: one read ~0.1 s; boot is seconds
TESTCMD = 0xF6F8       # g_stAwtoDiag + 0x28 (dbg_link.py TESTCMD)
POWER_KEY = 0x3E
PWR_OFF, PWR_NORMAL = 1, 2             # Global.h EnumPowerStatus
MODE_ACTIVE, MODE_POWER_OFF = 3, 7     # fw_sim.MODE_NAMES


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(*a, limit=120):
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, cwd=ROOT, timeout=limit)


def ring(mp: Path, whole=False) -> str:
    run("scripts/dbg_link.py", "on", BUS, limit=30)
    r = run("scripts/sync_log.py", BUS, "--serial", SERIAL, "--map", mp, *(["--whole"] if whole else []), limit=30)
    run("scripts/dbg_link.py", "off", BUS, limit=30)
    return r.stdout


def until_active(mp: Path, wait_s: float, want_kind: str, done=("mode ACTIVE",)) -> str:
    t0, txt = time.monotonic(), ""
    while time.monotonic() - t0 < wait_s:
        time.sleep(POLL_S)
        txt = ring(mp)
        if want_kind in txt and any(d in txt for d in done):
            break
    return txt


def xsym(mp: Path, name: str) -> int:
    m = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", mp.read_text(errors="replace"))
    return int(m.group(1), 16) & 0xFFFF


def press_until(mp: Path, want: tuple, wait_s: float, what: str) -> bool:
    """POWER press (test cmd 0x3E) until (power status, mode) == want, read live (g_stPowerInfo high nibble, g_stModeInfo
    & 0x1F as fw_sim); a press can go to closing the console (AwtoKeyRoute): at most PRESSES presses."""
    import dbg_link
    import dbg_xdata as X
    import rtd_i2c_bridge as B
    pa, ma = xsym(mp, "g_stPowerInfo"), xsym(mp, "g_stModeInfo")
    with dbg_link.linked(BUS, 2):
        rio = B.Real(BUS, allow_write=True, regread=True)
        try:
            for n in range(PRESSES):
                if not (rio.write(X.DEV8, 0x01, bytes([TESTCMD >> 8])) and rio.write(X.DEV8, 0x03, bytes([POWER_KEY])) and
                        rio.write(X.DEV8, 0x3B, bytes([TESTCMD & 0xFF]))):
                    say(f"  POWER press for {what}: NAKed")
                    return False
                t0 = time.monotonic()
                while time.monotonic() - t0 < wait_s:
                    time.sleep(POLL_S)
                    p, m = X.read_bytes(rio, pa, 1), X.read_bytes(rio, ma, 1)     # None while the MCU halts on a flash op
                    if p and m and (p[0] >> 4, m[0] & 0x1F) == want:
                        say(f"  POWER press {n + 1} -> {what} after {time.monotonic() - t0:.1f} s")
                        return True
            say(f"  {what}: not reached after {PRESSES} presses")
            return False
        finally:
            rio.close()


def facts(txt: str) -> dict:
    rows = [(int(m.group(1)), m.group(2).strip()) for m in re.finditer(r"\+\s*(\d+) ms (.*)", txt)]
    ms = lambda pat: next((t for t, x in rows if re.search(pat, x)), None)
    bl = [(t, x) for t, x in rows if x in ("backlight on", "backlight off")]
    blink = sum(1 for a, b in zip(bl, bl[1:]) if a[1] == "backlight off" and b[1] == "backlight on")
    video = ms(r"-> VIDEO: eDP-1 link trained")
    blon = next((t for t, x in bl if x == "backlight on"), None)
    return dict(off=ms(r"^mode POWER OFF"), search=ms(r"^mode SEARCH"), active=ms(r"^mode ACTIVE|FAST SWITCH -> ACTIVE"),
                flaps=len(re.findall(r"D2 signal lost", txt)) + sum(int(x) for x in re.findall(r"repeated (\d+) more", txt)),
                bl=" ".join(f"{x.split()[1]}@{t}" for t, x in bl), blinks=blink,
                links=sum(1 for _, x in rows if "eDP-1 link trained, stream on" in x or x == "eDP-1: link trained"),
                link_fail=sum(1 for _, x in rows if "link training FAIL" in x),
                stream_bl=(blon - video) if (video is not None and blon is not None) else None,
                outside=sum(1 for _, x in rows if "outside the panel machine" in x))


def report(tag: str, name: str, txt: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}-{name}.txt").write_text(txt)
    d = facts(txt)
    say(f"  {tag} {name}: POWER OFF +{d['off']} SEARCH +{d['search']} ACTIVE +{d['active']} flaps {d['flaps']} | backlight {d['bl']} "
        f"blinks {d['blinks']} | link trainings {d['links']} (fail {d['link_fail']}) stream->backlight {d['stream_bl']} ms | "
        f"outside-machine lines {d['outside']}")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cold", type=int, default=3)
    ap.add_argument("--power-key", type=int, default=1)
    ap.add_argument("--switch", type=int, default=0, help="input switches D1 then D2 (kvm.py, VCP 0x60)")
    ap.add_argument("--no-flash", action="store_true")
    ap.add_argument("--wait", type=float, default=BOOT_WAIT_S, help="cold boot -> ACTIVE poll limit, s (characterising slow HDMI scans)")
    a = ap.parse_args()
    b = ROOT / f"tmp/fw/{SERIAL}-{a.tag}-be.bin"
    mp = b.with_suffix(".map")
    if not a.no_flash:
        run("scripts/dbg_link.py", "off", BUS, limit=30)
        r = run("dev.py", "flash", "--unit", UNIT, b, limit=400)
        say(f"== {a.tag}: flash rc={r.returncode} {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
        if r.returncode:
            return 1
    bad = 0
    for n in range(a.cold):
        run("scripts/hass_power.py", "cycle", "--unit", UNIT)
        d = report(a.tag, f"cold{n + 1}", until_active(mp, a.wait, "power on"))
        bad += d["active"] is None
    for n in range(a.power_key):
        if not press_until(mp, (PWR_OFF, MODE_POWER_OFF), OFF_S, "power OFF"):
            return 1
        time.sleep(T6_S)
        ok = press_until(mp, (PWR_NORMAL, MODE_ACTIVE), KEY_WAIT_S, "power key on -> ACTIVE")
        d = report(a.tag, f"key{n + 1}", ring(mp))
        bad += (not ok) or d["active"] is None
    for n in range(a.switch):
        for port in ("D1", "D2"):
            run("scripts/kvm.py", port, "--units", UNIT, limit=30)
            d = report(a.tag, f"switch{n + 1}-{port}", until_active(mp, SWITCH_WAIT_S, f"switch to {port}", ("mode ACTIVE", "FAST SWITCH -> ACTIVE")))
            bad += d["active"] is None and port == "D2"     # on D1 the debug slave follows to the DP port: bus 11 reads fail
        (OUT / f"{a.tag}-switch{n + 1}-whole.txt").write_text(ring(mp, whole=True))      # the D1 episode, read back on D2
    say(f"{'PASS' if not bad else 'FAIL'} panel_unit {a.tag}: {bad} run(s) without ACTIVE")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
