#!/usr/bin/env python3
"""Make reduced copies of board photos for docs (EXIF stripped, long edge capped, JPEG q82).

--full: copy all originals at full size, GPS tags removed (lossless). Otherwise: reduced copies of the picks.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True,
                                            cwd=Path(__file__).parent).strip())
    except (OSError, subprocess.CalledProcessError):
        return Path(__file__).resolve().parent.parent


REPO = _repo()
LOG = REPO / "tmp/logs/doc_photos.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True, help="folder with the original photos")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--edge", type=int, default=1600, help="max long edge, px")
    ap.add_argument("--full", action="store_true",
                    help="copy every *.jpg in --src at full size; only GPS tags removed (lossless, public repo)")
    ap.add_argument("pick", nargs="*", help="SRC_NAME=OUT_NAME (OUT_NAME without extension)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    bad = 0
    if a.full:
        for src in sorted(a.src.glob("*.jpg")):
            dst = a.out / src.name
            r = subprocess.run(["exiftool", "-q", "-gps:all=", "-o", str(dst), str(src)],
                               capture_output=True, text=True)
            bad += r.returncode != 0
            gps = subprocess.run(["exiftool", "-q", "-gps:all", str(dst)], capture_output=True, text=True).stdout
            bad += bool(gps.strip())
            log(f"{src.name} -> {dst}: rc {r.returncode}, gps left: {gps.strip() or 'none'} {r.stderr.strip()[:120]}")
        return 1 if bad else 0
    for p in a.pick:
        src, name = p.split("=", 1)
        dst = a.out / f"{name}.jpg"
        r = subprocess.run(["magick", str(a.src / src), "-auto-orient", "-strip", "-resize", f"{a.edge}x{a.edge}>",
                            "-quality", "82", str(dst)], capture_output=True, text=True)
        bad += r.returncode != 0
        size = dst.stat().st_size if dst.exists() else 0
        log(f"{src} -> {dst.relative_to(REPO) if dst.is_relative_to(REPO) else dst}: rc {r.returncode}, "
            f"{size // 1024} KiB {r.stderr.strip()[:120]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
