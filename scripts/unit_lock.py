#!/usr/bin/env python3
"""Hardware unit locks: one work stream per monitor unit (#65, docs/cleanroom.md "Hardware unit locks").

usage: unit_lock.py acquire SERIAL --owner NAME [--pid PID]   hold the unit for a stream (several tool runs)
       unit_lock.py release SERIAL --owner NAME
       unit_lock.py status [SERIAL]
  Lock file tmp/locks/<serial>: owner, pid, host, tool, ISO time (key=value lines).
  Tools (rtd_flash_image.py, unit_health.py) call held(serial, tool): free or stale -> taken for the run and released;
  held by owner == $AWTO_UNIT_OWNER -> the stream's own lock, run proceeds; held by anyone else -> SystemExit naming them.
  Stale = the recorded pid is dead (this host). acquire's default pid = the nearest ancestor named claude/node
  (the agent session), else the parent shell.
Log: tmp/logs/unit_lock.log
"""
from __future__ import annotations

import argparse, os, socket, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
LOCKS = ROOT / "tmp" / "locks"
SESSION_COMM = ("claude", "node")


def log(s: str) -> None:
    try:
        (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
        with (ROOT / "tmp/logs/unit_lock.log").open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n")
    except OSError as error:
        # In particular, ENOSPC after a verified flash must not mask its result.
        try:
            print(f"WARNING: unit lock log unavailable: {error}", file=sys.stderr)
        except (OSError, ValueError):
            pass


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def session_pid() -> int:
    pid = os.getppid()
    p = pid
    for _ in range(32):
        try:
            comm = Path(f"/proc/{p}/comm").read_text().strip()
            pp = int(Path(f"/proc/{p}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
        if comm in SESSION_COMM:
            return p
        if pp <= 1:
            break
        p = pp
    return pid


def read(serial: str) -> dict | None:
    p = LOCKS / serial
    try:
        return dict(line.split("=", 1) for line in p.read_text().splitlines() if "=" in line)
    except FileNotFoundError:
        return None


def _create(serial: str, owner: str, pid: int, tool: str) -> bool:
    LOCKS.mkdir(parents=True, exist_ok=True)
    body = (f"owner={owner}\npid={pid}\nhost={socket.gethostname()}\ntool={tool}\n"
            f"since={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
    try:
        fd = os.open(LOCKS / serial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(body)
    return True


def _clear_if_stale(serial: str) -> bool:
    cur = read(serial)
    if cur is None:
        return True
    if cur.get("host") == socket.gethostname() and not alive(int(cur.get("pid", "0") or 0)):
        log(f"{serial}: stale lock cleared (owner {cur.get('owner')}, pid {cur.get('pid')} dead, since {cur.get('since')})")
        try:
            (LOCKS / serial).unlink()
        except FileNotFoundError:
            pass
        return True
    return False


def acquire(serial: str, owner: str, pid: int, tool: str = "stream") -> None:
    for _ in range(2):                                   # second try after clearing a stale lock
        if _create(serial, owner, pid, tool):
            log(f"{serial}: acquired by {owner} pid {pid} ({tool})")
            return
        cur = read(serial) or {}
        if cur.get("owner") == owner:
            return
        if not _clear_if_stale(serial):
            raise SystemExit(f"unit {serial} is locked by {cur.get('owner')} (pid {cur.get('pid')}, {cur.get('tool')}, "
                             f"since {cur.get('since')}); refusing. Release: scripts/unit_lock.py release {serial} --owner ...")
    raise SystemExit(f"unit {serial}: lock race, retry")


def release(serial: str, owner: str) -> None:
    cur = read(serial)
    if cur is None:
        return
    if cur.get("owner") != owner:
        raise SystemExit(f"unit {serial} is held by {cur.get('owner')}, not {owner}")
    (LOCKS / serial).unlink()
    log(f"{serial}: released by {owner}")


@contextmanager
def held(serial: str, tool: str):
    """For hardware tools: run under the caller's stream lock, or take a per-run lock."""
    owner = os.environ.get("AWTO_UNIT_OWNER", "")
    cur = read(serial)
    if cur and owner and cur.get("owner") == owner:
        yield
        return
    run_owner = owner or f"{tool}-pid{os.getpid()}"
    acquire(serial, run_owner, os.getpid(), tool)
    try:
        yield
    finally:
        cur = read(serial)
        if cur and cur.get("owner") == run_owner and cur.get("pid") == str(os.getpid()):
            (LOCKS / serial).unlink()
            log(f"{serial}: released by {run_owner} ({tool} done)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("acquire", "release", "status"))
    ap.add_argument("serial", nargs="?")
    ap.add_argument("--owner")
    ap.add_argument("--pid", type=int)
    a = ap.parse_args()
    if a.cmd == "status":
        for p in sorted(LOCKS.glob(a.serial or "*")) if LOCKS.exists() else []:
            cur = read(p.name) or {}
            st = "alive" if alive(int(cur.get("pid", "0") or 0)) else "STALE"
            print(f"{p.name}: {cur.get('owner')} pid {cur.get('pid')} ({st}) {cur.get('tool')} since {cur.get('since')}")
        return 0
    if not a.serial or not a.owner:
        ap.error("acquire/release need SERIAL and --owner")
    if a.cmd == "acquire":
        acquire(a.serial, a.owner, a.pid or session_pid())
    else:
        release(a.serial, a.owner)
    return 0


if __name__ == "__main__":
    sys.exit(main())

