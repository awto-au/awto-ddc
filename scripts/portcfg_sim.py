#!/usr/bin/env python3
"""#81 port disable (registry d1_enable..d3_enable) in the fw_sim model: a disabled port never raises HPD, is never searched,
the selector shows it and re-enables it on a take, the input on screen cannot be disabled.

usage: portcfg_sim.py BIN MAP [--secs 10]
  Board: HDMI source on D3; D2 cabled, no source; D1 cabled (sim pins), no source. Search order D2 D1 D3.
  Stored D1 off: set_get(d1_enable) answers 0 until the selector step (fw_sim models no flash writes, so a stored value cannot
  survive a sim reboot; the unit test covers the real store).
  --control: D1 left on, boot only: prints the D1 scans / HPD writes the checks below must not see.
  Checks:
    boot     line "D1 disabled by setting (stored)", ACTIVE on D3, D1 HPD (FE02) never written high, D1 never scanned
             (SysSourceScanPortInitial), DDC1 channel enable bit (DDC1_DDC_ENABLE bit 0) clear, isr_g_ucAwtoPortOff = D1 bit
    auto     AUTO key: auto search again, ACTIVE on D3, D1 still never scanned or raised
    veto     test cmd 0x08 (disable D3, on screen): refused line, mask unchanged
    select   SOURCE, UP (row D1), AUTO: line "D1 enabled by the input selector", mask clear, DDC1 bit set
    disable  test cmd 0x06 while D1 is the fixed input without signal: disabled line, HPD written low, back to ACTIVE on D3,
             no D1 HPD high after the disable
Log: tmp/logs/portcfg_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import sync_log as SL  # noqa: E402

D1, D2, D3 = 4, 5, 6                    # Global.h _D1.._D3_INPUT_PORT
SET_D1_ENABLE = 36                      # registry id d1_enable (AwtoSetIds.h)
TESTCMD = 0xF6F8                        # isr_g_stAwtoDiag + 0x28
TC_D1_OFF, TC_D3_OFF = 0x06, 0x08       # fw/test/testcmd.c AWTO_TC_PORT_OFF + port index
HPD_D1 = 0xFE02                         # bD1_HPD = MCU_FE02_PORT42_PIN_REG (board header)
DDC1_DDC_ENABLE, DDC_EN = 0xFF2C, 0x01  # regdb DDC1_DDC_ENABLE bit 0 ddc1_ddc_en
EV_PORT = 0xE1                          # sync.tsv E1: arg = AWTO_PORT_WHY_* (E0 = the input selector)
WHY = {1: "boot", 2: "off", 3: "on", 4: "selector", 5: "select", 6: "on screen", 7: "last", 8: "wake", 9: "already off",
       10: "already on", 11: "fixed->auto"}
A0, A1, IDLE = 0xFF09, 0xFF0A, 0xF8     # key ADC cells (deadport_sim.py)
KEY_SOURCE, KEY_UP, KEY_AUTO, KEY_MENU = (A1, 0x80), (A0, 0x38), (A0, 0x80), (A0, 0xD0)


class HpdWatch(S.Dev):
    """D1 HPD pin writes (value written, firmware ms)."""
    writes = (HPD_D1,)

    def __init__(self):
        self.log = []

    def on_write(self, m, a):
        self.log.append(m.rd(HPD_D1)[0] & 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--secs", type=float, default=10.0, help="settle time after each step (search 2-3 s per port, x ~3)")
    ap.add_argument("--control", action="store_true", help="D1 enabled: boot only, print D1 scans / HPD writes (shows the checks can fail)")
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (S.ROOT / "tmp/logs/portcfg_sim.log").open("a", buffering=1)
    fails = []

    def say(s):
        print(s, flush=True); lf.write(s + "\n")

    def check(name, ok, detail=""):
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
        if not ok:
            fails.append(name)

    hpd = HpdWatch()
    bus = S.SimBus(a.bin, a.map, video="1080p60", port="D3", devs=[hpd], boot=False)
    m = bus.m
    stored_off = [not a.control]
    lines, scans = [], []

    def set_get(m_, r):
        if stored_off[0] and (r["a1"] & 0xFF) == SET_D1_ENABLE:
            return {"val": 0}
        return None

    def push(m_, r):
        if (r["a1"] & 0xFF) == EV_PORT:
            lines.append((r["a2"], round(bus.now(), 3)))
        return None

    def scan(m_, r):
        pri = m_.rd(m_.addr("g_pucSourceSearchPriority"), 10)
        scans.append(pri[(r["a1"] & 0xFF) % 10])
        return None

    m.stub("set_get", set_get)
    m.stub("AwtoSyncPush", push)
    m.stub("SysSourceScanPortInitial", scan)

    def tap(key, ms=150, gap=0.4):
        m.wr(key[0], bytes([key[1]])); bus.wait(ms / 1000.0)
        m.wr(key[0], bytes([IDLE])); bus.wait(gap)

    def close_console():
        if bus.m.rd(bus.addr("g_stAwtoGpio") + 3)[0] | bus.m.rd(bus.addr("g_stAwtoKey") + 3)[0]:
            tap(KEY_MENU)                       # the sync console opened by itself: MENU closes it (deadport_sim.py)

    def port_now():
        pri = bus.xdata(bus.addr("g_pucSourceSearchPriority"), 10)
        return pri[bus.xdata(bus.addr("g_ucSearchIndex"))[0] % 10]

    def off_mask():
        return bus.xdata(bus.addr("isr_g_ucAwtoPortOff"))[0]

    def whys(since=0):
        return [WHY.get(w, w) for w, _ in lines[since:]]

    def settle(want_mode=3, want_port=D3):
        t0 = bus.now()
        while bus.now() - t0 < a.secs:
            bus.wait(0.25)
            if bus.mode_state() == want_mode and port_now() == want_port:
                return round(bus.now() - t0, 2)
        return None

    try:
        bus.boot()
        bus.dbg_link_on()
        t = settle()
        if a.control:
            say(f"control (D1 on): ACTIVE in {t} s, scanned {[hex(p) for p in scans]}, D1 HPD writes {hpd.log}")
            return 0
        check("boot:ACTIVE on D3", t is not None, f"mode {bus.mode_state()} port 0x{port_now():02X} at {bus.now():.2f} s")
        check("boot:stored-off line", "boot" in whys(), f"lines {whys()}")
        check("boot:D1 HPD never high", 1 not in hpd.log, f"FE02 writes {hpd.log}")
        check("boot:D1 never scanned", D1 not in scans, f"scanned ports {[hex(p) for p in scans]}")
        check("boot:DDC1 EDID channel off", (bus.xdata(DDC1_DDC_ENABLE)[0] & DDC_EN) == 0, f"0x{bus.xdata(DDC1_DDC_ENABLE)[0]:02X}")
        check("boot:mask", off_mask() == 1 << (D1 - 3), f"isr_g_ucAwtoPortOff 0x{off_mask():02X}")

        close_console()
        n_scan, n_hpd = len(scans), len(hpd.log)
        tap(KEY_AUTO)
        bus.wait(1.0)
        t = settle()
        check("auto: ACTIVE on D3", t is not None, f"mode {bus.mode_state()} port 0x{port_now():02X}")
        check("auto: D3 rescanned, D1 not", D1 not in scans[n_scan:] and len(scans) > n_scan, f"scans {[hex(p) for p in scans[n_scan:]]}")
        check("auto: D1 HPD never high", 1 not in hpd.log[n_hpd:], f"FE02 writes {hpd.log[n_hpd:]}")

        n = len(lines)
        m.wr(TESTCMD, bytes([TC_D3_OFF])); bus.wait(0.5)
        check("veto: D3 on screen refused", "on screen" in whys(n) and off_mask() == 1 << (D1 - 3), f"lines {whys(n)} mask 0x{off_mask():02X}")

        n = len(lines)
        stored_off[0] = False                   # from here the registry row is the firmware's own value
        close_console()
        tap(KEY_SOURCE)
        tap(KEY_UP)
        tap(KEY_AUTO)
        bus.wait(1.0)
        check("select: enabled by the selector", "selector" in whys(n) and off_mask() == 0, f"lines {whys(n)} mask 0x{off_mask():02X}")
        check("select: DDC1 EDID channel on", (bus.xdata(DDC1_DDC_ENABLE)[0] & DDC_EN) != 0, f"0x{bus.xdata(DDC1_DDC_ENABLE)[0]:02X}")
        check("select: switched to D1", port_now() == D1, f"port 0x{port_now():02X} mode {bus.mode_state()}")
        say(f"  select: D1 HPD writes after the take {hpd.log[n_hpd:]}")

        bus.wait(3.0)                           # D1 fixed, no DP source: NOSIGNAL (not on screen)
        n, n_hpd = len(lines), len(hpd.log)
        m.wr(TESTCMD, bytes([TC_D1_OFF])); bus.wait(0.5)
        check("disable: line + mask", "off" in whys(n) and off_mask() == 1 << (D1 - 3), f"lines {whys(n)} mask 0x{off_mask():02X}")
        check("disable: HPD low written", 0 in hpd.log[n_hpd:], f"FE02 writes {hpd.log[n_hpd:]}")
        t = settle()
        check("disable: back to ACTIVE on D3", t is not None, f"mode {bus.mode_state()} port 0x{port_now():02X} in {t} s")
        check("disable: D1 HPD never high after", 1 not in hpd.log[n_hpd:], f"FE02 writes {hpd.log[n_hpd:]}")
        say(f"  all port lines: {[(WHY.get(w, w), t) for w, t in lines]}")
    finally:
        bus.close()
    say(f"portcfg_sim {a.bin.name}: {'PASS' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
