#!/usr/bin/env python3
"""FastMachine: fw_sim.Machine on an in-process 8051 core (scripts/mcs51_core.c via ctypes) instead of the ucsim subprocess.

Select:
- env `AWTO_SIM_CORE=fast` -> fw_sim.Machine is FastMachine (SimBus, osd_render, sim_live, gpio_shot, tests unchanged)
- `fw_sim.py --fast ...` (boot-check / video-check / ddr-trace); default stays ucsim
- library: `fastmachine.FastMachine(img, map_path, tag, log, devs)`, same arguments as fw_sim.Machine
Core (mcs51_core.c):
- ucsim 0.9.12 -t 52 semantics: cycle counts, timers 0/1/2, IRQ poll order + 2 levels, no IRQ after RETI / IE write
- code bank = XDATA 0xFFFF low nibble (as fw_sim's ucsim banker); built on first use into tmp/mcs51_core.so (gcc)
- Dev hooks: bitmap per XDATA/SFR address, handled after the accessing instruction (+ IRQ entry), as ucsim event stops
- stubs: PC hooks (core supports per-bank masks; stub() sets all banks like ucsim); no host round trip otherwise
API differences vs Machine:
- instr / run(n) budget: Machine's accounting (each stop uses max(1, ticks / TICKS_PER_INSTR)), so instruction budgets
  mean the same firmware time on both cores; real count = .p.instr; bind(S, exact=True): real counts (lockstep tests)
- puts run immediately (flush is a no-op); ucsim command subset only: set memory/bit, pc, fill, break/tbreak/delete,
  info breakpoints; anything else raises SimError
- start state: XDATA zero (as Machine), IRAM = ucsim's fixed power-on pattern (ucsim_iram), SFRs as ucsim reset
- a stub PC right after an event stop is still hooked (ucsim skips the breakpoint check on the first step instruction)
Not modelled (both cores, or ucsim only): serial port (SCON/SBUF writes counted in .p.serial_wr), PCON idle/power-down,
  0xA5 (run stops: "invalid instruction"); a bank number >= image banks keeps the old code bank
Stay on ucsim: fw_sim --isr-check, --serial (raw ucsim sessions, not Machine)
Verification: scripts/fastcore_check.py (differential vs ucsim + fw_sim gates), log tmp/logs/fastcore_check.log.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CPU_MODES = ("dw8051", "8052")
MODEL_JSON = HERE / "dw8051_model.json"


def cpu_mode() -> str:
    """AWTO_SIM_CPU (set by --cpu): dw8051 (default; gates, sim_live, tests) or 8052 (ucsim -t 52 compatible: classic 12-clock cycles)."""
    m = os.environ.get("AWTO_SIM_CPU", "dw8051")
    if m not in CPU_MODES:
        raise SystemExit(f"AWTO_SIM_CPU={m!r}: want one of {CPU_MODES}")
    return m
sys.path.insert(0, str(HERE))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
SRC = HERE / "mcs51_core.c"
SO = ROOT / "tmp/mcs51_core.so"
BANK = 0x10000
R_DONE, R_EVENT, R_PC, R_BADOP = 0, 1, 2, 3
EV_KIND = ("read", "write", "sread", "swrite")
EV_SW = 3                   # EV_KIND index of an SFR write
GCC_TIMEOUT_S = 60          # gcc -O2 of one 600-line file: < 2 s; 60 s = project host-process stall limit


class Pub(ctypes.Structure):
    _fields_ = [("instr", ctypes.c_uint64), ("cycles", ctypes.c_uint64), ("nirq", ctypes.c_uint64),
                ("pc", ctypes.c_uint32), ("bank", ctypes.c_uint32), ("nev", ctypes.c_uint32), ("skip_pc", ctypes.c_uint32),
                ("ev", ctypes.c_uint32 * 16), ("reason", ctypes.c_uint32), ("bad_op", ctypes.c_uint32),
                ("nbanks", ctypes.c_uint32), ("nlvl", ctypes.c_uint32), ("serial_wr", ctypes.c_uint64),
                ("irq_tail", ctypes.c_uint32), ("_pad", ctypes.c_uint32),
                ("clk", ctypes.c_uint64), ("fm_miss", ctypes.c_uint64), ("fm_stall", ctypes.c_uint64),
                ("dw", ctypes.c_uint32), ("max_instr_clk", ctypes.c_uint32)]


_LIB = None


def lib():
    """Load the core, compiling it into tmp/ when the .so is missing or older than the source."""
    global _LIB
    if _LIB is not None:
        return _LIB
    if not SO.exists() or SO.stat().st_mtime < SRC.stat().st_mtime:
        SO.parent.mkdir(parents=True, exist_ok=True)
        tmp = SO.with_name(f"{SO.name}.{os.getpid()}")
        subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(tmp), str(SRC)], check=True, timeout=GCC_TIMEOUT_S,
                       capture_output=True)
        os.replace(tmp, SO)                        # atomic: a concurrent build never loads half a file
    L = ctypes.CDLL(str(SO))
    vp = ctypes.c_void_p
    L.core_new.restype, L.core_new.argtypes = vp, [ctypes.c_char_p, ctypes.c_uint32]
    L.core_free.argtypes = [vp]
    L.core_reset.argtypes = [vp]
    L.core_pub.restype, L.core_pub.argtypes = ctypes.POINTER(Pub), [vp]
    L.core_mem.restype, L.core_mem.argtypes = vp, [vp, ctypes.c_int]
    L.core_pchooks.restype, L.core_pchooks.argtypes = vp, [vp]
    L.core_opcount.restype, L.core_opcount.argtypes = vp, [vp]
    L.core_set_bank.argtypes = [vp, ctypes.c_uint]
    L.core_sfr_write.argtypes = [vp, ctypes.c_int, ctypes.c_int]
    L.core_set_dw.argtypes = [vp, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    L.core_set_fetch.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
    L.core_set_fetch_ratio.argtypes = [vp, ctypes.c_uint32]
    L.core_level.restype, L.core_level.argtypes = ctypes.c_int, [vp, ctypes.c_int]
    L.core_run.restype, L.core_run.argtypes = ctypes.c_int, [vp, ctypes.c_uint64]
    _LIB = L
    return L


def ucsim_iram() -> bytes:
    """ucsim's power-on IRAM: bytes 256..511 of its urnd() stream (CMWC, core/utils.src/utils.cc, srnd(0) at start).
    Same in every ucsim run, so seeding it makes fast runs repeat ucsim's (code that reads IRAM before writing it)."""
    phi, m32 = 0x9E3779B9, 0xFFFFFFFF
    q = [0] * 4096
    q[0], q[1], q[2] = 0, phi, (2 * phi) & m32
    for i in range(3, 4096):
        q[i] = (q[i - 3] ^ q[i - 2] ^ phi ^ i) & m32
    c, i, out = 362436, 4095, bytearray()
    for _ in range(512):
        i = (i + 1) & 4095
        t = 18782 * q[i] + c
        c = t >> 32
        x = (t + c) & m32
        if x < c:
            x = (x + 1) & m32
            c += 1
        q[i] = (0xFFFFFFFE - x) & m32
        out.append(q[i] & 0xFF)
    return bytes(out[256:])


class Core:
    """Thin ctypes view of one core: memoryviews on IRAM / SFR (index addr - 0x80) / XDATA / code, PC hooks, hook bitmaps."""

    def __init__(self, img: bytes):
        self.L = L = lib()
        self.h = L.core_new(img, len(img))
        self.p = L.core_pub(self.h).contents
        mv = lambda sp, n, t=ctypes.c_uint8: memoryview((t * n).from_address(L.core_mem(self.h, sp))).cast("B")
        self.iram, self.sfr, self.xram = mv(0, 256), mv(1, 128), mv(2, 65536)
        self.code = mv(3, self.p.nbanks * BANK)
        self.hooks = mv(4, 4 * 8192)
        self.pch = memoryview((ctypes.c_uint16 * 65536).from_address(L.core_pchooks(self.h))).cast("B").cast("H")
        self.opcount = (ctypes.c_uint64 * 256).from_address(L.core_opcount(self.h))

    def set_dw(self, mdl: dict | None):
        """CPU timing mode: mdl = scripts/dw8051_model.json (DW8051, default) or None (8052: ucsim -t 52 classic cycles)."""
        if mdl is None:
            self.L.core_set_dw(self.h, 0, bytes(256), 0, 0, 0, 0, 0)
        else:
            td = mdl["timer_clk_div"]
            self.L.core_set_dw(self.h, 1, bytes(mdl["cycles"]), mdl["movx"]["base_cycles"], mdl["irq_cycles"], mdl["clk_per_cycle"],
                               td["slow"], td["fast"])

    def set_fetch(self, mdl: dict | None):
        """Flash code-fetch stall model (mdl["flash_fetch"]) or none."""
        if mdl is None:
            self.L.core_set_fetch(self.h, 0, 0, 0, 0, 0, 0, None)
        else:
            ff = mdl["flash_fetch"]
            sets = int(os.environ.get("AWTO_SIM_FETCH_SETS", ff["sets"]))      # sensitivity runs only; the default is the JSON
            self.L.core_set_fetch(self.h, ff["line_bytes"], sets, ff["ways"], ff["cmd_flash_clk"], ff["byte_flash_clk"],
                                  ff["common_end"], bytes(mdl["oplen"]))

    def reset(self):
        self.L.core_reset(self.h)

    def run(self, n: int) -> int:
        return self.L.core_run(self.h, n)

    def set_bank(self, b: int):
        self.L.core_set_bank(self.h, b)

    def sfr_write(self, a: int, v: int):
        self.L.core_sfr_write(self.h, a, v & 0xFF)

    def hook(self, kind: int, a: int, on: bool = True):
        i = kind * 8192 + (a >> 3)
        self.hooks[i] = (self.hooks[i] | (1 << (a & 7))) if on else (self.hooks[i] & ~(1 << (a & 7)))

    def regs(self) -> dict:
        s, rs = self.sfr, self.sfr[0x50] & 0x18
        return {"pc": self.p.pc, "acc": s[0x60], "b": s[0x70], "psw": s[0x50], "sp": s[0x01], "dptr": s[0x03] << 8 | s[0x02],
                "r": list(self.iram[rs:rs + 8]), "bank": self.p.bank}

    def free(self):
        if self.h:
            self.L.core_free(self.h)
            self.h = None


class _Shim:
    """m.s stand-in: scripts that send ucsim break commands (fw_sim_trace, delay_inventory) keep working."""

    def __init__(self, m):
        self.m = m

    def send(self, cmd: str):
        self.m.cmd(cmd)


_NUM = r"(0x[0-9a-fA-F]+|\d+)"


class FastMachine:
    """fw_sim.Machine API on Core. run(n) serves Dev events until n instructions ran, a non-stub breakpoint is hit,
    or a model calls request_stop()."""
    S = None                                   # fw_sim module this class is bound to (bind())
    EXACT = False                              # True: instr / run(n) count real instructions (lockstep tests)

    @classmethod
    def _S(cls):
        if cls.S is None:
            import fw_sim
            cls.S = fw_sim
        return cls.S

    def __init__(self, img: bytes, mapp: Path, tag: str, log=None, devs=(), extra_breaks=(), ncode: int | None = None,
                 ret_pc: int | None = None):
        S = self._S()
        self.img, self.devs, self.tag = img, list(devs), tag
        self.map_text = Path(mapp).read_text(errors="replace")
        self.sym, self.where = S.parse_map(self.map_text, img, ncode)
        self.log = log or S._Null()
        self.core = Core(img)
        self.cpu = cpu_mode()
        self.dw = self.cpu == "dw8051"
        self._avg_clk = 8.0                      # clk per instruction, last chunk (deadline caps)
        self.wall_ms = None                      # real time from the CPU clock model (dw8051 only); None = Timer2 cycle time
        self.clock = None
        if self.dw:
            import json
            from sim_clock import ClockModel
            mdl = json.loads(MODEL_JSON.read_text())
            self.core.set_dw(mdl)
            if os.environ.get("AWTO_SIM_FETCH", "on") != "off":      # off: no flash code-fetch stall (isolates the CPU / clock model)
                self.core.set_fetch(mdl)
            self.clock, self.wall_ms = ClockModel(), 0.0
            self.devs.append(self.clock)
        print(f"sim CPU model: {self.cpu}", file=sys.stderr) if not getattr(FastMachine, "_said", False) else None
        FastMachine._said = True
        self.core.reset()
        self.core.iram[:] = ucsim_iram()
        self.p = self.core.p
        self.ticks, self.instr, self._stop, self.last_out = 0, 0, False, ""
        self._tpi = S.TICKS_PER_INSTR
        self.stubs, self.stub_hits = {}, {}
        self.t2_scale, self._t2_set, self._t2_at = 1, -1, -10**9
        self.keil = ncode is not None or S.keil_abi(self.sym)
        self.ret_pc = ret_pc if ret_pc is not None else S.sw_ret(img, self.sym["__bs_call_sw"])
        self.hook, self._addr = {}, {}
        self._brk, self._nbrk, self._tbrk = {}, 0, set()          # break nr -> (kind, addr) ; temporary PC breaks
        self.s = _Shim(self)
        for v in extra_breaks:
            self.cmd(f"break 0x{v:x}")
        for d in self.devs:
            for a in d.reads:
                self.hook[("read", a)] = d
                self.cmd(f"break xram r 0x{a:x}")
            for a in d.writes:
                self.hook[("write", a)] = d
                self.cmd(f"break xram w 0x{a:x}")
        for d in self.devs:
            d.init(self)
        self._tickers = [d for d in self.devs if hasattr(d, "tick")]
        if self.dw:
            for a_ in self.clock.shared:
                self.core.hook(1, a_, True)            # EV_XW: clock registers another dev may also hook
        self.core.hook(EV_SW, 0xCB, True)              # RCAP2H write: dilate the new reload at once (#138: Timer0 follows RCAP2)

    # ---- ucsim command subset ----
    def cmd(self, text: str, timeout: float = 120) -> str:
        out = []
        for line in text.split("\n"):
            r = self._exec(line.strip())
            if r:
                out.append(r)
        return "\n".join(out)

    def put(self, c: str):
        self._exec(c.strip())

    def flush(self):
        pass

    def _exec(self, c: str) -> str:
        S = self._S()
        if not c or c.startswith("echo"):
            return ""
        w = c.split()
        if w[0] == "set" and len(w) >= 4 and w[1] == "memory":
            self.wr(int(w[3], 0), bytes(int(x, 0) & 0xFF for x in w[4:]), w[2])
            return ""
        if w[0] == "set" and len(w) == 4 and w[1] == "bit":
            self._set_bit(int(w[2], 0), int(w[3], 0))
            return ""
        if w[0] == "pc" and len(w) == 2:
            self.p.pc = int(w[1], 0) & 0xFFFF
            return ""
        if w[0] == "fill" and len(w) == 5:
            a, b, v = int(w[2], 0), int(w[3], 0), int(w[4], 0)
            self.wr(a, bytes([v & 0xFF]) * (b - a + 1), w[1])
            return ""
        if w[0] in ("break", "tbreak"):
            if len(w) == 4 and w[1] in ("xram", "sfr") and w[2] in ("r", "w"):
                kind = (0 if w[2] == "r" else 1) + (2 if w[1] == "sfr" else 0)
                return self._add_brk((kind, int(w[3], 0)))
            if len(w) == 2:
                pc = int(w[1], 0) & 0xFFFF
                self.core.pch[pc] = 0xFFFF
                if w[0] == "tbreak":
                    self._tbrk.add(pc)
                return self._add_brk(("pc", pc))
        if w[0] == "delete" and len(w) == 2:
            k = self._brk.pop(int(w[1]), None)
            if k and k[0] != "pc" and k not in self._brk.values():
                self.core.hook(k[0], k[1], False)
            return ""
        if c == "info breakpoints":
            rows = ["Num Type       Disp Hit   Cnt   Address  What"]
            for n, (k, a) in sorted(self._brk.items()):
                if k == "pc":
                    rows.append(f"{n:<3} fetch      keep 1     1     0x{a:06x}")
                else:
                    rows.append(f"{n:<3} event      keep 1     1     0x{a:06x} {EV_KIND[k][-5:] if k < 2 else EV_KIND[k][1:]}")
            return "\n".join(rows)
        if c == "reset":
            self.core.reset()
            return ""
        raise S.SimError(f"fast core: unsupported ucsim command `{c[:60]}`")

    def _add_brk(self, key) -> str:
        if key[0] != "pc":
            self.core.hook(key[0], key[1], True)
        self._nbrk += 1
        self._brk[self._nbrk] = key
        return ""

    def _set_bit(self, b: int, v: int):
        a = 0x20 + (b >> 3) if b < 0x80 else b & 0xF8
        m = 1 << (b & 7)
        if a < 0x80:
            self.core.iram[a] = (self.core.iram[a] | m) if v else (self.core.iram[a] & ~m)
        else:
            x = self.core.sfr[a - 0x80]
            self.core.sfr_write(a, (x | m) if v else (x & ~m))

    # ---- memory ----
    def addr(self, name: str) -> int:
        """XDATA address of a global (16-bit, from the map); cached (the map is MBs, Machine re-searches each call)."""
        a = self._addr.get(name)
        if a is None:
            mt = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", self.map_text)
            if not mt:
                raise self._S().SimError(f"_{name} not in the map")
            a = self._addr[name] = int(mt.group(1), 16) & 0xFFFF
        return a

    def rd(self, a: int, n: int = 1, space: str = "xram") -> bytes:
        c = self.core
        if space == "xram":
            if a + n > 0x10000:
                raise self._S().SimError(f"rd xram 0x{a:x}+{n} out of range")
            return bytes(c.xram[a:a + n])
        if space == "iram":
            return bytes(c.iram[a:a + n])
        if space == "sfr":
            return bytes(c.sfr[a - 0x80:a - 0x80 + n])
        if space in ("rom", "code"):
            base = c.p.bank * BANK if c.p.bank < c.p.nbanks else 0
            return bytes(c.code[base + a:base + a + n])
        if space == "flash":
            return bytes(c.code[a:a + n])
        raise self._S().SimError(f"rd: unknown space {space}")

    def wr(self, a: int, data: bytes, space: str = "xram"):
        c, n = self.core, len(data)
        if space == "xram":
            c.xram[a:a + n] = bytes(data)
            if a <= 0xFFFF < a + n:
                c.set_bank(data[0xFFFF - a] & 0x0F)
        elif space == "iram":
            c.iram[a:a + n] = bytes(data)
        elif space == "sfr":
            for i, v in enumerate(data):
                c.sfr_write(a + i, v)
        elif space in ("flash", "rom"):
            base = 0 if space == "flash" else c.p.bank * BANK
            c.code[base + a:base + a + n] = bytes(data)
        else:
            raise self._S().SimError(f"wr: unknown space {space}")

    def request_stop(self):
        self._stop = True

    # ---- stubs ----
    def stub(self, name: str, fn):
        """As Machine.stub. PC hook in every bank, bank filtered in _do_stub, as ucsim's bank-blind breakpoint: each stop
        splits a run() and so changes how many instructions run(n) executes (Machine accounting)."""
        v = self.sym.get("_" + name)
        if v is None:
            raise self._S().SimError(f"_{name} not in the map")
        bank, pc = v >> 16, v & 0xFFFF
        common = v < getattr(self.where, "cend", 0)
        self.stubs.setdefault(pc, []).append((None if common else bank, name, fn))
        self.core.pch[pc] = 0xFFFF

    def watch(self, name: str):
        self.stub(name, lambda m, r: None)

    def patch_const(self, name: str, carry: int):
        v = self.sym.get("_" + name)
        if v is None:
            raise self._S().SimError(f"_{name} not in the map")
        bank, pc = v >> 16, v & 0xFFFF
        common = v < getattr(self.where, "cend", 0)
        code = bytes((0xD3 if carry else 0xC3, 0x22))
        for b in (range(self.core.p.nbanks) if common else (bank,)):
            self.core.code[b * BANK + pc:b * BANK + pc + 2] = code
        self.patched = getattr(self, "patched", []) + [name]

    def _do_stub(self, pc: int):
        c = self.core
        bank = c.xram[0xFFFF] & 15
        hit = [(n, f) for b, n, f in self.stubs[pc] if b is None or b == bank]
        if not hit:
            return
        name, fn = hit[0]
        g = c.regs()
        regs = {"acc": g["acc"], "b": g["b"], "r": g["r"], "dptr": g["dptr"]}
        r = regs["r"]
        regs["a1"], regs["a2"] = (r[6] << 8 | r[7], r[5]) if self.keil else (regs["dptr"], r[7])
        ret = fn(self, regs)
        self.stub_hits[name] = self.stub_hits.get(name, 0) + 1
        if ret is None:
            return
        ret = dict(ret)
        if "val" in ret:
            v = ret.pop("val")
            ret.update({"r7": v & 255, "r6": v >> 8 & 255} if self.keil else {"dpl": v & 255, "dph": v >> 8 & 255})
        if "r6" in ret:
            c.iram[6] = ret["r6"] & 255
        if "r7" in ret:
            c.iram[7] = ret["r7"] & 255
        if "dpl" in ret:
            c.sfr[0x02] = ret["dpl"] & 255
        if "dph" in ret:
            c.sfr[0x03] = ret["dph"] & 255
        if "carry" in ret:
            c.sfr[0x50] = (c.sfr[0x50] | 0x80) if ret["carry"] else (c.sfr[0x50] & 0x7F)
        self.p.pc = self.ret_pc

    # ---- run ----
    def _scale_t2(self):
        """As Machine._scale_t2 (time dilation: RCAP2 = t2_scale x the firmware's count)."""
        lo, hi = self.rd(0xCA, 2, "sfr")
        cnt = 0x10000 - (hi << 8 | lo)
        if 0 < cnt < 0x10000 // self.t2_scale and (hi << 8 | lo) != self._t2_set:
            new = 0x10000 - cnt * self.t2_scale
            self._t2_set = new
            self.wr(0xCA, bytes([new & 0xFF, new >> 8]), "sfr")

    def _out(self, why: str) -> str:
        c, p = self.core, self.p
        sp = c.sfr[0x01]
        stack = " ".join(f"{c.iram[(sp - i) & 0xFF]:02x}" for i in range(8))
        return (f"Stop at 0x{p.pc:06x}: {why}\nSP 0x{sp:02x} -> {stack}\nbank {p.bank}\n"
                f"Simulated {self.ticks} ticks\n")

    def run(self, n: int) -> str:
        rem, self._stop, p, core = n, False, self.p, self.core
        if self.t2_scale > 1 and not self.dw and self.instr - self._t2_at >= 100_000:
            self._t2_at = self.instr
            self._scale_t2()
        while True:
            i0, c0, k0 = p.instr, p.cycles, p.clk
            n = max(rem, 1)
            for d in self._tickers:                    # stop near a model deadline (hardware WDT IRQ / reset)
                if self.dw:                            # deadline in real ms; at most max_instr_clk per instruction
                    left = (getattr(d, "deadline", 0) - self.wall_ms) * self.clock.f_cpu / 1000.0
                    if 0 < left:
                        n = min(n, max(1, int(left / self._avg_clk)))      # last chunk's clk per instruction: a worst-case cap would creep up on the deadline
                    elif getattr(d, "deadline", 0) > 0:
                        n = 1                                  # deadline passed, not yet ticked: tick before a full chunk (awto-ddc#162 crash 0x4C overshoot)
                    continue
                left = getattr(d, "deadline", 0) - self.ticks // 12      # <= 4 cycles per instr
                if 0 < left:
                    n = min(n, max(1, left // 4))
            r = core.run(n)
            if self.t2_scale > 1 and not self.dw and r == R_EVENT and any(p.ev[i] == (EV_SW << 16 | 0xCB) for i in range(min(p.nev, 16))):
                lo, hi = self.rd(0xCA, 2, "sfr")
                tl, th = self.rd(0xCC, 2, "sfr")
                self._scale_t2()                       # the firmware's next RCAP2 read sees the dilated reload, as Timer2 does
                if (tl, th) == (lo, hi):               # SDK loads TL2/TH2 with the same count (ScalerTimerSetTimerCount)
                    self.wr(0xCC, self.rd(0xCA, 2, "sfr"), "sfr")
            di, dt = p.instr - i0, (p.cycles - c0) * 12
            if self.dw:
                self.wall_ms += (p.clk - k0) * 1000.0 / self.clock.f_cpu       # f_cpu as it was while these clk ran
                if p.instr > i0:
                    self._avg_clk = max(1.0, (p.clk - k0) / (p.instr - i0))
                self.core.L.core_set_fetch_ratio(self.core.h, self.clock.ratio_x256)
            if r == R_EVENT and p.irq_tail and not self.EXACT:
                dt -= 12                # ucsim: an event stop's "Simulated" ticks miss the IRQ entry cycle after it
            used = di if self.EXACT else max(1, dt // self._tpi)       # Machine: max(1, ticks // TICKS_PER_INSTR) per stop
            self.instr += used
            self.ticks += dt
            rem -= used
            for d in self._tickers:                    # time-driven models (fw_sim ChipReset hardware WDT, #138)
                d.tick(self)
            if r == R_EVENT:
                evs = [p.ev[i] for i in range(min(p.nev, 16))]
                self.last_out = out = self._out("event")
                for e in evs:
                    kind, a = EV_KIND[e >> 16], e & 0xFFFF
                    d = self.hook.get((kind, a))
                    if d is not None:
                        getattr(d, "on_" + kind)(self, a)
                    if self.dw and kind == "write" and a in self.clock.shared:
                        self.clock.update(self)             # FFEE is ChipReset's hook too (one handler per address)
                if rem <= 0 or self._stop:
                    return out
                continue
            if r == R_PC:
                pc = p.pc
                self.last_out = out = self._out("Breakpoint")
                if pc in self._tbrk:
                    self._tbrk.discard(pc)
                    self.core.pch[pc] = 0
                    for k, v in list(self._brk.items()):
                        if v == ("pc", pc):
                            del self._brk[k]
                    self._restub(pc)
                    return out
                if pc in self.stubs:
                    self._do_stub(pc)
                    if p.pc == pc:
                        p.skip_pc = pc
                    if rem <= 0 or self._stop:
                        return out
                    continue
                p.skip_pc = pc                              # a plain breakpoint: the next run starts past it
                return out
            if r == R_BADOP:
                self.last_out = out = self._out(f"invalid instruction 0x{p.bad_op:02x}")
                return out
            self.last_out = out = self._out("step done")
            return out

    def _restub(self, pc: int):
        """PC hook mask after a temporary break at pc is gone: the stubs and plain breaks still there."""
        m = 0
        for b, _, _ in self.stubs.get(pc, []):
            m |= 0xFFFF if b is None else 1 << b
        if ("pc", pc) in self._brk.values():
            m = 0xFFFF
        self.core.pch[pc] = m

    def close(self):
        self.core.free()


def bind(S, exact: bool = False):
    """FastMachine bound to fw_sim module S (fw_sim as __main__ and as an import are two modules: own SimError each)."""
    return type("FastMachine", (FastMachine,), {"S": S, "EXACT": exact})


def boot_check(binp: Path, mapp: Path, be: bool, passes: int, max_instr: int, log, S=None) -> int:
    """fw_sim.boot_check on the fast core: same verdicts (PASS, RESTART, SJMP $ trap, stall, budget) and report lines."""
    S = S or FastMachine._S()
    import rtd_diag
    img = binp.read_bytes()
    sym, where = S.parse_map(mapp.read_text(errors="replace"), img)
    gsinit = sym.get("__sdcc_gsinit_startup")
    flash = S.FlashDev(img)
    m = bind(S)(img, mapp, binp.stem, log, [flash], [gsinit] if gsinit is not None else [])
    chunk, stall_chunks, done = 1_000_000, 15, 0
    starts, last, hb0, same, verdict, d, pc = 0, None, None, 0, None, None, None
    while done < max_instr and verdict is None:
        out = m.run(chunk)
        done += chunk
        pc = m.p.pc
        if "Breakpoint" in out and pc == gsinit:
            starts += 1
            if starts > 1:
                verdict = f"RESTART (startup re-entered) after ~{done} instr"
            continue
        blk = m.rd(0xF6D0, 48)
        d = rtd_diag.decode(blk, be)
        key = (d["stage"], d["hb"])
        if d["stage"] >= 8:
            hb0 = d["hb"] if hb0 is None else hb0
            if (d["hb"] - hb0) & 0xFFFF >= passes:
                verdict = "PASS"; break
        same = same + 1 if key == last else 0
        last = key
        if m.rd(pc, 2, "rom") == b"\x80\xfe":
            verdict = "FAIL trap: SJMP $ at the stop PC"
        elif same >= stall_chunks:
            verdict = f"FAIL stall: no stage/heartbeat change for {stall_chunks * chunk} instr"
    bank = m.rd(0xFFFF)[0] & 0x0F
    sp = m.core.sfr[0x01]
    top = m.core.iram[sp] << 8 | m.core.iram[(sp - 1) & 0xFF]
    m.close()
    st = d["stage"] if d else -1
    hb = d["hb"] if d else -1
    pcs = f"0x{pc:04x} bank {bank} in {where(bank, pc)}" if pc is not None else "?"
    if verdict != "PASS":
        pcs += f"; stack top 0x{top:04x} = {where(bank, top)} (SP 0x{sp:02x})"
    if verdict == "PASS":
        print(f"PASS boot-check {binp.name}: stage {st}, heartbeat {hb0} -> {hb} (+{(hb - hb0) & 0xFFFF}), "
              f"~{done} instr, flash-port reads {flash.fp.reads} [fast core]")
        return 0
    if verdict is None:
        verdict = f"FAIL budget: {max_instr} instr without {passes} heartbeats at stage 8"
    print(f"{verdict}\nFAIL boot-check {binp.name}: last PC {pcs}; diag stage {st} heartbeat {hb}; "
          f"~{done} instr; flash-port reads {flash.fp.reads} [fast core]")
    if d:
        print(rtd_diag.report(d, None, None))
    return 1
