"""Stand-in for `dev.py flash --direct` in the control-port tests: prints the real flasher's progress lines, no hardware.
usage: fake_flasher.py [--sectors N] [--step S] [--rc RC] [--refuse] (S seconds between sectors)"""
import argparse
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--sectors", type=int, default=6)
ap.add_argument("--step", type=float, default=0.1)
ap.add_argument("--rc", type=int, default=0)
ap.add_argument("--refuse", action="store_true")
a, _rest = ap.parse_known_args()
if a.refuse:
    print("dev.py: image is not gated (fw/.gates.json): refusing; --force-ungated overrides", flush=True)
    sys.exit(3)
print(f"per-sector mode: {a.sectors} sectors, boot/common last", flush=True)
for k in range(a.sectors):
    time.sleep(a.step)
    print(f"written+verified {k + 1}/{a.sectors} sectors ({k}s)", flush=True)
print("burst failures redone in byte mode: 1; ISP recoveries 0; aux-fast pages 0, done-polls 0", flush=True)
sys.exit(a.rc)
