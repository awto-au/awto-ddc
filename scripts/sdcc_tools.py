"""SDCC tool paths: awto-sdcc (SourceForge trunk + our fixes), never the distro package.

$AWTO_SDCC_BIN, else ~/opt/awto-sdcc/bin (installed by awto-sdcc scripts/build.py).
Distro sdcc changes under us on OS upgrades (Fedora 45: 4.5.0 -> 4.6.0, 2026-11-05) -> not used.
"""
import os, sys
from pathlib import Path

BIN = Path(os.environ.get("AWTO_SDCC_BIN") or Path.home() / "opt/awto-sdcc/bin")
# trunk installs mcs51.lib in lib/mcs51-large but the driver still searches lib/large (r17118+ move)
LIB = BIN.parent / "share/sdcc/lib/mcs51-large"


def tool(name: str) -> str:
    """name: sdcc, sdas8051, sdld, ucsim_51."""
    p = BIN / name
    if not p.exists():
        sys.exit(f"{p} missing: build awto-sdcc (/mnt/2tb/git/awto-sdcc/scripts/build.py) or set AWTO_SDCC_BIN")
    return str(p)
