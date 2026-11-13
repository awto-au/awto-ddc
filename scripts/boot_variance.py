#!/usr/bin/env python3
"""Cold-boot variance on unit 2 (#162): per image N x (hass_power cycle, ring read), POWER OFF / SEARCH / ACTIVE and the predetect flap count.

usage: boot_variance.py TAG [TAG ...] [--runs 3] [--unit 2]      (TAG = tmp/fw/AWT26110002-<tag>-be.bin; each image flashed once, gated images only)
- Flash: ./dev.py flash --unit N <bin>. Boot: hass_power.py cycle --unit N; ring: dbg_link on, sync_log.py, dbg_link off (bus 11 = unit 2).
- Wait: the ring is polled until the episode holds 'mode ACTIVE' (BOOT_WAIT_S: boot 2.4 s + HDMI scan variance, x2.5 = 6 s; expiry = run FAIL).
- Flap count = 'D2 signal lost' lines (each repeat of the predetect pair collapsed into '(the 2 lines above repeated N more times)': + N).
Log: tmp/logs/boot_variance.log
"""
import argparse, re, statistics, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/boot_variance.log"
BUS, SERIAL = 11, "AWT26110002"          # unit 2 (devices.json)
BOOT_WAIT_S = 6.0
POLL_S = 0.5                              # ring poll: one read ~0.1 s; boot is seconds


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def run(*a, limit=120):
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, cwd=ROOT, timeout=limit)


def one(mp: Path):
    run("scripts/hass_power.py", "cycle", "--unit", "2")
    t0 = time.monotonic()
    txt = ""
    while time.monotonic() - t0 < BOOT_WAIT_S:
        time.sleep(POLL_S)
        run("scripts/dbg_link.py", "on", BUS, limit=30)
        r = run("scripts/sync_log.py", BUS, "--serial", SERIAL, "--map", mp, limit=30)
        run("scripts/dbg_link.py", "off", BUS, limit=30)
        txt = r.stdout
        if re.search(r"mode ACTIVE|-> ACTIVE[:( ]", txt):        # old images | #162 s3b system transition
            break
    ms = lambda pat: next((int(m.group(1)) for ln in txt.splitlines() if (m := re.search(r"\+\s*(\d+) ms " + pat, ln))), None)
    lost = len(re.findall(r"D2 signal lost", txt)) + sum(int(x) for x in re.findall(r"repeated (\d+) more", txt))
    return dict(off=ms(r"(mode POWER OFF|system:in RESET for \d+ms->AC ON)"), search=ms("(mode SEARCH|system:.*->SEARCH:)"),
                active=ms("(mode ACTIVE|system:.*->ACTIVE:)"), flaps=lost)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    for tag in a.tags:
        b = ROOT / f"tmp/fw/{SERIAL}-{tag}-be.bin"
        r = run("dev.py", "flash", "--unit", 2, b, limit=400)
        say(f"== {tag}: flash rc={r.returncode}")
        if r.returncode:
            return 1
        rows = []
        for n in range(a.runs):
            d = one(b.with_suffix(".map"))
            rows.append(d)
            say(f"  {tag} boot {n + 1}: POWER OFF +{d['off']}  SEARCH +{d['search']}  ACTIVE +{d['active']}  predetect flaps {d['flaps']}")
        for k in ("off", "search", "active", "flaps"):
            v = [d[k] for d in rows if d[k] is not None]
            say(f"  {tag} {k}: mean {statistics.mean(v):.0f}  min {min(v)}  max {max(v)}  spread {max(v) - min(v)}" if v else f"  {tag} {k}: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
