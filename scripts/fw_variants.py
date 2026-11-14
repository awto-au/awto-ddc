#!/usr/bin/env python3
"""Build check of the opt-in firmware variants (-D options default _OFF), so their code does not rot (awto-ddc#165).

usage: fw_variants.py [--serial AWT26110002] [--only NAME,...] [--keep]
- Each variant: a detached git worktree of HEAD in tmp/variants/<name> (compile cache shared through the git common dir),
  fw_build.py with K2S_SDCC_EXTRA = its -D flags and --xdata-floor 0 (an opt-in build must fit, not keep the floor).
- Variants (VARIANTS): meas4k (-D_AWTO_MEAS4K=_ON), net (-D_AWTO_NET=_ON), both.
- Compiler = the rolled one (wb_build.py): awto-sdcc /usr/local, BE, --sdcccall 3. Commit first: uncommitted edits are not built.
- One PASS / FAIL line per variant with XDATA free; exit 1 if any fails. --keep leaves the worktrees (default: removed).
Log: ./tmp/logs/fw_variants.log (+ tmp/logs/fw_variants_<name>.out = fw_build output)
"""
import argparse, os, re, shutil, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


ROOT = repo_root()
VARIANTS = {"meas4k": ["-D_AWTO_MEAS4K=_ON"], "net": ["-D_AWTO_NET=_ON"], "both": ["-D_AWTO_MEAS4K=_ON", "-D_AWTO_NET=_ON"]}
SDCC = "/usr/local"
BUILD_TIMEOUT = 300        # whole fw_build: 76 s cold, ~45 s cached (2026-11-12) x3 cold + worktree checkout; fw_build has stall guards
LOG = None


def say(s):
    line = f"{isostamp.now()} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def git(*a, cwd=ROOT):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="AWT26110002")
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/fw_variants.log").open("a")
    names = [n for n in VARIANTS if not a.only or n in a.only.split(",")]
    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    say(f"variants {names} at HEAD {head}")
    fails = 0
    for n in names:
        wt = ROOT / "tmp/variants" / n
        if wt.exists():
            git("worktree", "remove", "--force", str(wt))
            shutil.rmtree(wt, ignore_errors=True)
        r = git("worktree", "add", "--detach", str(wt), "HEAD")
        if r.returncode:
            say(f"FAIL {n}: worktree: {r.stderr.strip()[-200:]}"); fails += 1; continue
        env = dict(os.environ, AWTO_DDC_REPO=str(wt), AWTO_SDCC_BE="1", AWTO_SDCCCALL="3", AWTO_SDCC_BIN=f"{SDCC}/bin",
                   AWTO_SDCC_SRC="/usr/local/share/sdcc/awto-src", AWTO_FW_TAG=f"var-{n}", K2S_SDCC_EXTRA=" ".join(VARIANTS[n]))
        out = ROOT / f"tmp/logs/fw_variants_{n}.out"
        t0 = time.monotonic()
        try:
            with out.open("w") as fh:
                rc = subprocess.run([sys.executable, "scripts/fw_build.py", "--serial", a.serial, "--xdata-floor", "0"],
                                    cwd=wt, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=BUILD_TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        txt = out.read_text(errors="replace")
        free = re.search(r"XDATA free (\d+) B of (\d+) B", txt)
        last = [l for l in txt.splitlines() if l.strip() and "unused row" not in l][-1:] or [""]
        ok = rc == 0
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {n} {VARIANTS[n]}: rc={rc}, XDATA free {free.group(1) if free else '-'} B, "
            f"{time.monotonic() - t0:.0f} s" + ("" if ok else f" | {last[0][-200:]} (log {out})"))
        if not a.keep:
            git("worktree", "remove", "--force", str(wt))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
