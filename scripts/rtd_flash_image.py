#!/usr/bin/env python3
"""Write a multi-bank firmware image to a Realtek RTD scaler's SPI flash in ONE ISP session.

usage: rtd_flash_image.py <bus> <image.bin> --serial AWT2611000N [--write] [--backup-dir DIR] [--reprotect V|none]
  default = DRY RUN: enter ISP, JEDEC check, read the whole 1 MiB flash once (backup) and the image region again, require identical reads,
            save the backup, list the 4 KiB sectors inside the image length that differ. Nothing written.
  --write : then erase + program + verify each differing sector (rtd_flash_sector.py routines), stop at the
            first verify failure (flash left unprotected, no reprotect of a bad image), else re-protect.
  --serial: label for the backup file; must match `ddcutil detect` for this bus (checked by the caller).
  Revert: rerun with the backup (1 MiB) as <image.bin>: only sectors that differ are rewritten.
  Image sectors beyond its length are never touched (banks 14-15 = settings/gamma data, #8).
Single session = the MCU stays halted throughout, so a half-written image never runs.
Backups: ~/vendors/realtek/analysis/dumps/ (flash contents = vendor binary store, repo CLAUDE.md).
Log: ./tmp/logs/rtd_flash_image.log
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_flash_sector as F  # noqa: E402
from rtd_flash_sector import Rtd, SECTOR, PAGE, JEDEC_OK, SR_PROT, T_READ, T_ERASE_LIMIT, ENGINE_OPS  # noqa: E402

FLASH = 1 << 20
DUMPS = Path.home() / "vendors/realtek/analysis/dumps"


def log(s):
    F.log(s)


SECTOR_TRIES = 5            # failures cluster (i915 stays bit-bang after a GMBUS timeout); 3 aborted once (#12)


def write_sector(isp, addr, new):
    """erase+program+verify; on mismatch re-read once (read-path glitch), else redo, up to SECTOR_TRIES."""
    for n in range(1, SECTOR_TRIES + 1):
        try:
            return _write_sector(isp, addr, new)
        except RuntimeError as e:
            if isp.read_flash(addr, SECTOR) == new:
                log(f"0x{addr:06x}: {e}; re-read matches (read glitch), accepted"); return
            log(f"0x{addr:06x}: {e}; try {n}/{SECTOR_TRIES}")
            if n == SECTOR_TRIES:
                raise


def _write_sector(isp, addr, new):
    for ops in ENGINE_OPS:
        isp.write(*ops)
    isp.write_enable()
    isp.erase_sector(addr)
    isp.wait_wip(f"erase 0x{addr:06x}", T_ERASE_LIMIT)
    if isp.read_flash(addr, SECTOR) != b"\xff" * SECTOR:
        raise RuntimeError(f"sector 0x{addr:06x} not blank after erase")
    isp.program_setup()
    for off in range(0, SECTOR, PAGE):
        pg = new[off:off + PAGE]
        if pg != b"\xff" * PAGE:
            isp.program_page(addr + off, pg)
    back = isp.read_flash(addr, SECTOR)
    if back != new:
        bad = [i for i in range(SECTOR) if back[i] != new[i]]
        detail = " ".join(f"+{i:03x}:{new[i]:02x}->{back[i]:02x}(x{new[i] ^ back[i]:02x})" for i in bad[:12])
        log(f"0x{addr:06x}: {len(bad)} bad byte(s), off%4={sorted({i % 4 for i in bad})}: {detail}")
        raise RuntimeError(f"VERIFY FAILED at 0x{addr + bad[0]:06x}")


NUDGE_ADDR = 0x08          # reserved I2C address: nothing answers, so the transfer NAKs
NUDGE_COUNT = 20           # one NAK did not take on 2026-11-06; 20 did (#26)
# normal sector (erase + 16 pages + verify) ~2.5 s on i915 GMBUS; bit-bang ~25 s. 3x normal = slow
SLOW_SECTOR_S = 7.5


def gmbus_nudge(bus: int) -> None:
    """i915 falls back to bit-banging after a GMBUS timeout and returns to GMBUS only after a bit-banged
    transfer fails: NAK a few transfers to an empty address (#26, 2026-11-06: 25 s -> 2.5 s per sector)."""
    import fcntl, os
    fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
    try:
        fcntl.ioctl(fd, 0x0703, NUDGE_ADDR)          # I2C_SLAVE
        for _ in range(NUDGE_COUNT):
            try:
                os.read(fd, 1)
            except OSError:
                pass
    finally:
        os.close(fd)


def program(isp, a, img, diff, bk, reprot) -> int:
    sr0 = isp.status()
    log(f"status reg = 0x{sr0:02x}")
    if sr0 & SR_PROT:
        isp.release_wp(); isp.unprotect(sr0)
    gmbus_nudge(a.bus)
    t0 = time.monotonic()
    for i, s in enumerate(diff):
        ts = time.monotonic()
        write_sector(isp, s, img[s:s + SECTOR])
        dt = time.monotonic() - ts
        if dt > SLOW_SECTOR_S:
            log(f"0x{s:06x}: {dt:.1f} s > {SLOW_SECTOR_S} s: host I2C on bit-bang? nudging GMBUS")
            gmbus_nudge(a.bus)
        if i % 16 == 15 or i == len(diff) - 1:
            log(f"written+verified {i + 1}/{len(diff)} sectors ({time.monotonic() - t0:.0f}s)")
    log(f"VERIFY OK: all {len(diff)} sectors; revert = rerun with {bk}")
    if reprot is not None:
        isp.reprotect(reprot)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("image", type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--backup-dir", type=Path, default=DUMPS)
    ap.add_argument("--reprotect", default="0x9C")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the dump reads; write+verify every image sector (unit already runs our own build)")
    a = ap.parse_args()
    reprot = None if a.reprotect.lower() == "none" else int(a.reprotect, 0)
    root = F.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    F.LOG = (root / "tmp/logs/rtd_flash_image.log").open("a")
    img = a.image.read_bytes()
    if len(img) % SECTOR or len(img) > FLASH:
        log(f"refuse: image {len(img)} B must be a multiple of {SECTOR} and <= {FLASH}"); return 2
    log(f"mode={'WRITE' if a.write else 'DRY-RUN'} bus=/dev/i2c-{a.bus} image={a.image} ({len(img)} B) serial={a.serial}")
    isp = Rtd(a.bus)
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        log("ISP mode not enabled; aborting"); return 3
    try:
        jid = isp.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
        log(f"JEDEC {jid.hex()}")
        if jid != JEDEC_OK:
            log(f"refuse: JEDEC != {JEDEC_OK.hex()}"); return 4
        if a.no_backup and a.write:
            # Dan 2026-11-05: re-dumping our own builds is wasted time; the vendor backup per unit is kept once
            diff, bk = list(range(0, len(img), SECTOR)), "the unit's vendor backup in ~/vendors/realtek/analysis/dumps"
            log(f"--no-backup: writing all {len(diff)} image sectors, no dump")
            return program(isp, a, img, diff, bk, reprot)
        t0 = time.monotonic()
        d1 = isp.read_flash(0, FLASH)
        log(f"dump 1 read in {time.monotonic() - t0:.1f}s")
        d2 = isp.read_flash(0, len(img))                  # 2nd read only where we write; the rest is never touched (Dan 2026-11-05)
        if d1[:len(img)] != d2:
            nd = sum(x != y for x, y in zip(d1, d2))
            log(f"refuse: two reads differ in {nd} bytes of the image region (unstable read path)"); return 5
        a.backup_dir.mkdir(parents=True, exist_ok=True)
        bk = a.backup_dir / f"jxc-4k-flash-{a.serial}-{time.strftime('%Y%m%d-%H%M%S')}.bin"
        bk.write_bytes(d1)
        log(f"two reads identical over the image region ({len(img)} B); backup {bk}")
        diff = [s for s in range(0, len(img), SECTOR) if d1[s:s + SECTOR] != img[s:s + SECTOR]]
        log(f"{len(diff)}/{len(img) // SECTOR} sectors differ: "
            + ", ".join(f"0x{s:05x}" for s in diff[:12]) + (" ..." if len(diff) > 12 else ""))
        if not a.write:
            log("DRY-RUN complete: nothing erased or programmed"); return 0
        return program(isp, a, img, diff, bk, reprot)
    except Exception as e:
        log(f"ERROR: {e}. Flash NOT re-protected. Revert: rtd_flash_image.py {a.bus} <backup> --serial {a.serial} --write")
        return 7
    finally:
        try:
            isp.write(0xEE, 0x02)
        except OSError:
            pass
        log("scaler reset sent (0xEE <- 0x02)")


if __name__ == "__main__":
    sys.exit(main())
