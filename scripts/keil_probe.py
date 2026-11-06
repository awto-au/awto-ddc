#!/usr/bin/env python3
"""Compile a probe .c with Keil C51 (Wine) and print the generated assembly (.SRC), comments stripped.

Usage: keil_probe.py FILE.c [C51 controls...]   (default controls: SRC LARGE)
Tool tree: $KEIL_C51_TREE or tmp/wine-keil/tree; prefix tmp/wine-keil/prefix. Log: tmp/logs/keil_probe.log
"""
import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = repo_root()
    wk = root / "tmp" / "wine-keil"
    tree = Path(os.environ.get("KEIL_C51_TREE", wk / "tree"))
    src = Path(sys.argv[1]).resolve()
    ctl = sys.argv[2:] or ["SRC", "LARGE"]
    env = dict(os.environ, WINEPREFIX=str(wk / "prefix"), WINEDEBUG="-all")
    # stall guard: C51 compiles a probe in <2 s under Wine; 60 s = hung
    r = subprocess.run(["wine", str(tree / "C51" / "BIN" / "C51.exe"), src.name, *ctl],
                       cwd=src.parent, env=env, capture_output=True, text=True, timeout=60)
    out = "\n".join(l for l in r.stdout.splitlines() if l.strip())
    log = root / "tmp" / "logs" / "keil_probe.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(f"== {src.name} {' '.join(ctl)}\n{out}\n")
    print(out)
    asm = src.with_suffix(".SRC")
    if "SRC" in ctl and asm.exists():
        for l in asm.read_text(errors="replace").splitlines():
            if l.strip() and not l.lstrip().startswith(";"):
                print(l)
    return 0 if " 0 ERROR" in out else 1


if __name__ == "__main__":
    sys.exit(main())
