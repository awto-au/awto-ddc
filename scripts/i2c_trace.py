#!/usr/bin/env python3
"""Who talks on the host's i2c adapters (incl. DisplayPort I2C-over-AUX = DDC/EDID): kernel i2c tracepoints for a short window.

usage: i2c_trace.py [--secs 5] [--adapter 15]
  Enables /sys/kernel/tracing/events/i2c, reads trace_pipe for --secs, ALWAYS disables the events again, then prints a count per
  (adapter, process) and the first --show transactions on --adapter with timestamps (relative to the first).
  Needs `sudo -n` (tracefs is root only). Observation only: no i2c traffic is generated.
  Window: --secs of wall time, because trace_pipe blocks until events arrive; a quiet bus ends the read at the deadline, logged.
Log: tmp/logs/i2c_trace.log
"""
import argparse
import collections
import re
import select
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/i2c_trace.log"
TR = "/sys/kernel/tracing"


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def tee(path, value):
    subprocess.run(["sudo", "-n", "tee", path], input=value.encode(), stdout=subprocess.DEVNULL, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--adapter", type=int, default=15)
    ap.add_argument("--show", type=int, default=30)
    a = ap.parse_args()
    lines = []
    tee(f"{TR}/trace", "")                         # clear the ring
    tee(f"{TR}/events/i2c/enable", "1")
    p = None
    try:
        p = subprocess.Popen(["sudo", "-n", "cat", f"{TR}/trace_pipe"], stdout=subprocess.PIPE, text=True)
        end = time.monotonic() + a.secs
        while time.monotonic() < end:
            r, _, _ = select.select([p.stdout], [], [], max(0.0, end - time.monotonic()))
            if not r:
                break
            ln = p.stdout.readline()
            if not ln:
                break
            lines.append(ln.rstrip())
    finally:
        tee(f"{TR}/events/i2c/enable", "0")      # never leave tracing on
        if p is not None:
            p.terminate()
    log(f"captured {len(lines)} i2c trace lines in {a.secs} s; i2c events disabled again")
    cnt = collections.Counter()
    mine = []
    for ln in lines:
        m = re.match(r"\s*(\S+)-(\d+)\s+\[\d+\]\s+\S+\s+([\d.]+):\s+(i2c_\w+):\s+i2c-(\d+)", ln)
        if not m:
            continue
        comm, pid, ts, ev, ad = m.group(1), m.group(2), float(m.group(3)), m.group(4), int(m.group(5))
        cnt[(ad, comm, pid)] += 1
        if ad == a.adapter:
            mine.append((ts, comm, pid, ev, ln.split(ev + ":")[1].strip()))
    for (ad, comm, pid), n in cnt.most_common(15):
        log(f"  i2c-{ad:<3d} {comm}[{pid}] {n} events")
    if mine:
        t0 = mine[0][0]
        for ts, comm, pid, ev, rest in mine[:a.show]:
            log(f"  +{(ts - t0) * 1000:8.2f} ms i2c-{a.adapter} {comm}[{pid}] {ev} {rest[:80]}")
    else:
        log(f"  no transaction on i2c-{a.adapter} in the window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
