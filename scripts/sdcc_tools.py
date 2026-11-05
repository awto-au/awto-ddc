"""SDCC tool paths: awto-sdcc (SourceForge trunk + our fixes), never the distro package.

$AWTO_SDCC_BIN, else ~/opt/awto-sdcc/bin (installed by awto-sdcc scripts/build.py).
Distro sdcc changes under us on OS upgrades (Fedora 45: 4.5.0 -> 4.6.0, 2026-11-05) -> not used.
"""
import os, sys
from pathlib import Path

BIN = Path(os.environ.get("AWTO_SDCC_BIN") or Path.home() / "opt/awto-sdcc/bin")
# AWTO_SDCC_BE=1: Keil byte order (--big-endian, awto-sdcc#5, ddc#15); needs the BE compiler in AWTO_SDCC_BIN
BIG_ENDIAN = os.environ.get("AWTO_SDCC_BE") == "1"
CFLAGS_EXTRA = ["--big-endian"] if BIG_ENDIAN else []
# trunk installs mcs51.lib in lib/mcs51-large but the driver still searches lib/large (r17118+ move)
LIB = BIN.parent / ("share/sdcc/lib/mcs51-large-be" if BIG_ENDIAN else "share/sdcc/lib/mcs51-large")
# ISR lib clones are compiled from this source tree (the BE branch carries the BE lib code)
LIBSRC = Path(os.environ.get("AWTO_SDCC_SRC") or ("/mnt/2tb/git/awto-sdcc-be" if BIG_ENDIAN else "/mnt/2tb/git/awto-sdcc")) / "device/lib"


def tool(name: str) -> str:
    """name: sdcc, sdas8051, sdld, ucsim_51."""
    p = BIN / name
    if not p.exists():
        sys.exit(f"{p} missing: build awto-sdcc (/mnt/2tb/git/awto-sdcc/scripts/build.py) or set AWTO_SDCC_BIN")
    return str(p)
