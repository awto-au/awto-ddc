#!/usr/bin/env python3
"""Offline speed bench of firmware images: main-loop cycles per pass in ucsim (fw_profile.py), appended to docs/speed-bench.tsv.

usage: speed_bench.py IMAGE_STEM [IMAGE_STEM ...] [--passes 12] [--label TEXT] [--compiler COMMIT] [--abi N]
                      [--xdata-free N] [--unit-loop R] [--no-record]
  --compiler/--abi are recorded as given (sdcc commit, --sdcccall level); code_bytes = bytes of the .bin that are not 0xFF fill.
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
COLS = ["date", "commit", "image", "label", "passes", "cycles_pass", "work", "stub_entries", "stub_cyc", "instr_pass", "movc", "compiler", "abi", "code_bytes", "xdata_free", "unit_loop"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="+")
    ap.add_argument("--passes", type=int, default=12)
    ap.add_argument("--label", default="")
    ap.add_argument("--compiler", default="", help="awto-sdcc commit the image was built with")
    ap.add_argument("--abi", default="", help="--sdcccall level of the image")
    ap.add_argument("--xdata-free", default="", help="free bytes of the XDATA window (fw_ram_report.py)")
    ap.add_argument("--unit-loop", default="", help="unit main-loop rate /s (loop_rate.py steady median, unit in --label)")
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
               round(stub), round(r["instr_per_pass"]), round(r["counts"].get("movc", 0), 1), a.compiler, a.abi,
               len(b.read_bytes()) - b.read_bytes().count(0xFF), a.xdata_free, a.unit_loop]
        rows.append(row)
        print("\t".join(map(str, row)), flush=True)
    if not a.no_record:
        new = not TSV.exists()
        if not new:    # columns were added: pad old rows once
            lines = TSV.read_text().splitlines()
            width = len(COLS)
            if lines[0].count("\t") + 1 < width:
                lines = ["\t".join(COLS)] + [l + "\t" * (width - 1 - l.count("\t")) for l in lines[1:]]
                TSV.write_text("\n".join(lines) + "\n")
        with TSV.open("a") as f:
            if new:
                f.write("\t".join(COLS) + "\n")
            f.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
