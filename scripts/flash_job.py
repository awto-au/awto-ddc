#!/usr/bin/env python3
"""Detached flash job (awto-ddc#276): own process session, survives the app (a flash killed half-way left a unit half-erased, #156).
usage (internal, started by start()): flash_job.py run JOBFILE; holds unit_lock for the whole flash, runs argv, writes log + rc.
Job file tmp/flash_jobs/<serial>.json; env AWTO_FLASH_JOBS_DIR / AWTO_LOCK_DIR redirect for tests. Details: docs/monitor-gui.md "Flash"."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import unit_lock

JOBS = Path(os.environ.get("AWTO_FLASH_JOBS_DIR") or unit_lock.LOCKS.parent / "flash_jobs")
SPAWN_WAIT_S = 2                                     # python start ~0.05 s x ~40; expiry: SystemExit, no flash started by the app
SPAWN_POLL_S = 0.02
LAST_LINES = 20                                      # log lines kept for the panel
ERR_RE = re.compile(r"\bERROR\b|refuse|REFUSED|FAILED|Traceback")
RECOVER_RE = re.compile(r"\brecover \(|ISP recoveries (\d+)")
REDO_RE = re.compile(r"redo sector|burst failures redone in byte mode: (\d+)")
SECTORS_RE = re.compile(r"(erased|written\+verified) (\d+)/(\d+) sectors")
PER_SECTOR_RE = re.compile(r"per-sector mode: (\d+) sectors")
ERASED_ALL_RE = re.compile(r"erased (\d+) sectors \(")
SUMMARY_RE = re.compile(r"burst failures redone in byte mode: (\d+); ISP recoveries (\d+)")


def job_path(serial: str) -> Path:
    return JOBS / f"{serial}.json"


def wrapper_alive(pid: int) -> bool:
    """the wrapper pid exists AND is a flash_job.py process (a reused pid of some other program is not our wrapper)"""
    if not unit_lock.alive(pid):
        return False
    try:
        return b"flash_job.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return True                                   # no /proc entry to judge by: trust the signal-0 answer


def load(serial: str) -> dict | None:
    """the job record. A record that is not finished but has no live wrapper (never got a pid, or its pid is gone) is closed here
    as rc 255 with an error and a log line: nothing is ever left 'running' on disk without a process behind it"""
    try:
        job = json.loads(job_path(serial).read_text())
    except (FileNotFoundError, ValueError):
        return None
    if "rc" in job:
        return job
    pid = int(job.get("pid") or 0)
    why = None
    if not pid:
        if time.time() - job.get("started_mono_wall", 0) > 2 * SPAWN_WAIT_S:
            why = "the wrapper never started (no pid)"
    elif not wrapper_alive(pid):
        why = f"the wrapper pid {pid} is gone without a result"
    if why:
        job = {**job, "rc": 255, "finished": isostamp.now(), "error": f"stale: {why}"}
        save(job)
        unit_lock.log(f"flash job {serial} {job.get('id')}: stale record closed as rc 255 ({why})")
    return job


def clean() -> list[str]:
    """delete finished (reported or stale) records and their logs; returns the serials. Human: python3 scripts/flash_job.py clean"""
    gone = []
    for p in sorted(JOBS.glob("*.json")):
        job = load(p.stem)
        if job and "rc" in job and (job.get("reported") or job.get("error")):
            p.unlink()
            if job.get("log"):
                Path(job["log"]).unlink(missing_ok=True)
            gone.append(p.stem)
    return gone


def save(job: dict) -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    p = job_path(job["serial"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job))
    os.replace(tmp, p)


def running(job: dict | None) -> bool:
    """started and not finished: the wrapper pid is alive and no rc recorded (a dead wrapper without rc = lost, reported by the app)"""
    return bool(job) and "rc" not in job and wrapper_alive(int(job.get("pid") or 0))


def lost(job: dict | None) -> bool:
    return bool(job) and "rc" not in job and not wrapper_alive(int(job.get("pid") or 0))


def start(serial: str, unit: str, argv: list[str], python: str = sys.executable) -> dict:
    """write the job file and spawn the detached wrapper; returns the job (pid filled in)"""
    cur = load(serial)
    if running(cur):
        raise SystemExit(f"unit {serial}: a flash job is already running (pid {cur['pid']}, started {cur['started']})")
    lk = unit_lock.read(serial)
    if lk and unit_lock.alive(int(lk.get("pid", "0") or 0)):
        raise SystemExit(f"unit {serial} is locked by {lk.get('owner')} (pid {lk.get('pid')}, {lk.get('tool')}); not starting a flash")
    JOBS.mkdir(parents=True, exist_ok=True)
    jid = time.strftime("%Y%m%d-%H%M%S")
    job = {"id": jid, "unit": unit, "serial": serial, "argv": [str(a) for a in argv], "started": isostamp.now(),
           "started_mono_wall": time.time(), "log": str(JOBS / f"{serial}.{jid}.log")}
    save(job)
    try:
        proc = subprocess.Popen([python, str(Path(__file__).resolve()), "run", str(job_path(serial))], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, cwd=unit_lock.ROOT)
        threading.Thread(target=proc.wait, daemon=True).start()      # reap the wrapper when it ends: no zombie left looking alive
    except OSError as e:
        save({**job, "rc": 255, "finished": isostamp.now(), "error": repr(e)})      # no stuck job file
        raise SystemExit(f"flash job for {serial}: could not start the wrapper ({python}): {e!r}") from None
    t0 = time.monotonic()
    while time.monotonic() - t0 < SPAWN_WAIT_S:       # the wrapper's first act is writing its pid into the job file
        cur = load(serial)
        if cur and cur.get("id") == jid and cur.get("pid"):
            return cur
        time.sleep(SPAWN_POLL_S)
    save({**job, "rc": 255, "finished": isostamp.now(), "error": "wrapper never reported its pid"})
    raise SystemExit(f"flash job for {serial}: wrapper did not report its pid in {SPAWN_WAIT_S} s (python start is ~0.05 s); see {job['log']}")


class Progress:
    """incremental parse of the flash log (rtd_flash_image / dev.py lines) into what the GUI shows"""

    def __init__(self, started_wall: float):
        self.t0 = started_wall
        self.phase, self.total, self.erased, self.written = "starting", 0, 0, 0
        self.per_sector, self.errors, self.recoveries, self.redo = False, 0, 0, 0
        self.last: list[str] = []
        self.rc: int | None = None

    def feed(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        self.last = (self.last + [line])[-LAST_LINES:]
        if m := PER_SECTOR_RE.search(line):
            self.per_sector, self.total = True, int(m.group(1))
        if m := SECTORS_RE.search(line):
            k, n = int(m.group(2)), int(m.group(3))
            self.total = n
            if m.group(1) == "erased":
                self.erased, self.phase = k, "erase"
            else:
                self.written, self.phase = k, "write"
        elif m := ERASED_ALL_RE.search(line):
            self.erased = self.total = int(m.group(1))
        if "ISP enter" in line or "status reg" in line:
            self.phase = self.phase if self.phase in ("erase", "write") else "isp"
        if "final CRC OK" in line or "VERIFY OK" in line:
            self.phase = "verify"
        if m := SUMMARY_RE.search(line):
            self.redo, self.recoveries = int(m.group(1)), int(m.group(2))
        else:
            if RECOVER_RE.search(line):
                self.recoveries += 1
            if "redo sector" in line:
                self.redo += 1
        if ERR_RE.search(line):
            self.errors += 1

    def percent(self) -> float:
        if not self.total:
            return 0.0
        done = self.written if self.per_sector else (self.erased + self.written) / 2
        return round(min(100.0, 100.0 * done / self.total), 1)

    def snapshot(self, now: float | None = None) -> dict:
        el = (now or time.time()) - self.t0
        pct = self.percent()
        return {"phase": "done" if self.rc == 0 else "failed" if self.rc else self.phase, "percent": pct, "erased": self.erased,
                "written": self.written, "total": self.total, "elapsed_s": round(el, 1),
                "eta_s": round(el * (100 - pct) / pct, 1) if 0 < pct < 100 and self.rc is None else None,
                "errors": self.errors, "recoveries": self.recoveries, "redo": self.redo, "rc": self.rc, "last": list(self.last)}


def run(jobfile: Path) -> int:
    job = json.loads(jobfile.read_text())
    signal.signal(signal.SIGHUP, signal.SIG_IGN)      # the terminal / app going away must not stop the flash
    job["pid"] = os.getpid()
    save(job)
    owner = f"gui-flash-{job['serial']}-{job['id']}"

    def finish(rc: int) -> int:
        cur = load(job["serial"]) or job
        if cur.get("id") == job["id"]:
            save({**cur, "rc": rc, "finished": isostamp.now()})
        return rc

    with open(job["log"], "a", buffering=1) as logf:
        try:
            unit_lock.acquire(job["serial"], owner, os.getpid(), tool="flash")
        except SystemExit as e:
            logf.write(f"{isostamp.now()} ERROR: {e}\n")
            return finish(1)
        try:
            env = {**os.environ, "AWTO_UNIT_OWNER": owner, "AWTO_GUI_WORKER": "1"}
            rc = subprocess.Popen(job["argv"], stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env,
                                  cwd=unit_lock.ROOT).wait()
        finally:
            try:
                unit_lock.release(job["serial"], owner)
            except SystemExit:
                pass
    return finish(rc)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        sys.exit(run(Path(sys.argv[2])))
    if sys.argv[1:] == ["clean"]:
        print("removed:", " ".join(clean()) or "nothing")
        sys.exit(0)
    sys.exit("flash_job.py is started by the GUI app (start()); see the module docstring")
