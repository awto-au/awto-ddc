#!/usr/bin/env python3
"""Build a wb-p14ui-diag image (awto-ddc#157): wb_build with the nv layout; one warn_shift + rebuild when only line shifts fail.

usage: diag_build.py TAG          e.g. diag_build.py wb-p14ui-diag1
- Tree = this worktree; rtdfw = $AWTO_RTDFW_REPO (default /mnt/2tb/git/awto-rtdfw-diag); main repo = $AWTO_DDC_MAIN
  (default /mnt/2tb/git/awto-ddc, where wb_build.py lives); -D _AWTO_AUDIO_TEST, the tracked fw/bank_layout.tsv (fw_build refuses a layout under tmp/).
- Prints the build summary: XDATA free, main DATA overlay path, link result.
Log: tmp/logs/diag_build.log
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
MAIN = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc"))
RTDFW = os.environ.get("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw-diag")
LOG = TREE / "tmp/logs/diag_build.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def build(tag) -> int:
    env = dict(os.environ, AWTO_RTDFW_REPO=RTDFW)
    env.pop("AWTO_DDC_REPO", None)
    return subprocess.run([sys.executable, "scripts/wb_build.py", "--tree", str(TREE), "--serial", "AWT26110002", "--tag", tag,
                           "-D", "_AWTO_AUDIO_TEST"], cwd=MAIN, env=env,
                          capture_output=True, text=True).returncode


def main() -> int:
    tag = sys.argv[1]
    out = TREE / f"tmp/logs/build_{tag}_AWT26110002.out"
    for attempt in (1, 2):
        rc = build(tag)
        txt = out.read_text(errors="replace")
        unrev = re.findall(r"WARN-GATE unreviewed: (.*)", txt)
        say(f"{tag} attempt {attempt}: rc={rc}, {len(unrev)} unreviewed warning site(s)")
        if rc == 0 or not unrev or attempt == 2:
            break
        r = subprocess.run([sys.executable, "scripts/warn_shift.py", "--tree", str(TREE), "--write"], cwd=TREE,
                           capture_output=True, text=True)
        say("warn_shift: " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
    for pat in (r"free after placement \[[^\]]*\]", r"IRAM layout: .*", r"\[link\] failed", r"image tmp/fw/\S+"):
        for m in re.findall(pat, txt):
            say("  " + m)
    ov = (TREE / "tmp/logs/sdcc_overlay.log").read_text(errors="replace").splitlines()
    md = [ln for ln in ov if "main DATA path" in ln]
    if md:
        say("  " + md[-1].split("  ", 1)[-1][:200])
    for u in unrev:
        say("  unreviewed: " + u)
    return rc


if __name__ == "__main__":
    sys.exit(main())
