#!/usr/bin/env python3
"""Watchdog crash record v2 (awto-ddc#131, #138, docs/watchdog.md): read, decode, clear over the firmware debug slave 0x35.

usage: rtd_crash.py BUS --map MAP --serial SERIAL [--clear] [--snap]
- Reads the 32 B `_isr_g_stAwtoWdt` (address from the map; 0xF6B0 in #131 images) with the 0x3C block read, prints one decoded line:
  cause, bites / other warm resets, PC as bank:addr + symbol+offset (map), registers, heartbeat, uptime, pass age; live: max
  pass, max gap between watchdog pokes, the unit-2 probe result (test cmd 0x49 / 0x4F).
- --clear: writes 0 to the magic byte (debug write 0x01 hi, 0x03 value, 0x3B lo); the record is invalid until the next bite.
- Library (crash_sim_test.py): decode(b), line(d, syms), symbolize(syms, bank, pc), read(io, addr), clear(io, addr).
Log: tmp/logs/rtd_crash.log (+ rtd_crash.raw.log byte trace)
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402

DEV8, SIZE, REC_N, SEED = 0x6A, 32, 25, 0xA5
COMMON_END = 0x5000                                  # banked code from 0x5000 (docs/reversing/realtek-rtd/mcu-8051.md)
CAUSE = {0: "none", 1: "STALL"}
BOOT = ((0x01, "HW-WDT"), (0x02, "BITE-PENDING"), (0x04, "TEST-ARMED"), (0x08, "NEW"), (0x10, "WARM"), (0x20, "COLD"),
        (0x40, "AFTER-BITE"), (0x80, "AFTER-PROBE"))       # RL6449_Project.h AWTO_WDT_B_* (record v2, #138)
FIELDS = ("m0 m1 ver cause bites warm pch pcl bank sp psw acc b dph dpl reth retl stage mode hbh hbl uph upl "
          "agh agl check boot passh passl max_pass max_poke probe").split()
PROBE = ((0x01, "TIMER-MODE"), (0x02, "ARMED"), (0x04, "IRQ"), (0x08, "RESET"), (0x10, "NO-RESET"), (0x20, "WDTI"), (0x40, "EARLY"))
POKE_MS = 32 * 2048 / 14318.18                       # ucMaxPoke unit: 32 CNT3 counts (RL6449_Project.h)
SITES = {0: "-", 1: "main pass", 2: "DelayXms", 3: "PollingFlagProc", 4: "WaitForEvent", 5: "AwtoMsgWait", 6: "FlashWREN",
         7: "FlashWRDis", 8: "FlashWRProtect", 9: "FlashRead", 10: "FlashWrite", 11: "OsdPropPutString", 12: "PanelT3Wait", 13: "DPTxHpdPoll"}   # AWTO_WDT_S_* (#150)


def site_addr(map_text: str, name: str = "g_ucAwtoPokeSite") -> int | None:
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{name}\b", map_text, re.M)
    return int(m.group(1), 16) & 0xFFFF if m else None


def decode(b: bytes) -> dict:
    if len(b) < SIZE:
        raise ValueError(f"crash record: {len(b)} bytes, want {SIZE}")
    d = dict(zip(FIELDS, b[:SIZE]))
    s = SEED
    for x in b[:REC_N]:
        s ^= x
    d["valid"] = b[0:2] == b"WD" and b[2] == 2 and b[REC_N] == s
    d["pass_age"] = d["agh"] << 8 | d["agl"]
    d["pc"], d["ret"] = d["pch"] << 8 | d["pcl"], d["reth"] << 8 | d["retl"]
    d["dptr"], d["hb"], d["up"] = d["dph"] << 8 | d["dpl"], d["hbh"] << 8 | d["hbl"], d["uph"] << 8 | d["upl"]
    return d


def load_syms(map_text: str) -> tuple[list, list, tuple]:
    """Sorted (address, name) of code symbols (bank << 16 | addr for banked code, addr for common) + the bank-return table
    range of fw/sdcc/bank.asm (__bs_call_sw + 1 .. __bs_ret: 16 entries of 4 B, entry k returns into bank k)."""
    sym = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(\w+)", map_text, re.M)}
    for m in re.finditer(r"^CH_(\w+)=0x([0-9a-fA-F]+)\s*$", map_text, re.M):      # full-length names (C: lines cut at 32 chars)
        sym["_" + m.group(1)] = int(m.group(2), 16)
    f = sorted((v, k[1:]) for k, v in sym.items() if k.startswith("_") and not k.startswith("__bs_") and not k.startswith("__str_"))
    rtab = (sym["__bs_call_sw"] + 1, sym["__bs_ret"]) if "__bs_call_sw" in sym and "__bs_ret" in sym else (0, 0)
    return [v for v, _ in f], f, rtab


def symbolize(syms: tuple, bank: int, pc: int) -> str:
    keys, f, rtab = syms
    if rtab[0] <= pc < rtab[1]:
        return f"bank-return to bank {(pc - rtab[0]) // 4}"
    a = pc if pc < COMMON_END else bank << 16 | pc
    i = bisect.bisect_right(keys, a) - 1
    return f"{f[i][1]}+0x{a - f[i][0]:x}" if i >= 0 else "?"


def where(d: dict, pc: int) -> str:
    return f"{d['bank']:02X}:{pc:04X}" if pc >= COMMON_END else f"C:{pc:04X}"


def line(d: dict, syms: tuple | None = None) -> str:
    boot = "|".join(n for bit, n in BOOT if d["boot"] & bit) or "-"
    probe = "|".join(n for bit, n in PROBE if d["probe"] & bit) or "-"
    poke = ">=586" if d["max_poke"] == 0xFF else f"{d['max_poke'] * POKE_MS:.0f}"
    live = f"live: boot {boot} max pass {d['max_pass'] * 32} ms max poke gap {poke} ms probe {probe}"
    if not d["valid"]:
        return f"no crash record (magic/check invalid); {live}"
    if d["bites"] == 0:
        return f"no bite recorded; other warm resets {d['warm']}; {live}"
    c = CAUSE.get(d["cause"] & 0x3F, f"0x{d['cause']:02x}") + (" TMODE" if d["cause"] & 0x40 else "") + (" TEST" if d["cause"] & 0x80 else "")
    pcs = where(d, d["pc"]) + (f" {symbolize(syms, d['bank'], d['pc'])}" if syms else "")
    ret = f"{d['ret']:04X}" + (f" ({symbolize(syms, d['bank'], d['ret'])}?)" if syms else "")    # top word: may be data
    return (f"WDT bite {c}: PC {pcs} STACK TOP {ret} SP {d['sp']:02X} A {d['acc']:02X} B {d['b']:02X} PSW {d['psw']:02X} "
            f"DPTR {d['dptr']:04X}; hb {d['hb']} up {d['up']} ms stage {d['stage']} mode {d['mode']}; "
            f"pass age {d['pass_age']} ms; bites {d['bites']} warm {d['warm']}; {live}")


def ages(d: dict) -> str:
    """live watchdog ages of this boot (record v2): longest main-loop pass, longest gap between pokes"""
    poke = ">=586" if d["max_poke"] == 0xFF else f"{d['max_poke'] * POKE_MS:.0f}"
    return f"max pass {d['max_pass'] * 32} ms, max poke gap {poke} ms"


# Reset-vector snapshot (#29 / #138): crt_rtd_startup copies these before any init; 20 B at _g_stAwtoSnap (0xF69C).
SNAP_N = 20
SNAP_REGS = ("EICON D8", "PCON 87", "EXIF 91", "CKCON 8E", "IE A8", "EIE E8", "IP B8", "EIP F8", "FFEA", "FFEB", "FFAA",
             "FFAB", "FFAC", "FFAD", "FFE0", "FFED", "FFEE", "P0_01")
# DW8051 databook v3.2a reset values (SFRs; XFRs: regdb). A byte away from it on some reset type = reset-cause candidate.
SNAP_RESET = {"EICON D8": 0x40, "PCON 87": 0x30, "EXIF 91": 0x08, "CKCON 8E": 0x01, "IE A8": 0x00, "EIE E8": 0xE0,
              "IP B8": 0x80, "EIP F8": 0xE0}


def snap_addr(map_text: str) -> int | None:
    m = re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stAwtoSnap\b", map_text, re.M)
    return int(m.group(1), 16) & 0xFFFF if m else None


def snap_decode(b: bytes) -> dict | None:
    if b is None or len(b) < SNAP_N or b[0:2] != b"RS":
        return None
    return dict(zip(SNAP_REGS, b[2:SNAP_N]))


def snap_line(s: dict | None) -> str:
    if s is None:
        return "no snapshot"
    return " ".join(f"{k.split()[0]}={v:02X}" + ("" if SNAP_RESET.get(k, v) == v else "!") for k, v in s.items())


def snap_diff(snaps: list) -> str:
    """registers that differ between snapshots (reset-cause candidates)"""
    ok = [s for s in snaps if s]
    d = [k for k in SNAP_REGS if len({s[k] for s in ok}) > 1]
    return ", ".join(f"{k}: " + "/".join(f"{s[k]:02X}" for s in ok) for k in d) or "none"


def read(io, addr: int) -> bytes | None:
    return X.read_blocks(io, addr, SIZE)


def clear(io, addr: int) -> bool:
    return (io.write(DEV8, 0x01, bytes([addr >> 8])) and io.write(DEV8, 0x03, b"\x00")
            and io.write(DEV8, 0x3B, bytes([addr & 0xFF])))


def map_addr(map_text: str) -> int:
    m = re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_isr_g_stAwtoWdt\b", map_text, re.M)
    if not m:
        raise SystemExit("_isr_g_stAwtoWdt not in this map: image without the #131 watchdog")
    return int(m.group(1), 16) & 0xFFFF


def main() -> int:
    import i2cbus
    import rtd_i2c_bridge as B
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--snap", action="store_true", help="also print the reset-vector snapshot (#29), '!' = not the DW8051 reset value")
    a = ap.parse_args()
    i2cbus.require_unit(a.bus, a.serial)
    mt = a.map.read_text(errors="replace")
    addr, syms = map_addr(mt), load_syms(mt)
    logs = B.setup_logs("rtd_crash", map=str(a.map))
    io = B.Real(a.bus, allow_write=True)      # a debug read sets the address by a write (as rtd_dbg_read); --clear gates the record write
    try:
        b = read(io, addr)
        if b is None:
            raise SystemExit("crash record read failed (debug slave 0x35 silent or checksum errors)")
        out = line(decode(b), syms)
        sa = site_addr(mt)
        if sa is not None:
            s = X.read_bytes(io, sa, 1)
            out += f"; max poke gap ended by {SITES.get(s[0], s[0]) if s else '?'}"
        if a.snap:
            sa = snap_addr(mt)
            out += "; snapshot: " + (snap_line(snap_decode(X.read_blocks(io, sa, SNAP_N))) if sa else "image without it")
        if a.clear:
            out += "; " + ("cleared" if clear(io, addr) else "CLEAR FAILED (I2C write)")
        print(out)
        logs.log(f"bus {a.bus} {a.serial}: {out}")
        return 0
    finally:
        io.close()
        logs.close()


if __name__ == "__main__":
    sys.exit(main())
