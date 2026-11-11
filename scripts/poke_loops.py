#!/usr/bin/env python3
"""Static check (awto-ddc#138 task 4): every loop that reaches a watchdog-poking helper must be bounded.

usage: poke_loops.py TREE [--out re/poke_loops.tsv]
- Poking helpers = functions whose body pokes (AWTO_WDT_FEED / AWTO_WDT_POKE / AWTO_WDT_PASS in the ported source):
  ScalerTimerDelayXms, ScalerTimerPollingFlagProc, ScalerTimerWaitForEvent, AwtoMsgWait, the SDK flash WREN / WRDis, ...
- Reach = the linked call graph (TREE/tmp/sdcc-port/asm_sel: lcall / ljmp / bank-call targets), transitively.
- Loops = for / while / do in the compiled C files (an asm_sel module of that name) and Code/*.h of linked functions; a loop pokes when its body calls a
  function that reaches a helper. Class: bounded (for with a compare on a counter; while with a counter / timeout compare),
  unbounded (constant-true condition), check (anything else: a person reads it). main's loop is the one allowed unbounded.
- Prints the table; exit 1 if an unbounded poking loop other than main's exists. Log: tmp/logs/poke_loops.log
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/poke_loops.log"
POKE_RX = re.compile(r"\bAWTO_WDT_(?:FEED|POKE|PASS)\s*\(")
FN_RX = re.compile(r"^(?:[A-Za-z_][\w \*]*?)\b([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*(?:__\w+(?:\(\w*\))?\s*)*\n?\{", re.M)
CALL_RX = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
KEYW = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case"}
TRUE_RX = re.compile(r"^\s*\(\s*(?:1|_TRUE|TRUE|0x01)\s*\)\s*$")


def strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def block_end(t: str, i: int) -> int:
    """i at '{': index after the matching '}'"""
    d = 0
    for k in range(i, len(t)):
        if t[k] == "{":
            d += 1
        elif t[k] == "}":
            d -= 1
            if d == 0:
                return k + 1
    return len(t)


def paren_end(t: str, i: int) -> int:
    d = 0
    for k in range(i, len(t)):
        if t[k] == "(":
            d += 1
        elif t[k] == ")":
            d -= 1
            if d == 0:
                return k + 1
    return len(t)


def strip_pp_off(t: str) -> str:
    """#if 0 blocks out (others kept: both arms are scanned, the call graph says what is linked)."""
    out, depth = [], 0
    for ln in t.split("\n"):
        s = ln.strip()
        if depth:
            if s.startswith("#if"):
                depth += 1
            elif s.startswith("#endif"):
                depth -= 1
            out.append("")
            continue
        if re.match(r"#\s*if\s+0\b", s):
            depth = 1
            out.append("")
            continue
        out.append(ln)
    return "\n".join(out)


def call_graph(asm_dir: Path) -> dict:
    g, cur = defaultdict(set), None
    for p in asm_dir.glob("*.asm"):
        for ln in p.read_text(errors="replace").splitlines():
            m = re.match(r"^_(\w+):", ln)
            if m:
                cur = m.group(1)
                continue
            m = re.search(r"\b(?:lcall|ljmp|acall|ajmp)\s+_(\w+)", ln) or re.search(r"mov\s+dptr,#_(\w+)\s*$", ln)
            if cur and m:
                g[cur].add(m.group(1))
    return g


def loops(body: str):
    """(offset, kind, header, loop body) for every for / while / do in a function body"""
    for m in re.finditer(r"\b(for|while|do)\b", body):
        kind, i = m.group(1), m.end()
        if kind == "do":
            j = body.find("{", i)
            if j < 0 or body[i:j].strip():
                continue
            e = block_end(body, j)
            w = re.match(r"\s*while\s*", body[e:])
            if not w:
                continue
            ps = e + w.end()
            yield m.start(), "do", body[ps:paren_end(body, ps)], body[j:e]
            continue
        ps = body.find("(", i)
        if ps < 0 or body[i:ps].strip():
            continue
        pe = paren_end(body, ps)
        hdr = body[ps:pe]
        rest = body[pe:]
        if kind == "while" and re.match(r"\s*;", rest):
            if re.search(r"\}\s*$", body[:m.start()]):           # the tail of a do-while: counted at 'do'
                continue
            yield m.start(), "while", hdr, ""
            continue
        b = re.match(r"\s*\{", rest)
        if b:
            j = pe + b.end() - 1
            yield m.start(), kind, hdr, body[j:block_end(body, j)]
        else:
            k = body.find(";", pe)
            yield m.start(), kind, hdr, body[pe:k + 1]


def classify(kind: str, hdr: str) -> str:
    if kind == "for":
        parts = hdr[1:-1].split(";")
        if len(parts) == 3 and parts[1].strip() and re.search(r"[<>]=?|!=", parts[1]):
            return "bounded"
        return "unbounded" if len(parts) == 3 and not parts[1].strip() else "check"
    if TRUE_RX.match(hdr):
        return "unbounded"
    if re.search(r"(?i)(cnt|count|timeout|retry|times|elapsed|loop|ucI|usI|ucIndex|ucTemp\w*)\s*(?:--|\+\+)?\s*[<>]=?|"
                 r"(?:--|\+\+)\s*\w*(?:cnt|count|times|retry)|\b\w+--\s*(?:!= *0|> *0|\))", hdr):
        return "bounded"
    return "check"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    src, asm = a.tree / "tmp/sdcc-port/src", a.tree / "tmp/sdcc-port/asm_sel"
    g = call_graph(asm)
    linked = set(g) | {c for v in g.values() for c in v}
    bodies = {}
    stems = {q.stem for q in asm.glob("*.asm")}           # compiled files only (other chip families share names)
    files = [q for q in sorted(src.rglob("*.c")) if q.stem in stems] + sorted(src.rglob("Code/*.h"))
    for p in files:
        t = strip_pp_off(strip_comments(p.read_text(errors="replace")))
        for m in FN_RX.finditer(t):
            name = m.group(1)
            if name in KEYW or name not in linked:
                continue
            j = m.end() - 1
            bodies.setdefault(name, (p.relative_to(src), t.count("\n", 0, j) + 1, t[j:block_end(t, j)]))
    helpers = {n for n, (_, _, b) in bodies.items() if POKE_RX.search(b)}
    reach = set(helpers)                                   # functions that reach a helper (linked graph)
    changed = True
    while changed:
        changed = False
        for f, cs in g.items():
            if f not in reach and cs & reach:
                reach.add(f); changed = True
    rows = []
    for name, (rel, line0, body) in sorted(bodies.items()):
        for off, kind, hdr, lbody in loops(body):
            called = {c for c in CALL_RX.findall(lbody + hdr) if c not in KEYW}
            hit = sorted(called & reach)
            if not hit:
                continue
            cls = classify(kind, re.sub(r"\s+", " ", hdr))
            if name == "main" and cls == "unbounded":
                cls = "main"
            rows.append((cls, f"{rel}:{line0 + body.count(chr(10), 0, off)}", name, kind, re.sub(r"\s+", " ", hdr)[:90], ",".join(hit[:4])))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    order = {"unbounded": 0, "check": 1, "main": 2, "bounded": 3}
    rows.sort(key=lambda r: (order[r[0]], r[1]))
    lines = ["class\tsite\tfunction\tloop\theader\treaches"] + ["\t".join(r) for r in rows]
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} poke_loops {a.tree}: helpers {sorted(helpers)}\n")
        for ln in lines:
            f.write(ln + "\n")
    if a.out:
        a.out.write_text("\n".join(lines) + "\n")
    print(f"poking helpers ({len(helpers)}): {', '.join(sorted(helpers))}")
    for ln in lines:
        print(ln)
    cnt = defaultdict(int)
    for r in rows:
        cnt[r[0]] += 1
    bad = cnt["unbounded"]
    print(f"poking loops: {dict(cnt)}; {'FAIL' if bad else 'ok'}: {bad} unbounded besides main, {cnt['check']} to read by hand")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
