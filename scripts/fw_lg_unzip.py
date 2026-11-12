#!/usr/bin/env python3
"""Extract LG OSC firmware zips (ZipCrypto) into the fw_pkg_unpack layout. Never executes anything.

usage: python3 -I fw_lg_unzip.py [package ...]   (default: every ~/vendors/lg/sources/* with a MODEL_*.zip)
- Per-model zip passwords ("<MODEL>!<suffix>") are plain strings in the OSC macOS binary
  (~/vendors/lg/analysis/osc_mac_7_30/...); read at run time, never printed or stored.
- Output: ~/vendors/lg/analysis/<pkg>/unpacked/<zip>.x/ (same layout as fw_pkg_unpack.py), then run fw_pkg_scan.py.
Log: tmp/logs/fw_lg_unzip.log
Timeout: 7z call 120 s backstop (largest zip < 10 MB).
"""
import os, re, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
OSC = next((HOME / "vendors/lg/analysis/osc_mac_7_30/unpacked").rglob("OnScreen Control"), None)
PW = re.compile(rb"([A-Za-z0-9_-]{3,24})(![A-Za-z0-9]{6,24}!@#)")


def main():
    root = Path(os.environ.get("AWTO_DDC_REPO", Path(__file__).resolve().parent.parent))
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/fw_lg_unzip.log").open("a")
    data = OSC.read_bytes()
    by_model = {}
    for m in PW.finditer(data):
        by_model.setdefault(m.group(1).decode().upper(), set()).add((m.group(1) + m.group(2)).decode())
    allpw = sorted({p for s in by_model.values() for p in s})
    pk = sys.argv[1:] or sorted(p.name for p in (HOME / "vendors/lg/sources").iterdir() if p.is_dir())
    for p in pk:
        zs = list((HOME / "vendors/lg/sources" / p).glob("*.zip"))
        if not zs or not zs[0].name.startswith(("MODEL_", "TBT_")):
            continue
        z = zs[0]
        model = z.name.split("_")[1].upper() if z.name.startswith("MODEL_") else ""
        out = HOME / "vendors/lg/analysis" / p / "unpacked" / (z.name + ".x")
        if out.exists() and any(f.stat().st_size > 0 for f in out.rglob("*") if f.is_file()):
            continue
        cands = sorted(by_model.get(model, [])) + [x for x in allpw if x not in by_model.get(model, [])]
        done = False
        for pw in cands:
            out.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["7z", "x", "-y", f"-p{pw}", f"-o{out}", str(z)], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                done = True; break
        msg = f"{'ok' if done else 'FAIL'} {p} (model {model}, {len(cands)} candidates)"
        print(msg); log.write(f"{time.strftime('%FT%T%z')} {msg}\n"); log.flush()


if __name__ == "__main__":
    main()
