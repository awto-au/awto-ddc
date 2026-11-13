"""Our firmware source folders by subsystem (#196): fw/<dir>/*.c / *.h. One list for the build and the lints."""
from pathlib import Path

OUR_DIRS = ("osd", "nvram", "keys", "power", "input", "log", "test", "diag", "dp", "timer", "meas", "ddcci", "net", "audio", "settings")


def our_dirs(root: Path) -> list:
    return [root / "fw" / d for d in OUR_DIRS if (root / "fw" / d).is_dir()]


def our_files(root: Path, exts=("*.c", "*.h")) -> list:
    return [p for d in our_dirs(root) for e in exts for p in sorted(d.glob(e))]
