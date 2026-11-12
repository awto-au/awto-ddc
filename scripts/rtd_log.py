#!/usr/bin/env python3
"""Decode an existing raw I2C log (old tool logs, *.raw.log) into readable lines after the fact.

usage: rtd_log.py FILE [FILE ...] [--map fw.map] [--chip RTD2795T-CG] [--merge-pages] [-o OUT]
  Lines `<ts> REAL write|read dev=0x.. reg 0x.. ..` are decoded (scripts/rtd_proto.py); every other line is
  passed through unchanged, so old mixed logs (rtd_diag.log, rtd_dbg_read.log) read top to bottom.
  `-` reads stdin. Output: stdout, or -o OUT (e.g. tmp/logs/<name>.decoded.log). Reads files only, no bus access.
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto as P  # noqa: E402


def decode_lines(lines, out, map_path=None, chip="RTD2795T-CG", merge_pages=False, root=None):
    root = root or P.repo_root()
    dec = P.Decoder(lambda ts, tag, text: out.write(f"{ts} {tag:<4} {text}\n"), P.Symbols.load(root, map_path),
                    P.regdb_namer(chip), P.load_msgids(root), merge_pages)
    for line in lines:
        if not dec.feed_raw_line(line):
            dec.flush()
            out.write(line if line.endswith("\n") else line + "\n")
    dec.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--map")
    ap.add_argument("--chip", default="RTD2795T-CG")
    ap.add_argument("--merge-pages", action="store_true", help="merge contiguous page programs into one line")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    out = open(a.out, "w") if a.out else sys.stdout
    for f in a.files:
        src = sys.stdin if f == "-" else open(f, errors="replace")
        decode_lines(src, out, a.map, a.chip, a.merge_pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
