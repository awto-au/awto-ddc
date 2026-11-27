#!/usr/bin/env python3
"""One-off: renumber the # column of docs/data-channels.md table rows 1..N in file order (18a -> 19 ...)."""
import re, sys
from pathlib import Path

P = Path(sys.argv[1])
n = 0
out = []
for line in P.read_text().splitlines():
    m = re.match(r"^\| (\d+a?) \|", line)
    if m:
        n += 1
        line = re.sub(r"^\| \d+a? \|", f"| {n} |", line, count=1)
    out.append(line)
P.write_text("\n".join(out) + "\n")
print(f"{n} rows")
