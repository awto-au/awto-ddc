#!/usr/bin/env python3
"""Name vendor functions by matching them against our SDCC build of the same SDK (register-access fingerprints).

usage: ghidra_match_sdk.py [--min-regs 3] [--min-score 0.60] [--margin 0.10] [--apply] [--banks 0 1 ...]
Vendor side: ~/vendors/realtek/analysis/jxc-4k/bank<N>/regwrites.tsv + regreads.tsv (re/ghidra/ExportRegAccess.java).
Our side: tmp/sdcc-port/asm_bank/*.asm + tmp/sdcc-port/asm/**/*.asm; every `_name:` function is fingerprinted by
  - registers: `mov dptr,#0xHHHH` constants that are regdb registers (not XRAM), idf-weighted
  - tokens reg:imm: immediates of the mov a,#/anl a,#/orl a,#/xrl a,#/clr a following that dptr load
Score = weighted Jaccard (registers) + 0.5 x weighted Jaccard (tokens) normalised; accepted when >= min-score, the vendor
function has >= min-regs distinct registers, and the best SDK name leads the runner-up by >= margin.
--apply appends `CODE:<addr>  <name>  func  <comment>  [auto-sdk]` to re/jxc-4k/ghidra_names_bank<N>.tsv
(existing entries of any status are never changed; one name per address, one address per name per bank).
Report: ./tmp/logs/ghidra_match_sdk.log (match rate per bank), candidates: ./tmp/match_bank<N>.tsv
"""
import csv, math, os, re, sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
VEND = Path.home() / "vendors/realtek/analysis/jxc-4k"
SDK = ROOT / "tmp" / "sdcc-port"
RAM = range(0xD700, 0xF700)
LABELS = ROOT / "tmp" / "regs_labels.tsv"


def reg_set():
    s = set()
    for ln in LABELS.read_text().splitlines():
        if ln.startswith("EXTMEM:"):
            s.add(int(ln.split("\t")[0][7:], 16))
    return s


DPTR = re.compile(r"mov\s+dptr,\s*#0x([0-9a-fA-F]{4})\b")
IMM = re.compile(r"(?:mov\s+a,|anl\s+a,|orl\s+a,|xrl\s+a,)\s*#0x([0-9a-fA-F]{1,2})\b")
LABEL = re.compile(r"^(_[A-Za-z0-9_]+):")
CALL = re.compile(r"\b[la]call\s+(_[A-Za-z0-9_]+)")


def sdk_funcs(regs):
    """name -> (set regs, set tokens, set callees)"""
    out = {}
    files = sorted((SDK / "asm_bank").glob("*.asm")) + sorted((SDK / "asm").rglob("*.asm"))
    for f in files:
        cur, last = None, None
        for ln in f.read_text(errors="replace").splitlines():
            m = LABEL.match(ln)
            if m and not m.group(1).startswith("__"):
                name = m.group(1).lstrip("_")
                cur = None if name in out else out.setdefault(name, [set(), set(), set()])
                last = None
                continue
            if cur is None:
                continue
            d = DPTR.search(ln)
            if d:
                a = int(d.group(1), 16)
                last = a if (a in regs and a not in RAM) else None
                if last is not None:
                    cur[0].add(last)
                continue
            if last is not None:
                i = IMM.search(ln)
                if i:
                    cur[1].add((last, int(i.group(1), 16)))
                elif "clr\ta" in ln:
                    cur[1].add((last, 0))
            c = CALL.search(ln)
            if c:
                cur[2].add(c.group(1).lstrip("_"))
    return {n: (v[0], v[1], v[2]) for n, v in out.items() if v[0]}


def vendor_funcs(bank):
    """func_addr -> (name, regs, tokens)"""
    fn = {}
    for fname, wr in (("regwrites.tsv", True), ("regreads.tsv", False)):
        p = VEND / f"bank{bank}" / fname
        for r in csv.DictReader((l for l in p.open() if not l.startswith("#")), delimiter="\t"):
            if not r["func_addr"] or r["reg_addr"] in ("?", ""):
                continue
            a = int(r["reg_addr"], 16)
            if a in RAM:
                continue
            e = fn.setdefault(int(r["func_addr"], 16), [r["func"], set(), set()])
            e[1].add(a)
            if wr:
                for k in ("value", "and_mask", "or_mask"):
                    v = r.get(k, "")
                    if v.startswith("0x"):
                        e[2].add((a, int(v, 16)))
            elif r.get("mask", "").startswith("0x"):
                e[2].add((a, int(r["mask"], 16)))
    return fn


def jac(a, b, w):
    u = a | b
    if not u:
        return 0.0
    return sum(w(x) for x in a & b) / sum(w(x) for x in u)


def main():
    a = sys.argv[1:]
    opt = lambda k, d, t=float: t(a[a.index(k) + 1]) if k in a else d
    min_regs, min_score, margin = opt("--min-regs", 3, int), opt("--min-score", 0.60), opt("--margin", 0.10)
    banks = [int(x) for x in a[a.index("--banks") + 1:]] if "--banks" in a else range(7)
    regs = reg_set()
    sdk = sdk_funcs(regs)
    df = Counter(r for v in sdk.values() for r in v[0])
    n = len(sdk)
    idf = lambda r: math.log(1 + n / df.get(r, 1)) if isinstance(r, int) else math.log(1 + n / df.get(r[0], 1)) * 1.5
    log = ROOT / "tmp" / "logs" / "ghidra_match_sdk.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"sdk functions with register fingerprints: {n}"]
    byreg = defaultdict(set)
    for nm, v in sdk.items():
        for r in v[0]:
            byreg[r].add(nm)
    for bank in banks:
        vf = vendor_funcs(bank)
        tsv = ROOT / "re" / "jxc-4k" / f"ghidra_names_bank{bank}.tsv"
        have = tsv.read_text() if tsv.exists() else ""
        named_addr = {l.split("\t")[0].lower() for l in have.splitlines() if l and not l.startswith("#")}
        named_name = {l.split("\t")[1] for l in have.splitlines() if l and not l.startswith("#") and "\t" in l}
        cands, eligible = [], 0
        for fa, (fname, vr, vt) in vf.items():
            if len(vr) < min_regs:
                continue
            eligible += 1
            pool = set().union(*(byreg.get(r, set()) for r in vr)) if vr else set()
            sc = []
            for nm in pool:
                sr, st, _ = sdk[nm]
                s = jac(vr, sr, idf) + 0.5 * jac(vt, st, idf) if (vt and st) else jac(vr, sr, idf)
                s = s / (1.5 if (vt and st) else 1.0)
                sc.append((s, nm))
            sc.sort(reverse=True)
            if not sc:
                continue
            best = sc[0]
            second = sc[1][0] if len(sc) > 1 else 0.0
            cands.append((fa, fname, best[1], best[0], second, len(vr)))
        acc, used = [], set()
        for fa, fname, nm, s, s2, k in sorted(cands, key=lambda c: -c[3]):
            addr = f"code:{fa:04x}"
            ok = s >= min_score and s - s2 >= margin
            if ok and nm not in used and nm not in named_name and addr not in named_addr:
                used.add(nm); acc.append((fa, nm, s, k))
        cp = ROOT / "tmp" / f"match_bank{bank}.tsv"
        with cp.open("w") as f:
            f.write("func_addr\tvendor_name\tbest_sdk\tscore\trunner_up\tn_regs\taccepted\n")
            accd = {x[0] for x in acc}
            for c in cands:
                f.write(f"{c[0]:04x}\t{c[1]}\t{c[2]}\t{c[3]:.3f}\t{c[4]:.3f}\t{c[5]}\t{int(c[0] in accd)}\n")
        total = len(vf)
        lines.append(f"bank{bank}: functions with reg accesses {total}, eligible (>= {min_regs} regs) {eligible}, "
                     f"accepted {len(acc)} ({100*len(acc)/max(eligible,1):.0f}% of eligible, {100*len(acc)/max(total,1):.0f}% of accessing)")
        if "--apply" in a and acc:
            with tsv.open("a") as f:
                if not have.endswith("\n") and have:
                    f.write("\n")
                for fa, nm, s, k in sorted(acc):
                    f.write(f"CODE:{fa:04x}\t{nm}\tfunc\tauto: matched SDK {nm} by register fingerprint, score {s:.2f}, {k} regs.\t[auto-sdk]\n")
    msg = "\n".join(lines)
    print(msg)
    log.open("a").write(msg + "\n")


if __name__ == "__main__":
    main()
