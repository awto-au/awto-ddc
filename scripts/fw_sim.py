#!/usr/bin/env python3
"""Run the banked firmware image in ucsim with a bank-switch model, to see how far init gets.

usage: fw_sim.py --serial AWT26110003 [--budget 3000000] [--max-switches 2000]
  ucsim has no RL6449 bank register: breakpoints on __bs_call (bank = r2) and __bs_ret (bank = r1) load
  that bank's 64 KiB image (common area identical in every bank, so the swap is exact). Peripherals are
  not modelled (XDATA/SFR reads return RAM contents), so a wait-for-hardware loop shows up as a stall.
  Stops on: --budget instructions without a bank switch (prints PC + function from the map), or max switches.
Log: tmp/logs/fw_sim.log; per-bank ihx in tmp/fwsim/<serial>/
"""
import argparse, bisect, os, re, select, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
BANK = 0x10000


def write_ihx(data: bytes, path: Path):
    out = []
    for a in range(0, len(data), 16):
        ch = data[a:a + 16]                              # all bytes: a bank swap must overwrite the old one
        rec = bytes([len(ch), a >> 8, a & 0xFF, 0]) + ch
        out.append(":" + rec.hex().upper() + "%02X" % ((-sum(rec)) & 0xFF))
    path.write_text("\n".join(out + [":00000001FF"]) + "\n")


class Sim:
    def __init__(self, ihx, log):
        self.p = subprocess.Popen(["sdcc-ucsim_51", "-t", "52", str(ihx)], stdin=subprocess.PIPE,
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--budget", type=int, default=3_000_000, help="instructions without a bank switch = stall")
    ap.add_argument("--max-switches", type=int, default=2000)
    a = ap.parse_args()
    fw = ROOT / "tmp/fw" / a.serial
    img = (fw / "fw.bin").read_bytes()
    mp = (fw / "fw.map").read_text(errors="replace")
    sym = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(\w+)", mp, re.M)}
    funcs = sorted((v, k) for k, v in sym.items() if k.startswith("_") and not k.startswith("__bs_"))
    keys = [v for v, _ in funcs]
    where = lambda bank, pc: next((k for v, k in reversed(funcs[:bisect.bisect_right(keys, bank * BANK + pc)])
                                   if v >> 16 in (bank, 0)), "?")
    d = ROOT / "tmp/fwsim" / a.serial
    d.mkdir(parents=True, exist_ok=True)
    nb = len(img) // BANK
    for k in range(nb):
        write_ihx(img[k * BANK:(k + 1) * BANK], d / f"bank{k}.ihx")
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/fw_sim.log").open("w")
    call, ret = sym["__bs_call"], sym["__bs_ret"]
    s = Sim(d / "bank0.ihx", log)
    s.read_until(rb"words read", 10)
    s.send(f"break 0x{call:x}"); s.send(f"break 0x{ret:x}")
    s.send(f"step {a.budget}")
    bank, trail = 0, []
    for n in range(a.max_switches):
        out = s.read_until(rb"Simulated \d+ ticks[^\n]*\n", 120)
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
        nbank = rv[2] if pc == call else rv[1]
        if pc == call:
            tgt = rv[1] << 8 | rv[0]
            trail.append(f"{where(nbank, tgt)}@{nbank}")
        if nbank >= nb:
            print(f"bank {nbank} out of range at switch {n} (pc 0x{pc:x}); trail {trail[-8:]}"); break
        if nbank != bank:
            s.send(f'file "{d / f"bank{nbank}.ihx"}"'); s.read_until(rb"words read", 10); bank = nbank
        s.send(f"step {a.budget}")
    else:
        print(f"{a.max_switches} switches without a stall; last: {' -> '.join(trail[-12:])}")
    s.send("quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
