#!/usr/bin/env python3
"""Build a work-branch firmware image with the rolled compiler setup and file it as tmp/fw/<serial>-<tag>-be.{bin,map}.

usage: wb_build.py --tree /mnt/2tb/git/awto-ddc-port --serial AWT26110003 --tag wb-p14split [-D NAME=VAL ...]
- Compiler = the one the rolled images use (BE, rcbe sc1, --sdcccall 1); a default-env fw_build gives an LE image
  that boots with byte-swapped diag fields and broken delay cal (#75, 2026-11-07).
- -D: extra defines (K2S_SDCC_EXTRA), e.g. -D _AWTO_LOOP_PROF=_ON.
- --bin/--src/--level/--flags: compiler A/B (install bin dir, its source tree for the ISR lib clones, --sdcccall, extra flags).
Log: ./tmp/logs/wb_build.log (+ <tree>/tmp/logs/build_<tag>_<serial>.out = fw_build output)
"""
import argparse, os, shutil, subprocess, sys, time
from pathlib import Path

SDCC_BIN = "/mnt/2tb/git/awto-sdcc-rcbe/tmp/rc-be-install-sc1/bin"


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("-D", dest="defs", action="append", default=[])
    ap.add_argument("--bin", default=SDCC_BIN)
    ap.add_argument("--src", default="")
    ap.add_argument("--level", default="1")
    ap.add_argument("--flags", default="", help="extra sdcc flags, e.g. --flags=--keil-compat")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (a.tree / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/wb_build.log").open("a")

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); log.write(line + "\n"); log.flush()

    env = dict(os.environ, AWTO_SDCC_BE="1", AWTO_SDCC_BIN=a.bin, AWTO_SDCCCALL=a.level, AWTO_FW_TAG=a.tag,
               K2S_SDCC_EXTRA=" ".join([*(f"-D{d}" for d in a.defs), *a.flags.split()]))
    if a.src:
        env["AWTO_SDCC_SRC"] = a.src
    out = a.tree / f"tmp/logs/build_{a.tag}_{a.serial}.out"
    say(f"build {a.tag} serial {a.serial} tree {a.tree} bin {a.bin} sc{a.level} flags {a.flags!r} defs {a.defs or 'none'} -> {out}")
    with out.open("w") as fh:
        rc = subprocess.run([sys.executable, "scripts/fw_build.py", "--serial", a.serial], cwd=a.tree, env=env,
                            stdout=fh, stderr=subprocess.STDOUT).returncode
    head = out.read_text().splitlines()[:1]
    say(f"rc={rc}; {head[0][25:] if head else 'no output'}")
    if rc:
        return rc
    for ext in ("bin", "map"):
        dst = root / "tmp/fw" / f"{a.serial}-{a.tag}-be.{ext}"
        shutil.copy2(a.tree / f"tmp/fw/{a.serial}/fw.{ext}", dst)
    say(f"image tmp/fw/{a.serial}-{a.tag}-be.bin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
