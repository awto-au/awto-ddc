#!/usr/bin/env python3
"""Native I2C bridge for the Wine comm shim (scripts/rtd_comm_shim/).

usage: rtd_i2c_bridge.py emu  <flash_dump.bin> [--port N]
       rtd_i2c_bridge.py real <bus> [--allow-write] [--port N]

emu : software model of an RTD scaler ISP port (slave 0x4A) backed by an in-memory copy
      of a flash dump. Writes/erases touch only the copy. Every access is logged.
real: forwards to /dev/i2c-<bus>. Writes are BLOCKED unless --allow-write.
Wire format (shim -> bridge): <BBBHH> op(1=read,2=write) dev8 sub nbytes datalen + data;
reply: <BH> status(0 ok, 1 fail) len + data. dev8 = 8-bit address incl. R/W bit.
Protocol/regs: docs/reversing/realtek-rtd/README.md. Log: ./tmp/logs/rtd_i2c_bridge.log
"""
import ctypes, fcntl, os, socket, struct, sys, time
from pathlib import Path

PORT = 17420
JEDEC = bytes([0xC2, 0x20, 0x14])
LOG = None


def log(s: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {s}"
    print(line, flush=True); LOG.write(line + "\n"); LOG.flush()


class Emu:
    def __init__(self, dump: bytes):
        self.flash = bytearray(dump)
        self.regs = bytearray(256)
        self.regs[0x23] = 0x6E   # read from two real units (ISP mode), 2026-11-04; the tool reads this first
        self.regs[0x00] = 0xCF   # ID_REG via direct MCU-subaddress path (tool probes this too)
        self.regs[0x0F] = 0x23
        self.isp = False
        self.fifo = 0
        self.prog = bytearray()
        # Scaler registers read via the F4/F5 indirect window (F4 = index, F5 = data).
        # Seeded from the live RTD2795T unit (ID_REG 0xCF, 0x0F 0x23) so the tool identifies the chip.
        self.scaler = {0x00: 0xCF, 0x0F: 0x23, 0x9F: 0x00, 0x90: 0x00, 0x91: 0x40, 0x93: 0x00, 0x94: 0x80}

    def addr24(self) -> int:
        return (self.regs[0x64] << 16) | (self.regs[0x65] << 8) | self.regs[0x66]

    def read(self, dev8: int, sub: int, n: int) -> bytes | None:
        if dev8 >> 1 != 0x4A:
            log(f"EMU read  dev=0x{dev8>>1:02x} NACK"); return None
        out = bytearray()
        for i in range(n):
            r = sub if sub == 0x70 else (sub + i) & 0xFF
            if r == 0x70:
                out.append(self.flash[self.fifo] if self.fifo < len(self.flash) else 0xFF); self.fifo += 1
            elif r == 0x6F:
                out.append(0x92 if self.isp else 0x00)
            elif r == 0x60:
                out.append(self.regs[0x60] & ~1)
            elif r == 0xF5:
                out.append(self.scaler.get(self.regs[0xF4], 0x00))   # indirect scaler-register read
            else:
                out.append(self.regs[r])
        log(f"EMU read  reg 0x{sub:02x} n={n} -> {bytes(out[:16]).hex()}{'..' if n > 16 else ''}")
        return bytes(out)

    def write(self, dev8: int, sub: int, data: bytes) -> bool:
        if dev8 >> 1 != 0x4A:
            log(f"EMU write dev=0x{dev8>>1:02x} NACK"); return False
        log(f"EMU write reg 0x{sub:02x} {data[:16].hex()}{'..' if len(data) > 16 else ''}")
        for i, v in enumerate(data):
            r = sub if sub == 0x70 else (sub + i) & 0xFF
            if r == 0x70:
                self.prog.append(v)
            elif r == 0x6F:
                if v & 0x80 and not v & 0x20:
                    self.isp = True
                if v == 0xA0:
                    a = self.addr24(); n = self.regs[0x71] + 1
                    for k, b in enumerate(self.prog[:n]):
                        self.flash[a + k] &= b
                    log(f"EMU program 0x{a:06x} {n} B (copy only)"); self.prog.clear()
                if v == 0x84:
                    log("EMU CRC requested (not modelled)"); self.regs[0x6F] |= 2
                self.regs[0x6F] = v
            elif r == 0x60:
                self.regs[0x60] = v
                if v & 1:
                    self.spi(v)
                    self.regs[0x60] &= ~1
            else:
                self.regs[r] = v
        return True

    def spi(self, ctl: int) -> None:
        op = self.regs[0x61]
        typ, nw, nr = (ctl >> 5) & 7, (ctl >> 3) & 3, (ctl >> 1) & 3
        if op == 0x9F:
            self.regs[0x67:0x6A] = JEDEC
        elif op == 0xAB:
            self.regs[0x67] = 0x13
        elif op == 0x05:
            self.regs[0x67] = 0x00
        elif op == 0x03:
            self.fifo = self.addr24()
        elif op in (0xC7, 0x60, 0x20, 0xD8, 0x52):
            a = self.addr24()
            span = len(self.flash) if op in (0xC7, 0x60) else (0x1000 if op == 0x20 else 0x10000)
            a = 0 if op in (0xC7, 0x60) else a
            self.flash[a:a + span] = b"\xff" * span
            log(f"EMU erase op 0x{op:02x} @0x{a:06x} {span} B (copy only)")
        log(f"EMU spi ctl=0x{ctl:02x} type={typ} nw={nw} nr={nr} op=0x{op:02x}")


class Real:
    I2C_RDWR, I2C_M_RD = 0x0707, 1

    class Msg(ctypes.Structure):
        _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                    ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]

    class RdWr(ctypes.Structure):
        _fields_ = [("msgs", ctypes.c_void_p), ("nmsgs", ctypes.c_uint32)]

    def __init__(self, bus: int, allow_write: bool):
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        self.allow_write = allow_write

    def _x(self, msgs):
        arr = (self.Msg * len(msgs))(*msgs)
        fcntl.ioctl(self.fd, self.I2C_RDWR, self.RdWr(ctypes.addressof(arr), len(msgs)))

    def read(self, dev8, sub, n):
        w = ctypes.create_string_buffer(bytes([sub]), 1); r = ctypes.create_string_buffer(n)
        try:
            self._x([self.Msg(dev8 >> 1, 0, 1, ctypes.addressof(w)),
                     self.Msg(dev8 >> 1, self.I2C_M_RD, n, ctypes.addressof(r))])
        except OSError as e:
            log(f"REAL read dev=0x{dev8>>1:02x} reg 0x{sub:02x} FAIL {e}"); return None
        log(f"REAL read dev=0x{dev8>>1:02x} reg 0x{sub:02x} n={n} -> {r.raw[:16].hex()}")
        return r.raw

    def write(self, dev8, sub, data):
        if not self.allow_write:
            log(f"REAL write BLOCKED dev=0x{dev8>>1:02x} reg 0x{sub:02x} {data[:16].hex()}"); return False
        w = ctypes.create_string_buffer(bytes([sub]) + data, 1 + len(data))
        try:
            self._x([self.Msg(dev8 >> 1, 0, 1 + len(data), ctypes.addressof(w))])
        except OSError as e:
            log(f"REAL write FAIL {e}"); return False
        log(f"REAL write dev=0x{dev8>>1:02x} reg 0x{sub:02x} {data[:16].hex()}")
        return True


def recvn(c: socket.socket, n: int) -> bytes:
    b = b""
    while len(b) < n:
        d = c.recv(n - len(b))
        if not d:
            raise ConnectionError
        b += d
    return b


def serve(be, port: int) -> None:
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port)); s.listen(4)
    log(f"listening 127.0.0.1:{port}")
    while True:
        c, _ = s.accept()
        log("shim connected")
        try:
            while True:
                op, dev8, sub, nb, dl = struct.unpack("<BBBHH", recvn(c, 7))
                data = recvn(c, dl) if dl else b""
                if op == 1:
                    r = be.read(dev8, sub, nb)
                    c.sendall(struct.pack("<BH", 0, len(r)) + r if r is not None else struct.pack("<BH", 1, 0))
                else:
                    ok = be.write(dev8, sub, data)
                    c.sendall(struct.pack("<BH", 0 if ok else 1, 0))
        except ConnectionError:
            log("shim disconnected")


def main() -> int:
    global LOG
    root = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp" / "logs" / "rtd_i2c_bridge.log").open("a")
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    if sys.argv[1] == "emu":
        be = Emu(Path(sys.argv[2]).read_bytes())
    else:
        be = Real(int(sys.argv[2]), "--allow-write" in sys.argv)
    serve(be, port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
