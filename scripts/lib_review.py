#!/usr/bin/env python3
"""Side-by-side review of Realtek .LIB functions vs vendor firmware banks.
Output quotes Realtek disassembly: allowed only under re/lib-review/ (repo is PRIVATE, see CLAUDE.md).

  lib_review.py side <FuncName> [--at BANK:ADDR] [--lib LIB] [--banks DIR]
      -> markdown table, one row per instruction: .LIB (fixups marked) | vendor | same/diff
  lib_review.py unsourced [--src DIR]...   -> markdown table of .LIB functions with no C source
Logs: ./tmp/logs/lib_review.log. Repo root: $AWTO_DDC_REPO -> file-relative.
"""
import argparse, difflib, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omf51_lib as omf
import rtk_libsig as sig
import d8051
log = sig.log

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
OUT = REPO / "re/lib-review"
LIB = Path("/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST/Kernel/Scaler/RL6449_Series_Scaler/Lib/Output/RL6449_FunctionLib.LIB")
BANKS = sig.ANALYSIS / "banks"
NAMES = d8051.load_regnames()


def lib_functions(lib=LIB):
    fns = {}
    for m in omf.parse_lib(lib):
        for pub, seg, off, size in m.functions():
            fns[omf.display_name(m, pub)] = (m, seg, off, size)
    return fns


def fix_label(m, seg, fx):
    _, ty, kind, ref, add = fx
    if kind == 2:
        nm = m.externs.get(ref, f"ext{ref}")
    else:
        s = m.segs.get(ref)
        nm = s.name if s else f"seg{ref}"
    part = {0: ".lo", 1: "", 3: ".hi", 4: "", 6: ".bit"}.get(ty, f".t{ty}")
    return f"{nm}{'+%d' % add if add else ''}{part}"


def lib_insns(m, seg, off, size):
    code = bytes(seg.data[off:off + size])
    reloc = {r - off for r in seg.reloc if off <= r < off + size}
    fx = {f[0] - off: fix_label(m, seg, f) for f in seg.fixups if off <= f[0] < off + size}
    out = []
    for ins in d8051.disasm(code, 0, NAMES, reloc):
        # label fixups within this insn
        labs = [fx[ins.off + j] for j in range(ins.n) if (ins.off + j) in fx]
        ins.note = ", ".join(labs)
        out.append(ins)
    return out


def locate(f_mask_data, banks):
    return sig.fuzzy(*f_mask_data, banks)


def vendor_insns(banks, bank, addr, n):
    img = banks[bank]
    return list(d8051.disasm(img, 0, NAMES, start=addr, end=min(len(img), addr + n)))


def side(name, at=None, lib=LIB, banks_dir=BANKS):
    m, seg, off, size = lib_functions(lib)[name]
    banks = sig.load_banks(banks_dir)
    data = bytes(seg.data[off:off + size])
    mask = bytes(0 if (off + i) in seg.reloc else 1 for i in range(size))
    if at:
        b, a = at.split(":"); loc = (int(b), int(a, 16)); score = None
    else:
        score, loc = sig.fuzzy(data, mask, banks)
        if not loc:
            return f"### {name}\n\nno vendor placement found\n"
    li = lib_insns(m, seg, off, size)
    if not at:  # refine start by instruction-stream similarity (byte positions drift when code is inserted)
        lk = [(i.raw[0], i.n) for i in li]
        def ratio(a):
            vk = [(i.raw[0], i.n) for i in vendor_insns(banks, loc[0], a, size + 24)]
            return difflib.SequenceMatcher(None, lk, vk, autojunk=False).ratio()
        loc = (loc[0], max(range(max(0, loc[1] - 8), loc[1] + 9), key=lambda a: (ratio(a), -abs(a - loc[1]))))
    vi = vendor_insns(banks, loc[0], loc[1], size + 24)
    # cut vendor at the first RET/RETI at or after the lib's last instruction offset
    cut = len(vi)
    for k, v in enumerate(vi):
        if v.text in ("RET", "RETI") and v.off - loc[1] >= size - 8:
            cut = k + 1; break
    vi = vi[:cut]
    sm = difflib.SequenceMatcher(None, [(i.raw[0], i.n) for i in li], [(i.raw[0], i.n) for i in vi], autojunk=False)
    ops = sm.get_opcodes()
    if ops and ops[0][0] == "insert":  # leading vendor-only bytes belong to the preceding function
        vi = vi[ops[0][4]:]
        loc = (loc[0], vi[0].addr)
        sm = difflib.SequenceMatcher(None, [(i.raw[0], i.n) for i in li], [(i.raw[0], i.n) for i in vi], autojunk=False)
    rows = []

    def lrow(i):
        return f"{i.off:03X}: {i.raw.hex()} {i.text}" + (f" **[fix {i.note[:48]}]**" if i.reloc else "") + (f" ; {i.note}" if i.note and not i.reloc else "")

    def vrow(i):
        return f"{i.addr:04X}: {i.raw.hex()} {i.text}" + (f" ; {i.note}" if i.note else "")

    nsame = ndiff = 0

    def explain(x, y, mark):
        if mark == "same":
            return ""
        if mark == "same-op, fixup":
            return f"link-time fixup ({x.note[:60]}); vendor linked value {y.raw[1:].hex()}" + (f" = {y.note}" if y.note else "")
        if mark == "**DIFF operand**":
            e = f"same opcode, operand lib {x.raw[1:].hex()} vs vendor {y.raw[1:].hex()}"
            if x.dptr is not None:
                e += f"; lib reg {x.note or NAMES.get(x.dptr, '?')} vs vendor {y.note or NAMES.get(y.dptr, '?')}"
            return e
        if mark == "**lib-only**":
            return "present in .LIB, absent in vendor"
        if mark == "**vendor-only**":
            return "inserted in vendor"
        return "different instruction" + (f" (lib fixup {x.note})" if x.reloc else "")

    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            for x, y in zip(li[a0:a1], vi[b0:b1]):
                if x.reloc:
                    mark = "same-op, fixup"; nsame += 1
                elif x.raw == y.raw:
                    mark = "same"; nsame += 1
                else:
                    mark = "**DIFF operand**"; ndiff += 1
                rows.append((lrow(x), vrow(y), mark, explain(x, y, mark)))
        else:
            for k in range(max(a1 - a0, b1 - b0)):
                x = li[a0 + k] if a0 + k < a1 else None
                y = vi[b0 + k] if b0 + k < b1 else None
                mark = "**lib-only**" if y is None else "**vendor-only**" if x is None else "**DIFF opcode**"
                ndiff += 1
                rows.append((lrow(x) if x else "", vrow(y) if y else "", mark, explain(x, y, mark)))
    hdr = [f"### {name}", "",
           f"- module {m.name}, lib size {size} bytes, {sum(1 for r in seg.reloc if off <= r < off + size)} link-time fixup bytes",
           f"- vendor placement bank {loc[0]} addr {loc[1]:04X}" + (f", fixed-byte score {score*100:.1f}%" if score is not None else ""),
           f"- instruction rows: {nsame} same (incl. fixup sites with same opcode), {ndiff} different", "",
           "| .LIB | vendor | same/diff | explanation |", "|---|---|---|---|"]
    return "\n".join(hdr + [f"| `{a}` | `{b}` | {c} | {d} |" for a, b, c, d in rows]) + "\n"


SDK = Path("/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST/Kernel/Scaler")
SRC_TREES = ["RL6449_Series_Scaler", "RL6449_Series_Common", "ScalerFunction", "ScalerCommonFunction"]
PRIMARY = ("RL6449_Series_Scaler/Lib/Code", "ScalerCommonFunction/Lib/Code")  # the two trees srccheck was run on (169 unsourced)
SERIES_SKIP = re.compile(r"RL6(369|410|432|463|492)_")
DEF_RE = re.compile(r"^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)[ \t]*\([^;{}]*\)[ \t]*(?:(?:using|reentrant)[ \t]*\d*[ \t]*)*(?://[^\n]*)?\n?[ \t]*\{", re.M)

CATEGORIES = [
    ("OSD", r"Osd|Reference4Bit"), ("MBR (motion blur reduction)", r"Mbr"), ("TCON", r"Tcon"),
    ("DP/data port", r"DataPort"), ("colour: DCR/DCC", r"DCR|DCC"), ("colour: HLW (highlight window)", r"HLW"),
    ("colour: dither/filter", r"Dither|DigitalFilter|Ringing"), ("colour: space/gamma/ICM", r"Color|PCM|ICM|Gamma"),
    ("math", r"Compute"), ("chip ID", r"GetIDCode"), ("memory/M-domain", r"MDomain|Scaling"), ("other", r"")]


def category(n):
    return next(c for c, rx in CATEGORIES if re.search(rx, n))


def sdk_defs():
    """name -> list of defining files (relative to SDK) in the RL6449-relevant trees."""
    defs = {}
    for t in SRC_TREES:
        for f in (SDK / t).rglob("*.c"):
            txt = f.read_text(errors="replace")
            for m in DEF_RE.finditer(txt):
                if m.group(1) not in ("if", "while", "for", "switch"):
                    defs.setdefault(m.group(1), []).append(str(f.relative_to(SDK)))
    return defs


def refs_in_build(names):
    """name -> sorted files in the compiled tree (tmp/sdcc-port/src, RL6449 + common trees) that mention it."""
    root = REPO / "tmp/sdcc-port/src"
    pat = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    out = {}
    for f in root.rglob("*"):
        if f.suffix not in (".c", ".h") or SERIES_SKIP.search(str(f)):
            continue
        for n in set(pat.findall(f.read_text(errors="replace"))):
            out.setdefault(n, set()).add(str(f.relative_to(root)))
    return out


def touched(m, seg, off, size):
    """(register names via MOV DPTR,#imm; data-port regs via R7/R6 pairs; callee names from fixups)."""
    regs, ports, calls = [], [], []
    ins = lib_insns(m, seg, off, size)
    for k, i in enumerate(ins):
        if i.dptr is not None and not i.reloc:
            nm = NAMES.get(i.dptr)
            if nm and nm not in regs:
                regs.append(nm)
        if i.raw[0] in (0x7E, 0x7F) and not i.reloc:  # MOV R6/R7,#imm near an adjacent counterpart
            for j in ins[k + 1:k + 4]:
                if j.raw[0] in (0x7E, 0x7F) and j.raw[0] != i.raw[0] and not j.reloc:
                    hi, lo = (i, j) if i.raw[0] == 0x7E else (j, i)
                    nm = NAMES.get(hi.raw[1] << 8 | lo.raw[1])
                    if nm and nm not in ports:
                        ports.append(nm)
        if i.raw[0] in (0x12, 0x02) and i.note and not i.note.startswith(("?PR?", "?C?")):
            c = i.note.lstrip("_")
            if c not in calls and not c.startswith("?"):
                calls.append(c)
    return regs, ports, calls


def unsourced():
    fns = lib_functions()
    defs = sdk_defs()
    match = {}
    for ln in open(sig.ANALYSIS / "lib_match.tsv").read().splitlines()[1:]:
        c = ln.split("\t")
        old = match.get(c[0])
        if old is None or c[2].endswith("FunctionLib"):  # prefer the FunctionLib row (module is from that .LIB)
            match[c[0]] = (c[4], c[5], c[6])
    nosrc = sorted(n for n in fns if not any(f.startswith(PRIMARY) for f in defs.get(n, [])))
    refs = refs_in_build(nosrc)
    rows = []
    for n in nosrc:
        m, seg, off, size = fns[n]
        regs, ports, calls = touched(m, seg, off, size)
        cls, where, pct = match.get(n, ("?", "", ""))
        rows.append(dict(name=n, module=m.name, size=size, cls=cls, where=where, pct=pct,
                         regs=regs, ports=ports, calls=calls, cat=category(n),
                         refs=sorted(refs.get(n, [])), src=(defs.get(n) or [''])[0]))
    return fns, rows


def unsourced_md():
    fns, rows = unsourced()
    real = [r for r in rows if not r["src"]]
    out = [f"## 2. .LIB functions with no C source in {' / '.join(PRIMARY)} ({len(rows)} of {len(fns)})", "",
           f"- {len(real)} of them have no C source anywhere in the RL6449-relevant trees ({', '.join(SRC_TREES)}); "
           f"the other {len(rows) - len(real)} are defined under Kernel/Scaler/ScalerFunction (column src)",
           "- vendor column: lib_match.tsv class and placement (EXACT = byte-identical modulo fixups)",
           "- refs = .c/.h files in tmp/sdcc-port/src (RL6449 + common trees) naming the function; "
           "a referencing .c with no source for the callee needs a stub, an omission or a re-implementation in our build", ""]
    byc = {}
    for r in rows:
        byc.setdefault(r["cat"], []).append(r)
    out.append("| category | count | vendor EXACT | vendor SHORT/ABSENT | referenced by compiled .c |")
    out.append("|---|---|---|---|---|")
    for c, lst in sorted(byc.items()):
        out.append(f"| {c} | {len(lst)} | {sum(r['cls'].startswith('EXACT') for r in lst)} | "
                   f"{sum(r['cls'] in ('SHORT', 'ABSENT', 'SIBLING') for r in lst)} | "
                   f"{sum(any(f.endswith('.c') for f in r['refs']) for r in lst)} |")
    out += ["", "| function | module | size | vendor | src | refs (.c) | registers / ports touched | calls | category |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cref = [f for f in r["refs"] if f.endswith(".c")]
        rg = ", ".join(r["regs"][:5] + ["port " + p for p in r["ports"][:3]]) or "-"
        out.append(f"| {r['name']} | {r['module'][:28]} | {r['size']} | {r['cls']} {r['where'].split(';')[0]} | {Path(r['src']).parent.name + '/' if r['src'] else '**none**'} | "
                   f"{len(cref)}{' ' + Path(cref[0]).name if cref else ''} | {rg} | {', '.join(r['calls'][:4]) or '-'} | {r['cat']} |")
    return "\n".join(out) + "\n", rows


def c_source(name):
    """(path, text) of the C definition: RL6449 trees first, else any other series (path says which)."""
    defs = sdk_defs()
    cands = [SDK / f for f in defs.get(name, [])]
    if not cands:
        cands = [f for f in SDK.glob("RL6*_Series_Scaler/Lib/Code/**/*.c") if re.search(r"\b%s\s*\(" % name, f.read_text(errors="replace"))]
    for f in cands:
        txt = f.read_text(errors="replace")
        for m in DEF_RE.finditer(txt):
            if m.group(1) == name:
                i = txt.index("{", m.end() - 1); d = 0
                for j in range(i, len(txt)):
                    d += (txt[j] == "{") - (txt[j] == "}")
                    if d == 0:
                        return str(f.relative_to(SDK)), txt[m.start():j + 1]
    return None, None


VARIANTS = [("ScalerGetDataPortSingleByte", None), ("ScalerColorRGBOutputGammaAdjust", None),
            ("ScalerColorDCRLocalDimmingReadTHDResult", None), ("ScalerColorDCRLocalDimmingReadTHDResult", "0:c119"),
            ("ScalerColorDCRGetLocalDimmingHistoEnable", None),
            ("ScalerColorHLWOutputGammaAdjust", None), ("ScalerColorHLWIAPSGainAdjust", None), ("ScalerTcon0Enable", None)]


def verdicts(path):
    v, cur = {}, None
    for ln in Path(path).read_text().splitlines():
        if ln.startswith("### "):
            cur = ln[4:].strip(); v[cur] = []
        elif cur:
            v[cur].append(ln)
    return {k: "\n".join(x).strip() for k, x in v.items()}


def readme(head):
    ver = verdicts(REPO / "re/lib-review/verdicts.md")
    out = [Path(head).read_text().rstrip(), "", "## 1. Variants and look-alikes, line by line", "",
           "Reading guide: `[fix X]` = link-time fixup site (masked in the signature; value is the linker's choice); "
           "`same-op, fixup` = opcode equal, operand is a fixup (address of whatever the linker placed); "
           "`**DIFF ...**` = a real byte difference. Placement = best fuzzy placement of the .LIB bytes in the vendor banks.", ""]
    for name, at in VARIANTS:
        title = name + (f" (vendor placement forced to {at})" if at else "")
        out.append(f"### 1.{VARIANTS.index((name, at)) + 1} {title}")
        out.append("")
        out.append(side(name, at).split("\n", 2)[2])
        if not at:
            path, src = c_source(name)
            out += ["", f"C source ({path}):" if path else "C source: none found", "", "```c", src or "", "```", ""]
            out += [ver.get(name, "verdict: TODO"), ""]
        else:
            out += ["", ver.get(name + " @" + at, ""), ""]
    out += ["### TCON constants (all 14 ScalerTconNEnable, bytes identical apart from the data-port index)", "",
            "| function | index byte (R5) / port | vendor 2:FCE7 same? |", "|---|---|---|"]
    fns = lib_functions()
    for i in range(14):
        m, seg, off, size = fns[f"ScalerTcon{i}Enable"]
        b = bytes(seg.data[off:off + size])
        out.append(f"| ScalerTcon{i}Enable | {b[17]:02X} (port {NAMES.get(b[21] << 8 | b[19], '?')}) | no (vendor index 25h, port DISPLAY_FORMAT_ADDR_PORT) |")
    out += ["", unsourced_md()[0]]
    Path(REPO / "re/lib-review/README.md").write_text("\n".join(out))
    log(f"wrote re/lib-review/README.md")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("side"); s.add_argument("name"); s.add_argument("--at")
    sp.add_parser("unsourced")
    r = sp.add_parser("readme"); r.add_argument("--head", default=str(REPO / "re/lib-review/README.head.md"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "side":
        print(side(a.name, a.at))
    elif a.cmd == "unsourced":
        print(unsourced_md()[0])
    else:
        readme(a.head)


if __name__ == "__main__":
    main()
