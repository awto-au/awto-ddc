#!/usr/bin/env python3
"""Produce the sanitizer mark list (isr-marks v1.1) with awto-sdcc's static ISR check (docs/sanitizer.md).

usage: san_marks.py [OUT.tsv]      default tmp/san/marks.tsv; via `./dev.py san --marks [OUT]`
- Needs the awto-sdcc checkout ($AWTO_SDCC_REPO, default /mnt/2tb/git/awto-sdcc) and the installed compiler ($AWTO_SDCC_BIN).
- Exit 0 only when no object is left unmarked (isr_volatile_link exit code).
Log: tmp/logs/san_marks.log
"""
import os
import subprocess
import sys
from pathlib import Path

import sdcc_tools as T
from _repo import ROOT

SDCC = Path(os.environ.get("AWTO_SDCC_REPO") or "/mnt/2tb/git/awto-sdcc")
DUMP_TMO = 120      # port + file list of the firmware tree: seconds when warm; 120 s = host-process backstop
LINK_TMO = 600      # 456 compiles at -j4 on the shared box: ~60 s measured warm (2026-11-21); 10x backstop


def run(cmd: list[str], tmo: int, log) -> int:
    log.write(" ".join(cmd) + "\n")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=tmo, check=False)
    log.write(r.stdout + r.stderr)
    print(r.stdout[-600:] + r.stderr[-300:])
    return r.returncode


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tmp/san/marks.tsv").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    cmds = ROOT / "tmp/scratch/isr_cmds.json"
    cmds.parent.mkdir(parents=True, exist_ok=True)
    with (ROOT / "tmp/logs/san_marks.log").open("w", buffering=1) as log:
        rc = run([sys.executable, str(SDCC / "scripts/ddc_corpus.py"), "dump", str(ROOT), "--out", str(cmds)], DUMP_TMO, log)
        if rc:
            return rc
        return run([sys.executable, str(SDCC / "scripts/isr_volatile_link.py"), "--ddc", str(T.BIN), "--cmds", str(cmds),
                    "--jobs", "4", "--marks", str(out)], LINK_TMO, log)


if __name__ == "__main__":
    sys.exit(main())
