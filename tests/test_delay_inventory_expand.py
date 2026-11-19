"""delay_inventory.Eval.expand with the per-name compiled patterns gives what the plain re.sub loop gave (the speed-up of the delays gate).

Offline, no image: a made-up macro table with nested function-like macros, object macros and a name that is a substring of another.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import delay_inventory as DI

DEFS = {
    "MS(x)": "((x) * 1000)", "SEC(t)": "(MS(t) * 1)", "TWICE(a,b)": "(a + b)", "AB": "7", "A": "3", "ABC(z)": "(z + AB)",
    "_PANEL_T3": "SEC(2)", "_LONG": "TWICE(_PANEL_T3, ABC(1))",
}


def reference(ev, s, depth=0):
    """the loop as it was before: a fresh re.sub per macro name, no substring guard"""
    if depth > 12:
        return s
    prev = None
    for _ in range(12):
        if prev == s:
            break
        prev = s
        for name, (params, body) in ev.fn.items():
            s = re.sub(rf"\b{name}\s*\(([^()]*)\)", lambda m, p=params, b=body: ev._call(p, b, m.group(1)), s)
        s = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: ev.obj.get(m.group(0), m.group(0)), s)
    return s


def test_expand_matches_the_plain_loop():
    ev = DI.Eval(DEFS)
    for e in ("SEC(2)", "_LONG", "ABC(A)", "MS(AB)", "TWICE(1,2) + SEC(3)", "no macro here", "ABC(ABC(1))", "_PANEL_T3 - 10"):
        assert ev.expand(e) == reference(ev, e), e
