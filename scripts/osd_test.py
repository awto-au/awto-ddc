#!/usr/bin/env python3
"""OSD test mode over I2C: raise RTD2014 OSD events / press keys in the RUNNING firmware (no halt, no reflash).

usage: osd_test.py <bus> --serial AWT2611000N --map tmp/fw/<image>.map ACTION [ACTION ...]
  Events (g_stOsdInfo.ucOsdEventMsg): info nosignal nocable nosupport failsafe powersaving-msg source-menu
  Keys   (g_stOsdInfo.ucOsdKeyMessage): menu right left exit
  Offsets/values: RTD2014Include.h (EnumOsdEvent order, _*_KEY_MESSAGE); address from the image's map.
  Writes via rtd_dbg_write.py (debug slave 0x35, EDID-serial guarded). Field offsets: rtd_proto.osd_offsets_from_map (_DP_DEBUG_MSG moves them, #37; unit_health cross-checks the firmware's own report).
  --cmd: write the firmware test byte (g_stAwtoDiag + 0x28, awto-ddc#33) instead: 1..4 = menu/right/left/exit key
    injected after the key scan, 0x10+n = event n. Visuals someone is asked to look at stay up until cleared (#28):
      logo / logo-on = 0x24  boot logo, held (black background)      logo-off = 0x25  logo away, picture back
      debug = 0x26           debug pop-up, held                       clear    = 0x27  every held visual away
      timed (old images): debug-6s = 0x20 (pop-up, _AWTO_INFO_POPUP_SEC, #34), logo-3s = 0x21 (boot logo 3 s, #46).
    0x22/0x23 = message log on/off (wb-msgtable, #56). An image older than #28 ignores 0x24..0x27.
    Held state: g_stAwtoDiag + 0x2F (bit0 logo, bit1 pop-up). Works for keys (the direct key write is overwritten).
Log: ./tmp/logs/rtd_dbg_write.log
"""
import argparse, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTCMD_OFF = 0x28
sys.path.insert(0, str(HERE))
from rtd_proto import OSD_EVENTS as EVENTS, OSD_KEYS as KEYS, osd_offsets_from_map  # noqa: E402  (one table, also decodes the log)
CMD_ONLY = {"debug": 0x26, "debug-6s": 0x20, "logo": 0x24, "logo-on": 0x24, "logo-off": 0x25, "logo-3s": 0x21,
            "clear": 0x27, "msglog-on": 0x22, "msglog-off": 0x23,
            "msg-on": 0x28, "msg-off": 0x29, "auto-search": 0x30, "defaults": 0x40}   # --cmd only (firmware test byte, #33/#28/#56; msg-on/off = NVRAM, #74; auto-search #60; defaults = settings registry #67)
HOLD_MARK = "_AwtoTestHoldLogoOff"                       # in the map = image understands 0x24..0x27 (#28)
OLD_FALLBACK = {0x26: 0x20, 0x24: 0x21}                 # image without holds: timed variants; 0x25/0x27 have none
CONSUME_READS = 8                                      # read-backs (~0.4 s each); main loop clears the byte in one pass, but 0x35 NAKs while it draws the OSD


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
    ofs = osd_offsets_from_map(a.map.read_text(errors="replace"))
    hold = HOLD_MARK in a.map.read_text(errors="replace")
    writes = []
    for act in a.actions:
        if act in CMD_ONLY and not a.cmd:
            sys.exit(f"{act}: needs --cmd")
        kind = "event" if act in EVENTS else "key" if act in KEYS else "popup"
        if a.cmd:
            val = CMD_ONLY.get(act) or ((0x10 + EVENTS[act]) if act in EVENTS else (1 + KEYS[act]))
            if 0x24 <= val <= 0x27 and not hold:
                if val not in OLD_FALLBACK:
                    print(f"osd_test: {act} (0x{val:02X}) needs an image with held visuals (#28; {HOLD_MARK} not in {a.map.name}); skipped")
                    continue
                print(f"osd_test: {a.map.name} has no held visuals (#28): {act} sent as timed 0x{OLD_FALLBACK[val]:02X}")
                val = OLD_FALLBACK[val]
            writes.append((f"{base + TESTCMD_OFF:04X}={val:02X}", f"osd_test {act.upper()} {kind} via ucTestCmd (cmd 0x{val:02X})"))
            continue
        field = "ucOsdEventMsg" if act in EVENTS else "ucOsdKeyMessage"
        off, val = ofs[field], (EVENTS[act] if act in EVENTS else KEYS[act])
        writes.append((f"{base + off:04X}={val:02X}", f"osd_test {act.upper()} {kind} via g_stOsdInfo.{field}={val}"))
    rc = 0
    for w, label in writes:                # one call per action: the firmware consumes each before the next
        rc |= subprocess.call([sys.executable, str(HERE / "rtd_dbg_write.py"), str(a.bus), "--serial", a.serial,
                               "--map", str(a.map), "--label", label, w])
        if a.cmd and rc == 0:
            rc |= consumed(a, w.split("=")[0])
    return rc


def consumed(a, addr: str) -> int:
    """Test byte back to 0 = the main loop applied it; still set = firmware stuck or no #33 handler."""
    for k in range(CONSUME_READS):
        out = subprocess.run([sys.executable, str(HERE / "rtd_dbg_read.py"), str(a.bus),      # read-only; the write was serial-guarded
                              "--map", str(a.map), "0x" + addr], capture_output=True, text=True,
                             timeout=5).stdout       # 1-byte read ~0.4 s incl. interpreter start; 5 s = hung bus, raises
        m = re.search(r"@0x[0-9a-f]+: ([0-9a-f]{2}|--)", out)
        if m and m.group(1) == "00":
            print(f"osd_test: test byte 0x{addr} consumed (read {k + 1})")
            return 0
    print(f"osd_test: test byte 0x{addr} NOT consumed after {CONSUME_READS} reads (last: {out.strip()[-80:]})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
