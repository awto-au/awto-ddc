#!/usr/bin/env python3
"""#83 pre-fill on hardware: wait for the idle-D1 cache pre-fill after a boot, watch D1, then the first switch to D1.

usage: prefill_hw.py --hdmi-bus 11 --dp-bus 15 --serial S --map MAP [--delay-s 0] [--wait-s 40]
- Run right after `dev.py reset --unit N` with D2 HDMI on screen and D1 DP live (DP-1 mirrored, dev.py mode --dp mirror).
- Links the debug slave onto D2 (dbg_link on), polls D1's cache valid byte + g_ucAwtoPfScans every POLL_S, and the
  host side of the D1 link (DPCD 0x202..0x205 lane status, 0x600 power) via /dev/drm_dp_aux (sudo -n).
- --delay-s after the fill: then one sw_timeline.py --to D1 (test cmd 0x31), log read on the DP bus.
Log: ./tmp/logs/prefill_hw.log
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link  # noqa: E402
import dbg_xdata as X  # noqa: E402
import rtd_i2c_bridge as B  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/prefill_hw.log"
ENTRY = 2 + 48              # StAwtoSwCache: ucValid, ucSourceType, pucScaler[AWTO_FAST_SCALER_BYTES 48]
POLL_S = 0.25               # D1 change resolution; one poll = 2 XDATA reads (~10 ms) + 2 sudo dd
# boot to ACTIVE ~5 s (#83 log 2026-11-08) + 5 tries x AWTO_PF_STEP_MS 2 s + scan 0.5 s = ~16 s; 2.5x as the boot varies
WAIT_S = 40


def log(s: str) -> None:
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def sym(mp: str, name: str) -> int:
    m = re.search(rf"^D:\s+([0-9A-F]{{8}})\s+_{name}\b", mp, re.M)
    if not m:
        sys.exit(f"{name} not in the map: image without #83 pre-fill")
    return int(m.group(1), 16) & 0xFFFF


def aux_dev(conn: str = "card1-DP-1") -> str | None:
    """/dev/drm_dp_auxN of the connector (sysfs device link)."""
    for d in Path(f"/sys/class/drm/{conn}").glob("drm_dp_aux*"):
        return f"/dev/{d.name}"
    for d in Path("/sys/class/drm_dp_aux_dev").iterdir():       # i915 TC port: aux dev not under the connector
        if "TC" in (d / "name").read_text():
            return f"/dev/{d.name}"
    return None


def dpcd(dev: str | None, off: int, n: int) -> str:
    if dev is None:
        return "-"
    r = subprocess.run(["sudo", "-n", "dd", f"if={dev}", "bs=1", f"skip={off}", f"count={n}", "status=none"],
                       capture_output=True, timeout=2, check=False)
    return r.stdout.hex(" ") if r.returncode == 0 else f"rc{r.returncode}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hdmi-bus", type=int, required=True)
    ap.add_argument("--dp-bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--delay-s", type=float, default=0.0)
    ap.add_argument("--wait-s", type=float, default=WAIT_S)
    a = ap.parse_args()
    mp = Path(a.map).read_text(errors="replace")
    cache, scans = sym(mp, "s_pstAwtoSwCache"), sym(mp, "g_ucAwtoPfScans")
    dev = aux_dev()
    t0 = time.monotonic()
    while True:
        try:
            dbg_link.on(a.hdmi_bus, 0xFF)
            break
        except SystemExit:                  # NAK while the unit boots
            pass
        if time.monotonic() - t0 > a.wait_s:
            log(f"no debug link on bus {a.hdmi_bus} after {a.wait_s} s (unit still booting?)")
            return 1
        time.sleep(POLL_S)
    log(f"debug link on bus {a.hdmi_bus} at +{time.monotonic() - t0:.1f} s")
    io = B.Real(a.hdmi_bus, allow_write=False, regread=True)
    last, t_fill = None, None
    try:
        while True:
            now = time.monotonic() - t0
            v = X.read_bytes(io, cache, 2 * ENTRY)
            s = X.read_bytes(io, scans, 1)
            if v is None or s is None:          # a reset drops the debug link (DDC/CI owns D2 after boot): link again
                io.close()
                try:
                    dbg_link.on(a.hdmi_bus, 0xFF)
                except SystemExit:
                    pass
                io = B.Real(a.hdmi_bus, allow_write=False, regread=True)
                cur = last
            else:
                cur = (v[0], v[ENTRY], s[0])
            link = f"DPCD 202..205 {dpcd(dev, 0x202, 4)} 600 {dpcd(dev, 0x600, 1)}"
            if cur != last:
                log(f"+{now:.2f} s: valid D1 {cur[0] if cur else '-'} D2 {cur[1] if cur else '-'} "
                    f"scans {cur[2] if cur else '-'}; {link}")
                last = cur
            if cur and cur[0] == 2 and t_fill is None:
                t_fill = now
            if cur and cur[0] == 1:
                log("D1 valid 1 (full path visited it): not a pre-fill test")
                return 1
            if t_fill is not None and now - t_fill >= a.delay_s:
                log(f"filled at +{t_fill:.2f} s; switching to D1 {now - t_fill:.2f} s later; {link}")
                break
            if t_fill is None and now > a.wait_s:
                log(f"no pre-fill within {a.wait_s} s")
                return 1
            time.sleep(POLL_S)
    finally:
        io.close()
    pre = subprocess.run([sys.executable, str(ROOT / "scripts/sw_timeline.py"), str(a.hdmi_bus), "--serial", a.serial,
                          "--map", a.map, "--read-only"], capture_output=True, text=True, timeout=30).stdout
    log("boot log before the switch:\n" + pre.rstrip())
    out = subprocess.run([sys.executable, str(ROOT / "scripts/sw_timeline.py"), str(a.hdmi_bus), "--serial", a.serial,
                          "--map", a.map, "--to", "D1", "--read-bus", str(a.dp_bus), "--settle-s", "4"],
                         capture_output=True, text=True, timeout=60).stdout
    log("first switch to D1:\n" + out.rstrip())
    return 0 if "FAST path taken" in out else 2


if __name__ == "__main__":
    sys.exit(main())
