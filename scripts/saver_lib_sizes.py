#!/usr/bin/env python3
"""Code / const / XDATA bytes per function of the savers and games (docs/saver-library.md inventory).

usage: saver_lib_sizes.py MAP [--mem tmp/sdcc-port/mem_report.json] [--tsv OUT]
  - Code and const: sdld areas CH_<name> (one chunk per function / const, sdcc_bank.py) + ST_<name> bank stubs (8 B), bank = address >> 16.
  - Names come from the saver sources (FILES) and the .inc files they include; a name missing from the map is not linked.
  - XDATA: per module from sdcc_mem_report.py's mem_report.json (run it on the same build first); osd_lines.c is compiled inside saver_canvas.
Log: ./tmp/logs/saver_lib_sizes.log
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
LOG = ROOT / "tmp/logs/saver_lib_sizes.log"
FILES = ["fw/test/saver_canvas.c", "tools/osd_lines/osd_lines.c", "fw/test/scope_saver2.c", "fw/test/asteroids.c", "fw/test/pacman_classic.c",
         "fw/test/snd.c", "fw/test/flash_screen.c", "fw/test/qc_osd.c", "fw/test/osd_demo.c", "fw/test/saver.c",
         "fw/osd/osd_screen.c", "fw/osd/osd_rot.c", "fw/keys/key_click.c"]
MODULE = {"tools/osd_lines/osd_lines.c": "saver_canvas"}             # compiled into this module (#include)
AREA = re.compile(r"^(CH|ST)_(\w+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+(\d+)\. bytes", re.M)
FUNC = re.compile(r"^(?:static\s+)?[A-Za-z_][\w \*]*?\b([A-Za-z_]\w*)\s*\([^;{]*\)\s*(?:__\w+\s*)*$", re.M)
CONST = re.compile(r"__code[^=;\[]*?\b([A-Za-z_]\w*)\s*\[", re.M)
INC = re.compile(r'^#include\s+"([^"]+\.inc)"', re.M)
MAP_NAME_MAX = 32                                                   # sdld cuts area names (CH_ + 29 chars)
BANK_WINDOW = 0x10000 - 0x5000                                      # banked code window 0x5000..0xFFFF (fw build: common 0x0000..0x4FFF)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def names(path: Path):
    text = re.sub(r"[ \t]*//[^\n]*", "", path.read_text(errors="replace"))
    funcs = [m.group(1) for m in FUNC.finditer(text) if m.group(1) not in ("if", "for", "while", "switch")]
    consts = [m.group(1) for m in CONST.finditer(text)]
    for inc in INC.findall(text):
        p = path.parent / inc
        if p.exists():
            consts += [m.group(1) for m in CONST.finditer(p.read_text(errors="replace"))]
    return funcs, consts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mem", type=Path, default=ROOT / "tmp/sdcc-port/mem_report.json")
    ap.add_argument("--tsv", type=Path)
    a = ap.parse_args()
    ch, st = {}, {}
    for m in AREA.finditer(a.map.read_text(errors="replace")):
        (ch if m.group(1) == "CH" else st)[m.group(2)] = (int(m.group(5)), int(m.group(3), 16) >> 16)
    xd = {}
    if a.mem.exists():
        for r in json.loads(a.mem.read_text()):
            if r["area"] in ("XSEG", "XISEG"):
                xd[r["module"]] = xd.get(r["module"], 0) + r["size"]
    rows, tot = [], {}
    for f in FILES:
        funcs, consts = names(ROOT / f)
        mod = MODULE.get(f, Path(f).stem)
        for kind, lst in (("code", funcs), ("const", consts)):
            for n in dict.fromkeys(lst):
                key = n[:MAP_NAME_MAX - 3]
                if key not in ch:
                    continue
                size, bank = ch[key]
                stub = st.get(key, (0, 0))[0]
                rows.append((f, kind, n, size, stub, bank))
                t = tot.setdefault(f, {"code": 0, "const": 0, "stub": 0})
                t[kind] += size
                t["stub"] += stub
    out = ["file\tkind\tname\tbytes\tstub\tbank"] + [f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}" for r in rows]
    if a.tsv:
        a.tsv.parent.mkdir(parents=True, exist_ok=True)
        a.tsv.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    say(f"{a.map.name}: per file code / const / stubs / XDATA (module)")
    for f, t in tot.items():
        mod = MODULE.get(f, Path(f).stem)
        say(f"  {f:34s} code {t['code']:6d}  const {t['const']:6d}  stubs {t['stub']:4d}  xdata[{mod}] {xd.get(mod, 0) if f not in MODULE else '(in module)'}")
    used = {}
    for size, bank in ch.values():
        used[bank] = used.get(bank, 0) + size
    say("  CH_ bytes per bank (banked window " + str(BANK_WINDOW) + " B): " + ", ".join(f"{b}: {used[b]} ({BANK_WINDOW - used[b]} free)" for b in sorted(used) if b > 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
