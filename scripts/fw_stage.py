#!/usr/bin/env python3
"""Stage a worktree build as tmp/fw/<serial>-<tag>-be.{bin,map} and run the offline gates (boot, isr, link).

usage: fw_stage.py <worktree> <serial> <tag>
Log: ./tmp/logs/fw_stage.log
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATES_LIMIT_S = 90          # boot+isr+link take ~6 s (2026-11-08); 15x margin is the backstop only, fw_gates has its own


def main() -> int:
    tree, serial, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    stem = REPO / "tmp/fw" / f"{serial}-{tag}-be"
    src = tree / "tmp/fw" / serial
    for ext in ("bin", "map"):
        shutil.copy2(src / f"fw.{ext}", f"{stem}.{ext}")
    ids = tree / "tmp/sdcc-port/trace_ids.tsv"
    if ids.is_file():
        shutil.copy2(ids, f"{stem}.ids.tsv")
    r = subprocess.run([sys.executable, str(REPO / "scripts/fw_gates.py"), str(stem), "--tree", str(tree),
                        "--only", "boot,isr,link"], capture_output=True, text=True, timeout=GATES_LIMIT_S)
    out = r.stdout.strip().splitlines()[-4:]
    with (REPO / "tmp/logs/fw_stage.log").open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {stem.name} gates rc={r.returncode}\n" + "\n".join(out) + "\n")
    print(f"{stem}.bin", *out, sep="\n")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
