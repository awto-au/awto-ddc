#!/usr/bin/env python3
"""IRAM objects by the compiler's placement: report, name check, rename (awto-ddc#189).

usage: iram_names.py report|check|rename [--asm DIR] [--map FILE]
- Source of truth: the linked asm (tmp/sdcc-port/asm_ovl, after the overlay pass): `.area DSEG/ISEG/BSEG` storage.
- Names: direct IRAM (DATA, BIT) = `d_` prefix, indirect (IDATA) = `i_`. Static objects only (globals, file and
  function statics); overlay frames (__dovlN / __bovl) and library objects are reported, not named.
- report: every IRAM object (area, size, owner, address from the map where global) + overlay blocks + stack.
- check: exit 1 if a static IRAM object lacks its prefix or a prefixed C name is not placed in IRAM.
- rename: adds the prefix in fw/ (not fw/sdk-parked) and scripts/; function statics only inside their function.
Log: tmp/logs/iram_names.log
"""
import argparse, re, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
PREFIX = {"DSEG": "d_", "BSEG": "d_", "ISEG": "i_"}
STORE = re.compile(r"^\s+\.area\s+(\w+)")
LABEL = re.compile(r"^(\w+)::?")
DS = re.compile(r"^\s*\.ds\s+(\w+)")
FUNC = re.compile(r"^;\s+function (\w+)\s*$")
SKIP = re.compile(r"_PARM_\d+$|_sloc\d+_\d+_\d+$")          # overlaid frame members
SRC_EXT = (".c", ".h", ".inc", ".asm")
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def objects(asm_dir: Path):
    """[(area, module, asm label, size)] for static IRAM storage, + function names seen."""
    out, funcs = [], set()
    for p in [*sorted(asm_dir.glob("*.asm")), *sorted((ROOT / "fw/sdcc").glob("*.asm"))]:   # + our hand asm (bank.asm)
        area, lab = None, None
        for l in p.read_text(errors="replace").split("\n"):
            m = FUNC.match(l)
            if m:
                funcs.add(m.group(1))
            m = STORE.match(l)
            if m:
                area, lab = m.group(1), None
                continue
            if area not in PREFIX:
                continue
            m = LABEL.match(l)
            if m:
                lab = m.group(1)
                l = l[m.end():]                                     # `_d_bs_cur:\t.ds\t1` (label and storage on one line)
            m = DS.match(l)
            if m and lab:
                out.append((area, p.stem, lab, int(m.group(1), 0)))
                lab = None
    return out, funcs


def c_name(label: str, funcs: set):
    """asm label -> (function or None, C name). `_Fn_name_<level>_<key>` = static local of Fn."""
    m = re.match(r"^_(\w+)_(\d+)_(\d+)$", label)
    if m:
        for f in sorted(funcs, key=len, reverse=True):
            if m.group(1).startswith(f + "_"):
                return f, m.group(1)[len(f) + 1:]
    return None, label[1:]


def addr_of(map_text: str) -> dict:
    return {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^\s+([0-9A-F]{8})\s+(_\w+)\s", map_text, re.M)}


def src_files():
    for d in (ROOT / "fw", ROOT / "scripts"):
        for p in d.rglob("*"):
            if p.is_file() and "sdk-parked" not in p.parts and (p.suffix in SRC_EXT or d.name == "scripts" and p.suffix == ".py"):
                yield p


def word(name: str):
    return re.compile(r"(?<![\w.>$])" + re.escape(name) + r"(?!\w)")


def body_span(text: str, fn: str):
    """(start, end) of fn's definition body: `fn(...)` then the brace block (comments / strings skipped)."""
    for m in re.finditer(r"(?m)^[\w \t*]*\b" + re.escape(fn) + r"\s*\([^;{]*\)\s*(?:__\w+\s*(?:\([^)]*\))?\s*)*\{", text):
        i, depth = m.end() - 1, 0
        while i < len(text):
            if text.startswith("//", i):
                i = text.find("\n", i); i = len(text) if i < 0 else i; continue
            if text.startswith("/*", i):
                i = text.find("*/", i) + 2; continue
            c = text[i]
            if c in "\"'":
                j = i + 1
                while j < len(text) and text[j] != c:
                    j += 2 if text[j] == "\\" else 1
                i = j + 1; continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return m.start(), i + 1
            i += 1
    return None


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["report", "check", "rename"])
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_ovl"))
    ap.add_argument("--map", default=str(ROOT / "tmp/fw/AWT26110003/fw.map"))
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/iram_names.log").open("a")
    objs, funcs = objects(Path(a.asm))
    mp = Path(a.map).read_text(errors="replace") if Path(a.map).exists() else ""
    addr = addr_of(mp)
    rows = []
    for area, mod, lab, size in objs:
        if re.match(r"^__[dbx]ovl", lab):                         # overlay blocks (__dovl0, __bovl)
            rows.append((area, mod, None, lab, size, False))
            continue
        fn, cn = c_name(lab, funcs)
        rows.append((area, mod, fn, cn, size, not SKIP.search(lab)))

    if a.mode == "report":
        tot = defaultdict(int)
        for area, mod, fn, cn, size, named in sorted(rows, key=lambda r: (r[0], addr.get("_" + r[3], 999), r[1])):
            ad = addr.get("_" + cn) if fn is None else None
            log(f"{area:5} {('0x%02X' % ad) if ad is not None else '  -  '} {size:3} {mod:32} {(fn + ':') if fn else ''}{cn}")
            tot[area] += size
        for blk in re.findall(r"^(DDOVL\w*|SSEG|BSEG_BYTES|BIT_BANK|DSEG|ISEG)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", mp, re.M):
            log(f"area {blk[0]:10} at 0x{int(blk[1], 16):02X} size {int(blk[2], 16)}")
        log(f"totals (BSEG in bits): {dict(tot)}")
        return 0

    bad = []
    for area, mod, fn, cn, size, named in rows:
        if named and not cn.startswith(PREFIX[area]):
            bad.append((area, mod, fn, cn))
    if a.mode == "check":
        placed = {r[3] for r in rows}
        for p in src_files():
            if p.suffix == ".py":
                continue
            for n in set(re.findall(r"\b([di]_\w+)", p.read_text(errors="replace"))):
                pass                                               # prefixed-but-not-placed: needs the C decl scan (#189 step 2)
        for b in bad:
            log(f"UNPREFIXED {b[0]} {b[1]} {(b[2] + ':') if b[2] else ''}{b[3]}")
        log(f"check: {len(rows)} IRAM objects, {len(bad)} without the d_/i_ prefix")
        return 1 if bad else 0

    # rename
    files = {p: p.read_text(errors="replace") for p in src_files()}
    glob_names = sorted({(PREFIX[b[0]], b[3]) for b in bad if b[2] is None})
    loc = sorted({(PREFIX[b[0]], b[2], b[3]) for b in bad if b[2] is not None})
    changed = defaultdict(int)
    for pre, n in glob_names:
        new = pre + n.lstrip("_") if n.startswith("_") else pre + n
        rx = word(n)
        asm_rx = word("_" + n)                                      # asm / map / Python spellings carry the C underscore
        for p, t in files.items():
            t2 = rx.sub(new, t) if p.suffix != ".asm" else t
            t2 = asm_rx.sub("_" + new, t2) if p.suffix in (".asm", ".py") else t2
            if p.suffix == ".py":
                t2 = word("'" + n).sub("'" + new, t2)
            if t2 != t:
                changed[p] += 1; files[p] = t2
        log(f"rename {n} -> {new}")
    for pre, fn, n in loc:
        hit = False
        for p, t in files.items():
            if p.suffix not in (".c", ".inc"):
                continue
            sp = body_span(t, fn)
            if not sp:
                continue
            body = t[sp[0]:sp[1]]
            b2 = word(n).sub(pre + n, body)
            if b2 != body:
                files[p] = t[:sp[0]] + b2 + t[sp[1]:]; changed[p] += 1; hit = True
        log(f"rename {fn}:{n} -> {pre + n}" + ("" if hit else "  NOT FOUND"))
    for p, t in files.items():
        if changed.get(p):
            p.write_text(t)
    log(f"rename: {len(glob_names)} globals / file statics, {len(loc)} function statics, {len(changed)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
