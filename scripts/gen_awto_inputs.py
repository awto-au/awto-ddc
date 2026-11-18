#!/usr/bin/env python3
"""Generate the input-monitor C tables from fw/awto/inputs.tsv (the one source for firmware, screen and host names).

usage: gen_awto_inputs.py [--check]
  Rewrites the blocks between `GENERATED-BEGIN awto_inputs` / `GENERATED-END awto_inputs` markers in:
    fw/sdk/Project/Header/RL6449_Project.h   (counts + index defines)
    fw/sdcc/awto_gpio.inc                        (tables for the poller)
    fw/osd/console.c                             (tables + name / label functions for the screen)
  --check: exit 1 when any block is out of date (for tests / gates).
Log: tmp/logs/gen_awto_inputs.log
"""
import argparse
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "fw/awto/inputs.tsv"
LOG = ROOT / "tmp/logs/gen_awto_inputs.log"
KINDS = {"bit": 0, "analog": 1, "byte": 2}
SRCS = {"p1": 0, "p3": 1, "p30": 2, "adc0": 3, "adc1": 4, "adc2": 5, "vsync": 6, "vcmp": 7, "xreg": 8, "key0": 9, "key1": 10}
BEGIN, END = "GENERATED-BEGIN awto_inputs", "GENERATED-END awto_inputs"


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def rows():
    out = []
    for ln in TSV.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        n, pin, kind, src, a, b, text, screen, lg, desc, rate = ln.split("\t")
        assert rate in ("pass", "slow"), ln
        out.append(dict(name=n, pin=int(pin), kind=KINDS[kind], src=SRCS[src], a=a if src == "xreg" else int(a, 0), b=int(b, 0), text=text,
                        screen=screen == "y", log=lg == "y", desc=desc, srcname=src, kindname=kind, fast=rate == "pass"))
    n_screen = sum(r["screen"] for r in out)
    assert all(r["screen"] for r in out[:n_screen]), "screen rows must come first"
    assert len(out) <= 255, "ring id is one byte"
    for i, x in enumerate(out):                    # a key row decodes the ADC row before it: that row must be read at least as often
        if x["src"] in (SRCS["key0"], SRCS["key1"]):
            adc = next(y for y in out if y["src"] == (SRCS["adc0"] if x["src"] == SRCS["key0"] else SRCS["adc1"]))
            assert x["fast"] and adc["fast"] and out.index(adc) < i, f"{x['name']}: key rows and their ADC row must be rate pass, ADC first"
    return out


def arr(name, typ, vals, per_line=12, n="AWTO_IN_N"):
    body = ",\n    ".join(", ".join(vals[i:i + per_line]) for i in range(0, len(vals), per_line))
    return f"static const __code {typ} {name}[{n}] = {{\n    {body}}};"


KEYS = ("SOURCE", "MENU", "DOWN", "UP", "AUTO", "POWER")      # front keys: the key reader (awto_keys.inc) builds its mask from these rows


def header_block(r):
    n, ns = len(r), sum(x["screen"] for x in r)
    idx = {x["name"]: i for i, x in enumerate(r) if x["name"] in ("ADC0", "ADC1") + KEYS}
    assert all(k in idx for k in KEYS), "inputs.tsv needs a row per front key"
    return "\n".join([
        f"#define AWTO_IN_N                                               {n}      // inputs in fw/awto/inputs.tsv; also the transition ring id range",
        f"#define AWTO_IN_ROWS                                            {ns}      // inputs shown on the diagnostic console (the first AWTO_IN_ROWS)",
        f"#define AWTO_IN_FAST_N                                          {sum(x['fast'] for x in r)}      // rows read every pass (inputs.tsv rate = pass)",
        f"#define AWTO_IN_ADC0                                            {idx['ADC0']}",
        f"#define AWTO_IN_ADC1                                            {idx['ADC1']}"]
        + [f"#define AWTO_IN_{k:<48}{idx[k]}" for k in KEYS])


def table_block(r, which, suffix=""):
    """Only the tables a translation unit uses; the suffix keeps the static names unique across units (the bank packer names areas by symbol)."""
    cols = {
        "Kind": ("BYTE", [str(x["kind"]) for x in r], 12),
        "Src": ("BYTE", [str(x["src"]) for x in r], 12),
        "A": ("BYTE", [str(x["a"] & 0xFF if x["src"] != 8 else 0) for x in r], 12),
        "B": ("BYTE", [str(x["b"]) for x in r], 12),
        "Addr": ("WORD", [f"AWTO_R_{x['a']}" if x["src"] == 8 else "0" for x in r], 8),
        "Pin": ("BYTE", [str(x["pin"]) for x in r], 12),
        "Flags": ("BYTE", [str(int(x["screen"]) | int(x["log"]) << 1) for x in r], 12),
    }
    if "Fast" in which:
        fast = [str(i) for i, x in enumerate(r) if x["fast"]]
        slow = [str(i) for i, x in enumerate(r) if not x["fast"]]
        cols["Fast"] = ("BYTE", fast, 12)
        cols["Slow"] = ("BYTE", slow, 12)
    L = ["// kind 0 bit, 1 analog (deadband), 2 byte; src: see awto_gpio.inc AwtoInRead; flags bit0 = screen row, bit1 = logged in the ring"]
    for k in which:
        typ, vals, per = cols[k]
        n = {"Fast": "AWTO_IN_FAST_N", "Slow": "AWTO_IN_N - AWTO_IN_FAST_N"}.get(k, "AWTO_IN_N")
        L.append(arr(f"tAwtoIn{k}{suffix}", typ, vals, per, n))
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
    return sw("AwtoInName", "name") + "\n\n" + sw("AwtoInText", "text") + "\n\n" + text_table(r)


UI_TEXT = [("AWTO_TXT_DESCHDR", "DESCRIPTION"), ("AWTO_TXT_LOGHDR", "EVENT LOG"),
           ("AWTO_TXT_MS", " MS  "), ("AWTO_TXT_MARK", "-----")]


def text_table(r):
    """Console text as one constant table + one reader (stable names, so the layout can keep both in one bank:
    a constant read through a pointer must sit in the reader's bank, awto-sdcc#39 / awto-ddc#111)."""
    texts = [x["desc"] if x["desc"] != "-" else "" for x in r] + [t for _, t in UI_TEXT]
    offs, blob = [], ""
    for t in texts:
        offs.append(len(blob))
        blob += t + "\\0"
    lens = [o for o in offs]
    L = [f"#define {n:<22} {len(r) + i}" for i, (n, _) in enumerate(UI_TEXT)]
    uniq, real, pos = {}, [], 0                   # identical texts share one copy
    for t in texts:
        if t not in uniq:
            uniq[t] = pos
            pos += len(t) + 1
        real.append(uniq[t])
    body = "".join(t.replace('"', '\\"') + "\\0" for t in uniq)
    L.append(f"static const __code char tAwtoTxtS[] = \"{body}\";")
    L.append(f"static const __code WORD tAwtoTxtOffS[{len(texts)}] = {{" + ", ".join(str(o) for o in real) + "};")
    L += ["static void AwtoTxt(BYTE ucI)                  // input description (0..AWTO_IN_N-1) or AWTO_TXT_*",
          "{",
          "    const __code char *pc = &tAwtoTxtS[tAwtoTxtOffS[ucI]];",
          "",
          "    while(*pc != 0)",
          "    {",
          "        AwtoPutChar(*pc);",
          "        pc++;",
          "    }",
          "}"]
    return "\n".join(L)


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
    targets = [(ROOT / "fw/sdk/Project/Header/RL6449_Project.h", header_block(r)),
               (ROOT / "fw/input/inputs.c", table_block(r, ("Kind", "Src", "A", "B", "Addr", "Flags", "Fast", "Slow"))),
               (ROOT / "fw/osd/console.c", table_block(r, ("Kind", "Pin", "Flags"), "S") + "\n\n" + names_block(r))]
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
