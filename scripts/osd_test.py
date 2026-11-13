#!/usr/bin/env python3
"""OSD test mode over I2C: raise RTD2014 OSD events / press keys in the RUNNING firmware (no halt, no reflash).

usage: osd_test.py <bus> --serial AWT2611000N --map tmp/fw/<image>.map ACTION [ACTION ...]
  Events (g_stOsdInfo.ucOsdEventMsg): info nosignal nocable nosupport failsafe powersaving-msg source-menu
  Keys   (g_stOsdInfo.ucOsdKeyMessage): menu right left exit
  Offsets/values: RTD2014Include.h (EnumOsdEvent order, _*_KEY_MESSAGE); address from the image's map.
  Writes via rtd_dbg_write.py (debug slave 0x35, EDID-serial guarded). Field offsets: rtd_proto.osd_offsets_from_map (_DP_DEBUG_MSG moves them, #37; unit_health cross-checks the firmware's own report).
  --cmd: write the firmware test byte (g_stAwtoDiag + 0x28, awto-ddc#33) instead: 1..4 = menu/right/left/exit key
    injected after the key scan, 0x10+n = event n (n<16; n>=16 at 0x70+n-16). Visuals someone is asked to look at stay up until cleared (#28):
      debug = 0x26           debug pop-up (console), held             clear    = 0x27  every held visual away
      demo-log = 0x3A  console + 100 log lines 'line N test 1234567890...' 5ms apart (every third wraps)
      timed (old images): debug-6s = 0x20 (pop-up, _AWTO_INFO_POPUP_SEC, #34). Boot logo cmds 0x21 / 0x24 / 0x25: gone (#144).
    0x22/0x23 = message log on/off (wb-msgtable, #56). An image older than #28 ignores 0x26 / 0x27.
    Held state: g_stAwtoDiag + 0x2F (bit1 pop-up). Works for keys (the direct key write is overwritten).
Log: ./tmp/logs/rtd_dbg_write.log
"""
import argparse, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTCMD_OFF = 0x28
sys.path.insert(0, str(HERE))
from rtd_proto import OSD_EVENTS as EVENTS, event_cmd, OSD_KEYS as KEYS, osd_offsets_from_map  # noqa: E402  (one table, also decodes the log)
CMD_ONLY = {"debug": 0x26, "debug-6s": 0x20,
            "clear": 0x27, "msglog-on": 0x22, "msglog-off": 0x23, "demo-log": 0x3A,
            "msg-on": 0x28, "msg-off": 0x29, "auto-search": 0x30, "defaults": 0x40,
            "keytest": 0x41, "keytest-off": 0x42, "gpio": 0x43, "gpio-off": 0x44, "probe": 0x45, "probe-off": 0x46, "scale1": 0x4A, "scale2": 0x4B, "scroll": 0x47, "scroll-reset": 0x48,
            # diagnostic-screen font n (osd_font_load index): 0x60 + n; probe-N = limit probe with N numbered lines (0x80 + N)
            **{f"font{n}": 0x60 + n for n in range(7)}, **{f"cols{c}": 0xC0 + c // 4 for c in (36, 64, 80, 96, 120, 128, 160)}, **{f"probe{n}": 0x80 + n for n in (16, 24, 28, 32, 36, 40, 42, 48, 56, 58, 60, 62, 63, 72, 90)},
            # 0x50 + EnumOSDDispMsg: direct, held visual-review paths in current firmware.
            "card-nosignal": 0x50, "card-nocable": 0x51, "card-nosupport": 0x52,
            "auto-adjust": 0x54, "auto-colour": 0x56, "ddcci-port": 0x57, "power-saving": 0x58,
            "panel-uniformity": 0x59}   # --cmd only (firmware test byte); freeze is compiled out on this board
HOLD_MARK = "_AwtoHoldBlocksDisable"                     # in the map = image understands 0x26 / 0x27 (#28)
OLD_FALLBACK = {0x26: 0x20}                             # image without holds: timed variant; 0x27 has none
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
            val = CMD_ONLY.get(act) or (event_cmd(EVENTS[act]) if act in EVENTS else (1 + KEYS[act]))
            if val in (0x26, 0x27) and not hold:
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
