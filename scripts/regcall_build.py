#!/usr/bin/env python3
"""Build the firmware once per --sdcccall level and keep the artefacts (awto-sdcc#2 phase 2).

usage: regcall_build.py LEVEL [--bin DIR] [--serial S] [--tag NAME] [--layout fw/bank_layout.tsv]
  LEVEL  0|1|2|3 (AWTO_SDCCCALL); --bin = compiler install whose lib matches LEVEL (REQUIRED; one install holds the libs of all levels)
Result: tmp/runs/<tag>/{fw.bin,fw.map,fw.ihx,build.json,sdcc_bank.log tail,size.txt}. Log: tmp/logs/regcall_build.log
"""
import argparse, os, shutil, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip())
STALL = 300             # fw_build is silent inside a step (asm step <= 240 s own timeout); backstop only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("level", choices="0123")
    ap.add_argument("--bin", default=None)
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--layout", default="", help="passed to fw_build (sticky layout, working-base)")
    ap.add_argument("--cluster", choices=["module", "fn"], default="", help="passed to fw_build")
    ap.add_argument("--cluster-weights", default="")
    ap.add_argument("--pin-common", default="")
    a = ap.parse_args()
    tag = a.tag or f"sc{a.level}"
    if not a.bin:
        sys.exit("--bin is required: name the compiler install explicitly (e.g. /usr/local); it must be stamped by awto-sdcc scripts/build.py")
    inst = a.bin
    env = dict(os.environ, AWTO_DDC_REPO=str(ROOT), AWTO_SDCC_BE="1", AWTO_SDCCCALL=a.level,
               AWTO_SDCC_BIN=f"{inst}/bin", AWTO_SDCC_SRC=os.environ.get("AWTO_SDCC_SRC", f"{inst}/share/sdcc/awto-src"))   # the install's own library sources
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/regcall_build.log").open("a")
    log.write(f"{isostamp.now()} build {tag} bin={inst}\n")
    p = subprocess.Popen([sys.executable, "scripts/fw_build.py", "--serial", a.serial, *(["--layout", a.layout] if a.layout else []), *(["--cluster", a.cluster] if a.cluster else []),
                          *(["--cluster-weights", a.cluster_weights] if a.cluster_weights else []),
                          *(["--pin-common", a.pin_common] if a.pin_common else [])], cwd=ROOT, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import select
    t_last, t0 = time.monotonic(), time.monotonic()
    while p.poll() is None:
        r, _, _ = select.select([p.stdout], [], [], 5)
        if r:
            line = p.stdout.readline()
            if line:
                log.write(line); log.flush(); t_last = time.monotonic(); last = line
        if time.monotonic() - t_last > STALL:       # fw_build steps are silent while a child runs (asm up to 70 s)
            p.kill(); log.write(f"STALL: no output {time.monotonic() - t_last:.0f}s, loadavg {os.getloadavg()}\n")
            return 2
    log.write(p.stdout.read())
    if p.returncode:
        print(f"build {tag} failed rc={p.returncode}; see tmp/logs/regcall_build.log"); return 1
    out = ROOT / "tmp/runs" / tag
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    for f in ("fw.bin", "fw.map", "fw.ihx", "build.json"):
        shutil.copy(ROOT / "tmp/fw" / a.serial / f, out / f)
    shutil.copy(ROOT / "tmp/sdcc-port/bank.json", out / "bank.json")
    r = subprocess.run([sys.executable, "scripts/fw_stack.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    (out / "fw_stack.txt").write_text(r.stdout + r.stderr)
    print(f"{tag}: ok in {time.monotonic() - t0:.0f}s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
