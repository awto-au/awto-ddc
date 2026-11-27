#!/usr/bin/env python3
"""episode.py TYPE UNIT N : time-to-picture episodes (scratch). TYPE = isp | sleepwake | switch
Per episode: host trigger time, fw timeline mapped to host time, host events from hostmon.jsonl. Output jsonl + txt per episode in tmp/logs/bringup/ep/."""
import json, os, re, subprocess, sys, time, datetime as dt
from pathlib import Path
ROOT = Path("/mnt/2tb/git/awto-ddc")
OUT = ROOT / "tmp/logs/bringup/ep"; OUT.mkdir(parents=True, exist_ok=True)
typ, unit, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
env = dict(os.environ, AWTO_UNIT_OWNER="bringup-soak")
CONN = {"1": "card2-HDMI-A-3", "2": "card1-DP-1", "3": "card1-HDMI-A-2"}
if typ == "switch":
    CONN["3"] = "card1-HDMI-A-2,card2-DP-4"
def sh(a):
    t = time.time(); p = subprocess.run(a, cwd=ROOT, capture_output=True, text=True, env=env); return t, time.time(), p.stdout + p.stderr
def last_episode(text):
    rows = []
    for ln in text.splitlines():
        m = re.match(r"^\S+\s+(\d+):(.*)$", ln)
        if m: rows.append((int(m.group(1)), m.group(2)))
    start = 0
    for i in range(1, len(rows)):
        if rows[i][0] < rows[i-1][0] - 50 and not rows[i][1].startswith("(the"): start = i
    return rows[start:]
def host_events(t0, t1):
    ev = []
    for ln in open(ROOT / "tmp/logs/bringup/hostmon.jsonl"):
        try: e = json.loads(ln)
        except Exception: continue
        if e["src"] == "udev" and not e["ev"].startswith(("KERNEL", "UDEV")): continue
        if t0 <= e["t"] <= t1:
            if e["src"] == "dmesg":
                m = re.match(r"(\S+)[,.](\d+)([+-]\d\d:\d\d)", e["ev"])
                if m:
                    try:
                        tt = dt.datetime.fromisoformat(m.group(1) + "." + m.group(2)[:6].ljust(6, "0") + m.group(3)).timestamp()
                    except Exception: tt = e["t"]
                    if not (t0 <= tt <= t1): continue
                    e = dict(e, t=tt)
            ev.append(e)
    return sorted(ev, key=lambda e: e["t"])
def dmesg_anchor():
    return None
for k in range(1, n + 1):
    tag = f"{typ}-u{unit}-{k:02d}"
    if typ == "isp":
        t0, t1, o = sh(["./dev.py", "reset", "--unit", unit])
        m = re.search(r"(\d{4}-\d\d-\d\dT[\d:.]+[+-]\d\d:\d\d)\s+scaler reset sent", o)
        anchor = dt.datetime.fromisoformat(m.group(1)).timestamp() if m else (t0 + t1) / 2
        what = "isp reset"
    elif typ == "cold":
        t0, t1, o = sh(["python3", "scripts/hass_power.py", "cycle", "--unit", unit]); anchor = t1; what = "hass cold cycle (anchor = command return)"
    elif typ == "sleepwake":
        sh(["./dev.py", "ddc", "--unit", unit, "sleep"]); time.sleep(0)  # (wait done by loop below)
        # settle: sleep episode complete before wake (3 s: panel off sequence T4..T6 ~ 1.5 s per log)
        end = time.time() + 3
        while time.time() < end: time.sleep(0.1)
        t0, t1, o = sh(["./dev.py", "ddc", "--unit", unit, "wake"]); anchor = (t0 + t1) / 2; what = "ddc wake"
    elif typ == "switch":
        # away then back; measure the back episode
        away, back = ("dp", "hdmi2") if k % 2 else ("hdmi2", "dp")
        t0, t1, o = sh(["./dev.py", "kvm", back if False else away, "--units", unit]); anchor = (t0 + t1) / 2; what = f"kvm {away}"
    end = time.time() + (9 if typ == 'cold' else 4.5)       # episode ends ~1.6 s (DP) after the trigger; read once, no polling (a read toggles the debug link)
    while time.time() < end: time.sleep(0.1)
    tr, tr2, log = sh(["./dev.py", "synclog", "--unit", unit, "--whole"])
    ep = last_episode(log)
    hev = host_events(t0 - 0.5, tr2)
    lines = [f"# {tag} trigger {what} host t0={t0:.3f} returned +{(t1-t0)*1000:.0f} ms anchor={anchor:.3f} synclog read at +{(tr-t0):.2f}s"]
    for ms, txt in ep:
        lines.append(f"fw   +{anchor + ms/1000 - t0:8.3f}s  ms={ms:6d}  {txt}")
    for e in hev:
        lines.append(f"host +{e['t'] - t0:8.3f}s  [{e['src']}] {e['ev'][:150]}")
    lines.sort(key=lambda s: float(re.search(r"\+\s*(-?[\d.]+)s", s).group(1)) if s.startswith(("fw", "host")) else -1e9)
    (OUT / f"{tag}.txt").write_text("\n".join(lines) + "\n")
    (OUT / f"{tag}.synclog.txt").write_text(log)
    act = [ms for ms, t in ep if "picture on screen" in t]
    print(tag, "fw_active_ms", act[:1], "ep_lines", len(ep), "host_events", len(hev), flush=True)
