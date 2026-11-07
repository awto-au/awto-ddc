#!/usr/bin/env python3
"""One firmware build for the --keil-compat A/B (awto-sdcc#25): fw_build with a given awto-sdcc install and extra sdcc
flags, outputs kept in tmp/runs/<tag>/ (fw.bin/.map/.ihx, build.json, asm/ = the per-file compiler output).

usage: kc_build.py TAG --bin INSTALL/bin [--src AWTO_SDCC_TREE] [--flags "--keil-compat"] [--level 1] [--no-layout]
  --no-layout: first-fit packing (fw_build --layout ''); no CH_ names in the map, so fw_sim/health cannot run on it
  --layout FILE: a sticky layout file; a missing one is created (fresh layout for code that no longer fits)
  Big-endian, --sdcccall LEVEL (wb-vfreq: 1). Image copy: tmp/runs/<tag>/AWT26110003-<tag>-be.{bin,map}.
Log: tmp/logs/kc_build.log (fw_build output: tmp/logs/fw_build.log)
"""
import argparse, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
BUILD_TMO = 3600   # s backstop; fw_build has its own per-file compile timeout (keil2sdcc COMPILE_TIMEOUT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--bin", required=True)
    ap.add_argument("--src", default="/mnt/2tb/git/awto-sdcc-kc")
    ap.add_argument("--flags", default="")
    ap.add_argument("--level", default="1")
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--no-layout", action="store_true")
    ap.add_argument("--layout", default="")
    ap.add_argument("--resid-end", default="")
    ap.add_argument("--fw-args", default="", help="more fw_build args, e.g. '--cluster fn --cluster-weights fw/cluster_weights.json'")
    argv = sys.argv[1:]
    for i, s in enumerate(argv[:-1]):          # --flags "--keil-compat" (argparse rejects values starting with --)
        if s in ("--flags", "--fw-args") and argv[i + 1].startswith("-"):
            argv[i:i + 2] = [f"{s}={argv[i + 1]}"]
    a = ap.parse_args(argv)
    env = dict(os.environ, AWTO_DDC_REPO=str(ROOT), AWTO_SDCC_BE="1", AWTO_SDCCCALL=a.level, AWTO_SDCC_BIN=a.bin,
               AWTO_SDCC_SRC=a.src, K2S_SDCC_EXTRA=a.flags)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/kc_build.log").open("a", buffering=1)
    t0 = time.monotonic()
    log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {a.tag}: bin={a.bin} flags={a.flags!r} level={a.level}\n")
    r = subprocess.run([sys.executable, "scripts/fw_build.py", "--serial", a.serial, *(["--layout", ""] if a.no_layout else []),
                        *(["--layout", str(Path(a.layout).resolve())] if a.layout else []),
                        *(["--resid-end", a.resid_end] if a.resid_end else []), *a.fw_args.split()], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=BUILD_TMO)
    log.write(r.stdout[-3000:] + r.stderr[-2000:])
    out = ROOT / "tmp/runs" / a.tag
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if r.returncode:
        if (ROOT / "tmp/sdcc-port/asm").is_dir():          # asm is complete when only link/layout failed
            shutil.copytree(ROOT / "tmp/sdcc-port/asm", out / "asm")
        print(f"FAIL {a.tag}: fw_build rc={r.returncode}: {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
        return 1
    fw = ROOT / "tmp/fw" / a.serial
    for f in fw.iterdir():
        shutil.copy2(f, out / f.name)
    shutil.copytree(ROOT / "tmp/sdcc-port/asm", out / "asm", dirs_exist_ok=True)
    stem = out / f"{a.serial}-{a.tag}-be"
    shutil.copy2(fw / "fw.bin", stem.with_suffix(".bin"))
    shutil.copy2(fw / "fw.map", stem.with_suffix(".map"))
    msg = f"OK {a.tag}: {stem}.bin in {time.monotonic() - t0:.0f} s"
    log.write(msg + "\n")
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
