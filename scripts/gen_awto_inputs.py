#!/usr/bin/env python3
"""Generate the input-monitor C tables from fw/awto/inputs.tsv (the one source for firmware, screen and host names).

usage: gen_awto_inputs.py [--check]
  Rewrites the blocks between `GENERATED-BEGIN awto_inputs` / `GENERATED-END awto_inputs` markers in:
    fw/overlay/Project/Header/RL6449_Project.h   (counts + index defines)
    fw/sdcc/awto_gpio.inc                        (tables for the poller)
    fw/sdcc/awto_gpiopop.inc                     (tables + name / label functions for the screen)
  --check: exit 1 when any block is out of date (for tests / gates).
Log: tmp/logs/gen_awto_inputs.log
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "fw/awto/inputs.tsv"
LOG = ROOT / "tmp/logs/gen_awto_inputs.log"
KINDS = {"bit": 0, "analog": 1, "byte": 2}
SRCS = {"p1": 0, "p3": 1, "p30": 2, "adc0": 3, "adc1": 4, "adc2": 5, "vsync": 6, "vcmp": 7, "xreg": 8, "key0": 9, "key1": 10}
BEGIN, END = "GENERATED-BEGIN awto_inputs", "GENERATED-END awto_inputs"


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def rows():
    out = []
    for ln in TSV.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        n, pin, kind, src, a, b, text, screen, lg = ln.split("\t")
        out.append(dict(name=n, pin=int(pin), kind=KINDS[kind], src=SRCS[src], a=int(a, 0), b=int(b, 0), text=text,
                        screen=screen == "y", log=lg == "y", srcname=src, kindname=kind))
    n_screen = sum(r["screen"] for r in out)
    assert all(r["screen"] for r in out[:n_screen]), "screen rows must come first"
    assert len(out) <= 255, "ring id is one byte"
    return out


def arr(name, typ, vals, per_line=12):
    body = ",\n    ".join(", ".join(vals[i:i + per_line]) for i in range(0, len(vals), per_line))
    return f"static const __code {typ} {name}[AWTO_IN_N] = {{\n    {body}}};"


def header_block(r):
    n, ns = len(r), sum(x["screen"] for x in r)
    idx = {x["name"]: i for i, x in enumerate(r) if x["name"] in ("ADC0", "ADC1")}
    return "\n".join([
        f"#define AWTO_IN_N                                               {n}      // inputs in fw/awto/inputs.tsv; also the transition ring id range",
        f"#define AWTO_IN_ROWS                                            {ns}      // inputs shown on the diagnostic console (the first AWTO_IN_ROWS)",
        f"#define AWTO_IN_ADC0                                            {idx['ADC0']}",
        f"#define AWTO_IN_ADC1                                            {idx['ADC1']}"])


def table_block(r, which, suffix=""):
    """Only the tables a translation unit uses; the suffix keeps the static names unique across units (the bank packer names areas by symbol)."""
    cols = {
        "Kind": ("BYTE", [str(x["kind"]) for x in r], 12),
        "Src": ("BYTE", [str(x["src"]) for x in r], 12),
        "A": ("BYTE", [str(x["a"] & 0xFF if x["src"] != 8 else 0) for x in r], 12),
        "B": ("BYTE", [str(x["b"]) for x in r], 12),
        "Addr": ("WORD", [f"0x{x['a']:04X}" if x["src"] == 8 else "0" for x in r], 8),
        "Pin": ("BYTE", [str(x["pin"]) for x in r], 12),
        "Flags": ("BYTE", [str(int(x["screen"]) | int(x["log"]) << 1) for x in r], 12),
    }
    L = ["// kind 0 bit, 1 analog (deadband), 2 byte; src: see awto_gpio.inc AwtoInRead; flags bit0 = screen row, bit1 = logged in the ring"]
    for k in which:
        typ, vals, per = cols[k]
        L.append(arr(f"tAwtoIn{k}{suffix}", typ, vals, per))
    return "\n".join(L)


def names_block(r):
    def sw(fn, key):
        seen = {}
        L = [f"static void {fn}(BYTE ucI)", "{", "    switch(ucI)", "    {"]
        for i, x in enumerate(r):
            if x["screen"] or key == "name":
                seen.setdefault(x[key], []).append(i)
        for t, idxs in seen.items():
            for i in idxs:
                L.append(f"        case {i}:")
            L.append(f'            AwtoPutStr("{t}"); break;')
        L += ["        default: break;", "    }", "}"]
        return "\n".join(L)
    return sw("AwtoInName", "name") + "\n\n" + sw("AwtoInText", "text")


def patch(path, new_block):
    t = path.read_text()
    a = t.index(BEGIN)
    a = t.index("\n", a) + 1
    b = t.index(END)
    b = t.rindex("\n", 0, b) + 1
    return t[:a] + new_block + "\n" + t[b:], t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    r = rows()
    targets = [(ROOT / "fw/overlay/Project/Header/RL6449_Project.h", header_block(r)),
               (ROOT / "fw/sdcc/awto_gpio.inc", table_block(r, ("Kind", "Src", "A", "B", "Addr", "Flags"))),
               (ROOT / "fw/sdcc/awto_gpiopop.inc", table_block(r, ("Kind", "Pin", "Flags"), "S") + "\n\n" + names_block(r))]
    stale = 0
    for path, blk in targets:
        new, old = patch(path, blk)
        if new != old:
            stale += 1
            if not a.check:
                path.write_text(new)
            log(f"{path.name}: {'out of date' if a.check else 'rewritten'}")
    log(f"{len(r)} inputs ({sum(x['screen'] for x in r)} screen rows, {sum(x['log'] for x in r)} logged); {stale} block(s) changed")
    return 1 if (a.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
