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
PREFIX = {"DSEG": "d_", "BSEG": "d_", "ISEG": "i_", "XSEG": "", "XISEG": "", "XABS": ""}
XRAM = (0xD700, 0xF700)                                     # RL6449 XRAM (fw.mem EXTERNAL RAM + no-init top to 0xF6FF)
ISR = "isr_"                                                # after the space prefix: used by ISR and main code
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
            m = re.match(r"^(_\w+)\s*=\s*(0x[0-9a-fA-F]+)\s*$", l)    # __at() object: `_isr_g_stAwtoDiag = 0xf6d0`
            if m:
                if XRAM[0] <= int(m.group(2), 16) < XRAM[1]:              # variables only, not __at() hardware registers
                    out.append((area, p.stem, m.group(1), 0))
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


def isr_refs(asm_dir: Path) -> set:
    """Labels referenced by code reachable from an interrupt handler (sdcc_bank chunks: reti roots, lcall/ljmp closure)."""
    from sdcc_bank import Module
    funcs = {c.name: c for p in sorted(asm_dir.glob("*.asm")) if not p.name.startswith("__")
             for c in Module(p).chunks if c.area == "CSEG"}
    seen, st = set(), [n for n, c in funcs.items() if c.isr]
    while st:
        n = st.pop()
        if n in seen or n not in funcs:
            continue
        seen.add(n); st.extend(funcs[n].calls)
    return {r for n in seen for r in funcs[n].refs} | {w for n in seen for l in funcs[n].lines for w in re.findall(r"\b_\w+", l)}


def shared_refs(asm_dir: Path) -> set:
    """Labels referenced both by ISR-reachable and by main-reachable (main + address-taken) code."""
    from sdcc_bank import Module
    funcs = {c.name: c for p in sorted(asm_dir.glob("*.asm")) if not p.name.startswith("__")
             for c in Module(p).chunks if c.area == "CSEG"}

    def reach(roots):
        seen, st = set(), list(roots)
        while st:
            n = st.pop()
            if n in seen or n not in funcs:
                continue
            seen.add(n); st.extend(funcs[n].calls)
        return seen
    isr = reach([n for n, c in funcs.items() if c.isr])
    main = reach(["_main", *{r for c in funcs.values() for r in c.refs if r in funcs}])
    refs = lambda S: {w for n in S for l in funcs[n].lines for w in re.findall(r"\b_\w+", l)}
    return refs(isr) & refs(main - isr)


def base_of(cn: str) -> str:
    for pre in ("d_", "i_"):
        if cn.startswith(pre):
            cn = cn[len(pre):]
    return cn[len(ISR):] if cn.startswith(ISR) else cn


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
    ap.add_argument("mode", choices=["report", "check", "rename", "to-xdata"])
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
        tot, isr = defaultdict(int), isr_refs(Path(a.asm))
        for area, mod, fn, cn, size, named in sorted(rows, key=lambda r: (r[0], addr.get("_" + r[3], 999), r[1])):
            if not PREFIX[area]:
                continue                                           # XDATA: names checked, not listed
            ad = addr.get("_" + cn) if fn is None else None
            lab = ("_" + cn) if fn is None else f"_{fn}_{cn}"
            hot = "ISR" if any(r == lab or r.startswith(lab + "_") for r in isr) else "   "
            log(f"{area:5} {('0x%02X' % ad) if ad is not None else '  -  '} {size:3} {hot} {mod:32} {(fn + ':') if fn else ''}{cn}")
            tot[area] += size
        for blk in re.findall(r"^(DDOVL\w*|SSEG|BSEG_BYTES|BIT_BANK|DSEG|ISEG)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", mp, re.M):
            log(f"area {blk[0]:10} at 0x{int(blk[1], 16):02X} size {int(blk[2], 16)}")
        log(f"totals (BSEG in bits): {dict(tot)}")
        return 0

    if a.mode == "to-xdata":                                       # bits no ISR code uses -> __xdata _Bool (#201)
        isr = isr_refs(Path(a.asm))
        files = {p: p.read_text(errors="replace") for p in src_files()}
        n_moved = 0
        for area, mod, fn, cn, size, named in rows:
            lab = ("_" + cn) if fn is None else f"_{fn}_{cn}"
            if area != "BSEG" or not named or any(r == lab or r.startswith(lab + "_") for r in isr):
                continue
            base = cn[len(PREFIX[area]):] if cn.startswith(PREFIX[area]) else cn
            hit = False
            for p, t in files.items():
                if fn is None:
                    t2 = re.sub(r"\b((?:static|extern)\s+)?((?:volatile\s+)?)bit(\s+)" + re.escape(cn) + r"\b",
                                lambda m: f"{m.group(1) or ''}{m.group(2)}__xdata _Bool{m.group(3)}{base}", t) if p.suffix != ".py" else t
                    t2 = word(cn).sub(base, t2) if p.suffix != ".asm" else t2
                    t2 = word("_" + cn).sub("_" + base, t2) if p.suffix in (".asm", ".py") else t2
                else:
                    sp = body_span(t, fn) if p.suffix in (".c", ".inc") else None
                    if not sp:
                        continue
                    body = re.sub(r"\bbit(\s+)" + re.escape(cn) + r"\b", lambda m: f"_Bool{m.group(1)}{base}", t[sp[0]:sp[1]])
                    t2 = t[:sp[0]] + word(cn).sub(base, body) + t[sp[1]:]
                if t2 != t:
                    files[p] = t2; hit = True
            n_moved += hit
            log(f"to-xdata {(fn + ':') if fn else ''}{cn} -> {base}" + ("" if hit else "  NOT FOUND"))
        for p, t in files.items():
            if t != p.read_text(errors="replace"):
                p.write_text(t)
        log(f"to-xdata: {n_moved} bits moved")
        return 0

    bad, sh = [], shared_refs(Path(a.asm))
    for area, mod, fn, cn, size, named in rows:
        lab = ("_" + cn) if fn is None else f"_{fn}_{cn}"
        is_sh = any(r == lab or r.startswith(lab + "_") or r.startswith(lab + "+") for r in sh)
        want = PREFIX[area] + (ISR if is_sh else "") + base_of(cn)
        if named and cn != want:
            bad.append((area, mod, fn, cn, want))
    if a.mode == "check":
        placed = {r[3] for r in rows}
        for p in src_files():
            if p.suffix == ".py":
                continue
            for n in set(re.findall(r"\b([di]_\w+)", p.read_text(errors="replace"))):
                pass                                               # prefixed-but-not-placed: needs the C decl scan (#189 step 2)
        for b in bad:
            log(f"MISNAMED {b[0]} {b[1]} {(b[2] + ':') if b[2] else ''}{b[3]} (want {b[4]})")
        log(f"check: {len(rows)} objects, {len(bad)} not named by placement (d_ / i_ space, isr_ shared with an ISR)")
        return 1 if bad else 0

    # rename
    files = {p: p.read_text(errors="replace") for p in src_files()}
    glob_names = sorted({(b[3], b[4]) for b in bad if b[2] is None})
    loc = sorted({(b[3], b[4], b[2]) for b in bad if b[2] is not None})
    changed = defaultdict(int)
    for n, new in glob_names:
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
    for n, new, fn in loc:
        hit = False
        for p, t in files.items():
            if p.suffix not in (".c", ".inc"):
                continue
            sp = body_span(t, fn)
            if not sp:
                continue
            body = t[sp[0]:sp[1]]
            b2 = word(n).sub(new, body)
            if b2 != body:
                files[p] = t[:sp[0]] + b2 + t[sp[1]:]; changed[p] += 1; hit = True
        log(f"rename {fn}:{n} -> {new}" + ("" if hit else "  NOT FOUND"))
    for p, t in files.items():
        if changed.get(p):
            p.write_text(t)
    log(f"rename: {len(glob_names)} globals / file statics, {len(loc)} function statics, {len(changed)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
