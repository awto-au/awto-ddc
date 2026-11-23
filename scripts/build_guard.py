"""One `dev.py build` at a time per machine, and not into low memory (#316). stdlib only.

- Lock: flock on <main checkout>/tmp/locks/build.lock (shared by every worktree); the holder (pid, tree, start) is written into it.
- Wait for the lock is bounded by SIGALRM; expiry = exit with the holder named.
- Memory: MemAvailable must be >= MIN_AVAIL_MB at start, else exit (systemd-oomd kills the whole VS Code scope at 80 % pressure).
"""
import fcntl
import os
import signal
import sys
from pathlib import Path

import isostamp
import unit_lock

MIN_AVAIL_MB = int(os.environ.get("AWTO_BUILD_MIN_AVAIL_MB", "12288"))   # largest build process measured 5.7 GB (#316): 2 x that + headroom
WAIT_S = int(os.environ.get("AWTO_BUILD_WAIT_S", "600"))   # 57 s warm build measured (#316); 600 s covers a cold build ahead in the queue
LOCK = unit_lock.LOCKS / "build.lock"
_held = None


def avail_mb(meminfo: Path = Path("/proc/meminfo")) -> int:
    for ln in meminfo.read_text().splitlines():
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) // 1024
    return 1 << 30


def _say(msg: str) -> None:
    print(f"{isostamp.now()} {msg}", flush=True)


def acquire(tree: Path, lock: Path = LOCK, wait_s: int = WAIT_S, min_mb: int = MIN_AVAIL_MB) -> None:
    global _held
    free = avail_mb()
    if free < min_mb:
        sys.exit(f"build: only {free} MB available, need {min_mb} MB (AWTO_BUILD_MIN_AVAIL_MB); nothing done")
    lock.parent.mkdir(parents=True, exist_ok=True)
    fh = lock.open("a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.seek(0)
        _say(f"build: another build holds the lock ({fh.read().strip() or 'unknown holder'}); waiting up to {wait_s} s")

        def _expire(*_):
            raise TimeoutError

        old = signal.signal(signal.SIGALRM, _expire)
        signal.alarm(wait_s)
        try:
            fcntl.flock(fh, fcntl.LOCK_EX)
        except TimeoutError:
            fh.seek(0)
            sys.exit(f"build: waited {wait_s} s for the build lock held by {fh.read().strip() or 'unknown'}; nothing done")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    fh.seek(0)
    fh.truncate()
    fh.write(f"pid {os.getpid()} tree {tree} since {isostamp.now()}\n")
    fh.flush()
    _held = fh                                                  # released at process exit
    _say(f"build: lock taken, {free} MB available")
