#!/usr/bin/env python3
"""Repeated HDMI re-locks of unit 3 with the AWTO_TMDS_PHY_PROBE image: per-lock PHY set-up timing (#256).

usage: phy_probe_runs.py N [--skip 0|1] [--label L] [--method sleep|kvm] [--away D1]
- Per lock: DDC/CI sleep + wake (default) or kvm away (VCP 0x60) and back to D2 (flaky: DDC/CI on the D2 bus is silent while D1 is active), then the sync ring is read until a new PHY probe triplet and the ACTIVE line show.
- --skip: g_ucPhyProbeSkip (1 = the 2.9 ms block is not run) written over the debug link first.
- Events decoded from the raw ring entries (id 0xEC, arg = kind << 4 | port); table printed + tmp/logs/phy_probe_runs.tsv.
Log: ./tmp/logs/phy_probe_runs.log
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/phy_probe_runs.log"
TSV = ROOT / "tmp/logs/phy_probe_runs.tsv"
UNIT = "3"
POLLS = 12          # ring reads per lock: each ~0.5 s, lock + display set-up takes ~1.5 s (sync log, 2026-11-21)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = isostamp.now() + " " + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def dev(*a: str) -> str:
    r = subprocess.run([str(ROOT / "dev.py"), *a], capture_output=True, text=True, cwd=ROOT)
    return r.stdout + r.stderr


def kvm(port: str) -> None:
    for _ in range(3):
        if '"verified": true' in dev("kvm", port, "--units", UNIT):
            return
    say(f"kvm {port}: not verified after 3 tries")


def ring() -> list[dict]:
    out = dev("synclog", "--unit", UNIT, "--json")
    for ln in out.splitlines():
        if "SYNCJSON" in ln:
            d = json.loads(ln.split("SYNCJSON", 1)[1])
            for e in d["entries"]:                   # seq restarts with each episode
                e["seq"] = (d["ep_seq"], e["seq"])
            return d["entries"]
    return []


def decode(e: dict):
    raw = bytes.fromhex(e["raw"])
    return raw[0], raw[1], int.from_bytes(raw[2:4], "big"), int.from_bytes(raw[4:8], "big")


def lock_rec(entries: list[dict], seen: set) -> dict | None:
    """One lock = EC triplet (kind 0, 1, 2) for the port, newer than anything in `seen`, plus an ACTIVE line after it."""
    ec = {}
    t_active = None
    for e in entries:
        i, a, ms, v = decode(e)
        if e["seq"] in seen:
            continue
        if i == 0xEC:
            ec[a >> 4] = (e["seq"], ms, v, a & 0xF)
        elif "->ACTIVE" in e["text"] and ec:
            t_active = ms
    if {0, 1, 2} <= ec.keys() and t_active is not None:
        return {"ec": ec, "t_active": t_active}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--label", default="run")
    ap.add_argument("--away", default="D1")
    ap.add_argument("--method", default="sleep", choices=["sleep", "kvm"], help="re-lock by DDC/CI power sleep/wake, or input switch away and back")
    ap.add_argument("--unit", default="3")
    a = ap.parse_args()
    global UNIT
    UNIT = a.unit
    import re
    m = re.search(r"@0x([0-9a-f]+)", dev("dbg-read", "--unit", UNIT, "_g_ucPhyProbeSkip"))
    for _ in range(3):                          # the first debug-link write can NAK while the link comes up
        dev("dbg-write", "--unit", UNIT, "%s=%02X" % (m.group(1), a.skip))
        if re.search(r"@0x[0-9a-f]+: %02X" % a.skip, dev("dbg-read", "--unit", UNIT, "_g_ucPhyProbeSkip")):
            break
    say(f"skip knob = {a.skip}; {a.n} locks, away input {a.away}, label {a.label}")
    seen: set = set()
    rows = []
    for k in range(a.n):
        if a.method == "sleep":
            dev("ddc", "--unit", UNIT, "sleep")
            for _ in range(POLLS):                   # asleep before the wake: the ring shows the power saving state
                if any("POWER SAVING" in e["text"] or "->SAVING" in e["text"] for e in ring() if e["seq"] not in seen):
                    break
            seen.update(e["seq"] for e in ring())
            dev("ddc", "--unit", UNIT, "wake")
        else:
            kvm(a.away)
            for _ in range(POLLS):                   # away input settled before switching back
                if any("->ACTIVE" in e["text"] or "->NO SIGNAL" in e["text"] for e in ring() if e["seq"] not in seen):
                    break
            seen.update(e["seq"] for e in ring())
            kvm("D2")
        rec = None
        for _ in range(POLLS):
            rec = lock_rec(ring(), seen)
            if rec:
                break
        if not rec:
            say(f"lock {k}: NO PROBE TRIPLET / ACTIVE within {POLLS} ring reads")
            rows.append([a.label, k, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"])
            continue
        e0, e1, e2 = rec["ec"][0], rec["ec"][1], rec["ec"][2]
        tot, clk = e0[2] >> 16, e0[2] & 0x1FFF
        adp, ck = e1[2] >> 16, e1[2] & 0xFFFF
        ck2, low = e2[2] >> 16, e2[2] & 0xFFFF
        mask, win = ((rec['ec'][3][2] >> 16, rec['ec'][3][2] & 0xFFFF) if 3 in rec['ec'] else ('-', '-'))
        fld = '/'.join(str((rec['ec'][4][2] >> sh) & 0xFF) for sh in (24, 16, 8, 0)) if 4 in rec['ec'] else '-'
        if {5, 6, 7} <= rec['ec'].keys():
            st = [rec['ec'][5][2] >> 16, rec['ec'][5][2] & 0xFFFF, rec['ec'][6][2] >> 16, rec['ec'][6][2] & 0xFFFF, rec['ec'][7][2] >> 16]
            fld += ' ' + '/'.join(map(str, st))
        row = [a.label, k, f"D{e0[3]}", clk, tot, adp, ck, ck2, (low >> 8) & 3, f"{(low >> 4) & 7:x}", f"cdr{low & 1}/ckend{(low >> 2) & 1}/skip{(low >> 1) & 1}/retry{(low >> 3) & 1}", mask, win, fld]
        rows.append(row)
        say("lock %d: " % k + " ".join(map(str, row[2:])) + f" active@{rec['t_active']}ms")
        seen.update(x[0] for x in rec["ec"].values())
    with TSV.open("a") as f:
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
