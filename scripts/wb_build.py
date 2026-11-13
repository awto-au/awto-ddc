#!/usr/bin/env python3
"""Build a work-branch firmware image with the rolled compiler setup and file it as tmp/fw/<serial>-<tag>-be.{bin,map}.

usage: wb_build.py --tree /mnt/2tb/git/awto-ddc-p14sc3 --serial AWT26110003 --tag wb-p14kc2 [-D NAME=VAL ...]
- Compiler = /usr/local (awto-sdcc main e18804a26d, keil-compat), BE, --sdcccall 3, far locals off (awto-sdcc#36, ddc#204).
  The install's stamp (awto-sdcc-commit.txt) must start with SDCC_COMMIT and the tree must use --keil-compat
  (fw_compile refuses a compiler without it). A default-env fw_build gives an LE image (byte-swapped diag, #75).
- -D: extra defines (K2S_SDCC_EXTRA), e.g. -D _AWTO_LOOP_PROF=_ON.
- --fw-args: more fw_build args; fresh layout = `--layout <missing file> --cluster fn --cluster-weights fw/cluster_weights.json`.
- --bin/--src/--level/--flags/--expect: compiler A/B (install bin dir, its source tree for the ISR lib clones, --sdcccall,
  extra flags, stamp prefix; --expect '' skips the stamp check, for unstamped installs).
Log: ./tmp/logs/wb_build.log (+ <tree>/tmp/logs/build_<tag>_<serial>.out = fw_build output)
"""
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

SDCC_INSTALL = Path("/usr/local")
SDCC_COMMIT = "e18804a26d"
SDCC_SRC = str(SDCC_INSTALL / "share/sdcc/awto-src")   # ISR lib clones (sdcc_isr_libs) compile from this tree's device/lib
SDCCCALL = "3"


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


def stamp(bin_dir: Path) -> str:
    for f in (bin_dir.parent / "share/sdcc/awto-sdcc-commit.txt", bin_dir.parent / "awto-sdcc-commit.txt"):
        if f.exists():
            return f.read_text().strip()
    return "unstamped"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("-D", dest="defs", action="append", default=[])
    ap.add_argument("--bin", type=Path, default=SDCC_INSTALL / "bin")
    ap.add_argument("--src", help="default: <install>/share/sdcc/awto-src if the install has it, else SDCC_SRC")
    ap.add_argument("--level", default=SDCCCALL)
    ap.add_argument("--expect", default=SDCC_COMMIT, help="install stamp prefix ('' = no check)")
    ap.add_argument("--flags", default="", help="extra sdcc flags")
    ap.add_argument("--fw-args", default="", help="more fw_build args (fresh layout: '--layout NEW.tsv --cluster fn ...')")
    a = ap.parse_args()
    if re.search(r"--layout\s+(\./)?tmp/", a.fw_args):
        ap.error("--layout under tmp/ is refused: the build uses the tracked fw/bank_layout.tsv only")
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (a.tree / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/wb_build.log").open("a")

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); log.write(line + "\n"); log.flush()

    st = stamp(a.bin)
    if a.expect and not st.startswith(a.expect):
        say(f"REFUSED: compiler {a.bin} stamp {st!r}, expected {a.expect} (pass --expect '' for an A/B with another install)")
        return 2
    own = a.bin.parent / "share/sdcc/awto-src"          # newer installs ship their library sources (awto-sdcc#80)
    a.src = a.src or str(own if own.is_dir() else SDCC_SRC)
    say(f"library sources {a.src}")
    env = dict(os.environ, AWTO_SDCC_BE="1", AWTO_SDCC_BIN=str(a.bin), AWTO_SDCCCALL=a.level, AWTO_FW_TAG=a.tag,
               AWTO_SDCC_SRC=a.src, K2S_SDCC_EXTRA=" ".join([*(f"-D{d}" for d in a.defs), *a.flags.split()]))
    out = a.tree / f"tmp/logs/build_{a.tag}_{a.serial}.out"
    say(f"build {a.tag} serial {a.serial} tree {a.tree} bin {a.bin} ({st[:10]}) sc{a.level} flags {a.flags!r} "
        f"defs {a.defs or 'none'} -> {out}")
    with out.open("w") as fh:
        rc = subprocess.run([sys.executable, "scripts/fw_build.py", "--serial", a.serial, *a.fw_args.split()], cwd=a.tree, env=env,
                            stdout=fh, stderr=subprocess.STDOUT).returncode
    head = out.read_text().splitlines()[:1]
    say(f"rc={rc}; {head[0][25:] if head else 'no output'}")
    if rc:
        return rc
    bj = json.loads((a.tree / f"tmp/fw/{a.serial}/build.json").read_text())
    got = (bj.get("compiler") or {}).get("commit", "not recorded")
    if a.expect and not got.startswith(a.expect):
        say(f"REFUSED: build.json compiler {got!r}, expected {a.expect} (tree without the stamp in build.json?)")
        return 2
    for ext in ("bin", "map"):
        dst = root / "tmp/fw" / f"{a.serial}-{a.tag}-be.{ext}"
        shutil.copy2(a.tree / f"tmp/fw/{a.serial}/fw.{ext}", dst)
    if (a.tree / "fw/awto/sync.tsv").exists():          # #139: the sync-log texts of this image (scripts/sync_log.py)
        dst = root / "tmp/fw" / f"{a.serial}-{a.tag}-be.sync.tsv"
        gen = a.tree / "scripts/gen_awto_sync.py"
        if gen.exists():                                  # #162: {NAME} tokens resolved against the tree's header
            import importlib.util
            sp = importlib.util.spec_from_file_location("gen_awto_sync_tree", gen)
            mod = importlib.util.module_from_spec(sp)
            old = os.environ.get("AWTO_DDC_REPO")
            os.environ["AWTO_DDC_REPO"] = str(a.tree)
            sp.loader.exec_module(mod)
            os.environ.pop("AWTO_DDC_REPO") if old is None else os.environ.__setitem__("AWTO_DDC_REPO", old)
            dst.write_text("\n".join((ln if ln.startswith("#") else mod.resolve(ln, mod.HEADER)) for ln in (a.tree / "fw/awto/sync.tsv").read_text().splitlines()) + "\n")
        else:
            shutil.copy2(a.tree / "fw/awto/sync.tsv", dst)
    rtdfw = os.environ.get("AWTO_RTDFW_REPO")           # the registry this image was built from: its host settings table
    if rtdfw:
        subprocess.run([sys.executable, str(root / "scripts/settings_gen.py"), "--rtdfw", rtdfw, "--host-out",
                        str(root / "tmp/fw" / f"{a.serial}-{a.tag}-be.settings_table.py")], check=True)
    say(f"image tmp/fw/{a.serial}-{a.tag}-be.bin (compiler {got[:10]}, sdcccall {bj.get('sdcccall')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
