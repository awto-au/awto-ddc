#!/usr/bin/env python3
"""Delete C function definitions + their one-line prototypes by name (#209 strip of unlinked SDK code).

usage: strip_funcs.py FILE.c [--from-tsv tmp/logs/dead_code.tsv | NAME ...] [--headers DIR] [--write]
  Definition = a line at column 0 naming the function followed by '(' (not a ';' prototype), through the matching '}'
  (comments, strings and char literals skipped while counting braces), plus the `//` comment block right above it.
  Prototypes = single-line `[extern] ... NAME(...);` in FILE and in every .h under --headers (default fw/sdk).
  --from-tsv: the names dead_code.py lists for FILE's source path. Without --write: report only.
  Then: scripts/warn_rekey.py --write, build, gates (dead code only: the build proves nothing live referenced it).
Log: ./tmp/logs/strip_funcs.log
"""
import argparse
import os
import re
import sys
from pathlib import Path

from _log import log_line as _log_line

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/strip_funcs.log"


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def code_only(text: str) -> str:
    """Same length, comments / strings / char literals blanked (braces inside them don't count)."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i); j = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2); j = n if j < 0 else j + 2
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            j += 1
        else:
            i += 1; continue
        for k in range(i, min(j, n)):
            if out[k] != "\n":
                out[k] = " "
        i = j
    return "".join(out)


def find_def(text: str, code: str, name: str):
    """(start, end) of NAME's definition incl. the // block above, or None."""
    for m in re.finditer(rf"^[A-Za-z_][^\n;{{}}]*\b{re.escape(name)}\s*\(", code, re.MULTILINE):
        brace = code.find("{", m.end())
        semi = code.find(";", m.end())
        if brace < 0 or (0 <= semi < brace):
            continue                                   # a prototype / call, not a definition
        depth, j = 0, brace
        while j < len(code):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        end = code.find("\n", j); end = len(text) if end < 0 else end + 1
        start = m.start()
        lines = text[:start].split("\n")[:-1]          # header comment: contiguous `//` lines right above
        k = len(lines)
        while k > 0 and lines[k - 1].lstrip().startswith("//"):
            k -= 1
        if k < len(lines):
            start = len("\n".join(lines[:k])) + (1 if k else 0)
        return start, end
    return None


def strip_protos(text: str, names: set) -> tuple[str, int]:
    pat = re.compile(r"^[ \t]*(?:extern[ \t]+)?[A-Za-z_][^\n;(){}]*\b(" + "|".join(map(re.escape, names)) + r")\s*\([^;{}]*\)\s*;[^\n]*\n", re.MULTILINE)
    return pat.subn("", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--from-tsv", type=Path)
    ap.add_argument("--headers", type=Path, default=ROOT / "fw/sdk")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    names = set(a.names)
    if a.from_tsv:
        rel = a.file.resolve().relative_to(ROOT / "fw/sdk").as_posix() if a.file.resolve().is_relative_to(ROOT / "fw/sdk") else a.file.as_posix()
        for l in a.from_tsv.read_text().splitlines()[1:]:
            src, fn = l.split("\t")
            if src == rel:
                names.add(fn.lstrip("_"))
    text = a.file.read_text(errors="replace")
    gone, missing = [], []
    for nm in sorted(names):
        code = code_only(text)
        span = find_def(text, code, nm)
        if span is None:
            missing.append(nm); continue
        text = text[:span[0]] + text[span[1]:]
        gone.append(nm)
    text, np = strip_protos(text, set(gone)) if gone else (text, 0)
    say(f"{a.file.name}: {len(gone)} definitions removed, {np} prototypes in the file; not found: {missing or '-'}")
    hdr_hits = []
    if gone:
        for h in sorted(a.headers.rglob("*.h")):
            t = h.read_text(errors="replace")
            t2, k = strip_protos(t, set(gone))
            if k:
                hdr_hits.append((h, t2, k))
        say(f"  header prototypes: {sum(k for *_, k in hdr_hits)} in {len(hdr_hits)} files")
    if a.write:
        a.file.write_text(text)
        for h, t2, _ in hdr_hits:
            h.write_text(t2)
    else:
        say("  report only (--write to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
