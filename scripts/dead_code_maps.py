#!/usr/bin/env python3
"""Build the default image + opt-in variants, then run dead_code.py over all maps (#209 recount).

usage: dead_code_maps.py [--serial AWT26110003] [--skip-build]
  Variants first (no-FRC, audio test, meas4k+net), each on a fresh layout fw/bank_layout.dc-<name>.tsv, deleted after,
  (maps only). Default last, committed layout: tmp/sdcc-port is then the default build (gates read it);
  its compiler output is snapshotted to tmp/dc/asm_default. Freeze variant: keys.c #error, skipped.
  --skip-build: rerun dead_code.py on the maps already in tmp/dc/.
Log: ./tmp/logs/dead_code_maps.log (each build: tmp/logs/dead_code_maps.<tag>.out)
"""
import argparse, os, shutil, subprocess, sys
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/dead_code_maps.log"
DC = ROOT / "tmp/dc"
VARIANTS = {                                           # map name -> -D defines
    "nofrc": ["_AWTO_FRC=_OFF"],
    "audio": ["_AWTO_AUDIO_TEST"],
    "mn": ["_AWTO_MEAS4K=_ON", "_AWTO_NET=_ON"],
}
FRESH = "--cluster fn --cluster-weights fw/cluster_weights.json"  # maps only, never flashed; resid_end from fw/rl6449_memory.toml


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def build(serial: str, tag: str, defines: list[str], fw_args: str | None) -> Path:
    cmd = [sys.executable, str(ROOT / "dev.py"), "build", "--tree", str(ROOT), "--serial", serial, "--tag", tag]
    for d in defines:
        cmd += ["-D", d]
    if fw_args:
        cmd += ["--fw-args", fw_args]
    out = ROOT / f"tmp/logs/dead_code_maps.{tag}.out"
    say(f"build {tag}: {' '.join(defines) or 'default'} -> {out.relative_to(ROOT)}")
    with out.open("w") as f:                           # dev.py build has its own stall guard
        rc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode
    if rc:
        raise SystemExit(f"build {tag} failed rc={rc}: see {out}")
    return ROOT / f"tmp/fw/{serial}-{tag}-be.map"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--skip-build", action="store_true")
    a = ap.parse_args()
    if not a.skip_build:
        shutil.rmtree(DC, ignore_errors=True)
        DC.mkdir(parents=True)
        for name, defs in VARIANTS.items():
            layout = ROOT / f"fw/bank_layout.dc-{name}.tsv"   # dev.py build refuses tmp/ layouts; deleted after
            layout.unlink(missing_ok=True)
            try:
                m = build(a.serial, f"dc-{name}", defs, f"--layout {layout.relative_to(ROOT)} {FRESH}")
            finally:
                layout.unlink(missing_ok=True)
            shutil.copy(m, DC / f"{name}.map")
        shutil.copy(build(a.serial, "dc-default", [], None), DC / "default.map")   # last: tmp/sdcc-port = default for gates
        shutil.copytree(ROOT / "tmp/sdcc-port/asm", DC / "asm_default")
    maps = [str(DC / "default.map")] + [str(DC / f"{n}.map") for n in VARIANTS]
    return subprocess.run([sys.executable, str(ROOT / "scripts/dead_code.py"), *maps, "--asm", str(DC / "asm_default")],
                          cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
