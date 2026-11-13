#!/usr/bin/env python3
"""Dump + decode the 4K60 measurement ring (awto-ddc#26): firmware side fw/meas/meas4k.c, layout RL6449_Project.h StAwtoMeas.

usage: meas4k_dump.py --unit N [--map F] [--tag NAME]     live: block reads (0x3C) over debug slave 0x35
       meas4k_dump.py --file RAW [--tag NAME]             decode a saved raw ring (or a sim dump)
  Output: one line per sample, then the call/event list; both to ./tmp/logs/meas4k_<tag>.log and stdout.
  Re-arm for the next capture (state byte 0): ./dev.py dbg-write --unit N <addr+3 hex>=00 (address printed by this tool).
Layout (SDCC big-endian: WORD = high byte first): header 16 B (byte 7 = sample slots, version 2), samples x 17 B, 40 events x 6 B.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HDR, EVENTS = 16, 40
REC, EVREC = 17, 6
STATE = {0: "idle", 1: "sampling", 2: "done"}
MODE = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
EVNAME = {1: "MDomainControl enter", 2: "MemoryInitial", 3: "FrameSyncSetDt", 4: "SetDisplayFormat(LINE_BUF)",
          5: "FineTuneLineBuffer call", 6: "VgipAdjustIHVDelay", 7: "ControlDBApply", 8: "SetDPLLSSC",
          9: "WaitForEvent(IVS) #1", 10: "MemoryReset", 14: "P0_02 clear + IVS wait #2 next", 11: "MemoryCheck call",
          13: "MemoryCheck+TimingGenCheck OK", 30: "FineTune enter", 31: "FineTune loop (arg=debounce, val=new offset)",
          32: "FineTune final offset (val)", 33: "FineTune exit"}
COLS = ("P0_02", "P0_0C", "P5_B0", "P45_B0", "P5_2B", "P45_2B", "P0_3D", "P0_3E", "P0_40", "P0_41", "P0_45", "P1_C4", "P1_C5", "P0_28")


def u16(b: bytes, i: int) -> int:
    return (b[i] << 8) | b[i + 1]


def decode(b: bytes) -> dict:
    if len(b) < HDR or b[:2] != b"MK" or len(b) < HDR + b[7] * REC + EVENTS * EVREC:
        raise ValueError(f"not a meas4k ring: {len(b)} B, magic {b[:2]!r}")
    SAMPLES = b[7]
    h = {"version": b[2], "state": b[3], "arms": b[4], "nsamp": b[5], "nev": b[6],
         "start": u16(b, 8), "next": u16(b, 10), "end": u16(b, 12)}
    s = []
    for k in range(min(h["nsamp"], SAMPLES)):
        r = b[HDR + k * REC: HDR + (k + 1) * REC]
        s.append({"ms": u16(r, 0), "mode": r[2], **{n: r[3 + i] for i, n in enumerate(COLS)}})
    ev = []
    for k in range(min(h["nev"], EVENTS)):
        r = b[HDR + SAMPLES * REC + k * EVREC: HDR + SAMPLES * REC + (k + 1) * EVREC]
        ev.append({"ms": u16(r, 0), "id": r[2], "arg": r[3], "val": u16(r, 4)})
    return {"hdr": h, "samples": s, "events": ev}


def p0_02_flags(v: int) -> str:
    names = {0: "udf1", 1: "ovf1", 5: "ihs/ivs err", 6: "ihs/ivs err"}
    return ",".join(n for bit, n in names.items() if v >> bit & 1)


def render(d: dict, tag: str) -> list[str]:
    h, t0 = d["hdr"], d["hdr"]["start"]
    out = [f"meas4k {tag}: state {STATE.get(h['state'], h['state'])} arms {h['arms']} samples {h['nsamp']} events {h['nev']} "
           f"window {h['end'] - t0 if h['state'] == 2 else '?'} ms (t0 = timer ms {t0})", ""]
    out.append(f"{'#':>2} {'t_ms':>5} {'mode':<15} 0_02 0_0C  5_B0 45_B0 5_2B 45_2B  3D 3E 40 41 45  C4C5  0_28  flags")
    for i, s in enumerate(d["samples"]):
        mode = MODE[s["mode"]] if s["mode"] < len(MODE) else str(s["mode"])
        off = ((s["P1_C4"] & 0x1F) << 8) | s["P1_C5"]
        out.append(f"{i:>2} {(s['ms'] - t0) & 0xFFFF:>5} {mode:<15} {s['P0_02']:02x}   {s['P0_0C']:02x}    {s['P5_B0']:02x}   {s['P45_B0']:02x}    "
                   f"{s['P5_2B']:02x}   {s['P45_2B']:02x}    {s['P0_3D']:02x} {s['P0_3E']:02x} {s['P0_40']:02x} {s['P0_41']:02x} {s['P0_45']:02x}  "
                   f"{s['P1_C4']:02x}{s['P1_C5']:02x}  {s['P0_28']:02x}    {p0_02_flags(s['P0_02'])}")
    out += ["", "events (t_ms from t0):"]
    for e in d["events"]:
        out.append(f"{(e['ms'] - t0) & 0xFFFF:>5}  id {e['id']:>2} {EVNAME.get(e['id'], '?'):<44} arg {e['arg']:02x} val {e['val']:04x}")
    return out


def live(unit: str, mp: Path, wait_done: bool = False) -> tuple[bytes, int]:
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    from sdcc_overlay import repo_root
    u = json.loads((repo_root() / "scripts/devices.json").read_text())["units"][unit]
    bus = next((b for b in i2cbus.list_buses(display_only=True) if i2cbus.edid_serial(b) == u["serial"]), None)
    if bus is None:
        raise SystemExit(f"no bus with EDID serial {u['serial']}; nothing read")
    m = re.search(r"([0-9A-F]{8})\s+_g_stAwtoMeas\b", mp.read_text(errors="replace"))
    if not m:
        raise SystemExit(f"_g_stAwtoMeas not in {mp}: not a meas4k image")
    addr = int(m.group(1), 16) & 0xFFFF
    io = B.Real(bus, allow_write=True)               # debug read commands only (0x3C)
    if wait_done:      # paced by the failed bus transactions themselves (no sleep); 400 polls ~ 0.5 ms each when 0x35 answers, NAK-timeouts otherwise
        for _ in range(400):
            h = X.read_blocks(io, addr, 8)
            if h is not None and h[:2] == b"MK" and h[3] == 2:
                break
        else:
            print("warning: state never reached 2 (done); dumping anyway", file=sys.stderr)
    h = X.read_blocks(io, addr, HDR)
    if h is None or h[:2] != b"MK":
        raise SystemExit("block read failed (0x35 not answering?) or no 'MK' header")
    data = X.read_blocks(io, addr, HDR + h[7] * REC + EVENTS * EVREC)
    if data is None:
        raise SystemExit("block read failed (0x35 not answering?)")
    return data, addr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit")
    ap.add_argument("--map", type=Path)
    ap.add_argument("--file", type=Path)
    ap.add_argument("--tag", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--save-raw", action="store_true")
    ap.add_argument("--wait-done", action="store_true", help="poll the header until the window is done (state 2), then dump")
    a = ap.parse_args()
    from sdcc_overlay import repo_root
    logdir = repo_root() / "tmp/logs"
    logdir.mkdir(parents=True, exist_ok=True)
    if a.file:
        data, addr = a.file.read_bytes(), None
    elif a.unit and a.map:
        data, addr = live(a.unit, a.map, a.wait_done)
        if a.save_raw:
            (logdir / f"meas4k_{a.tag}.raw").write_bytes(data)
    else:
        ap.error("need --file, or --unit and --map")
    lines = render(decode(data), a.tag)
    if addr is not None:
        lines.append(f"\nring at 0x{addr:04x}; re-arm: ./dev.py dbg-write --unit {a.unit} {addr + 3:04X}=00")
    text = "\n".join(lines)
    (logdir / f"meas4k_{a.tag}.log").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
