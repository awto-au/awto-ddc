#!/usr/bin/env python3
"""OSD test mode over I2C: raise RTD2014 OSD events / press keys in the RUNNING firmware (no halt, no reflash).

usage: osd_test.py <bus> --serial AWT2611000N --map tmp/fw/<image>.map ACTION [ACTION ...]
  Events (g_stOsdInfo.ucOsdEventMsg = +5): info nosignal nocable nosupport failsafe powersaving-msg source-menu
  Keys   (g_stOsdInfo.ucOsdKeyMessage = +6): menu right left exit
  Offsets/values: RTD2014Include.h (EnumOsdEvent order, _*_KEY_MESSAGE); address from the image's map.
  Writes via rtd_dbg_write.py (debug slave 0x35, EDID-serial guarded). Struct layout assumes _DP_DEBUG_MSG off.
  --cmd: write the firmware test byte (g_stAwtoDiag + 0x28, awto-ddc#33) instead: 1..4 = menu/right/left/exit key
    injected after the key scan, 0x10+n = event n, `debug` = 0x20 = debug pop-up (awto-ddc#34),
    `logo` = 0x21 = redraw the boot logo for 3 s (awto-ddc#46).
    Works for keys (the direct key write is overwritten).
Log: ./tmp/logs/rtd_dbg_write.log
"""
import argparse, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVENT_OFF, KEY_OFF = 5, 6
TESTCMD_OFF = 0x28
sys.path.insert(0, str(HERE))
from rtd_proto import OSD_EVENTS as EVENTS, OSD_KEYS as KEYS  # noqa: E402  (one table, also decodes the log)
CMD_ONLY = {"debug": 0x20, "logo": 0x21}                  # --cmd only


def osdinfo_addr(map_path: Path) -> int:
    m = re.search(r"([0-9A-F]{8})\s+_g_stOsdInfo\b", map_path.read_text(errors="replace"))
    if not m:
        sys.exit(f"_g_stOsdInfo not in {map_path}")
    return int(m.group(1), 16) & 0xFFFF


def diag_addr(map_path: Path) -> int:
    m = re.search(r"([0-9A-F]{8})\s+_g_stAwtoDiag\b", map_path.read_text(errors="replace"))
    if not m:
        sys.exit(f"_g_stAwtoDiag not in {map_path}")
    return int(m.group(1), 16) & 0xFFFF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--cmd", action="store_true", help="use the firmware test-command byte (needs an image with #33)")
    ap.add_argument("actions", nargs="+", choices=sorted(EVENTS) + sorted(KEYS) + sorted(CMD_ONLY))
    a = ap.parse_args()
    base = diag_addr(a.map) if a.cmd else osdinfo_addr(a.map)
    writes = []
    for act in a.actions:
        if act in CMD_ONLY and not a.cmd:
            sys.exit(f"{act}: needs --cmd")
        kind = "event" if act in EVENTS else "key" if act in KEYS else "popup"
        if a.cmd:
            val = CMD_ONLY.get(act) or ((0x10 + EVENTS[act]) if act in EVENTS else (1 + KEYS[act]))
            writes.append((f"{base + TESTCMD_OFF:04X}={val:02X}", f"osd_test {act.upper()} {kind} via ucTestCmd (cmd 0x{val:02X})"))
            continue
        off, val = (EVENT_OFF, EVENTS[act]) if act in EVENTS else (KEY_OFF, KEYS[act])
        field = "ucOsdEventMsg" if act in EVENTS else "ucOsdKeyMessage"
        writes.append((f"{base + off:04X}={val:02X}", f"osd_test {act.upper()} {kind} via g_stOsdInfo.{field}={val}"))
    rc = 0
    for w, label in writes:                # one call per action: the firmware consumes each before the next
        rc |= subprocess.call([sys.executable, str(HERE / "rtd_dbg_write.py"), str(a.bus), "--serial", a.serial,
                               "--map", str(a.map), "--label", label, w])
    return rc


if __name__ == "__main__":
    sys.exit(main())
