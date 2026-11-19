#!/usr/bin/env python3
"""CPU / interrupt / timer / memory conformance suite: host runner (docs/cpu-suite.md).

usage: cpu_suite.py --sim [--clocks 87,175,350] [--bin F --map F] [--cases NAME,...] [--groups T,I,M,R,D] [--allow-scratch-write]
       cpu_suite.py --bus B --serial S --map MAP [--bin BIN] ...        (unit; Phase B, test unit only, the suite image must be flashed)
  The suite image is its own build: ./dev.py build --serial S --tag cpusuite-350 -D _AWTO_CPU_SUITE -D AWTO_CLOCK_MHZ=350
  (fw/test/cpu_suite.c: main() = a mailbox loop, nothing of the monitor runs). --sim runs tmp/fw/<serial>-cpusuite-<clock>-be per clock in fw_sim (dw8051 core).
  Per run: one line PASS / FAIL with the measured numbers; log ./tmp/logs/cpu_suite.log, TSV ./tmp/logs/cpu_suite.tsv, matrix at the end.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/cpu_suite.log"
TSV = ROOT / "tmp/logs/cpu_suite.tsv"

# StAwtoCpu (fw/test/cpu_suite.c), big endian
(O_GO, O_SEQ, O_STATE, O_PASS, O_STRETCH, O_FLAGS, O_ARG, O_ARG2, O_BAD, O_V0, O_V1, O_V2, O_MS, O_CKCON, O_READY, O_RCAP, O_BEAT,
 O_STACK, O_SPMAX, O_BUFAT, O_BUFN, O_END) = (0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 26, 27, 28, 30, 32, 33, 34, 36, 38)
READY_MAGIC = 0xA5
ST_DONE, ST_BAD_CASE, ST_REFUSED = 2, 3, 4
F_WRITE, F_LIMIT = 0x01, 0x80
KEEP = 0xFF
CLOCKS = {87: 87_700, 175: 175_400, 350: 350_800}          # kHz, AWTO_CLOCK_MHZ builds (docs/delay-audit.md)
CRC_FROM, CRC_TO = 0x0100, 0x1100                          # M_CRC code region (common area)
CRC_POLY, CRC_INIT = 0x1021, 0xFFFF
SIM_READY_INSTR = 60_000_000                               # boot to the mailbox loop: measured 0.5 M instr, x120
SIM_CHUNK = 200_000
SIM_INSTR_PER_MS_DIV = 4                                   # instr per fw ms <= f_kHz / 4 (>= 4 clk per instruction), the sim budget of a run
HW_POLL_S = 0.0                                            # unit: the I2C transaction of the next poll paces the loop


@dataclass
class Run:
    label: str = ""
    arg: int = 0
    arg2: int = 0
    stretch: int = KEEP
    flags: int = 0


@dataclass
class Case:
    name: str
    cid: int
    group: str                 # T timers, I interrupts, M memory, R scaler register blocks, D SDK delay helpers
    what: str
    ref: str                   # DW8051 databook (v3.2a) rule / page
    bound_ms: int              # fw ms a run may take: stated reason in docs/cpu-suite.md
    runs: list = field(default_factory=lambda: [Run()])
    hw_note: str = ""          # expected to differ on the unit (Phase B)
    info: bool = False         # numbers only, no pass / fail from the host side


def stretch_runs(extra=()):
    return [Run(f"stretch {s}", stretch=s, **dict(extra)) for s in range(8)]


CASES = [
    Case("T_RATE0", 1, "T", "Timer0 count vs Timer2's own count over 20 one-tick windows (EA off at the sample)", "Timers 0 and 1, Mode 1 / Timer Rate Control p3-6, p3-9 (12 clk per count); Timer 2 p3-10", 60),
    Case("T_RATE1", 2, "T", "Timer1 count vs Timer2's own count, same method", "Timers 0 and 1 p3-3..3-9", 60),
    Case("T_RELOAD", 3, "T", "reload edge values 0xFFFF 0xFFFE 0xFFFC 0xFFF0 0xFF00: overflow flag sets, later = not sooner, 256 vs 16 counts ratio", "Mode 1 p3-6", 5),
    Case("T_FULL", 4, "T", "load 0x0000: 65536 counts = 65536 / (65536 - RCAP2) ticks", "Mode 1 p3-6", 40),
    Case("T_AUTORELOAD", 5, "T", "Timer1 mode 2: 20 periods of 128 counts, TL1 reloaded from TH1", "Mode 2 p3-7", 10),
    Case("T_TORN", 6, "T", "16-bit timer read while it counts: naive pair (torn count, information) vs high-low-high (must be 0)", "Mode 1 p3-6; no hardware read protection in the databook", 150,
         hw_note="naive torn count differs by timing (sim 4 %)"),
    Case("T_MS16", 7, "T", "deadline forms (now - deadline) < 0x8000 across 65535 -> 0; the real 1 ms counter injected 5 ticks before the wrap", "software; Timer2 auto-reload p3-14", 40),
    Case("T_MS32", 8, "T", "AwtoMs() across 2^32 -> 0: every tick +1 (hi word bumped by the ISR at lo wrap)", "software; Timer2 auto-reload p3-14", 40),
    Case("T_DRIFT", 9, "T", "Timer1 counts vs Timer2 counts over 200 ticks (drift; 1 ms ISR period exact)", "Timer 2 auto-reload p3-14; Mode 1 p3-6", 400, [Run("200 ticks", 200)]),
    Case("I_TRIG_EX0", 10, "I", "IE0 set by software: one EXINT0 ISR per flag, entry latency in timer counts (mean must be <= 20 us; min / max information; first 4 runs cold)", "Interrupt Processing p3-45, Latency p3-49 (5..13 instruction cycles + vector prologue)", 10,
         hw_note="latency: sim shows uncached ISR code (162 counts at 350.8 MHz); unit has the real flash cache"),
    Case("I_TRIG_T0", 11, "I", "TF0 set by software: one Timer0 ISR per flag, entry latency", "Interrupt Processing p3-45, Latency p3-49", 10, hw_note="as I_TRIG_EX0"),
    Case("I_TRIG_T1", 12, "I", "TF1 set by software: one Timer1 ISR per flag, entry latency", "Interrupt Processing p3-45, Latency p3-49", 10),
    Case("I_PRIO", 13, "I", "EXINT0 and Timer1 pending together: IP high wins, either way; same level = polling order (EXINT0 first)", "Interrupt Priorities p3-47", 5),
    Case("I_NEST", 14, "I", "high-priority EXINT0 raised inside a low-priority Timer1 ISR runs inside it; same level waits; SP high-water < 0xF0", "Interrupt Priorities p3-47", 5),
    Case("I_EA_GATE", 15, "I", "TF1 pending with EA off: no ISR; EA on: ISR starts before the 2nd store after SETB EA", "Interrupt Masking p3-46", 5),
    Case("I_EA_RACE", 16, "I", "20000 x (CLR EA .. SETB EA) against a 255-count Timer1 period: no ISR starts after the instruction following CLR EA", "Interrupt Masking p3-46, Sampling p3-48", 100),
    Case("I_STORM", 17, "I", "Timer1 interrupts at the maximum rate (10 ms) while main copies / compares XDATA and does 16-bit read-modify-writes; ISR does the same; main must progress", "RETI executes one main instruction p3-49; Dual Data Pointers p2-26", 40,
         [Run("reload 0xFF", 0xFF), Run("reload 0x40", 0x40)]),
    Case("I_ATOMIC", 18, "I", "shared u16 incremented by an ISR: naive read (torn, information) vs EA-protected read (must be monotonic); no lost increment", "software; Interrupt Masking p3-46", 40),
    Case("M_PATTERN", 20, "M", "XDATA buffer: walking 1 / 0, address-in-address, LFSR write + immediate read-back, write + N nops + read-back, pointer-increment burst copy", "Stretch Memory Cycles p2-25, Table 2-5 p2-26", 80,
         stretch_runs() + [Run("keep, no delay", arg2=1)],
         hw_note="stretch is not modelled by the sim core: every stretch passes there"),
    Case("M_GUARD", 21, "M", "16 byte buffer written in bursts under an ISR load with guard bytes around it: guards unchanged; detector self-test sees one deliberate overflow", "software (guard helper fw/test/cpu_suite.h)", 40),
    Case("M_CRC", 22, "M", "CRC-16 of code 0x0100..0x1100 read with MOVC, 3 passes: equal each pass and equal to the image bytes; second run under an ISR load", "Program Memory p2-12", 3300, [Run("quiet", 0), Run("ISR load", 1)],
         hw_note="flash fetch through the cache at 70.2 MHz: the unit may differ"),
    Case("R_READ", 30, "R", "scaler registers (read-only table, 2 per page): 64 back-to-back reads and 64 spaced reads equal the settled value, per MOVX stretch", "Stretch Memory Cycles p2-25; re/regmap (constant registers)", 1500, stretch_runs() + [Run("keep")],
         hw_note="the hypothesis under test: a block needs slow MOVX at 350.8 MHz"),
    Case("R_WRITE", 31, "R", "scratch candidates (blank-reserved, SDK-unused, 00 in every observation): write pattern, read back at once and spaced; only with --allow-scratch-write", "Stretch Memory Cycles p2-25", 60, [Run("write", flags=F_WRITE)],
         hw_note="hardware safety of each candidate is unverified: Phase B first reads the table only"),
    Case("D_XMS", 40, "D", "ScalerTimerDelayXms(n): elapsed ticks in [n, n + 2]", "software (SDK helper); Timer2 p3-10", 300, [Run(f"{n} ms", n) for n in (0, 1, 2, 10, 255, 256)],
         hw_note="65535 ms not run (65 s: no bounded reason); the sim stubs nothing here, the unit may differ in the 0 / 1 cases by one tick"),
    Case("D_5US", 41, "D", "4000 x DELAY_5US vs the timer tick (20 ms nominal): 98..118 %", "software (SDK helper)", 60, hw_note="sim: counts are not calibrated (delay cal sim row); unit expected 105 %"),
    Case("D_XUS", 42, "D", "200 x DELAY_XUS(100) vs the timer tick (20 ms nominal): 98..118 %", "software (SDK helper)", 60, hw_note="as D_5US"),
    Case("D_POLL", 43, "D", "ScalerTimerPollingFlagProc on a flag that never sets: returns after the timeout, elapsed in [n, n + 2]", "software (SDK helper)", 300, [Run(f"{n} ms", n) for n in (1, 5, 50)]),
]
BY_NAME = {c.name: c for c in CASES}


def crc16(data: bytes) -> int:
    c = CRC_INIT
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ CRC_POLY) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def say(s: str) -> None:
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


class Sim:
    """fw_sim (dw8051 core): mailbox through XDATA, time = instructions."""

    def __init__(self, binp: Path, mapp: Path, tag: str, khz: int):
        import fw_sim as S
        self.bus = S.SimBus(binp, mapp, tag, None, boot=False, devs=[S.ChipReset()])       # ChipReset = chip reset + hardware watchdog model
        self.m = self.bus.m
        self.base = self.m.addr("g_stAwtoCpu")
        self.khz = khz
        used = 0
        while used < SIM_READY_INSTR:
            self.m.run(500_000)
            used += 500_000
            if self.rd(O_READY, 1)[0] == READY_MAGIC:
                return
        raise SystemExit(f"{binp.name}: mailbox loop never came up ({used} instr)")

    def wr(self, off: int, data: bytes) -> None:
        self.m.wr(self.base + off, bytes(data))

    def rd(self, off: int, n: int) -> bytes:
        return bytes(self.m.rd(self.base + off, n))

    def xrd(self, addr: int, n: int) -> bytes:
        return bytes(self.m.rd(addr, n))

    def wait_done(self, bound_ms: int) -> bool:
        budget = int(bound_ms * 2 * self.khz / SIM_INSTR_PER_MS_DIV) + 2_000_000       # 2x: instr per ms depends on the code mix
        used = 0
        while used < budget:
            self.m.run(SIM_CHUNK)
            used += SIM_CHUNK
            if self.rd(O_GO, 1)[0] == 0:
                return True
        return False

    def close(self) -> None:
        self.bus.close()


class Unit:
    """Real unit over debug slave 0x35 (Phase B: the suite image flashed on the test unit)."""

    def __init__(self, bus: int, serial: str, mapp: Path, identity: str | None = None):
        import dbg_xdata as X
        import i2cbus
        import rtd_i2c_bridge as B
        import sw_timeline as T
        i2cbus.require_unit(bus, serial, identity)       # the suite image serves no EDID: identity = how the caller proved the bus
        self.X = X
        self.io = B.Real(bus, allow_write=True, regread=True)
        self.base = T.sym(mapp, "g_stAwtoCpu")
        self.khz = 0

    def wr(self, off: int, data: bytes) -> None:
        for i, v in enumerate(data):
            a = self.base + off + i
            if not (self.io.write(0x6A, 0x01, bytes([a >> 8])) and self.io.write(0x6A, 0x03, bytes([v])) and self.io.write(0x6A, 0x3B, bytes([a & 0xFF]))):
                raise RuntimeError(f"debug write NAK at 0x{a:04X}")

    def rd(self, off: int, n: int) -> bytes:
        for _ in range(40):
            r = self.X.read_blocks(self.io, self.base + off, n)
            if r is not None:
                return bytes(r)
        raise RuntimeError(f"debug read failed at 0x{self.base + off:04X}")

    def wait_done(self, bound_ms: int) -> bool:
        time.sleep(bound_ms / 3000.0)                      # quiet first: debug-slave traffic during a case disturbs timing cases and a read while EA is off fails (unit 1 2026-11-19)
        t0 = time.monotonic()
        limit = bound_ms * 3 / 1000 + 2.0                  # host bound: 3x the fw bound + the I2C round trips
        while time.monotonic() - t0 < limit:
            if self.rd(O_GO, 1)[0] == 0:
                return True
        return False

    def close(self) -> None:
        self.io.close()


def be(b: bytes, o: int, n: int) -> int:
    return int.from_bytes(b[o:o + n], "big")


def run_one(dev, case: Case, run: Run) -> dict:
    dev.wr(O_ARG, run.arg.to_bytes(2, "big") + run.arg2.to_bytes(2, "big"))
    dev.wr(O_STRETCH, bytes([run.stretch, run.flags]))
    seq = dev.rd(O_SEQ, 1)[0]
    dev.wr(O_GO, bytes([case.cid]))
    done = dev.wait_done(case.bound_ms)
    r = dev.rd(0, O_END)
    return dict(done=done and r[O_SEQ] != seq, state=r[O_STATE], fwpass=r[O_PASS], bad=be(r, O_BAD, 2), v0=be(r, O_V0, 4), v1=be(r, O_V1, 4), v2=be(r, O_V2, 4),
                ms=be(r, O_MS, 2), flags=r[O_FLAGS], ckcon=r[O_CKCON], rcap=be(r, O_RCAP, 2), sp=r[O_SPMAX], stack=r[O_STACK])


def judge(case: Case, run: Run, res: dict, ctx: dict) -> tuple[bool, str]:
    """(pass, note): the firmware's verdict plus the host-side checks."""
    if not res["done"]:
        return False, f"no answer within the bound ({case.bound_ms} fw ms)"
    if res["state"] == ST_REFUSED:
        return True, "SKIP refused (needs --allow-scratch-write)"
    if res["state"] != ST_DONE:
        return False, f"state {res['state']}"
    ok, note = res["fwpass"] == 1, ""
    if res["flags"] & F_LIMIT:
        ok, note = False, note + " a bounded wait expired;"
    if res["ms"] > case.bound_ms:
        ok, note = False, note + f" took {res['ms']} ms > bound {case.bound_ms};"
    if case.name == "M_CRC" and ctx.get("crc") is not None and res["v0"] != ctx["crc"]:
        ok, note = False, note + f" CRC 0x{res['v0']:04X} != image 0x{ctx['crc']:04X};"
    return ok, note.strip()


def describe(case: Case, res: dict, khz: int) -> str:
    n, v0, v1, v2 = case.name, res["v0"], res["v1"], res["v2"]
    if n in ("T_RATE0", "T_RATE1"):
        return f"counts {v0} vs Timer2 {v1}, worst window error {v2}"
    if n == "T_DRIFT":
        return f"counts {v0} vs Timer2 {v1}: drift {v2} counts over {v1 // max(1, (65536 - res['rcap']))} ms"
    if n == "T_RELOAD":
        return f"polls to overflow: 1 count {v2}, 16 counts {v0}, 256 counts {v1}"
    if n == "T_FULL":
        return f"ticks x100: {v0} (expected {v1})"
    if n == "T_AUTORELOAD":
        return f"20 periods = {v0} counts (expected {v1}), TL1 after {v2}"
    if n == "T_TORN":
        return f"torn reads: naive {v0}, protected {v1}" + (f", first protected 0x{v2 >> 16:04X} -> 0x{v2 & 0xFFFF:04X}" if v2 else "")
    if n in ("T_MS16", "T_MS32"):
        return f"last counter 0x{v0:X} (wrapped when small)"
    if n.startswith("I_TRIG"):
        us = lambda c: c * 12 / khz * 1000 if khz else 0
        return f"latency counts min {v0} max {v1} (info: holds a Timer2 ISR) mean {v2} ({us(v2):.1f} us)"
    if n == "I_PRIO":
        return f"order: IP EX0 high 0x{v0:02X}, T1 high 0x{v1:02X}, same level 0x{v2:02X}"
    if n == "I_NEST":
        return f"first inside low ISR: vec {v0}, same level: vec {v1}, SP max {v2}"
    if n == "I_EA_GATE":
        return f"main stores done at ISR entry {v0}, ISRs {v1}"
    if n == "I_EA_RACE":
        return f"ISRs {v0}, started after CLR EA: {v1}"
    if n == "I_STORM":
        return f"ISRs {v0}, main passes {v1}, bad main {v2 & 0xFFFF} isr {v2 >> 16}, SP max {res['sp']}"
    if n == "I_ATOMIC":
        return f"torn: naive {v0}, protected {v1}, reads {v2}"
    if n == "M_PATTERN":
        return f"{v0} bytes verified, CKCON 0x{res['ckcon']:02X}"
    if n == "M_GUARD":
        return f"guard bytes changed {v0}, self-test sees {v1}, passes {v2}"
    if n == "M_CRC":
        return f"CRC-16 0x{v0:04X}, ISRs {v1}"
    if n == "R_READ":
        return f"unstable registers {v0} (fast-read differs {v1}), first 0x{v2:04X}, CKCON 0x{res['ckcon']:02X}"
    if n == "R_WRITE":
        return f"scratch storage {v0}, not storage {v1}"
    if n in ("D_XMS", "D_POLL"):
        return f"elapsed {v0} ticks for {v1}"
    if n in ("D_5US", "D_XUS"):
        return f"{v0} % of nominal ({v1} ms)"
    return f"v0 {v0} v1 {v1} v2 {v2}"


def reg_blocks(dev, khz: int, run: Run, say_) -> list:
    """R_READ failed: per-entry runs, grouped by page -> list of (page, entries, bad entries)."""
    import cpu_suite_regs as G
    rd, _ = G.build()
    case = BY_NAME["R_READ"]
    bad = []
    for i, (addr, _v) in enumerate(rd):
        res = run_one(dev, case, Run(run.label, i, 1, run.stretch))
        if res["bad"] != 0:
            bad.append(addr)
    pages: dict[int, list] = {}
    for a in bad:
        pages.setdefault(a >> 8, []).append(a)
    for pg in sorted(pages):
        say_(f"    block page 0x{pg:02X}: unstable " + " ".join(f"0x{a:04X}" for a in pages[pg]))
    return sorted(pages)


def suite(dev, name: str, khz: int, cases: list, ctx: dict, rows: list, allow_write: bool) -> int:
    fails = 0
    for c in cases:
        if c.name == "R_WRITE" and not allow_write:
            say(f"[{name}] SKIP {c.name}: scratch writes are opt-in (--allow-scratch-write)")
            continue
        for run in c.runs:
            res = run_one(dev, c, run)
            ok, note = judge(c, run, res, ctx)
            tag = "PASS" if ok else "FAIL"
            lab = f" [{run.label}]" if run.label else ""
            say(f"[{name}] {tag} {c.name}{lab}: {describe(c, res, khz)}; {res['ms']} fw ms {note}".rstrip())
            if not ok:
                fails += 1
                if c.name == "R_READ" and res["done"]:
                    reg_blocks(dev, khz, run, lambda s: say(f"[{name}] {s}"))
            rows.append(dict(clock=name, case=c.name, label=run.label, stretch=run.stretch, arg=run.arg, pass_=int(ok), bad=res["bad"], v0=res["v0"], v1=res["v1"], v2=res["v2"], ms=res["ms"],
                             ckcon=res["ckcon"], note=note))
    return fails


def write_tsv(rows: list) -> None:
    keys = ["time", "clock", "case", "label", "stretch", "arg", "pass_", "bad", "v0", "v1", "v2", "ms", "ckcon", "note"]
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(keys) + "\n")
        for r in rows:
            f.write("\t".join([isostamp.now()] + [str(r.get(k, "")) for k in keys[1:]]) + "\n")


def matrix(rows: list, clocks: list) -> None:
    say("matrix (runs passed / runs) by case and clock:")
    names = [c.name for c in CASES if any(r["case"] == c.name for r in rows)]
    say("  " + "case".ljust(14) + "".join(f"{k:>10}" for k in clocks))
    for n in names:
        cells = []
        for k in clocks:
            rr = [r for r in rows if r["case"] == n and r["clock"] == k]
            cells.append(f"{sum(r['pass_'] for r in rr)}/{len(rr)}" if rr else "-")
        say("  " + n.ljust(14) + "".join(f"{x:>10}" for x in cells))


def selected(a) -> list:
    cs = CASES
    if a.groups:
        cs = [c for c in cs if c.group in a.groups.split(",")]
    if a.cases:
        want = a.cases.split(",")
        bad = [w for w in want if w not in BY_NAME]
        if bad:
            raise SystemExit(f"unknown case {bad}; known {sorted(BY_NAME)}")
        cs = [BY_NAME[w] for w in want]
    return cs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--clocks", default="87,175,350", help="sim: builds to run (tmp/fw/<serial>-cpusuite-<clock>-be.bin)")
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--bus", type=int)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--clock", type=int, default=350, help="unit: AWTO_CLOCK_MHZ of the flashed image")
    ap.add_argument("--identity", help="unit: how the bus was proven (the suite image serves no EDID, so the serial check cannot)")
    ap.add_argument("--cases")
    ap.add_argument("--groups", help="comma list of T I M R D")
    ap.add_argument("--allow-scratch-write", action="store_true", help="R_WRITE: write the generated scratch candidates (opt-in)")
    a = ap.parse_args()
    cases = selected(a)
    rows: list = []
    fails = 0
    t0 = time.monotonic()
    if a.sim:
        names = [int(x) for x in a.clocks.split(",")]
        for k in names:
            if k not in CLOCKS:
                raise SystemExit(f"--clocks: {k} not in {sorted(CLOCKS)}")
            binp = a.bin or ROOT / f"tmp/fw/{a.serial}-cpusuite-{k}-be.bin"
            mapp = a.map or binp.with_suffix(".map")
            if not binp.exists():
                raise SystemExit(f"{binp} missing: build it first (see --help); nothing run")
            img = binp.read_bytes()
            ctx = {"crc": crc16(img[CRC_FROM:CRC_TO])}
            say(f"== sim {binp.name} ({CLOCKS[k] / 1000:.1f} MHz)")
            dev = Sim(binp, mapp, f"cpus{k}", CLOCKS[k])
            try:
                fails += suite(dev, str(k), CLOCKS[k], cases, ctx, rows, a.allow_scratch_write)
            finally:
                dev.close()
        clocks = [str(k) for k in names]
    else:
        if a.bus is None or a.map is None:
            raise SystemExit("unit: --bus and --map needed (dev.py cpu-suite adds them); nothing done")
        binp = a.bin or a.map.with_suffix(".bin")
        ctx = {"crc": crc16(binp.read_bytes()[CRC_FROM:CRC_TO])} if binp.exists() else {}
        dev = Unit(a.bus, a.serial, a.map, a.identity)
        dev.khz = CLOCKS.get(a.clock, 0)
        try:
            if dev.rd(O_READY, 1)[0] != READY_MAGIC:
                raise SystemExit("the unit does not run the suite image (no ready byte): flash it first; nothing done")
            say(f"== unit {a.serial} bus {a.bus} ({a.clock} MHz build)")
            fails += suite(dev, str(a.clock), dev.khz, cases, ctx, rows, a.allow_scratch_write)
        finally:
            dev.close()
        clocks = [str(a.clock)]
    write_tsv(rows)
    matrix(rows, clocks)
    say(f"{len(rows)} runs, {fails} failed, {time.monotonic() - t0:.1f} s host wall; log {LOG}, TSV {TSV}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
