"""Device operations on a unit's bus: the ONE implementation (awto-ddc#276). The GUI's workers run them through
`dev.py <cmd> --direct`; the dev.py CLI is a thin client of the GUI control port and never runs them by itself.
Each op takes the dev module `d` (unit lookup, bus lookup, script runner) and the argument list; returns the exit code."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus

DDC_SUBS = {"list": 0, "get": 1, "set": 2, "sleep": 0, "wake": 0, "brightness": 1}
I2C_ADDR_MAX = 0x7F                                  # 7-bit address; an 8-bit 0x6E style address is refused, not shifted

# DDC/CI Set / Get VCP straight on the unit's bus (no `ddcutil detect`, awto-ddc#277). Frame to 0x37: source 0x51, 0x80|len, opcode, data, chk
DDCCI_ADDR, DDCCI_SRC, DDCCI_DEST_W = 0x37, 0x51, 0x6E
OP_GET, OP_GET_REPLY, OP_SET = 0x01, 0x02, 0x03
MIN_FRAME_GAP_S = 0.020          # two frames to one unit: firmware serves DDC/CI in the AWTO_SET_LOOP_MS (20 ms) main-loop pass, one deferred request per engine
GET_WAIT_S = 0.040               # MCCS: a Get reply is ready >= 40 ms after the request (ddcutil waits the same)
GET_REPLY_LEN = 11               # 6E 88 02 rc code type maxH maxL curH curL chk
VCP_SEL, VCP_VAL = 0xE0, 0xE1    # registry id select / value of the selected row (fw vcp.c): a paged write for rows without an own VCP code


def ddcci_frame(opcode: int, *data: int) -> bytes:
    """bytes after the 0x37 address for one request: 51, 0x80 | length, opcode, data..., checksum (0x6E ^ every byte before it)"""
    body = bytes([DDCCI_SRC, 0x80 | (1 + len(data)), opcode, *data])
    chk = DDCCI_DEST_W
    for x in body:
        chk ^= x
    return body + bytes([chk])


def set_frame(code: int, value: int) -> bytes:
    if not 0 <= code <= 0xFF or not 0 <= value <= 0xFFFF:
        raise ValueError(f"VCP set {code:#x} = {value}: code 0..0xFF, value 0..0xFFFF")
    return ddcci_frame(OP_SET, code, value >> 8, value & 0xFF)


def get_frame(code: int) -> bytes:
    return ddcci_frame(OP_GET, code)


def parse_get_reply(buf: bytes, code: int) -> tuple[int, int]:
    """(current, max) of a Get VCP reply; ValueError on a wrong length / checksum / code / result code (a NAK-style reply is not a value)"""
    if len(buf) < GET_REPLY_LEN or buf[0] != DDCCI_DEST_W or buf[1] != 0x88 or buf[2] != OP_GET_REPLY:
        raise ValueError(f"VCP {code:#04x} get: not a get reply: {buf.hex(' ')}")
    chk = 0x50                                       # the reply checksum is seeded with 0x50 (destination 0x51 read-side)
    for x in buf[:GET_REPLY_LEN - 1]:
        chk ^= x
    if chk != buf[GET_REPLY_LEN - 1]:
        raise ValueError(f"VCP {code:#04x} get: bad checksum in {buf.hex(' ')}")
    if buf[3] != 0 or buf[4] != code:
        raise ValueError(f"VCP {code:#04x} get: result {buf[3]:#x} for code {buf[4]:#x} (1 = unsupported)")
    return buf[8] << 8 | buf[9], buf[6] << 8 | buf[7]


class DdcSession:
    """One unit's DDC/CI: a persistent /dev/i2c fd, frames spaced >= MIN_FRAME_GAP_S, the EDID serial proven once at open.
    Used from ONE worker thread (the unit's queue); `lock` makes a stray second caller wait. Errors are OSError / ValueError, never swallowed."""

    def __init__(self, bus: int, serial: str, bus_cls=None, clock=time.monotonic, nap=time.sleep, prove=True):
        self.bus_no, self.serial, self.bus_cls, self.clock, self.nap, self.prove = bus, serial, bus_cls or BUS_CLS, clock, nap, prove
        self.bus, self.last_t, self.sel, self.lock, self.stale = None, None, None, threading.Lock(), False

    def open(self) -> None:
        if self.bus is None:
            if self.prove:
                i2cbus.require_unit(self.bus_no, self.serial)
            self.bus = self.bus_cls(self.bus_no)
            self.sel = None

    def close(self) -> None:
        if self.bus is not None:
            self.bus.close()
            self.bus = None

    def _gap(self) -> None:
        if self.last_t is not None:
            wait = MIN_FRAME_GAP_S - (self.clock() - self.last_t)
            if wait > 0:
                self.nap(wait)

    def _send(self, frame: bytes) -> None:
        self._gap()
        try:
            self.bus.write(DDCCI_ADDR, frame[0], frame[1:])
        except OSError:
            self.close()                             # a failed transfer may leave the fd in a bad state: the next call reopens + re-proves
            self.stale = True                        # and session_for() looks the bus up again (the unit may have been recabled)
            raise
        finally:
            self.last_t = self.clock()

    def set_vcp(self, code: int, value: int, reselect: bool = False, row_id: int | None = None) -> None:
        """one Set VCP frame; row_id = a registry row without its own VCP code: select it first (when it changed or `reselect`), then 0xE1"""
        with self.lock:
            self.open()
            if row_id is not None:
                if reselect or self.sel != row_id:
                    self._send(set_frame(VCP_SEL, row_id))
                    self.sel = row_id
                code = VCP_VAL
            self._send(set_frame(code, value))

    def get_vcp(self, code: int, row_id: int | None = None) -> tuple[int, int]:
        with self.lock:
            self.open()
            if row_id is not None:
                self._send(set_frame(VCP_SEL, row_id))
                self.sel = row_id
                code = VCP_VAL
            self._send(get_frame(code))
            self.nap(GET_WAIT_S)
            try:
                buf = self.bus.ops(DDCCI_ADDR, [GET_REPLY_LEN])[0]
            except OSError:
                self.close()
                self.stale = True
                raise
            self.last_t = self.clock()
            return parse_get_reply(buf, code)


BUS_CLS = i2cbus.Bus                                 # tests put a fake bus here
SESSIONS: dict[str, DdcSession] = {}                 # per serial, in the app process: the persistent fd of each unit
SESSIONS_LOCK = threading.Lock()


def session_for(d, u: dict) -> DdcSession:
    """the unit's session; the bus comes from dev.py's EDID-proven lookup, re-looked-up when the session had no open fd"""
    with SESSIONS_LOCK:
        s = SESSIONS.get(u["serial"])
        if s is None or s.stale:
            s = SESSIONS[u["serial"]] = DdcSession(d._bus(u), u["serial"], prove=False)   # _bus() just proved the serial on that bus
        return s


def parse_code(text: str) -> int:
    """a VCP code as ddcutil reads it: 0x10 or bare hex (10 = 0x10)"""
    return int(text, 16)


def ddc(d, extra: list[str]) -> int:
    _n, u = d._unit(extra)
    many = bool(extra) and extra[0] == "get" and 2 <= len(extra) <= 9          # get CODE [CODE...]: one detect for all codes
    if not extra or extra[0] not in DDC_SUBS or (len(extra) != 1 + DDC_SUBS[extra[0]] and not many) \
            or any(x.startswith("-") for x in extra):
        raise SystemExit(f"ddc: one of {DDC_SUBS} (arg counts {list(DDC_SUBS.values())}); got {extra}; nothing done")
    if extra[0] == "set":                            # plain Set VCP: straight on the bus, no `ddcutil detect` (awto-ddc#277)
        code, val = parse_code(extra[1]), int(extra[2], 0)
        t0 = time.monotonic()
        try:
            session_for(d, u).set_vcp(code, val)
        except (OSError, ValueError) as e:
            d.log(f"ddc set {code:#04x} = {val}: fast DDC/CI write failed ({e!r}); falling back to ddcutil setvcp through ddc_ctl.py", "WARN")
            return d._py("ddc_ctl.py", "--bus", d._bus(u), *extra)
        d.log(f"ddc set {code:#04x} = {val}: fast DDC/CI write ok ({(time.monotonic() - t0) * 1000:.0f} ms)")
        return 0
    return d._py("ddc_ctl.py", "--bus", d._bus(u), *extra)


def settings(d, extra: list[str]) -> int:
    sim, given = d._opt(extra, "--sim"), d._opt(extra, "--map")
    if extra[:1] == ["rows"]:
        return d._py("settings_cli.py", "--map", "-", *extra)
    if sim:
        mp = given or str(d.Path(sim).with_suffix(".map"))
        return d._py("settings_cli.py", "--sim", sim, "--map", mp, *extra)
    _n, u = d._unit(extra)
    b = d._live_bus(u)
    mp = d._fwmap(u, given)
    if not given:
        d._registry_verify(u, b)                     # flash registry staleness probe (same as before the port)
    return d._dbg_py(b, "settings_cli.py", "--bus", str(b), "--serial", u["serial"], "--map", mp, *extra)


def synclog(d, extra: list[str]) -> int:
    flags = [f for f in ("--whole", "--delta", "--json") if d._flag(extra, f)]
    given = d._opt(extra, "--map")
    _n, u = d._unit(extra)
    b = d._live_bus(u)
    return d._dbg_py(b, "sync_log.py", b, "--serial", u["serial"], "--map", d._fwmap(u, given), *flags)


def note(d, extra: list[str]) -> int:
    given, openc = d._opt(extra, "--map"), d._flag(extra, "--open-console")
    _n, u = d._unit(extra)
    text = list(extra)
    if given is True or len(text) != 1 or text[0].startswith("--"):
        raise SystemExit("note: one TEXT argument (quote it); nothing done")
    b = d._live_bus(u)
    return d._dbg_py(b, "host_note.py", b, "--serial", u["serial"], "--map", d._fwmap(u, given),
                     *(["--open-console"] if openc else []), text[0], keep_console=openc)


def kvm(d, extra: list[str]) -> int:
    return d._py("kvm.py", *extra)


def i2c(d, extra: list[str]) -> int:
    """raw transfer on the unit's EDID-proven bus: ADDR [BYTES...] [--read N]; bytes = write, then a repeated-start read of N"""
    read = d._opt(extra, "--read", None)
    _n, u = d._unit(extra)
    if not extra:
        raise SystemExit("i2c: ADDR [BYTES...] [--read N]; nothing done")
    args = ["--addr", extra[0], "--serial", u["serial"], "--bus", str(d._bus(u))]
    if extra[1:]:
        args += ["--write", *extra[1:]]
    if read not in (None, True):
        args += ["--read", str(read)]
    return d._py("i2c_raw.py", *args)
