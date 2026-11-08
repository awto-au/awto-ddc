#!/usr/bin/env python3
"""Decode I2C traffic to an RTD scaler / monitor into readable lines, ONCE, in code.

Stream in: Txn (dev, 'w' sub data | 'r' sub n -> bytes), fed by taps (rtd_i2c_bridge.Real, rtd_isp_probe.Isp)
or by rtd_log.py from an old raw log. Stream out: one line per MEANING, stateful, repetitive sequences coalesced.
  0x35 debug slave : SDK ScalerCommonDebug.c ScalerDebug (stage 0x01/0x02 hi, 0x03 val, 0x3A read, 0x3B write,
                     0x41 scaler read, 0x80 halt, message protocol 0x55/0x25/0x2A/0x2F)
  0x4A ISP slave   : F4/F5 indexed scaler window + page select 0x9F, 0x6F ISP ctl, SPI engine 0x60-0x6D/0x70-0x75
                     (docs/flash-crc.md, docs/flash-burst.md), 0xEE reset
  0x50 EDID, 0x54 SCDC, 0x37 DDC/CI (VCP)
  Symbols: --map image .map (XDATA names), StAwtoDiag/StAwtoSafe fields parsed from fw/overlay RL6449_Project.h,
  regdb register names (re/regdb via regdb_query).
API: setup_logs(name, map=None) -> Logs: <tool>.log (decoded + the tool's own lines), <tool>.raw.log (byte trace).
Raw line format (parse_raw): `<ts> REAL write dev=0x35 reg 0x3b f8` / `REAL read dev=0x35 reg 0x08 n=1 -> 41`.
"""
from __future__ import annotations

import atexit, os, re, sys, time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import NamedTuple

HERE = Path(__file__).resolve().parent


def repo_root() -> Path:
    return Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Txn(NamedTuple):
    ts: str
    dev: int                       # 7-bit
    kind: str                      # 'w' | 'r'
    sub: int
    data: bytes | None             # write payload / bytes read; None = failed
    n: int = 0                     # read length requested
    err: str | None = None
    blocked: bool = False


TAPS: list = []


def trace(dev: int, kind: str, sub: int, data: bytes | None, n: int = 0, err: str | None = None,
          blocked: bool = False) -> None:
    if TAPS:
        t = Txn(now(), dev, kind, sub, None if data is None else bytes(data), n or len(data or b""), err, blocked)
        for f in TAPS:
            f(t)


# ---- raw line format -------------------------------------------------------------------------------------------
def _hex(b: bytes) -> str:
    return b[:16].hex() + (f".. len={len(b)}" if len(b) > 16 else "")


def raw_line(t: Txn) -> str:
    d = f"dev=0x{t.dev:02x} reg 0x{t.sub:02x}"
    if t.kind == "w":
        s = f"REAL write {'BLOCKED ' if t.blocked else ''}{d} {_hex(t.data or b'')}"
        return s + (f" FAIL {t.err}" if t.err else "")
    if t.err or t.data is None:
        return f"REAL read {d} n={t.n} FAIL {t.err}"
    return f"REAL read {d} n={t.n} -> {_hex(t.data)}"


_RAW = re.compile(r"^(?P<ts>\S+) REAL (?P<k>write|read) (?P<blk>BLOCKED )?dev=0x(?P<dev>[0-9a-f]+) "
                  r"reg 0x(?P<sub>[0-9a-f]+)(?P<rest>.*)$")


def parse_raw(line: str) -> Txn | None:
    m = _RAW.match(line.rstrip("\n"))
    if not m:
        return None
    rest, err = m["rest"], None
    f = re.search(r" FAIL (.*)$", rest)
    if f:
        err, rest = f[1], rest[:f.start()]
    ln = re.search(r" len=(\d+)", rest)
    nn = re.search(r" n=(\d+)", rest)
    hm = re.search(r"(?:->\s*)?([0-9a-f]*)(?:\.\.)?(?: len=\d+)?\s*$", re.sub(r" n=\d+", "", rest)) if not err else None
    data = bytes.fromhex(hm[1]) if hm and len(hm[1]) % 2 == 0 else b""
    n = int(nn[1]) if nn else len(data)
    if ln:
        data = data + b"\0" * (int(ln[1]) - len(data))      # length only matters, values past 16 B were not logged
    return Txn(m["ts"], int(m["dev"], 16), "w" if m["k"] == "write" else "r", int(m["sub"], 16),
               None if err else data, n, err, bool(m["blk"]))


# ---- exact input frequencies (#34, #26) --------------------------------------------------------------------------
# The SDK keeps HFreq in 0.1 kHz and VFreq in 0.1 Hz from the HS period (~650 measure clocks at 4K: 1 count = 0.15 %), so 60.000
# and 59.940 both read "60.0" (60.000 even reads 60.1). Exact values come from the input active-region count the M-domain set-up
# took (g_ulInputActiveRegionBackUp, measure clocks from the first to the last active pixel): resolution 1 in ~1.4 M at 4K.
XTAL_HZ = 14_318_180                       # board crystal (4x NTSC colour burst); SDK _XTAL14318K = 14318 kHz
MEAS_HZ = XTAL_HZ * 49 // 2 // 4           # _MEASURE_CLK: M2PLL (M 49, N 2, O 1) / P40_07 divider 4 = 87.699 MHz
TIMING_SYMS = ("g_stMDomainInputData", "g_ulInputActiveRegionBackUp")   # + g_stAwtoFreq in images with fw/sdcc/awto_freq.inc
AWTO_FREQ_SYM, AWTO_FREQ_LEN = "g_stAwtoFreq", 30
STALE_TOL = 0.01                           # exact vs SDK VFreq: SDK error <= 0.2 % at 4K (1 HS count); 1 % apart = other timing


def _be(b: bytes, i: int, n: int) -> int:
    return int.from_bytes(b[i:i + n], "big")


def decode_timing(b: bytes) -> dict:
    """g_stMDomainInputData (StructTimingInfo, big-endian WORDs after the flag byte): SDK units (0.1 kHz, 0.1 Hz)."""
    return {"hfreq": _be(b, 1, 2), "htotal": _be(b, 3, 2), "hwidth": _be(b, 5, 2), "vfreq": _be(b, 11, 2),
            "vtotal": _be(b, 13, 2), "vheight": _be(b, 15, 2)}


def exact_timing(t: dict, count: int, extra_lines: int = 0, meas_hz: int = MEAS_HZ) -> dict | None:
    """Pixel clock / H / V frequency from the active-region count: {pclk_hz, hfreq_hz, vfreq_mhz} (floats), None = no count."""
    if not count or not t["htotal"] or not t["vtotal"] or not t["vheight"]:
        return None
    pclk = meas_hz * (t["htotal"] * (t["vheight"] - 1 + extra_lines) + t["hwidth"]) / count
    x = {"pclk_hz": pclk, "hfreq_hz": pclk / t["htotal"], "vfreq_mhz": pclk * 1000 / (t["htotal"] * t["vtotal"])}
    if t["vfreq"] and abs(x["vfreq_mhz"] / 100 - t["vfreq"]) > max(3, t["vfreq"] * STALE_TOL):
        return None                        # count from an earlier mode set (timing changed since): not this timing
    return x


def decode_awto_freq(b: bytes) -> dict:
    """g_stAwtoFreq (RL6449_Project.h StAwtoFreq, big-endian): the firmware's own exact values and the raw count they came from."""
    return {"count": _be(b, 0, 4), "meas_hz": _be(b, 4, 4), "pclk_hz": _be(b, 8, 4), "hfreq_hz": _be(b, 12, 4),
            "vfreq_mhz": _be(b, 16, 4), "htotal": _be(b, 20, 2), "vtotal": _be(b, 22, 2), "hwidth": _be(b, 24, 2),
            "vheight": _be(b, 26, 2), "extra": b[28], "valid": b[29]}


def fmt_timing(t: dict, x: dict | None) -> str:
    """'3840x2160@59.940 Hz (H 134.865 kHz, pclk 593.407 MHz; htotal 4400 vtotal 2250)'; no count: the SDK's 0.1 values, marked."""
    if x:
        return (f"{t['hwidth']}x{t['vheight']}@{x['vfreq_mhz'] / 1000:.3f} Hz (H {x['hfreq_hz'] / 1000:.3f} kHz, "
                f"pclk {x['pclk_hz'] / 1e6:.3f} MHz; htotal {t['htotal']} vtotal {t['vtotal']})")
    return (f"{t['hwidth']}x{t['vheight']}@{t['vfreq'] / 10:.1f} Hz (SDK 0.1 Hz, no active-region count; H {t['hfreq'] / 10:.1f} kHz; "
            f"htotal {t['htotal']} vtotal {t['vtotal']})")


def read_timing(read, addr: dict) -> tuple[dict, dict | None, str]:
    """read(addr, n) -> bytes; addr: symbol -> XDATA address (TIMING_SYMS required, AWTO_FREQ_SYM optional).
    -> (SDK timing, exact from the raw count or None, note on the firmware's own exact values vs ours)."""
    t = decode_timing(read(addr["g_stMDomainInputData"], 17))
    count = _be(read(addr["g_ulInputActiveRegionBackUp"], 4), 0, 4)
    note, extra = "", 0
    if addr.get(AWTO_FREQ_SYM) is not None:
        f = decode_awto_freq(read(addr[AWTO_FREQ_SYM], AWTO_FREQ_LEN))
        if f["valid"] and f["count"] == count:
            extra = f["extra"]
            x = exact_timing(t, count, extra, f["meas_hz"])
            dv = abs(x["vfreq_mhz"] - f["vfreq_mhz"]) if x else None
            note = (f"fw {f['vfreq_mhz'] / 1000:.3f} Hz " + ("agrees" if dv is not None and dv <= 1.5 else f"DISAGREES by {dv} mHz")
                    if x else "")
        else:
            note = "fw exact values not valid for this count"
    return t, exact_timing(t, count, extra), note


# ---- symbols ---------------------------------------------------------------------------------------------------
OSD_EVENTS = {"info": 10, "nosignal": 1, "nocable": 2, "nosupport": 3, "failsafe": 4, "powersaving-msg": 5,
              "source-menu": 7}
OSD_KEYS = {"menu": 0, "right": 1, "left": 2, "exit": 3}
# g_stOsdInfo (StructOsdInfo, RTD2014Include.h): byte offsets of the fields the tools touch. The map has no member offsets and
# _DP_DEBUG_MSG (#37) adds a bit-field byte in front of them, so: firmware self-report (diag block 0x2C..0x2E, images from #37 on)
# > map hint (DP-info function linked = +1) > the layout of the images without both (_DP_DEBUG_MSG off).
OSD_OFS_LEGACY = {"usOsdState": 3, "ucOsdEventMsg": 5, "ucOsdKeyMessage": 6}
DIAG_OSD_OFS_AT = 0x2C
OSD_DP_INFO_SYM = "OsdPropGetShowDpInfoStringAddress"          # exists only with _DP_DEBUG_MSG on


def osd_offsets_from_map(map_text: str) -> dict:
    shift = 1 if OSD_DP_INFO_SYM in map_text else 0
    return {k: v + shift for k, v in OSD_OFS_LEGACY.items()}


def osd_offsets_from_diag(diag3: bytes) -> dict | None:
    """diag3 = diag block bytes 0x2C..0x2E; None when the image does not report (zeros; the event offset is never 0)."""
    if len(diag3) < 3 or diag3[1] == 0:
        return None
    return dict(zip(OSD_OFS_LEGACY, diag3[:3]))
TESTCMD = ("g_stAwtoDiag", 0x28)                               # firmware test-command byte (awto-ddc#33)
_CTYPE = {"unsigned char": 1, "unsigned int": 2, "unsigned long": 4, "char": 1, "int": 2}


def testcmd_name(v: int) -> str:
    if v == 0:
        return "idle"
    if 1 <= v <= 4:
        return f"inject key {next(k for k, x in OSD_KEYS.items() if x == v - 1)}"
    ev = {x: k for k, x in OSD_EVENTS.items()}.get(v - 0x10)
    return f"raise event {ev}" if ev else f"cmd 0x{v:02X}"


def parse_structs(header: str) -> tuple[dict, dict]:
    """-> ({type: [(off, size, name)]}, {symbol: (addr, type)}) from `typedef struct {...} T;` and `__at(0x..) T g_x;`."""
    structs = {}
    for m in re.finditer(r"typedef struct\s*\{(.*?)\}\s*(\w+);", header, re.S):
        off, fields = 0, []
        for fm in re.finditer(r"^\s*(unsigned (?:char|int|long)|char|int)\s+(\w+)(?:\[(\d+)\])?\s*;", m[1], re.M):
            sz, cnt = _CTYPE[fm[1]], int(fm[3] or 0)
            if cnt:
                for i in range(cnt):
                    fields.append((off, sz, f"{fm[2]}[{i}]")); off += sz
            else:
                fields.append((off, sz, fm[2])); off += sz
        structs[m[2]] = fields
    syms = {}
    for m in re.finditer(r"__at\(0x([0-9A-Fa-f]+)\)\s+(\w+)\s+(g_\w+)\s*;", header):
        syms[m[3]] = (int(m[1], 16), m[2])
    return structs, syms


class Symbols:
    def __init__(self):
        self.addr: dict[int, str] = {}              # exact XDATA/XFR symbol addresses
        self.struct_at: list[tuple[int, str, list]] = []   # (base, symbol, fields)
        self.size: dict[str, int] = {}
        self.osd_ofs = dict(OSD_OFS_LEGACY)

    @classmethod
    def load(cls, root: Path | None = None, map_path: Path | str | None = None) -> "Symbols":
        s, root = cls(), root or repo_root()
        mp = Path(map_path) if map_path else default_map(root)
        if mp and Path(mp).exists():
            mtxt = Path(mp).read_text(errors="replace")
            s.osd_ofs = osd_offsets_from_map(mtxt)
            for line in mtxt.splitlines():
                m = re.match(r"^(?:(D):)?\s+([0-9A-F]{8})\s+_(\w+)", line)
                if m and int(m[2], 16) <= 0xFFFF and (m[1] or int(m[2], 16) >= 0xE000):
                    s.addr.setdefault(int(m[2], 16), m[3])
        h = root / "fw/overlay/Project/Header/RL6449_Project.h"
        if h.exists():
            structs, syms = parse_structs(h.read_text(errors="replace"))
            for name, (a, typ) in syms.items():
                if typ in structs:
                    s.struct_at.append((a, name, structs[typ]))
                    s.addr.setdefault(a, name)
                    s.size[name] = sum(f[1] for f in structs[typ])
        for a, n in list(s.addr.items()):
            if n == "g_stOsdInfo":
                o = s.osd_ofs
                s.struct_at.append((a, n, [(o["ucOsdEventMsg"], 1, "ucOsdEventMsg"), (o["ucOsdKeyMessage"], 1, "ucOsdKeyMessage")]))
        return s

    def base(self, name: str) -> int | None:
        return next((a for a, n in self.addr.items() if n == name), None)

    def name(self, a: int) -> str | None:
        for base, sym, fields in self.struct_at:
            off = a - base
            if off < 0 or (sym in self.size and off >= self.size[sym]):
                continue
            for fo, fs, fn in fields:
                if fo <= off < fo + fs:
                    return f"{sym}.{fn}" + (f"+{off - fo}" if off > fo else "")
            if sym not in self.size and off < 0x10:
                return f"{sym}+{off}"
        return self.addr.get(a)

    def range_name(self, lo: int, hi: int) -> str | None:
        for base, sym, _ in self.struct_at:
            if sym in self.size and base == lo and base + self.size[sym] - 1 == hi:
                return sym
        a, b = self.name(lo), self.name(hi)
        return f"{a}..{b}" if a and b else a

    def value_note(self, a: int, v: int, write: bool = False) -> str:
        n = self.name(a) or ""
        if n == "g_stOsdInfo.ucOsdEventMsg":
            ev = {x: k for k, x in OSD_EVENTS.items()}.get(v)
            return f" = event {ev}" if ev else ""
        if n == "g_stOsdInfo.ucOsdKeyMessage":
            k = {x: k for k, x in OSD_KEYS.items()}.get(v)
            return f" = key {k}" if k else ""
        if write and a == (self.base(TESTCMD[0]) or -1) + TESTCMD[1]:
            return f" = test cmd: {testcmd_name(v)}"
        return ""


def default_map(root: Path) -> Path | None:
    if os.environ.get("AWTO_DDC_MAP"):
        return Path(os.environ["AWTO_DDC_MAP"])
    maps = sorted((root / "tmp/fw").glob("*/fw.map"), key=lambda p: p.stat().st_mtime) if (root / "tmp/fw").exists() else []
    return maps[-1] if maps else None


def regdb_namer(chip: str = "RTD2795T-CG"):
    """reg16 (page<<8 | idx) -> regdb register name; table loads on first lookup."""
    tab: dict = {}

    def f(a: int) -> str | None:
        if not tab:
            try:
                sys.path.insert(0, str(HERE))
                import regdb_query as Q
                for r in Q.load(chip):
                    if r["kind"] == "REG" and not r["port_idx"]:
                        tab.setdefault(int(r["address"], 0), r["register"])
            except (SystemExit, Exception):
                tab[-1] = ""
        return tab.get(a)
    return f


def load_msgids(root: Path) -> dict:
    """fw/msgids.tsv: id (hex), category, file:line, text -> {id: (file:line, text)}."""
    out, f = {}, root / "fw/msgids.tsv"
    if f.exists():
        for line in f.read_text().splitlines():
            c = line.split("\t")
            try:
                out[int(c[0], 16)] = (c[2], c[3]) if len(c) >= 4 else (c[2] if len(c) > 2 else "", "")
            except ValueError:
                pass
    return out


# ---- tables ----------------------------------------------------------------------------------------------------
DBG_CMDS = {0x01: "stage hi", 0x02: "stage hi", 0x03: "stage value", 0x05: "stage b4", 0x06: "stage value",
            0x04: "EEPROM write", 0x0F: "EEPROM write", 0x20: "handshake", 0x25: "message fetch", 0x2A: "message end",
            0x2F: "message stop", 0x3A: "XDATA read", 0x3B: "XDATA write", 0x3C: "XDATA block read", 0x3D: "net exchange (#80)", 0x41: "scaler read", 0x44: "EEPROM read",
            0x45: "EEPROM read", 0x55: "message enable", 0x71: "DDC/CI mode switch", 0x80: "halt main"}
ISP_REGS = {0x60: "SPI_CTL", 0x61: "SPI_OP", 0x62: "OP_WREN", 0x63: "OP_EWSR", 0x6A: "OP_READ", 0x6B: "OP_FAST_READ", 0x6E: "OP_RDSR", 0x64: "ADDR_H", 0x65: "ADDR_M", 0x66: "ADDR_L",
            0x67: "RDATA0", 0x68: "RDATA1", 0x69: "RDATA2", 0x6D: "OP_PP", 0x6F: "ISP_CTL", 0x70: "FIFO",
            0x71: "PROG_LEN", 0x72: "CRC_END_H", 0x73: "CRC_END_M", 0x74: "CRC_END_L", 0x75: "CRC_RESULT",
            0xEE: "RESET", 0xF4: "SCA_INDEX", 0xF5: "SCA_DATA"}
OPCFG = {0x62: "WREN", 0x63: "EWSR", 0x6A: "READ", 0x6B: "FAST_READ", 0x6D: "PP", 0x6E: "RDSR"}   # engine opcode config
ENG = {0x60, 0x61, 0x62, 0x64, 0x65, 0x66, 0x6D, 0x71, 0x72, 0x73, 0x74}
SPI_OPS = {0x9F: "JEDEC ID", 0x05: "RDSR", 0x01: "WRSR", 0x06: "WREN", 0x04: "WRDI", 0x03: "READ", 0x0B: "FAST_READ",
           0x20: "sector erase 4K", 0xD8: "block erase 64K", 0x52: "block erase 32K", 0xC7: "chip erase",
           0x60: "chip erase", 0x02: "page program", 0xB1: "ENSO", 0xC1: "EXSO", 0x4B: "RDUID", 0xAB: "RDP/ID"}
SCDC_REGS = {0x01: "SINK_VERSION", 0x02: "SOURCE_VERSION", 0x10: "UPDATE_FLAGS_0", 0x11: "UPDATE_FLAGS_1",
             0x20: "TMDS_CONFIG", 0x21: "SCRAMBLER_STATUS", 0x30: "CONFIG_0", 0x31: "CONFIG_1",
             0x40: "STATUS_FLAGS_0", 0x41: "STATUS_FLAGS_1", 0x50: "CH0_ERR_L", 0x51: "CH0_ERR_H", 0x52: "CH1_ERR_L",
             0x53: "CH1_ERR_H", 0x54: "CH2_ERR_L", 0x55: "CH2_ERR_H", 0x56: "ERR_CHECKSUM"}
VCP = {0x02: "new control value", 0x04: "restore factory defaults", 0x10: "brightness", 0x12: "contrast",
       0x14: "colour preset", 0x16: "red gain", 0x18: "green gain", 0x1A: "blue gain", 0x60: "input source",
       0x62: "audio volume", 0x6C: "red black level", 0x6E: "green black level", 0x70: "blue black level",
       0xAC: "h frequency", 0xAE: "v frequency", 0xB6: "display technology", 0xC0: "usage time", 0xC6: "app enable key",
       0xC8: "controller type", 0xC9: "firmware version", 0xCA: "OSD", 0xCC: "OSD language", 0xD6: "power mode",
       0xDC: "display mode", 0xDF: "VCP version"}
DDC_OPS = {0x01: "get VCP", 0x02: "VCP reply", 0x03: "set VCP", 0x07: "save settings", 0xE3: "capabilities reply",
           0xF3: "capabilities request", 0x0C: "enable/disable", 0xA1: "timing request", 0xA2: "timing reply",
           0xD0: "net exchange (#80)", 0xD1: "net reply (#80)"}
DEV_TAG = {0x35: "dbg", 0x4A: "isp", 0x50: "edid", 0x54: "scdc", 0x37: "ddc"}


INLINE_MAX = 8     # decoded log shows bytes of reads up to this size; longer ones are in <tool>.raw.log


def hx(b, limit: int = 48) -> str:
    s = " ".join("--" if x is None else f"{x:02x}" for x in b[:limit])
    return s + (f" ... ({len(b)} B)" if len(b) > limit else "")


def edid_info(b: bytes) -> str:
    if len(b) >= 128 and b[:8] == bytes.fromhex("00ffffffffffff00"):
        for i in range(54, 126, 18):
            if b[i:i + 3] == b"\0\0\0" and b[i + 3] == 0xFF:
                return " serial " + b[i + 5:i + 18].split(b"\n")[0].decode("latin-1").strip()
        return " header ok"
    return ""


# ---- decoder ---------------------------------------------------------------------------------------------------
class Decoder:
    """feed(Txn) ... flush(). emit(ts, tag, text) is called once per meaning; events may wait for coalescing."""

    def __init__(self, emit, syms: Symbols | None = None, regname=None, msgids: dict | None = None,
                 merge_pages: bool = False):
        self.emit, self.sym, self.msgids, self.merge_pages = emit, syms or Symbols(), msgids or {}, merge_pages
        self.regname = regname or (lambda a: None)
        self.ev = None
        self.d_hi = self.d_val = self.d_rd = None
        self.d_kind = "x"
        self.d_blk = None
        self.net_q = None                # #80 net exchange request waiting for its reply read
        self.msg_mode = False
        self.reg: dict[int, int] = {}
        self.f4 = self.page = None
        self.fifo = bytearray()
        self.isp_on = False
        self.e_off = 0

    # -- plumbing
    def flush(self) -> None:
        ev, self.ev = self.ev, None
        if ev:
            self.emit(ev.ts, ev.tag, self._render(ev))

    def put(self, t: Txn, tag: str, text: str) -> None:
        self.flush()
        self.emit(t.ts, tag, text)

    def open(self, t: Txn, tag: str, kind: str, **kw) -> NS:
        self.flush()
        self.ev = NS(ts=t.ts, tag=tag, kind=kind, **kw)
        return self.ev

    def keep(self, *kinds: str) -> None:
        if self.ev and self.ev.kind not in kinds:
            self.flush()

    def feed(self, t: Txn) -> None:
        tag = DEV_TAG.get(t.dev, "i2c")
        if t.err or t.data is None:
            self.put(t, tag, f"{'write' if t.kind == 'w' else 'read'} reg 0x{t.sub:02X} FAILED ({t.err})")
            return
        if t.blocked:
            self.put(t, tag, f"BLOCKED (not sent) write reg 0x{t.sub:02X} {hx(t.data)}")
            return
        {0x35: self._dbg, 0x4A: self._isp, 0x50: self._edid, 0x54: self._scdc, 0x37: self._ddc}.get(t.dev, self._other)(t)

    def feed_raw_line(self, line: str) -> bool:
        t = parse_raw(line)
        if t:
            self.feed(t)
        return t is not None

    def _other(self, t: Txn) -> None:
        self.put(t, "i2c", f"dev 0x{t.dev:02X} {'write' if t.kind == 'w' else 'read'} reg 0x{t.sub:02X} {hx(t.data)}")

    # -- naming
    def _xname(self, a: int) -> str:
        n = self.sym.name(a) or self.regname(a)
        return f"  {n}" if n else ""

    def _timing_note(self, e, lo: int, n: int) -> str:
        """Reads of the input timing / active-region count: decoded, exact frequency once both are seen (#34)."""
        if e.kind != "dr" or e.what != "x" or None in e.vals:
            return ""
        b = bytes(e.vals)
        if lo == self.sym.base("g_stMDomainInputData") and n >= 17:
            self.last_timing = decode_timing(b)
            t = self.last_timing
            return f"  = {t['hwidth']}x{t['vheight']} htotal {t['htotal']} vtotal {t['vtotal']} (SDK {t['vfreq'] / 10:.1f} Hz)"
        if lo == self.sym.base("g_ulInputActiveRegionBackUp") and n == 4:
            cnt = int.from_bytes(b, "big")
            x = exact_timing(self.last_timing, cnt) if getattr(self, "last_timing", None) else None
            return f"  = count {cnt}" + (f" -> {fmt_timing(self.last_timing, x)}" if x else "")
        return ""

    # -- rendering of coalesced events
    def _render(self, e) -> str:
        k = e.kind
        if k in ("dr", "dw"):
            w = "read" if k == "dr" else "write"
            what = {"x": "XDATA", "s": "scaler reg", "e": "EEPROM"}[e.what]
            n, lo = len(e.vals), e.start
            if n == 1:
                v = e.vals[0]
                note = self.sym.value_note(lo, v, k == "dw") if v is not None and e.what == "x" else ""
                arrow = "=" if k == "dr" else "<-"
                vs = "--" if v is None else f"0x{v:02X}"
                return f"{w} {what} 0x{lo:04X} {arrow} {vs}{note}{self._xname(lo) if e.what == 'x' else ''}"
            hi = lo + n - 1
            nm = self.sym.range_name(lo, hi) or self.regname(lo) or ""
            vals = f"{':' if k == 'dr' else ' <-'} {hx(e.vals)}" if n <= INLINE_MAX else ""   # longer: .raw.log + tool's decode
            return f"{w} {what} 0x{lo:04X}..0x{hi:04X} ({n} B){'  ' + nm if nm else ''}{vals}{self._timing_note(e, lo, n)}"
        if k == "msg":
            text = bytes(e.text)
            if not text and e.val is None:              # header not seen by the decoder: the tool's own line follows
                return "message fetch"
            if text[:1] == b"\x01" and len(text) >= 3:
                mid = int.from_bytes(text[1:3], "big")
                loc, txt = self.msgids.get(mid, (None, None))
                label = f"{loc} {txt}" if loc else f"#{mid}"
            else:
                label = "".join(chr(c) if 32 <= c < 127 else f"\\x{c:02x}" for c in text)
            val = "?" if e.val is None else str(e.val)
            return f'message "{label}" = {val}{"" if e.ok else "  (checksum mismatch)"}'
        if k == "rr":
            return f"read reg 0x{e.sub:02X} ({len(e.vals)} B)" + (f": {hx(e.vals)}" if len(e.vals) <= INLINE_MAX else "")
        if k == "net":
            x = [f"{e.full} full" if e.full else "", f"{e.bad} bad/retried" if e.bad else "", f"{e.reset} reset" if e.reset else "",
                 "echo mode" if e.ctl & 1 else ""]
            return (f"net {'0x3D' if e.tr == 'B' else 'DDC/CI D0'}: {e.n} exchange(s), out {e.o} B, in {e.i} B"
                    + "".join(f", {s}" for s in x if s))
        if k == "mpoll":
            return f"message channel status: {'message pending' if e.st == 0xF1 else 'none'}" + (f" (x{e.n})" if e.n > 1 else "")
        if k == "edid":
            return f"read 0x{e.start:02X}..0x{e.start + len(e.buf) - 1:02X} ({len(e.buf)} B){edid_info(bytes(e.buf)) if e.start == 0 else ''}"
        if k == "sw":
            r = self._reg16(e.page, e.idx)
            if len(e.vals) == 1:
                return f"scaler write {r} <- 0x{e.vals[0]:02X}{self._rname(e.page, e.idx)}"
            return f"scaler write {r} <- {len(e.vals)} B: {hx(e.vals)}{self._rname(e.page, e.idx)}"
        if k == "sr":
            r0 = self._reg16(*e.regs[0][:2])
            vals = [x[2] for x in e.regs]
            if len(vals) == 1:
                return f"scaler read {r0} = 0x{vals[0]:02X}{self._rname(*e.regs[0][:2])}"
            if all(x[:2] == e.regs[0][:2] for x in e.regs):
                return f"scaler read {r0} = 0x{vals[-1]:02X} (x{len(vals)} polls){self._rname(*e.regs[0][:2])}"
            r1 = self._reg16(*e.regs[-1][:2])
            return f"scaler read {r0}..{r1} ({len(vals)} B): {hx(vals, 32)}"
        if k == "ir":
            return (f"read ISP 0x{e.reg:02X} {ISP_REGS.get(e.reg, '')} = 0x{e.val:02X}" + (f" (x{e.n} polls)" if e.n > 1 else "")).replace("  ", " ")
        if k == "enter":
            ok = {None: "", True: " (0x6F reads back enabled)", False: " (0x6F did NOT read back enabled)"}[e.ok]
            return f"enter ISP: 0x6F <- 0x{e.v:02X}{ok}"
        if k == "opcfg":
            if list(e.ops) == ["PP"]:
                return f"program setup: PP opcode 0x{e.ops['PP']:02X}"
            return "SPI opcodes: " + " ".join(f"{n}=0x{v:02X}" for n, v in e.ops.items())
        if k == "crc":
            res = "result not read" if e.res is None else f"= 0x{e.res:02X}"
            return f"CRC 0x{e.start:05X}-0x{e.end:05X} {res}"
        if k == "prog":
            if e.pages == 1:
                return f"program page 0x{e.start:05X} ({e.bytes} B)"
            return f"program 0x{e.start:05X}..0x{e.end - 1:05X} ({e.pages} pages, {e.bytes} B)"
        if k == "flr":
            if not e.n:
                return f"SPI READ cmd @0x{e.start:05X} (no data read)"
            return f"read flash 0x{e.start:05X}..0x{e.start + e.n - 1:05X} ({e.n} B)"
        if k == "cmd":
            return self._render_cmd(e)
        if k == "ddc":
            return e.text
        return str(e)

    def _reg16(self, page, idx) -> str:
        return f"0x{page:02X}{idx:02X}" if page is not None else f"0x??{idx:02X}"

    def _rname(self, page, idx) -> str:
        if page is None:
            return ""
        a = (page << 8) | idx
        n = self.sym.name(a) or self.regname(a)
        return f"  {n}" if n else ""

    def _render_cmd(self, e) -> str:
        op, typ, a = e.op, e.typ, e.addr
        name = SPI_OPS.get(op, f"op 0x{op:02X}")
        res = [e.res[r] for r in (0x67, 0x68, 0x69) if r in e.res]
        if op == 0x01 and e.ctl == 0x71 and e.r64 == 0x06:
            return "SPI WREN"
        if op == 0x01 and e.nw == 1:
            return f"SPI WRSR 0x{e.r64:02X}"
        if op == 0x20:
            return f"erase sector 0x{a:05X} (4 KiB)"
        if op in (0xD8, 0x52) or typ == 5:
            return f"{name.replace('block erase', 'erase block')} @0x{a:05X}"
        if op in (0xC7, 0x60):
            return "erase chip"
        if op == 0x05 and res:
            return f"SPI RDSR = 0x{res[0]:02X}"
        if res:
            return f"SPI {name} = {' '.join(f'{x:02X}' for x in res)}"
        return f"SPI {name} (ctl 0x{e.ctl:02X}{', no result read' if e.nr else ''})"

    # -- 0x35 debug slave
    def _dbg(self, t: Txn) -> None:
        s, d = t.sub, t.data
        if t.kind == "r":
            return self._dbg_read(t)
        if s in (0x01, 0x02) and d:
            self.d_hi = d[0]; return
        if s in (0x03, 0x06) and d:
            self.d_val = d[0]; return
        if s in (0x04, 0x05, 0x0F) and not d:
            return
        if s == 0x3A and d:
            self.d_rd, self.d_kind = (self.d_hi or 0) << 8 | d[0], "x"; return
        if s == 0x3C and len(d) == 4:                          # block read: lo, hi, len, seq; read of len data + checksum follows
            self.d_rd, self.d_kind, self.d_blk = d[1] << 8 | d[0], "x", d[2]; return
        if s == 0x3D and len(d) >= 4:                          # #80 net: seq ctl ack data chk; fixed 25 B reply read follows
            self.net_q = d; return
        if s == 0x41 and d:
            self.d_rd, self.d_kind = d[0], "s"; return
        if s in (0x44, 0x45) and d:
            self.d_rd, self.d_kind = d[0], "e"; return
        if s == 0x3B and d:
            return self._dbg_write(t, (self.d_hi or 0) << 8 | d[0], self.d_val)
        if s == 0x80 and d:
            return self.put(t, "dbg", "halt main loop (0x80 <- 1)" if d[0] else "resume main loop (0x80 <- 0)")
        if s in (0x55, 0x20):
            self.msg_mode = True
            return self.put(t, "dbg", "message channel: enable")
        if s == 0x2F:
            self.msg_mode = False
            return self.put(t, "dbg", "message channel: stop")
        if s == 0x25:
            k = d[0] if d else 0
            if k == 0 or not (self.ev and self.ev.kind == "msg"):
                self.open(t, "dbg", "msg", text=bytearray(), val=None, ok=True, expect=k, hdr=None)
            else:
                self.ev.expect = k
            return
        if s == 0x2A:
            if self.ev and self.ev.kind == "msg":
                self.flush()
            else:
                self.put(t, "dbg", "message end (releases firmware)")
            return
        if (s & 0x0F) == 0 and s not in (0x80, 0x20) and d:     # ScalerSetByte(page<<8 | staged lo, d[0])
            lo = self.d_hi or 0
            if lo == 0x9F:
                return self.put(t, "dbg", f"select scaler page 0x{d[0]:02X}")
            return self.put(t, "dbg", f"write scaler reg 0x??{lo:02X} <- 0x{d[0]:02X} (cmd 0x{s:02X}, current page)")
        self.put(t, "dbg", f"cmd 0x{s:02X} {DBG_CMDS.get(s, '?')} {hx(d)}")

    def _dbg_write(self, t: Txn, addr: int, v) -> None:
        if addr == 0x009F and v is not None:
            return self.put(t, "dbg", f"select scaler page 0x{v:02X}")
        e = self.ev
        if e and e.kind == "dw" and addr == e.start + len(e.vals):
            e.vals.append(v)
        else:
            self.open(t, "dbg", "dw", what="x", start=addr, vals=[v])

    def _dbg_read(self, t: Txn) -> None:
        d = t.data
        e = self.ev
        if t.sub == 0x08 and e and e.kind == "msg":
            return self._msg_data(t, e)
        if t.sub == 0x08 and self.net_q is not None and len(d) == 25:
            q, self.net_q = self.net_q, None
            ok = (0x3D + sum(d[:24])) & 0xFF == d[24] and d[0] == q[0]
            return self._net(t, "B", q[1], len(q) - 4, d[1] if ok else None, min(d[3], 20) if ok else 0)
        if t.sub == 0x08 and self.d_rd is not None and len(d) >= 1:
            a, kind, self.d_rd = self.d_rd, self.d_kind, None
            n = self.d_blk if self.d_blk else 1                # block read: len data bytes (the checksum byte is dropped)
            self.d_blk = None
            if e and e.kind == "dr" and e.what == kind and a == e.start + len(e.vals):
                e.vals.extend(d[:n])
            else:
                self.open(t, "dbg", "dr", what=kind, start=a, vals=list(d[:n]))
            return
        if t.sub == 0x08 and len(d) == 1 and d[0] in (0xFC, 0xF1) and (self.msg_mode or d[0] == 0xF1):
            if e and e.kind == "mpoll" and e.st == d[0]:
                e.n += 1
            else:
                self.open(t, "dbg", "mpoll", st=d[0], n=1)
            return
        if t.sub == 0x08 and self.msg_mode:             # message payload: the tool logs the decoded message line;
            return                                      # bytes stay in the .raw.log
        if e and e.kind == "rr" and e.sub == t.sub:
            e.vals += d
        else:
            self.open(t, "dbg", "rr", sub=t.sub, vals=bytearray(d))

    def _msg_data(self, t: Txn, e) -> None:
        d = t.data
        if e.expect == 0:                                  # header: FA F5 len v3 v2 v1 v0 c1 c2
            if len(d) >= 8 and d[0] == 0xFA and d[1] == 0xF5:
                e.hdr, e.val = d, int.from_bytes(d[3:7], "big")
            e.expect = None
        elif e.expect is not None and len(d) >= 1:         # chunk k: text + checksum (k + 0x0F + sum)
            txt = d[:-1]
            e.text += txt
            e.ok &= (e.expect + 0x0F + sum(txt)) & 0xFF == d[-1]
            e.expect = None
        elif not self.msg_mode:
            self.flush(); self.put(t, "dbg", f"read reg 0x{t.sub:02X} ({len(d)} B) {hx(d)}")

    # -- 0x4A ISP slave
    def _isp(self, t: Txn) -> None:
        s, d = t.sub, t.data
        if t.kind == "r":
            return self._isp_read(t)
        if s == 0x70:
            self.keep("prog")
            self.fifo += d
            return
        for i, v in enumerate(d):
            self._isp_w(t, (s + i) & 0xFF, v)
        if not d:
            self.put(t, "isp", f"write reg 0x{s:02X} (no data)")

    def _isp_w(self, t: Txn, r: int, v: int) -> None:
        old = self.reg.get(r)
        self.reg[r] = v
        if r == 0xF4:
            self.f4 = v; self.keep("sr", "sw"); return
        if r == 0xF5:
            return self._sc_write(t, v)
        if r == 0xEE:
            self.isp_on = False
            return self.put(t, "isp", f"reset 0xEE <- 0x{v:02X} (scaler MCU reboots)")
        if r == 0x6F:
            return self._isp_ctl(t, v)
        if r in OPCFG:
            e = self.ev
            if e and e.kind == "opcfg":
                e.ops[OPCFG[r]] = v
            else:
                self.open(t, "isp", "opcfg", ops={OPCFG[r]: v})
            return
        if r in ENG:
            self.keep("flr", "prog")
            if r == 0x60 and v & 1:
                self._go(t, v)
            return
        self.put(t, "isp", f"write ISP 0x{r:02X} {ISP_REGS.get(r, '')} <- 0x{v:02X}".replace("  ", " "))

    def _a24(self) -> int:
        return (self.reg.get(0x64, 0) << 16) | (self.reg.get(0x65, 0) << 8) | self.reg.get(0x66, 0)

    def _go(self, t: Txn, ctl: int) -> None:
        op, a = self.reg.get(0x61, 0), self._a24()
        typ, nw, nr = (ctl >> 5) & 7, (ctl >> 3) & 3, (ctl >> 1) & 3
        e = self.ev
        if op == 0x03 and typ == 2:
            if e and e.kind == "flr" and a == e.start + e.n:
                return
            self.open(t, "isp", "flr", start=a, n=0)
            return
        self.open(t, "isp", "cmd", ctl=ctl, op=op, typ=typ, nw=nw, nr=nr, addr=a, r64=self.reg.get(0x64, 0), res={})

    def _isp_ctl(self, t: Txn, v: int) -> None:
        if v & 0x80 and v & 0x04:
            self.open(t, "isp", "crc", start=self._a24(),
                      end=(self.reg.get(0x72, 0) << 16) | (self.reg.get(0x73, 0) << 8) | self.reg.get(0x74, 0), res=None)
        elif v & 0x20:
            if self.ev and self.ev.kind == "ir" and self.ev.reg == 0x6F:
                self.ev = None                                   # buffer-ready polls in front of the start
            a, n, e = self._a24(), len(self.fifo), self.ev
            self.fifo.clear()
            if self.merge_pages and e and e.kind == "prog" and a == e.end:
                e.end, e.pages, e.bytes = a + 256, e.pages + 1, e.bytes + n
            else:
                self.open(t, "isp", "prog", start=a, end=a + 256, pages=1, bytes=n)
        elif v & 0x80 and not self.isp_on:
            self.isp_on = True
            self.open(t, "isp", "enter", v=v, ok=None)
        else:
            if not v & 0x80:
                self.isp_on = False
            self.put(t, "isp", f"write ISP 0x6F ISP_CTL <- 0x{v:02X}" + ("  (leave ISP)" if not v & 0x80 else ""))

    def _isp_read(self, t: Txn) -> None:
        s, d = t.sub, t.data
        e = self.ev
        if s == 0x70:
            if e and e.kind == "flr":
                e.n += len(d)
            else:
                self.put(t, "isp", f"read FIFO 0x70 ({len(d)} B)")
            return
        for i, v in enumerate(d):
            r = (s + i) & 0xFF
            e = self.ev
            if r == 0x60 and e and e.kind in ("cmd", "flr"):
                continue
            if r in (0x67, 0x68, 0x69) and e and e.kind == "cmd":
                e.res[r] = v; continue
            if r == 0x75 and e and e.kind == "crc":
                e.res = v; self.flush(); continue
            if r == 0x6F and e and e.kind in ("prog", "crc"):
                continue
            if r == 0x6F and e and e.kind == "enter" and e.ok is None:
                e.ok = bool(v & 0x80); continue
            if r == 0xF5:
                self._sc_read(t, v); continue
            if e and e.kind == "ir" and e.reg == r:
                e.n += 1; e.val = v
            else:
                self.open(t, "isp", "ir", reg=r, val=v, n=1)

    def _sc_write(self, t: Txn, v: int) -> None:
        if self.f4 == 0x9F:
            if v != self.page:
                self.page = v
                self.put(t, "isp", f"select scaler page 0x{v:02X}")
            return
        e = self.ev
        if e and e.kind == "sw" and (e.page, e.idx) == (self.page, self.f4):
            e.vals.append(v)
        else:
            self.open(t, "isp", "sw", page=self.page, idx=self.f4, vals=[v])

    def _sc_read(self, t: Txn, v: int) -> None:
        key = (self.page, self.f4, v)
        e = self.ev
        if e and e.kind == "sr":
            p, i, _ = e.regs[-1]
            if (p, i) == key[:2] or (p == self.page and p is not None and self.f4 == i + 1):
                e.regs.append(key); return
        self.open(t, "isp", "sr", regs=[key])

    # -- 0x50 EDID
    def _edid(self, t: Txn) -> None:
        if t.kind == "w":
            if t.data:
                return self.put(t, "edid", f"write 0x{t.sub:02X} {hx(t.data)}")
            self.e_off = t.sub
            return
        e = self.ev
        off = t.sub if t.sub else self.e_off
        if e and e.kind == "edid" and off == e.start + len(e.buf):
            e.buf += t.data
        else:
            self.open(t, "edid", "edid", start=off, buf=bytearray(t.data))
        self.e_off = off + len(t.data)

    # -- 0x54 SCDC
    def _scdc(self, t: Txn) -> None:
        s, d = t.sub, t.data
        nm = lambda r: SCDC_REGS.get(r, "")
        if t.kind == "r":
            parts = " ".join(f"{(nm(s + i) or f'0x{s + i:02X}')}=0x{v:02X}" for i, v in enumerate(d[:8]))
            return self.put(t, "scdc", f"read 0x{s:02X} ({len(d)} B): {parts}{' ...' if len(d) > 8 else ''}")
        self.put(t, "scdc", f"write 0x{s:02X} {nm(s)} <- {hx(d)}")

    # -- 0x37 DDC/CI
    def _ddc(self, t: Txn) -> None:
        d = t.data
        vn = lambda c: f"0x{c:02X} {VCP.get(c, '')}".strip()
        if t.kind == "w" and t.sub == 0x51 and len(d) >= 2 and d[0] & 0x80:
            op, a = d[1], d[2:-1]
            if op == 0x01 and a:
                self.open(t, "ddc", "ddc", text=f"get VCP {vn(a[0])} (no reply read)", code=a[0])
            elif op == 0x03 and len(a) >= 3:
                self.put(t, "ddc", f"set VCP {vn(a[0])} = {a[1] << 8 | a[2]}")
            elif op == 0xD0 and len(a) >= 3:                  # #80 net: seq ctl ack data
                self.net_q = a
            else:
                self.put(t, "ddc", f"{DDC_OPS.get(op, f'op 0x{op:02X}')} {hx(a)}")
            return
        if t.kind == "r" and len(d) >= 3 and d[0] == 0x6E and d[1] & 0x80:
            op, a = d[2], d[3:-1]
            if op == 0x02 and len(a) >= 7:
                res, code, mx, cur = a[0], a[1], a[3] << 8 | a[4], a[5] << 8 | a[6]
                txt = (f"get VCP {vn(code)} = {cur} (max {mx})" if res == 0 else
                       f"get VCP {vn(code)} -> result 0x{res:02X} ({'unsupported' if res == 1 else 'error'})")
                if self.ev and self.ev.kind == "ddc":
                    self.ev = None
                return self.put(t, "ddc", txt)
            if op == 0xD1 and len(a) >= 3 and self.net_q is not None:
                q, self.net_q = self.net_q, None
                return self._net(t, "A", q[1], len(q) - 3, a[1] if a[0] == q[0] else None, len(a) - 3)
            return self.put(t, "ddc", f"{DDC_OPS.get(op, f'op 0x{op:02X}')} {hx(a)}")
        self.put(t, "ddc", f"{'write' if t.kind == 'w' else 'read'} reg 0x{t.sub:02X} {hx(d)}")

    def _net(self, t: Txn, tr: str, ctl: int, n_out: int, flags, n_in: int) -> None:
        """#80 exchanges coalesce into one line per run: count, bytes each way, retries / full / reset seen."""
        e = self.ev
        if not (e and e.kind == "net" and e.tr == tr):
            e = self.open(t, "dbg" if tr == "B" else "ddc", "net", tr=tr, n=0, o=0, i=0, bad=0, full=0, reset=0, ctl=ctl)
        e.n += 1
        if flags is None:
            e.bad += 1; return
        e.bad += bool(flags & 0x04); e.full += bool(flags & 0x02); e.reset += bool(flags & 0x08)
        e.o += n_out if flags & 0x01 else 0
        e.i += n_in if flags & 0x03 else 0


# ---- logging API -----------------------------------------------------------------------------------------------
class LogFile:
    """File-like main log: flushes the decoder first so tool lines and decoded lines stay in order."""

    def __init__(self, f, dec):
        self.f, self.dec = f, dec

    def write(self, s: str) -> int:
        self.dec.flush()
        return self.f.write(s)

    def flush(self) -> None:
        self.dec.flush(); self.f.flush()

    def close(self) -> None:
        self.flush(); self.f.close()


class Logs:
    def __init__(self, main: LogFile, raw, dec: Decoder, tap):
        self.main, self.raw, self.dec, self.tap = main, raw, dec, tap

    def log(self, s: str) -> None:
        self.main.write(f"{now()} {s}\n"); self.main.f.flush()

    def close(self) -> None:
        if self.tap in TAPS:
            TAPS.remove(self.tap)
        self.main.flush()
        if self.raw:
            self.raw.close()


def setup_logs(name: str, map=None, raw: bool | None = None, merge_pages: bool = False, chip: str = "RTD2795T-CG",
               root: Path | None = None, detail: bool = False, diagnostics=None) -> Logs:
    """Decoded lines + the tool's own lines -> tmp/logs/<name>.log; byte trace -> <name>.raw.log.
    raw=None: on unless $AWTO_RAW_TRACE=0 (flash tools pass raw=False: ~1M lines per image). Replaces earlier taps.
    detail=True: decoded protocol lines go to <name>.detail.log; the main log keeps the tool's own lines only.
    diagnostics: best-effort sinks for flash sessions; opening still fails before ISP."""
    root = root or repo_root()
    d = root / "tmp/logs"
    d.mkdir(parents=True, exist_ok=True)
    open_log = diagnostics.open if diagnostics is not None else lambda path: path.open("a")
    f = open_log(d / f"{name}.log")
    df = open_log(d / f"{name}.detail.log") if detail else f
    if raw is None:
        raw = os.environ.get("AWTO_RAW_TRACE") != "0"
    rf = open_log(d / f"{name}.raw.log") if raw else None
    dec = Decoder(lambda ts, tag, text: df.write(f"{ts} {tag:<4} {text}\n"), Symbols.load(root, map), regdb_namer(chip),
                  load_msgids(root), merge_pages)
    err = []

    def tap(t: Txn) -> None:
        if rf:
            rf.write(f"{t.ts} {raw_line(t)}\n")
        try:
            dec.feed(t)
        except Exception as e:                       # a decoder bug must never break a tool
            if not err:
                err.append(e); f.write(f"{t.ts} proto decoder error: {e!r}\n")

    TAPS.clear()
    TAPS.append(tap)
    lg = Logs(LogFile(f, dec), rf, dec, tap)
    lg.detail = LogFile(df, dec)

    def done():
        try:
            lg.main.flush()
            lg.detail.flush()
            if rf:
                rf.flush()
        except ValueError:
            pass
    atexit.register(done)
    return lg
