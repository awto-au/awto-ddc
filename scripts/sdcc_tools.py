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
