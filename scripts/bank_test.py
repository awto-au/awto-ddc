#!/usr/bin/env python3
"""Banked-call test: fw/simtests/banked built through sdcc_bank.py (modules in different banks, stubs + fw/sdcc/bank.asm),
run in ucsim with its RL6449-style banker (XDATA 0xFFFF); checks the program prints ALL-OK (awto-sdcc#2 phase 2).

usage: bank_test.py [--common 0x4000]      honours AWTO_SDCCCALL / AWTO_SDCC_BE / AWTO_SDCC_BIN (sdcc_tools.py)
- Packing: --pack-margin leaves ~256 B per bank, so each module gets its own bank; main + library stay common.
- Stop: no breakpoint (code is banked): step STEP_CAP instr, then read the serial capture. CAP = 3M instr; the program
  needs < 0.3M (uart polls), ucsim ~9M instr/s, so a hang costs < 1 s. Subprocess timeouts are backstops (30 s).
Log: tmp/logs/bank_test.log; scratch tmp/banktest/
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_build  # noqa: E402  (parse_ihx)
import sdcc_link  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
SRC = ROOT / "fw/simtests/banked"
RT = ROOT / "fw/simtests/_rt"
W = ROOT / "tmp/banktest"
BANK = 0x10000
STEP_CAP = 3_000_000
CFLAGS = ["-mmcs51", "--model-large", "--std-sdcc11", "--opt-code-size", "--nooverlay", "--noinvariant", "--constseg", "CONST", *T.CFLAGS_EXTRA]


def run(cmd, **kw):
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=30, **kw)
    with (ROOT / "tmp/logs/bank_test.log").open("a") as f:
        f.write(f"$ {' '.join(map(str, cmd))} -> {r.returncode}\n{r.stdout[-1500:]}{r.stderr[-1500:]}\n")
    if r.returncode:
        sys.exit(f"FAIL: {cmd[0]} rc={r.returncode}\n{(r.stdout + r.stderr)[-1500:]}")
    return r


def main() -> int:
    common = int(sys.argv[sys.argv.index("--common") + 1], 0) if "--common" in sys.argv else 0x4000
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    shutil.rmtree(W, ignore_errors=True)
    asm, bank = W / "asm", W / "bank"
    asm.mkdir(parents=True)
    for s in [*sorted(SRC.glob("*.c")), RT / "sim_rt.c"]:
        run([T.tool("sdcc"), *CFLAGS, "-I", RT, "-I", SRC, "-S", "-o", asm / (s.stem + ".asm"), s])
    cap = BANK - common
    run([sys.executable, ROOT / "scripts/sdcc_bank.py", "--asm", asm, "--out", bank, "--banks", 8, "--common-max", hex(common),
         "--pack-margin", hex(cap - 256), "--hot-budget", "0"])
    for extra in (ROOT / "fw/sdcc/bank.asm",):
        (bank / extra.name).write_text(extra.read_text())
    # linker orders areas by first appearance: pin common CONST right after CSEG, before the BANKn areas
    (bank / "0areas.asm").write_text("\t.module areas\n" + "".join(f"\t.area {a}    (CODE)\n" for a in (
        "HOME", "GSINIT0", "GSINIT1", "GSINIT2", "GSINIT3", "GSINIT4", "GSINIT5", "GSINIT", "GSFINAL", "CSEG", "CONST", "XINIT")))
    rels = []
    for a in sorted(bank.glob("*.asm")):
        run([T.tool("sdas8051"), "-plosgffw", bank / (a.stem + ".rel"), a])
        rels.append(bank / (a.stem + ".rel"))
    used = sorted({int(m) for r in rels for m in re.findall(r"^A BANK(\d+) ", r.read_text(errors="replace"), re.M)})
    wl = [f"-Wl-aBANK{n}=0x{n * BANK + common:x}" for n in used]
    ihx = W / "out.ihx"
    r, _ = sdcc_link.link([T.tool("sdcc"), "-mmcs51", "--model-large", *T.CFLAGS_EXTRA, "--code-loc", "0", "--code-size", "0x100000",
                           f"-L{T.LIB}", "-Wl-aDSEG=0x30", *wl, "-o", ihx, *rels], ihx, rels)
    if r.returncode or not ihx.exists():
        sys.exit("FAIL link: " + "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Library:" not in l and "found more than once" not in l)[-1500:])
    mem = fw_build.parse_ihx(ihx)
    cend = max((x for x in mem if x < common), default=0) + 1
    nb = max(used, default=0) + 1
    img = bytearray(b"\xff" * (nb * BANK))
    for k in range(nb):
        for x in range(cend):
            if x in mem:
                img[k * BANK + x] = mem[x]
    for x, v in mem.items():
        if x >= common:
            img[x] = v
    for k in range(nb):
        fw_build_ihx = W / f"bank{k}.ihx"
        import fw_sim
        fw_sim.write_ihx(bytes(img[k * BANK:(k + 1) * BANK]), fw_build_ihx)
    ser = W / "serial.txt"
    cmds = [f"memory create chip flash 0x{nb * BANK:x} 8", "memory create banker xram 0xffff 0x0f rom 0x0000 0xffff"]
    for k in range(nb):
        cmds.append(f"memory create bank rom 0x0000 {k} flash 0x{k * BANK:x}")
    for k in range(nb):
        cmds += [f"set memory xram 0xffff {k}", f'file "{W / f"bank{k}.ihx"}"']
    cmds += ["set memory xram 0xffff 0", "reset", f"step {STEP_CAP}", "quit"]
    r = subprocess.run([T.tool("ucsim_51"), "-t", "52", "-S", f"uart=0,out={ser}"], input="\n".join(cmds) + "\n",
                       capture_output=True, text=True, timeout=30)
    (W / "sim.log").write_text(r.stdout + r.stderr)
    out = ser.read_text(errors="replace") if ser.exists() else ""
    sw = sum(1 for k in range(nb))
    ok = "ALL-OK" in out and "SIM-DONE" in out and "FAIL" not in out
    print(f"{'PASS' if ok else 'FAIL'} banked: {nb} banks (common {cend} B), {len(re.findall('__bs_', ''.join(p.read_text() for p in bank.glob('*.asm'))))} stub refs; "
          f"serial: {out.strip()[:200]!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
