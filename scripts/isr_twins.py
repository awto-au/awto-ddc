#!/usr/bin/env python3
"""ISR-context twins (_EXINT0 / _EXINT / _WDINT) of linked functions: size, source diff, static storage (#337).

usage: isr_twins.py [--sdcc DIR] [--tsv OUT]
  --sdcc  build tree (default tmp/sdcc-port: asm/ pre-overlay, asm_bank/ linked listings, src/)
Per suffix function: linked bytes (CH_ area in the .rst), plain twin + bytes, differing source lines after
suffix normalisation, own static storage (PARM / locals / sloc), callees, whether the plain twin has any.
Log: tmp/logs/isr_twins.log
"""

import argparse
import difflib
import re
from pathlib import Path

from _log import Logger
from _repo import repo_root

ROOT = repo_root()
SUFFIX = re.compile(r"_(EXINT0|EXINT1|EXINT|WDINT)$")
AREA = re.compile(r"^\s+\d+\s+\.area\s+CH_(\w+)\s+\(CODE\)")
HEXB = re.compile(r"^\s+[0-9A-F]{6}\s+((?:[0-9A-F]{2} ?)+)\s*\[")
FUNC = re.compile(r"^;\s+function (\w+)\s*$")
CALL = re.compile(r"^\s+(?:lcall|ljmp|acall|ajmp)\s+(\w+)\s*$")
EXTRA = re.compile(r"^(\w+)(_PARM_\d+|_sloc\d+_\d+_\d+|_\w+_\d+_\d+):")


def sizes(tree: Path) -> dict:
    out = {}
    for rst in (tree / "asm_bank").glob("*.rst"):
        cur = None
        for line in rst.read_text(errors="replace").split("\n"):
            m = AREA.match(line)
            if m:
                cur = m.group(1)
                out[cur] = out.get(cur, 0)
                continue
            if cur:
                h = HEXB.match(line)
                if h:
                    out[cur] += len(h.group(1).split())
    return out


def storage_and_calls(tree: Path) -> tuple:
    """Pre-overlay asm: per function static slots (names `_fn_*:` followed by .ds) and callees."""
    stor, calls, where = {}, {}, {}
    for asm in (tree / "asm").glob("*.asm"):
        cur = None
        lines = asm.read_text(errors="replace").split("\n")
        for i, line in enumerate(lines):
            m = FUNC.match(line)
            if m:
                cur = m.group(1)
                where[cur] = asm.stem
                calls[cur] = set()
                continue
            c = CALL.match(line)
            if c and cur:
                calls[cur].add(c.group(1).lstrip("_"))
            lab = re.match(r"^_(\w+):\s*$", line)
            if lab and i + 1 < len(lines) and lines[i + 1].lstrip().startswith(".ds"):
                n = lab.group(1)
                size = int(re.findall(r"\.ds\s+(\d+)", lines[i + 1])[0])
                stor.setdefault(n, []).append((n, size))
    return stor, calls, where


def asm_funcs(tree: Path) -> dict:
    """Linked-tree asm per function, normalised: no comments, local labels / sloc / suffix names folded."""
    out = {}
    for asm in (tree / "asm_bank").glob("*.asm"):
        cur = None
        for line in asm.read_text(errors="replace").split("\n"):
            if line.startswith("\t.area") or FUNC.match(line):
                cur = None
            m = re.match(r"^_(\w+):\s*$", line)
            if m and m.group(1) in out_names:
                cur = m.group(1)
                out[cur] = []
                continue
            if cur and line.strip() and not line.lstrip().startswith(";"):
                t = re.sub(r";.*", "", line).strip()
                t = re.sub(r"\d+\$", "L", t)
                t = re.sub(r"_(EXINT0|EXINT1|EXINT|WDINT)\b", "", t)
                t = re.sub(r"_\w*sloc\d+_\d+_\d+|\b_?\w+_PARM_\d+", "SLOT", t)
                out[cur].append(re.sub(r"\s+", " ", t))
    return out


out_names = set()


def c_body(src_root: Path, name: str) -> str:
    pat = re.compile(
        r"^[A-Za-z_][\w \*]*\b" + re.escape(name) + r"\s*\([^;{]*\)\s*\n?\{",
        re.MULTILINE,
    )
    for f in src_root.rglob("*.c"):
        t = f.read_text(errors="replace")
        m = pat.search(t)
        if m:
            i, depth = t.index("{", m.start()), 0
            for j in range(i, len(t)):
                depth += (t[j] == "{") - (t[j] == "}")
                if depth == 0:
                    return t[m.start() : j + 1]
    return ""


def norm(body: str) -> list:
    body = re.sub(r"_(EXINT0|EXINT1|EXINT|WDINT)\b", "", body)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.DOTALL)
    return [re.sub(r"\s+", " ", ln).strip() for ln in body.split("\n") if ln.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdcc", default=str(ROOT / "tmp/sdcc-port"))
    ap.add_argument("--tsv", default=str(ROOT / "tmp/scratch/isr_twins.tsv"))
    a = ap.parse_args()
    log = Logger(ROOT / "tmp/logs/isr_twins.log")
    tree = Path(a.sdcc)
    sz = sizes(tree)
    stor, calls, _where = storage_and_calls(tree)
    names = sorted(n for n in calls if SUFFIX.search(n))
    out_names.update(names, (SUFFIX.sub("", n) for n in names))
    af = asm_funcs(tree)
    rows = []
    for n in names:
        plain = SUFFIX.sub("", n)
        tw = plain if plain in calls else ""
        d = ""
        if tw:
            x, y = norm(c_body(tree / "src", n)), norm(c_body(tree / "src", plain))
            d = sum(1 for t in difflib.ndiff(x, y) if t[0] in "+-")
        own = sum(s for k, v in stor.items() if k.startswith(n + "_") for _, s in v)
        twst = sum(
            s for k, v in stor.items() if tw and k.startswith(tw + "_") for _, s in v
        )
        ad = ""
        if tw and n in af and tw in af:
            ad = sum(1 for t in difflib.ndiff(af[n], af[tw]) if t[0] in "+-")
        rows.append(
            (
                n,
                sz.get(n, 0),
                tw,
                sz.get(tw, 0) if tw else "",
                d,
                ad,
                own,
                twst,
                ",".join(sorted(calls[n])),
            )
        )
    with open(a.tsv, "w") as f:
        f.write(
            "isr_fn\tbytes\tplain_twin\ttwin_bytes\tdiff_lines\tasm_diff\tisr_static_B\ttwin_static_B\tcalls\n"
        )
        f.writelines("\t".join(str(c) for c in r) + "\n" for r in rows)
    log.say(
        f"{len(rows)} suffix functions, {sum(r[1] for r in rows)} B, {sum(1 for r in rows if r[2])} with a plain twin -> {a.tsv}"
    )


if __name__ == "__main__":
    main()
