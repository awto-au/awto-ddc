"""Placement intent from the C source (#149): `AWTO_PLACE(group=<g> | bank=<n> | common)` right above a definition.

The macro expands to nothing (fw/sdcc shim, awto-rtdfw headers); this module reads it from the sources the compiler used
(the `; <file.c>:<line>:` comments in each module's asm). The definition is the next code line: its symbol is the name
before `(` (function) or before `[` / `=` / `;` (object). sdcc_bank.py applies the rules; any bad marker stops the build.
"""
import re
from pathlib import Path

MARK = re.compile(r"^\s*AWTO_PLACE\s*\(([^)]*)\)\s*;?\s*(//.*|/\*.*\*/)?\s*$")
SRC = re.compile(r"^;\s+(/.+?\.(?:c|h|inc)):\d+:")
NAME = re.compile(r"\b([A-Za-z_]\w*)\s*(?:\(|\[|=|;)")
KEYS = ("group", "bank", "common")
INC = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


class PlaceError(Exception):
    pass


def sources(asm_dir: Path) -> list[Path]:
    """Every C source a module's asm names (absolute paths from the compiler's line comments)."""
    out = set()
    for f in sorted(Path(asm_dir).glob("*.asm")):
        for l in f.read_text(errors="replace").splitlines():
            m = SRC.match(l)
            if m:
                out.add(Path(m.group(1)))
    todo = list(out)                                          # quoted includes beside a source (generated tables, .inc)
    while todo:
        f = todo.pop()
        if not f.is_file():
            continue
        for inc in INC.findall(f.read_text(errors="replace")):
            q = (f.parent / inc).resolve()
            if q.is_file() and q not in out:
                out.add(q); todo.append(q)
    return sorted(out)


def parse_args(text: str, where: str) -> dict:
    r = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if k not in KEYS or (k == "common") == bool(v):
            raise PlaceError(f"{where}: AWTO_PLACE({text}): use group=<name>, bank=<n> or common")
        if k == "bank" and not v.isdigit():
            raise PlaceError(f"{where}: AWTO_PLACE bank={v}: not a bank number")
        r[k] = int(v) if k == "bank" else (v or True)
    if not r or ("common" in r and "bank" in r):
        raise PlaceError(f"{where}: AWTO_PLACE({text}): empty, or common together with bank")
    return r


def scan_text(text: str, path: str) -> list[dict]:
    """Rules in one file: [{sym: '_name', group|bank|common, where: 'file:line'}]."""
    lines, out = text.splitlines(), []
    for i, l in enumerate(lines):
        m = MARK.match(l)
        if not m or l.lstrip().startswith("#define"):
            continue
        where = f"{path}:{i + 1}"
        r = parse_args(m.group(1), where)
        nxt = next((x for x in lines[i + 1:i + 4] if x.strip() and not x.strip().startswith("//")), "")
        n = NAME.search(nxt.split("//", 1)[0])
        if not n or MARK.match(nxt):
            raise PlaceError(f"{where}: AWTO_PLACE is not followed by a definition (next line: {nxt.strip()[:60]!r})")
        out.append(dict(r, sym="_" + n.group(1), where=where))
    return out


def scan(paths) -> list[dict]:
    rules = []
    for p in paths:
        t = Path(p).read_text(errors="replace")
        if "AWTO_PLACE" in t:
            rules += scan_text(t, str(p))
    seen = {}
    for r in rules:
        if r["sym"] in seen:
            raise PlaceError(f"{r['where']}: {r['sym']} already placed at {seen[r['sym']]}")
        seen[r["sym"]] = r["where"]
    return rules
