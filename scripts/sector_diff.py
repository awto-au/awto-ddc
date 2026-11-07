#!/usr/bin/env python3
"""usage: sector_diff.py A.bin B.bin  -> number of differing 4 KiB sectors, and how many fall in the message block (#56)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import msg_table as M
a, b = Path(sys.argv[1]).read_bytes(), Path(sys.argv[2]).read_bytes()
n = max(len(a), len(b)); a = a.ljust(n, b"\xff"); b = b.ljust(n, b"\xff")
d = [s for s in range(0, n, 4096) if a[s:s + 4096] != b[s:s + 4096]]
m = [s for s in d if M.MSG_ADDR <= s < M.MSG_ADDR + M.MSG_SIZE]
print(f"{len(d)}/{n // 4096} sectors differ, {len(m)} in the message block, {len(d) - len(m)} elsewhere")
