#!/usr/bin/env python3
"""Erase + reprogram ONE 4 KiB sector of a Realtek RTD scaler's SPI flash over DDC ISP (I2C 0x4A).

usage: rtd_flash_sector.py <bus> <sector_addr> <file4k> [--write] [--expect-current FILE]
                           [--backup-dir DIR] [--no-reset] [--reprotect VALUE|none]
       rtd_flash_sector.py <bus> --read-id          (alias --read-uid)
       rtd_flash_sector.py --selftest
  default (no --write) = DRY RUN: enter ISP, read JEDEC + status, read the sector, save a timestamped
                         backup, compare current vs <file4k> (and vs --expect-current). No erase, no program,
                         no status-register write, no SPI-engine config writes.
  --read-id            : READ ONLY. Enter ISP, print JEDEC (0x9F) + RDUID (0x4B, not on MX25L8006E) +
                         the Macronix 128-bit secured-OTP ESN (unique per chip; ENSO 0xB1 -> READ -> EXSO
                         0xC1), reset the scaler. No erase/program. read_uid() is the shared implementation;
                         the UID-derived EDID serial path calls it too.
  --write              : the only way to modify flash. Requires JEDEC C2 20 14, 4 KiB-aligned addr, exactly
                         4096-byte file, and (if --expect-current given) current sector == that file.
  --expect-current F   : abort unless the sector currently equals F (guards against overwriting unknown data).
Sequence (--write): backup -> (if protected) release flash WP# (scaler GPIO: sys 0x1036/0xFE26) + WRSR=0x00
  -> engine program opcode setup (0x6D=0x02, 0x71=0xFF, 0x66=0x00) -> standalone WREN -> sector erase (op 0x20)
  -> blank check -> program 16 x 256 B pages (op 0x02) -> read back + compare -> "VERIFY OK" ->
  RE-PROTECT (see below) -> reset.
  --reprotect VALUE    : (default 0x9C = factory SRWD|BP2..0 on Macronix C2 20 14; 'none' = skip) After VERIFY OK
                         ONLY: WP# released (if not already) -> WREN+WRSR(VALUE) via the same engine path as unprotect
                         -> RDSR must equal VALUE (masked 0x9C) -> WP# GPIO restored to its pre-release values
                         (asserted, as factory). Runs even if the sector started unprotected. On ANY earlier failure
                         re-protect is NOT attempted (no locking of a bad image). WRSR happens while WP# is released
                         because SRWD=1 + WP# low locks the SR; WP# is re-asserted only afterwards.
  --selftest : no hardware; prints the register writes the unprotect + program would do (simulated chip).
PROGRAM PATH — faithfully transcribed from naorunaoru/rtdflash flash_write_sector() (RTD2795-family, same
  DP-AUX ISP slave 0x4A and WP# release as this unit), cross-checked against ghent360/RTD-2660-Programmer
  ProgramFlash(). Clean-room: from the published algorithm.
  Per sector (rtdflash flash_write_sector, rtdflash-macos/rtdflash.c):
    WREN:  60<-70, 61<-01, 64<-06, 65<-00, 60<-71, poll 60.0==0   (standalone write-enable before erase)
    ERASE: 64<-A23:16, 65<-A15:8, 66<-00, 60<-B8, 61<-20, 60<-B9, poll 60.0==0   (4K sector erase, op 0x20)
    SETUP: 6D<-02 (program opcode), 71<-FF (program size-1 = 255), 66<-00   (ONCE, before the page loop)
    Per 256 B page (flash_program_page_prepared): 64<-A23:16, 65<-A15:8; poll 6F.4==1 (buffer ready);
      write 256 B to 0x70; 6F |= 0x20 (start program); poll 6F.5==0 (done).  Engine supplies per-page WREN.
  WHY OUR PRIOR CODE WROTE NOTHING: it used the RTD2660 program kick (6F<-0xA0, poll 6F bit6) and skipped the
    6F.4 buffer-ready gate. This engine kicks on 6F bit5 (0x20) and gates loads on 6F bit4 (0x10). See issue.
Why WRSR failed before: SRWD=1 + WP# low = hardware protect, WRSR ignored; WP# is a scaler GPIO that must be
  released first. docs/flash-unprotect.md.
Revert: run again with the backup file as <file4k> (and --expect-current <file4k of the new data>).
Protocol: docs/reversing/realtek-rtd/README.md; SPI-engine common cmd after ghent360 main.cpp
  (reg 0x60 = type<<5 | nw<<3 | nr<<1 | go; types READ=2 WRITE_AFTER_WREN=3 ERASE=5).
Monitor MCU is stopped while in ISP; the final 0xEE=0x02 resets the scaler (as rtd_isp_probe --resume).
Log: ./tmp/logs/rtd_flash_sector.log
"""
import argparse, ctypes, fcntl, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_isp_probe import Isp, Msg, ISP_ADDR, repo_root  # noqa: E402

SECTOR = 4096
PAGE = 256
JEDEC_OK = bytes.fromhex("c22014")      # Macronix 1 MiB, seen on all dumped units (docs/monitors/README.md)
T_READ, T_WRITE_WREN, T_ERASE = 2, 3, 5
OP_ERASE_4K, OP_RDSR, OP_WRSR, OP_WREN, OP_PROG = 0x20, 0x05, 0x01, 0x06, 0x02
SR_WIP, SR_WEL = 0x01, 0x02
SR_PROT = 0x9C                          # SRWD | BP2 | BP1 | BP0 (MX25L8006E Table 5); bits 6,5 reserved
# reg 0x6F program-engine bits (rtdflash flash_program_page_prepared): bit4 (0x10) page buffer ready,
# bit5 (0x20) set to start a page program, cleared by the engine when the page is written.
PROG_BUF_RDY, PROG_BUSY = 0x10, 0x20
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
# Poll granularity (~5-10 ms per I2C poll) means the page limit is only checked between polls, so the
# program/buffer-ready limits are floored at a few poll periods (never fire on a healthy page, only on hang).
# On expiry: abort, log op + elapsed.
T_WRSR_LIMIT, T_ERASE_LIMIT = 0.05, 0.25
T_PROG_LIMIT = 0.05        # tPP 3 ms x1.25 = 3.75 ms is below one I2C poll (~5-10 ms); floor at ~5 polls
T_BUFRDY_LIMIT = 0.05      # page buffer ready should be immediate; same floor, fires only on a stuck engine

LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    LOG.write(line + "\n"); LOG.flush()


I2C_RETRIES = 0x0701        # linux/i2c-dev.h: set adapter retry count (adapter-wide, not per fd)
I2C_RETRIES_DEFAULT = 1     # i915 gmbus sets adapter.retries = 1 (intel_gmbus.c); restored after each page


class Rtd(Isp):
    def set_retries(self, n):
        fcntl.ioctl(self.fd, I2C_RETRIES, n)

    def write_block(self, reg, data):
        # One message. Splitting select + data (to dodge i915 "NAK on first message, retry") did not stop the
        # duplicated-chunk failures (#12); don't repeat the reg byte after a repeated start: it lands in the FIFO.
        w = ctypes.create_string_buffer(bytes([reg]) + bytes(data), 1 + len(data))
        self._xfer([Msg(ISP_ADDR, 0, 1 + len(data), ctypes.addressof(w))])

    def wait_engine(self, what, limit=0.3):
        # Engine clears reg0x60 bit0 when the SPI transaction completes. Erase (op 0x20) can take up to
        # ~200ms (MX25L8006E tSE) so this must be TIME-based, not a fixed poll count. limit = 1.25x tSE.
        t0 = time.monotonic()
        while self.read(0x60) & 1:
            if time.monotonic() - t0 > limit:
                raise TimeoutError(f"SPI engine busy after {time.monotonic()-t0:.3f}s ({what}), reg60=0x{self.read(0x60):02x}")
        return

    def poll_reg(self, reg, mask, expected, what, limit):
        # Poll `reg` until (value & mask) == (expected & mask). Time-based; on expiry log reg + elapsed.
        # rtdflash scaler_mcu_poll equivalent (used for the 0x6F program-engine handshake).
        t0 = time.monotonic()
        while True:
            v = self.read(reg)
            if (v & mask) == (expected & mask):
                return v
            if time.monotonic() - t0 > limit:
                raise TimeoutError(
                    f"{what}: reg 0x{reg:02x} mask 0x{mask:02x} != 0x{expected:02x} "
                    f"after {time.monotonic()-t0:.3f}s (last 0x{v:02x}, limit {limit}s)")

    def common(self, typ, op, nr=0, nw=0, val=0, limit=0.3):
        v = (typ << 5) | ((nw & 3) << 3) | ((nr & 3) << 1)
        self.write(0x60, v); self.write(0x61, op)
        for i, r in enumerate((0x64, 0x65, 0x66)[:nw]):
            self.write(r, (val >> (8 * (nw - 1 - i))) & 0xFF)
        self.write(0x60, v | 1)
        self.wait_engine(f"op 0x{op:02x}", limit)
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

    wp_saved = None        # {sys addr: original value} while WP# is released; None = asserted/untouched

    def release_wp(self):
        if self.wp_saved is None:
            self.wp_saved = {}
        for addr, and_mask, or_val in WP_RELEASE:
            cur = self.sys_read(addr)
            self.wp_saved.setdefault(addr, cur)
            v = (cur & and_mask) | or_val
            self.sys_write(addr, v)
            got = self.sys_read(addr)
            log(f"WP# release: sys[0x{addr:04x}] <- 0x{v:02x}, readback 0x{got:02x}")
            if got != v:
                raise RuntimeError(f"sys[0x{addr:04x}] readback 0x{got:02x} != 0x{v:02x}; WP# GPIO not released")

    def assert_wp(self):
        # Put the WP# GPIO regs back to their pre-release values (factory: asserted). No-op if never released.
        if self.wp_saved is None:
            return
        for addr, orig in reversed(list(self.wp_saved.items())):
            self.sys_write(addr, orig)
            log(f"WP# restore: sys[0x{addr:04x}] <- 0x{orig:02x}, readback 0x{self.sys_read(addr):02x}")
        self.wp_saved = None

    def reprotect(self, value):
        """WREN+WRSR(value) with WP# released, verify RDSR, then re-assert WP#. Raises on mismatch."""
        for ops in ENGINE_OPS:
            self.write(*ops)
        if self.wp_saved is None:
            self.release_wp()
        try:
            self.wrsr(value, f"WRSR reprotect 0x{value:02x}")
            sr = self.status()
            log(f"status reg after reprotect = 0x{sr:02x} (wanted 0x{value:02x})")
            if sr & SR_PROT != value & SR_PROT:
                raise RuntimeError(f"reprotect: status 0x{sr:02x} != wanted 0x{value:02x}")
        finally:
            self.assert_wp()
        sr = self.status()
        log(f"status reg after WP# re-assert = 0x{sr:02x}")
        if sr & SR_PROT != value & SR_PROT:
            raise RuntimeError(f"reprotect: status 0x{sr:02x} != wanted 0x{value:02x} after WP# re-assert")

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

    def cmd(self, op, limit=0.3):
        # Bare opcode, no address/data (ENSO/EXSO). Engine WRITE type, nw=0: 60<-type, 61<-op, 60<-type|1.
        self.common(T_WRITE_WREN, op, nr=0, nw=0, limit=limit)

    def read_uid(self):
        """Read flash identity: JEDEC (0x9F), attempt RDUID 0x4B, and the Macronix 128-bit secured-OTP ESN.
        Returns dict {jedec, rduid, esn, uid}. READ ONLY. `uid` = the chosen per-unit fingerprint hex
        (ESN if it looks programmed, else RDUID, else None). No erase/program.
        - MX25L8006E has NO 0x4B opcode; 0x4B is attempted anyway (reported) then ESN is the real UID.
        - ESN = first 16 B of the 512-bit secured OTP (datasheet Table 3, addr xxxx00-xxxx0F), reached via
          ENSO(0xB1) -> READ(0x03)@0 -> EXSO(0xC1). docs/reversing/realtek-rtd/README.md (RE section)."""
        jedec = self.common(T_READ, 0x9F, nr=3).to_bytes(3, "big")
        # 0x4B RDUID: not on this part; the engine 0x67-0x69 path gives at most 3 bytes. Report what comes back.
        try:
            rduid = self.common(T_READ, 0x4B, nr=3).to_bytes(3, "big")
        except Exception as e:
            rduid = None
            log(f"RDUID 0x4B: no response ({e})")
        # Secured-OTP ESN via ENSO -> READ@0 (16 B) -> EXSO. Array access is blocked while in OTP mode,
        # so EXSO must always run (finally) before any other flash use.
        self.cmd(0xB1)                                   # ENSO
        try:
            esn = bytearray()
            self.write(0x60, 0x46); self.write(0x61, 0x03)
            self.write(0x64, 0); self.write(0x65, 0); self.write(0x66, 0)
            self.write(0x60, 0x47)
            self.wait_engine("ESN read")
            esn += self.read_block(0x70, 16)
            esn = bytes(esn)
        finally:
            self.cmd(0xC1)                               # EXSO (restore normal array access)
        # Pick the fingerprint: ESN if programmed (not all-00 / all-FF), else RDUID if usable, else None.
        esn_blank = esn in (b"\x00" * 16, b"\xff" * 16)
        uid = None
        if not esn_blank:
            uid = esn.hex()
        elif rduid and rduid not in (b"\x00\x00\x00", b"\xff\xff\xff"):
            uid = rduid.hex()
        log(f"JEDEC {jedec.hex()}  RDUID {rduid.hex() if rduid else 'none'}  "
            f"ESN {esn.hex()}{' (blank)' if esn_blank else ''}  UID {uid or 'none'}")
        return {"jedec": jedec, "rduid": rduid, "esn": esn, "uid": uid, "esn_blank": esn_blank}

    def write_enable(self):
        # Standalone WREN via the raw engine, before sector erase. rtdflash flash_write_enable_p25q80h_prepared:
        #   60<-0x70, 61<-0x01, 64<-WREN(0x06), 65<-0x00, 60<-0x71, poll 60.0==0.
        # (0x70 = engine "write, 1 write byte" setup; 0x71 = same | execute. Equivalent to common(WRITE,...,nw=1)
        #  but transcribed as the literal rtdflash register writes since that is the proven sequence.)
        self.write(0x60, 0x70); self.write(0x61, 0x01)
        self.write(0x64, OP_WREN); self.write(0x65, 0x00)
        self.write(0x60, 0x71)
        self.wait_engine("WREN", T_WRSR_LIMIT)

    def erase_sector(self, addr):
        # rtdflash flash_erase_sector_prepared: 64<-A23:16, 65<-A15:8, 66<-00, 60<-B8, 61<-ERASE(0x20), 60<-B9,
        # poll 60.0==0. (0xB8 = engine erase setup with 3 addr bytes staged; 0xB9 = | execute.)
        self.write(0x64, (addr >> 16) & 0xFF); self.write(0x65, (addr >> 8) & 0xFF); self.write(0x66, addr & 0xFF)
        self.write(0x60, 0xB8); self.write(0x61, OP_ERASE_4K); self.write(0x60, 0xB9)
        self.wait_engine(f"erase 0x{addr:06x}", T_ERASE_LIMIT)

    def program_setup(self):
        # ONCE before the page loop (rtdflash flash_write_sector): program opcode, program size-1, low addr byte.
        self.write(0x6D, OP_PROG); self.write(0x71, PAGE - 1); self.write(0x66, 0x00)

    def program_page(self, addr, data):
        # rtdflash flash_program_page_prepared: stage high addr bytes, wait buffer ready (6F.4==1),
        # write 256 B to 0x70, start (6F |= 0x20), wait done (6F.5==0). Engine issues its own per-page WREN.
        assert len(data) == PAGE
        self.write(0x64, (addr >> 16) & 0xFF); self.write(0x65, (addr >> 8) & 0xFF)
        self.poll_reg(0x6F, PROG_BUF_RDY, PROG_BUF_RDY, f"page 0x{addr:06x} buffer-ready", T_BUFRDY_LIMIT)
        # 0x70 is a FIFO: a resent chunk duplicates bytes (#12). Block the i2c-core resend on GMBUS timeout
        # (-EAGAIN, adapter retries = 1); other resends still happen -> caller verifies and redoes the sector.
        self.set_retries(0)
        try:
            for i in range(0, PAGE, 64):                     # 64 B chunks: matches read_block granularity
                self.write_block(0x70, data[i:i + 64])
        except OSError as e:
            raise RuntimeError(f"page 0x{addr:06x} buffer write failed at chunk +0x{i:02x}: {e}") from e
        finally:
            self.set_retries(I2C_RETRIES_DEFAULT)
        v = self.read(0x6F)
        self.write(0x6F, (v & 0xFF) | PROG_BUSY)             # update_bits(0x6F, 0xFF, 0x20): set start bit
        self.poll_reg(0x6F, PROG_BUSY, 0x00, f"page 0x{addr:06x} program", T_PROG_LIMIT)


def do_write(isp, addr, new, sr0, reprotect, nd, bk):
    """Unprotect (if started protected) -> erase -> program -> verify -> re-protect. Returns rc.
    Re-protect runs ONLY after a passing verify (or when the sector already equals the new data)."""
    if nd == 0:
        log("sector already equals new data; skipping erase/program")
    else:
        if sr0 & SR_PROT:
            isp.release_wp()
            isp.unprotect(sr0)
        else:
            log("status already unprotected (SRWD+BP = 0); skipping WP# release + WRSR")
        for ops in ENGINE_OPS:                               # WREN/EWSR/READ/FAST_READ/PP/RDSR opcodes
            isp.write(*ops)
        isp.write_enable()
        log("WREN issued; erasing 4K sector"); isp.erase_sector(addr)
        isp.wait_wip("sector erase", T_ERASE_LIMIT)
        blank = isp.read_flash(addr, SECTOR)
        if blank != b"\xff" * SECTOR:
            log("ABORT: sector not blank after erase; restore with the backup file"); return 6
        isp.program_setup()
        prog_pages = 0
        for off in range(0, SECTOR, PAGE):
            pg = new[off:off + PAGE]
            if pg != b"\xff" * PAGE:
                isp.program_page(addr + off, pg); prog_pages += 1
        log(f"programmed {prog_pages} non-blank pages")
        back = isp.read_flash(addr, SECTOR)
        bad = [i for i in range(SECTOR) if back[i] != new[i]]
        if bad:
            log(f"VERIFY FAILED: {len(bad)} bytes differ, first at +0x{bad[0]:03x}. NOT re-protecting. Revert: rerun with {bk} as file4k"); return 7
        log("VERIFY OK: readback == new data")
    if reprotect is None:
        log("--reprotect none: leaving status reg as is"); return 0
    try:
        isp.reprotect(reprotect)
    except Exception as e:
        log(f"ERROR: re-protect to 0x{reprotect:02x} failed: {e}"); return 8
    return 0


class FakeRtd(Rtd):
    """Hardware-free model for --selftest: simulates the SPI engine, flash SR, WREN latch, a 4 KiB flash
    array, erase and the 0x6F page-program handshake, so the new program path is exercised offline."""
    def __init__(self, sr=0x9C, wp_low=True, base=0x13000, verbose=False):
        self.regs, self.sr, self.wp_low, self.sys_page, self.sysm = {}, sr, wp_low, 0, {}
        self.verbose = verbose
        self.base = base
        self.flash = bytearray(b"\xff" * SECTOR)   # one simulated sector starting at `base`
        self.wel = False                           # write-enable latch (WREN sets, any write clears)
        self.programmed = False
        self.bad_verify = False                    # corrupt read-back after programming (selftest)
        self.pend = None                           # staged page buffer: (addr, bytearray)
        self.regs[0x6F] = 0x80                      # ISP mode bit set, program bits clear

    def _faddr(self):
        return (self.regs.get(0x64, 0) << 16) | (self.regs.get(0x65, 0) << 8) | self.regs.get(0x66, 0)

    def write(self, reg, val):
        if self.verbose:
            print(f"  W 0x{reg:02x} <- 0x{val:02x}")
        if reg == 0x70:                             # page-buffer data byte load
            if self.pend is not None:
                self.pend[1].append(val & 0xFF)
            return
        self.regs[reg] = val
        if reg == 0xF5 and self.regs.get(0xF4) == 0x9F:
            self.sys_page = val
        elif reg == 0xF5:
            self.sysm[(self.sys_page << 8) | self.regs[0xF4]] = val
            if (self.sys_page << 8 | self.regs[0xF4]) == 0xFE26:
                self.wp_low = not val & 1
        elif reg == 0x65 and self.regs.get(0x6D) == OP_PROG:
            # Both high addr bytes staged for a page program -> arm a fresh page buffer (rtdflash writes
            # 0x64 then 0x65 per page; 0x66 low byte stays 0 from program_setup).
            self.pend = (self._faddr() & ~(PAGE - 1), bytearray())
        elif reg == 0x60 and val & 1:
            self._exec_engine(val >> 5, self.regs.get(0x61), (val >> 3) & 3)
        elif reg == 0x6F:
            if val & PROG_BUSY:                     # start page program
                self._program(val)

    def set_retries(self, n):
        pass

    def write_block(self, reg, data):
        for b in data:
            self.write(reg, b)

    def _exec_engine(self, typ, op, nw):
        # Distinguish by write-byte count: write_enable() frames 2 write bytes (0x60<-0x71, 64<-06,65<-00)
        # and leaves WEL set for the following erase; WRSR via common() frames 1 write byte (0x60<-0x69).
        if typ == T_WRITE_WREN and nw == 2 and self.regs.get(0x64) == OP_WREN:
            self.wel = True
        if typ == T_WRITE_WREN and nw == 1 and op == OP_WRSR and self.regs.get(0x62) == 0x06 and not (self.wp_low and self.sr & 0x80):
            self.sr = (self.sr & ~SR_PROT) | (self.regs[0x64] & SR_PROT)
        if typ == T_READ and op == OP_RDSR:
            self.regs[0x67] = self.sr
        if typ == T_ERASE and op == OP_ERASE_4K:
            if not self.wel:
                raise SystemExit("selftest: erase attempted without WREN (write-enable latch clear)")
            a = self._faddr() - self.base
            if 0 <= a < SECTOR:
                self.flash[a:a + SECTOR] = b"\xff" * SECTOR
            self.wel = False
        if typ == T_READ and op == 0x9F:
            self.regs[0x67], self.regs[0x68], self.regs[0x69] = JEDEC_OK

    def _program(self, kick):
        if self.pend is None:
            raise SystemExit("selftest: program started with no staged page (6F.4 buffer-ready not honoured)")
        addr, buf = self.pend
        if len(buf) != PAGE:
            raise SystemExit(f"selftest: staged {len(buf)} bytes, expected {PAGE} (data load wrong)")
        a = addr - self.base
        for i in range(PAGE):                       # NOR: program only clears bits (AND)
            self.flash[a + i] &= buf[i]
        self.pend = None
        self.programmed = True

    def read(self, reg):
        if reg == 0x60:
            return 0                                # engine always idle in the model
        if reg == 0xF5:
            return self.sysm.get((self.sys_page << 8) | self.regs.get(0xF4, 0), 0)
        if reg == 0x6F:
            # Page buffer is always ready in the model; program-busy bit always reads clear (engine idle).
            return (self.regs.get(0x6F, 0) & ~PROG_BUSY) | PROG_BUF_RDY
        if reg == 0x70:
            return 0
        return self.regs.get(reg, 0)

    def read_flash(self, addr, n):
        a = addr - self.base
        out = bytearray(self.flash[a:a + n])
        if self.bad_verify and self.programmed:
            out[0] ^= 0xFF
        return bytes(out)


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

    print("== program path: WREN -> erase -> page program must land the data")
    f = FakeRtd(sr=0x00, wp_low=False, base=0x13000)
    f.flash[:] = os.urandom(SECTOR)                 # start dirty, prove erase+program clears to new data
    for ops in ENGINE_OPS:
        f.write(*ops)
    f.write_enable()
    assert f.wel, "selftest: WREN did not set the write-enable latch"
    f.erase_sector(0x13000)
    assert f.read_flash(0x13000, SECTOR) == b"\xff" * SECTOR, "selftest: erase did not blank the sector"
    new = bytearray(os.urandom(SECTOR))
    new[0x100:0x200] = b"\xff" * PAGE               # one fully-blank page: must be skipped, stays 0xFF
    f.program_setup()
    for off in range(0, SECTOR, PAGE):
        pg = bytes(new[off:off + PAGE])
        if pg != b"\xff" * PAGE:
            f.program_page(0x13000 + off, pg)
    back = f.read_flash(0x13000, SECTOR)
    bad = [i for i in range(SECTOR) if back[i] != new[i]]
    if bad:
        raise SystemExit(f"selftest: program readback {len(bad)} mismatches, first +0x{bad[0]:03x}")
    print(f"  -> program readback: 0 mismatches over {SECTOR} bytes (1 blank page skipped)")

    print("== control: program without a staged buffer must fail")
    f2 = FakeRtd(sr=0x00, wp_low=False)
    try:
        f2.write(0x6F, (f2.read(0x6F) & 0xFF) | PROG_BUSY)   # kick with no page staged... but read armed it
        f2.pend = None
        f2._program(PROG_BUSY)
    except SystemExit as e:
        print("  expected failure:", e)
    else:
        raise SystemExit("selftest: program with no staged buffer should not succeed")
    print("== full write + re-protect (do_write) from three starting states")
    new = bytearray(os.urandom(SECTOR))
    for name, sr0, bad in (("start SR 0x00 (unprotected)", 0x00, False), ("start SR 0x9C (protected)", 0x9C, False),
                           ("forced verify failure from 0x00", 0x00, True)):
        f = FakeRtd(sr=sr0, wp_low=True, base=0x13000)
        f.flash[:] = os.urandom(SECTOR)
        f.bad_verify = bad
        rc = do_write(f, 0x13000, bytes(new), sr0, 0x9C, 1, "bk")
        print(f"  {name}: rc={rc} final SR=0x{f.sr:02x} wp_low={f.wp_low}")
        if bad:
            assert rc == 7 and f.sr == sr0, "failed verify must error and leave protection untouched"
        else:
            assert rc == 0 and f.sr == 0x9C and f.wp_low, "success must end SR=0x9C with WP# re-asserted"
            assert bytes(f.flash) == bytes(new)
    f = FakeRtd(sr=0x00, wp_low=True)
    assert do_write(f, 0x13000, bytes(f.flash), 0x00, None, 0, "bk") == 0 and f.sr == 0x00, "--reprotect none must not touch SR"
    print("selftest OK")
    return 0


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int, nargs="?")
    ap.add_argument("sector_addr", type=lambda x: int(x, 0), nargs="?")
    ap.add_argument("file4k", type=Path, nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--read-id", "--read-uid", dest="read_id", action="store_true",
                    help="READ-ONLY: enter ISP, print JEDEC + RDUID(0x4B) + Macronix secured-OTP ESN (UID), reset; no erase/program")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--expect-current", type=Path)
    ap.add_argument("--backup-dir", type=Path)
    ap.add_argument("--no-reset", action="store_true")
    ap.add_argument("--reprotect", default="0x9C", help="SR value to leave after VERIFY OK (default 0x9C factory); 'none' skips")
    a = ap.parse_args()
    a.reprotect = None if a.reprotect.lower() == "none" else int(a.reprotect, 0)
    if a.selftest:
        return selftest()

    root = repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp" / "logs" / "rtd_flash_sector.log").open("a")

    if a.read_id:
        if a.bus is None:
            ap.error("bus required for --read-id")
        log(f"mode=READ-ID bus=/dev/i2c-{a.bus}")
        isp = Rtd(a.bus)
        isp.write(0x6F, 0x80)
        if not isp.read(0x6F) & 0x80:
            log("ISP mode not enabled; aborting"); return 3
        try:
            info = isp.read_uid()
        finally:
            if not a.no_reset:
                try:
                    isp.write(0xEE, 0x02)
                except OSError:
                    pass
                log("scaler reset sent (0xEE <- 0x02)")
        print(f"JEDEC={info['jedec'].hex()} "
              f"RDUID={info['rduid'].hex() if info['rduid'] else 'none'} "
              f"ESN={info['esn'].hex()} UID={info['uid'] or 'none'}")
        return 0

    if a.bus is None or a.sector_addr is None or a.file4k is None:
        ap.error("bus, sector_addr, file4k required")

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

        rc = do_write(isp, a.sector_addr, new, sr0, a.reprotect, nd, bk)
    finally:
        if not a.no_reset:
            try:
                isp.write(0xEE, 0x02)    # reset scaler MCU; transfer drop (errno 110) is expected
            except OSError:
                pass
            log("scaler reset sent (0xEE <- 0x02); power-cycle the monitor if it does not come back")
    return rc


if __name__ == "__main__":
    sys.exit(main())
