#!/usr/bin/env python3
"""Ghidra RE driver for the JXC 4K monitor firmware (8051, one program per 64 KB bank).

usage: ghidra_re.py import <bank|all>   create/refresh the program from banks/bank<N>.bin, seed, analyse, apply names, export
       ghidra_re.py regen  <bank|all>   apply names TSV to the existing program and re-export (daily use)
Per-bank data in re/jxc-4k/: ghidra_names_bank<N>.tsv (source of truth), seeds_bank<N>.txt (new banks: scripts/ghidra_seeds.py).
Register labels (every scaler register, XDATA (page<<8)|reg, chip RTD2795T-CG) come from re/regdb via
scripts/regdb_ghidra_labels.py (hand names win) into ./tmp/regs_bank<N>.tsv (+ ./tmp/regs_ports.tsv, data-port index
names) and are applied before the hand names.
Exports per bank in ~/vendors/realtek/analysis/jxc-4k/bank<N>/: decompiled*.c, disassembly.asm, and (re/ghidra/ExportRegAccess.java)
  regwrites.tsv / regreads.tsv: every register access site (insn, function, reg, name, kind, constant value/masks, callee).
  Columns/kinds: header of ExportRegAccess.java. Example: grep -P '\tFF3A\t|\tff3a\t' bank*/regwrites.tsv
Shared scripts (ApplyNames.java, ExportAll.java) are used from awto-2000 by path ($AWTO_2000), not copied.
Project + firmware bytes stay out of git: ~/vendors/realtek/analysis/. Log: ./tmp/logs/re_<cmd>_<bank>.log
Process: awto-dan docs/embedded/reversing/README.md
"""
import os, subprocess, sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regdb_ghidra_labels

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)
A2000 = Path(os.environ.get("AWTO_2000", "/mnt/2tb/git/awto-2000")) / "tools" / "ghidra"
VEND = Path.home() / "vendors" / "realtek" / "analysis"
PROJ_DIR, PROJ = VEND / "ghidra", "jxc4k"
LANG = "8051:BE:16:default"
CHIP = os.environ.get("RTD_CHIP", "RTD2795T-CG")   # or "consensus"
DATA = ROOT / "re" / "jxc-4k"
# Stall: Ghidra prints per phase; 120 s silence = hung. Backstop 900 s (cold bank import ~60 s measured).
STALL_S, TOTAL_S = 120, 900


def run(cmd, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    last, t0 = [time.time()], time.time()

    def pump():
        for line in p.stdout:
            last[0] = time.time(); log.write(line); log.flush()
    threading.Thread(target=pump, daemon=True).start()
    while p.poll() is None:
        time.sleep(2)
        if time.time() - last[0] > STALL_S or time.time() - t0 > TOTAL_S:
            p.kill(); log.write("\nKILLED: stall/total limit\n")
            print(f"killed: see {log_path}"); return 2
    time.sleep(0.5)
    print(f"exit {p.returncode} in {time.time()-t0:.0f}s, log {log_path}")
    return p.returncode


def main() -> int:
    cmd = sys.argv[1]
    if sys.argv[2] == "all":
        return max(one(cmd, b) for b in range(7))
    return one(cmd, int(sys.argv[2]))


def one(cmd, bank) -> int:
    name = f"bank{bank}.bin"
    tsv, seeds = DATA / f"ghidra_names_bank{bank}.tsv", DATA / f"seeds_bank{bank}.txt"
    out = VEND / "jxc-4k" / f"bank{bank}"
    out.mkdir(parents=True, exist_ok=True)
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    base = ["analyzeHeadless", str(PROJ_DIR), PROJ]
    paths = ["-scriptPath", f"{HERE.parent / 're' / 'ghidra'};{A2000}"]   # Ghidra separates with ';' on all OSes
    regs, ports = ROOT / "tmp" / f"regs_bank{bank}.tsv", ROOT / "tmp" / "regs_ports.tsv"
    regdb_ghidra_labels.write(CHIP, [tsv], regs, ports)
    tail = ["-postScript", "ApplyRegLabels.java", str(regs), "-postScript", "ApplyNames.java", str(tsv),
            "-postScript", "ExportRegAccess.java", str(out), str(ports), str(regs),
            "-postScript", "ExportAll.java", str(out), str(tsv)]
    if cmd == "import":
        c = base + ["-import", str(VEND / "banks" / name), "-overwrite", "-loader", "BinaryLoader",
                    "-loader-baseAddr", "0", "-processor", LANG] + paths + \
            ["-postScript", "SeedFile.java", str(seeds)] + tail
    elif cmd == "regen":
        c = base + ["-process", name, "-noanalysis"] + paths + tail
    else:
        return 2
    return run(c, ROOT / "tmp" / "logs" / f"re_{cmd}_bank{bank}.log")


if __name__ == "__main__":
    sys.exit(main())
