#!/usr/bin/env python3
"""Visible KVM fast-switch demo on one unit: VCP 0x60 D2 <-> D1, info pop-up after each switch, timing per switch.

usage: kvm_demo.py [--unit 2] [--rounds 3] [--hold-s 4]
- Needs a live signal on both inputs (e.g. `dev.py mode --unit 2 --dp mirror`): same picture, so the pop-up shows the input.
- Switch: scripts/kvm.py (monitor side, VCP 0x60; no host output changes). Pop-up: dev.py osd info.
Log: ./tmp/logs/kvm_demo.log
"""
import argparse, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)
LOG = ROOT / "tmp" / "logs" / "kvm_demo.log"
STEP_LIMIT_S = 15   # one kvm.py / osd call: worst seen ~0.7 s + bus scan; 15 s = backstop, expiry = demo stops with the step named


def log(s: str):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run(cmd: list) -> tuple[int, float, str]:
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=STEP_LIMIT_S)
    except subprocess.TimeoutExpired:
        return -1, time.monotonic() - t0, f"timeout after {STEP_LIMIT_S} s"
    return r.returncode, time.monotonic() - t0, (r.stdout + r.stderr).strip().splitlines()[-1:][0] if (r.stdout + r.stderr).strip() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="2")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--hold-s", type=float, default=4.0, help="pause after each switch so a person can see it (demo only)")
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    for i in range(a.rounds):
        for port in ("dp", "hdmi1"):
            rc, dt, last = run([sys.executable, str(HERE / "kvm.py"), port, "--units", a.unit])
            log(f"round {i + 1}: switch -> {port}: rc={rc}, host call {dt * 1000:.0f} ms; {last}")
            if rc != 0:
                return 1
            rc, _, last = run([sys.executable, str(ROOT / "dev.py"), "osd", "--unit", a.unit, "info"])
            log(f"round {i + 1}: info pop-up rc={rc}; {last}")
            time.sleep(a.hold_s)   # demo pause for the viewer, not a wait on hardware
    log("demo done: unit on D2 HDMI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
