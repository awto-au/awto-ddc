#!/usr/bin/env python3
"""KVM input switch for all our monitors at once (#60): DDC/CI VCP 0x60, one process per bus, in parallel.

usage: kvm.py <D1|D2|D3|dp|hdmi1|hdmi2|next|here> [--units 1,2,3] [--ddcutil] [--verify] [--dry-run]
- Bus per unit = the one whose EDID serial is the unit's (connector i2c link first; NVIDIA has none: scan display buses).
- Raw path: i2cbus (the only /dev/i2c toucher, #48) to 0x37. --ddcutil: `ddcutil --bus N setvcp 60 0xNN --noverify`.
- next: getvcp 0x60 on the first unit, then the next of D1 -> D2 -> D3 -> D1 for every unit.
- here: each unit gets its own current input back (getvcp, then setvcp the same value; the firmware ignores a switch to
  where it is): times a parallel all-monitor command without losing a single-cable unit's picture or its DDC/CI.
- Firmware side: fw/sdcc/awto_ddcci.inc (wb-p14kvm). With _AWTO_DDCCI_ENGINES 1 only the host on the active port reaches 0x37.
Log: ./tmp/logs/kvm.log (one decoded line per monitor + the wall time)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus  # noqa: E402


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[1]


REPO = _repo()
LOG = REPO / "tmp/logs/kvm.log"
DDCCI = 0x37
VCP_INPUT = 0x60
PORTS = {"D1": 0x0F, "dp": 0x0F, "D2": 0x11, "hdmi1": 0x11, "D3": 0x12, "hdmi2": 0x12}    # MCCS 0x60 values (our board)
NAMES = {0x0F: "D1 DP", 0x11: "D2 HDMI1", 0x12: "D3 HDMI2"}
CYCLE = [0x0F, 0x11, 0x12]
REPLY_WAIT_S = 0.040        # MCCS/DDC-CI: host waits >= 40 ms between a request and its reply read
READ_TRIES = 3              # null message (6E 80 BE) = firmware not ready (main loop blocked by an OSD draw): re-read
# raw: write ~1 ms + up to 3 x (40 ms wait + 11-byte read ~1 ms) = ~130 ms worst for a get; x1.25 -> per-unit limit below
RAW_LIMIT_S = 0.17
# ddcutil: setvcp 0.1-0.2 s, worst 1.37 s (getvcp after a power change, docs/ddc-control.md 2026-11-04); x1.25
DDCUTIL_LIMIT_S = 1.7


def log(line: str) -> None:
    s = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}"
    print(s)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(s + "\n")


def units() -> dict:
    return json.loads((REPO / "scripts/devices.json").read_text())["units"]


def _ddcci_acks(bus: int) -> bool:
    try:
        with i2cbus.Bus(bus) as b:
            b.raw_read(DDCCI, 1)            # an idle DDC/CI slave answers with its null message
        return True
    except OSError:
        return False


BUS_CACHE = _repo() / "tmp/kvm_bus.json"       # serial -> bus of the last switch; checked by one EDID read + 0x37 ACK


def find_bus(u: dict) -> int | None:
    """The unit's bus that answers DDC/CI: a unit cabled twice (unit 3: HDMI + DP) only has 0x37 where the engine sits."""
    try:
        b = json.loads(BUS_CACHE.read_text()).get(u["serial"])
        if b is not None and i2cbus.edid_serial(b) == u["serial"] and _ddcci_acks(b):
            return b
    except (OSError, ValueError):
        pass
    b = _find_bus_scan(u)
    if b is not None:
        try:
            d = json.loads(BUS_CACHE.read_text()) if BUS_CACHE.is_file() else {}
            d[u["serial"]] = b
            BUS_CACHE.write_text(json.dumps(d))     # one process per bus writes its own key; a lost race only costs a rescan
        except (OSError, ValueError):
            pass
    return b


def _find_bus_scan(u: dict) -> int | None:
    cands = []
    for c in (u["connector"], u.get("connector_dp")):
        link = (Path("/sys/class/drm") / c / "ddc").resolve() if c else Path("x")
        if link.name.startswith("i2c-"):
            cands.append(int(link.name.split("-")[1]))
    cands += [b for b in i2cbus.list_buses(display_only=True) if b not in cands]
    mine = [b for b in cands if i2cbus.edid_serial(b) == u["serial"]]
    return next((b for b in mine if _ddcci_acks(b)), mine[0] if mine else None)


def _chk(start: int, data: bytes) -> int:
    for x in data:
        start ^= x
    return start


def raw_set(bus: int, value: int) -> None:
    body = bytes([0x84, 0x03, VCP_INPUT, 0x00, value])
    with i2cbus.Bus(bus) as b:
        b.write(DDCCI, 0x51, body + bytes([_chk(0x6E ^ 0x51, body)]))


def raw_get(bus: int, vcp: int) -> int:
    body = bytes([0x82, 0x01, vcp])
    with i2cbus.Bus(bus) as b:
        b.write(DDCCI, 0x51, body + bytes([_chk(0x6E ^ 0x51, body)]))
        for _ in range(READ_TRIES):
            time.sleep(REPLY_WAIT_S)        # spec reply wait, not a poll
            r = b.raw_read(DDCCI, 11)
            if r[:2] == b"\x6e\x80" or r[:3] == body[:3]:
                continue                    # null message, or our request still in the engine buffer (main loop busy): not ready
            if r[0] != 0x6E or r[1] != 0x88 or r[2] != 0x02 or _chk(0x50, r[:10]) != r[10]:
                raise OSError(f"bad reply {r.hex(' ')}")
            if r[3] != 0:
                raise OSError(f"VCP 0x{vcp:02X} unsupported (rc {r[3]})")
            return (r[8] << 8) | r[9]
    raise OSError(f"no reply after {READ_TRIES} reads")


def ddcutil(bus: int, *args: str) -> str:
    r = subprocess.run(["ddcutil", "--bus", str(bus), *args], capture_output=True, text=True, timeout=DDCUTIL_LIMIT_S)
    if r.returncode:
        raise OSError(f"ddcutil rc={r.returncode}: {(r.stderr or r.stdout).strip()[:120]}")
    return r.stdout


def get_input(bus: int, use_ddcutil: bool) -> int:
    if use_ddcutil:
        m = re.search(r"VCP 60 SNC x([0-9a-fA-F]+)", ddcutil(bus, "getvcp", "60", "--brief"))
        if not m:
            raise OSError("ddcutil getvcp 60: no value")
        return int(m.group(1), 16)
    return raw_get(bus, VCP_INPUT)


def switch_one(job: tuple) -> tuple:
    """Worker (one process per bus): returns (unit, bus, value, set ms, bus-lookup ms, error, read-back)."""
    n, u, value, use_ddcutil, verify = job
    t0 = time.monotonic()
    bus = find_bus(u)
    t_bus = time.monotonic()
    if bus is None:
        return n, None, value, 0.0, (t_bus - t0) * 1000, "no bus with that EDID serial", None
    try:
        if value is None:                   # here
            value = get_input(bus, use_ddcutil)
            time.sleep(REPLY_WAIT_S)        # spec gap before the next request
        if use_ddcutil:
            ddcutil(bus, "setvcp", "60", f"0x{value:02x}", "--noverify")
        else:
            raw_set(bus, value)
        ms = (time.monotonic() - t_bus) * 1000
        got = None
        if verify:
            time.sleep(REPLY_WAIT_S)        # spec gap before the next request
            got = get_input(bus, use_ddcutil)
        return n, bus, value, ms, (t_bus - t0) * 1000, None, got
    except (OSError, subprocess.TimeoutExpired) as e:
        return n, bus, value, (time.monotonic() - t_bus) * 1000, (t_bus - t0) * 1000, repr(e), None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=[*PORTS, "next", "here"])
    ap.add_argument("--units", default="", help="comma list (default: every unit in scripts/devices.json)")
    ap.add_argument("--ddcutil", action="store_true")
    ap.add_argument("--verify", action="store_true", help="getvcp 0x60 after the set")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; no I2C traffic")
    a = ap.parse_args()
    all_u = units()
    sel = [x for x in (a.units.split(",") if a.units else sorted(all_u)) if x]
    bad = [x for x in sel if x not in all_u]
    if bad:
        raise SystemExit(f"unknown unit(s) {bad}: see scripts/devices.json")
    how = "ddcutil" if a.ddcutil else "raw i2c 0x37"
    if a.dry_run:
        for n in sel:
            log(f"dry-run: unit {n} {all_u[n]['serial']} ({all_u[n]['connector']}): setvcp 0x60 "
                + ("<next of first unit>" if a.target == "next" else "<its own input>" if a.target == "here"
                   else f"0x{PORTS[a.target]:02X} ({NAMES[PORTS[a.target]]})")
                + f" via {how}; bus by EDID serial at run time")
        return 0
    t0 = time.monotonic()
    if a.target == "next":
        first = all_u[sel[0]]
        bus = find_bus(first)
        if bus is None:
            raise SystemExit(f"next: unit {sel[0]} has no bus with its EDID serial")
        cur = get_input(bus, a.ddcutil)
        value = CYCLE[(CYCLE.index(cur) + 1) % len(CYCLE)] if cur in CYCLE else CYCLE[0]
        log(f"next: unit {sel[0]} reports 0x{cur:02X} ({NAMES.get(cur, '?')}) -> 0x{value:02X} ({NAMES[value]})")
    else:
        value = None if a.target == "here" else PORTS[a.target]
    jobs = [(n, all_u[n], value, a.ddcutil, a.verify) for n in sel]
    limit = (DDCUTIL_LIMIT_S if a.ddcutil else RAW_LIMIT_S) * (1 + a.verify + (value is None)) + 2.0     # + bus scan (EDID reads)
    rc = 0
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        futs = [ex.submit(switch_one, j) for j in jobs]
        for f in futs:
            try:
                n, bus, v, ms, bus_ms, err, got = f.result(timeout=limit)
            except Exception as e:      # TimeoutError: a hung bus; the pool shuts down with the others' results kept
                log(f"FAIL worker: {e!r} (limit {limit:.2f} s)")
                rc = 1
                continue
            s = all_u[n]["serial"]
            if err:
                rc = 1
                log(f"FAIL unit {n} {s} bus {bus}: 0x60 <- 0x{v:02X} ({NAMES[v]}) via {how}: {err} after {ms:.0f} ms")
            else:
                ver = "" if got is None else f"; reads back 0x{got:02X} {'ok' if got == v else 'MISMATCH'}"
                rc |= int(got is not None and got != v)
                log(f"unit {n} {s} bus {bus}: 0x60 <- 0x{v:02X} ({NAMES[v]}) via {how} in {ms:.0f} ms "
                    f"(bus lookup {bus_ms:.0f} ms){ver}")
    log(f"kvm {a.target}: {len(jobs)} monitor(s), wall {(time.monotonic() - t0) * 1000:.0f} ms, rc {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
