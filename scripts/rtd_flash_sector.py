#!/usr/bin/env python3
"""Erase + reprogram ONE 4 KiB sector of a Realtek RTD scaler's SPI flash over DDC ISP (I2C 0x4A).

usage: rtd_flash_sector.py <bus> <sector_addr> <file4k> [--write] [--expect-current FILE]
                           [--backup-dir DIR] [--no-reset]
       rtd_flash_sector.py --selftest
  default (no --write) = DRY RUN: enter ISP, read JEDEC + status, read the sector, save a timestamped
                         backup, compare current vs <file4k> (and vs --expect-current). No erase, no program,
                         no status-register write, no SPI-engine config writes.
  --write              : the only way to modify flash. Requires JEDEC C2 20 14, 4 KiB-aligned addr, exactly
                         4096-byte file, and (if --expect-current given) current sector == that file.
  --expect-current F   : abort unless the sector currently equals F (guards against overwriting unknown data).
Sequence (--write): backup -> release flash WP# (scaler GPIO: sys 0x1036/0xFE26) -> engine opcode setup ->
  WRSR=0x00 as write-after-WREN, verify SRWD+BP == 0 -> erase 4K (op 0x20) -> blank check -> program
  16 x 256 B pages (op 0x02 via reg 0x6F=0xA0) -> read back + compare -> restore status reg -> reset scaler.
  --selftest : no hardware; prints the register writes the unprotect would do (against a simulated chip).
Why WRSR failed before: SRWD=1 + WP# low = hardware protect, WRSR ignored; WP# is a scaler GPIO that must be
  released first. docs/flash-unprotect.md.
Revert: run again with the backup file as <file4k> (and --expect-current <file4k of the new data>).
Protocol: docs/reversing/realtek-rtd/README.md; SPI-engine flow after ghent360/RTD-2660-Programmer main.cpp
  (reg 0x60 = type<<5 | nw<<3 | nr<<1 | go; types READ=2 WRITE_AFTER_WREN=3 ERASE=5).
Monitor MCU is stopped while in ISP; the final 0xEE=0x02 resets the scaler (as rtd_isp_probe --resume).
Log: ./tmp/logs/rtd_flash_sector.log
"""
import argparse, ctypes, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_isp_probe import Isp, Msg, ISP_ADDR, repo_root  # noqa: E402

SECTOR = 4096
PAGE = 256
JEDEC_OK = bytes.fromhex("c22014")      # Macronix 1 MiB, seen on all dumped units (docs/monitors/README.md)
T_READ, T_WRITE_WREN, T_ERASE = 2, 3, 5
OP_ERASE_4K, OP_RDSR, OP_WRSR = 0x20, 0x05, 0x01
SR_WIP, SR_WEL = 0x01, 0x02
SR_PROT = 0x9C                          # SRWD | BP2 | BP1 | BP0 (MX25L8006E Table 5); bits 6,5 reserved
# Flash WP# is a scaler GPIO. Realtek PlugIn_ISP.dll FUN_1001bd80 and naorunaoru/rtdflash:
# WriteRegBitEx(sys 0x1036, 0xF8, 0x01); WriteRegBitEx(sys 0xFE26, 0xFE, ISP_WP bValueHigh=1)
WP_RELEASE = ((0x1036, 0xF8, 0x01), (0xFE26, 0xFE, 0x01))
# Engine opcode config (ghent360 SetupChipCommands + rtdflash common_setup): WREN, EWSR, READ, FAST_READ, PP, RDSR
ENGINE_OPS = ((0x62, 0x06), (0x63, 0x50), (0x6A, 0x03), (0x6B, 0x0B), (0x6D, 0x02), (0x6E, 0x05))
UNPROTECT_TRIES = 3

# Timeouts (stall-style, one I2C poll ~ 5-10 ms on DP-AUX buses; bench: scripts/i2c_bench.py)
# SPI engine busy: probe uses 20 polls for a 1 KiB read; same here, on expiry: abort, log reg 0x60.
POLL_MAX = 20
# MX25L8006E v1.6 Table 13 max: tW (WRSR) 40 ms, tSE 200 ms, tPP 3 ms. Limits = 1.25x max.
# Poll granularity (~5-10 ms per I2C poll) means the page limit is only checked between polls.
# On expiry: abort, log op + elapsed.
T_WRSR_LIMIT, T_ERASE_LIMIT, T_PROG_LIMIT = 0.05, 0.25, 0.004

LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    LOG.write(line + "\n"); LOG.flush()


class Rtd(Isp):
    def write_block(self, reg, data):
        w = ctypes.create_string_buffer(bytes([reg]) + bytes(data), 1 + len(data))
        self._xfer([Msg(ISP_ADDR, 0, 1 + len(data), ctypes.addressof(w))])

    def wait_engine(self, what):
        for _ in range(POLL_MAX):
            if not self.read(0x60) & 1:
                return
        raise TimeoutError(f"SPI engine busy after {POLL_MAX} polls ({what}), reg60=0x{self.read(0x60):02x}")

    def common(self, typ, op, nr=0, nw=0, val=0):
        v = (typ << 5) | ((nw & 3) << 3) | ((nr & 3) << 1)
        self.write(0x60, v); self.write(0x61, op)
        for i, r in enumerate((0x64, 0x65, 0x66)[:nw]):
            self.write(r, (val >> (8 * (nw - 1 - i))) & 0xFF)
        self.write(0x60, v | 1)
        self.wait_engine(f"op 0x{op:02x}")
        return int.from_bytes(bytes(self.read(r) for r in (0x67, 0x68, 0x69)[:nr]), "big") if nr else 0

    def status(self):
        return self.common(T_READ, OP_RDSR, nr=1)

    # scaler "system" registers: page select via scaler reg 0x9F, then ISP F4 (index) / F5 (data)
    def sys_read(self, addr):
        self.write(0xF4, 0x9F); self.write(0xF5, addr >> 8)
        self.write(0xF4, addr & 0xFF)
        return self.read(0xF5)

    def sys_write(self, addr, val):
        self.write(0xF4, 0x9F); self.write(0xF5, addr >> 8)
        self.write(0xF4, addr & 0xFF); self.write(0xF5, val)

    def release_wp(self):
        for addr, and_mask, or_val in WP_RELEASE:
            v = (self.sys_read(addr) & and_mask) | or_val
            self.sys_write(addr, v)
            got = self.sys_read(addr)
            log(f"WP# release: sys[0x{addr:04x}] <- 0x{v:02x}, readback 0x{got:02x}")
            if got != v:
                raise RuntimeError(f"sys[0x{addr:04x}] readback 0x{got:02x} != 0x{v:02x}; WP# GPIO not released")

    def wrsr(self, val, what):
        """WRSR as write-after-WREN: the engine emits WREN (reg 0x62) then 0x01 + val; then wait tW."""
        self.common(T_WRITE_WREN, OP_WRSR, nw=1, val=val)
        self.wait_wip(what, T_WRSR_LIMIT)

    def unprotect(self, sr0):
        for ops in ENGINE_OPS:
            self.write(*ops)
        for n in range(1, UNPROTECT_TRIES + 1):
            self.wrsr(0x00, f"WRSR unprotect try {n}")
            sr = self.status()
            log(f"status reg now 0x{sr:02x} (try {n})")
            if not sr & SR_PROT:
                return
        raise RuntimeError(
            f"status 0x{sr:02x}: SRWD/BP still set after {UNPROTECT_TRIES} WRSR tries. "
            "SRWD=1 with WP# low locks WRSR (datasheet Table 6); check WP# release (sys 0xFE26 bit0)")

    def wait_wip(self, what, limit):
        t0 = time.monotonic()
        while self.status() & SR_WIP:
            if time.monotonic() - t0 > limit:
                raise TimeoutError(f"{what}: WIP still set after {time.monotonic()-t0:.3f}s (limit {limit}s)")
        log(f"{what} done in {time.monotonic()-t0:.3f}s")

    def read_flash(self, addr, n):
        out = bytearray()
        for a in range(addr, addr + n, 1024):
            self.write(0x60, 0x46); self.write(0x61, 0x03)
            self.write(0x64, (a >> 16) & 0xFF); self.write(0x65, (a >> 8) & 0xFF); self.write(0x66, a & 0xFF)
            self.write(0x60, 0x47)
            self.wait_engine(f"read 0x{a:06x}")
            for _ in range(1024 // 64):
                out += self.read_block(0x70, 64)
        return bytes(out[:n])

    def program_page(self, addr, data):
        assert len(data) == PAGE
        t0 = time.monotonic()
        while self.read(0x6F) & 0x40:                       # previous program still running
            if time.monotonic() - t0 > T_PROG_LIMIT:
                raise TimeoutError(f"reg6F busy before page 0x{addr:06x}")
        self.write(0x71, PAGE - 1)
        self.write(0x64, (addr >> 16) & 0xFF); self.write(0x65, (addr >> 8) & 0xFF); self.write(0x66, addr & 0xFF)
        for i in range(0, PAGE, 32):
            self.write_block(0x70, data[i:i + 32])
        self.write(0x6F, 0xA0)
        t0 = time.monotonic()
        while self.read(0x6F) & 0x40:
            if time.monotonic() - t0 > T_PROG_LIMIT:
                raise TimeoutError(f"page 0x{addr:06x}: program busy after {time.monotonic()-t0:.3f}s (limit {T_PROG_LIMIT}s)")


class FakeRtd(Rtd):
    """Hardware-free model for --selftest: prints every register write, simulates the SPI engine + flash SR."""
    def __init__(self, sr=0x9C, wp_low=True):
        self.regs, self.sr, self.wp_low, self.sys_page, self.sysm = {}, sr, wp_low, 0, {}
        self.regs[0x6F] = 0x80

    def write(self, reg, val):
        print(f"  W 0x{reg:02x} <- 0x{val:02x}")
        self.regs[reg] = val
        if reg == 0xF5 and self.regs.get(0xF4) == 0x9F:
            self.sys_page = val
        elif reg == 0xF5:
            self.sysm[(self.sys_page << 8) | self.regs[0xF4]] = val
            if (self.sys_page << 8 | self.regs[0xF4]) == 0xFE26:
                self.wp_low = not val & 1
        elif reg == 0x60 and val & 1:
            typ, op = val >> 5, self.regs.get(0x61)
            if typ == T_WRITE_WREN and op == OP_WRSR and self.regs.get(0x62) == 0x06 and not self.wp_low:
                self.sr = (self.sr & ~SR_PROT) | (self.regs[0x64] & SR_PROT)
            if typ == T_READ and op == OP_RDSR:
                self.regs[0x67] = self.sr

    def read(self, reg):
        if reg == 0x60:
            return 0
        if reg == 0xF5:
            return self.sysm.get((self.sys_page << 8) | self.regs.get(0xF4, 0), 0)
        return self.regs.get(reg, 0)


def selftest():
    global LOG
    LOG = open(os.devnull, "w")
    for name, kw in (("WP# low, SRWD=1 (monitor as found; fix releases WP# first)", {}),):
        print(f"== {name}")
        f = FakeRtd(**kw)
        f.release_wp(); f.unprotect(0x9C)
        assert not f.sr & SR_PROT, "sim unprotect failed"
        print(f"  -> simulated SR = 0x{f.sr:02x}")
    print("== control: skipping release_wp() must fail")
    f = FakeRtd()
    try:
        f.unprotect(0x9C)
    except RuntimeError as e:
        print("  expected failure:", e)
    else:
        raise SystemExit("selftest: unprotect without WP# release should not succeed")
    print("selftest OK")
    return 0


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int, nargs="?")
    ap.add_argument("sector_addr", type=lambda x: int(x, 0), nargs="?")
    ap.add_argument("file4k", type=Path, nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--expect-current", type=Path)
    ap.add_argument("--backup-dir", type=Path)
    ap.add_argument("--no-reset", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.bus is None or a.sector_addr is None or a.file4k is None:
        ap.error("bus, sector_addr, file4k required")

    root = repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp" / "logs" / "rtd_flash_sector.log").open("a")
    bdir = a.backup_dir or (root / "tmp" / "flash-backups")
    bdir.mkdir(parents=True, exist_ok=True)

    new = a.file4k.read_bytes()
    if len(new) != SECTOR or a.sector_addr % SECTOR:
        log(f"refuse: file must be {SECTOR} B (is {len(new)}) and addr 4 KiB-aligned (0x{a.sector_addr:x})"); return 2
    exp = a.expect_current.read_bytes() if a.expect_current else None
    if exp is not None and len(exp) != SECTOR:
        log("refuse: --expect-current must be 4096 B"); return 2
    mode = "WRITE" if a.write else "DRY-RUN"
    log(f"mode={mode} bus=/dev/i2c-{a.bus} sector=0x{a.sector_addr:06x} file={a.file4k}")

    isp = Rtd(a.bus)
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        log("ISP mode not enabled; aborting"); return 3
    rc = 1
    unprot = False
    try:
        jid = isp.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
        log(f"JEDEC {jid.hex()}")
        if jid != JEDEC_OK:
            log(f"refuse: JEDEC != {JEDEC_OK.hex()}"); return 4
        sr0 = isp.status()
        log(f"status reg = 0x{sr0:02x} (SRWD+BP 0x{sr0 & SR_PROT:02x})")
        cur = isp.read_flash(a.sector_addr, SECTOR)
        bk = bdir / f"sector_{a.sector_addr:06x}_{time.strftime('%Y%m%d-%H%M%S')}.bin"
        with bk.open("wb") as f:
            f.write(cur); f.flush()
        log(f"backup saved: {bk} ({len(cur)} B)")
        nd = sum(x != y for x, y in zip(cur, new))
        log(f"current vs new file: {nd} bytes differ")
        if exp is not None:
            ne = sum(x != y for x, y in zip(cur, exp))
            log(f"current vs --expect-current: {ne} bytes differ")
            if ne and a.write:
                log("refuse: sector is not what --expect-current says; nothing written"); return 5
        if not a.write:
            log("DRY-RUN complete: nothing erased or programmed"); rc = 0; return 0
        if nd == 0:
            log("sector already equals new data; nothing to do"); rc = 0; return 0

        # --- WRITE path ---
        unprot = False
        if sr0 & SR_PROT:
            unprot = True
            isp.release_wp()
            isp.unprotect(sr0)
        log("erasing 4K sector"); isp.common(T_ERASE, OP_ERASE_4K, nw=3, val=a.sector_addr)
        isp.wait_wip("sector erase", T_ERASE_LIMIT)
        blank = isp.read_flash(a.sector_addr, SECTOR)
        if blank != b"\xff" * SECTOR:
            log("ABORT: sector not blank after erase; restore with the backup file"); return 6
        for off in range(0, SECTOR, PAGE):
            pg = new[off:off + PAGE]
            if pg != b"\xff" * PAGE:
                isp.program_page(a.sector_addr + off, pg)
        back = isp.read_flash(a.sector_addr, SECTOR)
        bad = [i for i in range(SECTOR) if back[i] != new[i]]
        if bad:
            log(f"VERIFY FAILED: {len(bad)} bytes differ, first at +0x{bad[0]:03x}. Revert: rerun with {bk} as file4k"); return 7
        log("VERIFY OK: readback == new data"); rc = 0
    finally:
        if unprot:
            try:
                isp.wrsr(sr0 & SR_PROT, "WRSR restore")
                log(f"status reg restored: 0x{isp.status():02x} (wanted 0x{sr0:02x})")
            except Exception as e:
                log(f"WARNING: could not restore status reg 0x{sr0:02x}: {e}")
        if not a.no_reset:
            try:
                isp.write(0xEE, 0x02)    # reset scaler MCU; transfer drop (errno 110) is expected
            except OSError:
                pass
            log("scaler reset sent (0xEE <- 0x02); power-cycle the monitor if it does not come back")
    return rc


if __name__ == "__main__":
    sys.exit(main())
