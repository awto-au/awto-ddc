"""`#pragma place` (awto-sdcc#141, awto-ddc#149): compiler asm -> plain CSEG / CONST sections plus a `;@place` marker.

The compiler puts a placed definition into its own area (`PLACE_<g>` for group(g), `BANK<n>` for bank(n); `common` stays CSEG).
Every build pass after the compile (overlay, ISR libs, bank, link check) keys on CSEG / CONST, so normalise() rewrites those
sections right after the compile and leaves `;@place group=<g>` / `;@place bank=<n>` before each placed definition.
sdcc_bank.py reads the markers (Module.parse): the group's chunks go to one bank, a pinned chunk to its bank.
"""
import re
from pathlib import Path

AREA = re.compile(r"^\s*\.area\s+(PLACE_(\w+)|BANK(\d+))\s*\(CODE\)\s*$")
ANY_AREA = re.compile(r"^\s*\.area\b")
FUNC = re.compile(r"^;\s+function \w+\s*$")
MARK = re.compile(r"^;@place (group|bank)=(\w+)\s*$")


def normalise_text(text: str) -> tuple[str, int]:
    """(rewritten asm, placed sections): each PLACE_<g> / BANK<n> section becomes CSEG (function) or CONST (data) + marker."""
    lines = text.split("\n")
    out, n, i = [], 0, 0
    while i < len(lines):
        m = AREA.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not ANY_AREA.match(lines[j]):
            j += 1
        func = any(FUNC.match(x) for x in lines[i + 1:j])
        out.append("\t.area CSEG    (CODE)" if func else "\t.area CONST   (CODE)")
        out.append(f";@place group={m.group(2)}" if m.group(2) else f";@place bank={m.group(3)}")
        out.extend(lines[i + 1:j])
        n += 1
        i = j
    return "\n".join(out), n


def normalise(path: Path) -> int:
    """In place; returns the number of placed sections. No placed section: the file is not touched."""
    t = Path(path).read_text(errors="replace")
    if "PLACE_" not in t and ".area BANK" not in t:
        return 0
    new, n = normalise_text(t)
    if n:
        Path(path).write_text(new)
    return n
