#!/usr/bin/env python3
"""Run the banked firmware image in ucsim with a bank-switch model, to see how far init gets.

usage: fw_sim.py --serial AWT26110003 [--budget 3000000] [--max-switches 2000]
  ucsim has no RL6449 bank register: breakpoints on __bs_call (bank = r2) and __bs_ret (bank = r1) load
  that bank's 64 KiB image (common area identical in every bank, so the swap is exact). Peripherals are
  not modelled (XDATA/SFR reads return RAM contents), so a wait-for-hardware loop shows up as a stall.
  Stops on: --budget instructions without a bank switch (prints PC + function from the map), or max switches.
       fw_sim.py --boot-check BIN MAP [--be|--le] [--passes 50]   offline PASS/FAIL: boot to the main loop (#11, #38)
       fw_sim.py --isr-check BIN MAP                              interrupts in every bank return to that bank
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


class Sim:
    def __init__(self, ihx, log):
        self.p = subprocess.Popen([T.tool("ucsim_51"), "-t", "52", *([str(ihx)] if ihx else [])], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
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
    funcs = sorted((v, k) for k, v in sym.items() if k.startswith("_") and not k.startswith("__bs_"))
    keys = [v for v, _ in funcs]
    nb = len(img) // BANK
    cend = 0
    while cend < BANK and all(img[k * BANK + cend] == img[cend] for k in range(1, nb)):
        cend += 1
    where = lambda bank, pc: next((k for v, k in reversed(funcs[:bisect.bisect_right(
        keys, pc if pc < cend or bank == 0 else bank * BANK + pc)])), "?")
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
    if not a.serial:
        ap.error("--serial, --boot-check or --isr-check required")
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
