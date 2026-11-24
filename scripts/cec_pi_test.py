#!/usr/bin/env python3
"""CEC test of the monitor from a Raspberry Pi 5 (runs ON the Pi; docs/cec.md): wraps cec-ctl / cec-compliance, prints a pass / fail table.

usage: python3 cec_pi_test.py [--dev /dev/cec0] [--only NAME[,NAME]] [--compliance] [--no-setup]
  Pi micro-HDMI port -> monitor HDMI input (D2 or D3) with an HDMI cable that carries CEC (pin 13).
  Setup: the Pi becomes a playback device (logical address 4): cec-ctl --playback. The monitor is the TV (logical address 0).
  Each row sends one message to logical address 0 and expects the monitor's reply (or, for logged-only messages, that the
  transmit was acknowledged). The monitor's own view of every frame: `./dev.py synclog` on the PC (rows "CEC rx / tx ...").
- Expected strings are the cec-ctl output tokens (written from the cec-ctl documentation, NOT yet run on a Pi: the first run may need token fixes) (message name + one field); the raw output of every call is kept, a mismatch is
  fixed by reading it: tmp/logs/cec_pi_test.raw.log.
- Not covered by a row (no way to tell from the Pi): that a <Standby> or <Image View On> does NOT change the monitor (cec_ctl off).
Log: ./tmp/logs/cec_pi_test.log (table), ./tmp/logs/cec_pi_test.raw.log (cec-ctl output)
"""
import argparse
import re
import shutil
import subprocess
import sys
import time

import isostamp
from _log import Logger
from _repo import ROOT

LOGDIR = ROOT / "tmp/logs"
# One cec-ctl call: waits up to 1 s for the reply (its default) after up to 5 transmit attempts of ~50 ms; slowest observed
# case is a NACKed poll with retries, about 2 s. 5 s = 2.5x; on expiry the row fails and the raw log says which call.
CALL_TIMEOUT_S = 5
# cec-compliance remote test of one device: ~60 messages, each up to the 1 s reply wait; 120 s = ~2x the sum of waits.
COMPLIANCE_TIMEOUT_S = 120

# name, cec-ctl arguments (after -d DEV), regexes that must all appear in the output
ROWS = [
    ("poll", ["--to", "0", "--poll"], [r"Transmit|Poll"]),
    ("give-physical-addr", ["--to", "0", "--give-physical-addr"], [r"REPORT_PHYSICAL_ADDR", r"phys-addr: 0\.0\.0\.0", r"prim-devtype: tv"]),
    ("give-device-vendor-id", ["--to", "0", "--give-device-vendor-id"], [r"DEVICE_VENDOR_ID", r"0x00a770d0|10973392"]),
    ("get-cec-version", ["--to", "0", "--get-cec-version"], [r"CEC_VERSION", r"version-1-4"]),
    ("give-osd-name", ["--to", "0", "--give-osd-name"], [r"SET_OSD_NAME", r"awto-mon"]),
    ("give-device-power-status", ["--to", "0", "--give-device-power-status"], [r"REPORT_POWER_STATUS", r"pwr-state: on"]),
    ("unsupported opcode -> feature abort", ["--to", "0", "--give-deck-status", "status-req=once"], [r"FEATURE_ABORT", r"unrecognized"]),
    ("active-source (logged only)", ["--active-source", "phys-addr=1.0.0.0"], [r"Transmit"]),
    ("image-view-on (logged only)", ["--to", "0", "--image-view-on"], [r"Transmit"]),
    ("text-view-on (logged only)", ["--to", "0", "--text-view-on"], [r"Transmit"]),
    ("user-control-pressed (logged only)", ["--to", "0", "--user-control-pressed", "ui-cmd=select"], [r"Transmit"]),
    ("user-control-released (logged only)", ["--to", "0", "--user-control-released"], [r"Transmit"]),
    ("standby (logged only; monitor must stay on)", ["--to", "0", "--standby"], [r"Transmit"]),
]
BAD = re.compile(r"Not Acknowledged|Timed out|Max Retries|Arbitration Lost|Low Drive|TIMEOUT|not found", re.IGNORECASE)


def run(cmd, timeout, raw):
    raw.write(f"$ {' '.join(cmd)}\n")
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # rc ignored: output is logged and judged by the case
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") + f"\nTIMEOUT after {timeout} s: {' '.join(cmd)}\n"
    except FileNotFoundError:
        out = f"not found: {cmd[0]}\n"
    raw.write(out + f"[{time.time() - t:.1f} s]\n\n")
    raw.flush()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/cec0")
    ap.add_argument("--only", help="comma separated row names")
    ap.add_argument("--compliance", action="store_true", help="also run cec-compliance against logical address 0")
    ap.add_argument("--no-setup", action="store_true", help="the adapter is already configured as a playback device")
    a = ap.parse_args()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    log, raw = Logger(LOGDIR / "cec_pi_test.log", stamp_file=False, stamp_echo=False), (LOGDIR / "cec_pi_test.raw.log").open("a")
    log.say(f"{isostamp.now()} cec_pi_test {a.dev}")
    if shutil.which("cec-ctl") is None:
        log.say("FAIL cec-ctl not installed (apt install v4l-utils)")
        return 2
    base = ["cec-ctl", "-d", a.dev]
    if not a.no_setup:
        run(base + ["--playback", "--osd-name", "pi5-test"], CALL_TIMEOUT_S, raw)
    topo = run(base + ["-S"], CALL_TIMEOUT_S, raw)
    log.say("topology:\n" + "\n".join("  " + x for x in topo.splitlines()[:30]))
    if not re.search(r"Playback", topo):
        log.say("FAIL the adapter is not a playback device (physical address 0xf.f.f.f = no HDMI link / EDID read failed?)")
    fails = 0
    only = set(a.only.split(",")) if a.only else None
    log.say(f"{'row':44} {'result':6} detail")
    for name, args, want in ROWS:
        if only and name not in only:
            continue
        out = run(base + ["-s"] + args, CALL_TIMEOUT_S, raw)
        miss = [w for w in want if not re.search(w, out)]
        bad = BAD.search(out)
        ok = not miss and not bad
        fails += not ok
        log.say(f"{name:44} {'PASS' if ok else 'FAIL':6} " + ("" if ok else (f"missing {miss}" if miss else f"saw '{bad.group(0)}'")))
    if a.compliance:
        if shutil.which("cec-compliance") is None:
            log.say("compliance: cec-compliance not installed (apt install v4l-utils)")
        else:
            hlp = run(["cec-compliance", "--help"], CALL_TIMEOUT_S, raw)
            m = re.search(r"(--test-remote|--remote-test|-r)\b", hlp)
            if m is None:
                log.say("compliance: no remote-test option in cec-compliance --help; run it by hand (docs/cec.md)")
            else:
                out = run(["cec-compliance", "-d", a.dev, m.group(1), "0"], COMPLIANCE_TIMEOUT_S, raw)
                tot = re.findall(r"Total.*", out)
                log.say("compliance: " + (tot[-1] if tot else "no Total line, see the raw log"))
                fails += bool(re.search(r"Failures?: *[1-9]|fail: *[1-9]", out, re.IGNORECASE))
    log.say(f"{'PASS' if fails == 0 else 'FAIL'} cec_pi_test: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
