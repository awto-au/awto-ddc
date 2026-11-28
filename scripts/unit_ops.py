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
import isostamp
import settings_table as T
import unit_status as S

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

    def __init__(self, bus: int, serial: str, bus_cls=None, clock=time.monotonic, nap=time.sleep, prove=True,
                 gap_s: float = MIN_FRAME_GAP_S, guard=None):
        self.bus_no, self.serial, self.bus_cls, self.clock, self.nap, self.prove = bus, serial, bus_cls or BUS_CLS, clock, nap, prove
        self.gap_s, self.guard = gap_s, guard           # guard(bus, serial): identity proof at open; default i2cbus.require_unit
        self.bus, self.last_t, self.sel, self.lock, self.stale = None, None, None, threading.Lock(), False

    def open(self) -> None:
        if self.bus is None:
            if self.prove:
                (self.guard or i2cbus.require_unit)(self.bus_no, self.serial)
            self.bus = self.bus_cls(self.bus_no)
            self.sel = None

    def close(self) -> None:
        if self.bus is not None:
            self.bus.close()
            self.bus = None

    def _gap(self) -> None:
        if self.last_t is not None:
            wait = self.gap_s - (self.clock() - self.last_t)
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


_MAPS: dict[str, dict] = {}                          # map path -> symbol table (unit_health.load_maps), parsed once


def _debug_part(bus: int, serial: str, be: bool) -> tuple[dict | None, str]:
    """reads over the debug slave 0x35 when it ALREADY answers: diag block, clocks, PWM4 duty, input timing (needs the flashed map).
    Staging writes only (Real allow_write=False); never the DDC <-> debug swap (that is a Set VCP). (dict | None, why none)"""
    import dbg_xdata as X
    import flash_registry
    import rtd_i2c_bridge as B
    import rtd_proto as P
    import unit_health as H
    io = B.Real(bus, allow_write=False, regread=True)
    try:
        h = X.read_bytes(io, S.DIAG_BASE, 3)
        if h is None or h[:2] != b"AD":
            return None, "0x35 not answering (debug link is on the DDC side)"
        blk = X.block_supported(h)
        diag = X.read(io, S.DIAG_BASE, S.DIAG_LEN, blk)
        pll, mcu, pwm = X.read(io, S.PLL_E0, S.PLL_E7 - S.PLL_E0 + 1, blk), X.read(io, S.MCU_FFE9, S.MCU_FFEE - S.MCU_FFE9 + 1, blk), \
            X.read(io, S.FF_PWM4H_DUT, 1, blk)
        if None in (diag, pll, mcu, pwm):
            return None, "0x35 read failed"
        g = S.decode_diag(diag, be)
        g["clk"] = S.clocks(pll[0], pll[S.PLL_E1 - S.PLL_E0], pll[-1], mcu[0], mcu[S.MCU_FFED - S.MCU_FFE9], mcu[-1])
        g["pwm"], g["timing"], g["timing_why"] = pwm[0], None, ""
        mp = flash_registry.current(serial).get("map")
        if not mp:
            g["timing_why"] = "no map for the flashed image"
            return g, ""
        try:
            maps = _MAPS.get(str(mp)) or _MAPS.setdefault(str(mp), H.load_maps(Path(mp).read_text(errors="replace")))

            def rd(a, n):
                b = X.read(io, a, n, blk)
                if b is None:
                    raise H.DbgError(f"read {a:#06x}+{n} failed")
                return b
            t, x, _note = P.read_timing(rd, maps)
        except H.DbgError as e:
            g["timing_why"] = str(e)
            return g, ""
        if t["hwidth"]:
            g["timing"] = {"w": t["hwidth"], "h": t["vheight"], "hz": x["vfreq_mhz"] / 1000 if x else t["vfreq"] / 10}
        return g, ""
    finally:
        io.close()


def status(d, u: dict) -> dict:
    """One read-only pass for the GUI status line (awto-ddc#277): Get VCP of the quick rows + the info rows (paged read) over the unit's DDC session, then the
    debug-slave reads only for fields the rows left empty. A failed source is named in `ddc_err` / `dbg_err`; the rest still returns."""
    import flash_registry
    st = {"serial": u["serial"], "t": isostamp.now(), "ddc": {}, "ddc_err": "", "dbg": None, "dbg_err": "",
          "tag": str(flash_registry.current(u["serial"]).get("tag") or "")}
    s = session_for(d, u)
    st["info"] = {}
    reads = [(n, st["ddc"], lambda n=n: S.row_value(n, s.get_vcp(T.BY_NAME[n]["vcp"])[0])) for n in S.DDC_ROWS]
    reads += [(n, st["info"], lambda n=n: s.get_vcp(0, row_id=T.BY_NAME[n]["id"])[0]) for n in S.INFO_ROWS]    # paged: row select + Get
    for name, into, read in reads:
        try:
            v = read()
        except OSError as e:
            st["ddc_err"] = f"{name}: {e}"             # a bus error: the rest would fail the same way
            break
        except ValueError as e:                        # unsupported / garbled for this one row: keep going
            st["ddc_err"] = f"{name}: {e}"
            continue
        if v is not None:
            into[name] = v
    if not S.missing_fields(st):                       # the info rows filled every field: 0x35 is only the fallback for firmware without them
        return st
    try:
        st["dbg"], why = _debug_part(s.bus_no, u["serial"], bool(u.get("be")))
    except (OSError, SystemExit, ValueError) as e:
        why = f"{type(e).__name__}: {e}"
    gaps = S.missing_fields(st)
    if gaps:
        st["dbg_err"] = f"{', '.join(gaps)} n/a: {why or (st['dbg'] or {}).get('timing_why') or 'no source'}"
    return st


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
    flags = [f for f in ("--whole", "--json", "--dram", "--all") if d._flag(extra, f)]
    for opt in ("--last", "--boot", "--since", "--count"):           # DRAM log (docs/dram-log-design.md): newest K entries / one boot / a page
        v = d._opt(extra, opt)
        if v not in (None, True):
            flags += [opt, str(v)]
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
