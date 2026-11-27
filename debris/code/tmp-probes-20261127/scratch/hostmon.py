#!/usr/bin/env python3
"""Host-side event recorder (scratch): sysfs connector state transitions (5 ms poll) + udev drm uevents + filtered dmesg.
Writes jsonl {t: unix s, src, ev} to tmp/logs/bringup/hostmon.jsonl until killed."""
import json, subprocess, threading, time, re, sys
from pathlib import Path
OUT = Path("/mnt/2tb/git/awto-ddc/tmp/logs/bringup/hostmon.jsonl")
CONN = ["card1-DP-1", "card1-HDMI-A-2", "card2-HDMI-A-3", "card2-DP-4"]
lock = threading.Lock()
f = OUT.open("a", buffering=1)
def emit(src, ev, t=None):
    with lock:
        f.write(json.dumps({"t": t or time.time(), "src": src, "ev": ev}) + "\n")
def rd(p):
    try:
        return Path(p).read_text().strip()
    except Exception:
        return "?"
def poll():
    last = {}
    while True:
        for c in CONN:
            v = " ".join(rd(f"/sys/class/drm/{c}/{n}") for n in ("status", "enabled", "dpms"))
            if last.get(c) != v:
                emit("sysfs", f"{c} {v}")
                last[c] = v
        time.sleep(0.005)   # 5 ms: finer than the ~300 ms gaps looked for
def pipe(cmd, src, filt=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for ln in p.stdout:
        if filt and not re.search(filt, ln): continue
        if " BAD " in ln: continue
        emit(src, ln.strip())
threading.Thread(target=poll, daemon=True).start()
threading.Thread(target=pipe, args=(["udevadm", "monitor", "-k", "-u", "-s", "drm", "--property"], "udev", r"^(KERNEL|UDEV)"), daemon=True).start()
threading.Thread(target=pipe, args=(["sudo", "-n", "dmesg", "-w", "--time-format", "iso"], "dmesg", r"i915|drm|nvidia|NVRM|hotplug|HPD|link train|DPCD"), daemon=True).start()
emit("hostmon", "started")
while True: time.sleep(3600)
