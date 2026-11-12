#!/usr/bin/env python3
"""Cold power-on timing of a relay unit (#63 boot time): relay OFF, wait, relay ON, then time the external milestones.

usage: cold_boot.py --unit 3 [--runs 3] [--map tmp/fw/<tag>.map] [--label L]
  Per run: relay off (power_cycle.py --off, then OFF_S: the PSU holds the scaler ~6 s, #27), relay on = t0 (after the
  verified-on return), then poll from t0: EDID serial readable at 0x50 (scaler alive, DDC RAM loaded), debug slave 0x35
  answers the diag magic (main loop running), diag stage 8 (panel + eDP up), mode ACTIVE. Then reads the diag stage
  times (firmware ms since its Timer2 start) and the #60/#63 switch log (logo draw, VDD, power actions, T3).
  Host side: drm uevents for the connector (udevadm monitor) with their times relative to t0.
  Polls are 10 ms apart (each EDID/0x35 probe itself costs ~1-3 ms at 100 kHz); per-milestone limit LIMIT_S.
Log: ./tmp/logs/cold_boot.log; TSV row per run: tmp/logs/cold_boot.tsv
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

ROOT = Path(__file__).resolve().parent.parent
OFF_S = 8                    # power_cycle.py OFF_S: PSU hold-up ~6 s measured (#27) x1.25
LIMIT_S = 15.0               # boot to ACTIVE was 5.7 s in the sim (docs/delays.md) + host modeset; x~2.5 (cold, HDMI retrain)
POLL_S = 0.010
MODES = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF"]


def mapsym(mp: str, name: str) -> int | None:
    m = re.search(rf"^D:\s+([0-9A-F]{{8}})\s+_{name}\b", mp, re.M)
    return int(m.group(1), 16) & 0xFFFF if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="3")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    u = json.loads((ROOT / "scripts/devices.json").read_text())["units"][a.unit]
    if not u.get("relay"):
        sys.exit(f"unit {a.unit} has no relay; nothing done")
    if a.map is None:
        a.map = Path(json.loads((ROOT / f"tmp/fw/{u['serial']}-flashed.json").read_text())["image"]).with_suffix(".map")
    mp = a.map.read_text(errors="replace")
    diag, mode_a, sw = mapsym(mp, "g_stAwtoDiag") or 0xF6D0, mapsym(mp, "g_stModeInfo"), mapsym(mp, "g_stAwtoSw")
    lf = (ROOT / "tmp/logs/cold_boot.log").open("a", buffering=1)
    tsv = ROOT / "tmp/logs/cold_boot.tsv"
    if not tsv.exists():
        tsv.write_text("time\tlabel\timage\trun\tedid_s\tdbg_s\tstage8_s\tactive_s\tstages_ms\tlogo_ms\tvdd_ms\tbl_on_ms\tuevents\n")

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    def pc(*args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/power_cycle.py"), "--relay", u["relay"], *args],
                              capture_output=True, text=True, timeout=60).returncode

    bus = None
    for run in range(1, a.runs + 1):
        if pc("--off"):
            sys.exit("relay off failed")
        t_off = time.monotonic()
        while time.monotonic() - t_off < OFF_S:      # PSU hold-up; the unit must be fully dead before the cold start
            time.sleep(0.2)
        udev = subprocess.Popen(["stdbuf", "-oL", "udevadm", "monitor", "--kernel", "--subsystem-match=drm"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if pc("--on"):
            sys.exit("relay on failed")
        t0 = time.monotonic()
        res = {}
        cands = [b for b in i2cbus.list_buses(display_only=True)]
        while time.monotonic() - t0 < LIMIT_S and "edid" not in res:
            for b in cands:
                if i2cbus.edid_serial(b) == u["serial"]:
                    bus, res["edid"] = b, time.monotonic() - t0
                    break
            time.sleep(POLL_S)
        io = B.Real(bus, allow_write=False, regread=True) if bus is not None else None
        while io and time.monotonic() - t0 < LIMIT_S:
            h = X.read_bytes(io, diag, 4)
            if h and h[:2] == b"AD":
                res.setdefault("dbg", time.monotonic() - t0)
                if h[3] >= 8:
                    res.setdefault("stage8", time.monotonic() - t0)
                    if mode_a is not None:
                        ms = X.read_bytes(io, mode_a, 1)
                        if ms and ms[0] & 0x1F == 3:
                            res["active"] = time.monotonic() - t0
                            break
            time.sleep(POLL_S)
        stages, evs = [], []
        if io:
            blk = X.read_blocks(io, diag, 20) or b""
            stages = [int.from_bytes(blk[4 + 2 * i:6 + 2 * i], "big") for i in range(8)] if len(blk) >= 20 else []
            if sw is not None:
                raw = X.read_blocks(io, sw, 12 + 4 * 40) or b""
                if len(raw) >= 12:
                    evs = [(raw[12 + 4 * i], raw[13 + 4 * i], int.from_bytes(raw[14 + 4 * i:16 + 4 * i], "big")) for i in range(min(raw[3], 40))]
            io.close()
        udev.terminate()
        ue = [ln for ln in udev.communicate(timeout=2)[0].splitlines() if "change" in ln]
        ev = lambda i, g=None: next((t for e, arg, t in evs if e == i and (g is None or arg == g)), None)   # noqa: E731
        logo = (ev(0x60, 0), ev(0x60, 1))
        say(f"run {run} {a.map.stem}: EDID {res.get('edid', -1):.3f} s, 0x35 {res.get('dbg', -1):.3f} s, stage 8 {res.get('stage8', -1):.3f} s, "
            f"ACTIVE {res.get('active', -1):.3f} s after relay on; fw stages ms {stages}; logo draw {logo} ms (T2 ticks), "
            f"VDD {ev(0x70)}, backlight on {ev(0x10, 2)}, T3 {ev(0x20, 0)}..{ev(0x20, 1)}; drm uevents {len(ue)}")
        with tsv.open("a") as f:
            f.write("\t".join(map(str, [time.strftime("%Y-%m-%dT%H:%M:%S%z"), a.label, a.map.stem, run,
                                        *(f"{res.get(k, -1):.3f}" for k in ("edid", "dbg", "stage8", "active")),
                                        stages, logo, ev(0x70), ev(0x10, 2), len(ue)])) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
