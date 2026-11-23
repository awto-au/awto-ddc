#!/usr/bin/env python3
"""Site table of the micro-delay long-block log (fw/timer/delay.c, sync event FD): caller return PC -> bank, function, delay row.

usage: delay_sites.py BIN MAP [--resolve BB:PPPP]     writes tmp/fw/<stem>.delay_sites.tsv (generated, never edited)
  The sync line prints `BB:PPPP` = bank : return address of the `lcall _AwtoDelayXus`; this lists every such call in the image.
Log: tmp/logs/delay_sites.log
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L
import fw_sim as F
import isostamp

ROOT = F.ROOT
COMMON_BANK = 0
ROUTINES = ("AwtoDelayXus",)        # the routine with the long-block check


def sites(binp: Path, mapp: Path):
    im = L.Image(binp, mapp, str(L.layout_of(binp, ROOT)), 0x5000)
    text = mapp.read_text(errors="replace")
    out = []
    for r in ROUTINES:
        a = int(re.search(rf"^C:\s+([0-9A-F]{{8}})\s+_{r}\b", text, re.MULTILINE).group(1), 16) & 0xFFFF
        pat = re.compile(re.escape(bytes([0x12, a >> 8, a & 0xFF])), re.DOTALL)
        for c in im.chunks:
            if c["kind"] != "fn":
                continue
            code, base = im.code(c), c["addr"] & 0xFFFF
            bank = COMMON_BANK if c["addr"] < im.common else c["addr"] >> 16
            for m in pat.finditer(code):
                out.append((bank, base + m.end() + 0, c["name"].lstrip("_"), r))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("map")
    ap.add_argument("--resolve")
    a = ap.parse_args()
    binp, mapp = Path(a.bin), Path(a.map)
    rows = sites(binp, mapp)
    tsv = ROOT / "tmp/fw" / (binp.stem + ".delay_sites.tsv")
    tsv.parent.mkdir(parents=True, exist_ok=True)
    with tsv.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["bank", "return_pc", "function", "routine"])
        for bank, pc, fn, r in rows:
            w.writerow([f"{bank:02X}", f"{pc:04X}", fn, r])
    log = ROOT / "tmp/logs/delay_sites.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    msg = f"{binp.name}: {len(rows)} call sites -> {tsv}"
    log.open("a").write(f"{isostamp.now()} {msg}\n")
    print(msg)
    if a.resolve:
        bk, pc = (int(x, 16) for x in a.resolve.split(":"))
        hits = [r for r in rows if r[1] == pc and (r[0] == bk or r[0] == COMMON_BANK)]
        print("\n".join(f"{r[0]:02X}:{r[1]:04X} {r[2]} ({r[3]})" for r in hits) or "no such call site")
    return 0


if __name__ == "__main__":
    sys.exit(main())
