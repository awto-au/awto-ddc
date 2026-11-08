#!/usr/bin/env python3
"""Build-time check: every character of every UI string exists in the font (awto/osd/charset.txt), and the tile budget holds.

usage: tools/check_font.py [--list]
  Scans the string literals of awto/**/*.c, the registry labels / options / notes shown on screen (settings/registry.tsv label,
  options) and settings/pages.tsv titles. A character missing from charset.txt is an error naming the file and string.
  Runtime-built text (numbers, 'x', '@', '.', ':', '%', '/' ...) is covered by RUNTIME below. Exit 1 on any miss, or if tools/gen_font.py
  needs more than 256 tiles. Log: ./tmp/logs/check_font.log
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_RTDFW_REPO") or Path(__file__).resolve().parents[1])
RUNTIME = "0123456789 .:@x%-*<>^v?"          # built at run time: values, units, timing, markers, scroll arrows
LOG = ROOT / "tmp/logs/check_font.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    print(s)
    with LOG.open("a") as f:
        f.write(s + "\n")


def strings():
    """(where, text)"""
    out = []
    lit = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
    for p in sorted((ROOT / "awto").rglob("*.c")):
        if p.name == "set_table.c":                      # generated text pool: the registry / pages files below are its source
            continue
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if line.lstrip().startswith("#include") or line.lstrip().startswith("//"):
                continue
            for m in lit.finditer(line):
                out.append((f"{p.relative_to(ROOT)}:{n}", m.group(1).encode().decode("unicode_escape")))
    for p in (ROOT / "settings/registry.tsv", ROOT / "settings/pages.tsv"):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if line.startswith("#") or not line.strip():
                continue
            f = line.split("\t")
            if p.name == "registry.tsv" and len(f) > 14:
                out.append((f"settings/registry.tsv:{n}", f[13]))
                for o in f[14].split("|"):
                    out.append((f"settings/registry.tsv:{n}", re.sub(r"=0x[0-9A-Fa-f]+$", "", o) if o != "-" else ""))
            elif p.name == "pages.tsv":
                out.append((f"settings/pages.tsv:{n}", f[1]))
    return out


def main():
    cs = set((ROOT / "awto/osd/charset.txt").read_text().replace("\n", "")) | set(RUNTIME)
    bad = {}
    for where, text in strings():
        for ch in text:
            if ch not in cs:
                bad.setdefault(ch, []).append((where, text))
    for ch, uses in sorted(bad.items()):
        say(f"MISSING {ch!r} (0x{ord(ch):02X}) in the font: {uses[0][0]} \"{uses[0][1]}\"" + (f" (+{len(uses) - 1} more)" if len(uses) > 1 else ""))
    if "--list" in sys.argv:
        say("charset: " + "".join(sorted(cs)))
    say(f"check_font: {len(strings())} strings, {len(cs)} characters in the set, {len(bad)} missing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
