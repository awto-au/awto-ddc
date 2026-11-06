#!/usr/bin/env python3
"""Run the banked firmware image in ucsim with a bank-switch model, to see how far init gets.

usage: fw_sim.py --serial AWT26110003 [--budget 3000000] [--max-switches 2000]
  ucsim has no RL6449 bank register: breakpoints on __bs_call (bank = r2) and __bs_ret (bank = r1) load
  that bank's 64 KiB image (common area identical in every bank, so the swap is exact). Peripherals are
  not modelled (XDATA/SFR reads return RAM contents), so a wait-for-hardware loop shows up as a stall.
  Stops on: --budget instructions without a bank switch (prints PC + function from the map), or max switches.
       fw_sim.py --boot-check BIN MAP [--be|--le] [--passes 50]   offline PASS/FAIL: boot to the main loop (#11, #38)
       fw_sim.py --isr-check BIN MAP                              interrupts in every bank return to that bank
       fw_sim.py --video-check BIN MAP [--mode 1080p60|2160p60] [--instr 60000000] [--fault underflow]   stable HDMI source on D2: mode-state timeline
         + blocker log (AwtoMsg ids with SDK source line, PC histogram, stub hits) -> tmp/logs/fw_sim_video.log
  Library: Machine (ucsim + Dev register models + function stubs), SimBus (i2cbus-compatible debug slave 0x35, see
  unit_health.py --sim), video_devs/video_stubs (what the firmware sees on D2). Models: IicSlave (FF24..FF2A, FE66),
  FlashDev (FF78..FF7B), IndPort (DPCD), HdmiInput (measure + auto-function results), regdb reset values (re/regdb).
  Boot check = native banking + flash-read port model (below); PASS = diag stage 8 and the heartbeat advances.
  Native-mode histogram runs stop after --samples interrupts (~300k instr): that, not hardware, ended at stage 4.
Log: tmp/logs/fw_sim.log; per-bank ihx in tmp/fwsim/<serial>/ (boot/isr check: tmp/fwsim/<bin stem>/)
"""
import argparse, bisect, os, re, select, subprocess, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = repo_root()
BANK = 0x10000
VECTORS = (0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B, 0x43)   # break here: stack top = interrupted PC


def write_ihx(data: bytes, path: Path):
    out = []
    for a in range(0, len(data), 16):
        ch = data[a:a + 16]                              # all bytes: a bank swap must overwrite the old one
        rec = bytes([len(ch), a >> 8, a & 0xFF, 0]) + ch
        out.append(":" + rec.hex().upper() + "%02X" % ((-sum(rec)) & 0xFF))
    path.write_text("\n".join(out + [":00000001FF"]) + "\n")


def nodelay_env() -> dict:
    """ucsim sleeps 100 ms per idle console poll once it is 2 s old (every command round trip then costs 100 ms);
    scripts/ucsim_nodelay.c turns that sleep into 50 us. Built on first use into tmp/; no gcc = slow but correct."""
    src, so = Path(__file__).resolve().parent / "ucsim_nodelay.c", ROOT / "tmp/ucsim_nodelay.so"
    try:
        if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
            so.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(src), "-ldl"], check=True, timeout=60,
                           capture_output=True)
        return {**os.environ, "LD_PRELOAD": str(so)}
    except (OSError, subprocess.SubprocessError):
        return dict(os.environ)


class Sim:
    def __init__(self, ihx, log):
        self.p = subprocess.Popen([T.tool("ucsim_51"), "-t", "52", *([str(ihx)] if ihx else [])], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, env=nodelay_env())
        self.log, self.buf = log, b""

    def send(self, cmd):
        self.p.stdin.write((cmd + "\n").encode()); self.p.stdin.flush()

    def read_until(self, rx, timeout):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            m = re.search(rx, self.buf)
            if m:
                out, self.buf = self.buf[:m.end()], self.buf[m.end():]
                self.log.write(out.decode(errors="replace")); return out.decode(errors="replace")
            r, _, _ = select.select([self.p.stdout], [], [], 0.05)
            if r:
                self.buf += os.read(self.p.stdout.fileno(), 65536)
        return None


def print_diag(s):
    """Diag block (rtd_diag.py layout) from sim XRAM: stage reached + stage timestamps; none if the fw has no block."""
    import rtd_diag
    s.send("dump xram 0xf6d0 0xf6ff")
    out = s.read_until(rb"0xf6f8 [^\n]*\n", 120)
    rows = {int(m.group(1), 16): bytes.fromhex(m.group(2).replace(" ", ""))
            for m in re.finditer(r"^0x([0-9a-f]{4})\s+((?:[0-9a-f]{2} ){8})", out or "", re.M)}
    blk = b"".join(rows.get(a, b"") for a in range(0xF6D0, 0xF700, 8))
    if len(blk) != 48:
        print("diag block: not read from sim XRAM"); return
    print("diag block (sim XRAM 0xf6d0):", blk.hex())
    print(rtd_diag.report(rtd_diag.decode(blk, T.BIG_ENDIAN), None, None))


class FlashPort:
    """Flash data port (SDK ScalerFlashRead): FF78..FF7A = 24-bit flash address, FF7B = data port, auto-increment.
    Served from the image (flash content = the .bin; 0xFF beyond it). ucsim has no auto-increment: event
    breakpoints on FF7A writes / FF7B reads preload the next byte into the cell."""
    ADDR, PORT = 0xFF78, 0xFF7B

    def __init__(self, img: bytes):
        self.img, self.ptr, self.reads = img, 0, 0

    def arm(self, s):
        s.send(f"break xram w 0x{self.ADDR + 2:x}"); s.send(f"break xram r 0x{self.PORT:x}")

    def byte(self, p):
        return self.img[p] if p < len(self.img) else 0xFF

    def handle(self, s, out) -> bool:
        """True if this stop was a flash-port event (handled; caller resumes)."""
        if "Event break" not in out:
            return False
        s.send(f"dump xram 0x{self.ADDR:x} 0x{self.PORT:x}")
        r = s.read_until(rb"0xff78\s+((?:[0-9a-f]{2} ){4})", 10)
        if r is None:
            return False
        ev = re.findall(r"Event `(\w+)' at xram\[0x([0-9a-f]+)\]", out + r)
        a = [int(x, 16) for x in re.search(r"0xff78\s+((?:[0-9a-f]{2} ){4})", r).group(1).split()]
        kind, adr = ev[-1] if ev else ("", "")
        if adr == f"{self.ADDR + 2:x}" and kind == "write":
            self.ptr = a[0] << 16 | a[1] << 8 | a[2]
        elif adr == f"{self.PORT:x}":
            self.ptr += 1; self.reads += 1
        else:
            return False
        s.send(f"set memory xram 0x{self.PORT:x} 0x{self.byte(self.ptr):x}")
        return True


def open_native(img: bytes, d: Path, log, flash: FlashPort | None = None, extra_breaks=()):
    """ucsim with the RL6449 banker (see native), all banks loaded, reset, breakpoints set."""
    nb = len(img) // BANK
    d.mkdir(parents=True, exist_ok=True)
    for k in range(nb):
        write_ihx(img[k * BANK:(k + 1) * BANK], d / f"bank{k}.ihx")
    s = Sim(None, log)
    s.send(f"memory create chip flash 0x{nb * BANK:x} 8")
    s.send("memory create banker xram 0xffff 0x0f rom 0x0000 0xffff")
    for k in range(nb):
        s.send(f"memory create bank rom 0x0000 {k} flash 0x{k * BANK:x}")
    for k in range(nb):
        s.send(f"set memory xram 0xffff {k}"); s.send(f'file "{d / f"bank{k}.ihx"}"')
        if not s.read_until(rb"Loading from[^\n]*bank%d\.ihx" % k, 30):
            raise RuntimeError(f"load of bank {k} failed")
    s.send("set memory xram 0xffff 0"); s.send("reset")
    for v in extra_breaks:
        s.send(f"break 0x{v:x}")
    if flash:
        flash.arm(s)
    return s


def parse_map(mp: str, img: bytes):
    """(sym dict, where(bank, pc)). Common area = leading bytes identical in every bank (no build.json for loose images)."""
    sym = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(\w+)", mp, re.M)}
    for m in re.finditer(r"^CH_(\w+)=0x([0-9a-fA-F]+)\s*$", mp, re.M):      # full-length names (the C: lines cut at 32 chars)
        sym["_" + m.group(1)] = int(m.group(2), 16)
    funcs = sorted((v, k) for k, v in sym.items() if k.startswith("_") and not k.startswith("__bs_"))
    keys = [v for v, _ in funcs]
    nb = len(img) // BANK
    cend = 0
    while cend < BANK and all(img[k * BANK + cend] == img[cend] for k in range(1, nb)):
        cend += 1
    where = lambda bank, pc: next((k for v, k in reversed(funcs[:bisect.bisect_right(
        keys, pc if pc < cend or bank == 0 else bank * BANK + pc)])), "?")
    where.cend = cend
    return sym, where


def run_chunk(s, flash, n, timeout=120):
    """step n instructions, serving flash-port events; returns the last output (the Stop/Simulated text)."""
    s.send(f"step {n}")
    while True:
        out = s.read_until(rb"Simulated \d+ ticks[^\n]*\n", timeout)
        if out is None:
            return None
        if flash and flash.handle(s, out):
            s.send(f"step {n}"); continue
        return out


# ---- Machine: ucsim + peripheral models (offline monitor; #38) ----------------------------------------------
TICKS_PER_INSTR = 21        # ucsim ticks per instruction on this image (stepped 3 M instr = 63.7 M ticks, 2026-11-06)


class _Null:
    def write(self, _):
        pass


class SimError(RuntimeError):
    pass


class Dev:
    """Peripheral model. Registers are plain ucsim XRAM cells; only addresses in reads/writes raise an event stop
    (after the accessing instruction), where the model fixes up the cells the next access will see."""
    reads: tuple = ()
    writes: tuple = ()

    def init(self, m):
        """Called after reset: preset constant status cells."""

    def on_read(self, m, a):
        pass

    def on_write(self, m, a):
        pass


class FlashDev(Dev):
    """FlashPort (FF78..FF7B) as a Dev."""
    reads, writes = (FlashPort.PORT,), (FlashPort.ADDR + 2,)

    def __init__(self, img):
        self.fp = FlashPort(img)

    def _preload(self, m):
        m.put(f"set memory xram 0x{FlashPort.PORT:x} 0x{self.fp.byte(self.fp.ptr):x}")

    def on_write(self, m, a):
        v = m.rd(FlashPort.ADDR, 3)
        self.fp.ptr = v[0] << 16 | v[1] << 8 | v[2]
        self._preload(m)

    def on_read(self, m, a):
        self.fp.ptr += 1; self.fp.reads += 1
        self._preload(m)


class IicSlave(Dev):
    """Debug slave 0x35 on DDC2 (SDK ScalerDebugIntProc_EXINT1 + fw/sdcc/awto_dbgisr.inc).
    FF24 SUB_IN, FF25 DATA_IN (rx FIFO head), FF26 DATA_OUT (tx FIFO), FF27 STATUS (bit1 SUB_I, bit2 D_IN_I, bit4 stop;
    write 0 clears), FF29 STATUS2 (bit1 rx empty, bit2 tx full), FF2A IRQ_CONTROL2 (bit6 reset FIFO), FE66 bit0 SCL hold."""
    SUB, DIN, DOUT, STAT, STAT2, IRQ2, SCL = 0xFF24, 0xFF25, 0xFF26, 0xFF27, 0xFF29, 0xFF2A, 0xFE66
    SUB_I, D_IN_I, STOP_I = 0x02, 0x04, 0x10
    reads, writes = (DIN,), (DOUT, STAT, IRQ2, SCL)

    def __init__(self):
        self.rx, self.rxpos, self.tx, self.flags = b"", 0, bytearray(), 0
        self.held = self.released = False
        self.ex1_ticks = 0

    def init(self, m):
        m.put(f"set memory xram 0x{self.STAT2:x} 0x02")          # rx FIFO empty

    def on_read(self, m, a):
        self.rxpos += 1
        if self.rxpos < len(self.rx):
            m.put(f"set memory xram 0x{self.DIN:x} 0x{self.rx[self.rxpos]:x}")
        else:
            m.put(f"set memory xram 0x{self.STAT2:x} 0x{m.rd(self.STAT2)[0] | 0x02:x}")

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == self.DOUT:
            self.tx.append(v)
        elif a == self.IRQ2:
            if v & 0x40:
                self.tx.clear()
        elif a == self.STAT:
            self.flags &= v
            m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")
        elif a == self.SCL:
            if v & 1:
                self.held = True
            elif self.held:
                self.released = True; m.request_stop()

    def inject(self, m, sub: int, data: bytes, stop: bool = True):
        """Present one host transaction (sub byte + data, then stop) and raise EXINT1 (IE1)."""
        self.rx, self.rxpos, self.held, self.released = bytes(data), 0, False, False
        self.flags = self.SUB_I | (self.D_IN_I if data else 0) | (self.STOP_I if stop else 0)
        st2 = m.rd(self.STAT2)[0]
        m.put(f"set memory xram 0x{self.SUB:x} 0x{sub:x}")
        if data:
            m.put(f"set memory xram 0x{self.DIN:x} 0x{data[0]:x}")
        m.put(f"set memory xram 0x{self.STAT2:x} 0x{(st2 & ~2) if data else (st2 | 2):x}")
        m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")
        m.put("set bit 0x8b 1")
        m.flush()


class RegTrace(Dev):
    """Which constant-address registers does the code read/write? Event breakpoints on the static candidates
    (fw_regs.candidates); a breakpoint is deleted after `limit` hits (so counts saturate at limit = polled)."""

    def __init__(self, rd_addrs, wr_addrs, limit: int = 200):
        self.reads, self.writes, self.limit = tuple(sorted(rd_addrs)), tuple(sorted(wr_addrs)), limit
        self.cnt = {"read": {}, "write": {}}
        self.first = {"read": {}, "write": {}}               # addr -> (pc, bank, value)
        self.nr = {}

    def init(self, m):
        m.flush()
        out = m.cmd("info breakpoints")
        for g in re.finditer(r"^(\d+)\s+event\s+keep\s+\d+\s+\d+\s+0x([0-9a-f]+)\s+(read|write)", out, re.M):
            self.nr[(g.group(3), int(g.group(2), 16))] = int(g.group(1))

    def _hit(self, m, kind, a):
        c = self.cnt[kind]
        c[a] = c.get(a, 0) + 1
        if a not in self.first[kind]:
            mt = re.search(r"Stop at 0x([0-9a-f]+)", m.last_out)
            self.first[kind][a] = (int(mt.group(1), 16) if mt else -1, m.rd(0xFFFF)[0] & 15, m.rd(a)[0])
        if c[a] >= self.limit and (kind, a) in self.nr:
            m.put(f"delete {self.nr.pop((kind, a))}")

    def on_read(self, m, a):
        self._hit(m, "read", a)

    def on_write(self, m, a):
        self._hit(m, "write", a)

    def report(self, m, names, kind="read") -> list[str]:
        rows = []
        for a, c in sorted(self.cnt[kind].items(), key=lambda kv: -kv[1]):
            pc, bank, v = self.first[kind][a]
            rows.append(f"{kind[0]} 0x{a:04X} {names.get(a, '?'):<42} n={c}{'+' if c >= self.limit else ' '} "
                        f"first {m.where(bank, pc)}@{bank} val 0x{v:02X}")
        return rows


class Cells(Dev):
    """Constant register values (after reset); name -> value dicts are applied through m.put."""

    def __init__(self, cells: dict[int, int]):
        self.cells = dict(cells)

    def init(self, m):
        items, i = sorted(self.cells.items()), 0
        while i < len(items):                         # consecutive addresses in one command (<= 16 values)
            j = i
            while j + 1 < len(items) and items[j + 1][0] == items[j][0] + 1 and j - i < 15:
                j += 1
            m.put(f"set memory xram 0x{items[i][0]:x} " + " ".join(f"0x{v:x}" for _, v in items[i:j + 1]))
            i = j + 1


class HdmiInput(Dev):
    """Stable CEA video on D2: sync-measure and auto-function result registers (P30_02..14 offline measure, P0_7C..83 auto
    function) as the SDK ScalerMeasure* code decodes them. F-to-P (P31_06 bit7) halves the auto-function V window as the
    hardware does (the code doubles it back). MODES: name -> (htotal, hact, hstart, vtotal, vact, vstart, pclk 0.1 MHz)."""
    MODES = {"1080p60": (2200, 1920, 192, 1125, 1080, 41, 1485), "2160p60": (4400, 3840, 384, 2250, 2160, 82, 5940)}
    MEAS_KHZ = 87_700          # _MEASURE_CLK with M2PLL 350.8 MHz / 4 (kHz): HS period counts = clk * 10 / hfreq(0.1 kHz)
    DATA_PATH_LIMIT = 3000     # RL6449_Series_IDomainInclude.h _DATA_PATH_SPEED_LIMIT (0.1 MHz)
    writes = (0x3106,)

    def __init__(self, mode: str = "1080p60"):
        """Modes above DATA_PATH_LIMIT (2160p60, pixel clock 594 MHz = TMDS clock 148.5 MHz x4 with SCDC 1/40) follow the data
        path the SDK sets up: P30_00 bit7 (measure clock divider /2: offline H total and width counted at half rate, the code
        doubles them back) and 1/2 scaling down (P31_05 bit7 = 0 with P31_06 bit7 = 0: auto-function H start/end in half
        pixels, the code doubles them) until ScalerFmtCnvFinalSetting switches to F-to-P."""
        self.mode = mode
        self.HTOT, self.HACT, self.HSTART, self.VTOT, self.VACT, self.VSTART, self.PCLK = self.MODES[mode]
        self.hfreq10 = round(self.PCLK * 1e5 / self.HTOT / 100)       # 0.1 kHz
        self.fast = self.PCLK > self.DATA_PATH_LIMIT
        if self.fast:
            self.writes = (0x3000, 0x3105, 0x3106)
        self.div = self.halfsd = False

    def cells(self) -> dict[int, int]:
        c = {}
        hs_per = round(self.MEAS_KHZ * 10 / self.hfreq10) - 1
        k = 2 if self.div else 1                                        # measure clock divider: H counts at half rate
        for a, v, mask_hi in ((0x3005, hs_per, 0x1F), (0x3008, self.VTOT - 1, 0x3F), (0x300A, 3, 0x1F), (0x300C, 4, 0x3F),
                              (0x300E, self.HTOT // k - 1, 0x1F), (0x3011, self.VACT - 1, 0x3F), (0x3013, self.HACT // k - 1, 0x1F)):
            c[a], c[a + 1] = (v >> 8) & mask_hi, v & 0xFF
        c[0x3003], c[0x3004] = 0x00, 0xC0                              # no measure error flags; HS/VS polarity positive
        c.update(self.auto(False))
        c[0x007D] = 0x40                                                # auto-function finished
        c[0x007C] = c[0x0078] = 0
        c[0x3106] = 0x10                                                # F-to-P off until the firmware enables it
        # active-region clock counts (P30_41..44 input, P30_46..49 display): ScalerDPLLFineTuneFrameSyncLineBuffer scales Dclk
        # by their ratio; equal counts = already in sync (zeros gave Dclk 0x830B6229 -> NOSUPPORT)
        n = round(self.VACT * self.HTOT / self.PCLK * 1e-1 * self.MEAS_KHZ * 1e3 / self.HTOT * self.HACT / 1e3)
        c[0x0044], c[0x0045], c[0x0046] = 0x08, 0xCA, 0x00               # LAST_LINE = display DVtotal read-back (2250 in line-buffer mode)
        for base in (0x3041, 0x3046):
            c[base] = 0
            c[base + 1], c[base + 2], c[base + 3] = (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF
        return c

    def auto(self, ftop: bool) -> dict[int, int]:
        vs, vh = ((self.VSTART - 1) // 2, self.VACT // 2) if ftop else (self.VSTART, self.VACT)
        ve = vs + vh - 1
        k = 2 if self.halfsd else 1
        hs, hw = self.HSTART // k, self.HACT // k
        he = hs + hw - 1
        r = {0x007E: ((vs >> 4) & 0xF0) | ((ve >> 8) & 0x0F), 0x007F: vs & 0xFF, 0x0080: ve & 0xFF,
             0x0081: (((hs - 1) >> 4) & 0xF0) | (((he - 1) >> 8) & 0x0F), 0x0082: (hs - 1) & 0xFF, 0x0083: (he - 1) & 0xFF}
        if self.fast:
            r[0x0078] = ((hs >> 11) & 2) | (((he - 1) >> 12) & 1)       # P0_78 bit1/bit0: H start/end bit 11/12 (> 4095 px)
        return r

    def init(self, m):
        for a, v in sorted(self.cells().items()):
            m.put(f"set memory xram 0x{a:x} 0x{v:x}")

    def on_write(self, m, a):
        ftop = bool(m.rd(0x3106)[0] & 0x80)
        if self.fast:
            self.div = bool(m.rd(0x3000)[0] & 0x80)
            self.halfsd = not (m.rd(0x3105)[0] & 0x80) and not ftop
            for k, v in self.cells().items():
                if 0x3005 <= k <= 0x3014:
                    m.put(f"set memory xram 0x{k:x} 0x{v:x}")
        for k, v in self.auto(ftop).items():
            m.put(f"set memory xram 0x{k:x} 0x{v:x}")


MODE_NAMES = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
T2_SCALE = 3
D2_INPUT_PORT, SOURCE_HDMI, SOURCE_NONE = 5, 3, 5          # Kernel/Common/Global.h


FAULTS = {"underflow": {0x0002: 0x01}}      # name -> sticky flag bits (address -> mask), see W1C


def video_devs(img: bytes, mode: str = "1080p60", fault: str | None = None):
    """Devs for a board with a stable HDMI source on D2 (#38): regdb reset values, D2 cable pin (low = connected) and no
    D3 cable, DPCD access port (DP Rx1), the HDMI measure/auto-function results. Returns (devs, hdmi).
    fault="underflow": P0_02 bit0 (M-domain FIFO underflow) re-sets after every clear, as in the unit-3 4K60 register dump
    tmp/regs/AWT26110003-20261105-181408.json (P0_02 = 0x01; the vendor dump 180523 has 0x00) (#26)."""
    hdmi = HdmiInput(mode)
    return [regdb_cells(), FlashDev(img), IicSlave(), Cells({0xFE2C: 1, 0xFE32: 0}),
            IndPort((0xBAC1, 0xBAC2, 0xBAC3), 0xBAC4),
            W1C({0x0002: 0xFF, 0x000C: 0x01, 0x1603: 0xFF, 0x1616: 0x70, 0x3003: 0xF0, 0x3016: 0x70},
                FAULTS[fault] if fault else None), hdmi], hdmi


def video_stubs(m: "Machine", hdmi: HdmiInput):
    """Functions replaced because they poll the HDMI Rx PHY (CDR/DFE lock, TMDS clock count, packet SRAM) that is not modelled:
    pre-detect and scan on D2 succeed, stability check passes, scan sets the input pixel clock like the SDK does."""
    m.stub("ScalerTMDSNormalPreDetect", lambda m, r: {"carry": (r["dptr"] & 255) == D2_INPUT_PORT})
    m.stub("ScalerTMDSStableDetect", lambda m, r: {"carry": 1})
    m.stub("ScalerSyncDpCheckUrgentHotPlugEventExist", lambda m, r: {"carry": 0})   # no DP source: pending HPD events never end

    def scan(m, r):
        if (r["dptr"] & 255) != D2_INPUT_PORT:
            return {"dpl": SOURCE_NONE}
        m.wr(m.addr("g_usInputPixelClk"), hdmi.PCLK.to_bytes(2, "big"))        # SET_INPUT_PIXEL_CLK (0.1 MHz)
        return {"dpl": SOURCE_HDMI}
    m.stub("ScalerTMDSScanInputPort", scan)


class W1C(Dev):
    """Write-1-to-clear flag bits (mask per address): after a write the flag bits read 0 (no new error/event arrives in the
    sim). Plain XRAM keeps the written 1s, so status checks like ScalerMDomainMemoryCheck failed forever."""

    def __init__(self, masks: dict[int, int], sticky: dict[int, int] | None = None):
        """sticky: address -> bits that read 1 again after the clear (a flag the hardware keeps raising)."""
        self.masks, self.sticky = masks, sticky or {}
        self.writes = tuple(masks)

    def on_write(self, m, a):
        m.put(f"set memory xram 0x{a:x} 0x{(m.rd(a)[0] & ~self.masks[a] & 0xFF) | self.sticky.get(a, 0):x}")


class IndPort(Dev):
    """Address-then-data port (DPCD access port etc.): data cell is preloaded with mem[addr] when the last address
    register is written (the read that follows then sees the right value); a data write stores into mem[addr]."""

    def __init__(self, addr_regs: tuple, data_reg: int, mem: dict | None = None):
        self.addr_regs, self.data_reg, self.mem = addr_regs, data_reg, mem if mem is not None else {}
        self.writes = (addr_regs[-1], data_reg)

    def addr(self, m):
        return int.from_bytes(b"".join(m.rd(a) for a in self.addr_regs), "big")

    def on_write(self, m, a):
        if a == self.data_reg:
            self.mem[self.addr(m)] = m.rd(a)[0]
        else:
            m.put(f"set memory xram 0x{self.data_reg:x} 0x{self.mem.get(self.addr(m), 0):x}")


def regdb_cells(chip: str = "RTD2795T-CG") -> Cells:
    """Register file at chip reset (re/regdb), minus the firmware's XDATA RAM (0xD700..0xF6FF) and the bank register."""
    import fw_regs
    return Cells({a: v for a, v in fw_regs.regdb_reset(chip).items() if not 0xD700 <= a < 0xF700 and a != 0xFFFF})


class Machine:
    """ucsim running a banked image with Dev models. run(n) serves device events until n instructions are used
    (estimated from ticks), a non-event stop (breakpoint) happens, or a model calls request_stop()."""

    def __init__(self, img: bytes, mapp: Path, tag: str, log=None, devs=(), extra_breaks=()):
        self.img, self.devs = img, list(devs)
        self.map_text = mapp.read_text(errors="replace")
        self.sym, self.where = parse_map(self.map_text, img)
        self.log = log or _Null()
        self.s = open_native(img, ROOT / "tmp/fwsim" / tag, _Null(), None, extra_breaks)
        self.s.send("fill xram 0x0 0xfffe 0x0")            # ucsim starts XRAM random: registers read the same every run
        self.ticks, self.instr, self._n, self._q, self._stop, self.last_out = 0, 0, 0, [], False, ""
        self.stubs, self.stub_hits = {}, {}
        self.t2_scale, self._t2_set, self._t2_at = 1, -1, -10**9
        self.ret_pc = self.sym["__bs_call_sw"] + 5            # the RET that ends __bs_call (mov dpl,r5 / mov dph,r6 / mov a,r4 / ret)
        self.hook = {}
        for d in self.devs:
            for a in d.reads:
                self.hook[("read", a)] = d
                self.s.send(f"break xram r 0x{a:x}")
            for a in d.writes:
                self.hook[("write", a)] = d
                self.s.send(f"break xram w 0x{a:x}")
        for d in self.devs:
            d.init(self)
        self.flush()

    def cmd(self, text: str, timeout: float = 120) -> str:
        self._n += 1
        tag = f"@@{self._n}"
        self.s.send(f"{text}\necho {tag}")
        out = self.s.read_until(rb"(?:^|\n)" + tag.encode() + rb"\n", timeout)
        if out is None:
            raise SimError(f"ucsim did not answer `{text[:60]}` within {timeout} s")
        return out

    def addr(self, name: str) -> int:
        """XDATA address of a global (16-bit, from the map)."""
        mt = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", self.map_text)
        if not mt:
            raise SimError(f"_{name} not in the map")
        return int(mt.group(1), 16) & 0xFFFF

    def put(self, c: str):
        self._q.append(c)

    def flush(self):
        q, self._q = self._q, []
        for i in range(0, len(q), 100):              # bounded batches: ucsim echoes input, an unread pipe would deadlock
            self.cmd("\n".join(q[i:i + 100]))

    def rd(self, a: int, n: int = 1, space: str = "xram") -> bytes:
        self.flush()
        out = self.cmd(f"dump {space} 0x{a:x} 0x{a + n - 1:x} 16")
        got = {}
        if space == "sfr":                           # one line per register: 0xca RCAP2L: 0b00000000 0x00 '.' 0
            for m in re.finditer(r"^0x([0-9a-f]{2})\s+\w+:\s+0b[01]{8} 0x([0-9a-f]{2})", out, re.M):
                got[int(m.group(1), 16)] = int(m.group(2), 16)
            if len(got) < n:
                raise SimError(f"dump sfr 0x{a:x}+{n} returned {len(got)} bytes")
            return bytes(got[a + i] for i in range(n))
        for m in re.finditer(r"0x([0-9a-f]{2,6})\s{2,}((?:[0-9a-f]{2} )+)", out):
            base = int(m.group(1), 16)
            for i, h in enumerate(m.group(2).split()[:min(16, a + n - base)]):
                got[base + i] = int(h, 16)
        if len(got) < n:
            raise SimError(f"dump {space} 0x{a:x}+{n} returned {len(got)} bytes")
        return bytes(got[a + i] for i in range(n))

    def wr(self, a: int, data: bytes, space: str = "xram"):
        self.put(f"set memory {space} 0x{a:x} " + " ".join(f"0x{b:x}" for b in data)); self.flush()

    def request_stop(self):
        self._stop = True

    def stub(self, name: str, fn):
        """Replace a function: fetch breakpoint on its entry (bank checked at the stop; common code matches any bank);
        fn(m, regs) -> dict (dpl, dph, carry) is the return value and the call is skipped with a RET at the entry; None =
        watch only, the function runs. regs = acc, r[0..7], dptr from the stop text."""
        v = self.sym.get("_" + name)
        if v is None:
            raise SimError(f"_{name} not in the map")
        bank, pc = v >> 16, v & 0xFFFF
        common = v < getattr(self.where, "cend", 0)
        self.stubs.setdefault(pc, []).append((None if common else bank, name, fn))
        if len(self.stubs[pc]) == 1:
            self.s.send(f"break 0x{pc:x}")

    def _do_stub(self, pc: int, out: str):
        bank = self.rd(0xFFFF)[0] & 15
        hit = [(n, f) for b, n, f in self.stubs[pc] if b is None or b == bank]
        if not hit:
            return
        name, fn = hit[0]
        acc = re.search(r"ACC= 0x([0-9a-f]{2})", out)
        rr = re.search(r"R0 R1 R2 R3 R4 R5 R6 R7\s*\n\s*((?:[0-9a-f]{2} ){7}[0-9a-f]{2})", out)
        dp = re.search(r"DPTR= 0x([0-9a-f]{4})", out)
        bb = re.search(r"B= 0x([0-9a-f]{2})", out)
        regs = {"acc": int(acc.group(1), 16) if acc else 0, "b": int(bb.group(1), 16) if bb else 0, "r": [int(x, 16) for x in rr.group(1).split()] if rr else [0] * 8,
                "dptr": int(dp.group(1), 16) if dp else 0}
        ret = fn(self, regs)
        self.stub_hits[name] = self.stub_hits.get(name, 0) + 1
        if ret is None:                                   # watch only: the function runs
            return
        
        if "dpl" in ret:
            self.put(f"set memory sfr 0x82 0x{ret['dpl'] & 255:x}")
        if "dph" in ret:
            self.put(f"set memory sfr 0x83 0x{ret['dph'] & 255:x}")
        if "carry" in ret:
            self.put(f"set bit 0xd7 {int(bool(ret['carry']))}")
        self.put(f"pc 0x{self.ret_pc:x}")
        self.flush()

    def watch(self, name: str):
        self.stub(name, lambda m, r: None)

    def _scale_t2(self):
        """Time dilation: the sim CPU runs ~3x fewer instructions per Timer2 tick than the 87.7 MHz DW8051 (SDK reload
        0xE373 = 7309 counts/ms), so software division loops in display setup overrun the firmware's 2 s NOSUPPORT timer.
        RCAP2 is rewritten to t2_scale x the firmware's count (auto-reload), keeping fw time = instr / (4.2 k x scale)."""
        lo, hi = self.rd(0xCA, 2, "sfr")
        cnt = 0x10000 - (hi << 8 | lo)
        if 0 < cnt < 0x10000 // self.t2_scale and (hi << 8 | lo) != self._t2_set:
            new = 0x10000 - cnt * self.t2_scale
            self._t2_set = new
            self.wr(0xCA, bytes([new & 0xFF, new >> 8]), "sfr")

    def run(self, n: int) -> str:
        rem, self._stop = n, False
        if self.t2_scale > 1 and self.instr - self._t2_at >= 100_000:
            self._t2_at = self.instr
            self._scale_t2()
        while True:
            out = self.cmd(f"step {max(rem, 1)}")
            t = re.search(r"Simulated (\d+) ticks", out)
            used = max(1, int(t.group(1)) // TICKS_PER_INSTR) if t else 1
            self.ticks += int(t.group(1)) if t else 0
            self.instr += used
            ev = re.findall(r"Event `(\w+)' at xram\[0x([0-9a-f]+)\]", out)
            self.last_out = out
            if not ev:
                stop = re.search(r"Stop at 0x([0-9a-f]+)", out)
                if stop and int(stop.group(1), 16) in self.stubs and "Breakpoint" in out:
                    self._do_stub(int(stop.group(1), 16), out)
                    rem -= used
                    if rem <= 0 or self._stop:
                        return out
                    continue
                return out
            rem -= used
            for kind, a in ev:
                getattr(self.hook[(kind, int(a, 16))], "on_" + kind)(self, int(a, 16))
            self.flush()
            if rem <= 0 or self._stop:
                return out

    def close(self):
        try:
            self.s.send("quit"); self.s.p.wait(5)
        except Exception:
            self.s.p.kill()


class SimBus:
    """Offline stand-in for i2cbus.Bus / rtd_i2c_bridge.Real on the debug slave 0x35 (#38): write(dev8, sub, data) -> bool,
    read(dev8, sub, n) -> bytes | None, wait(s) / now() in firmware time (Timer2 ticks of 1 ms), xdata(addr, n) direct."""
    DEV8 = 0x6A
    WRITE_BUDGET = 3_000_000       # instr until the SCL release; one main-loop pass is ~0.1 M (boot-check: 67 passes / 16 M)
    ISR_BUDGET = 20_000            # instr for a SUB_I-only EXINT1 (read address phase)

    def __init__(self, binp: Path, mapp: Path, tag: str | None = None, log=None, boot: bool = True,
                 devs=(), video: str | None = None):
        """video = HdmiInput mode name ("1080p60") for a firmware that sees a stable HDMI source on D2; None = bare
        CPU + flash port + debug slave (random XRAM, no source)."""
        import rtd_diag
        self.rtd_diag = rtd_diag
        self.img = Path(binp).read_bytes()
        self.be = "-be" in Path(binp).name or T.BIG_ENDIAN
        if video:
            all_devs, self.hdmi = video_devs(self.img, video)
            self.iic = next(d for d in all_devs if isinstance(d, IicSlave))
        else:
            self.iic = IicSlave()
            all_devs, self.hdmi = [FlashDev(self.img), self.iic], None
        self.m = Machine(self.img, Path(mapp), tag or Path(binp).stem, log, [*all_devs, *devs])
        if video:
            video_stubs(self.m, self.hdmi)
            self.m.t2_scale = T2_SCALE
        self.diag_base = self.m.sym.get("_g_stAwtoDiag", 0xF6D0)
        self.t2_abs, self._t2_last = 0, None
        self.naks = 0
        if boot:
            self.boot()

    def addr(self, name: str) -> int:
        return self.m.addr(name)

    def mode_state(self) -> int:
        return self.m.rd(self.addr("g_stModeInfo"))[0] & 0x1F

    def run_until_mode(self, mode: int = 3, max_instr: int = 150_000_000, chunk: int = 1_000_000) -> bool:
        """Let the firmware run (no host traffic) until g_stModeInfo reaches `mode` (3 = ACTIVE); False when the budget is out."""
        used = 0
        while used < max_instr:
            if self.mode_state() == mode:
                return True
            self.m.run(chunk); used += chunk
        return self.mode_state() == mode

    def xdata(self, a: int, n: int = 1) -> bytes:
        return self.m.rd(a, n)

    def diag(self) -> dict:
        return self.rtd_diag.decode(self.m.rd(0xF6D0, 48), self.be)

    def boot(self, passes: int = 3, max_instr: int = 60_000_000, chunk: int = 1_000_000):
        hb0, used = None, 0
        while used < max_instr:
            self.m.run(chunk); used += chunk
            d = self.diag()
            if d["stage"] >= 8:
                hb0 = d["hb"] if hb0 is None else hb0
                if (d["hb"] - hb0) & 0xFFFF >= passes:
                    return d
        raise SimError(f"boot: stage {self.diag()['stage']} after {used} instr")

    def write(self, dev8: int, sub: int, data: bytes) -> bool:
        if dev8 != self.DEV8:
            return False
        self.iic.inject(self.m, sub, bytes(data))
        used = 0
        while used < self.WRITE_BUDGET and not self.iic.released:
            self.m.run(5000); used += 5000
        if not self.iic.released:
            self.naks += 1
        return self.iic.released

    def read(self, dev8: int, sub: int, n: int) -> bytes | None:
        if dev8 != self.DEV8:
            return None
        tx = bytes(self.iic.tx)
        self.iic.inject(self.m, sub, b"")
        self.m.run(self.ISR_BUDGET)
        if len(tx) < n:
            self.naks += 1
            return None
        self.iic.tx.clear()
        return tx[:n]

    def _t2(self) -> int:
        t = self.diag_t2()
        if self._t2_last is not None:
            self.t2_abs += (t - self._t2_last) & 0xFFFF
        self._t2_last = t
        return self.t2_abs

    def diag_t2(self) -> int:
        b = self.m.rd(self.diag_base + 0x16, 2)
        return int.from_bytes(b, "big" if self.be else "little")

    def now(self) -> float:
        return self._t2() / 1000.0

    def wait(self, sec: float):
        t0 = self._t2()
        goal = max(1, int(sec * 1000))
        while self._t2() - t0 < goal:
            self.m.run(min(200_000, 4200 * max(1, goal - (self.t2_abs - t0))))

    def close(self):
        self.m.close()


def cur_bank(s) -> int:
    s.send("dump xram 0xffff 0xffff")
    bk = s.read_until(rb"0xffff\s+([0-9a-f]{2})", 10)
    return int(re.search(r"0xffff\s+([0-9a-f]{2})", bk).group(1), 16) & 0x0F if bk else -1


def read_diag(s):
    s.send("dump xram 0xf6d0 0xf6ff")
    out = s.read_until(rb"0xf6f8 [^\n]*\n", 30)
    rows = {int(m.group(1), 16): bytes.fromhex(m.group(2).replace(" ", ""))
            for m in re.finditer(r"^0x([0-9a-f]{4})\s+((?:[0-9a-f]{2} ){8})", out or "", re.M)}
    blk = b"".join(rows.get(a, b"") for a in range(0xF6D0, 0xF700, 8))
    return blk if len(blk) == 48 else None


def boot_check(binp: Path, mapp: Path, be: bool, passes: int, max_instr: int, log) -> int:
    """PASS: diag stage 8 and the heartbeat advances `passes` (u16 wrap-safe) after it. FAIL: restart, `SJMP $` trap,
    no (stage, heartbeat) change for STALL_CHUNKS chunks, or max_instr used up. Prints last PC/bank/symbol/stage."""
    import rtd_diag
    img = binp.read_bytes()
    sym, where = parse_map(mapp.read_text(errors="replace"), img)
    gsinit = sym.get("__sdcc_gsinit_startup")
    flash = FlashPort(img)
    s = open_native(img, ROOT / "tmp/fwsim" / binp.stem, log, flash, [gsinit] if gsinit is not None else [])
    chunk, stall_chunks, done = 1_000_000, 15, 0   # 1 M instr ~ 0.35 s; startup waits (DPTx, delays) can sit 10 M instr at one stage
    starts, last, hb0, same, verdict = 0, None, None, 0, None
    d = None
    while done < max_instr and verdict is None:
        out = run_chunk(s, flash, chunk)
        done += chunk
        if out is None:
            verdict = "ucsim did not answer"; break
        stop = re.search(r"Stop at 0x([0-9a-f]+)", out)
        pc = int(stop.group(1), 16) if stop else None
        if pc is not None and pc == gsinit:
            starts += 1
            if starts > 1:
                verdict = f"RESTART (startup re-entered) after ~{done} instr"
            continue
        blk = read_diag(s)
        d = rtd_diag.decode(blk, be) if blk else None
        key = (d["stage"], d["hb"]) if d else None
        if d and d["stage"] >= 8:
            hb0 = d["hb"] if hb0 is None else hb0
            if (d["hb"] - hb0) & 0xFFFF >= passes:
                verdict = "PASS"; break
        same = same + 1 if key == last else 0
        last = key
        if re.search(r"\n0x[0-9a-f]+\s+80 fe\s+SJMP", out):
            verdict = "FAIL trap: SJMP $ at the stop PC"
        elif same >= stall_chunks:
            verdict = f"FAIL stall: no stage/heartbeat change for {stall_chunks * chunk} instr"
    bank = cur_bank(s)
    s.send("quit")
    st = d["stage"] if d else -1
    hb = d["hb"] if d else -1
    pcs = f"0x{pc:04x} bank {bank} in {where(bank, pc)}" if pc is not None else "?"
    sp = re.search(r"SP 0x([0-9a-f]+) -> ([0-9a-f]{2}) ([0-9a-f]{2})", out or "")
    if sp and verdict != "PASS":                          # @SP = PCH, @SP-1 = PCL: a caller guess (valid at a trap entered by lcall)
        r = int(sp.group(2) + sp.group(3), 16)
        pcs += f"; stack top 0x{r:04x} = {where(bank, r)} (SP 0x{sp.group(1)})"
    if verdict == "PASS":
        print(f"PASS boot-check {binp.name}: stage {st}, heartbeat {hb0} -> {hb} (+{(hb - hb0) & 0xFFFF}), "
              f"~{done} instr, flash-port reads {flash.reads}")
        return 0
    if verdict is None:
        verdict = f"FAIL budget: {max_instr} instr without {passes} heartbeats at stage 8"
    print(f"{verdict}\\nFAIL boot-check {binp.name}: last PC {pcs}; diag stage {st} heartbeat {hb}; "
          f"~{done} instr; flash-port reads {flash.reads}".replace("\\n", "\n"))
    if d:
        print(rtd_diag.report(d, None, None))
    return 1


DECISION_FNS = ("UserCommonInterfaceCheckNoSupport", "UserInterfaceGetDclkNoSupportStatus", "ScalerMDomainMemoryCheck",
                "ScalerMeasureInputActiveRegionChange", "ScalerMDomainDHVtotalFinetune", "ScalerFmtCnvFinalSetting")


def decision_stubs(m: "Machine") -> dict:
    """Watch the checks that end in NOSUPPORT (SysJudge: CheckNoSupport / DclkNoSupportStatus; M-domain: MemoryCheck,
    InputActiveRegionChange) and keep a snapshot of the values they read at each entry: fn -> [count, snapshot of the last]."""
    snaps: dict = {}

    def snap(name):
        def f(m_, r):
            c = snaps.setdefault(name, [0, None])
            c[0] += 1
            be = lambda a, n: int.from_bytes(m_.rd(m_.addr(a), n), "big")
            od = m_.rd(m_.addr("g_stMDomainOutputData"), 20)
            c[1] = {"P0_02": m_.rd(0x0002)[0], "P0_0C": m_.rd(0x000C)[0], "P0_0D": m_.rd(0x000D)[0], "P0_28": m_.rd(0x0028)[0],
                    "P30_00": m_.rd(0x3000)[0], "P31_05": m_.rd(0x3105)[0], "P31_06": m_.rd(0x3106)[0],
                    "pixclk": be("g_usInputPixelClk", 2), "dclk": be("g_ulDClkFreq", 4), "dvf": be("g_usDVFreq", 2),
                    "info": m_.rd(m_.addr("g_stMDomainInfo"), 3).hex(), "out": [int.from_bytes(od[i:i + 2], "big") for i in range(0, 20, 2)],
                    "in": m_.rd(m_.addr("g_stMDomainInputData"), 17).hex(), "tin": m_.rd(m_.addr("g_stInputTimingData"), 17).hex()}
        return f
    for n in DECISION_FNS:
        if "_" + n in m.sym:
            m.stub(n, snap(n))
    return snaps


def panel_consts() -> dict:
    """Panel / project limits the checks compare against (fw/overlay, same names as the SDK macros)."""
    out = {}
    for f in ("Panel/AWTO_LTM270FL01.h", "Project/Header/RL6449_Project.h"):
        for mt in re.finditer(r"^#define\s+(_PANEL_\w+|_OOR_\w+|_INPUTCLOCK_RANG_HDMI|_FAIL_SAVE_\w+)\s+\(?(\d+)\)?", (ROOT / "fw/overlay" / f).read_text(), re.M):
            out[mt.group(1)] = int(mt.group(2))
    return out


def decision_report(m: "Machine", snaps: dict) -> list[str]:
    """One line per decision with the inputs and the verdict; the checks are the SDK's, re-evaluated on the sim's values."""
    import unit_health as H
    k, L = panel_consts(), []
    chk = snaps.get("UserCommonInterfaceCheckNoSupport")
    if chk:
        v = chk[1]
        t = H.decode_timing(bytes.fromhex(v["tin"]))      # g_stInputTimingData (the M-domain copy is made later)
        oor = [n for n, bad in (("H freq", not k["_OOR_H_FREQ_LOWER_BOUND"] <= t["hfreq"] <= k["_OOR_H_FREQ_UPPER_BOUND"]),
                                ("V freq", t["vfreq"] > k["_OOR_V_FREQ_UPPER_BOUND"] or t["vfreq"] < k["_OOR_V_FREQ_LOWER_BOUND"]),
                                ("V height", t["vheight"] < k["_OOR_V_HEIGHT_LOWER_BOUND"]),
                                ("H width", t["hwidth"] > k["_OOR_H_WIDTH_UPPER_BOUND"]),
                                ("HDMI pixel clock", v["pixclk"] >= k["_INPUTCLOCK_RANG_HDMI"])) if bad]
        L.append(f"decision UserCommonInterfaceCheckNoSupport x{chk[0]}: {t['hwidth']}x{t['vheight']}@{t['vfreq'] / 10:.1f} "
                 f"hfreq {t['hfreq'] / 10:.1f} kHz pixclk {v['pixclk'] / 10:.1f} MHz (limit {k['_INPUTCLOCK_RANG_HDMI'] / 10:.0f}) -> "
                 f"{'NOSUPPORT: ' + ', '.join(oor) if oor else 'supported'}")
    dc = snaps.get("UserInterfaceGetDclkNoSupportStatus")
    if dc:
        v, lo, hi = dc[1], k["_PANEL_PIXEL_CLOCK_MIN"] * 1000, k["_PANEL_PIXEL_CLOCK_MAX"] * 1000
        inf = bytes.fromhex(v["info"])
        L.append(f"decision UserInterfaceGetDclkNoSupportStatus x{dc[0]}: g_ulDClkFreq {v['dclk']} kHz, panel {lo}..{hi} kHz -> "
                 f"{'NOSUPPORT (Dclk out of range)' if not lo <= v['dclk'] <= hi else 'in range'}; memory select {inf[0] & 7} "
                 f"DVF {(inf[0] >> 3) & 7} config {inf[0] >> 6} (g_stMDomainInfo {v['info']}), "
                 f"DVtotal {v['out'][5]} (panel {k['_PANEL_DV_TOTAL_MIN']}..{k['_PANEL_DV_TOTAL_MAX']})")
    mc = snaps.get("ScalerMDomainMemoryCheck")
    if mc:
        v = mc[1]
        bad = [n for n, bit in (("P0_02.6 input HV error", 0x40), ("P0_02.5 input HV error", 0x20), ("P0_02.1 FIFO overflow", 0x02),
                                ("P0_02.0 FIFO underflow", 0x01)) if v["P0_02"] & bit]
        if v["P0_0C"] & 1:
            bad.append("P0_0C.0 display vsync timeout")
        inf = bytes.fromhex(v["info"])
        lo, hi = k["_PANEL_PIXEL_CLOCK_MIN"] * 1000, k["_PANEL_PIXEL_CLOCK_MAX"] * 1000
        o = v["out"]
        L.append(f"state at MemoryCheck: g_ulDClkFreq {v['dclk']} kHz (panel {lo}..{hi}: {'in range' if lo <= v['dclk'] <= hi else 'OUT'}), "
                 f"memory select {inf[0] & 7} DVF {(inf[0] >> 3) & 7} config {inf[0] >> 6} (g_stMDomainInfo {v['info']}), "
                 f"display {o[2]}x{o[7]} total {o[0]}x{o[5]} DVF {v['dvf'] / 10:.1f} Hz (DVtotal panel "
                 f"{k['_PANEL_DV_TOTAL_MIN']}..{k['_PANEL_DV_TOTAL_MAX']}), P30_00 0x{v['P30_00']:02X} P31_05 0x{v['P31_05']:02X} "
                 f"P31_06 0x{v['P31_06']:02X} P0_28 0x{v['P0_28']:02X}")
        L.append(f"decision ScalerMDomainMemoryCheck x{mc[0]}: P0_02 0x{v['P0_02']:02X} P0_0C 0x{v['P0_0C']:02X} (last entry) -> "
                 f"{'FAIL: ' + ', '.join(bad) if bad else 'pass'}")
    ar = snaps.get("ScalerMeasureInputActiveRegionChange")
    if ar:
        L.append(f"decision ScalerMeasureInputActiveRegionChange x{ar[0]} (reads P30_41..44 vs g_ulInputActiveRegionBackUp)")
    return L


# ---- DDR2 / FRC register trace against the vendor dump (#26) -----------------------------------------------
DDR_PAGES = (0x88, 0xC8, 0x8A, 0xCA, 0x8E, 0xCE, 0x8F, 0xCF, 0xA0, 0xA8, 0x05, 0x45)      # DDR2 PLL/SYS/PHY (B = A + 0x4000 or + 0x800), FRC P5/P45
DDR_EXTRA = (*range(0x00F8, 0x0100), 0x37B0, 0x37B1)                                       # P0_F8..FF MPLL, P37_B0/B1 DDR2 client mux
DDR_FNS = ("ScalerMemoryPowerControl", "ScalerDDR2PowerControl", "ScalerPLLSetMPLLFreq", "ScalerPLLSetDDR2PLLFreq",
           "ScalerDDR2DCSysInitial", "ScalerDDR2DCPHYInitial", "ScalerMDomainControl", "ScalerMDomainMemorySettings",
           "ScalerMemoryInitial", "ScalerFRCInitial", "ScalerFRCEn", "ScalerFRCControl", "ScalerMemorySetFIFOFreq",
           "ScalerMemoryReset", "ScalerFRCInputCtrl", "ScalerFRCDisplayCtrl", "ScalerDPLLFineTuneFrameSyncFrameBuffer")


class WriteLog(Dev):
    """Ordered write log (instr, bank, pc, addr, value) of the given XDATA addresses."""

    def __init__(self, addrs):
        self.writes = tuple(sorted(set(addrs)))
        self.rows: list[tuple[int, int, int, int, int]] = []

    def on_write(self, m, a):
        mt = re.search(r"Stop at 0x([0-9a-f]+)", m.last_out)
        self.rows.append((m.instr, m.rd(0xFFFF)[0] & 15, int(mt.group(1), 16) if mt else -1, a, m.rd(a)[0]))


def vendor_pages(path: Path) -> dict[int, int]:
    import json
    pages = json.loads(path.read_text())["pages"]
    return {int(pg, 16) << 8 | i: v for pg, vals in pages.items() for i, v in enumerate(vals)}


def ddr_trace(binp: Path, mapp: Path, mode: str, max_instr: int, log, vendor: Path | None) -> int:
    """Run `mode` to its end state and log, in order: calls of the DDR2/FRC/M-domain functions, every write to the DDR2 PLL / SYS /
    PHY pages, MPLL regs and FRC pages (function named from the PC), polled status registers (static candidates, saturated count =
    polled until the firmware timeout), and the last written value of each register against the vendor 4K60 dump."""
    import fw_regs
    import unit_health as H
    img = binp.read_bytes()
    devs, hdmi = video_devs(img, mode)
    ranges = {pg << 8 | i for pg in DDR_PAGES for i in range(256)} | set(DDR_EXTRA)
    rd, _ = fw_regs.candidates(img)
    wl, rt = WriteLog(ranges), RegTrace(rd & ranges, set())
    m = Machine(img, mapp, binp.stem + "-ddr", log, [*devs, wl, rt])
    video_stubs(m, hdmi)
    m.t2_scale = T2_SCALE
    calls: list[tuple[int, str]] = []
    for fn in DDR_FNS:
        if "_" + fn in m.sym:
            m.stub(fn, lambda m_, r, fn=fn: calls.append((m_.instr, fn)) or None)
    ma, last, done, tl = m.addr("g_stModeInfo"), None, 0, []
    while done < max_instr:
        m.run(1_000_000); done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        if ms != last:
            tl.append((done, ms)); last = ms
        if ms in (H.MODE_ACTIVE, 6) and ms != 0 and any(s_ in (2, 4) for _, s_ in tl):
            break
    names = fw_regs.names()
    out = [f"ddr-trace {binp.name} mode {mode}: final {MODE_NAMES[last]} after ~{done} instr; timeline "
           + " -> ".join(f"{MODE_NAMES[s_]}@{n // 1_000_000}M" for n, s_ in tl),
           f"function calls (instr, name; {len(calls)}):"]
    out += [f"  {i:>10} {fn}" for i, fn in calls[:80]]
    out.append(f"register writes in DDR2/MPLL/FRC pages ({len(wl.rows)}); first 400 below, grouped by writer:")
    for i, b, pc, a, v in wl.rows[:400]:
        out.append(f"  {i:>10} {m.where(b, pc):<40} 0x{a:04X} {names.get(a, '?'):<34} = 0x{v:02X}")
    final_all: dict[int, int] = {}
    for _, _, _, a, v in wl.rows:
        final_all[a] = v
    out.append(f"final written value per register ({len(final_all)}): addr=value")
    out.append("  " + " ".join(f"{a:04X}={v:02X}" for a, v in sorted(final_all.items())))
    out.append("polled registers (static read candidates in these pages; n+ = polled to the cap):")
    out += ["  " + r for r in rt.report(m, names, "read")[:40]]
    if vendor:
        vend = vendor_pages(vendor)
        final: dict[int, int] = {}
        for _, _, _, a, v in wl.rows:
            final[a] = v
        diff = [(a, v, vend[a]) for a, v in sorted(final.items()) if a in vend and vend[a] != v]
        out.append(f"final written value vs vendor dump {vendor.name}: {len(final)} registers written, "
                   f"{sum(1 for a in final if a in vend and vend[a] == final[a])} equal, {len(diff)} differ:")
        out += [f"  0x{a:04X} {names.get(a, '?'):<34} ours 0x{v:02X} vendor 0x{w:02X}" for a, v, w in diff[:120]]
        reset = fw_regs.regdb_reset()
        only = [(a, w) for a, w in sorted(vend.items()) if a in ranges and a not in final and w != reset.get(a, 0)]
        out.append(f"vendor dump values != chip reset in these pages that ours never wrote ({len(only)}; status/training bits included):")
        out += [f"  0x{a:04X} {names.get(a, '?'):<34} vendor 0x{w:02X} reset 0x{reset.get(a, 0):02X}" for a, w in only[:150]]
    m.close()
    for ln in out:
        log.write(ln + "\n")
    print("\n".join(out[:2]), f"\n(full log: tmp/logs/fw_sim_ddr_<bin>_<mode>.log; {len(calls)} calls, {len(wl.rows)} writes)")
    return 0


def msg_source(mid: int) -> str:
    """AwtoMsg0/AwtoMsgV(0xID...) call site in the SDK sources (tmp/sdcc-port/src), first RL6449-relevant match."""
    root = ROOT / "tmp/sdcc-port/src/Kernel"
    pat = re.compile(r"AwtoMsg[0V]\(0x%04X\b" % mid, re.I)
    for f in sorted(root.rglob("*.c")):
        if any(x in f.parts for x in ("RL6492_Series_Scaler", "RL6463_Series_Scaler", "RL6432_Series_Scaler", "RL6410_Series_Scaler",
                                      "RL6369_Series_Scaler")):
            continue
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if pat.search(line):
                return f"{f.relative_to(root)}:{n}"
    return "?"


def video_check(binp: Path, mapp: Path, mode: str, max_instr: int, log, fault: str | None = None) -> int:
    """Boot with a stable HDMI source on D2 and report how far the mode state machine gets (#38). Exit 0 = ACTIVE."""
    import unit_health as H
    img = binp.read_bytes()
    devs, hdmi = video_devs(img, mode, fault)
    msgs: Counter = Counter()
    m = Machine(img, mapp, binp.stem + "-video", log, devs)
    video_stubs(m, hdmi)
    m.t2_scale = T2_SCALE
    snaps = decision_stubs(m)

    def am(m_, r):
        msgs[r["dptr"] & 0xFFFF] += 1                                   # watch only: AwtoMsg0/AwtoMsgV(id, value)
    for fn in ("AwtoMsg0", "AwtoMsgV"):
        m.stub(fn, am)
    ma = m.addr("g_stModeInfo")
    timeline, done, last = [], 0, None
    while done < max_instr:
        m.run(1_000_000); done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        if ms != last:
            timeline.append((done, ms)); last = ms
            if ms == H.MODE_ACTIVE:
                break
        if last == 6 and any(s_ in (2, 4) for _, s_ in timeline):      # POWER_SAVING after a failed setting: end state
            break
    t = H.decode_timing(m.rd(m.addr("g_stMDomainInputData"), 17))
    hist: Counter = Counter()
    for i in range(100):
        out = m.run(1009 if i % 2 else 1511)
        mt = re.search(r"Stop at 0x([0-9a-f]+)", out)
        if mt:
            hist[m.where(m.rd(0xFFFF)[0] & 15, int(mt.group(1), 16))] += 1
    lines = [f"video-check {binp.name} mode {mode}: final mode {last} {MODE_NAMES[last] if last < len(MODE_NAMES) else '?'} "
             f"after ~{done} instr",
             "timeline: " + " -> ".join(f"{MODE_NAMES[s]}@{n // 1_000_000}M" for n, s in timeline),
             f"g_stMDomainInputData: {t['hwidth']}x{t['vheight']}@{t['vfreq'] / 10:.1f} htotal {t['htotal']} vtotal {t['vtotal']} "
             f"hfreq {t['hfreq'] / 10:.1f} kHz",
             f"stub hits: {m.stub_hits}", *decision_report(m, snaps)]
    if last != H.MODE_ACTIVE:
        lines.append("blockers (AwtoMsg id x count @ source; top 8): " + "; ".join(
            f"0x{k:04X} x{v} @ {msg_source(k)}" for k, v in msgs.most_common(8)))
        lines.append("PC histogram (200 samples): " + ", ".join(f"{k} {v}" for k, v in hist.most_common(6)))
    m.close()
    for ln in lines:
        print(ln)
        log.write(ln + "\n")
    return 0 if last == H.MODE_ACTIVE else 1


def isr_check(binp: Path, mapp: Path, be: bool, log, want_irqs: int = 1500, max_instr: int = 60_000_000) -> int:
    """An interrupt taken with logical bank k (= __bs_cur, the bank the code thinks it is in) returns with bank register
    == __bs_cur == k and SP as before. Timer2 comes by itself; EXINT1 (IE1) is forced once per bank seen.
    Flow: vector stop -> note (__bs_cur, SP, return PC) -> tbreak at the return PC -> compare."""
    img = binp.read_bytes()
    mp = mapp.read_text(errors="replace")
    sym, where = parse_map(mp, img)
    m = re.search(r"^\s+([0-9A-F]{8})\s+__bs_cur\s", mp, re.M)
    if not m:
        print("FAIL isr-check: __bs_cur not in map"); return 1
    cur = int(m.group(1), 16)
    flash = FlashPort(img)
    s = open_native(img, ROOT / "tmp/fwsim" / binp.stem, log, flash, VECTORS)
    # trampoline switch window: __bs_cur is already the target, the bank register not yet (written at the movx). An IRQ
    # whose return PC lies inside is consistent (ISR code is common; its own stubs restore __bs_cur's bank); skip the compare.
    windows = []
    for a, b in ((sym["__bs_call"], sym["__bs_call_sw"]), (sym["__bs_ret"], sym["__bs_ret_sw"])):
        for i in range(a, b - 1):
            if img[i + 1] == cur & 0xFF and img[i] in (0xF5, 0x88, 0x89, 0x8A, 0x8B):     # mov __bs_cur,A / Rn
                windows.append((i + 2, b)); break

    def logical():
        s.send(f"dump iram 0x{cur:x} 0x{cur:x}")
        r = s.read_until(rb"\n0x%02x\s+[0-9a-f]{2} [^\n]*\n" % cur, 10)
        g = re.search(r"0x[0-9a-f]+\s+([0-9a-f]{2})", r or "")
        return int(g.group(1), 16) if g else -1

    seen, bad, injected, irqs, done = Counter(), [], set(), 0, 0
    waited, chunk, pending = 0, 1_000_000, None                   # pending = (logical bank, SP before the IRQ, return PC, vector)
    while irqs < want_irqs and done < max_instr:
        out = run_chunk(s, flash, chunk)
        if out is None:
            print("FAIL isr-check: ucsim did not answer"); return 1
        stop = re.search(r"Stop at 0x([0-9a-f]+)", out)
        done += 1000 if stop else chunk
        if not stop:
            continue
        pc = int(stop.group(1), 16)
        sp = re.search(r"SP 0x([0-9a-f]+) -> ([0-9a-f]{2}) ([0-9a-f]{2})", out)
        if pending and pc == pending[2] and (pc not in VECTORS):
            spv = int(sp.group(1), 16) if sp else -1
            if spv > pending[1]:                        # the ISR itself ran through this PC (common code): still inside it
                s.send(f"tbreak 0x{pc:x}"); continue
            bank, lg = cur_bank(s), logical()
            if any(a <= pc < b for a, b in windows):
                bank = lg = pending[0]                  # in the switch window (see above): only SP is compared
            if not (bank == lg == pending[0]) or spv != pending[1]:
                bad.append(f"vector 0x{pending[3]:02x} in logical bank {pending[0]}: back with bank reg {bank}, __bs_cur {lg}, "
                           f"SP 0x{spv:02x} (was 0x{pending[1]:02x}) at pc 0x{pc:04x}")
            seen[pending[0]] += 1; pending = None; irqs += 1
            if lg not in injected:                      # main-context point in this bank: force EXINT1 once
                injected.add(lg)
                s.send("set bit 0x8b 1")
            continue
        if pc in VECTORS and pending is not None:
            waited += 1
            if waited > 50:                             # 50 more vectors and still no return to the interrupted PC
                bad.append(f"vector 0x{pending[3]:02x} in logical bank {pending[0]}: never returned to pc 0x{pending[2]:04x} "
                           f"(SP 0x{pending[1]:02x}); now pc 0x{pc:04x} bank {cur_bank(s)}")
                break
        if pc in VECTORS and sp and pending is None:
            waited = 0    # SP in the stop text is after the push of the return PC
            ret = int(sp.group(2) + sp.group(3), 16)    # @SP = PCH, @SP-1 = PCL (see native)
            pending = (logical(), int(sp.group(1), 16) - 2, ret, pc)
            s.send(f"tbreak 0x{ret:x}")
    s.send("quit")
    print(f"isr-check {binp.name}: {irqs} interrupts returned, banks covered {sorted(seen)} of {len(img) // BANK}, "
          f"~{done} instr")
    for b in bad[:10]:
        print("FAIL", b)
    return 1 if bad or not irqs else 0


def native(a, sym, d, nb, where, log) -> int:
    """ucsim's own banker: XDATA 0xFFFF selects which 64 KiB slice of a flash chip is code memory, as on
    the RL6449. Free run; stops only at ISR vectors (PC samples) and at startup re-entry (restart = crash)."""
    s = Sim(None, log)
    s.send(f"memory create chip flash 0x{nb * BANK:x} 8")
    s.send("memory create banker xram 0xffff 0x0f rom 0x0000 0xffff")
    for k in range(nb):
        s.send(f"memory create bank rom 0x0000 {k} flash 0x{k * BANK:x}")
    for k in range(nb):                                      # loads go through the decoder into bank k
        s.send(f"set memory xram 0xffff {k}"); s.send(f'file "{d / f"bank{k}.ihx"}"')
        # "N words read" is only flushed with the next command; commands run in order, so this suffices
        if not s.read_until(rb"Loading from[^\n]*bank%d\.ihx" % k, 30):
            print(f"load of bank {k} failed (see tmp/logs/fw_sim.log)"); return 1
    s.send("set memory xram 0xffff 0"); s.send("reset")
    gsinit = sym.get("__sdcc_gsinit_startup")
    for v in (*VECTORS, *([gsinit] if gsinit is not None else [])):
        s.send(f"break 0x{v:x}")
    samples, starts, done = Counter(), 0, 0
    chunk = 5_000_000                                        # instructions per step command; ISR stops end it early
    while done < a.instr:
        s.send(f"step {chunk}")
        out = s.read_until(rb"Simulated \d+ ticks[^\n]*\n", 300)
        if out is None:
            print("ucsim did not answer within 300 s (see tmp/logs/fw_sim.log)"); return 1
        stop = re.search(r"Stop at 0x([0-9a-f]+)", out)
        done += chunk if not stop else 1000                  # stop count is unknown; progress estimate only
        if not stop:
            continue
        pc = int(stop.group(1), 16)
        s.send("dump xram 0xffff 0xffff")
        bk = s.read_until(rb"0xffff\s+([0-9a-f]{2})", 10)
        bank = int(re.search(r"0xffff\s+([0-9a-f]{2})", bk).group(1), 16) & 0x0F if bk else -1
        if gsinit is not None and pc == gsinit:
            starts += 1
            if starts > 1:
                print(f"RESTART #{starts - 1} (bank {bank}) after ~{done} instr")
                print(out[-700:]); break
            continue
        sp = re.search(r"SP 0x[0-9a-f]+ -> ([0-9a-f]{2}) ([0-9a-f]{2})", out)
        if sp:
            ipc = int(sp.group(1) + sp.group(2), 16)
            samples[f"{where(bank, ipc)} @{bank}:0x{ipc:04x}"] += 1
        if sum(samples.values()) >= a.samples:
            break
    print(f"interrupted-PC histogram ({sum(samples.values())} interrupts, ~{done} instr, restarts {max(starts - 1, 0)}):")
    for f, k in samples.most_common(10):
        print(f"  {k:5d}  {f}")
    print_diag(s)
    s.send("quit")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial")
    ap.add_argument("--boot-check", nargs=2, metavar=("BIN", "MAP"), help="offline boot-to-main-loop PASS/FAIL")
    ap.add_argument("--isr-check", nargs=2, metavar=("BIN", "MAP"), help="interrupt return-to-bank check")
    ap.add_argument("--video-check", nargs=2, metavar=("BIN", "MAP"), help="stable HDMI source on D2: how far does the mode state get")
    ap.add_argument("--mode", default="1080p60", choices=sorted(HdmiInput.MODES), help="video-check: source timing")
    ap.add_argument("--ddr-trace", nargs=2, metavar=("BIN", "MAP"), help="DDR2/FRC call + register-write trace of --mode (log only)")
    ap.add_argument("--vendor-dump", help="ddr-trace: vendor register dump json (tmp/regs/AWT26110003-20261105-180523.json)")
    ap.add_argument("--fault", choices=sorted(FAULTS), help="video-check: hardware flag the sim keeps raising (see video_devs)")
    ap.add_argument("--be", action="store_true", help="diag block big-endian (default: from '-be' in the file name)")
    ap.add_argument("--passes", type=int, default=50, help="boot-check: heartbeats to see after stage 8")
    ap.add_argument("--max-instr", type=int, default=60_000_000, help="boot-check: instruction budget")
    ap.add_argument("--budget", type=int, default=3_000_000, help="instructions without a bank switch = stall")
    ap.add_argument("--max-switches", type=int, default=20000)
    ap.add_argument("--samples", type=int, default=300, help="interrupts sampled (main-context PC) before report")
    ap.add_argument("--ex1-at", type=int, help="after N switches fake a DDC-CI request (IIC regs + IE1); "
                    "report whether EXINT1 takes the DDC-CI or the debug path")
    ap.add_argument("--legacy-banking", action="store_true",
                    help="breakpoint + ihx-reload bank model (slow; keeps the banked-call trail)")
    ap.add_argument("--instr", type=int, default=200_000_000, help="native mode: total instructions to run")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    for mode in ("boot_check", "isr_check"):
        if getattr(a, mode):
            b, m = map(Path, getattr(a, mode))
            lg = (ROOT / "tmp/logs/fw_sim.log").open("w", buffering=1)
            be = a.be or "-be" in b.name or T.BIG_ENDIAN
            return (boot_check(b, m, be, a.passes, a.max_instr, lg) if mode == "boot_check" else isr_check(b, m, be, lg))
    if a.video_check:
        b, mp_ = map(Path, a.video_check)
        return video_check(b, mp_, a.mode, a.max_instr if a.max_instr != 60_000_000 else 60_000_000,
                           (ROOT / "tmp/logs/fw_sim_video.log").open("w", buffering=1), a.fault)
    if a.ddr_trace:
        b, mp_ = map(Path, a.ddr_trace)
        return ddr_trace(b, mp_, a.mode, a.max_instr if a.max_instr != 60_000_000 else 200_000_000,
                         (ROOT / f"tmp/logs/fw_sim_ddr_{Path(a.ddr_trace[0]).stem}_{a.mode}.log").open("w", buffering=1), Path(a.vendor_dump) if a.vendor_dump else None)
    if not a.serial:
        ap.error("--serial, --boot-check, --isr-check, --video-check or --ddr-trace required")
    fw = ROOT / "tmp/fw" / a.serial
    img = (fw / "fw.bin").read_bytes()
    mp = (fw / "fw.map").read_text(errors="replace")
    sym = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(\w+)", mp, re.M)}
    funcs = sorted((v, k) for k, v in sym.items() if k.startswith("_") and not k.startswith("__bs_"))
    keys = [v for v, _ in funcs]
    common_end = int(re.search(r'"common_end":\s*(\d+)', (fw / "build.json").read_text()).group(1))
    where = lambda bank, pc: next((k for v, k in reversed(funcs[:bisect.bisect_right(
        keys, pc if pc < common_end else bank * BANK + pc)])), "?")
    d = ROOT / "tmp/fwsim" / a.serial
    d.mkdir(parents=True, exist_ok=True)
    nb = len(img) // BANK
    for k in range(nb):
        write_ihx(img[k * BANK:(k + 1) * BANK], d / f"bank{k}.ihx")
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/fw_sim.log").open("w", buffering=1)
    call, ret = sym["__bs_call"], sym["__bs_ret"]
    if not a.legacy_banking:
        return native(a, sym, d, nb, where, log)
    s = Sim(d / "bank0.ihx", log)
    s.read_until(rb"words read", 10)
    s.send(f"break 0x{call:x}"); s.send(f"break 0x{ret:x}")
    # switch the image where the hardware does: right after the 0xFFFF write (A = bank). Switching at
    # __bs_call entry went wrong when an ISR's __bs_ret ran in between (false restart, #23)
    sw = {sym[k] for k in ("__bs_call_sw", "__bs_ret_sw") if k in sym}
    for v in sw:
        s.send(f"break 0x{v:x}")
    gsinit = sym.get("__sdcc_gsinit_startup")              # 2nd entry = restart (jump/ret to 0): crash
    if gsinit is not None:
        s.send(f"break 0x{gsinit:x}")
    starts = 0
    for v in VECTORS:
        s.send(f"break 0x{v:x}")
    s.send(f"step {a.budget}")
    bank, trail, samples = 0, [], Counter()
    # EXINT1 outcome stubs (common area): DDC-CI receive path vs debug-tool path
    probes = {sym[k]: k for k in ("__bs_UserCommonInterfaceDdcciInt", "__bs_ScalerDebugIntProc_EXINT1") if k in sym}
    for n in range(a.max_switches):
        out = s.read_until(rb"Simulated \d+ ticks[^\n]*\n", 120)
        stop = re.search(r"Stop at 0x([0-9a-f]+)", out or "")
        if stop and int(stop.group(1), 16) in probes and a.ex1_at is not None and n > a.ex1_at:
            print(f"EXINT1 -> {probes[int(stop.group(1), 16)]} after {n} switches (bank {bank})")
            print("last switches:", " -> ".join(trail[-12:]))
            break
        if a.ex1_at is not None and n == a.ex1_at:
            # IIC_STATUS: SUB_I | D_IN_I; SUB_IN = 0x51 (host source addr); STATUS2 bit1 = rx buffer empty
            for cmd in ("set memory xram 0xff27 0x06", "set memory xram 0xff24 0x51",
                        "set memory xram 0xff29 0x02", "set bit 0x8b 1"):
                s.send(cmd)
            for p in probes:
                s.send(f"break 0x{p:x}")
            print(f"injected EXINT1 at switch {n}")
        if stop and gsinit is not None and int(stop.group(1), 16) == gsinit:
            starts += 1
            if starts > 1:
                print(f"RESTART #{starts - 1} after {n} switches (bank {bank}); last switches: {' -> '.join(trail[-12:])}")
                print(out[-700:])
                break
            s.send(f"step {a.budget}")
            continue
        if stop and int(stop.group(1), 16) in VECTORS:
            sp = re.search(r"SP 0x[0-9a-f]+ -> ([0-9a-f]{2}) ([0-9a-f]{2})", out)   # @SP = PCH, @SP-1 = PCL
            if sp:
                ipc = int(sp.group(1) + sp.group(2), 16)
                samples[f"{where(bank, ipc)} @{bank}:0x{ipc:04x}"] += 1
            if sum(samples.values()) >= a.samples:
                print(f"interrupted-PC histogram ({a.samples} interrupts), bank {bank}:")
                for f, k in samples.most_common(8):
                    print(f"  {k:5d}  {f}")
                print("last switches:", " -> ".join(trail[-12:]))
                break
            s.send(f"step {a.budget}")
            continue
        if out is None or "Breakpoint" not in out:
            pcs = re.findall(r"^0x([0-9a-f]{4,6}) ", out or "", re.M)
            pc = int(pcs[-1], 16) if pcs else -1
            print(f"STALL ({a.budget} instr without a bank switch) after {n} switches: bank {bank} "
                  f"pc 0x{pc:04x} in {where(bank, pc)}")
            print("last switches:", " -> ".join(trail[-12:]))
            print((out or "")[-900:])
            break
        pc = int(re.search(r"Stop at 0x([0-9a-f]+)", out).group(1), 16)
        r = re.search(r"R0 R1 R2 R3 R4 R5 R6 R7\s*\n\s*((?:[0-9a-f]{2} ){7}[0-9a-f]{2})", out)
        rv = [int(x, 16) for x in r.group(1).split()] if r else [0] * 8
        if pc == call:
            tgt = rv[1] << 8 | rv[0]
            trail.append(f"{where(rv[2], tgt)}@{rv[2]}")
        if sw:
            if pc not in sw:                                 # entry stops only record the trail
                s.send(f"step {a.budget}"); continue
            acc = re.search(r"ACC= 0x([0-9a-f]{2})", out)
            nbank = int(acc.group(1), 16) if acc else bank
        else:
            nbank = rv[2] if pc == call else rv[1]
        if nbank >= nb:
            print(f"bank {nbank} out of range at switch {n} (pc 0x{pc:x}); trail {trail[-8:]}"); break
        if nbank != bank:
            s.send(f'file "{d / f"bank{nbank}.ihx"}"'); s.read_until(rb"words read", 10); bank = nbank
        s.send(f"step {a.budget}")
    else:
        print(f"{a.max_switches} switches without a stall; last: {' -> '.join(trail[-12:])}")
    print_diag(s)
    s.send("quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
