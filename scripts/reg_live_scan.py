#!/usr/bin/env python3
"""Read-only live scan of the scaler XDATA/register space of a RUNNING unit through the firmware debug slave 0x35.

usage: reg_live_scan.py --unit N --pass-label A [--pages all|00,38-3A,..] [--out FILE] [--wall-s S] [--no-block]
  One pass = link on (dbg_link) -> calibrate on page 00 -> heartbeat -> pages -> heartbeat -> link off.
  Reads only: the bus object is rtd_i2c_bridge.Real(allow_write=False, regread=True), which lets through debug
  read commands and hi-byte staging only. The link tooling itself writes: DDC/CI setvcp E3 = A5 NN to 0x37 (on),
  test cmd 0x3B over 0x35 (off) (scripts/dbg_link.py).
  Excluded addresses (EXCLUDE, reason per entry) are never read. Data: JSON in tmp/regs/live/, log: tmp/logs/reg_live_scan.log.
  Abort (link off, JSON kept with what was read): 3 consecutive failed reads, a failed heartbeat (0x0000 != 0xCF), wall bound.
  Page order: pages seen in ISP dumps / regdb / SDK first, never-read pages last (heartbeat every 64 B instead of 256 B).
"""
from __future__ import annotations

import argparse
import glob
import gzip
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
import isostamp  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/reg_live_scan.log"

ID_ADDR, ID_VALUE = 0x0000, 0xCF            # ID_REG, regdb reset 0xCF
DIAG_BASE = 0xF6D0                          # isr_g_stAwtoDiag: 'AD', version (docs/diag-block.md)
HB_KNOWN, HB_UNKNOWN = 256, 64              # reads between heartbeats
MAX_CONSEC_FAIL = 3                         # failed reads in a row that abort the pass
SLOW_ABORT_X = 10                           # a read that returned but took > 10 x limit counts as failed; 1..10 x = logged SLOW only
LIMIT_MARGIN = 1.25                         # per-read limit and wall bound = 1.25 x measured
CALIB_PAGE = 0x00
WALL_FLOOR_S = 2.0                          # only matters for a fake bus: a real scan is minutes

# (lo, hi inclusive, reason). Never read; logged as "excluded".
EXCLUDE: list[tuple[int, int, str]] = [
    (0x0024, 0x0025, "index/data port (regdb PORT_ADDR)"), (0x002A, 0x002B, "index/data port"),
    (0x0030, 0x0031, "index/data port"), (0x0033, 0x0034, "index/data port"),
    (0x005C, 0x005D, "index/data port"), (0x0060, 0x0061, "index/data port"),
    (0x0064, 0x0065, "index/data port"), (0x008D, 0x008E, "index/data port"),
    (0x07CE, 0x07CF, "index/data port"), (0x07D2, 0x07D3, "index/data port"),
    (0x15A3, 0x15A4, "index/data port"), (0x2AAC, 0x2AAD, "index/data port"),
    (0x2AFB, 0x2AFC, "index/data port"), (0x4024, 0x4025, "index/data port"),
    (0x68AC, 0x68AD, "index/data port"), (0x68FB, 0x68FC, "index/data port"),
    (0x7139, 0x713A, "index/data port"), (0x71C9, 0x71CA, "index/data port"),
    (0x7239, 0x723A, "index/data port"), (0x72C9, 0x72CA, "index/data port"),
    (0xB7C1, 0xB7C4, "index/data port"), (0xBAC1, 0xBAC4, "index/data port"),
    (0x0090, 0x0092, "OSD ports (auto-increment / RAM)"), (0x0099, 0x0099, "OSD port"),
    (0x009D, 0x009D, "OSD port"),
    (0x0069, 0x0069, "dither table port"), (0x006D, 0x006D, "background colour port (write-pointer reset)"),
    (0x07CA, 0x07CA, "DCC port (index > 255)"), (0x07D9, 0x07D9, "DCR port (ADDR reg holds measure_start)"),
    (0x71C4, 0x71C4, "HDCP key port (auto-increment, secret)"),
    (0x72C4, 0x72C4, "HDCP key port (auto-increment, secret)"),
    (0xFF22, 0xFF2F, "our debug engine registers"),
    (0xFE60, 0xFE6F, "DDC access ports"),
    (0xFF00, 0xFF00, "IRQ status (read-clear risk)"),
    (0xFF03, 0xFF07, "triple-byte op registers"),
    (0x8FF0, 0x8FF7, "INT_STATUS flags page 8F (read-clear risk)"),
    (0xCFF0, 0xCFF7, "INT_STATUS flags page CF (read-clear risk)"),
]
_EXCL_BY_ADDR: dict[int, str] = {a: why for lo, hi, why in EXCLUDE for a in range(lo, hi + 1)}


def excluded(addr: int) -> str | None:
    return _EXCL_BY_ADDR.get(addr)


class Aborted(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# -- page ordering -------------------------------------------------------------------------------------------
def known_pages(root: Path) -> set[int]:
    """Pages with an ISP dump, a regdb row or an SDK name; the rest are 'never read / unknown'."""
    pages: set[int] = set()
    for fn in glob.glob(str(root / "tmp/regs/*.json")):
        try:
            pages |= {int(k, 16) for k in json.load(open(fn)).get("pages", {})}
        except (OSError, ValueError, AttributeError):
            pass
    try:
        with gzip.open(root / "re/regdb/RTD2795T-CG.tsv.gz", "rt") as f:
            pages |= {int(r["address"], 0) >> 8 for r in csv.DictReader(f, delimiter="\t")}
    except OSError:
        pass
    hdr = root / "fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h"
    try:
        pages |= {int(m.group(1), 16) for m in re.finditer(r"#define\s+P([0-9A-F]{2})_[0-9A-F]{2}_\w+\s+0x", hdr.read_text(errors="replace"))}
    except OSError:
        pass
    return {p for p in pages if 0 <= p <= 0xFF}


def parse_pages(spec: str, known: set[int]) -> list[int]:
    if spec == "all":
        return sorted(known) + [p for p in range(0x100) if p not in known]
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out += range(int(lo, 16), int(hi or lo, 16) + 1)
    return list(dict.fromkeys(out))


# -- reading --------------------------------------------------------------------------------------------------
class Reader:
    """One read transaction at a time, timed; every attempt is logged (value, ok/NAK/SLOW, ms)."""

    def __init__(self, io, block: bool, log, clock=time.monotonic):
        self.io, self.block, self.log, self.clock = io, block, log, clock
        self.hi: int | None = None          # staged hi byte of the byte path
        self.limit_ms: float | None = None  # per-read limit once calibrated
        self.consec_fail = 0
        self.ok = self.failed = self.slow = 0
        self.max_ms = 0.0

    def _byte(self, addr: int) -> bytes | None:
        if addr >> 8 != self.hi:
            self.hi = None
            if not self.io.write(X.DEV8, X.CMD_HI, bytes([addr >> 8])):
                return None
            self.hi = addr >> 8
        if not self.io.write(X.DEV8, X.CMD_READ, bytes([addr & 0xFF])):
            self.hi = None
            return None
        r = self.io.read(X.DEV8, X.READ_SUB, 1)
        if r is None:
            self.hi = None
        return r

    def read(self, addr: int, n: int) -> list[int | None]:
        """n contiguous addresses (n > 1 only on the block path, one transaction). None entries = failed."""
        t0 = self.clock()
        if self.block:
            data = X.read_chunk(self.io, addr, n, tries=1)
        else:
            data = self._byte(addr)
        ms = (self.clock() - t0) * 1000
        self.max_ms = max(self.max_ms, ms)
        good = data is not None and len(data) == n
        slow = good and self.limit_ms is not None and ms > self.limit_ms
        for i in range(n):
            v = data[i] if good else None
            state = "SLOW" if slow else ("ok" if good else "NAK")
            self.log(f"{addr + i:04X} {'--' if v is None else f'{v:02X}'} {state} {ms:.2f}ms" + (f" blk{n}" if n > 1 else ""))
        self.slow += slow
        if good and not (slow and ms > SLOW_ABORT_X * self.limit_ms):
            self.consec_fail = 0
            self.ok += 1
        else:
            self.consec_fail += 1
            self.failed += not good
        if self.consec_fail >= MAX_CONSEC_FAIL:
            raise Aborted(f"{MAX_CONSEC_FAIL} consecutive failed reads ending at 0x{addr:04X} (limit {self.limit_ms} ms)")
        return list(data) if good else [None] * n


def runs(page: int, start: int = 0, end: int = 256, maxlen: int = 1) -> list[tuple[int, int]]:
    """(addr, n) transactions covering the page minus excluded addresses; n <= maxlen, contiguous."""
    out: list[tuple[int, int]] = []
    for off in range(start, end):
        a = (page << 8) | off
        if excluded(a) is not None:
            continue
        if out and out[-1][0] + out[-1][1] == a and out[-1][1] < maxlen:
            out[-1] = (out[-1][0], out[-1][1] + 1)
        else:
            out.append((a, 1))
    return out


def log_excluded(page: int, log) -> None:
    for off in range(256):
        why = excluded((page << 8) | off)
        if why:
            log(f"{(page << 8) | off:04X} -- EXCLUDED {why}")


def heartbeat(rd: Reader, tag: str, beats: list, log, clock=time.monotonic) -> None:
    """Byte-path read of ID_REG; anything but 0xCF aborts. Block-mode reader reads it as a 1-byte block."""
    t0 = clock()
    r = rd.read(ID_ADDR, 1)[0]
    ms = (clock() - t0) * 1000
    beats.append({"tag": tag, "value": r, "ms": round(ms, 2)})
    log(f"HB {tag} {'--' if r is None else f'{r:02X}'} {ms:.2f}ms")
    if r != ID_VALUE:
        raise Aborted(f"heartbeat {tag}: ID_REG read {r!r}, want 0x{ID_VALUE:02X}")


def calibrate(rd: Reader, log) -> dict:
    """256 addresses of page 00 (minus excluded): per-read worst/mean; sets the per-read limit."""
    ms: list[float] = []
    maxlen = X.BLK_MAX if rd.block else 1
    for a, n in runs(CALIB_PAGE, maxlen=maxlen):
        t0 = rd.clock()
        rd.read(a, n)
        ms.append((rd.clock() - t0) * 1000)
    worst, mean = max(ms), sum(ms) / len(ms)
    rd.limit_ms = worst * LIMIT_MARGIN
    rd.max_ms = 0.0
    rd.ok = rd.failed = rd.slow = 0
    log(f"CALIB path={'block' if rd.block else 'byte'} transactions={len(ms)} worst={worst:.2f}ms mean={mean:.2f}ms limit={rd.limit_ms:.2f}ms")
    return {"transactions": len(ms), "worst_ms": round(worst, 3), "mean_ms": round(mean, 3), "limit_ms": round(rd.limit_ms, 3)}


def run_pass(io, pages: list[int], block: bool, log, save, wall_s: float | None = None, known: set[int] | None = None,
             clock=time.monotonic) -> dict:
    """Calibrate, scan, heartbeat. save(result) after every page. Returns the result dict (result 'ok' | 'aborted')."""
    rd = Reader(io, block, log, clock)
    res: dict = {"path": "block" if block else "byte", "pages": {}, "heartbeats": [], "result": "ok", "abort": None}
    t_start = clock()
    try:
        heartbeat(rd, "before", res["heartbeats"], log, clock)
        res["calibration"] = cal = calibrate(rd, log)
        maxlen = X.BLK_MAX if block else 1
        total = sum(len(runs(p, maxlen=maxlen)) for p in pages)
        expect_s = total * cal["worst_ms"] / 1000      # calibration mean under-estimates (first pass: 8.8 s planned, 12 s real)
        res["wall_s"] = wall_s if wall_s is not None else round(max(expect_s * LIMIT_MARGIN, WALL_FLOOR_S), 1)
        res["expected_s"] = round(expect_s, 1)
        log(f"PLAN pages={len(pages)} transactions={total} expected={expect_s:.1f}s wall={res['wall_s']}s")
        known = known or set()
        since_hb = 0
        for p in pages:
            hb_every = HB_KNOWN if p in known else HB_UNKNOWN
            vals: list[int | None] = [None] * 256
            res["pages"][f"{p:02X}"] = vals
            log_excluded(p, log)
            for a, n in runs(p, maxlen=maxlen):
                if clock() - t_start > res["wall_s"]:
                    raise Aborted(f"wall bound {res['wall_s']} s exceeded at 0x{a:04X}")
                for i, v in enumerate(rd.read(a, n)):
                    vals[(a & 0xFF) + i] = v
                since_hb += n
                if since_hb >= hb_every:
                    heartbeat(rd, f"{a:04X}", res["heartbeats"], log, clock)
                    since_hb = 0
            save(res)
        heartbeat(rd, "after", res["heartbeats"], log, clock)
    except Aborted as e:
        res["result"], res["abort"] = "aborted", e.reason
        log(f"ABORT {e.reason}")
    res.update(reads_ok=rd.ok, reads_failed=rd.failed, reads_slow=rd.slow, max_ms=round(rd.max_ms, 3),
               elapsed_s=round(clock() - t_start, 2))
    return res


# -- host side: unit, bus, state --------------------------------------------------------------------------------
def unit_info(n: str) -> dict:
    return json.loads((ROOT / "scripts/devices.json").read_text())["units"][n]


def resolve_bus(u: dict) -> int:
    """The bus whose EDID serial is the unit's and whose DDC is live (0x37 ACK or 0x35 answers), else the first EDID match."""
    import dbg_link
    import i2cbus
    cands: list[int] = []
    for key in ("connector", "connector_dp"):
        if u.get(key):
            link = (Path("/sys/class/drm") / u[key] / "ddc").resolve()
            if link.name.startswith("i2c-"):
                cands.append(int(link.name.split("-")[1]))
    cands += [b for b in i2cbus.list_buses(display_only=True) if b not in cands]
    mine = [b for b in cands if i2cbus.edid_serial(b) == u["serial"]]
    for b in mine:
        if dbg_link.ddcci_ok(b) or dbg_link.dbg_ok(b):
            return b
    if mine:
        return mine[0]
    raise SystemExit(f"{u['serial']}: no bus with that EDID serial")


STATE_VCPS = {"input": "60", "brightness": "10", "power": "D6"}


def host_state(bus: int) -> dict:
    """Read-only ddcutil getvcp (DDC/CI 0x37: only while the debug link is OFF)."""
    import ddcutil_run
    out = {}
    for name, code in STATE_VCPS.items():
        r = ddcutil_run.ddc(bus, "getvcp", code, tries=2)
        out[name] = r.stdout.strip() if r else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--pass-label", required=True)
    ap.add_argument("--pages", default="all")
    ap.add_argument("--out")
    ap.add_argument("--bus", type=int, help="override the EDID-serial bus lookup")
    ap.add_argument("--wall-s", type=float, help="wall bound; default 1.25 x calibration-extrapolated full scan")
    ap.add_argument("--no-block", action="store_true", help="byte path even if the firmware advertises the block read")
    ap.add_argument("--link-minutes", type=int, default=60, help="firmware falls back to DDC/CI by itself after this")
    a = ap.parse_args()

    import dbg_link
    import rtd_i2c_bridge
    u = unit_info(a.unit)
    bus = a.bus if a.bus is not None else resolve_bus(u)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else ROOT / f"tmp/regs/live/{u['serial']}-{a.pass_label}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = LOG.open("a")

    def log(s: str) -> None:
        lf.write(f"{isostamp.now()} u{a.unit}/{a.pass_label} {s}\n")

    def note(s: str) -> None:
        print(s, flush=True)
        log(f"NOTE {s}")

    meta = {"serial": u["serial"], "unit": a.unit, "bus": bus, "label": a.pass_label, "start": isostamp.now(),
            "excluded": [[f"{lo:04X}", f"{hi:04X}", why] for lo, hi, why in EXCLUDE]}
    meta["state_before"] = host_state(bus)
    note(f"unit {a.unit} bus {bus} state before: {meta['state_before']}")
    try:
        how = dbg_link.on(bus, a.link_minutes)
    except SystemExit as e:
        note(f"no link: {e}; nothing read")
        return 1
    meta["link"] = how
    res: dict = {"result": "aborted", "abort": "not started"}
    io = rtd_i2c_bridge.Real(bus, allow_write=False, regread=True)
    try:
        hdr = X.read_bytes(io, DIAG_BASE, 3)
        meta["diag_header"] = hdr.hex() if hdr else None
        block = bool(hdr) and X.block_supported(hdr) and not a.no_block
        meta["diag_version"] = hdr[2] if hdr and len(hdr) > 2 else None

        def save(r: dict) -> None:
            tmp = out.with_suffix(".part")
            tmp.write_text(json.dumps({**meta, **r, "partial": True}))
            tmp.replace(out)

        known = known_pages(ROOT)
        res = run_pass(io, parse_pages(a.pages, known), block, log, save, a.wall_s, known)
    finally:
        io.close()
        meta["link_off"] = dbg_link.off(bus)
        lf.flush()
    meta["end"] = isostamp.now()
    meta["state_after"] = host_state(bus)
    out.write_text(json.dumps({**meta, **res}))
    out.with_suffix(".part").unlink(missing_ok=True)
    note(f"{res['result']}{(': ' + res['abort']) if res.get('abort') else ''}; ok={res.get('reads_ok')} "
         f"failed={res.get('reads_failed')} slow={res.get('reads_slow')} elapsed={res.get('elapsed_s')} s path={res.get('path')}; "
         f"link off={meta['link_off']}; state after {meta['state_after']}; {out}")
    lf.close()
    return 0 if res["result"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
