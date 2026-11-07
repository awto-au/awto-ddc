#!/usr/bin/env python3
"""Classify per-function asm differences of two runs: rename-only (helper name changes) vs code changes (awto-sdcc#36).

usage: kc_asm_classify.py RUN_A RUN_B [--rename '_keil'] [--show N]
  RUN = tmp/runs/<tag> (asm/**/*.asm). A function is `rename-only` when its normalised bodies are equal after deleting
  every --rename substring from B (e.g. __divulong_keil -> __divulong); else `code`, listed with its +/- line counts.
Log: tmp/logs/kc_asm_classify.log
"""
import argparse, difflib, os, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, "/mnt/2tb/git/awto-ddc-kc/scripts")
import kc_asmdiff as K  # noqa: E402  (per-function normaliser, wb-keilcompat d3a5b5c)


def load(run: Path) -> dict:
    out = {}
    for f in sorted((run / "asm").rglob("*.asm")):
        for fn, body in K.functions(f).items():
            out[(f.name, fn)] = body
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--rename", action="append", default=[])
    ap.add_argument("--show", type=int, default=0, help="print the diff of the first N code-changed functions")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/kc_asm_classify.log").open("a")
    A, B = load(a.a), load(a.b)
    ren, code = [], []
    for k in sorted(set(A) & set(B)):
        if A[k] == B[k]:
            continue
        bb = B[k]
        for r in a.rename:
            bb = [l.replace(r, "") for l in bb]
        (ren if bb == A[k] else code).append(k)
    lines = [f"{a.a.name} -> {a.b.name}: {len(ren)} rename-only, {len(code)} code-changed, "
             f"{len(set(A) ^ set(B))} only in one run"]
    for k in code:
        d = [l for l in difflib.unified_diff(A[k], B[k], lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        lines.append(f"code\t{k[0]}\t{k[1]}\t+{sum(l[0] == '+' for l in d)} -{sum(l[0] == '-' for l in d)}")
    for k in code[:a.show]:
        lines += [f"--- {k[1]}"] + [l for l in difflib.unified_diff(A[k], B[k], lineterm="", n=1)][2:]
    for l in lines:
        print(l)
    log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} " + lines[0] + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
