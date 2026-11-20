#!/usr/bin/env python3
"""Write a multi-bank firmware image to a Realtek RTD scaler's SPI flash in ONE ISP session.

usage: rtd_flash_image.py <bus> <image.bin> --serial AWT2611000N [--write] [--no-backup] [--full] [--verify crc|readback]
                          [--write-mode byte|burst] [--burst-chunk N]
                          [--manifest PATH] [--tag TAG] [--backup-dir DIR] [--reprotect V|none] [--identity HOW]
  default = DRY RUN: enter ISP, JEDEC check, read the whole 1 MiB flash once (backup) and the image region again, require identical reads,
            save the backup + flash-state manifest, list the 4 KiB sectors inside the image length that differ. Nothing written.
  --write : then erase + program + verify each differing sector (rtd_flash_sector.py routines), stop at the
            first verify failure (flash left unprotected, no reprotect of a bad image), else re-protect.
  --no-backup (own builds, no dump): INCREMENTAL by the per-unit manifest tmp/fw/<serial>-flash-state.json (scripts/flash_state.py):
            only sectors whose SHA-256 differs from the manifest are written; a drift guard (readback sample + CRC sweep
            of the skipped sectors) runs first and a mismatch falls back to a full readback diff.
            No manifest = write every image sector (then the manifest is created).
  --full  : ignore the manifest, write every image sector.
  --verify: crc (default) = on-chip CRC8 per sector, auto-falls back to readback if the engine fails its
            in-session calibration (docs/flash-crc.md); readback = compare all 4 KiB back (old behaviour).
  --write-mode: burst (default) = one I2C write of --burst-chunk bytes per page to the 0x70 FIFO; byte = 1 data byte per
            I2C message (#12). A burst error redoes that sector in byte mode. byte on a DP AUX bus is switched to burst
            (~90 s per sector in byte mode there, #177).
  --bus-kind ddc|dp-aux|auto: auto = i2cbus.bus_kind (adapter name / connector link); NVIDIA needs it from devices.json.
  --max-min M: time budget, checked BEFORE the first erase: a dry page program (256 x 0xFF, flash unchanged) is timed
            and the run projected; over budget -> byte is retried as burst, else refuse (rc 8, nothing erased).
            Once writing has started the run never stops for time: a stop would leave a mixed image (#177).
Exit: never sends the scaler reset while the image region is mixed (erased / part-written in this or an earlier
  session, manifest source write-in-progress|write-failed): the MCU stays halted in ISP and a rerun continues.
  Last line: `UNIT STATE: ...`.
  --serial: must equal the EDID serial on <bus> (i2cbus.require_unit, checked here before ISP is entered, #50.28).
  --identity HOW: only when the EDID is silent (unit held in the safe window): how the caller proved the bus; logged.
  Revert: rerun with the backup (1 MiB) as <image.bin>: only sectors that differ are rewritten.
  Image sectors beyond its length are never touched (banks 14-15 = settings/gamma data, #8).
Single session = the MCU stays halted throughout, so a half-written image never runs.
Backups: ~/vendors/realtek/analysis/dumps/ (flash contents = vendor binary store, repo CLAUDE.md).
Log: ./tmp/logs/rtd_flash_image.log
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_guard
import flash_manifest as FM
import flash_screen as FSCR
import flash_state as S
import i2cbus
import rtd_flash_sector as F
import rtd_proto
import unit_lock
from rtd_flash_sector import (
    ENGINE_OPS,
    JEDEC_OK,
    PAGE,
    SECTOR,
    SR_PROT,
    T_ERASE_LIMIT,
    T_READ,
    Rtd,
)

FLASH = 1 << 20
DUMPS = Path.home() / "vendors/realtek/analysis/dumps"


def unit_log(serial: str, s: str) -> None:
    """ISP enter/exit into the per-monitor log Dan watches (dev.py writes the rest there)."""
    with (F.repo_root() / f"tmp/logs/unit-{serial}.log").open("a") as f:
        f.write(f"{isostamp.now()} [rtd_flash_image] {s}\n")


def log(s):
    F.log(s)


SECTOR_TRIES = 5            # failures cluster (i915 stays bit-bang after a GMBUS timeout); 3 aborted once (#12)
BLANK = b"\xff" * SECTOR
BLANK_CRC = S.crc8(BLANK)


PH: dict[str, float] = {}                           # seconds per phase, for the SUMMARY split


@dataclass
class RunState:
    """What the flash holds, for the exit decision (reset or stay halted in ISP, #177)."""
    mixed_at_start: bool = False                    # manifest: an earlier session stopped part-way
    touched: bool = False                           # this session erased a sector of the image region
    complete: bool = False                          # every changed sector written + verified (+ final CRC)
    written: int = 0                                # sectors written + verified this session
    total: int = 0                                  # sectors this session set out to write
    source: str = ""                                # where the diff came from (summary)
    manifest: str = "not written"                   # device manifest outcome (summary)
    manifest_cur: bytes | None = None               # manifest sector as read at the start
    skipped: int = 0                                # image sectors that already match (shown on the warning screen)
    image: int = 0                                  # sectors in the image
    erased: int = 0                                 # erase operations (retries and redone sectors count again)

    @property
    def mixed(self) -> bool:
        return (self.touched or self.mixed_at_start) and not self.complete


RUN = RunState()


@contextmanager
def phase(name: str):
    t = time.monotonic()
    try:
        yield
    finally:
        PH[name] = PH.get(name, 0.0) + time.monotonic() - t


class _QuietStream:
    """stdout/stderr after a stop request: the parent (dev.py / agent shell) may be gone; a broken pipe must not abort a flash."""

    def __init__(self, s):
        self.s = s

    def write(self, t):
        try:
            return self.s.write(t)
        except (OSError, ValueError):
            return len(t)

    def flush(self):
        try:
            self.s.flush()
        except (OSError, ValueError):
            pass


class StopGuard:
    """SIGINT/SIGTERM/SIGHUP during a write never stop mid-sector (unit 3, 2026-11-07T19:42: killed after the erase-all, dead).
    Per-sector: stop at the next sector boundary. Erase-all: erased sectors only boot once written, so finish the run.
    The 3rd signal forces an exit (KeyboardInterrupt). SIGKILL cannot be caught: never send it to a flash."""
    SIGS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

    def __init__(self):
        self.count, self.old = 0, {}

    @property
    def stop(self) -> bool:
        return self.count > 0

    def _on(self, signum, _frame):
        self.count += 1
        if not isinstance(sys.stdout, _QuietStream):
            sys.stdout, sys.stderr = _QuietStream(sys.stdout), _QuietStream(sys.stderr)
        if self.count >= 3:
            log(f"{signal.Signals(signum).name} x{self.count}: forced exit, flash state unknown (manifest marks it)")
            raise KeyboardInterrupt
        log(f"{signal.Signals(signum).name}: stop requested ({self.count}/3); finishing the current sector / erased set first")

    def __enter__(self):
        for s in self.SIGS:
            self.old[s] = signal.signal(s, self._on)
        return self

    def __exit__(self, *_):
        for s, h in self.old.items():
            signal.signal(s, h)


IO_ERRORS = (RuntimeError, TimeoutError, OSError)   # TimeoutError: engine/CRC/WIP poll limits; OSError: ENXIO when i915 drops to bit-bang


def _nudge_safe(nudge) -> None:
    try:
        nudge()
    except OSError as e:
        log(f"GMBUS nudge failed: {e}")


# #167: a NAK mid-burst can leave the SPI engine busy (reg 0x60 go bit stuck); retries on the same ISP session then fail.
ENGINE_GO = 0x01                                     # reg 0x60 bit0: command go / busy
ISP_EN = 0x80                                        # reg 0x6F bit7: ISP enable (MCU halted)
RESET_ISP_LIMIT_S = 5.0                              # ISP answering again after the 0xEE reset: no datasheet figure; the
                                                     # 5 s monitor-return bound; expiry raises (flash stays failed)
RESET_POLL_S = 0.02
RECOVERIES = {"clear": 0, "reset": 0}


def _engine_idle(isp) -> bool:
    try:
        return not isp.read(0x60) & ENGINE_GO
    except OSError:
        return False


def recover_isp(isp, why: str, force_reset: bool = False) -> None:
    """Stuck SPI engine: clear the go bit (MCU stays halted); still busy -> scaler reset, ISP re-entry, JEDEC, WP release."""
    if not force_reset:
        try:
            isp.write(0x60, 0x00)
        except OSError:
            pass
        if _engine_idle(isp):
            RECOVERIES["clear"] += 1
            log(f"recover ({why}): reg 0x60 cleared, SPI engine idle"); return
    t0 = time.monotonic()
    try:
        isp.write(0xEE, 0x02)
    except OSError:
        pass                                         # the reset can cut its own ACK
    while True:
        try:
            isp.write(0x6F, ISP_EN)
            if isp.read(0x6F) & ISP_EN and _engine_idle(isp):
                break
        except OSError:
            pass
        if time.monotonic() - t0 > RESET_ISP_LIMIT_S:
            raise TimeoutError(f"recover ({why}): ISP not back {RESET_ISP_LIMIT_S} s after the scaler reset")
        time.sleep(RESET_POLL_S)
    jid = isp.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
    if jid != JEDEC_OK:
        raise RuntimeError(f"recover ({why}): JEDEC {jid.hex()} != {JEDEC_OK.hex()} after the ISP re-entry")
    sr = isp.status()
    if sr & SR_PROT:
        isp.release_wp(); isp.unprotect(sr)
    RECOVERIES["reset"] += 1
    log(f"recover ({why}): scaler reset + ISP re-entry in {time.monotonic() - t0:.2f} s, JEDEC ok, status 0x{isp.status():02x}")


def _recover_if_stuck(isp, why: str) -> None:
    forced = INJECT.take_reset()
    if forced or not _engine_idle(isp):
        recover_isp(isp, why, force_reset=forced)


class _Inject:
    """Test hook (#167): $AWTO_FLASH_INJECT = JSON file {"sector": "0x20000", "fail": N, "reset": M}. The first N programs of
    that sector raise like a burst NAK; the next M recoveries take the reset path. Counts are spent in the file (survive a rerun)."""
    def __init__(self):
        self.path = Path(os.environ["AWTO_FLASH_INJECT"]) if os.environ.get("AWTO_FLASH_INJECT") else None

    def _spend(self, key: str, sector: int | None = None) -> bool:
        if not self.path or not self.path.is_file():
            return False
        import json
        d = json.loads(self.path.read_text())
        if d.get(key, 0) <= 0 or (sector is not None and int(d["sector"], 0) != sector):
            return False
        d[key] -= 1
        self.path.write_text(json.dumps(d))
        log(f"INJECT {key} (left {d[key]})")
        return True

    def take_fail(self, sector: int) -> bool:
        return self._spend("fail", sector)

    def take_reset(self) -> bool:
        return self._spend("reset")


INJECT = _Inject()


def write_sector(isp, addr, new, crc_ok=False, nudge=lambda: None):
    """erase+program+verify; on mismatch re-read once (read-path glitch), else redo, up to SECTOR_TRIES.
    Timeout/OSError (bus dropped to bit-bang) nudge GMBUS first, then retry like a verify failure (#50.1)."""
    for n in range(1, SECTOR_TRIES + 1):
        try:
            return _write_sector(isp, addr, new, crc_ok)
        except IO_ERRORS as e:
            PH["retries"] = PH.get("retries", 0) + 1
            if not isinstance(e, RuntimeError):
                _nudge_safe(nudge)
            _recover_if_stuck(isp, f"0x{addr:06x} try {n}")
            try:
                with phase("verify"):
                    same = isp.read_flash(addr, SECTOR) == new
            except IO_ERRORS as e2:
                log(f"0x{addr:06x}: re-read failed: {e2!r}")
                same = False
            if same:
                log(f"0x{addr:06x}: {e!r}; re-read matches (read glitch), accepted"); return
            log(f"0x{addr:06x}: {e!r}; try {n}/{SECTOR_TRIES}")
            if n == SECTOR_TRIES:
                raise


def erase_with_retry(isp, addr, nudge=lambda: None):
    """One erase, SECTOR_TRIES attempts; nudge GMBUS between tries (#50.1/#50.4). Erase is idempotent."""
    for n in range(1, SECTOR_TRIES + 1):
        try:
            return erase_sector(isp, addr)
        except IO_ERRORS as e:
            PH["retries"] = PH.get("retries", 0) + 1
            log(f"0x{addr:06x}: erase {e!r}; try {n}/{SECTOR_TRIES}")
            if n == SECTOR_TRIES:
                raise
            _nudge_safe(nudge)


def erase_sector(isp, addr):
    RUN.erased += 1
    for ops in ENGINE_OPS:
        isp.write(*ops)
    isp.write_enable()
    isp.erase_sector(addr)
    isp.wait_wip(f"erase 0x{addr:06x}", T_ERASE_LIMIT)


def program_verify(isp, addr, new, crc_ok):
    """Program an erased sector and verify it; RuntimeError on mismatch."""
    with phase("program"):
        if INJECT.take_fail(addr):
            isp._byte_sector = addr                  # as a real burst failure: the redo runs in byte mode
            raise RuntimeError(f"page 0x{addr:06x} burst failed at +0x00: injected (#167 test)")
        isp.program_setup()
        for off in range(0, SECTOR, PAGE):
            pg = new[off:off + PAGE]
            if pg != b"\xff" * PAGE:
                isp.program_page(addr + off, pg)
    _verify(isp, addr, new, crc_ok)


def _write_sector(isp, addr, new, crc_ok):
    """Retry path: erase + blank check + program + verify one sector."""
    with phase("erase"):
        erase_sector(isp, addr)
    # blank check: CRC when validated (~10 ms) else readback (~0.4 s); a missed erase also fails the verify below
    with phase("blank"):
        if crc_ok:
            not_blank = isp.flash_crc(addr, SECTOR) != BLANK_CRC
        else:
            not_blank = isp.read_flash(addr, SECTOR) != b"\xff" * SECTOR
    if not_blank:
        raise RuntimeError(f"sector 0x{addr:06x} not blank after erase")
    program_verify(isp, addr, new, crc_ok)


def _verify(isp, addr, new, crc_ok):
    with phase("verify"):
        if crc_ok and isp.flash_crc(addr, SECTOR) == S.crc8(new):
            return                                       # CRC8 miss chance 1/256 per corrupted sector (docs/flash-crc.md)
        back = isp.read_flash(addr, SECTOR)              # CRC mismatch (or crc off): readback names the bad bytes
    if back != new:
        bad = [i for i in range(SECTOR) if back[i] != new[i]]
        detail = " ".join(f"+{i:03x}:{new[i]:02x}->{back[i]:02x}(x{new[i] ^ back[i]:02x})" for i in bad[:12])
        log(f"0x{addr:06x}: {len(bad)} bad byte(s), off%4={sorted({i % 4 for i in bad})}: {detail}")
        raise RuntimeError(f"VERIFY FAILED at 0x{addr + bad[0]:06x}")
    if crc_ok:
        raise RuntimeError(f"0x{addr:06x}: hw CRC != crc8(new) but readback matches: CRC engine untrustworthy")


# normal sector (erase + 16 pages + verify) ~2.5 s on i915 GMBUS; bit-bang ~25 s. 3x normal = slow
SLOW_SECTOR_S = 7.5


class ReadPathUnstable(RuntimeError):
    """Two readbacks of one range differ: every readback-based decision (diff, drift, blank, verify) is unsafe."""


def read_gate(isp) -> bytes:
    """Before any erase: two readbacks of sector 0 must match. Seen on unit 3 in D1 power saving at 1 MHz: ~60 bad
    bytes per 4 KiB plus a stale first byte per 1 KiB read, while the on-chip CRC stayed right (#71)."""
    t = time.monotonic()
    r1, r2 = isp.read_flash(0, SECTOR), isp.read_flash(0, SECTOR)
    S.STATS.sector_reads += 2
    S.STATS.read_s = (time.monotonic() - t) / 2
    if r1 != r2:
        nd = sum(x != y for x, y in zip(r1, r2))
        raise ReadPathUnstable(f"read path unstable: two readbacks of sector 0 differ in {nd} byte(s)")
    return r1


def crc_calibrate(isp, s0: bytes) -> bool:
    """Is the on-chip CRC the CRC8 we reproduce? Compare against crc8 of a readback of sector 0 (real code,
    non-trivial) and of its first 1 KiB (a second range, catches a stale crc_done/result). False -> readback verify.
    s0 = sector 0 as read_gate read it (twice, equal), so a mismatch means the CRC engine, not the read path."""
    try:
        for n in (SECTOR, 1024):
            data = s0[:n]
            hw, py = isp.flash_crc(0, n), S.crc8(data)
            if hw != py:
                log(f"CRC calibration FAILED 0x0+{n}: hw 0x{hw:02x} != py 0x{py:02x} "
                    f"(py excl-end 0x{S.crc8(data[:-1]):02x}, py skip-first 0x{S.crc8(data[1:]):02x}); verifying by readback")
                return False
    except (OSError, RuntimeError, ValueError) as e:
        log(f"CRC calibration error ({e}); verifying by readback")
        return False
    log("CRC calibration OK: hw CRC == crc8(readback) over 0x0+4096 and 0x0+1024")
    return True


PROJECT_AFTER = 5                                     # log the measured rate after 5 sectors (no stop, #177)
MIXED_SOURCES = ("write-in-progress", "write-failed")  # manifest sources of a session that ended part-way
COMMON_END = 0x5000                                   # fw_build --common: [0, 0x5000) of every bank = common code + vectors


def _phase(i: int) -> str:
    """Name of the boot_last group sector i belongs to (shown on the flash warning screen)."""
    per = BANK // SECTOR
    common = (i % per) * SECTOR < COMMON_END
    return ("BOOT" if i < per else "COMMON") if common else ("BANK0" if i < per else "BANKED")


def boot_last(diff: list[int]) -> list[int]:
    """Order for a stop mid-run: banked sectors of banks 1.. first, then bank 0's banked part (DDR/startup init,
    fw/bank_layout.tsv region 0), then common of banks 1.., bank 0's common (reset vector 0x0000) very last.
    A relinked image is still unbootable when mixed (calls cross banks): the pre-write budget is the real guard (#177)."""
    per = BANK // SECTOR
    def key(i):
        common = (i % per) * SECTOR < COMMON_END
        return (common, i < per, i)
    return sorted(diff, key=key)


ERASE_S = 0.2                       # MX25L8006E tSE max (Table 13); poll messages are counted on top
SECTOR_MSGS = (33, 8)               # (writes, reads) per sector outside the pages: engine ops, WREN, erase, WIP, CRC verify


def _msg_cost(isp, n: int = 4) -> tuple[float, float]:
    """Seconds per register write and per register read on this bus (0x64 = staged address byte, re-staged by every op)."""
    t = time.monotonic()
    for _ in range(n):
        isp.write(0x64, 0)
    tw = (time.monotonic() - t) / n
    t = time.monotonic()
    for _ in range(n):
        isp.read(0x6F)
    return tw, (time.monotonic() - t) / n


def dry_page(isp, addr: int, crc_ok: bool) -> float:
    """Seconds for one page program through the session's real path, flash unchanged: 256 x 0xFF at `addr` (a sector of
    this run, far from boot; NOR program clears no bits with 0xFF; a protected flash ignores it). Sector checked after."""
    for ops in ENGINE_OPS:                          # engine's per-page WREN opcode must be set before any program kick
        isp.write(*ops)
    sec = addr & ~(SECTOR - 1)
    before = isp.flash_crc(sec, SECTOR) if crc_ok else isp.read_flash(sec, SECTOR)
    fails, byte_sec = getattr(isp, "burst_fails", 0), getattr(isp, "_byte_sector", None)
    isp.dry = True
    t = time.monotonic()
    try:
        isp.program_setup()
        isp.program_page(addr, b"\xff" * PAGE)
    finally:
        dt = time.monotonic() - t
        isp.dry = False
        if hasattr(isp, "burst_fails"):
            isp.burst_fails, isp._byte_sector = fails, byte_sec
        if (isp.flash_crc(sec, SECTOR) if crc_ok else isp.read_flash(sec, SECTOR)) != before:
            RUN.touched = True                      # impossible for NOR; if it happens, never reset onto it
            raise RuntimeError(f"sector 0x{sec:06x} changed after the 0xFF dry page program: flash state unknown")
    return dt


def project_s(isp, img: bytes, diff: list[int], crc_ok: bool) -> float:
    """Projected seconds to write `diff`: per non-blank page the timed dry page, per sector the fixed messages + tSE."""
    tp = dry_page(isp, max(diff) * SECTOR + SECTOR - PAGE, crc_ok)
    tw, tr = _msg_cost(isp)
    pages = sum(img[i * SECTOR + o:i * SECTOR + o + PAGE] != b"\xff" * PAGE for i in diff for o in range(0, SECTOR, PAGE))
    fixed = SECTOR_MSGS[0] * tw + SECTOR_MSGS[1] * tr + ERASE_S
    total = pages * tp + len(diff) * fixed
    log(f"projection ({getattr(isp, 'write_mode', '?')}): dry page {tp * 1e3:.1f} ms, write {tw * 1e3:.2f} ms, "
        f"read {tr * 1e3:.2f} ms -> {pages} pages + {len(diff)} sectors = {total / 60:.1f} min")
    return total


def budget(isp, img: bytes, diff: list[int], o, crc_ok: bool) -> float | None:
    """Before any erase: projected seconds within o.max_min, else (byte) retry the projection in burst.
    Returns the projection, or None = refuse (nothing erased). A failing burst dry page switches the run to byte."""
    if not diff:
        return 0.0
    try:
        proj = project_s(isp, img, diff, crc_ok)
    except RuntimeError as e:
        if getattr(isp, "write_mode", "byte") != "burst" or "changed after the 0xFF dry page" in str(e):
            raise
        log(f"WARN: burst dry page failed ({e}); this run uses byte mode (#167)")
        isp.write_mode = "byte"
        proj = project_s(isp, img, diff, crc_ok)
    if not o.max_min or proj <= o.max_min * 60:
        return proj
    if getattr(isp, "write_mode", "burst") == "byte":
        log(f"byte mode projects {proj / 60:.1f} min > {o.max_min:g} min: trying burst")
        isp.write_mode = "burst"
        try:
            proj = project_s(isp, img, diff, crc_ok)
        except RuntimeError as e:
            log(f"burst dry page failed ({e})")
            isp.write_mode, proj = "byte", float("inf")
        if proj <= o.max_min * 60:
            log(f"WARN: write mode switched byte -> burst ({proj / 60:.1f} min)")
            return proj
    log(f"REFUSED before any erase: {len(diff)} sectors project to {proj / 60:.1f} min > budget {o.max_min:g} min. "
        f"Flash unchanged. Use a DDC (HDMI) bus, or raise --max-min")
    return None


def _uncounted_erase(isp, addr, nudge) -> None:
    n = RUN.erased
    erase_with_retry(isp, addr, nudge)
    RUN.erased = n                                   # manifest erases are not image sector erases


def invalidate_manifest(isp, crc_ok: bool, nudge) -> None:
    """Erase the manifest sector (when not blank) before the first image erase."""
    a = FM.MANIFEST_ADDR
    with phase("manifest"):
        blank = isp.flash_crc(a, SECTOR) == BLANK_CRC if crc_ok else isp.read_flash(a, SECTOR) == BLANK
        if not blank:
            _uncounted_erase(isp, a, nudge)
    RUN.manifest_cur = None
    RUN.manifest = "invalidated (erased) at the start of the writes"
    log("device manifest invalidated before the first image erase")


def write_manifest(isp, img: bytes, crc_ok: bool, nudge) -> None:
    """Device manifest for `img`: skipped when the device already holds exactly it; else erase (unless blank),
    program the body pages, the commit page LAST, verify. Failure is logged, never fails the flash (image already verified)."""
    a, want = FM.MANIFEST_ADDR, FM.build(img)
    if len(img) // SECTOR > FM.capacity() or len(img) // SECTOR > a // SECTOR:
        RUN.manifest = "not written (image too large for the manifest)"
        log(f"WARN: {RUN.manifest}")
        return
    cur = RUN.manifest_cur
    if cur == want:
        RUN.manifest = "unchanged (valid, identical): nothing written"
        log(f"device manifest {RUN.manifest}")
        return
    with phase("manifest"):
        try:
            if cur is None or cur != BLANK:
                if cur is None:                          # invalidated by us: blank already, unless that erase was skipped
                    if (isp.flash_crc(a, SECTOR) != BLANK_CRC) if crc_ok else (isp.read_flash(a, SECTOR) != BLANK):
                        _uncounted_erase(isp, a, nudge)
                else:
                    _uncounted_erase(isp, a, nudge)
            isp.program_setup()
            for off, pg in FM.pages(want):
                isp.program_page(a + off, pg)
            _verify(isp, a, want, crc_ok)
        except IO_ERRORS as e:
            RUN.manifest = f"NOT written ({e!r}); next flash rebuilds the diff from the device"
            log(f"WARN: device manifest {RUN.manifest}")
            return
    RUN.manifest = f"written (erase + {len(FM.pages(want))} pages, valid word last)"
    log(f"device manifest {RUN.manifest}")


def program(isp, img, diff, reprot, state, hashes, crc_ok, nudge, bk="the unit's vendor backup", tag="", commit="",
            per_sector: bool = False, max_min: float = 0, dm: bool = False) -> int:
    """Write+verify the sectors in `diff`; the manifest follows: a sector is unknown (null) from its erase until
    its verify passes, so a kill or failure never leaves a stale hash."""
    sr0 = isp.status()
    log(f"status reg = 0x{sr0:02x}")
    if sr0 & SR_PROT:
        isp.release_wp(); isp.unprotect(sr0)
    nudge()
    for i in diff:
        state.sectors[i] = None
    state.save(image=tag, image_size=len(img), source="write-in-progress", commit=commit)
    global INCOMPLETE
    INCOMPLETE = True                                 # from the first erase until the final CRC: never reset into this
    t0 = time.monotonic()
    RUN.total, RUN.written = len(diff), 0
    RUN.touched = RUN.touched or bool(diff)         # from the first erase on, a reset would boot a mixed image
    guard = StopGuard()
    try:
        guard.__enter__()
        if dm and diff:
            invalidate_manifest(isp, crc_ok, nudge)      # before the first image erase: an abort leaves "no manifest"
        if per_sector:
            # no-relay units: erase+program+verify one sector at a time, boot/common last; a stop leaves at most one
            # sector erased and the old boot path intact longest
            diff = boot_last(diff)
            log(f"per-sector mode: {len(diff)} sectors, boot/common last")
        else:
            # Dan 2026-11-06: erase every changed sector up front, then program; no per-sector blank check
            # (a bad erase fails the verify, and that sector is redone alone by write_sector)
            with phase("erase"):
                for k, i in enumerate(diff):
                    erase_with_retry(isp, i * SECTOR, nudge)
                    if k % S.SAVE_EVERY == S.SAVE_EVERY - 1:
                        log(f"erased {k + 1}/{len(diff)} sectors ({time.monotonic() - t0:.0f}s)")
            log(f"erased {len(diff)} sectors ({time.monotonic() - t0:.1f}s)")
        for k, i in enumerate(diff):
            s = i * SECTOR
            ts = time.monotonic()
            try:
                if per_sector:
                    with phase("erase"):
                        erase_with_retry(isp, s, nudge)
                if img[s:s + SECTOR] != BLANK:          # blank in the new image: erase was the whole job
                    program_verify(isp, s, img[s:s + SECTOR], crc_ok)
                else:                                   # but check it, ~10 ms CRC (Dan: else a failed erase reads as good)
                    _verify(isp, s, BLANK, crc_ok)
            except IO_ERRORS as e:
                log(f"0x{s:06x}: {e!r}; redo sector alone (erase+program+verify)")
                if not isinstance(e, RuntimeError):
                    _nudge_safe(nudge)
                _recover_if_stuck(isp, f"0x{s:06x}")
                write_sector(isp, s, img[s:s + SECTOR], crc_ok, nudge)
            state.sectors[i] = hashes[i]
            RUN.written = k + 1
            with phase("screen"):                       # #232: progress text on the warning screen, best effort
                FSCR.tick(isp, k, {"phase": _phase(i), "bank": s // BANK, "nbank": FLASH // BANK - 1, "addr": s, "sec": k + 1,
                                   "nsec": len(diff), "pct": (k + 1) * 100 // len(diff), "bad": getattr(isp, "burst_fails", 0),
                                   "recov": sum(RECOVERIES.values()), "t": time.monotonic() - t0, "skip": RUN.skipped,
                                   "nimg": RUN.image})
            dt = time.monotonic() - ts
            if dt > SLOW_SECTOR_S:
                log(f"0x{s:06x}: {dt:.1f} s > {SLOW_SECTOR_S} s: host I2C on bit-bang? nudging GMBUS")
                nudge()
            if k % S.SAVE_EVERY == S.SAVE_EVERY - 1 or k == len(diff) - 1:
                state.save()
                log(f"written+verified {k + 1}/{len(diff)} sectors ({time.monotonic() - t0:.0f}s)")
            if per_sector and guard.stop and k + 1 < len(diff):
                state.save()
                log(f"STOP (signal) at a sector boundary: {k + 1}/{len(diff)} written, none erased-unwritten "
                    f"(manifest saved; rerun continues)")
                if reprot is not None:
                    isp.reprotect(reprot)
                return 9
            if k + 1 == PROJECT_AFTER and len(diff) > PROJECT_AFTER:
                # no time stop once writing: a stop here leaves a mixed image (#177); the budget ran before the first erase
                act = (time.monotonic() - t0) / PROJECT_AFTER * len(diff) / 60
                over = max_min and act > max_min
                log(f"{'WARN: ' if over else ''}after {PROJECT_AFTER} sectors: {act:.1f} min projected for {len(diff)}"
                    + (f" (budget {max_min:g} min); continuing, a stop would leave a mixed image" if over else ""))
        if crc_ok:                                      # end-to-end over the image region, written or skipped
            runs = S._runs([i for i in range(len(img) // SECTOR) if img[i * SECTOR:(i + 1) * SECTOR] != BLANK])
            with phase("final crc"):                    # every non-blank run of the image, written or skipped
                for a, b in runs:
                    lo, hi = a * SECTOR, (b + 1) * SECTOR
                    hw, py = isp.flash_crc(lo, hi - lo), S.crc8(img[lo:hi])
                    if hw != py:
                        for i in range(a, b + 1):
                            state.sectors[i] = None     # unlocalised: next run reads back
                        raise RuntimeError(f"CRC mismatch 0x{lo:06x}-0x{hi:06x} hw 0x{hw:02x} != 0x{py:02x}")
            log(f"final CRC OK over {len(runs)} non-blank run(s)")
        if dm:
            write_manifest(isp, img, crc_ok, nudge)      # LAST: valid word after everything else verified
    except BaseException:
        state.save(source="write-failed")
        raise
    finally:
        guard.__exit__()
    if guard.stop:
        log("stop request deferred to the end of the run (erase-all mode: erased sectors must be written first)")
    state.save(image=tag, image_size=len(img), source="write", commit=commit)
    INCOMPLETE = False
    log(f"burst failures redone in byte mode: {getattr(isp, 'burst_fails', 0)}; ISP recoveries {RECOVERIES}; "
        f"aux-fast pages {getattr(isp, 'aux_pages', 0)}, done-polls {getattr(isp, 'aux_polls', 0)}")
    RUN.complete = True
    FSCR.clear(isp)                                     # #232: OSD off, the new firmware starts with an empty OSD
    log(f"VERIFY OK: {len(diff)} sectors written ({time.monotonic() - t0:.0f}s); revert = rerun with {bk}")
    if reprot is not None:
        isp.reprotect(reprot)
    return 0


@dataclass
class Opts:
    serial: str
    write: bool = False
    no_backup: bool = False
    full: bool = False
    verify: str = "crc"
    reprot: int | None = 0x9C
    backup_dir: Path = DUMPS
    manifest: Path | None = None
    tag: str = ""
    commit: str = ""
    per_sector: bool = False
    max_min: float = 0
    seed: int | None = None
    device_manifest: bool = False                   # write the on-device manifest (docs/flash-registry.md); dev.py flash: on


def volatile_map(img: bytes, nimg: int) -> dict:
    """Runtime-written sectors inside the image (flash_state.VOLATILE_RANGES) + the sector with the per-unit EDID tables."""
    extra = {}
    try:
        from build_fw_edid_sector import edid_offsets
        extra[edid_offsets(img)[0] // SECTOR] = "per-unit EDID tables (dev.py deploy)"
    except Exception as e:                           # noqa: BLE001 - an image without EDID tables: no such sector
        log(f"volatile: no EDID sector found in the image ({e!r})")
    return S.volatile_sectors(nimg, extra)


def flash(isp, img: bytes, o: Opts, nudge=lambda: None) -> int:
    """Everything after the JEDEC check. Returns rc."""
    t_all = time.monotonic()
    hashes = S.sector_hashes(img)
    nimg = len(hashes)
    RUN.__init__()
    prev = S.FlashState.load(o.manifest, o.serial, log)
    if prev is not None and prev.source in MIXED_SOURCES:
        RUN.mixed_at_start = True
        log(f"manifest source {prev.source!r} ({prev.image}): the flash holds a MIXED image from an earlier session")
    state = None if o.full else prev
    if state is None:
        state = S.FlashState.empty(o.manifest, o.serial)
        if not o.full:
            log(f"no usable flash-state manifest {o.manifest}: full path")
    else:
        log(f"flash-state manifest: {o.manifest} ({state.image or '?'}, {state.source}, {state.time}, {state.commit})")
    S.STATS.__init__()
    s0 = read_gate(isp) if o.write else b""          # raises before any erase (#71)
    crc_ok = o.write and o.verify == "crc" and crc_calibrate(isp, s0)
    if o.no_backup and o.write:
        # Dan 2026-11-05: re-dumping our own builds is wasted time; the vendor backup per unit is kept once
        bk = "the unit's vendor backup in ~/vendors/realtek/analysis/dumps"
        icrc = [FM.crc32(img[i * SECTOR:(i + 1) * SECTOR]) for i in range(nimg)]
        vol = volatile_map(img, nimg)
        cur = None                                  # manifest sector as the device holds it (None = not read / erased)
        with phase("gate"):
            if o.full:
                diff = list(range(nimg))
                RUN.source = "--full: every image sector written"
            else:
                cur = isp.read_flash(FM.MANIFEST_ADDR, SECTOR)          # (1) one 4 KiB read
                S.STATS.sector_reads += 1
                man, why = FM.parse(cur)
                if man is not None and man.count != nimg:
                    man, why = None, f"manifest covers {man.count} sectors, this image has {nimg}"
                if man is None:
                    log(f"no valid device manifest ({why}): hardware CRC / read of every image sector builds the diff")
                    RUN.source = f"no valid manifest ({why}); diff from the device"
                    diff = S.device_diff(isp, img, crc_ok, log)
                else:
                    RUN.source = f"device manifest (image_id {man.image_id:08x})"
                    log(f"device manifest valid: {man.count} sectors, image_id {man.image_id:08x}")
                    vsec = sorted(vol)
                    diff = [i for i in range(nimg) if i not in vol and man.crcs[i] != icrc[i]]          # (2)
                    if vsec:
                        log(f"volatile sectors {vsec} ({sorted(set(vol.values()))}): read and compared every flash")
                        for i in vsec:
                            S.STATS.sector_reads += 1
                            if isp.read_flash(i * SECTOR, SECTOR) != img[i * SECTOR:(i + 1) * SECTOR]:
                                diff.append(i)
                    skip = [i for i in range(nimg) if i not in vol and i not in set(diff)]
                    stale = S.truth_check(isp, img, skip, crc_ok, log)                                   # (3) every time
                    diff = sorted(set(diff) | set(stale))
                    if stale:
                        RUN.source += f"; STALE at {len(stale)} sector(s)"
        skipped = nimg - len(diff)
        RUN.skipped, RUN.image = skipped, nimg
        log(f"--no-backup: writing {len(diff)}/{nimg} sectors, skipping {skipped} unchanged ({RUN.source})")
        if budget(isp, img, diff, o, crc_ok) is None:
            return 8
        t_prog = time.monotonic()
        RUN.manifest_cur = cur
        rc = program(isp, img, diff, o.reprot, state, hashes, crc_ok, nudge, bk, o.tag, o.commit, o.per_sector, o.max_min,
                     dm=o.device_manifest)
        summary(diff, nimg, time.monotonic() - t_prog, time.monotonic() - t_all, img)
        return rc
    t0 = time.monotonic()
    d1 = isp.read_flash(0, FLASH)
    log(f"dump 1 read in {time.monotonic() - t0:.1f}s")
    d2 = isp.read_flash(0, len(img))                  # 2nd read only where we write; the rest is never touched (Dan 2026-11-05)
    if d1[:len(img)] != d2:
        nd = sum(x != y for x, y in zip(d1, d2))
        log(f"refuse: two reads differ in {nd} bytes of the image region (unstable read path)"); return 5
    o.backup_dir.mkdir(parents=True, exist_ok=True)
    bk = o.backup_dir / f"jxc-4k-flash-{o.serial}-{time.strftime('%Y%m%d-%H%M%S')}.bin"
    bk.write_bytes(d1)
    log(f"two reads identical over the image region ({len(img)} B); backup {bk}")
    t_prog = time.monotonic()
    for i in range(S.FLASH_SECTORS):                  # a full read is the best manifest source there is
        state.sectors[i] = S.sha(d1[i * SECTOR:(i + 1) * SECTOR])
    state.save(image=f"flash-readback {bk.name}", image_size=FLASH, source="readback", commit=o.commit)
    diff = list(range(nimg)) if o.full else [i for i in range(nimg) if d1[i * SECTOR:(i + 1) * SECTOR] != img[i * SECTOR:(i + 1) * SECTOR]]
    log(f"{len(diff)}/{nimg} sectors differ: "
        + ", ".join(f"0x{i * SECTOR:05x}" for i in diff[:12]) + (" ..." if len(diff) > 12 else ""))
    if not o.write:
        log("DRY-RUN complete: nothing erased or programmed"); return 0
    if budget(isp, img, diff, o, crc_ok) is None:
        return 8
    rc = program(isp, img, diff, o.reprot, state, hashes, crc_ok, nudge, str(bk), o.tag, o.commit, o.per_sector, o.max_min)
    summary(diff, nimg, time.monotonic() - t_prog, time.monotonic() - t_all, img)
    return rc


BANK = 0x10000                                        # 8051 code bank = 64 KiB of flash


def summary(diff: list[int], nimg: int, t_write: float, t_total: float, img: bytes = b"") -> None:
    """End-of-run summary: image / erased / programmed / skipped sectors, pages, bytes, ISP time, reads avoided."""
    per = BANK // SECTOR
    nb = -(-nimg // per)
    by_bank: dict[int, int] = {}
    for i in diff:
        by_bank[i // per] = by_bank.get(i // per, 0) + 1
    skipped = nimg - len(diff)
    prog = [i for i in diff if img[i * SECTOR:(i + 1) * SECTOR] != BLANK] if img else list(diff)
    pages = sum(img[i * SECTOR + o:i * SECTOR + o + PAGE] != b"\xff" * PAGE for i in prog for o in range(0, SECTOR, PAGE)) if img else 0
    wb = len(prog) * SECTOR
    rate = wb / t_write / 1024 if t_write > 0 and wb else 0.0
    st = S.STATS
    avoided = max(0, nimg - st.sector_reads)
    log(f"SUMMARY: sectors: image {nimg}, erased {len(diff)}, programmed {len(prog)} ({pages} pages), "
        f"skipped {skipped} (already match, no need to flash); erase operations {RUN.erased}")
    log(f"SUMMARY: bytes: erased {len(diff) * SECTOR // 1024} KiB, programmed {wb // 1024} KiB, skipped {skipped * SECTOR // 1024} KiB; "
        f"ISP time {t_write:.1f} s writing, {t_total:.1f} s total")
    log(f"SUMMARY: diff from: {RUN.source}")
    log(f"SUMMARY: device reads: {st.sector_reads} of {nimg} image sectors read, {avoided} avoided "
        f"(~{avoided * st.read_s:.1f} s at the measured {st.read_s * 1e3:.0f} ms per 4 KiB); "
        f"truth check: {st.crc_runs} CRC run(s) over {st.crc_sectors} sectors in {st.crc_s:.2f} s")
    log(f"SUMMARY: device manifest {RUN.manifest}")
    log(f"SUMMARY: {nimg} sectors (4 KiB) in {nb} banks (64 KiB): {len(diff)} changed, {skipped} unchanged")
    log("SUMMARY: changed per bank: " + (", ".join(f"bank {b} {n}/{per}" for b, n in sorted(by_bank.items()))
                                        or "none") + f"; {nb - len(by_bank)} banks untouched")
    log(f"SUMMARY: wrote {wb // 1024} KiB in {t_write:.1f} s = {rate:.1f} KiB/s ({rate / 1024:.3f} MB/s); "
        f"{t_total:.1f} s total incl. checks")
    named = ("gate", "erase", "blank", "program", "verify", "final crc", "manifest", "screen")
    split = ", ".join(f"{k} {PH.get(k, 0.0):.1f}" for k in named)
    other = t_total - sum(PH.get(k, 0.0) for k in named)
    log(f"SUMMARY: time split (s): {split}, other (ISP enter/JEDEC/protect/reset) {other:.1f}; "
        f"sector retries {int(PH.get('retries', 0))}")
    global DONE
    DONE = (f"{len(diff)}/{nimg} sectors changed, {wb / 1e6:.3f} MB at {rate * 1024 / 1e6:.4f} MB/s; "
            f"erased {len(diff)} programmed {len(prog)} skipped {skipped} of {nimg}")


DONE = ""                                             # one-line result, logged last by main()
INCOMPLETE = False                                    # program() failed mid-image: MCU stays halted, no reset (#167)
RC_INCOMPLETE = 10                                    # dev.py reruns once in a fresh ISP session


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("image", type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--backup-dir", type=Path, default=DUMPS)
    ap.add_argument("--reprotect", default="0x9C")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the dump reads (unit already runs our own build); incremental by the flash-state manifest")
    ap.add_argument("--full", action="store_true", help="ignore the manifest: write every image sector")
    ap.add_argument("--verify", choices=("crc", "readback"), default="crc")
    ap.add_argument("--write-mode", choices=F.WRITE_MODES, default="burst")
    ap.add_argument("--burst-chunk", type=int, default=F.BURST_CHUNK, help="data bytes per I2C write in burst mode (1..256)")
    ap.add_argument("--manifest", type=Path, help="default: <repo>/tmp/fw/<serial>-flash-state.json")
    ap.add_argument("--identity", help="EDID silent (unit held): how the bus was proven to be this unit")
    ap.add_argument("--max-min", type=float, default=0, help="time budget in minutes, checked before the first erase from a "
                    "timed dry page (0 = off); never stops a run that has started writing")
    ap.add_argument("--bus-kind", choices=("auto", *i2cbus.BUS_KINDS), default="auto",
                    help="ddc / dp-aux (devices.json); auto = from the adapter name / connector link")
    ap.add_argument("--aux-fast", choices=("auto", "off"), default="auto",
                    help="DP-AUX only: 0x4B auto-increment address writes + 2-transfer pages (#254); off = the 0x4A burst path")
    ap.add_argument("--per-sector", action="store_true",
                    help="erase+program+verify one sector at a time, boot/common sectors last (units without a relay)")
    ap.add_argument("--read-chunk", type=int, default=64, choices=(64, 128, 256),
                    help="bytes per 0x70 FIFO read (256 = NVIDIA DP-AUX cap; transactions, not bytes, cost the time)")
    ap.add_argument("--tag", default="", help="image tag recorded in the manifest (default: image file stem)")
    ap.add_argument("--no-device-manifest", action="store_true", help="do not write the on-device manifest (docs/flash-registry.md)")
    ap.add_argument("--direct", action="store_true", help="allow --write outside dev.py flash (both #167 failures were direct runs)")
    a = ap.parse_args()
    if a.write and not os.environ.get("AWTO_VIA_DEV") and not a.direct:
        print("refuse: --write runs through ./dev.py flash (unit guard, 1 MHz bus, retry on an incomplete image, #167); "
              "--direct to override", file=sys.stderr)
        return 2
    with unit_lock.held(a.serial, "rtd_flash_image"):            # one work stream per unit (#65)
        return flash_main(a)


def flash_main(a) -> int:
    i2cbus.dev_hint("flash", "rtd_flash_image.py")
    t_main = time.monotonic()
    reprot = None if a.reprotect.lower() == "none" else int(a.reprotect, 0)
    root = F.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lg = rtd_proto.setup_logs("rtd_flash_image", raw=os.environ.get("AWTO_RAW_TRACE") == "1", merge_pages=True,
                              detail=True)            # per-sector protocol lines -> rtd_flash_image.detail.log
    F.LOG, F.DETAIL = lg.main, lg.detail
    img = a.image.read_bytes()
    if len(img) % SECTOR or len(img) > FLASH:
        log(f"refuse: image {len(img)} B must be a multiple of {SECTOR} and <= {FLASH}"); return 2
    log(f"mode={'WRITE' if a.write else 'DRY-RUN'} bus=/dev/i2c-{a.bus} image={a.image} ({len(img)} B) serial={a.serial} "
        f"no_backup={a.no_backup} full={a.full} verify={a.verify} write_mode={a.write_mode} burst_chunk={a.burst_chunk}")
    kind = i2cbus.bus_kind(a.bus) if a.bus_kind == "auto" else a.bus_kind
    log(f"bus kind: {kind} ({i2cbus.adapter_name(a.bus) or 'no adapter name'}{', given' if a.bus_kind != 'auto' else ''})")
    FSCR.BUS = a.bus                                    # the screen marker file is per bus
    if kind == "dp-aux" and a.write_mode == "byte":
        log("WARN: --write-mode byte on DP AUX (~90 s per sector, #177): using burst")
        a.write_mode = "burst"
    o = Opts(serial=a.serial, write=a.write, no_backup=a.no_backup, full=a.full, verify=a.verify, reprot=reprot, per_sector=a.per_sector, max_min=a.max_min,
             backup_dir=a.backup_dir, manifest=a.manifest or root / "tmp/fw" / f"{a.serial}-flash-state.json",
             tag=a.tag or a.image.stem, commit=S.git_commit(root),
             device_manifest=not a.no_device_manifest)
    prev = S.FlashState.load(o.manifest, o.serial, lambda _m: None)
    RUN.mixed_at_start = prev is not None and prev.source in MIXED_SOURCES   # also guards exits before flash()
    if not 1 <= a.burst_chunk <= PAGE:
        log(f"refuse: --burst-chunk {a.burst_chunk} outside 1..{PAGE}"); return 2
    if a.write:
        disk_guard.require_free("flash")                           # ENOSPC mid-flash left unit 2 mixed (#77)
    seen = i2cbus.require_unit(a.bus, a.serial, a.identity)        # before any ISP traffic (#50.28)
    log(f"unit guard: EDID serial {seen!r} on bus {a.bus}" + (f"; EDID silent, identity per caller: {a.identity}" if seen is None else ""))
    isp = Rtd(a.bus)
    isp.read_chunk = a.read_chunk
    isp.write_mode, isp.burst_chunk = a.write_mode, a.burst_chunk
    entered = False                                   # 0xEE reset only once the ISP-enable write was attempted
    global INCOMPLETE
    INCOMPLETE = False                                # per run (module state outlives a call in tests / imports)
    try:
        entered = True
        unit_log(a.serial, f"ISP enter (MCU halted) bus {a.bus}")
        t_isp = time.monotonic()
        isp.write(0x6F, 0x80)
        if not isp.read(0x6F) & 0x80:
            entered = False                           # MCU never halted: nothing to reset
            log("ISP mode not enabled; aborting"); return 3
        jid = isp.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
        log(f"JEDEC {jid.hex()}")
        if jid != JEDEC_OK:
            log(f"refuse: JEDEC != {JEDEC_OK.hex()}"); return 4
        if kind == "dp-aux" and a.aux_fast == "auto" and a.write_mode == "burst":
            isp.enable_aux_fast()
        return flash(isp, img, o, nudge=lambda: i2cbus.gmbus_nudge(a.bus))
    except ReadPathUnstable as e:
        log(f"refuse: {e}; nothing erased or programmed. Unit in power saving / low flash clock? "
            f"Bring it to an active input, or rerun at 100 kHz (#71)")
        return 5
    except Exception as e:  # noqa: BLE001  last resort: logged with the rerun command; finally re-protects / resets
        again = f"./dev.py flash --unit <n> {a.image}" if a.no_backup else f"rtd_flash_image.py {a.bus} <backup> --serial {a.serial} --write"
        if INCOMPLETE:
            log(f"ERROR: {e!r}. Image INCOMPLETE: MCU left halted in ISP (no reset into a partial image). Rerun: {again}")
            return RC_INCOMPLETE
        log(f"ERROR: {e!r}. Flash NOT re-protected. Rerun: {again}")
        return 7
    finally:
        if entered and (INCOMPLETE or RUN.mixed):
            # a reset boots the mixed image: on DP the link (and with it this bus) dies with it (unit 3, #177)
            st = (f"MIXED image ({RUN.written}/{RUN.total} sectors of {o.tag} written this session"
                  + (", earlier session part-way too" if RUN.mixed_at_start else "")
                  + "), MCU HALTED in ISP, NO reset sent. "
                  f"Rerun the same flash on bus {a.bus} to continue (manifest); do not power-cycle (it would boot the mix)")
            log(f"UNIT STATE: {st}")
            unit_log(a.serial, f"ISP held (no reset, mixed / incomplete image) after {time.monotonic() - t_isp:.1f} s")
        elif entered:
            try:
                isp.write(0xEE, 0x02)
            except OSError:
                pass
            log("scaler reset sent (0xEE <- 0x02)")
            log("UNIT STATE: " + ("new image verified, reset sent (rebooting into it)" if RUN.complete
                                  else "flash unchanged by this session (old image), reset sent"))
            unit_log(a.serial, f"ISP exit (reset) after {time.monotonic() - t_isp:.1f} s")
        log(f"DONE: {time.monotonic() - t_main:.1f} s total, " + (DONE or "nothing written (see above)")
            + (", DP AUX (I2C speed n/a)" if kind == "dp-aux" else f", bus {i2cbus.rate_khz()} kHz"))


if __name__ == "__main__":
    sys.exit(main())
