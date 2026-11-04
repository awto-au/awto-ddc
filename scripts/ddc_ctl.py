#!/usr/bin/env python3
"""DDC/CI control of the identical JXC monitors via ddcutil. See docs/ddc-control.md."""
import argparse
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = REPO / "tmp" / "logs" / "ddc_ctl.log"

# Waits for one ddcutil call. Measured 2026-11-04: typical 0.1-0.4 s, worst 1.37 s (getvcp just after power change).
# Limit 4.5 s = ~3x worst. On expiry: log op, limit, elapsed; call fails.
TIMEOUT_S = 4.5

VCP_POWER, VCP_BRIGHT = "0xd6", "0x10"
POWER_STANDBY, POWER_ON = "4", "1"
log = logging.getLogger("ddc_ctl")


def setup_logging():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    for h in (logging.FileHandler(LOG), logging.StreamHandler(sys.stderr)):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def run(args, op):
    """Run ddcutil; return stdout or None on failure/timeout."""
    cmd = ["ddcutil", *args]
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.error("TIMEOUT op=%s limit=%.1fs elapsed=%.2fs cmd=%s", op, TIMEOUT_S, time.monotonic() - t0, " ".join(cmd))
        return None
    dt = time.monotonic() - t0
    if p.returncode != 0:
        log.error("FAIL op=%s rc=%d elapsed=%.2fs err=%s", op, p.returncode, dt, (p.stderr or p.stdout).strip()[:200])
        return None
    log.info("ok op=%s elapsed=%.2fs", op, dt)
    return p.stdout


def detect():
    """Return [{connector, bus, model}] for all displays, resolved at runtime."""
    out = run(["detect", "--brief"], "detect")
    mons = []
    for block in re.split(r"\n(?=Display \d+)", out or ""):
        bus = re.search(r"/dev/i2c-(\d+)", block)
        con = re.search(r"DRM connector:\s+(\S+)", block)
        mod = re.search(r"Monitor:\s+(.+)", block)
        if bus and con:
            mons.append({"connector": con.group(1), "bus": int(bus.group(1)), "model": mod.group(1).strip() if mod else "?"})
    return sorted(mons, key=lambda m: m["connector"])


def select(mons, sel):
    if sel == "all":
        return mons
    pick = [m for m in mons if m["connector"] == sel]
    if not pick:
        log.error("no monitor %r; have %s", sel, [m["connector"] for m in mons])
    return pick


def getvcp(mon, code):
    """Return (current, max, raw_line) or None. Parses `--brief` output."""
    out = run(["--bus", str(mon["bus"]), "getvcp", code, "--brief"], f"get {code} {mon['connector']}")
    if not out:
        return None
    f = out.split()  # VCP 10 C 50 100  |  VCP D6 SNC x01
    if len(f) >= 5 and f[2] == "C":
        return int(f[3]), int(f[4]), out.strip()
    if len(f) >= 4 and f[2] == "SNC":
        return int(f[3].lstrip("x"), 16), None, out.strip()
    log.error("unparsed getvcp output: %r", out)
    return None


def setvcp(mon, code, val):
    # --noverify: ddcutil's read-back check fails on 0xD6 (firmware reads back a different value)
    return run(["--bus", str(mon["bus"]), "setvcp", code, str(val), "--noverify"],
               f"set {code}={val} {mon['connector']}") is not None


def power_cmd(mons, val, name):
    rc = 0
    for m in mons:
        ok = setvcp(m, VCP_POWER, val)
        rb = getvcp(m, VCP_POWER)
        log.info("%s %s bus=%d set_ok=%s readback_sl=%s", name, m["connector"], m["bus"], ok, rb[0] if rb else None)
        rc |= 0 if ok else 1
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for c in ("sleep", "wake"):
        sub.add_parser(c).add_argument("--monitor", default="all")
    b = sub.add_parser("brightness")
    b.add_argument("value", type=int)
    b.add_argument("--monitor", default="all")
    sub.add_parser("get").add_argument("code")
    a = ap.parse_args()

    setup_logging()
    mons = detect()
    if not mons:
        log.error("no monitors detected")
        return 2
    if a.cmd == "list":
        print(f"{'connector':16} {'bus':>3}  {'brightness':>10}  {'power(sl)':9}  model")
        for m in mons:
            br, pw = getvcp(m, VCP_BRIGHT), getvcp(m, VCP_POWER)
            print(f"{m['connector']:16} {m['bus']:>3}  {br[0] if br else '?':>10}  "
                  f"{('0x%02x' % pw[0]) if pw else '?':9}  {m['model']}")
        return 0
    if a.cmd == "get":
        for m in mons:
            r = getvcp(m, a.code)
            print(f"{m['connector']:16} bus={m['bus']:<3} {r[2] if r else 'ERROR'}")
        return 0
    sel = select(mons, a.monitor)
    if not sel:
        return 2
    if a.cmd == "sleep":
        return power_cmd(sel, POWER_STANDBY, "sleep")
    if a.cmd == "wake":
        return power_cmd(sel, POWER_ON, "wake")
    if a.cmd == "brightness":
        if not 0 <= a.value <= 100:
            ap.error("brightness 0-100")
        return 0 if all([setvcp(m, VCP_BRIGHT, a.value) for m in sel]) else 1


if __name__ == "__main__":
    sys.exit(main())
