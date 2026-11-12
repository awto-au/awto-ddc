#!/usr/bin/env python3
"""Make build options unconditional: resolve `#if` on fixed option values in place and drop the option's #define (#165).

usage: unifdef_opt.py NAME=ON|OFF [NAME=ON|OFF ...] -- FILE [FILE ...]
- Terms `(NAME == _ON)`, `(NAME != _OFF)`, `defined(NAME)` ... are replaced by 1 / 0; a constant condition removes the
  directive and the dead group, a partly constant one is simplified (`(1) && (X)` -> `(X)`) and kept.
- `#ifdef NAME` / `#ifndef NAME` resolve too (the option counts as defined); `#define NAME ...` lines are dropped.
- Groups inside a dropped group are dropped unparsed. Directives with `\\` continuations are joined for parsing.
Log: ./tmp/logs/unifdef_opt.log (one line per file: directives resolved / simplified, lines removed).
"""
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def subst(cond: str, vals: dict) -> str:
    for n, v in vals.items():
        on = "1" if v else "0"
        off = "0" if v else "1"
        cond = re.sub(rf"\(\s*{n}\s*==\s*_ON\s*\)", on, cond)
        cond = re.sub(rf"\(\s*{n}\s*!=\s*_OFF\s*\)", on, cond)
        cond = re.sub(rf"\(\s*{n}\s*==\s*_OFF\s*\)", off, cond)
        cond = re.sub(rf"\(\s*{n}\s*!=\s*_ON\s*\)", off, cond)
        cond = re.sub(rf"\bdefined\s*\(\s*{n}\s*\)", "1", cond)
        cond = re.sub(rf"\bdefined\s+{n}\b", "1", cond)
        if re.search(rf"\b{n}\b", cond):
            raise ValueError(f"{n} in a form not handled: {cond!r}")
    return cond


def strip_parens(e: str) -> str:
    e = e.strip()
    while e.startswith("(") and e.endswith(")"):
        d = 0
        for i, ch in enumerate(e):
            d += (ch == "(") - (ch == ")")
            if d == 0 and i < len(e) - 1:
                return e
        e = e[1:-1].strip()
    return e


def split_top(e: str, op: str):
    parts, d, cur, i = [], 0, "", 0
    while i < len(e):
        if e[i] in "(":
            d += 1
        elif e[i] == ")":
            d -= 1
        if d == 0 and e.startswith(op, i):
            parts.append(cur); cur = ""; i += len(op); continue
        cur += e[i]; i += 1
    parts.append(cur)
    return [p.strip() for p in parts]


def simplify(e: str):
    """-> True / False (constant) or a simplified expression string."""
    e = strip_parens(e)
    if e in ("1", "0"):
        return e == "1"
    if e.startswith("!") and strip_parens(e[1:]) in ("1", "0"):
        return strip_parens(e[1:]) == "0"
    for op, unit, zero in (("||", False, True), ("&&", True, False)):
        parts = split_top(e, op)
        if len(parts) > 1:
            out = []
            for p in parts:
                s = simplify(p)
                if s is zero:
                    return zero
                if s is not unit:
                    out.append(s if isinstance(s, str) else ("1" if s else "0"))
            if not out:
                return unit
            if len(out) == 1:
                return out[0]
            return f" {op} ".join(f"({strip_parens(p)})" for p in out)
    return e


def fmt_cond(kw: str, s: str, tail: str) -> str:
    return f"#{kw}({strip_parens(s)})" + (f"{tail}" if tail else "")


DIR = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif|define)\b(.*)$")


def process(text: str, vals: dict):
    lines = text.split("\n")
    out, stack, stats = [], [], {"resolved": 0, "simplified": 0}
    i = 0
    keep = lambda: all(f["keep"] for f in stack)
    while i < len(lines):
        raw = [lines[i]]
        while raw[-1].endswith("\\") and i + 1 < len(lines):
            i += 1; raw.append(lines[i])
        i += 1
        full = " ".join(r[:-1] if r.endswith("\\") else r for r in raw)
        m = DIR.match(full)
        if not m:
            if keep():
                out.extend(raw)
            continue
        kw, rest = m.group(1), m.group(2)
        body, tail = rest, ""
        cm = re.search(r"\s*(//.*|/\*.*\*/\s*)$", rest)
        if cm:
            body, tail = rest[:cm.start()], rest[cm.start():]
        if kw == "define":
            dm = re.match(r"\s+(\w+)", rest)
            if keep() and not (dm and dm.group(1) in vals):
                out.extend(raw)
            continue
        if kw in ("if", "ifdef", "ifndef"):
            if not keep():
                stack.append({"keep": False, "dead": True}); continue
            if kw == "if":
                sb = subst(body, vals)
                s = simplify(sb) if sb != body else body
            else:
                n = body.strip()
                s = (kw == "ifdef") if n in vals else None
            if isinstance(s, bool):
                stats["resolved"] += 1
                stack.append({"keep": s, "res": True, "taken": s, "dead": False}); continue
            if kw == "if" and strip_parens(s) != strip_parens(body):
                stats["simplified"] += 1
                out.append(fmt_cond("if", s, tail))
            else:
                out.extend(raw)
            stack.append({"keep": True, "res": False, "closed": False, "dead": False}); continue
        f = stack[-1]
        if f["dead"]:
            if kw == "endif":
                stack.pop()
            continue
        if kw == "elif":
            sb = subst(body, vals)
            s = simplify(sb) if sb != body else body
            if f["res"]:
                if f["taken"]:
                    f["keep"] = False
                elif isinstance(s, bool):
                    f["keep"] = s; f["taken"] = s
                else:                                   # first live group of a resolved chain: becomes the #if
                    out.append(fmt_cond("if", s, tail)); f.update(res=False, closed=False, keep=True, opened=True)
            else:
                if f["closed"]:
                    f["keep"] = False
                elif s is True:
                    out.append("#else" + tail); f.update(keep=True, closed=True)
                elif s is False:
                    f["keep"] = False
                else:
                    out.append(fmt_cond("elif", s, tail) if strip_parens(s) != strip_parens(body) else full)
                    f["keep"] = True
            continue
        if kw == "else":
            if f["res"]:
                f["keep"] = not f["taken"]; f["taken"] = True
            elif f["closed"]:
                f["keep"] = False
            else:
                out.extend(raw); f["keep"] = True
            continue
        if kw == "endif":
            stack.pop()
            if not f["res"]:
                out.extend(raw)
            continue
    if stack:
        raise ValueError("unbalanced #if")
    return "\n".join(out), stats


def main() -> int:
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/unifdef_opt.log").open("a")
    a = sys.argv[1:]
    if "--" not in a:
        print(__doc__); return 2
    k = a.index("--")
    vals = {}
    for nv in a[:k]:
        n, v = nv.split("=")
        vals[n] = {"ON": True, "OFF": False}[v]
    for f in a[k + 1:]:
        p = Path(f)
        t = p.read_text(encoding="latin-1")
        new, st = process(t, vals)
        if new != t:
            p.write_text(new, encoding="latin-1")
            log(f"{f}: {st['resolved']} resolved, {st['simplified']} simplified, "
                f"{t.count(chr(10)) - new.count(chr(10))} lines removed ({vals})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
