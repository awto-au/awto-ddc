#!/usr/bin/env python3
"""Map SDK globals to vendor XDATA/IDATA addresses -> re/jxc-4k/ghidra_globals.tsv (typed labels, applied by re/ghidra/ApplySdkTypes.java).

usage: ghidra_globals_map.py [--min-score 1.0]
Method (details: docs/re-full-reversal.md):
 1. SDK inventory: every `_name::` in XSEG/DSEG/ISEG/BSEG of tmp/sdcc-port/asm (size from `.ds`, declaration order per module = Keil ?XD? order).
 2. Anchors: vendor functions already named as an SDK function ([lib] exact-signature, [auto-sdk] fingerprint, [fw] when the name is an SDK name).
    Per anchor pair: SDK `mov dptr,#_g (+off)` set vs vendor `MOV DPTR,#imm` set (imm in 0xD700-0xF6FF).
    Candidate base of g = imm - off for every vendor imm where ALL of g's offsets land on vendor immediates; vote 1/#candidates per function.
 3. Accept: score >= 1.0, >= 2x the runner-up, and >= 2 supporting functions (or one exact [lib] match with a single candidate); overlaps resolved by score.
    No declaration-order layout extrapolation: Keil's ?XD? order within a module is not declaration order (docs/re-full-reversal.md).
 4. Hand rows (re/jxc-4k/ghidra_globals_hand.tsv, same columns) are appended and win on name/address clashes.
Vendor side: ~/vendors/realtek/analysis/jxc-4k/bank<N>/disassembly.asm + names TSVs. Log: ./tmp/logs/ghidra_globals_map.log
"""
import math, os, re, sys
from collections import defaultdict, Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)
ASM = ROOT / "tmp" / "sdcc-port" / "asm"
VEND = Path.home() / "vendors/realtek/analysis/jxc-4k"
DATA = ROOT / "re" / "jxc-4k"
SDKG = ROOT / "tmp" / "ghidra_types" / "sdk_globals.tsv"
OUT = DATA / "ghidra_globals.tsv"
LOG = ROOT / "tmp" / "logs" / "ghidra_globals_map.log"
RAM = range(0xD700, 0xF700)
AREAS = ("XSEG", "DSEG", "ISEG", "BSEG", "PSEG")
TOK = re.compile(r"mov\s+dptr,\s*#\(?\s*(_\w+)(?:\s*\+\s*(0x[0-9a-fA-F]+|\d+))?\s*\)?")
LABEL = re.compile(r"^(_[A-Za-z0-9_]+):")
VDPTR = re.compile(r"^CODE:([0-9a-f]{4}):\s+MOV DPTR,#0x([0-9a-f]{4})\b")
VHEAD = re.compile(r"^; ==== (\S+) @ CODE:([0-9a-f]{4}) ====")
_logf = []


def log(m):
    _logf.append(m); print(m)


def sdk():
    glob, funcs, mods = {}, {}, defaultdict(list)    # glob: name -> (area, size, module)
    files = sorted(ASM.glob("*.asm")) + sorted((ASM / "Kernel").rglob("*.asm"))
    for f in files:
        area, cur = None, None
        for ln in f.read_text(errors="replace").splitlines():
            m = re.match(r"\s*\.area (\w+)", ln)
            if m:
                area = m.group(1); continue
            m = re.match(r"^(_\w+)::\s*$", ln)
            if m and area in AREAS:
                cur = m.group(1)[1:]; continue
            m = re.match(r"\s*\.ds\s+(\d+)", ln)
            if m and cur:
                if cur not in glob:
                    glob[cur] = (area, int(m.group(1)), f.stem); mods[f.stem].append(cur)
                cur = None
            elif not ln.startswith(("_", ";")) and "ds" not in ln:
                pass
            if ln.startswith("_") and "::" not in ln:
                cur = None
    for f in files:
        area, cur = None, None
        for ln in f.read_text(errors="replace").splitlines():
            m = re.match(r"\s*\.area (\w+)", ln)
            if m:
                area = m.group(1); continue
            if area != "CSEG":
                continue
            m = LABEL.match(ln)
            if m and not m.group(1).startswith("__") and not re.match(r"^_?\d", m.group(1)):
                n = m.group(1)[1:]
                cur = None if n in funcs else funcs.setdefault(n, [])
                continue
            if cur is None:
                continue
            t = TOK.search(ln)
            if t and t.group(1)[1:] in glob:
                cur.append((t.group(1)[1:], int(t.group(2), 0) if t.group(2) else 0))
    return glob, funcs, mods


def vendor_names(bank):
    """code addr -> (name, status) for named functions."""
    out = {}
    for ln in (DATA / f"ghidra_names_bank{bank}.tsv").read_text().splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        f = ln.split("\t")
        if len(f) >= 5 and f[2] == "func" and f[0].upper().startswith("CODE:"):
            out[int(f[0][5:], 16)] = (f[1], f[4])
    return out


def vendor_funcs(bank):
    """func code addr -> ordered unique list of RAM immediates."""
    fn, cur = {}, None
    for ln in (VEND / f"bank{bank}" / "disassembly.asm").read_text(errors="replace").splitlines():
        h = VHEAD.match(ln)
        if h:
            cur = fn.setdefault(int(h.group(2), 16), []); continue
        m = VDPTR.match(ln)
        if m and cur is not None:
            a = int(m.group(2), 16)
            if a in RAM and a not in cur:
                cur.append(a)
    return fn


IMM_S = re.compile(r"^\s*(?:mov\s+(?:a|r[0-7]|@r[01]|dpl|dph|\w+),|anl\s+a,|orl\s+a,|xrl\s+a,|add\s+a,|addc\s+a,|subb\s+a,|cjne\s+(?:a|r[0-7]|@r[01]),)\s*#(0x[0-9a-fA-F]+)")
IMM_V = re.compile(r"^CODE:[0-9a-f]{4}:\s+(?:MOV (?:A|R[0-7]|@R[01]|DPL|DPH|0x[0-9a-f]+),|ANL A,|ORL A,|XRL A,|ADD A,|ADDC A,|SUBB A,|CJNE (?:A|R[0-7]|@R[01]|0x[0-9a-f]+),)#(0x[0-9a-f]+)")
DP_S = re.compile(r"mov\s+dptr,\s*#(0x[0-9a-fA-F]{4})\b")
REGLABELS = ROOT / "tmp" / "regs_labels.tsv"


def reg_set():
    return {int(l.split("\t")[0][7:], 16) for l in REGLABELS.read_text().splitlines() if l.startswith("EXTMEM:")}


def sdk_feats(regs):
    """SDK function -> {('c', imm) 8/16-bit constants except 0/1, ('r', regaddr)}."""
    out = {}
    for f in sorted(ASM.glob("*.asm")) + sorted((ASM / "Kernel").rglob("*.asm")):
        area, cur = None, None
        for ln in f.read_text(errors="replace").splitlines():
            m = re.match(r"\s*\.area (\w+)", ln)
            if m:
                area = m.group(1); continue
            if area != "CSEG":
                continue
            m = LABEL.match(ln)
            if m and not m.group(1).startswith("__") and not re.match(r"^_?\d", m.group(1)):
                n = m.group(1)[1:]
                cur = None if n in out else out.setdefault(n, set()); continue
            if cur is None:
                continue
            i = IMM_S.match(ln)
            if i and int(i.group(1), 16) not in (0, 1):
                cur.add(("c", int(i.group(1), 16) & 0xffff))
            d = DP_S.search(ln)
            if d and int(d.group(1), 16) in regs:
                cur.add(("r", int(d.group(1), 16)))
    return out


def vendor_feats(bank, regs):
    out, cur = {}, None
    for ln in (VEND / f"bank{bank}" / "disassembly.asm").read_text(errors="replace").splitlines():
        h = VHEAD.match(ln)
        if h:
            cur = out.setdefault(int(h.group(2), 16), set()); continue
        if cur is None:
            continue
        i = IMM_V.match(ln)
        if i and int(i.group(1), 16) not in (0, 1):
            cur.add(("c", int(i.group(1), 16)))
        d = re.match(r"^CODE:[0-9a-f]{4}:\s+MOV DPTR,#(0x[0-9a-f]{4})", ln)
        if d and int(d.group(1), 16) in regs:
            cur.add(("r", int(d.group(1), 16)))
    return out


def const_matches(regs, bank, S, idf, inv, cand, T=0.30, MG=0.10):
    """Vendor functions -> best SDK function by weighted Jaccard of constants+registers (95-98% top-1 on the named set)."""
    out = {}
    for fa, f in vendor_feats(bank, regs).items():
        if len(f) < 4:
            continue
        pool = set().union(*(inv.get(t, set()) for t in f))
        sc = sorted(((sum(idf(t) for t in f & cand[n]) / sum(idf(t) for t in f | cand[n]), n) for n in pool), reverse=True)[:2]
        if sc and sc[0][0] >= T and sc[0][0] - (sc[1][0] if len(sc) > 1 else 0) >= MG:
            out[fa] = (sc[0][1], "[cmatch]")
    return out


def main():
    a = sys.argv[1:]
    min_score = float(a[a.index("--min-score") + 1]) if "--min-score" in a else 1.0
    glob, funcs, mods = sdk()
    log(f"SDK globals {len(glob)} ({Counter(v[0] for v in glob.values())}), functions {len(funcs)}, with global refs {sum(1 for v in funcs.values() if v)}")
    regs = reg_set()
    S = sdk_feats(regs)
    cand = {n: f for n, f in S.items() if len(f) >= 4}
    dfc = Counter(t for f in cand.values() for t in f)
    idf = lambda t: math.log(1 + len(cand) / dfc.get(t, 1))
    inv = defaultdict(set)
    for n, f in cand.items():
        for t in f:
            inv[t].add(n)
    pl = []                                              # (bank, func addr, status, weight, {g: offsets}, vendor RAM immediates)
    for bank in range(7):
        names, vf = vendor_names(bank), vendor_funcs(bank)
        weak = {}                                          # fingerprint candidates below the naming threshold: weight 0.5
        cp = ROOT / "tmp" / f"match_bank{bank}.tsv"
        if cp.exists():
            for ln in cp.read_text().splitlines()[1:]:
                f = ln.split("\t")
                if float(f[3]) >= 0.30 and float(f[3]) - float(f[4]) >= 0.05 and int(f[0], 16) not in names:
                    weak[int(f[0], 16)] = (f[2], "[weak]")
        cm = {fa: v for fa, v in const_matches(regs, bank, S, idf, inv, cand).items() if fa not in names and fa not in weak}
        for fa, (nm, st) in list(names.items()) + list(weak.items()) + list(cm.items()):
            toks = funcs.get(nm)
            if not toks or fa not in vf or not vf[fa]:
                continue
            byg = defaultdict(set)
            for g, off in toks:
                if glob[g][0] == "XSEG":
                    byg[g].add(off)
            if byg:
                pl.append((bank, fa, st, {"[weak]": 0.5, "[cmatch]": 0.7}.get(st, 1.0), byg, vf[fa]))
    log(f"anchor pairs with RAM refs: {len(pl)} ({Counter(x[2] for x in pl)})")
    taken, acc = {}, {}
    for rnd in range(8):
        votes = defaultdict(lambda: defaultdict(float))      # g -> base -> score
        support = defaultdict(lambda: defaultdict(set))      # g -> base -> {(bank, func, status)}
        for bank, fa, st, wt, byg, va0 in pl:
            va = list(va0)
            todo = {}
            for g, offs in byg.items():                      # explain-away: accepted globals consume their immediates here
                if g in acc:
                    for o in offs:
                        if acc[g][0] + o in va:
                            va.remove(acc[g][0] + o)
                else:
                    todo[g] = offs
            for g, offs in todo.items():
                cands = {v - o for v in va for o in offs}
                cands = {c for c in cands if all((c + o) in va for o in offs)
                         and not any((c + i) in taken for i in range(glob[g][1]))}
                for c in cands:
                    votes[g][c] += wt / len(cands)
                    support[g][c].add((bank, fa, st if len(cands) == 1 else "-"))
        best = []
        for g, d in votes.items():
            ranked = sorted(d.items(), key=lambda kv: -kv[1])
            sc, c = ranked[0][1], ranked[0][0]
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            nfun = len({fa for (_, fa, _) in support[g][c]})
            lib1 = any(x[2] == "[lib]" for x in support[g][c])
            best.append((sc, g, c, second, nfun, lib1))
        best.sort(reverse=True)
        new = 0
        for sc, g, c, second, nfun, lib1 in best:
            if sc < min_score or sc < 2 * second or (nfun < 2 and not lib1):
                continue
            size = glob[g][1]
            if any((c + i) in taken for i in range(size)):
                continue
            for i in range(size):
                taken[c + i] = g
            acc[g] = (c, sc, nfun, lib1)
            new += 1
        log(f"round {rnd}: globals with votes {len(best)}, newly accepted {new}, total {len(acc)}")
        if not new:
            break
    # layout pass
    rows = {g: (c, "[anchor]", f"anchored by {nfun} matched function(s), score {sc:.1f}") for g, (c, sc, nfun, lib1) in acc.items()}
    # types
    types = {}
    if SDKG.exists():
        for ln in SDKG.read_text().splitlines()[1:]:
            f = ln.split("\t")
            types[f[0]] = (f[2], f[3], f[4])
    lines = ["# ghidra_globals.tsv - SDK globals at their vendor XDATA addresses. Generated by scripts/ghidra_globals_map.py (+hand rows allowed below the marker).",
             "# Format: address<TAB>name<TAB>type<TAB>comment<TAB>status   (type: u8 s8 u16 s16 u32 s32 ptr3, <StructName>, with [n] for arrays; sdk_types.tsv)",
             "# status: [anchor] voted by matched functions, [hand] from ghidra_globals_hand.tsv"]
    for g, (c, st, cm) in sorted(rows.items(), key=lambda kv: kv[1][0]):
        size = glob[g][1]
        tref, tsize, dims = types.get(g, (None, None, None))
        if tref and tsize.isdigit() and int(tsize) == size:
            if dims:
                n = 1
                for d in dims.split("x"):
                    n *= int(d)
                ty = f"{tref}[{n}]" if n > 1 else tref
            else:
                ty = tref
            if ty.startswith("ptr"):
                ty = "ptr3" if size == 3 else "u8"
        else:
            ty = {1: "u8", 2: "u16", 4: "u32"}.get(size, f"u8[{size}]")
        lines.append(f"EXTMEM:{c:04x}\t{g}\t{ty}\t{cm}\t{st}")
    hand = DATA / "ghidra_globals_hand.tsv"
    if hand.exists():
        for ln in hand.read_text().splitlines():
            if ln.strip() and not ln.startswith("#"):
                lines.append(ln)
    OUT.write_text("\n".join(lines) + "\n")
    na = sum(1 for v in rows.values() if v[1] == "[anchor]")
    log(f"wrote {OUT}: {len(rows)} globals ({na} anchor, {len(rows)-na} layout) of {sum(1 for v in glob.values() if v[0]=='XSEG')} xdata globals")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(_logf) + "\n")


if __name__ == "__main__":
    main()
