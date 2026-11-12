#!/usr/bin/env python3
"""Host display power (Mutter PowerSaveMode) for tests, with a guard that always turns the displays back on (#159).

usage: host_dpms.py on | off --guard-s S | status | guard TOKEN DEADLINE
- off(guard_s): PowerSaveMode 3, then starts a detached guard process (own session: survives the test's death, SIGKILL,
  agent teardown) that sets PowerSaveMode 0 at the deadline unless on() ran first. on(): PowerSaveMode 0, guard cancelled.
- A test that hangs or dies leaves the displays off for at most guard_s, never until Dan reboots (2026-11-12 12:03).
- off() refuses while Dan is at the desk (desktop idle < IDLE_MIN_S): blank screens look like a dead PC and get the
  reset switch (09:06, 12:03, 12:14 that day). AWTO_DPMS_FORCE=1 overrides.
Log: tmp/logs/host_dpms.log
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


ROOT = _repo()
LOG = ROOT / "tmp" / "logs" / "host_dpms.log"
TOKEN = ROOT / "tmp" / "host_dpms.guard"      # present = displays off under a guard; content = deadline (epoch s)
GDBUS_S = 5.0                                  # one D-Bus property set, normally < 0.1 s; expiry -> logged, guard still runs
GUARD_POLL_S = 0.5                             # guard checks for a cancel; displays come back within 0.5 s of the deadline
IDLE_MIN_S = 300.0                             # = GNOME idle-delay: the desktop would blank itself by then anyway
DPMS_FILES = sorted(Path("/sys/class/drm").glob("card*-*/dpms"))


def log(msg: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def set_mode(mode: int) -> bool:
    try:
        r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.DisplayConfig", "--object-path",
                            "/org/gnome/Mutter/DisplayConfig", "--method", "org.freedesktop.DBus.Properties.Set",
                            "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", f"<int32 {mode}>"],
                           capture_output=True, text=True, timeout=GDBUS_S)
    except subprocess.TimeoutExpired:
        log(f"PowerSaveMode {mode}: gdbus timed out after {GDBUS_S} s")
        return False
    if r.returncode:
        log(f"PowerSaveMode {mode}: gdbus rc={r.returncode} {r.stderr.strip()}")
    return r.returncode == 0


def status() -> str:
    return " ".join(f"{f.parent.name.split('-', 1)[1]}={f.read_text().strip()}" for f in DPMS_FILES
                    if (f.parent / "status").read_text().strip() == "connected")


def idle_s() -> float | None:
    try:
        r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor", "--object-path",
                            "/org/gnome/Mutter/IdleMonitor/Core", "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
                           capture_output=True, text=True, timeout=GDBUS_S)
        return int(r.stdout.split()[1].rstrip(",)")) / 1000 if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, IndexError, ValueError):
        return None


class UserPresent(RuntimeError):
    pass


def off(guard_s: float) -> bool:
    """displays off; a detached guard turns them on after guard_s unless on() runs first.
    Raises UserPresent if someone used the desktop in the last IDLE_MIN_S."""
    idle = idle_s()
    if os.environ.get("AWTO_DPMS_FORCE") != "1" and (idle is None or idle < IDLE_MIN_S):
        log(f"off refused: desktop idle {idle} s < {IDLE_MIN_S:.0f} s (Dan at the desk); AWTO_DPMS_FORCE=1 overrides")
        raise UserPresent(f"host screens stay on: desktop idle {idle} s < {IDLE_MIN_S:.0f} s")
    deadline = time.time() + guard_s
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(f"{deadline:.3f}\n")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "guard", str(TOKEN), f"{deadline:.3f}"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, cwd=ROOT)
    log(f"off: guard armed, displays forced on in {guard_s:.0f} s if nobody turns them on")
    return set_mode(3)


def on() -> bool:
    TOKEN.unlink(missing_ok=True)
    return set_mode(0)


def guard(token: Path, deadline: float) -> int:
    while time.time() < deadline:
        if not token.exists() or token.read_text().strip() != f"{deadline:.3f}":
            return 0                           # on() ran, or a newer off() armed its own guard
        time.sleep(GUARD_POLL_S)
    if token.exists() and token.read_text().strip() == f"{deadline:.3f}":
        token.unlink(missing_ok=True)
        log("ALERT guard: deadline passed with the displays still off (test died or hung); PowerSaveMode 0")
        set_mode(0)
    return 0


def main() -> int:
    a = sys.argv[1:]
    if a[:1] == ["on"]:
        ok = on()
        log(f"on: {status()}")
        return 0 if ok else 1
    if a[:1] == ["off"] and a[1:2] == ["--guard-s"] and len(a) == 3:
        try:
            return 0 if off(float(a[2])) else 1
        except UserPresent as e:
            print(e)
            return 3
    if a[:1] == ["status"]:
        print(status())
        return 0
    if a[:1] == ["guard"] and len(a) == 3:
        return guard(Path(a[1]), float(a[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
