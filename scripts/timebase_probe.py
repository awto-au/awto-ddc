#!/usr/bin/env python3
"""Check the firmware ring clock against the host clock across a cold power-up (awto-ddc#144 boot profile).

usage: timebase_probe.py --unit 2 --bus 11 [--run-s 4]
- Polls bus slaves 0x50 (EDID RAM), 0x37 (DDC/CI / ISP slave) and a DDC/CI get-VCP reply (= main loop running) with host
  CLOCK_MONOTONIC stamps, switches the unit's mains relay on (hass_power.py) after the bus has been seen dead, prints the
  first-seen time of each. Compare the host deltas with the ring deltas of the same boot (sync_log.py).
- Host deltas, not absolute times: the relay-to-mains latency is not part of the result.
Log: ./tmp/logs/timebase_probe.log
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus  # noqa: E402

ROOT = i2cbus.ROOT
LOG = ROOT / "tmp/logs/timebase_probe.log"
DDC_EDID, DDC_CI = 0x50, 0x37
SRC, GETVCP_BRIGHTNESS = 0x51, 0x10
DEAD_S = 0.5            # bus must NACK this long before the relay goes on (relay is off: bus is dead anyway)
RELAY_S = 5.0           # HA REST call + relay on, normally < 0.5 s (hass_power HTTP_S)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def getvcp_alive(b: i2cbus.Bus) -> bool:
    body = bytes([0x82, 0x01, GETVCP_BRIGHTNESS])
    chk = 0x6E ^ SRC
    for x in body:
        chk ^= x
    try:
        b.write(DDC_CI, SRC, body + bytes([chk]))
        rep = b.raw_read(DDC_CI, 11)
    except OSError:
        return False
    return len(rep) >= 3 and rep[0] == 0x6E and (rep[1] & 0x80) != 0 and rep[2] == 0x02


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--run-s", type=float, default=4.0, help="poll this long after the relay command returns")
    a = ap.parse_args()
    seen: dict[str, float] = {}
    t_cmd = t_ret = None
    proc = None
    with i2cbus.Bus(a.bus) as b:
        t0 = time.monotonic()
        while True:
            now = time.monotonic()
            if proc is None and now - t0 >= DEAD_S:
                if b.probe(DDC_CI) or b.probe(DDC_EDID):
                    say("bus not dead before the relay command: unit is on; run hass_power.py off first")
                    return 1
                t_cmd = time.monotonic()
                proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "hass_power.py"), "on",
                                         "--unit", str(a.unit)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            if proc is not None and t_ret is None and proc.poll() is not None:
                t_ret = time.monotonic()
            for name, fn in (("edid 0x50 ACK", lambda: b.probe(DDC_EDID)), ("ddc 0x37 ACK", lambda: b.probe(DDC_CI)),
                             ("ddc/ci get-VCP reply (main loop)", lambda: getvcp_alive(b))):
                if name not in seen and fn():
                    seen[name] = time.monotonic()
            if len(seen) == 3 and t_ret is not None:
                break
            if t_ret is not None and time.monotonic() - t_ret > a.run_s:
                break
            if proc is not None and time.monotonic() - t_cmd > RELAY_S + a.run_s + 5:
                say("expiry: no relay return")
                break
    say(f"relay command at host t=0, returned at {(t_ret - t_cmd) * 1000:.0f} ms" if t_ret else "relay did not return")
    first = min(seen.values()) if seen else None
    for k, v in sorted(seen.items(), key=lambda kv: kv[1]):
        say(f"  {k}: t={(v - t_cmd) * 1000:.0f} ms after the relay command, +{(v - first) * 1000:.0f} ms after the first")
    for k in ("edid 0x50 ACK", "ddc 0x37 ACK", "ddc/ci get-VCP reply (main loop)"):
        if k not in seen:
            say(f"  {k}: not seen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
