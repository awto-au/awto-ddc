"""Reference monitors (devices.json `reference`, awto-ddc#390): standard DDC/CI Get / Set VCP over unit_ops.DdcSession.
- Bus: the connector's ddc link first, then Intel buses (i915 gmbus / AUX), proven by EDID serial. Never NVIDIA: its I2C-over-AUX ACKs every address (#381).
- Traffic: Get / Set VCP frames to 0x37 only, >= GAP_S apart. No vendor frames (FE EF / FE E1), no ISP 0x49, SERDB 0x59 or 0x4A.
- Writes: WRITE_CODES only, each value checked, and only after enable_writes(True) (off by default)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import isostamp
import unit_ops as U
from _repo import ROOT

GAP_S = 0.110             # min time between DDC/CI transactions: TPV drops faster traffic (#381: prior work paces 110-120 ms)
INTEL_PREFIXES = ("i915 gmbus", "AUX ")

# (code, label) shown in the GUI; meanings of the Philips values from #381 (SmartControl 7.2.0 tables + read-only scan)
STANDARD = ((0x10, "brightness"), (0x12, "contrast"), (0x14, "colour preset"), (0x16, "red gain"), (0x18, "green gain"),
            (0x1A, "blue gain"), (0x72, "gamma"), (0x60, "input"), (0x62, "volume"), (0xC0, "usage hours"),
            (0xD6, "power mode"), (0x8D, "audio mute"))
MANUFACTURER = ((0xE0, ""), (0xE6, "PBP state? (499P9, not in caps)"), (0xE7, ""), (0xE9, "resolution notifier"), (0xEB, ""),
                (0xEC, "PIP/PBP size + location"), (0xEF, ""), (0xF0, ""), (0xF6, "PIP/PBP swap"), (0xF7, "PIP/PBP modes supported"),
                (0xFA, ""), (0xFB, ""), (0xFC, ""), (0xFD, ""), (0xFE, ""), (0xFF, ""), (0x68, "not in caps"), (0xA8, "not in caps"))

PRESET = {0x01: "sRGB", 0x02: "native", 0x04: "5000K", 0x05: "6500K", 0x06: "7500K", 0x07: "8200K", 0x08: "9300K",
          0x0A: "11500K", 0x0B: "user"}
GAMMA = {0x50: "1.8", 0x64: "2.0", 0x78: "2.2", 0x8C: "2.4", 0xA0: "2.6"}
INPUT = {0x01: "VGA-1", 0x0F: "DP-1", 0x11: "HDMI-1", 0x12: "HDMI-2"}     # main inputs in the 288E2 caps 60(...)
POWER = {0x01: "on", 0x04: "off (recovers)", 0x05: "off"}
MUTE = {0x01: "muted", 0x02: "unmuted"}
NAMES = {0x14: PRESET, 0x72: GAMMA, 0x60: INPUT, 0xD6: POWER, 0x8D: MUTE}
WRITE_CODES = (0x10, 0x12, 0x14, 0x60)    # brightness, contrast, preset, input (#390)


def load() -> dict:
    """name -> entry of devices.json `reference`"""
    return json.loads((ROOT / "scripts" / "devices.json").read_text()).get("reference", {})


def conn_bus(connector: str) -> int | None:
    link = (Path("/sys/class/drm") / connector / "ddc").resolve()
    return int(link.name.split("-")[1]) if link.name.startswith("i2c-") else None


def candidates(ref: dict, conn=conn_bus, buses=None, name=i2cbus.adapter_name) -> list[int]:
    """the connector's link, then every Intel display bus; NVIDIA adapters are dropped"""
    first = conn(ref["connector"]) if ref.get("connector") else None
    out = [first] if first is not None else []
    out += [b for b in (buses if buses is not None else i2cbus.list_buses(display_only=True)) if b not in out]
    return [b for b in out if name(b).startswith(INTEL_PREFIXES)]


def find_bus(ref: dict, edid=i2cbus.edid_serial, **kw) -> int:
    for b in candidates(ref, **kw):
        if edid(b) == ref["serial"]:
            return b
    raise SystemExit(f"{ref.get('model', ref['serial'])}: no Intel bus with EDID serial {ref['serial']} (NVIDIA is never used)")


def prove(bus: int, serial: str, edid=i2cbus.edid_serial) -> None:
    """open guard for the session: this bus still carries the reference monitor's EDID serial"""
    s = edid(bus)
    if s != serial:
        raise SystemExit(f"bus {bus}: EDID serial {s!r} != reference {serial!r}; refusing")


def decode(code: int, cur: int, mx: int) -> str:
    if code == 0xC0:                          # usage time: sh sl hours; ml is a 3rd byte unless the max reads ff ff (288E2 does)
        return f"{cur if mx == 0xFFFF else (mx & 0xFF) << 16 | cur} h"
    names = NAMES.get(code)
    if names is not None:
        lo = cur & 0xFF
        return names.get(lo, names.get(cur >> 8, f"0x{cur:04X}"))
    return f"{cur} / {mx}"


def raw4(cur: int, mx: int) -> str:
    """the 4 value bytes of the Get reply as sent: mh ml ch cl"""
    return f"{mx >> 8:02x} {mx & 0xFF:02x} {cur >> 8:02x} {cur & 0xFF:02x}"


class ReferenceDdc:
    """one reference monitor's DDC/CI: a unit_ops.DdcSession paced at GAP_S, proven by EDID at every open.
    Used from one worker thread. Errors: OSError / ValueError (a transfer / reply), LookupError (bus lookup / proof), PermissionError (a refused write)."""

    def __init__(self, ref: dict, find=find_bus, guard=prove, bus_cls=None, clock=time.monotonic, nap=time.sleep):
        self.ref, self.find, self.guard = ref, find, guard
        self.bus_cls, self.clock, self.nap = bus_cls, clock, nap
        self.session: U.DdcSession | None = None
        self.writes = False
        self.maxes: dict[int, int] = {}

    @property
    def bus(self) -> int | None:
        return self.session.bus_no if self.session else None

    def _session(self) -> U.DdcSession:
        if self.session is None or self.session.stale:
            self.close()
            try:
                bus = self.find(self.ref)
            except SystemExit as e:
                raise LookupError(str(e)) from None
            self.session = U.DdcSession(bus, self.ref["serial"], bus_cls=self.bus_cls, clock=self.clock,
                                        nap=self.nap, gap_s=GAP_S, guard=self.guard)
        return self.session

    def _run(self, fn):
        """a failed proof (recabled: another EDID on the bus) drops the session: the next call looks the bus up again"""
        try:
            return fn(self._session())
        except SystemExit as e:
            self.close()
            raise LookupError(str(e)) from None

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def get(self, code: int) -> tuple[int, int]:
        cur, mx = self._run(lambda s: s.get_vcp(code))
        self.maxes[code] = mx
        return cur, mx

    def enable_writes(self, on: bool) -> None:
        self.writes = bool(on)

    def check(self, code: int, value: int) -> None:
        if not self.writes:
            raise PermissionError("writes are off (toggle in the GUI)")
        if code not in WRITE_CODES:
            raise PermissionError(f"VCP {code:#04x}: not a reference write code {[hex(c) for c in WRITE_CODES]}")
        if code in NAMES:
            if value not in NAMES[code]:
                raise PermissionError(f"VCP {code:#04x} = {value:#x}: not one of {[hex(v) for v in NAMES[code]]}")
        elif code not in self.maxes:
            raise PermissionError(f"VCP {code:#04x}: max not read yet; read before a write")
        elif not 0 <= value <= self.maxes[code]:
            raise PermissionError(f"VCP {code:#04x} = {value}: outside 0..{self.maxes[code]}")

    def set(self, code: int, value: int) -> None:
        self.check(code, value)
        self._run(lambda s: s.set_vcp(code, value))


def read_all(ddc: ReferenceDdc, codes=None) -> list[tuple[int, str, str]]:
    """(code, decoded, raw bytes) per code; a failed code reads as its error, the pass goes on"""
    out = []
    for code, _label in codes or (*STANDARD, *MANUFACTURER):
        try:
            cur, mx = ddc.get(code)
            out.append((code, decode(code, cur, mx), raw4(cur, mx)))
        except (OSError, ValueError, LookupError) as e:
            out.append((code, f"error: {e}", ""))
    return out


def main(argv: list[str]) -> int:
    """read-only: every STANDARD + MANUFACTURER code of one reference monitor, one line each -> stdout + tmp/logs/reference_mon.log"""
    name = argv[0] if argv else "philips"
    refs = load()
    if name not in refs:
        raise SystemExit(f"no reference monitor {name!r} in devices.json ({sorted(refs)})")
    log = ROOT / "tmp" / "logs" / "reference_mon.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    ddc = ReferenceDdc(refs[name])
    t0 = time.monotonic()
    rows = read_all(ddc)
    labels = dict((*STANDARD, *MANUFACTURER))
    with log.open("a") as f:
        for code, text, raw in rows:
            line = f"{isostamp.now_ms()} {name} bus {ddc.bus} VCP {code:02X} {labels[code] or '-'}: {text}  [{raw}]"
            print(line)
            f.write(line + "\n")
        f.write(f"{name}: {len(rows)} codes in {time.monotonic() - t0:.2f} s\n")
    ddc.close()
    print(f"{name}: {len(rows)} codes in {time.monotonic() - t0:.2f} s")
    return 0 if any(raw for _c, _t, raw in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
