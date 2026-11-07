#!/usr/bin/env python3
"""Free-space guard and build-output pruning (#77).

- A flash cut off by ENOSPC left unit 2 with a mixed image (#77): refuse to start under MIN_FREE_MB.
- tmp/fw keeps the newest KEEP_TAGS image tags plus anything flashed/attempted/last; older tags are
  already in git (fw/images, fw_archive.py) or regenerable by `dev.py build`.

CLI: disk_guard.py [--prune] -> prints free MB (and pruned bytes). Log: ./tmp/logs/disk_guard.log
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_FREE_MB = 200       # one flash run writes < 20 MB of logs; a build ~300 MB in its worktree tmp/
BUILD_FREE_MB = 600     # build: sdcc-port intermediates are ~260 MB (2026-11-08, #77)
KEEP_TAGS = 12


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[1]


def _log(msg: str) -> None:
    p = _repo() / "tmp/logs/disk_guard.log"
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass                                    # disk full: the print above is the record


def free_mb(path: Path | None = None) -> int:
    return shutil.disk_usage(path or _repo()).free // (1 << 20)


def require_free(what: str, min_mb: int = MIN_FREE_MB, path: Path | None = None) -> None:
    """SystemExit(6) if the filesystem holding path (default: the repo) has < min_mb free."""
    f = free_mb(path)
    if f < min_mb:
        _log(f"refuse {what}: {f} MB free on {path or _repo()}, need {min_mb} MB; nothing done (#77)")
        raise SystemExit(6)


def prune_fw(fw: Path | None = None, keep: int = KEEP_TAGS) -> int:
    """Delete tmp/fw/<tag>.{bin,map,ids.tsv} beyond the newest `keep` tags; never a flashed/attempted/last tag."""
    fw = fw or _repo() / "tmp/fw"
    pinned: set[str] = set()
    for j in fw.glob("*-flashed.json"):
        d = json.loads(j.read_text())
        pinned |= {d.get("tag", ""), d.get("attempted", ""), Path(d.get("image", "x")).stem}
    pinned |= {t.read_text().strip() for t in fw.glob("*-last.txt")}
    tags: dict[str, float] = {}
    for b in fw.glob("*.bin"):
        if re.match(r"AWT\d{8}-", b.name):
            tags[b.stem] = b.stat().st_mtime
    old = sorted(tags, key=tags.get, reverse=True)[keep:]
    freed = 0
    for t in old:
        if t in pinned:
            continue
        for ext in (".bin", ".map", ".ids.tsv"):
            p = fw / f"{t}{ext}"
            if p.is_file():
                freed += p.stat().st_size
                p.unlink()
    if freed:
        _log(f"prune tmp/fw: {len(old)} old tag(s) past the newest {keep}, {freed >> 20} MB freed")
    return freed


if __name__ == "__main__":
    if "--prune" in sys.argv:
        prune_fw()
    _log(f"free: {free_mb()} MB on {_repo()}")
