#!/usr/bin/env python3
"""Input-switch timeline (#60): switch a unit's input over debug slave 0x35 and decode the firmware's StAwtoSw log.

usage: sw_timeline.py <bus> --serial S --map MAP [--to D1|D2|D3] [--runs N] [--settle-s 8] [--read-only]
  --to: test cmd 0x31..0x33 (fixed port, as VCP 0x60), then read isr_g_stAwtoSw once the unit is ACTIVE again or --settle-s passed.
  --vcp: switch with DDC/CI VCP 0x60 (raw 0x37 on <bus>, as kvm.py) instead of the test cmd; after the settle the
    debug slave is linked onto --read-bus for the read (dbg_link on/off: DDC/CI owns the active port, #79).
  --read-only: decode the current log only. Host side per run: kernel drm uevents (udevadm monitor) and mutter journal lines.
  Events (RL6449_Project.h AWTO_SW_EV_*): 01 mode state, 10 panel power action, 20 T3 wait start/end, 40 switch cmd,
  50/51/52 held-visual guards. Times = firmware d_isr_g_usTimerCounter ms relative to the arm (usT0).
Log: ./tmp/logs/sw_timeline.log (one decoded line per event)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

MODES = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
POWER = {0: "PANEL_ON", 1: "PANEL_OFF", 2: "BACKLIGHT_ON", 3: "BACKLIGHT_OFF"}       # SDK _PANEL_ON.. order (UserCommonInterface)
TESTCMD = 0xF6F8
PORT_CMD = {"D1": 0x31, "D2": 0x32, "D3": 0x33}
PORT_VCP = {"D1": 0x0F, "D2": 0x11, "D3": 0x12}      # MCCS 0x60 values (kvm.py PORTS)
N_EV = 64                   # AWTO_SW_EVENTS (40 before #78); an older image just returns spare bytes
PROBES = {1: "reset-to-SEARCH start", 2: "SysModeResetState done", 3: "judge SEARCH refused (retry)", 4: "OSD reset proc done",
          5: "free run done", 6: "SysSourceSwitchInputPort done", 7: "active proc: NVRAM system-data save start",
          8: "active proc: NVRAM save done", 9: "OSD info pop-up draw start", 10: "OSD info pop-up drawn",
          11: "first active: ScalerGlobalFirstActiveProc done", 12: "first active: OSD active proc + backlight done (SysSourceFirstActiveProc next)",
          14: "display setting start", 15: "display setting done (colour next)",
          16: "colour proc done (setting ready)", 17: "measure start", 18: "measure done (timing confirmed)",
          19: "source judged (port found)", 20: "judge check FAIL: source unstable", 21: "judge check FAIL: timing change",
          22: "judge check FAIL: interlace", 23: "judge check FAIL: M-domain memory / timing gen",
          24: "eDP: panel VDD on", 25: "eDP: L2 link-only wake: PHY init", 26: "eDP: panel HPD high (T2 poll returned)",
          27: "eDP: link trained", 28: "eDP: link training FAIL"}       # AWTO_SW_EV_PROBE sites (#60, keil2sdcc)
MARKS = {0: "DDC/CI + colour + ScalerDebug (pass tail)", 1: "key+diag+testcmd", 2: "SysPowerHandler", 3: "SysJudgeHandler",
         4: "SysTimerHandler", 5: "SysSourceHandler (rest: judge)", 6: "SysModeHandler", 7: "SysDpRxHandler",
         8: "SysTMDSRxHandler", 9: "HDCP2 / MST", 10: "OSD handler",
         20: "source: cable detect + SwitchPort", 21: "source: SysSourceScanPortInitial", 22: "source: SearchTimeInitial",
         23: "source: SysSourceDetectPort", 30: "DP Rx1: predetect .. scramble", 31: "DP Rx1: HdcpCheck",
         32: "DP Rx1: GetVideoStream", 33: "DP Rx1: MSACheck", 34: "DP Rx1: GetVideoInfo", 35: "DP Rx1: DisplayFormatSetting",
         36: "DP Rx1: StreamClkRegenerate", 37: "DP Rx1: FifoCheck (+ vsync adjust)"}           # AWTO_SW_EV_SLOW: segment that ENDS at mark k (keil2sdcc AWTO_SW_MARK)


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
    if ev_id == 0x90:
        return f"probe {PROBES.get(arg, arg)}"
    if ev_id == 0x92:
        return f"MODE RESET set before mark {arg}: {MARKS.get(arg, '?')}"
    if ev_id == 0x91:
        return f"SLOW >= 20 ms before mark {arg}: {MARKS.get(arg, '?')}"
    if ev_id == 0xA0:
        return "FAST " + {0: "path taken (mux switched, blanked)", 1: "refused: no cache for the port", 6: "refused: mode not ACTIVE",
                          7: "refused: a fast switch is pending", 8: "refused: already on that port", 9: "refused: mode reset pending",
                          10: "refused: Fast switch setting off (#67)",
                          3: "refused: receiver not stable", 4: "dropped: SDK reset the mode", 5: "measure timeout -> full path",
                          0x21: "refused: H/V width", 0x22: "refused: H/V total", 0x23: "refused: H start", 0x24: "refused: V start",
                          0x25: "refused: interlace", 0x26: "refused: V freq", 0x27: "refused: pixel clock",
                          0x28: "refused: colour info"}.get(arg, str(arg))
    if ev_id == 0xA2:
        bits = [n for b, n in ((0x40, "input HV-sync error 6"), (0x20, "input HV-sync error 5"), (0x02, "FIFO overflow"),
                               (0x01, "FIFO underflow"), (0x80, "watchdog")) if arg & b]
        return f"FAST post-unblank M-domain flags 0x{arg:02X}: " + ", ".join(bits)
    if ev_id == 0xA1:
        why = [n for b, n in ((1, "off-line measure busy"), (2, "on-line watchdog"), (4, "FIFO / HV-sync error"),
                              (8, "receiver unstable"), (0x10, "timing change"), (0x20, "SysJudgeCheckStatus")) if arg & b]
        return "FAST failed checks: " + (", ".join(why) or "none")
    if ev_id == 0xA8:
        return "HOLD " + {1: "L1: signal lost, set-up held, backlight off", 2: "L2: eDP link off (VDD on)", 3: "L3: released to SDK power saving",
                          4: "tries used up: full path", 5: "receiver stable again: fast wake", 6: "backlight / panel on (wake)",
                          7: "fast wake timed out: back to hold", 8: "clock back (pre-detect), SDK scan next",
                          9: "auto search: another port has a signal, released", 0x10: "SDK reset the mode meanwhile"}.get(arg, str(arg))
    if ev_id == 0xB8:
        return "DEAD PORT (#84) " + {1: "key / VCP 0x60 to a port with no cable: refused", 2: "key next input: no other cabled port",
                                     3: "fixed port, no cable, no signal: back to auto search"}.get(arg, str(arg))
    if ev_id == 0xB9:
        return "PREFILL (#83) D1 " + {1: "filled (cache valid 2)", 2: "pre-detect false", 3: "scan not DP", 4: "not stable",
                                      5: "pixel clock differs > 1 %"}.get(arg, str(arg))
    if ev_id == 0xB0:
        return f"HPD recovery pulse on D{arg} (host lost SCDC / link: #78)"
    if ev_id == 0x80 and arg == 0:
        return "UNBLANK (picture on)"
    return {0x50: "hold: disable blocked", 0x51: "hold: logo redrawn", 0x52: "hold: OSD event dropped", 0x60: "logo",
            0x70: "panel VDD early", 0x80: "blank instead of backlight off"}.get(ev_id, f"ev 0x{ev_id:02X}") + f" ({arg})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--to", choices=sorted(PORT_CMD))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--settle-s", type=float, default=8.0, help="read the log this long after the switch (DP search 3 s + display setting)")
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--vcp", action="store_true", help="switch via DDC/CI VCP 0x60 instead of test cmd 0x31..0x33")
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
    base = sym(a.map, "isr_g_stAwtoSw")
    if a.vcp:
        if a.read_only or a.runs != 1:
            sys.exit("--vcp: one switch per call (the log is read over a re-linked debug slave)")
        rbus = a.read_bus if a.read_bus is not None else a.bus
        t_host = time.time()
        dbg_link._setvcp(a.bus, 0x60, 0x00, PORT_VCP[a.to])
        deadline = time.monotonic() + a.settle_s
        while time.monotonic() < deadline:            # host-side wait: switch + info pop-up (main loop busy ~0.5 s)
            time.sleep(0.25)
        with dbg_link.linked(rbus, 2):
            rio = B.Real(rbus, allow_write=False, regread=True)
            for _ in range(3):                      # a read right after the link sometimes fails once (2026-11-08)
                raw = X.read_blocks(rio, base, 12 + 4 * N_EV)
                if raw is not None:
                    break
            rio.close()
        if raw is None:
            say("log read failed (0x35 silent)"); return 1
        hdr, evs = decode(raw)
        say(f"vcp 0x60 switch to {a.to} seq {hdr['seq']} port {hdr['port']} events {hdr['n']} HPD-low D0..D3 {hdr['hpd_low']}")
        for ms, i, g in evs:
            say(f"  +{ms:5d} ms  {name(i, g)}")
        return 0
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
