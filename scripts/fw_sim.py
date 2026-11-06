#!/usr/bin/env python3
"""Run the banked firmware image in ucsim with a bank-switch model, to see how far init gets.

usage: fw_sim.py --serial AWT26110003 [--budget 3000000] [--max-switches 2000]
  Default = ucsim's own banker (native). --legacy-banking predates the lcall+data stubs (target/bank in r0-r2 at
  __bs_call): it no longer reads them correctly.
  ucsim has no RL6449 bank register: breakpoints on __bs_call (bank = r2) and __bs_ret (bank = r1) load
  that bank's 64 KiB image (common area identical in every bank, so the swap is exact). Peripherals are
  not modelled (XDATA/SFR reads return RAM contents), so a wait-for-hardware loop shows up as a stall.
  Stops on: --budget instructions without a bank switch (prints PC + function from the map), or max switches.
Log: tmp/logs/fw_sim.log; per-bank ihx in tmp/fwsim/<serial>/
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
    ap.add_argument("--serial", required=True)
    ap.add_argument("--budget", type=int, default=3_000_000, help="instructions without a bank switch = stall")
    ap.add_argument("--max-switches", type=int, default=20000)
    ap.add_argument("--samples", type=int, default=300, help="interrupts sampled (main-context PC) before report")
    ap.add_argument("--ex1-at", type=int, help="after N switches fake a DDC-CI request (IIC regs + IE1); "
                    "report whether EXINT1 takes the DDC-CI or the debug path")
    ap.add_argument("--legacy-banking", action="store_true",
                    help="breakpoint + ihx-reload bank model (slow; keeps the banked-call trail)")
    ap.add_argument("--instr", type=int, default=200_000_000, help="native mode: total instructions to run")
    a = ap.parse_args()
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
