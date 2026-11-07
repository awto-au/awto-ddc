#!/usr/bin/env python3
"""Offline gates for one or more images (awto-sdcc#25 --keil-compat A/B): fw_sim boot-check, isr-check, fw_link_check,
health --sim at 1080p60 / 2160p60 / 2160p59.94. One line per gate per image; full output in the log.

usage: kc_gates.py [--tools DIR] IMAGE_STEM [IMAGE_STEM ...]     (<stem>.bin + <stem>.map)
  --tools: awto-ddc checkout whose scripts/ run the gates (default $AWTO_DDC_TOOLS or this repo); main has fw_link_check.
Log: tmp/logs/kc_gates.log
"""
import argparse, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
GATE_TMO = 1800   # s, backstop: the slowest gate (health --sim 2160p) takes minutes; ucsim budgets end a hang first
MODES = {"1080p60": "1920x1080@60", "2160p60": "3840x2160@60", "2160p59.94": "3840x2160@59.94"}


def gates(tools: Path, b: Path, m: Path):
    py, s = sys.executable, tools / "scripts"
    yield "boot-check", [py, s / "fw_sim.py", "--boot-check", b, m, "--be"]
    yield "isr-check", [py, s / "fw_sim.py", "--isr-check", b, m]
    yield "link-check", [py, s / "fw_link_check.py", "--bin", b, "--map", m]
    for name, mode in MODES.items():
        yield f"health {name}", [py, s / "unit_health.py", "--sim", b, m, "--host-mode", mode]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default=os.environ.get("AWTO_DDC_TOOLS", str(ROOT)))
    ap.add_argument("stems", nargs="+")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/kc_gates.log").open("a", buffering=1)
    bad = 0
    for stem in a.stems:
        b = Path(stem).with_suffix(".bin").resolve()
        m = b.with_suffix(".map")
        for name, cmd in gates(Path(a.tools), b, m):
            t0 = time.monotonic()
            try:
                r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=GATE_TMO,
                                   cwd=a.tools, env=dict(os.environ, AWTO_DDC_REPO=a.tools))
                out, rc = r.stdout + r.stderr, r.returncode
            except subprocess.TimeoutExpired:
                out, rc = f"TIMEOUT after {GATE_TMO} s", 124
            log.write(f"== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} {b.name} {name} rc={rc} {time.monotonic() - t0:.0f}s\n{out}\n")
            tail = [l for l in out.strip().splitlines() if l.strip()][-1:] or [""]
            print(f"{'PASS' if rc == 0 else 'FAIL'} {b.stem:40s} {name:18s} {tail[0][:160]}", flush=True)
            bad += rc != 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
