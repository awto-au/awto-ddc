#!/usr/bin/env python3
"""NVRAM flush count for a burst of setting changes on one unit (awto-ddc#151).

Usage: ./scripts/nv_burst.py --unit N [--count 20] [--row osd_transparency] [--label TEXT]
- Marks the sync log with a host note, sets the row to alternating values via ./dev.py gui (one call each, as fast as
  the control port answers), waits WAIT_S, reads the sync log: every 'NVRAM flush' / 'NVRAM wrote' after the marker.
- Restores the row. Log: ./tmp/logs/nv_burst.log. Console mode is the caller's job (test rule: Always).
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time

from _repo import ROOT

LOG = ROOT / "tmp/logs/nv_burst.log"
# Longest wait the gate can add: AWTO_NV_FORCE_MS 60 s x 1.25 (after the last change; the main-image gate needs < 3 s)
WAIT_S = 75.0


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def gui(unit: str, *args: str) -> dict:
    r = subprocess.run([str(ROOT / "dev.py"), "gui", "--unit", unit, *args], capture_output=True, text=True, cwd=ROOT, check=False)
    out = r.stdout + r.stderr
    i, j = out.find("{"), out.rfind("}")
    return json.loads(out[i:j + 1]) if i >= 0 and j > i else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True)
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--row", default="osd_transparency")
    ap.add_argument("--label", default="burst")
    a = ap.parse_args()
    old = gui(a.unit, "get", a.row).get("value")
    base = 40 if old != 40 else 60
    marker = f"nv_burst {a.label} start"
    subprocess.run([str(ROOT / "dev.py"), "note", "--unit", a.unit, marker], capture_output=True, cwd=ROOT, check=False)
    t0 = time.monotonic()
    for i in range(a.count):
        gui(a.unit, "set", a.row, str(base + (i % 2) * 5))
    span = time.monotonic() - t0
    say(f"{a.label}: {a.count} sets of {a.row} in {span:.1f} s; waiting {WAIT_S:.0f} s for the gate")
    threading.Event().wait(WAIT_S)
    log = gui(a.unit, "synclog").get("output", "")
    gui(a.unit, "set", a.row, str(old))
    rows = []
    seen = False
    for ln in log.splitlines():
        if marker in ln:
            seen = True
        elif seen and "NVRAM" in ln:
            m = re.search(r"\s(\d+):(NVRAM .*)", ln)
            if m:
                rows.append((int(m.group(1)), m.group(2)))
    flushes = [r for r in rows if r[1].startswith(("NVRAM flush", "NVRAM write forced"))]
    say(f"{a.label}: {len(flushes)} flush episodes after the marker")
    for ms, txt in rows:
        say(f"  {ms} ms: {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
