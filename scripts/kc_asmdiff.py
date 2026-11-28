#!/usr/bin/env python3
"""Per-function diff of two compiler asm trees (tmp/runs/<tag>/asm), for compiler-option A/B (awto-sdcc#25, #28).

usage: kc_asmdiff.py RUN_A RUN_B [--show FN ...] [--tsv OUT] [--helpers]
  RUN = tmp/runs/<tag> (uses <run>/asm/**/*.asm). Comments, blank lines and local label numbers are normalised away.
  --helpers: helper symbols spelled alike on both sides (`___X` -> `__X`, `spx` -> `_spx`: sdcc 3e1e3c3dde / 8e21bcec5a rename).
  Prints changed functions (file, function, lines A/B, +/- line count); --show prints the unified diff of the named ones.
Log: tmp/logs/kc_asmdiff.log
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

from _repo import ROOT

FN = re.compile(r"^(_\w+):$")
LBL = re.compile(r"\b\d{5}\$")
HELPER = re.compile(r"(?<![\w$])___(?=\w)")
SPX = re.compile(r"(?<![\w$])spx\b")
NORM_HELPERS = False


def functions(asm: Path) -> dict:
    out, cur, body = {}, None, []
    area = ""
    for line in asm.read_text(errors="replace").splitlines():
        s = line.split(";", 1)[0].rstrip()
        if not s.strip():
            continue
        if s.startswith("\t.area"):
            area = s.split()[1]
        m = FN.match(s)
        if m and area.startswith(("CSEG", "BANK", "HOME")):
            if cur:
                out[cur] = body
            cur, body = m.group(1), []
            continue
        if cur:
            s = LBL.sub("L$", s)
            body.append(SPX.sub("_spx", HELPER.sub("__", s)) if NORM_HELPERS else s)
    if cur:
        out[cur] = body
    return out


def tree(run: Path) -> dict:
    res = {}
    for f in sorted((run / "asm").rglob("*.asm")):
        for fn, body in functions(f).items():
            res[(str(f.relative_to(run / "asm")), fn)] = body
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--show", nargs="*", default=[])
    ap.add_argument("--tsv")
    ap.add_argument("--helpers", action="store_true")
    a = ap.parse_args()
    global NORM_HELPERS
    NORM_HELPERS = a.helpers
    A, B = tree(Path(a.a)), tree(Path(a.b))
    rows = []
    for k in sorted(set(A) | set(B)):
        x, y = A.get(k, []), B.get(k, [])
        if x != y:
            d = list(difflib.unified_diff(x, y, lineterm="", n=2))
            plus = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
            minus = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
            rows.append((k[0], k[1], len(x), len(y), plus, minus, d))
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    with (ROOT / "tmp/logs/kc_asmdiff.log").open("a") as log:
        log.write(f"== {a.a} vs {a.b}: {len(rows)} changed of {len(set(A) | set(B))}\n")
        for r in rows:
            log.write(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\n" + "\n".join(r[6]) + "\n")
    print(f"{len(rows)} of {len(set(A) | set(B))} functions differ ({len(set(A) - set(B))} only in A, {len(set(B) - set(A))} only in B)")
    for r in rows:
        print(f"{r[0]}\t{r[1]}\tlines {r[2]}->{r[3]}\t+{r[4]} -{r[5]}")
    for r in rows:
        if r[1] in a.show:
            print("\n".join(r[6]))
    if a.tsv:
        Path(a.tsv).write_text("file\tfunction\tlines_a\tlines_b\tplus\tminus\n" +
                               "".join(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}\n" for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
