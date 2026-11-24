#!/usr/bin/env python3
"""Console line wrap decision, the REAL firmware function on the host (fw/osd/conwrap.c AwtoConWrapBreak), no simulator.

usage: con_wrap_host.py [--src FILE] [--txt0 N] [--width N]
- Compiles fw/osd/conwrap.c with the host cc (-D__xdata=) into tmp/conwrap_host/<hash>.so and calls it through ctypes.
- Checks it against the contract (docs: the comment above the function) over every row length 0..width, text column = AWTO_LOG_TXT0
  (read from fw/osd/console.c), with: no space, one space at every position, several spaces, spaces only inside the time column,
  a space as the last cell, and a long-line corpus (the widest ring lines, gen_awto_sync.py worst case) of the real row width.
- The simulator gates (con_wrap_sim.py) stay the integration check that console.c draws what this function decides.
Log: tmp/logs/con_wrap_host.log. Exit 1 on any FAIL. ~0.1 s (the .so is cached by source hash).
"""
import argparse
import ctypes
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

import isostamp

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/con_wrap_host.log"
CC_TIMEOUT_S = 20        # one 30-line file: gcc -O1 < 0.1 s; 20 s = the project host-process stall limit's order, expiry = FAIL


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def c_int(name: str) -> int:
    return int(re.search(rf"^#define {name}\s+(\d+)", (ROOT / "fw/osd/console.c").read_text(), re.MULTILINE).group(1))


def load(src: Path):
    h = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
    so = ROOT / "tmp/conwrap_host" / f"{h}.so"
    if not so.is_file():
        so.parent.mkdir(parents=True, exist_ok=True)
        tmp = so.with_suffix(f".{h}.tmp")
        subprocess.run(["cc", "-O1", "-shared", "-fPIC", "-D__xdata=", "-o", str(tmp), str(src)], check=True, timeout=CC_TIMEOUT_S)
        tmp.replace(so)
    lib = ctypes.CDLL(str(so))
    f = lib.AwtoConWrapBreak
    f.restype = ctypes.c_ubyte
    f.argtypes = [ctypes.c_char_p, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte)]
    return f


def spec(row: bytes, n: int, t0: int):
    """(draw, drop): the last space after the text column ends the first row; none = the row edge"""
    for i in range(n - 1, t0, -1):
        if row[i:i + 1] == b" ":
            return i, i
    return n, n - 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "fw/osd/conwrap.c")
    ap.add_argument("--txt0", type=int)
    ap.add_argument("--width", type=int)
    a = ap.parse_args()
    t0_ = time.process_time()
    t0 = a.txt0 if a.txt0 is not None else 1 + c_int("AWTO_LOG_TIME_W")      # console.c: AWTO_LOG_TXT0 = 1 + AWTO_LOG_TIME_W
    width = a.width or (c_int("AWTO_CON_COLS") - 3)
    f = load(a.src)
    drop = ctypes.c_ubyte(0)
    bad, n = [], 0

    def check(row: bytes, what: str):
        nonlocal n
        n += 1
        draw = f(row, len(row), t0, ctypes.byref(drop))
        want = spec(row, len(row), t0)
        if (draw, drop.value) != want:
            bad.append(f"{what}: len {len(row)} row {row[:40]!r}: got draw {draw} drop {drop.value}, want {want[0]} {want[1]}")

    body = b"x" * width
    for ln in range(t0 + 2, width + 1):
        row = body[:ln]
        check(row, "no space")
        check(b" " * t0 + row[t0:], "spaces only in the time column")
        for p in range(t0 + 1, ln):
            check(row[:p] + b" " + row[p + 1:], f"one space at {p}")
        check(row[:ln - 1] + b" ", "space as the last cell")
        check(row[:t0 + 1] + b" " + row[t0 + 2:ln - 3] + b" " + row[:2], "two spaces")
        check(b" ".join([row[:t0], b"ab", b"cd", b"ef" * 20])[:ln], "several words")
    for txt in ("system:in DISPLAY SETTING for 16777215ms->POWER SAVING:hold L2 released:no-signal path (power-saving timers); no signal, low power, waiting for a wake",
                "line 68 test 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890"):
        check((b"%5d:" % 12345 + b" " * (t0 - 6) + txt.encode())[:width], "widest line")
    say(f"con_wrap_host {a.src.name}: txt0 {t0}, width {width}: {n} rows, {len(bad)} wrong, {time.process_time() - t0_:.2f} s CPU")
    for b in bad[:6]:
        say(f"  FAIL {b}")
    say(f"{'PASS' if not bad else 'FAIL'} con_wrap_host")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
