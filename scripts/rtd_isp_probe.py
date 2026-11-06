#!/usr/bin/env python3
"""Probe a Realtek RTD scaler's ISP port over DDC (I2C slave 0x4A) via /dev/i2c-N.

usage: rtd_isp_probe.py <bus> [--enter-isp [--dump out.bin [--block N]]]   (dump = SPI READ only; N divides 1024)
  default      : reads only (reg 0x6F, 0x60, 0x67-0x69). No writes.
  --scaler-regs 0x00,0x0f,0x9f : enter ISP, read those scaler registers via ISP F4/F5, then resume (screen may blink)
  --resume     : writes 0x02 to reg 0xEE (resume/reset scaler after ISP; from rtdflash, untested on RTD27xx)
  --enter-isp  : writes 0x80 to reg 0x6F, then reads SPI flash JEDEC ID (op 0x9F).
                 Scaler MCU stops while in ISP mode: power-cycle the monitor after.
Protocol + tags: docs/reversing/realtek-rtd/README.md
Log: ./tmp/logs/rtd_isp_probe.log
"""
import ctypes, fcntl, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto  # noqa: E402  (trace tap: decoded + raw logs, see rtd_proto.setup_logs)

ISP_ADDR = 0x4A
I2C_RDWR = 0x0707
I2C_M_RD = 1
# SPI-engine poll: 3-byte JEDEC at >=1 MHz SPI ~ 30 us; one poll = 2 I2C msgs ~ 0.5 ms
# at 100 kHz, so 1-2 polls expected. 20 polls (~10 ms) = ~10x; on expiry: log + abort.
POLL_MAX = 20


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]


class RdWr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else Path(__file__).resolve().parent.parent


LOG = None


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


class Isp:
    def __init__(self, bus: int):
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)

    def _xfer(self, msgs):
        arr = (Msg * len(msgs))(*msgs)
        d = RdWr(arr, len(msgs))
        fcntl.ioctl(self.fd, I2C_RDWR, d)

    def read(self, reg: int) -> int:
        return self.read_block(reg, 1)[0]

    def read_block(self, reg: int, n: int) -> bytes:
        w = ctypes.create_string_buffer(bytes([reg]), 1)
        r = ctypes.create_string_buffer(n)
        try:
            self._xfer([Msg(ISP_ADDR, 0, 1, ctypes.addressof(w)),
                        Msg(ISP_ADDR, I2C_M_RD, n, ctypes.addressof(r))])
        except OSError as e:
            rtd_proto.trace(ISP_ADDR, "r", reg, None, n, str(e)); raise
        rtd_proto.trace(ISP_ADDR, "r", reg, r.raw, n)
        return r.raw

    def write(self, reg: int, val: int) -> None:
        w = ctypes.create_string_buffer(bytes([reg, val]), 2)
        try:
            self._xfer([Msg(ISP_ADDR, 0, 2, ctypes.addressof(w))])
        except OSError as e:
            rtd_proto.trace(ISP_ADDR, "w", reg, bytes([val]), 0, str(e)); raise
        rtd_proto.trace(ISP_ADDR, "w", reg, bytes([val]))

    def spi_jedec(self) -> bytes:
        self.write(0x60, 0x46)   # type=read, nr=3
        self.write(0x61, 0x9F)   # JEDEC ID opcode
        self.write(0x60, 0x47)   # go
        for _ in range(POLL_MAX):
            if not self.read(0x60) & 1:
                return bytes(self.read(r) for r in (0x67, 0x68, 0x69))
        raise TimeoutError(f"SPI engine busy after {POLL_MAX} polls of reg 0x60")


def dump(isp: "Isp", size: int, out: Path, block: int = 64) -> None:
    # Bench 2026-11-04 (scripts/i2c_bench.py), Intel DP AUX bus: 2.75 KB/s @128 B -> ~380 s/MiB
    # worst case used here. Backstop 3x = 1200 s; on expiry: TimeoutError with address reached.
    limit, t0 = 1200.0, time.time()
    with out.open("wb") as f:
        for addr in range(0, size, 1024):
            isp.write(0x60, 0x46); isp.write(0x61, 0x03)           # READ opcode
            isp.write(0x64, (addr >> 16) & 0xFF); isp.write(0x65, (addr >> 8) & 0xFF)
            isp.write(0x66, addr & 0xFF)
            isp.write(0x60, 0x47)
            for _ in range(POLL_MAX):
                if not isp.read(0x60) & 1:
                    break
            else:
                raise TimeoutError(f"SPI busy at 0x{addr:06x}")
            for _ in range(1024 // block):
                f.write(isp.read_block(0x70, block))
            if time.time() - t0 > limit:
                raise TimeoutError(f"dump exceeded {limit}s at 0x{addr:06x}")
    log(f"dumped {size} bytes to {out} in {time.time()-t0:.1f}s")


def main() -> int:
    global LOG
    logdir = repo_root() / "tmp" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    LOG = rtd_proto.setup_logs("rtd_isp_probe").main
    bus = int(sys.argv[1])
    enter = "--enter-isp" in sys.argv
    isp = Isp(bus)
    log(f"bus=/dev/i2c-{bus} addr=0x{ISP_ADDR:02x} enter_isp={enter}")
    for reg in (0x6F, 0x60, 0x67, 0x68, 0x69):
        log(f"read reg 0x{reg:02x} = 0x{isp.read(reg):02x}")
    if "--scaler-regs" in sys.argv:
        # naorunaoru/rtdflash: with the MCU stopped, ISP:F4 <- reg then read ISP:F5 gives scaler register `reg`
        # in the page selected by scaler reg 0x9F. Reads only (F4 is just an index); monitor is resumed after.
        regs = [int(x, 0) for x in sys.argv[sys.argv.index("--scaler-regs") + 1].split(",")]
        isp.write(0x6F, 0x80)
        if not isp.read(0x6F) & 0x80:
            log("ISP mode not enabled; aborting"); return 3
        try:
            for r in regs:
                isp.write(0xF4, r)
                log(f"scaler reg 0x{r:02x} = 0x{isp.read(0xF5):02x}")
        finally:
            try:
                isp.write(0xEE, 0x02)
            except OSError:
                pass   # expected: the scaler resets and drops the transfer
            log("resumed scaler MCU (0xEE <- 0x02)")
        return 0
    if "--resume" in sys.argv:
        try:
            isp.write(0xEE, 0x02)   # naorunaoru/rtdflash: ISP:EE <- 02 resets the scaler MCU (monitor reboots)
        except OSError:
            pass   # expected: the scaler resets mid-transfer (errno 110)
        log("wrote 0x02 to reg 0xEE (reset scaler MCU; monitor reboots)")
        return 0
    if not enter:
        log("read-only phase done; no writes sent")
        return 0
    isp.write(0x6F, 0x80)
    v = isp.read(0x6F)
    log(f"after write 0x6F=0x80, read 0x6F = 0x{v:02x} (bit7 {'set' if v & 0x80 else 'CLEAR'})")
    if not v & 0x80:
        log("ISP mode not enabled; aborting"); return 3
    jid = isp.spi_jedec()
    log(f"JEDEC ID = {jid.hex()}  (mfr 0x{jid[0]:02x}, type 0x{jid[1]:02x}, cap 0x{jid[2]:02x})")
    if "--dump" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--dump") + 1])
        block = int(sys.argv[sys.argv.index("--block") + 1]) if "--block" in sys.argv else 64
        dump(isp, 1 << jid[2], out, block)
    log("monitor left in ISP mode: power-cycle it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
