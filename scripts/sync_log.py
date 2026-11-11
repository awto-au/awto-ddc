#!/usr/bin/env python3
"""Decode the #139 sync / power-on log ring (firmware g_stAwtoSync) into the same lines the monitor shows.

usage: sync_log.py BUS --map MAP [--tsv TSV] [--serial SERIAL]      read over the debug slave 0x35 and print the episode
       (library) decode(raw, rows) -> (header dict, [lines]); load_rows(tsv); tsv_for(map)
- Texts and value formats: the firmware tree's fw/awto/sync.tsv (one file for screen and host). Default TSV = the image's
  <map stem>.sync.tsv (wb_build.py copies it beside the image), else $AWTO_SYNC_TSV.
- Ring layout (RL6449_Project.h StAwtoSync, bytes only): 12 B header, 24 x 8 B entries {id, arg, ms hi, ms lo, value BE x4}.
Log: tmp/logs/sync_log.log
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/sync_log.log"
HDR, N, EV, WRAP = 12, 24, 8, 240         # AWTO_SYNC_N / AWTO_SYNC_WRAP: seq 0..239, entry = seq % N
D0 = 3                                                   # _D0_INPUT_PORT
SRC = {2: "DVI", 3: "HDMI", 4: "DP"}
DP_RATE = {0x06: "RBR", 0x0A: "HBR", 0x14: "HBR2", 0x1E: "HBR3"}
KINDS = {1: "power on", 2: "switch", 3: "wake", 4: "power key on"}


def log(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def load_rows(tsv: Path) -> list[dict]:
    out = []
    for ln in tsv.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        i, a, f, t = ln.split("\t")
        port = f.startswith("port")
        out.append(dict(id=int(i, 16), arg=None if a == "*" else int(a, 16), port=port, fmt=f[4:] if port else f, text=t))
    return out


def tsv_for(map_path: Path) -> Path:
    p = map_path.with_suffix(".sync.tsv")
    if p.exists():
        return p
    env = os.environ.get("AWTO_SYNC_TSV")
    if env:
        return Path(env)
    raise SystemExit(f"no sync.tsv beside {map_path} and no $AWTO_SYNC_TSV")


def milli(v: int) -> str:
    return f"{v // 1000}.{v % 1000:03d}"


def tenths(v: int) -> str:
    return f"{v // 10}.{v % 10}"


def value(fmt: str, arg: int, v: int) -> str:
    if fmt == "vport":
        return "auto" if (v & 0xFF) == 0xFF else f"D{(v & 0xFF) - D0}"
    if fmt == "res":
        return f"{v >> 16}x{v & 0xFFFF}"
    if fmt == "mhz1":
        return tenths(v) + " MHz"
    if fmt == "hz1":
        return tenths(v) + " Hz"
    if fmt == "hz3":
        return milli(v) + " Hz"
    if fmt == "mhz3":
        return milli(v) + " MHz"
    if fmt == "dp":
        r = (v >> 8) & 0xFF
        return f"{DP_RATE.get(r, f'{r:02X}')} x{v & 0xFF}"
    if fmt == "src":
        return SRC.get(v, str(v))
    if fmt == "harg":
        return f"{arg:02X}"
    return ""


def line(rows: list[dict], ev: tuple, t0: int) -> str:
    i, a, ms, v = ev
    dt = (ms - t0) & 0xFFFF
    head = f"+{dt:5d} ms "
    row = next((r for r in rows if r["id"] == i and (r["arg"] is None or r["arg"] == a)), None)
    if row is None:
        return head + f"event {i:02X} {a:02X}"
    pre = f"D{a - D0} " if row["port"] else ""
    before, _, after = row["text"].partition("%")
    return head + pre + before + value(row["fmt"], a, v) + after


def decode(raw: bytes, rows: list[dict]):
    h = dict(magic=raw[0:2], version=raw[2], seq=raw[3], ep_seq=raw[4], kind=raw[5], port=raw[6],
             t0=raw[7] << 8 | raw[8], done=raw[9], open_req=raw[10])
    if h["magic"] != b"SY":
        return h, []
    n = (h["seq"] - h["ep_seq"]) % WRAP
    lost = max(0, n - N)
    evs = []
    for k in range(min(n, N)):
        s = (h["seq"] - min(n, N) + k) % WRAP
        e = raw[HDR + EV * (s % N):HDR + EV * (s % N) + EV]
        evs.append((e[0], e[1], e[2] << 8 | e[3], int.from_bytes(e[4:8], "big")))
    h["lost"] = lost
    return h, [line(rows, ev, h["t0"]) for ev in evs]


def sym(map_path: Path, name: str) -> int:
    m = re.search(rf"^D:\s+([0-9A-F]{{8}})\s+_{name}\b", map_path.read_text(errors="replace"), re.M)
    if not m:
        raise SystemExit(f"{name} not in {map_path}: image without the #139 sync log")
    return int(m.group(1), 16) & 0xFFFF


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--serial", help="EDID serial the bus must belong to (i2cbus.require_unit)")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_xdata as X        # noqa: E402
    import i2cbus                # noqa: E402
    import rtd_i2c_bridge as B   # noqa: E402
    if a.serial:
        i2cbus.require_unit(a.bus, a.serial)
    rows = load_rows(a.tsv or tsv_for(a.map))
    io = B.Real(a.bus, allow_write=True, regread=True)
    raw = X.read_blocks(io, sym(a.map, "g_stAwtoSync"), HDR + N * EV)
    io.close()
    if raw is None:
        log("sync: read over 0x35 failed")
        return 1
    h, lines = decode(bytes(raw), rows)
    log(f"sync episode: {KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines" + (f", {h['lost']} older lines overwritten" if h.get("lost") else ""))
    for ln in lines:
        log("  " + ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
