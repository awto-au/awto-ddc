"""SDCC tool paths: awto-sdcc (SourceForge trunk + our fixes), never the distro package.

$AWTO_SDCC_BIN, else ~/opt/awto-sdcc/bin (installed by awto-sdcc scripts/build.py).
Distro sdcc changes under us on OS upgrades (Fedora 45: 4.5.0 -> 4.6.0, 2026-11-05) -> not used.
"""
import os, sys
from pathlib import Path

BIN = Path(os.environ.get("AWTO_SDCC_BIN") or Path.home() / "opt/awto-sdcc/bin")
# AWTO_SDCC_BE=1: Keil byte order (--big-endian, awto-sdcc#5, ddc#15); needs the BE compiler in AWTO_SDCC_BIN
BIG_ENDIAN = os.environ.get("AWTO_SDCC_BE") == "1"
# AWTO_SDCCCALL=1|2: register calling convention (awto-sdcc#2, needs awto/regcall(-be) compiler + matching -scN lib in
# AWTO_SDCC_BIN); 0/unset = today's ABI
SDCCCALL = os.environ.get("AWTO_SDCCCALL", "0")
CFLAGS_EXTRA = (["--big-endian"] if BIG_ENDIAN else []) + (["--sdcccall", SDCCCALL] if SDCCCALL != "0" else [])
# Library = the install's lib/mcs51-large[-be][-scN] (ABI of SDCCCALL), and only it: the driver's own -k dirs
# (lib/large*, configure-time DATADIR) can name another install (awto-sdcc#20), so links use LINK_LIBS (--nostdlib)
LIB = BIN.parent / ("share/sdcc/lib/mcs51-large" + ("-be" if BIG_ENDIAN else "") + (f"-sc{SDCCCALL}" if SDCCCALL != "0" else ""))
LINK_LIBS = ["--nostdlib", f"-L{LIB}", "-lmcs51"]       # mcs51 port default libs = {"mcs51"} (sdcc src/mcs51/main.c)
# ISR lib clones are compiled from this source tree (the BE branch carries the BE lib code)
LIBSRC = Path(os.environ.get("AWTO_SDCC_SRC") or ("/mnt/2tb/git/awto-sdcc-be" if BIG_ENDIAN else "/mnt/2tb/git/awto-sdcc")) / "device/lib"


def tool(name: str) -> str:
    """name: sdcc, sdas8051, sdld, ucsim_51."""
    p = BIN / name
    if not p.exists():
        sys.exit(f"{p} missing: build awto-sdcc (/mnt/2tb/git/awto-sdcc/scripts/build.py) or set AWTO_SDCC_BIN")
    return str(p)


def stamp() -> dict:
    """Which compiler built an image: install path, `sdcc --version`, fork commit (<install>/awto-sdcc-commit.txt, written by awto-sdcc scripts/build.py)."""
    import subprocess
    f = BIN.parent / "awto-sdcc-commit.txt"
    ver = subprocess.run([tool("sdcc"), "--version"], capture_output=True, text=True, timeout=10).stdout.splitlines()
    return {"install": str(BIN.parent), "version": ver[0] if ver else "?", "commit": f.read_text().strip() if f.exists() else "unstamped"}


def check_install() -> dict:
    """Refuse a stale or wrong install (awto-sdcc#7 audit: images were built with a pre-fix compiler).
    - $AWTO_SDCC_EXPECT=<commit prefix>: the stamp must start with it.
    - stamped install: the compiler/library sources (src/, device/) of the fork tree $AWTO_SDCC_SRC must be identical to the stamped commit; `dirty` stamps fail.
    - unstamped install (e.g. ~/opt/awto-sdcc): allowed, recorded as `unstamped`."""
    import subprocess
    st = stamp()
    exp = os.environ.get("AWTO_SDCC_EXPECT")
    if exp and not st["commit"].startswith(exp):
        sys.exit(f"compiler install {st['install']} is {st['commit']}, expected {exp}")
    if st["commit"] == "unstamped":
        return st
    if st["commit"].endswith("dirty"):
        sys.exit(f"compiler install {st['install']} was built from a dirty tree ({st['commit']}): rebuild from a commit")
    src = LIBSRC.parent.parent
    sha = st["commit"].split()[0]
    r = subprocess.run(["git", "-C", str(src), "diff", "--quiet", sha, "HEAD", "--", "src", "device"], capture_output=True, timeout=30)
    if r.returncode:
        sys.exit(f"compiler install {st['install']} ({sha[:10]}) differs from the fork HEAD in {src} (src/, device/): rebuild it "
                 f"(scripts/build.py --prefix <new dir>) and pass that dir as --bin / AWTO_SDCC_BIN")
    return st
