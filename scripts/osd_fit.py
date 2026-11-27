#!/usr/bin/env python3
"""OSD fit, static half: every fixed-width OSD box row in fw/osd/osd_fit.tsv against its box (build step + fw_gates osdfit).

usage: osd_fit.py [--check] [--tree DIR]
- Texts: tAwtoCardS (fw/osd/console.c, every #if part counted) by index, literals for formatted worst cases.
- Constants: #define integers of fw/osd/console.c and fw/sdk/Project/Header/RL6449_Project.h (+ - only).
- Also: every tAwtoCardS text fits a message card row (AWTO_CARD_COLS - 2 cells), unless the TSV checks it in a wider box.
- One line per row: box, text, cells used vs the limit; FAIL names the box, the text and the overflow in cells. Exit 1 on a FAIL.
- The sim half (scripts/osd_fit_sim.py + the firmware's own fit guard) covers rows formatted at run time with real inputs.
Log: tmp/logs/osd_fit.log
"""
import argparse
import re
import sys
from pathlib import Path

from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/osd_fit.log"
CONSOLE = "fw/osd/console.c"
HEADER = "fw/sdk/Project/Header/RL6449_Project.h"
TSV = "fw/osd/osd_fit.tsv"


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def defines(texts):
    """#define NAME <int expr> of the given sources -> {NAME: expr text} (comments stripped)"""
    d = {}
    for t in texts:
        for m in re.finditer(r"^#define\s+(\w+)\s+([^\n]*)$", t, re.MULTILINE):
            v = re.sub(r"//.*|/\*.*?\*/", "", m.group(2)).strip()
            if v and m.group(1) not in d:
                d[m.group(1)] = v
    return d


def evaluate(expr: str, d: dict, depth: int = 0) -> int:
    """integer of an expression of numbers, names in d, + - ( ) and (BYTE) casts"""
    if depth > 20:
        raise ValueError(f"define loop at {expr!r}")
    e = re.sub(r"\(\s*(BYTE|WORD|unsigned\s+char|unsigned\s+int)\s*\)", "", expr)
    e = re.sub(r"\b(\d+)[uUlL]+\b", r"\1", e)

    def name(m):
        n = m.group(0)
        if n not in d:
            raise ValueError(f"unknown name {n}")
        return f"({evaluate(d[n], d, depth + 1)})"
    e = re.sub(r"\b[A-Za-z_]\w*\b", name, e)
    if not re.fullmatch(r"[\d\s+\-()x]*", e):
        raise ValueError(f"not a + - expression: {expr!r}")
    return int(eval(e, {"__builtins__": {}}))        # digits, + - ( ) only (checked above)


def card_texts(src: str) -> list:
    """tAwtoCardS split at its NULs; every #if part kept (worst case: all built)"""
    m = re.search(r"tAwtoCardS\[\]\s*=(.*?);", src, re.DOTALL)
    if not m:
        raise ValueError("tAwtoCardS not found")
    body = "\n".join(ln for ln in m.group(1).splitlines() if not ln.strip().startswith("#"))
    raw = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', body))
    raw = raw.encode().decode("unicode_escape")
    parts = raw.split("\0")
    return parts[:-1] if parts and parts[-1] == "" else parts


def width(text: str, d: dict, ct: list) -> tuple:
    """(cells, shown text) of a TSV text spec"""
    total, shown = 0, []
    for tok in (t.strip() for t in text.split(" ++ ")):
        kind, _, arg = tok.partition(":")
        if kind == "lit":
            total += len(arg)
            shown.append(arg)
        elif kind == "ct":
            lo, _, hi = arg.partition("..")
            a = evaluate(lo, d)
            b = evaluate(hi, d) if hi else a
            if not 0 <= a <= b < len(ct):
                raise ValueError(f"text index {a}..{b} outside tAwtoCardS (0..{len(ct) - 1})")
            w = max(ct[a:b + 1], key=len)
            total += len(w)
            shown.append(w)
        else:
            raise ValueError(f"token {tok!r}: lit: or ct:")
    return total, "".join(shown)


def check(rows, d, ct, card_cols=None):
    """rows: (box, col, limit, text, why) -> list of (ok, line)"""
    out = []
    for box, col, limit, text, why in rows:
        try:
            c, lim = evaluate(col, d), evaluate(limit, d)
            w, shown = width(text, d, ct)
        except ValueError as e:
            out.append((False, f"FAIL {box}: {e}"))
            continue
        over = c + w - lim
        out.append((over <= 0, f"{'PASS' if over <= 0 else 'FAIL'} {box}: {shown!r} at col {c}, {w} cells, ends {c + w} of limit {lim}"
                    + (f": {over} cell(s) over" if over > 0 else "") + f" ({why})"))
    if card_cols is not None:                          # every text a centred message row could take
        lim = card_cols - 2
        for i, t in enumerate(ct):
            if len(t) > lim:
                out.append((False, f"FAIL card text {i} {t!r}: {len(t)} cells, a card row holds {lim}: {len(t) - lim} cell(s) over"))
    return out


def load_rows(p: Path):
    rows = []
    for ln in p.read_text().splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        f = ln.split("\t")
        if len(f) != 5:
            raise SystemExit(f"{p}: want 5 tab fields: {ln!r}")
        rows.append(tuple(f))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="the build / gate form (the same checks; exit 1 on a FAIL)")
    ap.add_argument("--tree", type=Path, default=ROOT)
    a = ap.parse_args()
    src = (a.tree / CONSOLE).read_text()
    d = defines([src, (a.tree / HEADER).read_text()])
    ct = card_texts(src)
    res = check(load_rows(a.tree / TSV), d, ct, evaluate("AWTO_CARD_COLS", d))
    for ok, line in res:
        if not ok or not a.check:
            say(f"  {line}")
    bad = sum(1 for ok, _ in res if not ok)
    say(f"osd_fit: {len(res)} rows, {bad} FAIL ({TSV}, {len(ct)} card texts)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
