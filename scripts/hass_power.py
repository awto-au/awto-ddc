#!/usr/bin/env python3
"""Unit mains power through Home Assistant (REST): status | on | off | cycle [--off-s S] [--unit N].

- Entity: switch.<relay>_relay, relay from scripts/devices.json (unit 2: so-th-1 -> switch.so_th_1_relay).
- Credentials: HASS_SERVER / HASS_TOKEN from the environment or ~/.config/hass-cli/env (never printed).
- cycle: off, wait --off-s (default 3 s: the board's caps drain and the scaler sees a real power-up), on.
Log: tmp/logs/hass_power.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parent.parent


ROOT = _repo()
LOG = ROOT / "tmp" / "logs" / "hass_power.log"
HTTP_S = 5.0          # one HA REST call on the LAN, normally < 0.2 s; expiry -> error logged, exit 1
STATE_S = 3.0         # relay state follows the service call in < 1 s (ESPHome); expiry -> logged, exit 1
POLL_S = 0.1


def log(msg: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='milliseconds')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def creds() -> tuple[str, str]:
    srv, tok = os.environ.get("HASS_SERVER"), os.environ.get("HASS_TOKEN")
    f = Path.home() / ".config/hass-cli/env"
    if (not srv or not tok) and f.exists():
        for m in re.finditer(r"^(?:export\s+)?(HASS_SERVER|HASS_TOKEN)=['\"]?([^'\"\n]+)", f.read_text(), re.M):
            if m[1] == "HASS_SERVER":
                srv = srv or m[2]
            else:
                tok = tok or m[2]
    if not srv or not tok:
        raise SystemExit("HASS_SERVER / HASS_TOKEN not set (~/.config/hass-cli/env)")
    return srv.rstrip("/"), tok


def call(path: str, body: dict | None = None) -> dict | list:
    srv, tok = creds()
    req = urllib.request.Request(srv + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=HTTP_S) as r:
        return json.loads(r.read() or b"null")


def entity(unit: int) -> str:
    u = json.loads((ROOT / "scripts/devices.json").read_text())["units"][str(unit)]
    if not u.get("relay"):
        raise SystemExit(f"unit {unit} has no relay in devices.json")
    if not u.get("test"):
        raise SystemExit(f"unit {unit} is not a test unit: refused")
    return f"switch.{u['relay'].replace('-', '_')}_relay"


def state(ent: str) -> str:
    return call(f"/api/states/{ent}")["state"]


def setp(ent: str, on: bool) -> bool:
    call(f"/api/services/switch/turn_{'on' if on else 'off'}", {"entity_id": ent})
    end = time.monotonic() + STATE_S
    while time.monotonic() < end:
        if state(ent) == ("on" if on else "off"):
            return True
        time.sleep(POLL_S)
    log(f"{ent}: state not {'on' if on else 'off'} after {STATE_S} s")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "on", "off", "cycle"])
    ap.add_argument("--unit", type=int, default=2)
    ap.add_argument("--off-s", type=float, default=3.0)
    a = ap.parse_args()
    ent = entity(a.unit)
    if a.cmd == "status":
        log(f"unit {a.unit} {ent}: {state(ent)}")
        return 0
    if a.cmd in ("on", "off"):
        ok = setp(ent, a.cmd == "on")
        log(f"unit {a.unit} {ent}: {a.cmd} {'ok' if ok else 'FAILED'}")
        return 0 if ok else 1
    if not setp(ent, False):
        return 1
    log(f"unit {a.unit} {ent}: off, {a.off_s} s")
    time.sleep(a.off_s)                        # the off period under test (board power drained)
    ok = setp(ent, True)
    log(f"unit {a.unit} {ent}: on {'ok' if ok else 'FAILED'} (power-up at this time)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
