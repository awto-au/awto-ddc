#!/usr/bin/env python3
"""Offline speed bench of firmware images: main-loop cycles per pass in ucsim (fw_profile.py), appended to docs/speed-bench.tsv.

usage: speed_bench.py IMAGE_STEM [IMAGE_STEM ...] [--passes 12] [--label TEXT] [--no-record]
  IMAGE_STEM = path to <stem>.bin with <stem>.map beside it (e.g. tmp/fw/AWT26110003-wb-clu3-be).
  `work` = cycles/pass minus the _ScalerTimerDelayXms spin (a timer-polled wait; the sim's timer is not the hardware's).
  Compare `work` and `stub_cyc` between images; absolute values are sim machine cycles, not hardware time.
Log: tmp/logs/speed_bench.log
"""
import argparse, subprocess, sys, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_profile as P  # noqa: E402
import fw_sim as F  # noqa: E402

TSV = F.ROOT / "docs/speed-bench.tsv"
COLS = ["date", "commit", "image", "label", "passes", "cycles_pass", "work", "stub_entries", "stub_cyc", "instr_pass", "movc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="+")
    ap.add_argument("--passes", type=int, default=12)
    ap.add_argument("--label", default="")
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args()
    (F.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (F.ROOT / "tmp/logs/speed_bench.log").open("a", buffering=1)
    commit = subprocess.run(["git", "-C", str(F.ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    rows = []
    for stem in a.stems:
        b = Path(stem).with_suffix(".bin") if Path(stem).suffix != ".bin" else Path(stem)
        r = P.profile(b, b.with_suffix(".map"), a.passes, "-be" in b.name, log)
        wait = r["excl"].get("_ScalerTimerDelayXms", 0)
        stub = sum(r["region"].values())
        row = [datetime.now().astimezone().isoformat(timespec="seconds"), commit, b.stem, a.label, r["passes"],
               round(r["cycles_per_pass"]), round(r["cycles_per_pass"] - wait), round(r["counts"].get("stub_entries", 0), 1),
               round(stub), round(r["instr_per_pass"]), round(r["counts"].get("movc", 0), 1)]
        rows.append(row)
        print("\t".join(map(str, row)), flush=True)
    if not a.no_record:
        new = not TSV.exists()
        with TSV.open("a") as f:
            if new:
                f.write("\t".join(COLS) + "\n")
            f.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
