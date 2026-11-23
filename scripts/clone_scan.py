#!/usr/bin/env python3
"""Clone detector (#283): maximal runs of identical normalised lines across tracked files.

usage: clone_scan.py [--min-lines N] [--norm] [--lang c|py|both] [--tsv OUT] [PATH ...]
       clone_scan.py --functions [--layout TSV] [--tsv OUT] [PATH ...]   (per-instance function families)
       clone_scan.py --asm DIR [--tsv OUT]   (compiled functions identical after symbol digits -> #)
  PATH: git pathspecs (default fw scripts tools); sdk-parked and generated files are skipped.
  Normalise: comments, blank lines, brace-only lines dropped; whitespace collapsed.
  --norm: digit runs become 0, so Rx2/Rx3, _D2_/_D3_, P71/P72 copies match as one class.
  TSV: class, lines, copies, norm, locations (file:first-last, in whole-file line numbers).
  --functions: C functions grouped by name with digits -> #; per family: copies, lines, min similarity of the
    copies to the first after digit normalisation (1.00 = identical), recoverable bytes (all linked copies minus the largest) and linked copy count, from --layout.
Log: ./tmp/logs/clone_scan.log
"""
import argparse
import difflib
import hashlib
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False).stdout.strip()
    or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/clone_scan.log"
SKIP = re.compile(r"fw/sdk-parked/|_gen[._]|set_table\.c|fw/log/sync\.c|bank_layout|/facts/regs/|third_party/|\.json$"
                  r"|fw/sdk/Panel/|Common/RLE?(?!6449)\w+_\w+\.h|Pcb/RL6449/LQFP_\d+/(?!RL6449_AWTO)|Project/Header/RL(?!6449)"
                  r"|Gamma|HdcpRxKey|FontWidthTable")
TABLE = re.compile(r"^[{\s]*(0[xX][0-9A-Fa-f]+|\d+)[\s,0-9A-Fa-fxX{}+\-]*$")
C_EXT = (".c", ".h")
PY_EXT = (".py",)
TRIVIAL = re.compile(r"^[{}();,\s]*$|^#\s*(endif|else)\b|^else$|^return;$|^break;$")
CMT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)         # one pass: `//****` lines must not open a block comment
DIGITS = re.compile(r"\d+")


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(s + "\n")
    print(s)


def norm_lines(path, digits):
    """[(orig_line_no, normalised_text)] for the substantive lines of one file."""
    txt = (ROOT / path).read_text(errors="replace")
    py = path.endswith(PY_EXT)
    if not py:
        txt = CMT.sub(lambda m: "\n" * m.group(0).count("\n"), txt)
    out = []
    for no, raw in enumerate(txt.split("\n"), 1):
        s = re.sub(r"\s*#.*$", "", raw) if py else raw
        s = " ".join(s.split())
        if not s or TRIVIAL.match(s) or (not py and TABLE.match(s)):
            continue
        if digits:
            s = DIGITS.sub("0", s)
        out.append((no, s))
    return out


def scan(files, k, digits):
    seqs = {f: norm_lines(f, digits) for f in files}
    groups = defaultdict(list)                       # window hash -> [(file idx, pos)]
    names = list(seqs)
    for fi, f in enumerate(names):
        t = [s for _, s in seqs[f]]
        for i in range(len(t) - k + 1):
            groups[hashlib.blake2b("\n".join(t[i:i + k]).encode(), digest_size=8).digest()].append((fi, i))
    groups = {h: m for h, m in groups.items() if len(m) > 1}
    where = {}                                       # (fi, pos) -> hash
    for h, m in groups.items():
        for p in m:
            where[p] = h
    succ, has_pred = {}, set()
    for h, m in groups.items():
        nxt = where.get((m[0][0], m[0][1] + 1))
        if nxt is not None and groups[nxt] == [(a, b + 1) for a, b in m]:
            succ[h] = nxt
            has_pred.add(nxt)
    runs = []
    for h in groups:
        if h in has_pred:
            continue
        n, cur = 1, h
        while cur in succ:
            cur = succ[cur]
            n += 1
        runs.append((h, n))
    runs.sort(key=lambda r: -(r[1] + k - 1) * len(groups[r[0]]))
    covered = defaultdict(set)                       # file -> covered normalised-line positions
    classes = []
    for h, n in runs:
        m = groups[h]
        ln = n + k - 1
        if any(abs(a[1] - b[1]) < ln for a in m for b in m if a[0] == b[0] and a != b):
            continue                                 # periodic data overlapping itself
        if all(all(p in covered[names[fi]] for p in range(i, i + ln)) for fi, i in m):
            continue
        locs = []
        for fi, i in m:
            s = seqs[names[fi]]
            locs.append(f"{names[fi]}:{s[i][0]}-{s[i + ln - 1][0]}")
            covered[names[fi]].update(range(i, i + ln))
        classes.append((ln, len(m), locs))
    return classes


KEYWORDS = {"if", "for", "while", "switch", "else", "do", "pragma", "sizeof", "return", "index", "main"}
FUNC_HEAD = re.compile(r"(\w+)\s*\([^;{}]*\)[^;{}()]*$")
STR = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')


def functions(path):
    """[(name, first_line, last_line, [normalised body lines])]: Allman style, `{` and `}` alone at column 0."""
    txt = (ROOT / path).read_text(errors="replace")
    txt = STR.sub('""', CMT.sub(lambda m: "\n" * m.group(0).count("\n"), txt))
    lines = txt.split("\n")
    out, head, start, name = [], [], 0, ""
    for no, raw in enumerate(lines, 1):
        if start:
            if raw.rstrip() == "}":
                body = [DIGITS.sub("0", " ".join(x.split())) for x in lines[start - 1:no] if x.strip()]
                out.append((name, start, no, body))
                start, head = 0, []
            continue
        s = raw.strip()
        if raw.rstrip() == "{":
            m = FUNC_HEAD.search(" ".join(head))
            if m and m.group(1) not in KEYWORDS and "=" not in " ".join(head):
                start, name = no, m.group(1)
            head = []
        elif not s or s.startswith("#") or s.endswith((";", "}")):
            head = []
        else:
            head.append(s)
    return out


def layout_sizes(path):
    """name -> bytes: CH_<name> area sizes of a linker map, or row sizes of a bank_layout.tsv."""
    sz = {}
    txt = Path(path).read_text(errors="replace")
    if str(path).endswith(".map"):
        by_addr = {}                                 # area names are cut at 32 chars; the CH_name=0xADDR lines are not
        for m in re.finditer(r"^CH_\w+\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =", txt, re.MULTILINE):
            by_addr[int(m.group(1), 16)] = int(m.group(2), 16)
        for m in re.finditer(r"^CH_(\w+)=0x([0-9a-f]+)$", txt, re.MULTILINE):
            sz[m.group(1)] = by_addr.get(int(m.group(2), 16), 0)
        return sz
    for ln in txt.split("\n"):
        c = ln.split("\t")
        if len(c) == 5 and c[0] == "fn":
            sz[c[1].lstrip("_")] = int(c[4])
    return sz


def asm_clones(adir, tsv):
    """Group compiler .asm functions by body with comments, local labels and digits in `_symbols` normalised."""
    grp = defaultdict(list)
    for f in sorted(Path(adir).glob("*.asm")):
        name, body = None, []
        for ln in [*f.read_text(errors="replace").split("\n"), "_END:"]:
            if re.match(r"^_\w+:", ln):
                if name and len(body) > 3:
                    key = "\n".join(re.sub(r"_\w+", lambda m: re.sub(r"\d+", "#", m.group(0)), x) for x in body)
                    grp[key].append((name, f.name, len(body)))
                name, body = ln.split(":")[0], []
            elif name and ln.strip() and not ln.lstrip().startswith((";", ".")):
                body.append(re.sub(r"\b\d\d\d\d\d\$", "L", ln.strip()))
    rows = sorted(((len(m) - 1) * m[0][2], m) for m in grp.values() if len(m) > 1)[::-1]
    with Path(tsv).open("w") as fh:
        fh.write("redundant_instr\tcopies\tinstr\tnames\n")
        fh.writelines(f"{r}\t{len(m)}\t{m[0][2]}\t{' '.join(x[0] + '@' + x[1] for x in m)}\n" for r, m in rows)
    say(f"clone_scan: {len(rows)} identical-after-normalisation compiled function groups -> {tsv}")


def families(files, mp, tsv):
    sizes = layout_sizes(mp)
    fam = defaultdict(list)
    for f in files:
        for name, a, b, body in functions(f):
            fam[re.sub(r"\d+", "#", name)].append((name, f, a, b, body))
    rows = []
    for key, mem in fam.items():
        if len(mem) < 2:
            continue
        base = mem[0][4]
        sims = [difflib.SequenceMatcher(None, base, m[4], autojunk=False).ratio() for m in mem[1:]]
        per = [sizes.get(m[0], 0) for m in mem]
        rows.append((len(base) * (len(mem) - 1), key, len(mem), len(base), min(sims), (sum(per) - max(per), sum(1 for x in per if x)),
                     " ".join(f"{m[1]}:{m[2]}-{m[3]}" for m in mem)))
    rows.sort(reverse=True)
    with Path(tsv).open("w") as fh:
        fh.write("dup_lines\tfamily\tcopies\tlines\tmin_sim\trecoverable_bytes\tlinked_copies\tlocations\n")
        fh.writelines(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]:.2f}\t{r[5][0]}\t{r[5][1]}\t{r[6]}\n" for r in rows)
    say(f"clone_scan: {len(rows)} function families -> {tsv}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", default=["fw", "scripts", "tools"])
    ap.add_argument("--min-lines", type=int, default=12)
    ap.add_argument("--norm", action="store_true", help="digit runs -> 0 (per-port copies match)")
    ap.add_argument("--lang", choices=["c", "py", "both"], default="both")
    ap.add_argument("--tsv", type=Path, default=ROOT / "tmp/logs/clone_scan.tsv")
    ap.add_argument("--asm", type=Path, help="compiler .asm directory: object-level clones")
    ap.add_argument("--functions", action="store_true", help="per-instance function families")
    ap.add_argument("--layout", type=Path, default=ROOT / "tmp/sdcc-port/bank_layout.new.tsv", help="sizes for --functions: a linker .map or bank_layout.tsv")
    a = ap.parse_args()
    ext = {"c": C_EXT, "py": PY_EXT, "both": C_EXT + PY_EXT}[a.lang]
    ls = subprocess.run(["git", "ls-files", *a.paths], cwd=ROOT, capture_output=True, text=True, check=True)
    files = [f for f in ls.stdout.split("\n") if f.endswith(ext) and not SKIP.search(f)]
    if a.asm:
        asm_clones(a.asm, a.tsv)
        return 0
    if a.functions:
        families([f for f in files if f.endswith(C_EXT)], a.layout, a.tsv)
        return 0
    say(f"clone_scan: {len(files)} files, min-lines {a.min_lines}, norm {a.norm}")
    classes = scan(files, a.min_lines, a.norm)
    classes.sort(key=lambda c: -c[0] * (c[1] - 1))
    a.tsv.parent.mkdir(parents=True, exist_ok=True)
    with a.tsv.open("w") as f:
        f.write("class\tlines\tcopies\tdup_lines\tnorm\tlocations\n")
        for n, (ln, cp, locs) in enumerate(classes, 1):
            f.write(f"{n}\t{ln}\t{cp}\t{ln * (cp - 1)}\t{int(a.norm)}\t{' '.join(locs)}\n")
    say(f"clone_scan: {len(classes)} classes, {sum(c[0] * (c[1] - 1) for c in classes)} redundant lines -> {a.tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
