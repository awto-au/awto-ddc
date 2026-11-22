#!/usr/bin/env python3
"""Raw DPCD access over /dev/drm_dp_aux* (awto-ddc#254). Run with sudo -n (device is root-only).

usage: dp_aux_probe.py <unit> info | read | loop [N] | dump | speed <kbps-code-hex>
- unit -> connector via scripts/devices.json connector_dp; aux node via /sys/class/drm/<conn>/drm_dp_aux*/dev
- read: step 1 (0x000-0x00F, 0x109, 0x500-0x50B); loop: 16 B reads at 0x000; dump: 0x000-0xFFF read-only
- speed: writes DPCD 0x109 (only if 0x00C bit0..3 non-zero), prints old value; restore = same command with the old value
Log: ./tmp/logs/dp_aux_probe.log (decoded); raw bytes: ./tmp/logs/dp_aux_probe.raw.log
"""
import json
import os
import sys
import time
from pathlib import Path

from _repo import ROOT

LOGD = ROOT / "tmp" / "logs"
LOGD.mkdir(parents=True, exist_ok=True)
LOG = (LOGD / "dp_aux_probe.log").open("a")
RAW = (LOGD / "dp_aux_probe.raw.log").open("a")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def out(s: str) -> None:
    print(s); LOG.write(f"{now()} {s}\n"); LOG.flush()


def aux_node(unit: str) -> str:
    conn = json.load((ROOT / "scripts" / "devices.json").open())["units"][unit]["connector_dp"]
    d = Path("/sys/class/drm") / conn
    for p in d.glob("drm_dp_aux*"):
        return "/dev/" + p.name
    raise SystemExit(f"no drm_dp_aux under {d}")


class Aux:
    def __init__(self, path: str, rw=os.O_RDONLY):
        self.fd = os.open(path, rw)

    def read(self, addr: int, n: int) -> bytes:
        b = os.pread(self.fd, n, addr)
        RAW.write(f"{now()} R {addr:05X} {b.hex()}\n"); RAW.flush()
        return b

    def write(self, addr: int, data: bytes) -> None:
        os.pwrite(self.fd, data, addr)
        RAW.write(f"{now()} W {addr:05X} {data.hex()}\n"); RAW.flush()


NAMES = {0x000: "DPCD_REV", 0x001: "MAX_LINK_RATE", 0x002: "MAX_LANE_COUNT", 0x003: "MAX_DOWNSPREAD",
         0x004: "NORP/DP_PWR_VOLTAGE_CAP", 0x005: "DOWN_STREAM_PORT_PRESENT", 0x006: "MAIN_LINK_CHANNEL_CODING",
         0x007: "DOWN_STREAM_PORT_COUNT", 0x008: "RECEIVE_PORT0_CAP_0", 0x009: "RECEIVE_PORT0_CAP_1",
         0x00A: "RECEIVE_PORT1_CAP_0", 0x00B: "RECEIVE_PORT1_CAP_1", 0x00C: "I2C_SPEED_CONTROL_CAPS",
         0x00D: "EDP_CONFIG_CAP", 0x00E: "TRAINING_AUX_RD_INTERVAL", 0x00F: "ADAPTER_CAP",
         0x109: "I2C_SPEED_CONTROL_STATUS(set)"}


def decode_00c(v: int) -> str:
    rates = {0x01: "1k", 0x02: "5k", 0x04: "10k", 0x08: "100k", 0x10: "400k", 0x20: "1M"}
    got = [n for b, n in rates.items() if v & b]
    return "none advertised" if not got else "+".join(got) + "bps"


def cmd_read(a: Aux) -> None:
    b = a.read(0, 16)
    for i, v in enumerate(b):
        extra = f" ({decode_00c(v)})" if i == 0x0C else ""
        out(f"DPCD 0x{i:03X} {NAMES.get(i, '?')} = 0x{v:02X}{extra}")
    out(f"DPCD 0x109 {NAMES[0x109]} = 0x{a.read(0x109, 1)[0]:02X}")
    b = a.read(0x500, 12)
    out(f"DPCD 0x500-0x50B sink ident: OUI={b[0:3].hex()} devid={b[3:9]!r} hw_rev={b[9]:02X} fw={b[10]}.{b[11]}")


def cmd_loop(a: Aux, n: int) -> None:
    t0 = time.perf_counter(); err = 0
    for _ in range(n):
        try:
            a.read(0, 16)
        except OSError:
            err += 1
    dt = time.perf_counter() - t0
    ok = n - err
    out(f"loop {n} x 16 B DPCD 0x000: {dt*1000/n:.3f} ms/transaction, {ok*16/dt/1000:.2f} KB/s (1 KB=1000 B), err={err}")


def cmd_dump(a: Aux) -> None:
    rows = []
    for base in range(0, 0x1000, 16):
        try:
            rows.append((base, a.read(base, 16)))
        except OSError as e:
            rows.append((base, None)); out(f"DPCD 0x{base:03X} read error {e}")
    for base, b in rows:
        if b is not None and any(b):
            out(f"DPCD 0x{base:03X}: {b.hex(' ')}")
    nz = sum(1 for _, b in rows if b and any(b))
    out(f"dump 0x000-0xFFF: {nz}/256 rows non-zero")


def main() -> int:
    unit, cmd = sys.argv[1], sys.argv[2]
    path = aux_node(unit)
    if cmd == "info":
        out(f"unit {unit} aux node {path}"); return 0
    a = Aux(path, os.O_RDWR if cmd == "speed" else os.O_RDONLY)
    out(f"unit {unit} {cmd} via {path}")
    if cmd == "read":
        cmd_read(a)
    elif cmd == "loop":
        cmd_loop(a, int(sys.argv[3]) if len(sys.argv) > 3 else 1000)
    elif cmd == "dump":
        cmd_dump(a)
    elif cmd == "speed":
        caps = a.read(0x00C, 1)[0]
        old = a.read(0x109, 1)[0]
        new = int(sys.argv[3], 16)
        out(f"0x00C=0x{caps:02X} ({decode_00c(caps)}); 0x109 old=0x{old:02X}, writing 0x{new:02X}")
        if not caps:
            out("0x00C = 0: no speed control advertised, no write"); return 0
        a.write(0x109, bytes([new]))
        out(f"0x109 readback = 0x{a.read(0x109, 1)[0]:02X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
