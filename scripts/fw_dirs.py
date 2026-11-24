"""Our firmware source folders by subsystem (#196): fw/<dir>/*.c / *.h. One list for the build and the lints.

Extra source root (docs/extra-apps.md): $AWTO_EXTRA_FW = a directory outside (or inside) fw/ whose **/*.c *.h *.inc *.asm join the
build like fw/ files. `fw/apps` (the app hooks) is compiled only when an extra root is set; the lints always see it.
"""
import os
from pathlib import Path

OUR_DIRS = ("osd", "nvram", "keys", "power", "input", "log", "test", "diag", "dp", "timer", "meas", "ddcci", "net", "audio", "settings", "cec")
APPS_DIR = "apps"
EXTRA_ENV = "AWTO_EXTRA_FW"
EXTRA_EXTS = ("*.c", "*.h", "*.inc", "*.asm")


def extra_root() -> Path | None:
    """The extra source root of this build ($AWTO_EXTRA_FW, resolved), or None."""
    env = os.environ.get(EXTRA_ENV)
    return Path(env).resolve() if env else None


def extra_dirs(extra: Path | None = None) -> list:
    """Every directory of the extra root that holds a source / header file (include path + compile list), root first."""
    extra = extra or extra_root()
    if extra is None or not extra.is_dir():
        return []
    dirs = {extra} | {p.parent for e in EXTRA_EXTS for p in extra.rglob(e)}
    return sorted(dirs, key=lambda d: (len(d.parts), str(d)))


def our_dirs(root: Path) -> list:
    """Repo folders + fw/apps (lints) + the extra root's folders when one is set."""
    base = [root / "fw" / d for d in (*OUR_DIRS, APPS_DIR) if (root / "fw" / d).is_dir()]
    return base + extra_dirs()


def our_files(root: Path, exts=("*.c", "*.h")) -> list:
    return [p for d in our_dirs(root) for e in exts for p in sorted(d.glob(e))]


def build_dirs(root: Path) -> list:
    """Include path of the compile: as our_dirs, but fw/apps only with an extra root (the default image's command lines stay as they were)."""
    return [d for d in our_dirs(root) if d != root / "fw" / APPS_DIR or extra_root() is not None]


def build_files(root: Path, exts=("*.c",)) -> list:
    return [p for d in build_dirs(root) for e in exts for p in sorted(d.glob(e))]
