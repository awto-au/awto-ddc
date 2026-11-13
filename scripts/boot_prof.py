#!/usr/bin/env python3
"""Boot profile (awto-ddc#144): decode the switch log (StAwtoSw) of a power-up, with the boot probe names and deltas.

usage: boot_prof.py BUS --serial S --map MAP [--power-key] [--main /mnt/2tb/git/awto-ddc]
- --power-key: test cmd 0x3E twice (soft off, wait OFF_S, soft on, wait ON_S); the second press re-arms the log, so the
  printout is the POWER-key power-on path (times relative to that press).
- Run after a cold boot (hass_power.py cycle): links the debug slave (dbg_link), reads isr_g_stAwtoSw, prints
  `+ms  (delta)  event`. Probe sites: AWTO_BPROF(k) in fw/sdk (SysMain.c, SysPower.c, UserCommonInterface.c, RTD2014Osd.c), RL6449_Project.h.
- Uses sw_timeline.py / dbg_link.py of the main repo (--main or $AWTO_DDC_MAIN).
Log: ./tmp/logs/boot_prof.log
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/boot_prof.log"
POWER_ACTIONS = ["OFF_TO_NORMAL", "OFF_TO_FAKE_OFF", "AC_ON_TO_NORMAL", "AC_ON_TO_OFF", "AC_ON_INITIAL", "PS_TO_NORMAL", "PS_TO_OFF",
                 "NORMAL_TO_PS", "NORMAL_TO_OFF", "NORMAL_TO_FAKE_OFF", "SWITCH_INTERFACE_TO_OFF", "NORMAL_TO_FAKE_PS",
                 "FAKE_PS_TO_NORMAL", "FAKE_OFF_TO_NORMAL"]
BOOT_PROBES = {0x30: "TimerEvent init done, UserCommonInterfaceInitial next", 0x31: "UserCommonInterfaceInitial done (NVRAM, DDC/CI)",
               0x32: "ScalerMcuDdcRamEnable done", 0x33: "SysSourceInitial done", 0x34: "SysPowerInitial done = SysMainSystemInitial end",
               0x35: "SysPowerInitial: whole chip reset done", 0x36: "SysPowerInitial: IOSC trimming done",
               0x37: "SysPowerInitial: LDO done, EDID load next", 0x38: "SysPowerInitial: EDID loaded, HDCP key next",
               0x39: "SysPowerInitial: HDCP key + DP D0 init done", 0x3A: "SysPowerInitial: DP init done",
               0x3B: "OSD flow: mode INITIAL entered (console + panel next)", 0x3C: "UserInterfaceInitial done (NVRAM load)"}


OFF_S = 4.0   # soft off: panel off sequence + T6 (panel_t6 in the registry) + settle; fw ms scale is 100s of ms, 4 s = ample
ON_S = 6.0    # power-key on -> ACTIVE took < 2.5 s before this work; 6 s = 2.4x


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--power-key", action="store_true")
    ap.add_argument("--main", type=Path, default=Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc")))
    a = ap.parse_args()
    sys.path.insert(0, str(a.main / "scripts"))
    import dbg_link  # noqa: E402
    import dbg_xdata as X  # noqa: E402
    import i2cbus  # noqa: E402
    import rtd_i2c_bridge as B  # noqa: E402
    import sw_timeline as T  # noqa: E402

    i2cbus.require_unit(a.bus, a.serial)
    base = T.sym(a.map, "isr_g_stAwtoSw")
    raw = None
    with dbg_link.linked(a.bus, 2):
        rio = B.Real(a.bus, allow_write=a.power_key, regread=True)
        if a.power_key:
            for n, wait_s in enumerate((OFF_S, ON_S)):
                if not (rio.write(X.DEV8, 0x01, bytes([T.TESTCMD >> 8])) and rio.write(X.DEV8, 0x03, bytes([0x3E]))
                        and rio.write(X.DEV8, 0x3B, bytes([T.TESTCMD & 0xFF]))):
                    say("test cmd 0x3E write NAKed")
                    return 1
                say(f"POWER key press {n + 1} sent")
                time.sleep(wait_s)
        for _ in range(3):
            raw = X.read_blocks(rio, base, 12 + 4 * T.N_EV)
            if raw is not None:
                break
        rio.close()
    if raw is None:
        say("log read failed (0x35 silent)")
        return 1
    hdr, evs = T.decode(raw)
    say(f"switch log: {hdr['n']} events, t0 {hdr['t0']}")
    prev = 0
    for ms, i, g in evs:
        if i == 0x90 and g in BOOT_PROBES:
            txt = f"probe {BOOT_PROBES[g]}"
        elif i == 0x90 and 0x40 <= g < 0x60:
            act = POWER_ACTIONS[(g & 0x0F) if (g & 0x0F) < len(POWER_ACTIONS) else 0]
            txt = f"SysPowerSwitch {'enter' if g < 0x50 else 'return'} {act}"
        elif i == 0x10 and g >= 4:
            txt = "panel call " + ["panel on", "panel off", "backlight on", "backlight off"][(g - 4) // 2] + (" requested (already)" if g & 1 else " requested")
        else:
            txt = T.name(i, g)
        say(f"  +{ms:5d} ms ({ms - prev:+5d})  {txt}")
        prev = ms
    return 0


if __name__ == "__main__":
    sys.exit(main())
