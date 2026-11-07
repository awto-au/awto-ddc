#!/usr/bin/env python3
"""Input-switch timeline (#60): switch a unit's input over debug slave 0x35 and decode the firmware's StAwtoSw log.

usage: sw_timeline.py <bus> --serial S --map MAP [--to D1|D2|D3] [--runs N] [--settle-s 8] [--read-only]
  --to: test cmd 0x31..0x33 (fixed port, as VCP 0x60), then read g_stAwtoSw once the unit is ACTIVE again or --settle-s passed.
  --read-only: decode the current log only. Host side per run: kernel drm uevents (udevadm monitor) and mutter journal lines.
  Events (RL6449_Project.h AWTO_SW_EV_*): 01 mode state, 10 panel power action, 20 T3 wait start/end, 40 switch cmd,
  50/51/52 held-visual guards. Times = firmware g_usTimerCounter ms relative to the arm (usT0).
Log: ./tmp/logs/sw_timeline.log (one decoded line per event)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

MODES = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
POWER = {0: "PANEL_ON", 1: "PANEL_OFF", 2: "BACKLIGHT_ON", 3: "BACKLIGHT_OFF"}       # SDK _PANEL_ON.. order (UserCommonInterface)
TESTCMD = 0xF6F8
PORT_CMD = {"D1": 0x31, "D2": 0x32, "D3": 0x33}
N_EV = 40


def sym(map_path: Path, name: str) -> int:
    import re
    m = re.search(rf"^D:\s+([0-9A-F]{{8}})\s+_{name}\b", map_path.read_text(errors="replace"), re.M)
    if not m:
        sys.exit(f"{name} not in {map_path}: image without the #60 switch log")
    return int(m.group(1), 16) & 0xFFFF


def decode(raw: bytes, be: bool = True):
    t0 = int.from_bytes(raw[4:6], "big" if be else "little")
    hdr = {"magic": chr(raw[0]) if raw[0] else "-", "seq": raw[1], "port": raw[2], "n": raw[3], "t0": t0,
           "hpd_low": list(raw[7:11]), "hold_blocks": raw[11]}
    evs = []
    for i in range(min(raw[3], N_EV)):
        e = raw[12 + 4 * i:16 + 4 * i]
        ms = (int.from_bytes(e[2:4], "big" if be else "little") - t0) & 0xFFFF
        evs.append((ms, e[0], e[1]))
    return hdr, evs


def name(ev_id: int, arg: int) -> str:
    if ev_id == 0x01:
        return f"mode {MODES[arg] if arg < len(MODES) else arg}"
    if ev_id == 0x10:
        return f"power {POWER.get(arg, arg)}"
    if ev_id == 0x20:
        return f"T3 wait {'start' if arg == 0 else 'end'}"
    if ev_id == 0x40:
        return f"switch cmd 0x{arg:02X}"
    return {0x50: "hold: disable blocked", 0x51: "hold: logo redrawn", 0x52: "hold: OSD event dropped"}.get(ev_id, f"ev 0x{ev_id:02X}") + f" ({arg})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--to", choices=sorted(PORT_CMD))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--settle-s", type=float, default=8.0, help="read the log this long after the switch (DP search 3 s + display setting)")
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--read-bus", type=int, help="bus to read the log on after the switch (debug slave follows the new port: "
                    "D1 = the DP AUX adapter); default = <bus>")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (root / "tmp/logs/sw_timeline.log").open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    i2cbus.require_unit(a.bus, a.serial)
    base = sym(a.map, "g_stAwtoSw")
    io = B.Real(a.bus, allow_write=not a.read_only, regread=True)     # regread: 0x35 read staging passes in read-only mode
    try:
        for run in range(1 if a.read_only else a.runs):
            udev = None
            if not a.read_only:
                udev = subprocess.Popen(["udevadm", "monitor", "--kernel", "--subsystem-match=drm"], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
                t_host = time.time()
                v = PORT_CMD[a.to]
                if not (io.write(X.DEV8, 0x01, bytes([TESTCMD >> 8])) and io.write(X.DEV8, 0x03, bytes([v]))
                        and io.write(X.DEV8, 0x3B, bytes([TESTCMD & 0xFF]))):
                    say("switch command write NAKed"); return 1
                deadline = time.monotonic() + a.settle_s
                while time.monotonic() < deadline:           # host-side wait for the firmware; no 0x35 traffic meanwhile
                    time.sleep(0.25)
                udev.terminate()
                ue = [ln for ln in udev.communicate(timeout=2)[0].splitlines() if "change" in ln or "add" in ln or "remove" in ln]
            rio = B.Real(a.read_bus, allow_write=False, regread=True) if a.read_bus not in (None, a.bus) else io
            raw = X.read_blocks(rio, base, 12 + 4 * N_EV)
            if rio is not io:
                rio.close()
            if raw is None:
                say("log read failed (0x35 silent)"); return 1
            hdr, evs = decode(raw)
            say(f"run {run + 1}: switch to {a.to or '-'} seq {hdr['seq']} port {hdr['port']} events {hdr['n']} "
                f"HPD-low D0..D3 {hdr['hpd_low']} hold-blocks {hdr['hold_blocks']}")
            for ms, i, g in evs:
                say(f"  +{ms:5d} ms  {name(i, g)}")
            if udev is not None:
                say(f"  host drm uevents: {len(ue)}" + "".join(f"\n    {u}" for u in ue[:8]))
                j = subprocess.run(["journalctl", "--user", "-b", "--since", f"@{int(t_host)}", "-o", "short-iso", "--no-pager",
                                    "-t", "gnome-shell"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
                say(f"  mutter journal lines: {len(j)}" + "".join(f"\n    {x}" for x in j[:6]))
    finally:
        io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
