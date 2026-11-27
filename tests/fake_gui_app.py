#!/usr/bin/env python3
"""Stand-in for the monitor GUI app in `./dev.py test` (#358): same control port protocol, never a unit.
- conftest.py points AWTO_GUI_LAUNCHER at this file and AWTO_GUI_SOCKET at a per-run socket; ensure_app starts it like run.py --headless.
- ping: this tree + its code stamp (no tree restart), "fake": true. quit: exits.
- passthrough: `dev.py NAME --direct ARGS --unit N` as the app's worker does, with AWTO_NO_HW=1 (i2cbus refuses, no-hw ddcutil on PATH).
- every other unit method: an error reply naming this file. Idle IDLE_EXIT_S without a request: exits (ensure_app relaunches it).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gui_client as GC

IDLE_EXIT_S = 5          # backstop for an orphan only: a later call relaunches it in ~0.2 s, so short costs nothing
# one passthrough = one dev.py --direct run that stops at argument validation (~0.3 s cold); the real app's server limit.
WORKER_LIMIT_S = GC.SERVER_LIMIT_S


def worker(p: dict) -> dict:
    name, args, unit = p.get("name"), [str(a) for a in p.get("args", [])], str(p.get("unit", ""))
    if name not in GC.ROUTED:
        return {"ok": False, "error": f"passthrough: {name!r} is not a routed command {sorted(GC.ROUTED)}"}
    env = {**os.environ, "AWTO_GUI_WORKER": "1", "AWTO_NO_HW": "1"}
    try:
        r = subprocess.run([sys.executable, str(ROOT / "dev.py"), name, "--direct", *args, *(["--unit", unit] if unit else [])],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=WORKER_LIMIT_S, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"fake app: {name} {args} gave no exit in {WORKER_LIMIT_S} s"}
    out = r.stdout + r.stderr
    res = {"rc": r.returncode, "output": out}
    return {"ok": True, "result": res} if r.returncode == 0 else {"ok": False, "result": res, "error": f"{name} failed (rc {r.returncode})"}


def handle(req: dict, path: Path) -> tuple[dict, bool]:
    m, p = str(req.get("method")), req.get("params") or {}
    if m == "ping":
        return {"ok": True, "result": {"pid": os.getpid(), "headless": True, "protocol": GC.PROTOCOL, "socket": str(path), "fake": True,
                                       "root": str(ROOT), "head": GC.git_head(ROOT), "code": GC.code_stamp(ROOT), "busy": []}}, False
    if m == "quit":
        return {"ok": True, "result": {"quitting": True}}, True
    if m == "passthrough":
        return worker(p), False
    return {"ok": False, "error": f"fake test app ({Path(__file__).name}): {m} needs a unit; ./dev.py test never reaches one (#358)"}, False


def serve(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}")
    tmp.unlink(missing_ok=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(tmp))
    os.chmod(tmp, 0o600)                       # gui_client.check_socket refuses anything wider
    os.replace(tmp, path)
    s.listen(8)
    s.settimeout(IDLE_EXIT_S)
    try:
        while True:
            try:
                c, _ = s.accept()
            except TimeoutError:
                print(f"fake app: no request for {IDLE_EXIT_S} s, exiting", flush=True)
                return 0
            with c, c.makefile("rwb") as f:
                for line in f:
                    t0 = time.monotonic()
                    req = json.loads(line)
                    rep, stop = handle(req, path)
                    f.write(json.dumps({"id": req.get("id"), "elapsed_ms": int((time.monotonic() - t0) * 1000), **rep}).encode() + b"\n")
                    f.flush()
                    if stop:
                        return 0
    finally:
        s.close()
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(serve(GC.socket_path()))
