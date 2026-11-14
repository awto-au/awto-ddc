#!/usr/bin/env python3
"""#60 timing table: alternate D2 -> D1 and D1 -> D2 switches N times each (DP-1 mirrored), ms to mode ACTIVE and to unblank per run,
  plus per-phase medians (BOUNDS).

usage: sw_table.py --hdmi-bus 11 --dp-bus 15 --serial S --map MAP [--runs 5] [--label TEXT]
- Each switch = one scripts/sw_timeline.py run (its fixed 8 s settle), the log read on the new port's bus.
- Ends on D2; send 0x30 (auto search) afterwards. Log: ./tmp/logs/sw_table.log; one TSV row per run in tmp/logs/sw_table.tsv.
"""
import argparse, re, statistics, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = re.compile(r"\+\s*(\d+) ms\s+mode ACTIVE")
UNBLANK = re.compile(r"\+\s*(\d+) ms\s+UNBLANK")
# phase boundaries: first event matching each name (sw_timeline decoded lines); a phase = next boundary - this one
BOUNDS = (("reset", "mode SEARCH"), ("scan", "probe source judged"), ("measure", "probe measure done"),
          ("to display setting", "probe display setting start"), ("display setting", "probe display setting done"),
          ("colour", "probe colour proc done"), ("wait to ACTIVE", "mode ACTIVE"), ("active proc", "UNBLANK"))


def phases(out: str) -> dict:
    t = {}
    for ln in out.splitlines():
        m = re.search(r"\+\s*(\d+) ms\s+(.*)$", ln)
        if m:
            for _, ev in BOUNDS:
                if m.group(2).startswith(ev) and ev not in t:
                    t[ev] = int(m.group(1))
    res, prev = {}, 0
    for ph, ev in BOUNDS:
        if ev in t:
            res[ph] = t[ev] - prev
            prev = t[ev]
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hdmi-bus", type=int, required=True)
    ap.add_argument("--dp-bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/sw_table.log").open("a", buffering=1)
    tsv = (ROOT / "tmp/logs/sw_table.tsv").open("a", buffering=1)

    def say(s):
        line = f"{isostamp.now()} {s}"
        print(line); lf.write(line + "\n")

    res, unb, phs = {"D1": [], "D2": []}, {"D1": [], "D2": []}, {"D1": [], "D2": []}
    legs = (("D1", a.hdmi_bus, a.dp_bus), ("D2", a.dp_bus, a.hdmi_bus))
    for run in range(a.runs):
        for to, bus, rbus in legs:
            out = subprocess.run([sys.executable, str(ROOT / "scripts/sw_timeline.py"), str(bus), "--serial", a.serial,
                                  "--map", a.map, "--to", to, "--read-bus", str(rbus)],
                                 capture_output=True, text=True).stdout
            m, u = ACTIVE.findall(out), UNBLANK.findall(out)
            ms = int(m[-1]) if m else None
            ub = int(u[-1]) if u else None
            res[to].append(ms)
            unb[to].append(ub)
            phs[to].append(phases(out))
            say(f"{a.label} run {run + 1} to {to}: ACTIVE at {ms} ms, unblank at {ub} ms")
            tsv.write(f"{isostamp.now()}\t{a.label}\t{to}\t{run + 1}\t{ms}\t{ub}\n")
    for to, v in res.items():
        ok = [x for x in v if x is not None]
        say(f"SUMMARY {a.label} to {to}: {v} median {statistics.median(ok) if ok else None} ms")
        ub = [x for x in unb[to] if x is not None]
        say(f"SUMMARY {a.label} to {to} unblank: {unb[to]} median {statistics.median(ub) if ub else None} ms")
        for ph, _ in BOUNDS:
            v = [p[ph] for p in phs[to] if ph in p]
            say(f"PHASE {a.label} to {to} {ph:20s} median {statistics.median(v) if v else '-':>6} ms  runs {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
