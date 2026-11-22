#!/usr/bin/env python3
"""awto-ddc#255 Test 2 steps 1-4: DCR statistics, MCU DDR port reads / writes, host-side burst rate. Debug slave 0x35, MCU running.

usage: ddr_frame_test.py --unit N OP [args]      (needs the debug link: ./dev.py link --unit N --force on --minutes 10)
  rd ADDR [N]                       N bytes from 0xPPRR (block path; read-behind pages byte path)
  wr ADDR V [V ..]                  write bytes (3 transactions each)
  caps                              frame base / M1 M2 capture address registers + page-37 port state
  dcr [--th1 T --th2 T --sel S --win X Y W H]   one DCR measurement (24-bit above-threshold counts, per-channel levels)
  ddr-read --addr A [--port a|b] [--len L] [--buf r|w]   one burst through MCU_DC_*, prints the bytes
  ddr-scan --addr A --count N [--step S]                 N bursts at A, A+S, .. (one line each)
  ddr-write --addr A --hex HEX [--mask M] [--yes-hang-risk]  ONE burst write (step 4; refuses without the flag)
  rate [--n N]                      host-side rates: per-register transactions, 16 B burst read/write via the debug slave
Log (one decoded line per action): ./tmp/logs/ddr_frame_test.log ; raw: ./tmp/logs/ddr_frame_test.raw.log
Rates measured here are the HOST debug-slave rate (I2C, ~3 ms per register), not the MCU rate.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import isostamp
from _log import log_line as _log_line
from _repo import ROOT
from dbg_xdata import BEHIND_PAGES, DEV8, read_bytes, read_chunk
from rtd_i2c_bridge import Real

LOG = ROOT / "tmp/logs/ddr_frame_test.log"
RAW = ROOT / "tmp/logs/ddr_frame_test.raw.log"
SERIALS = {1: "AWT26110001", 2: "AWT26110002", 3: "AWT26110003"}   # units released for tests (2026-11-20)

# regdb RTD2795T-CG names -> addresses (re/regdb/RTD2795T-CG.tsv.gz)
HLW_ADDR, HLW_DATA = 0x0060, 0x0061
HLW_IDX = {"hs_h": 0, "hs_l": 1, "he_h": 2, "he_l": 3, "vs_h": 4, "vs_l": 5, "ve_h": 6, "ve_l": 7, "border_en": 0x0C, "ctl1": 0x0D}
DCR_ADDR, DCR_DATA, DCR_CTRL = 0x07D8, 0x07D9, 0x07DA
DCR_IDX = {"th1_1": 0, "th2_1": 1, "th1_num": 2, "th1_val": 5, "th2_num": 9, "th2_val": 12, "hi_r": 16, "lo_r": 18, "hi_g": 22, "lo_g": 24, "hi_b": 28, "lo_b": 30,
               "ymax_1": 40, "ymin_1": 41, "th_val_5": 42, "th_val_0": 43, "th1_0": 56, "th2_0": 57}
CAP_M1, CAP_M2 = 0x0500, 0x4500
MCU_DC = {"a": {"cmd": 0x3700, "len": 0x3701, "addr": 0x3704, "wbuf": 0x3710, "rbuf": 0x3720, "wmask": 0x3730, "flag": 0x3734},
          "b": {"cmd": 0x3740, "len": 0x3741, "addr": 0x3744, "wbuf": 0x3750, "rbuf": 0x3760, "wmask": 0x3770, "flag": 0x3774}}
DC_CMD_WRITE, DC_CMD_READ = 0x80, 0xA0   # [7:5] 100 = write, 101 = read

_t0 = time.monotonic()


def log(s: str) -> None:
    _log_line(s, LOG)


class Dbg:
    def __init__(self, unit: int, bus: int | None = None):
        serial = SERIALS.get(unit)
        if serial is None:
            raise SystemExit(f"unit {unit}: not a test unit here")
        self.bus = bus
        if bus is None:       # the EDID at 0x50 is not served while the debug link is on: pass --bus then
            self.bus = next((b for b in i2cbus.list_buses(True) if i2cbus.edid_serial(b) == serial), None)
            if self.bus is None:
                raise SystemExit(f"no bus with EDID serial {serial}; link on? pass --bus (checked via dbg_link.py state)")
            i2cbus.require_unit(self.bus, serial)
        self.io = Real(self.bus, allow_write=True)
        self.n_tx = 0
        log(f"unit {unit} serial {serial} bus {self.bus}")

    def _raw(self, s: str) -> None:
        RAW.parent.mkdir(parents=True, exist_ok=True)
        with RAW.open("a") as f:
            f.write(f"{isostamp.now()} {s}\n")

    def rd(self, a: int) -> int:
        for _ in range(2 if (a >> 8) in BEHIND_PAGES else 1):
            if not (self.io.write(DEV8, 0x01, bytes([a >> 8])) and self.io.write(DEV8, 0x3A, bytes([a & 0xFF]))):
                raise OSError(f"rd {a:04X} write NAK")
            r = self.io.read(DEV8, 0x08, 1)
        if r is None:
            raise OSError(f"rd {a:04X} read NAK")
        self._raw(f"rd {a:04X} -> {r[0]:02X}")
        return r[0]

    def wr(self, a: int, v: int) -> None:
        if not (self.io.write(DEV8, 0x01, bytes([a >> 8])) and self.io.write(DEV8, 0x03, bytes([v]))
                and self.io.write(DEV8, 0x3B, bytes([a & 0xFF]))):
            raise OSError(f"wr {a:04X} NAK")
        self._raw(f"wr {a:04X} <- {v:02X}")

    def block(self, a: int, n: int) -> bytes:
        r = read_chunk(self.io, a, n) if (a >> 8) not in BEHIND_PAGES else read_bytes(self.io, a, n)
        if r is None:
            raise OSError(f"block {a:04X}+{n} failed")
        self._raw(f"blk {a:04X}+{n} -> {r.hex()}")
        return r

    def mod(self, a: int, mask: int, val: int) -> None:
        self.wr(a, (self.rd(a) & ~mask & 0xFF) | (val & mask))

    # ---- indexed ports ----
    def dcr_idx_rd(self, name: str) -> int:
        self.wr(DCR_ADDR, (DCR_IDX[name] << 2) | 0x03)     # bit1 = hold, bit0 = enable
        return self.rd(DCR_DATA)

    def dcr_idx_wr(self, name: str, v: int) -> None:
        self.wr(DCR_ADDR, (DCR_IDX[name] << 2) | 0x01)
        self.wr(DCR_DATA, v)

    def hlw_wr(self, name: str, v: int) -> None:
        self.wr(HLW_ADDR, HLW_IDX[name])
        self.wr(HLW_DATA, v)

    def hlw_rd(self, name: str) -> int:
        self.wr(HLW_ADDR, HLW_IDX[name])
        return self.rd(HLW_DATA)


def cmd_caps(d: Dbg) -> None:
    m1 = [d.rd(CAP_M1 + i) for i in range(4)]
    m2 = [d.rd(CAP_M2 + i) for i in range(4)]
    log(f"CAP_M1_MEM_ADDR MSB/H/M/L = {' '.join(f'{x:02X}' for x in m1)} -> 0x{int.from_bytes(bytes(m1), 'big'):08X}")
    log(f"CAP_M2_MEM_ADDR (page 45) = {' '.join(f'{x:02X}' for x in m2)} -> 0x{int.from_bytes(bytes(m2), 'big'):08X}")
    for p, r in MCU_DC.items():
        v = {k: d.rd(a) for k, a in (("cmd", r["cmd"]), ("len", r["len"]), ("flag", r["flag"]))}
        ad = [d.rd(r["addr"] + i) for i in range(4)]
        log(f"MCU_DC port {p}: CMD {v['cmd']:02X} LEN {v['len']:02X} ADDR {' '.join(f'{x:02X}' for x in ad)} READ_FLAG {v['flag']:02X}")


def dcr_measure(d: Dbg, th1: int, th2: int, sel: int, win=None, timeout_s: float = 0.2, keep_hlw: bool = False) -> dict:
    """One DCR measurement. Waits for ready_to_read (DVS rising, 16.7 ms at 60 Hz): limit 0.2 s = 12 frames, expiry logs and returns {}."""
    d.dcr_idx_wr("th1_1", th1 >> 2)
    d.dcr_idx_wr("th2_1", th2 >> 2)
    d.dcr_idx_wr("th1_0", (th1 & 3) << 6)
    d.dcr_idx_wr("th2_0", (th2 & 3) << 6)
    d.mod(DCR_CTRL, 0x0E, sel << 1)
    if keep_hlw:
        pass
    elif win:
        x, y, w, h = win
        for n, v in (("hs_h", x >> 8), ("hs_l", x & 255), ("he_h", (x + w - 1) >> 8), ("he_l", (x + w - 1) & 255),
                     ("vs_h", y >> 8), ("vs_l", y & 255), ("ve_h", (y + h - 1) >> 8), ("ve_l", (y + h - 1) & 255)):
            d.hlw_wr(n, v)
        d.hlw_wr("ctl1", (d.hlw_rd("ctl1") & ~0x30) | 0x10)   # win_dcr_sel = 01 inside window
        d.hlw_wr("border_en", d.hlw_rd("border_en") | 0xF0 | 0x01)   # all borders off, window_en
    else:
        d.hlw_wr("ctl1", d.hlw_rd("ctl1") & ~0x30)             # full region
    d.wr(DCR_ADDR, 0x01)                                        # enable, refresh on
    t = time.monotonic()
    ready = False
    for _ in range(2):          # first ready_to_read may hold the frame measured before the settings: discard it, use the second
        d.mod(DCR_CTRL, 0x10, 0x10)                             # write 1 clears ready_to_read
        ready = False
        while time.monotonic() - t < timeout_s:
            if d.rd(DCR_CTRL) & 0x10:
                ready = True
                break
        if not ready:
            break
    dt = (time.monotonic() - t) * 1000
    if not ready:
        log(f"DCR ready_to_read not set after {dt:.0f} ms (limit {timeout_s * 1000:.0f} ms)")
        return {}
    d.wr(DCR_ADDR, 0x03)                                        # hold the result
    out = {}
    for name, n in (("th1_num", 3), ("th2_num", 3)):
        d.wr(DCR_ADDR, (DCR_IDX[name] << 2) | 0x03)
        out[name] = int.from_bytes(bytes(d.rd(DCR_DATA) for _ in range(n)), "big")   # data port steps the index per read
    for name in ("hi_r", "lo_r", "hi_g", "lo_g", "hi_b", "lo_b"):
        d.wr(DCR_ADDR, (DCR_IDX[name] << 2) | 0x03)
        out[name] = (d.rd(DCR_DATA) << 8) | d.rd(DCR_DATA)
    d.mod(DCR_CTRL, 0x10, 0x10)
    d.wr(DCR_ADDR, 0x01)
    out["ready_ms"] = dt
    return out


def cmd_dcr(d: Dbg, a) -> None:
    r = dcr_measure(d, a.th1, a.th2, a.sel, tuple(a.win) if a.win else None, keep_hlw=a.keep_hlw)
    if not r:
        return
    log(f"DCR th1={a.th1} th2={a.th2} sel={a.sel} win={a.win}: ABOVE_TH1_NUM={r['th1_num']} ABOVE_TH2_NUM={r['th2_num']} "
        f"HIGH_LV_NUM R/G/B={r['hi_r']}/{r['hi_g']}/{r['hi_b']} LOW_LV_NUM R/G/B={r['lo_r']}/{r['lo_g']}/{r['lo_b']} ready after {r['ready_ms']:.0f} ms")


def dc_burst_read(d: Dbg, port: str, addr: int, ln: int, buf: str = "r", timeout_s: float = 0.05) -> bytes | None:
    """One MCU_DC read. Poll READ_FLAG (cleared by reading the buffer): limit 50 ms = 3 frames of DDR arbitration, expiry logs and returns None."""
    r = MCU_DC[port]
    d.wr(r["len"], ln)
    for i, sh in enumerate((24, 16, 8, 0)):
        d.wr(r["addr"] + i, (addr >> sh) & 0xFF)
    d.block(r["rbuf"], 16)                        # clear a stale ready flag
    d.wr(r["cmd"], DC_CMD_READ)
    t = time.monotonic()
    while time.monotonic() - t < timeout_s:
        if d.rd(r["flag"]) & 1:
            return d.block(r["rbuf"] if buf == "r" else r["wbuf"], 16)
    log(f"MCU_DC port {port} read flag not set after {(time.monotonic() - t) * 1000:.0f} ms at addr 0x{addr:07X}")
    return None


def cmd_ddr_read(d: Dbg, a) -> None:
    b = dc_burst_read(d, a.port, a.addr, a.len, a.buf)
    if b is not None:
        log(f"DDR {a.port.upper()} addr 0x{a.addr:07X} len {a.len}: {b.hex(' ')}")


def cmd_ddr_scan(d: Dbg, a) -> None:
    for i in range(a.count):
        ad = a.addr + i * a.step
        b = dc_burst_read(d, a.port, ad, a.len)
        if b is not None:
            log(f"DDR {a.port.upper()} 0x{ad:07X}: {b.hex(' ')}")


def cmd_ddr_write(d: Dbg, a) -> None:
    if not a.yes_hang_risk:
        raise SystemExit("ddr-write: refused without --yes-hang-risk (step 4; no relay on unit 1, main session must say go)")
    r = MCU_DC[a.port]
    data = bytes.fromhex(a.hex)
    if len(data) != 16:
        raise SystemExit("--hex must be 16 bytes")
    d.wr(r["len"], a.len)
    for i, sh in enumerate((24, 16, 8, 0)):
        d.wr(r["addr"] + i, (a.addr >> sh) & 0xFF)
    for i, v in enumerate(data):
        d.wr(r["wbuf"] + i, v)
    d.wr(r["wmask"], (a.mask >> 8) & 0xFF)
    d.wr(r["wmask"] + 1, a.mask & 0xFF)
    d.wr(r["cmd"], DC_CMD_WRITE)
    t = time.monotonic()
    while time.monotonic() - t < 0.05:
        if (d.rd(r["cmd"]) & 0xE0) == 0:
            break
    log(f"DDR {a.port.upper()} WRITE addr 0x{a.addr:07X} mask {a.mask:04X} {data.hex(' ')}: cmd back to NOP after {(time.monotonic() - t) * 1000:.1f} ms")


def cmd_rate(d: Dbg, a) -> None:
    n = a.n
    t = time.monotonic()
    for _ in range(n):
        d.rd(0x3734)
    dt = time.monotonic() - t
    log(f"host rate: {n} single-register reads (byte path, 3 I2C transactions) {dt * 1000 / n:.2f} ms each")
    t = time.monotonic()
    for _ in range(n):
        d.block(0x3720, 16)
    dt = time.monotonic() - t
    log(f"host rate: {n} x 16 B block reads (2 transactions) {dt * 1000 / n:.2f} ms each = {16 * n / dt / 1000:.2f} KB/s")
    t = time.monotonic()
    for _ in range(n):
        d.wr(0x3710, 0x00)
    dt = time.monotonic() - t
    log(f"host rate: {n} single-register writes (3 transactions) {dt * 1000 / n:.2f} ms each")
    t = time.monotonic()
    for _ in range(n):
        dc_burst_read(d, "a", 0x100000, 2)
    dt = time.monotonic() - t
    log(f"host rate: {n} full 16 B DDR read bursts through MCU_DC (len+addr+clear+cmd+poll+read) {dt * 1000 / n:.2f} ms each = {16 * n / dt / 1000:.2f} KB/s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int)
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("rd"); p.add_argument("addr", type=lambda x: int(x, 0)); p.add_argument("n", type=int, nargs="?", default=1)
    p = sub.add_parser("wr"); p.add_argument("addr", type=lambda x: int(x, 0)); p.add_argument("vals", type=lambda x: int(x, 0), nargs="+")
    sub.add_parser("caps")
    p = sub.add_parser("dcr")
    p.add_argument("--th1", type=int, default=32); p.add_argument("--th2", type=int, default=768)
    p.add_argument("--sel", type=int, default=0); p.add_argument("--win", type=int, nargs=4); p.add_argument("--keep-hlw", action="store_true")
    for nm in ("ddr-read", "ddr-scan", "ddr-write"):
        p = sub.add_parser(nm)
        p.add_argument("--addr", type=lambda x: int(x, 0), required=True)
        p.add_argument("--port", default="a", choices=["a", "b"])
        p.add_argument("--len", type=int, default=2)
        if nm == "ddr-read":
            p.add_argument("--buf", default="r", choices=["r", "w"])
        if nm == "ddr-scan":
            p.add_argument("--count", type=int, required=True); p.add_argument("--step", type=lambda x: int(x, 0), default=1)
        if nm == "ddr-write":
            p.add_argument("--hex", required=True); p.add_argument("--mask", type=lambda x: int(x, 0), default=0xFFFF)
            p.add_argument("--yes-hang-risk", action="store_true")
    p = sub.add_parser("rate"); p.add_argument("--n", type=int, default=50)
    a = ap.parse_args()
    d = Dbg(a.unit, a.bus)
    try:
        if a.op == "rd":
            b = d.block(a.addr, a.n) if a.n > 1 and a.n <= 24 else bytes(d.rd(a.addr + i) for i in range(a.n))
            log(f"rd 0x{a.addr:04X}+{a.n}: {b.hex(' ')}")
        elif a.op == "wr":
            for i, v in enumerate(a.vals):
                d.wr(a.addr + i, v)
            log(f"wr 0x{a.addr:04X} <- {' '.join(f'{v:02X}' for v in a.vals)}")
        elif a.op == "caps":
            cmd_caps(d)
        elif a.op == "dcr":
            cmd_dcr(d, a)
        elif a.op == "ddr-read":
            cmd_ddr_read(d, a)
        elif a.op == "ddr-scan":
            cmd_ddr_scan(d, a)
        elif a.op == "ddr-write":
            cmd_ddr_write(d, a)
        elif a.op == "rate":
            cmd_rate(d, a)
    finally:
        d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
