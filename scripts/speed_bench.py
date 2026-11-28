#!/usr/bin/env python3
"""Offline speed bench of firmware images: main-loop cycles per pass in ucsim (fw_profile.py), appended to docs/speed-bench.tsv.

usage: speed_bench.py IMAGE_STEM [IMAGE_STEM ...] [--passes 12] [--label TEXT] [--compiler COMMIT] [--abi N]
                      [--xdata-free N] [--unit-loop R] [--no-record]
       speed_bench.py --osd-render [--label TEXT] [--no-record]
  --compiler/--abi are recorded as given (sdcc commit, --sdcccall level); code_bytes = bytes of the .bin that are not 0xFF fill.
  IMAGE_STEM = path to <stem>.bin with <stem>.map beside it (e.g. tmp/fw/AWT26110003-wb-clu3-be).
  `work` = cycles/pass minus the _ScalerTimerDelayXms spin (a timer-polled wait; the sim's timer is not the hardware's).
  Compare `work` and `stub_cyc` between images; absolute values are sim machine cycles, not hardware time.
  --osd-render: host OSD model (osd_model.py) wall s per busy 4K frame (windows + full text map + highlight + blend; mean of 3
    after a warm-up) with the 1-min load average and core count; row image `osd_model-4k-busy`. No pass/fail (#367, Dan 2026-11-28).
Log: tmp/logs/speed_bench.log
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_profile as P
import fw_sim as F

TSV = F.ROOT / "docs/speed-bench.tsv"
COLS = ["date", "commit", "image", "label", "passes", "cycles_pass", "work", "stub_entries", "stub_cyc", "instr_pass", "movc", "compiler", "abi", "code_bytes", "xdata_free", "unit_loop",
        "pacing_ms", "passes_s_idle", "busy_pct_idle", "worst_ms_idle", "osd_render_s", "load_1m"]     # pacing_ms..worst_ms_idle: loop_pacing_sim.py --bench


def osd_render_s() -> float:
    """Wall s per frame of a busy 4K OSD state in osd_model (was tests/test_osd_model_robust.py, #367)."""
    sys.path.insert(0, str(F.ROOT / "scripts"))
    import osd_demo as D
    import osd_model as M
    i = D.Img().window(0, 100, 100, 3000, 1500, 2, gradient={"dir": 0, "pol": (1, 1, 1), "en": (1, 1, 1), "step": 1})
    i.window(10, 200, 200, 3000, 1400, 3, adr4=(0x80, 1, 4)).window(2, 300, 300, 3500, 1800, 4)
    i.text_boxes(100, 255, 1, 4).place(0, 0)
    i.reg(0x0A, 0x08, 0x0C).reg(0x2A, 0x42).ovl.__setitem__(0, 0x09)
    st = i.state()
    M.render(st, 3840, 2160, bg=(100, 100, 100))          # warm-up: glyph memo
    t0 = time.perf_counter()
    for _ in range(3):
        M.render(st, 3840, 2160, bg=(100, 100, 100))
    return (time.perf_counter() - t0) / 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*")
    ap.add_argument("--osd-render", action="store_true", help="time the host OSD model render instead of images (#367)")
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
    commit = subprocess.run(["git", "-C", str(F.ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    rows = []
    if not a.stems and not a.osd_render:
        ap.error("IMAGE_STEM or --osd-render required")
    if a.osd_render:
        dt = osd_render_s()
        load = os.getloadavg()[0]
        row = [datetime.now().astimezone().isoformat(timespec="seconds"), commit, "osd_model-4k-busy", a.label] + [""] * 16 + [f"{dt:.2f}", f"{load:.1f}/{os.cpu_count()}"]
        log.write(f"osd_render {dt:.2f} s/frame, load {load:.1f} on {os.cpu_count()} cores\n")
        rows.append(row)
        print("\t".join(map(str, row)), flush=True)
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
