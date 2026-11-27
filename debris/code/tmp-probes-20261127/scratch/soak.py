#!/usr/bin/env python3
"""Bring-up soak (scratch). usage: soak.py UNIT KIND N   KIND = isp | cold   Log: tmp/logs/bringup/"""
import os, re, subprocess, sys, time, json
from pathlib import Path

ROOT = Path("/mnt/2tb/git/awto-ddc")
OUT = ROOT / "tmp/logs/bringup"
OUT.mkdir(parents=True, exist_ok=True)
unit, kind, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
env = dict(os.environ, AWTO_UNIT_OWNER="bringup-soak")
LIM = 5.0  # waiting for a monitor to come back: 5 s max (memory monitor-wait-5s)


def sh(a):
    p = subprocess.run(a, cwd=ROOT, capture_output=True, text=True, env=env)
    return p.stdout + p.stderr


def dmesg_invalid():
    return sh(["sudo", "-n", "dmesg"]).lower().count("invalid dpcd")


def seg(text):
    i = text.rfind("boot:main() entered")
    return text[i:] if i >= 0 else text


def parse(t):
    s = seg(t)
    ms = lambda pat: (lambda m: int(m.group(1)) if m else None)(re.search(r"\s(\d+):" + pat, s))
    return dict(
        boot=("boot:main() entered" in t),
        active=ms(r".*picture on screen"),
        d2timing=ms(r"D2 timing") ,
        d1dp=ms(r"D1 DP link"),
        taken=ms(r"input taken"),
        link_ms=(lambda m: int(m.group(1)) if m else None)(re.search(r"link trained in (\d+)ms", s)),
        link_fail=len(re.findall(r"link training (failed|fail)|training fail", s, re.I)),
        scanfail=len(re.findall(r"scan fail", s)),
        notmeasured=len(re.findall(r"clock not measured", s)),
        tmds_meas=("TMDS clock" in s and "measured" in s and bool(re.search(r"TMDS clock [\d.]+MHz measured", s))),
        nosig=len(re.findall(r"no signal|NOSIGNAL|no-signal", s, re.I)),
        expired=len(re.findall(r"EXPIRED", s)),
    )


rows = []
for k in range(1, n + 1):
    d0 = dmesg_invalid()
    if kind == "cold":
        sh(["python3", "scripts/hass_power.py", "cycle", "--unit", unit])
    else:
        sh(["./dev.py", "reset", "--unit", unit])
    t0 = time.monotonic()
    text = ""
    got = False
    while time.monotonic() - t0 < LIM + (3 if kind == "cold" else 0):
        text = sh(["./dev.py", "synclog", "--unit", unit, "--whole"])
        if "boot:main() entered" in text and "picture on screen" in seg(text):
            got = True
            break
    # one more read to let the tail of the boot land
    wait_t = time.monotonic() - t0
    text2 = sh(["./dev.py", "synclog", "--unit", unit, "--whole"])
    if "boot:main() entered" in text2:
        text = text2
    r = parse(text)
    r.update(k=k, kind=kind, unit=unit, answered=got, wait_s=round(wait_t, 1), dmesg_new_invalid=dmesg_invalid() - d0)
    (OUT / f"unit{unit}-{kind}-{k:02d}.txt").write_text(text)
    rows.append(r)
    line = json.dumps(r)
    print(line, flush=True)
    with (OUT / f"soak-unit{unit}-{kind}.jsonl").open("a") as f:
        f.write(line + "\n")
bad = [r for r in rows if r["active"] is None]
print(f"SUMMARY unit {unit} {kind}: {len(rows)} resets, {len(bad)} without ACTIVE", flush=True)
