#!/usr/bin/env python3
"""Gate: the three EDID tables of make_edid.py pass `edid-decode -c` with no failures and no warning outside scripts/edid_allow.txt.

usage: edid_gate.py     (exit 1 on a failure or an unlisted warning; log ./tmp/logs/edid_gate.log)
  Runs make_edid.py into ./tmp/edid-gate. Runtime ~1 s; stall guard 60 s (fw_gates).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
ALLOW = ROOT / "scripts/edid_allow.txt"
DECODE_TIMEOUT = 10     # edid-decode runs in ~10 ms; stall guard only


def sections(text: str) -> dict:
    """edid-decode -c output -> {'Warnings': [msg], 'Failures': [msg]} (one entry per indented message line)."""
    out, cur = {"Warnings": [], "Failures": []}, None
    for ln in text.splitlines():
        if ln in ("Warnings:", "Failures:"):
            cur = ln[:-1]
        elif ln.startswith("EDID conformity"):
            cur = None
        elif cur and ln.startswith("  ") and ln.strip() and ln.strip() != "EDID:" and not ln.startswith("    "):
            out[cur].append(ln.strip())
        elif cur and ln.startswith("    "):
            out[cur].append(ln.strip())      # continuation line of an EDID: message
    return out


def main() -> int:
    if not shutil.which("edid-decode"):
        print("SKIP edid-decode not installed")
        return 0
    allow = [re.compile(ln) for ln in ALLOW.read_text().splitlines() if ln and not ln.startswith("#")]
    work = ROOT / "tmp/edid-gate"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/make_edid.py"), "--out", str(work), "--no-decode"],
                       capture_output=True, text=True, timeout=30, check=False)
    if r.returncode:
        print(r.stdout + r.stderr)
        return 1
    log, bad = [], 0
    for port in ("dp", "hdmi", "hdmi-d3"):
        t = subprocess.run(["edid-decode", "-c", str(work / f"awto-{port}.bin")], capture_output=True, text=True,
                           timeout=DECODE_TIMEOUT, check=False)
        s = sections(t.stdout)
        unlisted = [w for w in s["Warnings"] if not any(a.fullmatch(w) for a in allow)]
        stale = [a.pattern for a in allow if not any(a.fullmatch(w) for w in s["Warnings"])]
        msg = [f"{port}: rc={t.returncode} warnings={len(s['Warnings'])} unlisted={len(unlisted)} failures={len(s['Failures'])}"]
        msg += [f"  FAIL {f}" for f in s["Failures"]] + [f"  WARN {w}" for w in unlisted]
        msg += [f"  allow-list entry matches nothing: {a}" for a in stale]
        bad += bool(t.returncode or unlisted or s["Failures"] or stale)
        log += msg
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/logs/edid_gate.log").write_text("\n".join(log) + "\n")
    print("\n".join(log))
    print("PASS" if not bad else "FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
