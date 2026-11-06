#!/usr/bin/env python3
"""Equivalence + speed test for the hand-written lib asm overrides in fw/asmlib/ (awto-ddc#11).

usage: asmlib_test.py [Module ...]      (no names = every fw/asmlib/tests/<Module>/)
Per module: fw/asmlib/tests/<Module>/*.c = driver (test.c: calls the asm functions and the clean-room C reference
`ref_*` from ref.c on identical inputs, prints PASS) -> sdcc -S, link against
  A) fw/asmlib/<Module>.asm (the override)            must print PASS
  B) tmp/sdcc-port/asm_vendorC/<Module>.asm (vendor C as compiled by SDCC, saved by the last full fw_build), if present:
     the same driver must also PASS (proves the reference matches the vendor C); ticks A vs B = speed change.
  deps file (optional): module names linked into variant B too.
Run: ucsim_51 -t 52, step cap 20M instr, break at _sim_halt (as sim_test.py). Flags/CFLAGS reused from sim_test.py.
Log: tmp/logs/asmlib_test.log; scratch tmp/asmlib_test/<Module>/{A,B}.  Exit 0 only if every test passes.
"""
import re, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim_test as S  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = S.ROOT
LIBDIR = ROOT / "fw/asmlib"
WORK = ROOT / "tmp/asmlib_test"
ORIG = ROOT / "tmp/sdcc-port/asm_vendorC"      # compiled vendor C, saved by fw_build.apply_asm_overrides


BENCH_N = 50      # calls per timing run; loop overhead is identical in A and B


def bench_ticks(ihx):
    """ticks until _sim_halt, no UART attached (so no serial wait), step cap 20M instr as in sim_test."""
    m = re.search(r"^C:\s+([0-9A-Fa-f]{8})\s+_sim_halt\b", ihx.with_suffix(".map").read_text(), re.M)
    r = S.subprocess.run([T.tool("ucsim_51"), "-t", "52", str(ihx)], input=f"break 0x{m.group(1)}\nstep {S.STEP_CAP}\nquit\n",
                         capture_output=True, text=True, timeout=S.SIM_TMO)
    t = re.search(r"Stop at 0x[0-9a-f]+: \(104\) Breakpoint", r.stdout)
    n = re.search(r"Simulated (\d+) ticks", r.stdout)
    return int(n.group(1)) if t and n else None


def variant(name, asm_path, srcs, w, defs=(), deps=()):
    d = w
    shutil.rmtree(d, ignore_errors=True)
    (d / "asm").mkdir(parents=True)
    inc = ["-I", str(S.RT), "-I", str(srcs[0].parent)]
    for s in srcs + [S.RT / "sim_rt.c"]:
        if S.run([T.tool("sdcc"), *S.CFLAGS, *inc, *defs, "-S", "-o", str(d / "asm" / (s.stem + ".asm")), str(s)]).returncode:
            return None, f"compile {s.name}", 0
    shutil.copy2(asm_path, d / "asm" / (name + ".asm"))
    for dep in deps:                                  # vendor-C modules the vendor-C variant calls into
        shutil.copy2(ORIG / f"{dep}.asm", d / "asm" / f"{dep}.asm")
    err = S.assemble_link(d / "asm", d / "obj", d / "out.ihx")
    if err:
        return None, err, 0
    if defs:
        return "", None, bench_ticks(d / "out.ihx")
    out, err, ticks = S.simulate(d / "out.ihx", d)
    return out, err, ticks


def main():
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    S.LOG = (ROOT / "tmp/logs/asmlib_test.log").open("a")
    tdir = LIBDIR / "tests"
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or sorted(p.name for p in tdir.iterdir() if p.is_dir())
    bad = 0
    for n in names:
        srcs = sorted((tdir / n).glob("*.c"))
        res, bench = {}, {}
        for tag, asm in (("A", LIBDIR / f"{n}.asm"), ("B", ORIG / f"{n}.asm")):
            if not asm.exists():
                continue
            deps = (tdir / n / "deps").read_text().split() if tag == "B" and (tdir / n / "deps").exists() else ()
            out, err, ticks = variant(n, asm, srcs, WORK / n / tag, deps=deps)
            ok = out is not None and "PASS" in out and S.SENTINEL in out
            res[tag] = (ok, ticks, err or (out or "")[-120:].replace("\n", " | "))
            if ok:                                    # per-function timing: test.c `// BENCH-NAMES: a,b,c`
                nm = re.search(r"BENCH-NAMES:\s*(.+)", (tdir / n / "test.c").read_text())
                bt = []
                for i, fn in enumerate(nm.group(1).split(",") if nm else [], 1):
                    _, _, t = variant(n, asm, srcs, WORK / n / f"{tag}b", [f"-DBENCH={i}", f"-DBENCH_N={BENCH_N}"], deps)
                    bt.append((fn.strip(), t))
                bench[tag] = bt
        a = res.get("A")
        okA = bool(a and a[0])
        okB = res["B"][0] if "B" in res else True
        bad += not (okA and okB)
        msg = f"{'PASS' if okA and okB else 'FAIL':5} {n}: asm={'ok' if okA else 'FAIL'}"
        if "B" in res:
            msg += f"; vendor-C ref check={'ok' if okB else 'FAIL'}"
        S.log(msg, True)
        for i, (fn, ta) in enumerate(bench.get("A", [])):
            tb = bench["B"][i][1] if "B" in bench else None
            S.log(f"  {fn}: asm {ta / 12 / BENCH_N:.0f} cycles/call" + (f", C {tb / 12 / BENCH_N:.0f}" if tb else ""), True)
        for tag, r in res.items():
            if not r[0]:
                S.log(f"  {tag}: {r[2]}", True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
