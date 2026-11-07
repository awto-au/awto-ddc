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
  --write-mode: byte (default) = 1 data byte per I2C message; burst = one I2C write of --burst-chunk bytes (default 256) per
            page to the 0x70 FIFO, ~3x faster per sector; unvalidated on hardware, verify/retry unchanged (#12).
            A burst error redoes that sector in byte mode.
  --serial: must equal the EDID serial on <bus> (i2cbus.require_unit, checked here before ISP is entered, #50.28).
  --identity HOW: only when the EDID is silent (unit held in the safe window): how the caller proved the bus; logged.
  Revert: rerun with the backup (1 MiB) as <image.bin>: only sectors that differ are rewritten.
  Image sectors beyond its length are never touched (banks 14-15 = settings/gamma data, #8).
Single session = the MCU stays halted throughout, so a half-written image never runs.
Backups: ~/vendors/realtek/analysis/dumps/ (flash contents = vendor binary store, repo CLAUDE.md).
Log: ./tmp/logs/rtd_flash_image.log
"""
from __future__ import annotations

import argparse, os, random, signal, sys, time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto  # noqa: E402
import rtd_flash_sector as F  # noqa: E402
import flash_state as S  # noqa: E402
import i2cbus  # noqa: E402
import unit_lock  # noqa: E402
from rtd_flash_sector import Rtd, SECTOR, PAGE, JEDEC_OK, SR_PROT, T_READ, T_ERASE_LIMIT, ENGINE_OPS  # noqa: E402

FLASH = 1 << 20
DUMPS = Path.home() / "vendors/realtek/analysis/dumps"


def unit_log(serial: str, s: str) -> None:
    """ISP enter/exit into the per-monitor log Dan watches (dev.py writes the rest there)."""
    with (F.repo_root() / f"tmp/logs/unit-{serial}.log").open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} [rtd_flash_image] {s}\n")


def log(s):
    F.log(s)


SECTOR_TRIES = 5            # failures cluster (i915 stays bit-bang after a GMBUS timeout); 3 aborted once (#12)
BLANK = b"\xff" * SECTOR
BLANK_CRC = S.crc8(BLANK)


PH: dict[str, float] = {}                           # seconds per phase, for the SUMMARY split


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
    for ops in ENGINE_OPS:
        isp.write(*ops)
    isp.write_enable()
    isp.erase_sector(addr)
    isp.wait_wip(f"erase 0x{addr:06x}", T_ERASE_LIMIT)


def program_verify(isp, addr, new, crc_ok):
    """Program an erased sector and verify it; RuntimeError on mismatch."""
    with phase("program"):
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
    r1, r2 = isp.read_flash(0, SECTOR), isp.read_flash(0, SECTOR)
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
    except Exception as e:
        log(f"CRC calibration error ({e}); verifying by readback")
        return False
    log("CRC calibration OK: hw CRC == crc8(readback) over 0x0+4096 and 0x0+1024")
    return True


PROJECT_AFTER = 5                                     # --max-min: project the total from the first 5 sectors
COMMON_END = 0x5000                                   # fw_build --common: [0, 0x5000) of every bank = common code + vectors


def boot_last(diff: list[int]) -> list[int]:
    """Banked sectors first, then the common sectors of banks 1.., then bank 0's (reset vector at 0x0000) as the very last:
    a stop mid-run leaves the old boot path + common code in place for as long as possible."""
    per = BANK // SECTOR
    def key(i):
        common = (i % per) * SECTOR < COMMON_END
        return (common, common and i < per, i)
    return sorted(diff, key=key)


def program(isp, img, diff, reprot, state, hashes, crc_ok, nudge, bk="the unit's vendor backup", tag="", commit="",
            per_sector: bool = False, max_min: float = 0) -> int:
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
    t0 = time.monotonic()
    guard = StopGuard()
    try:
        guard.__enter__()
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
                write_sector(isp, s, img[s:s + SECTOR], crc_ok, nudge)
            state.sectors[i] = hashes[i]
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
            if per_sector and max_min and k + 1 == PROJECT_AFTER and len(diff) > PROJECT_AFTER:
                proj = (time.monotonic() - t0) / PROJECT_AFTER * len(diff) / 60
                log(f"projection after {PROJECT_AFTER} sectors: {proj:.1f} min for {len(diff)} (limit {max_min:g} min)")
                if proj > max_min:
                    state.save()
                    log(f"STOP at a sector boundary: {PROJECT_AFTER}/{len(diff)} written (manifest saved; rerun continues)")
                    if reprot is not None:
                        isp.reprotect(reprot)
                    return 8
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
    except BaseException:
        state.save(source="write-failed")
        raise
    finally:
        guard.__exit__()
    if guard.stop:
        log("stop request deferred to the end of the run (erase-all mode: erased sectors must be written first)")
    state.save(image=tag, image_size=len(img), source="write", commit=commit)
    log(f"burst failures redone in byte mode: {getattr(isp, 'burst_fails', 0)}")
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


def flash(isp, img: bytes, o: Opts, nudge=lambda: None) -> int:
    """Everything after the JEDEC check. Returns rc."""
    t_all = time.monotonic()
    hashes = S.sector_hashes(img)
    nimg = len(hashes)
    rng = random.Random(o.seed)
    state = None if o.full else S.FlashState.load(o.manifest, o.serial, log)
    have_manifest = state is not None
    if state is None:
        state = S.FlashState.empty(o.manifest, o.serial)
        if not o.full:
            log(f"no usable flash-state manifest {o.manifest}: full path")
    else:
        log(f"flash-state manifest: {o.manifest} ({state.image or '?'}, {state.source}, {state.time}, {state.commit})")
    s0 = read_gate(isp) if o.write else b""          # raises before any erase (#71)
    crc_ok = o.write and o.verify == "crc" and crc_calibrate(isp, s0)
    if o.no_backup and o.write:
        # Dan 2026-11-05: re-dumping our own builds is wasted time; the vendor backup per unit is kept once
        bk = "the unit's vendor backup in ~/vendors/realtek/analysis/dumps"
        p = S.plan(hashes, state if have_manifest else None, o.full)
        diff, skipped = list(p.write), len(p.unchanged)
        with phase("gate"):                         # every unchanged sector checked on-chip before any write
            if p.unknown:
                diff = sorted(set(diff) | set(S.resolve_unknown(isp, img, state, p.unknown, log)))
            # Dan 2026-11-06: a sector that is blank (all FF) in the new image is never checked; erase-only if changed
            check = [i for i in p.unchanged if img[i * SECTOR:(i + 1) * SECTOR] != BLANK]
            if check:
                bad = S.drift_check(isp, img, state, check, rng, crc_ok, log)
                if bad:
                    log(f"!!! DRIFT: manifest does not match the flash ({len(bad)} sector(s) {bad[:8]}); "
                        f"manifest untrusted -> full readback diff of the image region (authoritative, ~1/5 of a full write)")
                    diff = S.readback_diff(isp, img, state, log)
                    skipped = nimg - len(diff)
        mode = "full" if (o.full or not have_manifest) else "incremental"
        log(f"--no-backup {mode}: writing {len(diff)}/{nimg} sectors, skipping {skipped} unchanged")
        t_prog = time.monotonic()
        rc = program(isp, img, diff, o.reprot, state, hashes, crc_ok, nudge, bk, o.tag, o.commit, o.per_sector, o.max_min)
        summary(diff, nimg, time.monotonic() - t_prog, time.monotonic() - t_all)
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
    rc = program(isp, img, diff, o.reprot, state, hashes, crc_ok, nudge, str(bk), o.tag, o.commit, o.per_sector)
    summary(diff, nimg, time.monotonic() - t_prog, time.monotonic() - t_all)
    return rc


BANK = 0x10000                                        # 8051 code bank = 64 KiB of flash


def summary(diff: list[int], nimg: int, t_write: float, t_total: float) -> None:
    """End-of-run summary: sectors changed/unchanged, which banks, bytes, speed."""
    per = BANK // SECTOR
    nb = -(-nimg // per)
    by_bank: dict[int, int] = {}
    for i in diff:
        by_bank[i // per] = by_bank.get(i // per, 0) + 1
    wb = len(diff) * SECTOR
    rate = wb / t_write / 1024 if t_write > 0 and wb else 0.0
    log(f"SUMMARY: {nimg} sectors (4 KiB) in {nb} banks (64 KiB): {len(diff)} changed, {nimg - len(diff)} unchanged")
    log("SUMMARY: changed per bank: " + (", ".join(f"bank {b} {n}/{per}" for b, n in sorted(by_bank.items()))
                                        or "none") + f"; {nb - len(by_bank)} banks untouched")
    log(f"SUMMARY: wrote {wb // 1024} KiB in {t_write:.1f} s = {rate:.1f} KiB/s ({rate / 1024:.3f} MB/s); "
        f"{t_total:.1f} s total incl. checks")
    named = ("gate", "erase", "blank", "program", "verify", "final crc")
    split = ", ".join(f"{k} {PH.get(k, 0.0):.1f}" for k in named)
    other = t_total - sum(PH.get(k, 0.0) for k in named)
    log(f"SUMMARY: time split (s): {split}, other (ISP enter/JEDEC/protect/reset) {other:.1f}; "
        f"sector retries {int(PH.get('retries', 0))}")
    global DONE
    DONE = f"{len(diff)}/{nimg} sectors changed, {wb / 1e6:.3f} MB at {rate * 1024 / 1e6:.4f} MB/s"


DONE = ""                                             # one-line result, logged last by main()


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
    ap.add_argument("--max-min", type=float, default=0, help="per-sector: stop at a sector boundary if the total projected "
                    "from the first 5 sectors exceeds this many minutes (0 = off)")
    ap.add_argument("--per-sector", action="store_true",
                    help="erase+program+verify one sector at a time, boot/common sectors last (units without a relay)")
    ap.add_argument("--read-chunk", type=int, default=64, choices=(64, 128, 256),
                    help="bytes per 0x70 FIFO read (256 = NVIDIA DP-AUX cap; transactions, not bytes, cost the time)")
    ap.add_argument("--tag", default="", help="image tag recorded in the manifest (default: image file stem)")
    a = ap.parse_args()
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
    o = Opts(serial=a.serial, write=a.write, no_backup=a.no_backup, full=a.full, verify=a.verify, reprot=reprot, per_sector=a.per_sector, max_min=a.max_min,
             backup_dir=a.backup_dir, manifest=a.manifest or root / "tmp/fw" / f"{a.serial}-flash-state.json",
             tag=a.tag or a.image.stem, commit=S.git_commit(root))
    if not 1 <= a.burst_chunk <= PAGE:
        log(f"refuse: --burst-chunk {a.burst_chunk} outside 1..{PAGE}"); return 2
    seen = i2cbus.require_unit(a.bus, a.serial, a.identity)        # before any ISP traffic (#50.28)
    log(f"unit guard: EDID serial {seen!r} on bus {a.bus}" + (f"; EDID silent, identity per caller: {a.identity}" if seen is None else ""))
    isp = Rtd(a.bus)
    isp.read_chunk = a.read_chunk
    isp.write_mode, isp.burst_chunk = a.write_mode, a.burst_chunk
    entered = False                                   # 0xEE reset only once the ISP-enable write was attempted
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
        return flash(isp, img, o, nudge=lambda: i2cbus.gmbus_nudge(a.bus))
    except ReadPathUnstable as e:
        log(f"refuse: {e}; nothing erased or programmed. Unit in power saving / low flash clock? "
            f"Bring it to an active input, or rerun at 100 kHz (#71)")
        return 5
    except Exception as e:
        log(f"ERROR: {e!r}. Flash NOT re-protected. Revert: rtd_flash_image.py {a.bus} <backup> --serial {a.serial} --write")
        return 7
    finally:
        if entered:
            try:
                isp.write(0xEE, 0x02)
            except OSError:
                pass
            log("scaler reset sent (0xEE <- 0x02)")
            unit_log(a.serial, f"ISP exit (reset) after {time.monotonic() - t_isp:.1f} s")
        log(f"DONE: {time.monotonic() - t_main:.1f} s total, " + (DONE or "nothing written (see above)")
            + f", bus {i2cbus.rate_khz()} kHz")


if __name__ == "__main__":
    sys.exit(main())
