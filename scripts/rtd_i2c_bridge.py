#!/usr/bin/env python3
"""Native I2C bridge for the Wine comm shim (scripts/rtd_comm_shim/).

usage: rtd_i2c_bridge.py emu  <flash_dump.bin> [--port N]
       rtd_i2c_bridge.py real <bus> [--allow-write | --regread] [--port N]

emu : software model of an RTD scaler ISP port (slave 0x4A) backed by an in-memory copy
      of a flash dump. Writes/erases touch only the copy. Every access is logged.
real: forwards to /dev/i2c-<bus>. Writes are BLOCKED unless --allow-write.
      --regread: allow only register-select/read writes: ISP 0xF4/0xF5(page) and debug-slave 0x35 read
                 commands + page select (see Real.regread_ok). All other writes stay blocked.
Wire format (shim -> bridge): <BBBHH> op(1=read,2=write) dev8 sub nbytes datalen + data;
reply: <BH> status(0 ok, 1 fail) len + data. dev8 = 8-bit address incl. R/W bit.
Protocol/regs: docs/reversing/realtek-rtd/README.md.
Logs: ./tmp/logs/rtd_i2c_bridge.log (decoded by rtd_proto.py), ./tmp/logs/rtd_i2c_bridge.raw.log (byte trace).
Tools using Real get the same split with `B.setup_logs("<tool>", map=None)` (= rtd_proto.setup_logs).
"""
import socket, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto  # noqa: E402
import i2cbus  # noqa: E402
from rtd_proto import setup_logs  # noqa: E402,F401  (re-export: B.setup_logs)

PORT = 17420
JEDEC = bytes([0xC2, 0x20, 0x14])
LOG = None
RAW = None


def log(s: str) -> None:
    line = f"{rtd_proto.now()} {s}"
    print(line, flush=True); LOG.write(line + "\n"); LOG.flush()


def raw(s: str) -> None:
    """Per-access trace line of the Emu model -> raw log when set up (rtd_proto taps carry the Real traffic)."""
    if RAW:
        RAW.write(f"{rtd_proto.now()} {s}\n")
    else:
        log(s)


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
            raw(f"EMU read  dev=0x{dev8>>1:02x} NACK"); return None
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
        raw(f"EMU read  reg 0x{sub:02x} n={n} -> {bytes(out[:16]).hex()}{'..' if n > 16 else ''}")
        rtd_proto.trace(0x4A, "r", sub, bytes(out), n)
        return bytes(out)

    def write(self, dev8: int, sub: int, data: bytes) -> bool:
        if dev8 >> 1 != 0x4A:
            raw(f"EMU write dev=0x{dev8>>1:02x} NACK"); return False
        raw(f"EMU write reg 0x{sub:02x} {data[:16].hex()}{'..' if len(data) > 16 else ''}")
        rtd_proto.trace(0x4A, "w", sub, data)
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
        raw(f"EMU spi ctl=0x{ctl:02x} type={typ} nw={nw} nr={nr} op=0x{op:02x}")


class Real:
    def __init__(self, bus: int, allow_write: bool, regread: bool = False):
        self.bus = i2cbus.Bus(bus)
        self.allow_write = allow_write
        self.regread = regread
        self.f4 = None          # last scaler index written to ISP 0xF4

    # Firmware debug slave 0x35 (SDK ScalerCommonDebug.c ScalerDebug): first byte = command.
    DBG_READ = {0x80, 0x41, 0x44, 0x45, 0x3A, 0x3C, 0xBB, 0x55, 0x20, 0x25, 0x2A, 0x2F}   # run ctl, reads, msg
    DBG_STAGE = {0x1, 0x2, 0x3, 0x5, 0x6}       # low nibble: parameter staging only

    def regread_ok(self, dev8, sub, data) -> bool:
        """--regread: only writes that select/read registers. ISP 0x4A: 0xF4 index, 0xF5 when index = 0x9F.
        Debug 0x35: read cmds, staging, and register-write cmd only for page select 0x9F (data = [val, reg]).
        Blocked: flash engine, ISP 0x6F/0xEE, 0x3B XDATA write, 0xBA, EEPROM writes (nibble 4/F), 0x71."""
        dev = dev8 >> 1
        if dev == 0x4A and len(data) == 1:
            if sub == 0xF4:
                self.f4 = data[0]; return True
            return sub == 0xF5 and self.f4 == 0x9F
        if dev == 0x35:
            if sub in self.DBG_READ or (sub & 0x0F) in self.DBG_STAGE:
                return True
            if sub == 0x3B:                      # ScalerSetByte((staged hi << 8) | data[0], staged): page select only
                return len(data) >= 1 and data[0] == 0x9F
            return (sub & 0x0F) == 0 and sub != 0xBA and len(data) >= 2 and data[1] == 0x9F
        return False

    def read(self, dev8, sub, n):
        try:
            return self.bus.read(dev8 >> 1, sub, n)         # Bus traces success and error
        except OSError:
            return None

    def write(self, dev8, sub, data):
        if not self.allow_write and not (self.regread and self.regread_ok(dev8, sub, data)):
            rtd_proto.trace(dev8 >> 1, "w", sub, data, 0, None, True)
            return False
        try:
            self.bus.write(dev8 >> 1, sub, data)
        except OSError:
            return False
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
    global LOG, RAW
    lg = setup_logs("rtd_i2c_bridge")
    LOG, RAW = lg.main, lg.raw
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    if sys.argv[1] == "emu":
        be = Emu(Path(sys.argv[2]).read_bytes())
    else:
        be = Real(int(sys.argv[2]), "--allow-write" in sys.argv, "--regread" in sys.argv)
    serve(be, port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
