#!/usr/bin/env python3
"""Compare SDCC code size of SDK modules under flag variants (no link): sum CSEG+CONST from .rel headers.

usage: sdcc_size_probe.py [--n 40] [--jobs 16] [--sdcc BIN] VARIANT=FLAGS ...
  e.g. base= medium=--model-medium allocs=--max-allocs-per-node=100000
  Sample = the N largest C files of STD_FW_1P.Uv2 target RL6449_Project (ported tree, tmp/sdcc-port/src).
  FLAGS are appended after fw_compile's flags (last --model wins). Modules failing in any variant are dropped.
Log: tmp/logs/sdcc_size_probe.log; objects in tmp/sizeprobe/<variant>/
"""
import argparse, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_compile as K  # noqa: E402

UV2, TARGET = "STD_FW_1P.Uv2", "RL6449_Project"
# one large module compiles in ~60 s cold under 16 jobs; 3x backstop per global host-process rule
TIMEOUT = 200


def size_of(rel: Path):
    t = rel.read_text(errors="replace")
    return sum(int(m.group(2), 16) for m in re.finditer(r"^A (CSEG|CONST) size ([0-9A-Fa-f]+)", t, re.M))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--sdcc", default=K.SDCC)
    a = ap.parse_args()
    (K.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    logf = (K.ROOT / "tmp/logs/sdcc_size_probe.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); logf.write(line + "\n"); logf.flush()
    uv2 = K.SRC / UV2
    files, defines, incs, model = K.parse_uv2(uv2, TARGET)
    cs = sorted(((uv2.parent / f).resolve() for f in files), key=lambda p: p.stat().st_size if p.exists() else 0,
                reverse=True)[:a.n]
    variants = [v.split("=", 1) for v in a.variants]
    log(f"sdcc={a.sdcc} sample={len(cs)} variants={variants}")
    res = {}

    def one(job):
        (name, flags), c = job
        out = K.ROOT / "tmp/sizeprobe" / name / (c.stem + ".rel")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = K.sdcc_cmd(c, uv2.parent, defines, incs, model) + flags.split() + ["-c", "-o", str(out), str(c)]
        cmd[0] = a.sdcc
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
            ok = r.returncode == 0 and out.exists()
        except subprocess.TimeoutExpired:
            log(f"TIMEOUT {TIMEOUT}s: {name} {c.name}"); ok = False
        return name, c.stem, size_of(out) if ok else None
    with ThreadPoolExecutor(a.jobs) as ex:
        for name, stem, sz in ex.map(one, [(v, c) for v in variants for c in cs]):
            res.setdefault(stem, {})[name] = sz
    good = {s: d for s, d in res.items() if all(d.get(n) for n, _ in variants)}
    log(f"{len(good)}/{len(res)} modules compiled in every variant")
    base = sum(d[variants[0][0]] for d in good.values())
    for n, f in variants:
        tot = sum(d[n] for d in good.values())
        log(f"{n:12s} {tot:8d} B  {100.0 * tot / base:6.1f}%  flags: {f or '(fw_compile defaults)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
