#!/usr/bin/env python3
"""Black-box overlay-pass test: build each fw/simtests program plain (A) and through sdcc_overlay.py (B),
run both in sdcc-ucsim_51, require identical serial output containing the sentinel (awto-ddc#10).

usage: sim_test.py [name ...]     (no names = all tests; all run even after a failure)
- Tests: fw/simtests/*.c (single file) and fw/simtests/<dir>/*.c (multi-file); `_rt/` is the shared runtime.
- Build: sdcc -S (-mmcs51 --model-large --std-sdcc11 --opt-code-size) -> sdas8051 -plosgff -> sdcc links the .rel.
- Output: program writes to SBUF (TI polled); ucsim `-S uart=0,out=FILE` captures it (flushed at quit).
- Stop: commands on stdin `break <_sim_halt>` / `step CAP` / `quit`; step ends at the breakpoint or after CAP.
  CAP = 20M instr: slowest test runs ~3.5M clocks (>=5x margin); ucsim ~9M instr/s so a runaway costs ~2 s. No sentinel = TIMEOUT.
- subprocess timeouts (build 60 s, sim 30 s) are stall backstops only: ~10x the cold worst case seen.
- Overlay pass runs with AWTO_DDC_REPO=<scratch> so its log/overlay.json don't touch the real tmp/sdcc-port.
Log: tmp/logs/sim_test.log; scratch: tmp/simtest/<name>/{A,B}.  Exit 0 only if every test PASSes.
"""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_link  # noqa: E402


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
TESTS = ROOT / "fw/simtests"
RT = TESTS / "_rt"
WORK = ROOT / "tmp/simtest"
CFLAGS = ["-mmcs51", "--model-large", "--std-sdcc11", "--opt-code-size", "--nooverlay", "--noinvariant"]   # = keil2sdcc
STEP_CAP = 20_000_000
BUILD_TMO, SIM_TMO = 60, 30
SENTINEL = "SIM-DONE"
LOG = None


def log(s, echo=False):
    LOG.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n"); LOG.flush()
    if echo:
        print(s)


def run(cmd, **kw):
    """Run, log failures; returns CompletedProcess (never raises on non-zero)."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", BUILD_TMO), **kw)
    log(f"$ {' '.join(map(str, cmd))} -> {r.returncode}")
    if r.returncode:
        log((r.stdout + r.stderr)[-2000:])
    return r


def discover():
    t = {}
    for p in sorted(TESTS.iterdir()):
        if p.name.startswith("_"):
            continue
        if p.is_file() and p.suffix == ".c":
            t[p.stem] = [p]
        elif p.is_dir():
            t[p.name] = sorted(p.glob("*.c"))
    return t


def assemble_link(asm_dir, obj_dir, ihx):
    obj_dir.mkdir(parents=True, exist_ok=True)
    rels = []
    for a in sorted(asm_dir.glob("*.asm")):
        r = run(["sdcc-sdas8051", "-plosgff", "-o", str(obj_dir / (a.stem + ".rel")), str(a)])
        if r.returncode:
            return f"assemble {a.name}"
        rels.append(str(obj_dir / (a.stem + ".rel")))
    r, _ = sdcc_link.link(["sdcc-sdcc", "-mmcs51", "--model-large", "-o", str(ihx)] + rels, ihx, rels)
    return None if r.returncode == 0 and ihx.exists() else f"link {r.stdout[-300:]}"


def simulate(ihx, outdir):
    m = re.search(r"^C:\s+([0-9A-Fa-f]{8})\s+_sim_halt\b", ihx.with_suffix(".map").read_text(), re.M)
    if not m:
        return None, "no _sim_halt in map", 0
    ser = outdir / "serial.txt"
    ser.unlink(missing_ok=True)
    cmds = f"break 0x{m.group(1)}\nstep {STEP_CAP}\nquit\n"
    r = subprocess.run(["sdcc-ucsim_51", "-t", "52", "-S", f"uart=0,out={ser}", str(ihx)],
                       input=cmds, capture_output=True, text=True, timeout=SIM_TMO)
    (outdir / "sim.log").write_text(r.stdout + r.stderr)
    ticks = re.search(r"Simulated (\d+) ticks", r.stdout)
    out = ser.read_text(errors="replace") if ser.exists() else ""
    return out, None, int(ticks.group(1)) if ticks else 0


def one(name, srcs):
    w = WORK / name
    shutil.rmtree(w, ignore_errors=True)
    asmA = w / "A/asm"
    asmA.mkdir(parents=True)
    inc = ["-I", str(RT)] + (["-I", str(srcs[0].parent)] if srcs[0].parent != TESTS else [])
    for s in srcs + [RT / "sim_rt.c"]:
        if run(["sdcc-sdcc", *CFLAGS, *inc, "-S", "-o", str(asmA / (s.stem + ".asm")), str(s)]).returncode:
            return "BUILD-FAIL", f"compile {s.name}", {}
    sloc = any("sloc" in (asmA / (s.stem + ".asm")).read_text() for s in srcs)
    ovlroot = w / "ovlroot"
    (ovlroot / "tmp/sdcc-port").mkdir(parents=True)
    asmB = w / "B/asm"
    r = run([sys.executable, str(ROOT / "scripts/sdcc_overlay.py"), "--asm", str(asmA), "--out", str(asmB)],
            env={**os.environ, "AWTO_DDC_REPO": str(ovlroot)})
    if r.returncode:
        return "BUILD-FAIL", "overlay pass rc=%d" % r.returncode, {}
    ovl = json.loads((ovlroot / "tmp/sdcc-port/overlay.json").read_text())
    info = {"sloc": sloc, "xovl": ovl["overlay_block"]["x"], "dovl": ovl["overlay_block"]["d"],
            "x_before": ovl["frames_before"]["x"], "d_before": ovl["frames_before"]["d"],
            "static_fns": ovl["kept_static_fns"], "cyclic": ovl["cyclic_fns"]}
    outs = {}
    for v, asm in (("A", asmA), ("B", asmB)):
        ihx = w / v / "out.ihx"
        err = assemble_link(asm, w / v / "obj", ihx)
        if err:
            return "BUILD-FAIL", f"{v}: {err}", info
        out, err, ticks = simulate(ihx, w / v)
        if err:
            return "BUILD-FAIL", f"{v}: {err}", info
        outs[v] = out
        info[f"cycles_{v}"] = ticks
    (w / "diff.txt").write_text(f"--- A\n{outs['A']}\n--- B\n{outs['B']}\n")
    for v in "AB":
        if SENTINEL not in outs[v]:
            return "TIMEOUT", f"{v}: no sentinel within {STEP_CAP} instr; last output: {outs[v][-60:]!r}", info
    if outs["A"] != outs["B"]:
        la, lb = outs["A"].splitlines(), outs["B"].splitlines()
        d = [f"A:{x[:30]!r} | B:{y[:30]!r}" for x, y in zip(la, lb) if x != y] or ["length differs"]
        return "FAIL", "; ".join(d[:2]), info
    return "PASS", "", info


def main():
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sim_test.log").open("a")
    tests = discover()
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    names = want or list(tests)
    log(f"sim_test: {len(names)} tests", True)
    bad = 0
    for n in names:
        t0 = time.time()
        try:
            res, why, info = one(n, tests[n])
        except subprocess.TimeoutExpired as e:
            res, why, info = "TIMEOUT", f"stall backstop: {e.cmd[0]} > {e.timeout}s", {}
        bad += res != "PASS"
        sz = (f"x {info['x_before']}->{info['xovl']} d {info['d_before']}->{info['dovl']} sloc={int(info['sloc'])}"
              f" cyc={info['cyclic']} static={info['static_fns']} cycles={info.get('cycles_A')}/{info.get('cycles_B')}") if info else ""
        log(f"{res:10} {n:14} {sz} {why}", True)
        log(f"  ({time.time() - t0:.1f}s) diff: {WORK / n / 'diff.txt'}")
    log(f"{len(names) - bad}/{len(names)} PASS", True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
