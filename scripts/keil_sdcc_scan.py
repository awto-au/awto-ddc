#!/usr/bin/env python3
"""Scan the Realtek SDK (+ overlay) for source sites where Keil C51 and SDCC give different results (#57, docs/keil-vs-sdcc.md).

usage: keil_sdcc_scan.py [--all]   (default: only files compiled for RL6449 = tmp/sdcc-port/asm/*.asm stems, plus headers
                                    outside other chip series / boards)
Output: re/keil_sdcc_scan.tsv (class, file:line, snippet, risk, handled, fix_where), summary in the log.
Log: tmp/logs/keil_sdcc_scan.log. Repo root: $AWTO_DDC_REPO -> git toplevel -> file-relative. SDK: $RTD_SDK.

Method: comment/string-stripped token scan + declaration table (per file, then global-unique) for bit/BYTE/SBYTE/...,
macro bodies for bit-typed macros, regex call graph for ISR reachability. Not a full C parse: macro-expanded and
typedef'd-through-struct types are unknown -> those operands are skipped (under-count, never over-claimed as handled).
"""
import os, re, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
OVERLAY = ROOT / "fw" / "overlay"
ASMDIR = ROOT / "tmp" / "sdcc-port" / "asm"
OUT = ROOT / "re" / "keil_sdcc_scan.tsv"
LOGF = ROOT / "tmp" / "logs" / "keil_sdcc_scan.log"
LOGF.parent.mkdir(parents=True, exist_ok=True)
LOG = open(LOGF, "w")


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


OTHER_CHIPS = re.compile(r"RL6369|RL6410|RL6432|RL6463|RL6492|None Factory|NoneOsd|NoneFunction")
TYPE_CLASS = {"bit": "bit", "BYTE": "u8", "unsigned char": "u8", "SBYTE": "s8", "char": "s8", "signed char": "s8",
              "WORD": "u16", "unsigned int": "u16", "unsigned short": "u16", "SWORD": "s16", "int": "s16", "short": "s16",
              "DWORD": "u32", "unsigned long": "u32", "SDWORD": "s32", "long": "s32"}
TYPE_RE = r"(?:unsigned\s+(?:char|int|short|long)|signed\s+char|bit|BYTE|SBYTE|WORD|SWORD|DWORD|SDWORD|char|int|short|long|Enum\w+)"
KW_QUAL = {"extern", "static", "const", "volatile", "xdata", "data", "idata", "pdata", "code", "bdata", "register", "auto"}
CLEAR_STMT = {";", "{", "}", "(", ",", ")"} | KW_QUAL


def strip(text):
    """Blank comments and string/char literals, keep newlines (line numbers hold)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i); j = n if j < 0 else j
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2); j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j)); i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append('"S"'); i = j + 1
        elif c == "'":
            j = i + 1
            while j < n and text[j] != "'" and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append("'c'"); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)


TOK = re.compile(r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|<<=|>>=|\+\+|--|->|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&|^]=|\S")


def tokenize(clean):
    toks = []
    for ln, line in enumerate(clean.split("\n"), 1):
        if line.lstrip().startswith("#"):
            continue
        for m in TOK.finditer(line):
            toks.append((m.group(0), ln))
    return toks


def join_macro_lines(raw):
    return re.sub(r"\\[ \t]*\r?\n", " ", raw)


class Src:
    def __init__(self, rel, path):
        self.rel, self.path = rel, path
        raw = path.read_bytes().decode("latin-1")
        self.raw = join_macro_lines(raw)
        self.clean = strip(raw)
        self.lines = raw.split("\n")
        self.toks = tokenize(self.clean)
        self.in_build = False

    def snip(self, ln, w=110):
        s = self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ""
        return re.sub(r"\s+", " ", s)[:w]


def collect_files(everything):
    files = {}
    for base in (SDK, OVERLAY):
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".c", ".h") and ".git" not in p.parts:
                files[str(p.relative_to(base))] = p                      # overlay replaces SDK copy
    built = {p.stem for p in ASMDIR.rglob("*.asm")} if ASMDIR.exists() else set()
    out = []
    for rel, p in sorted(files.items()):
        if not everything:
            if OTHER_CHIPS.search(rel) or (rel.startswith("Pcb/") and "AWTO" not in rel and "RL6449" not in rel):
                continue
            if p.suffix.lower() == ".c" and built and p.stem not in built:
                continue
        s = Src(rel, p)
        s.in_build = p.suffix.lower() == ".c" and p.stem in built
        out.append(s)
    return out


# ---------------- declaration table ----------------
def parse_decls(src):
    """Return (vars: name->class, funcs: name->ret class, enumtypes). Token-level declarator walk."""
    t = src.toks
    vars_, funcs = {}, {}
    i, n = 0, len(t)
    typeset = set(TYPE_CLASS) | {"unsigned", "signed"}
    while i < n:
        tok = t[i][0]
        prev = t[i - 1][0] if i else ";"
        if (tok in ("unsigned", "signed") or tok in TYPE_CLASS or tok.startswith("Enum")) and prev in CLEAR_STMT:
            j = i
            words = []
            while j < n and (t[j][0] in typeset or t[j][0].startswith("Enum") or t[j][0] in KW_QUAL):
                if t[j][0] not in KW_QUAL:
                    words.append(t[j][0])
                j += 1
            ty = " ".join(words)
            if ty in ("unsigned", "signed"):
                ty += " int"
            cls = TYPE_CLASS.get(ty, "enum" if ty.startswith("Enum") else None)
            if cls is None:
                i = j; continue
            while j < n:
                ptr = False
                while j < n and t[j][0] == "*":
                    ptr = True; j += 1
                while j < n and t[j][0] in KW_QUAL:
                    j += 1
                if j >= n or not re.match(r"[A-Za-z_]", t[j][0]):
                    break
                name = t[j][0]; j += 1
                if j < n and t[j][0] == "(":
                    if not ptr:
                        funcs[name] = cls
                    break
                if not ptr:
                    vars_[name] = cls
                else:
                    vars_.setdefault(name, "ptr")
                depth = 0
                while j < n:                                 # skip [N] / = init to the next top-level , or ;
                    x = t[j][0]
                    if x in "([{":
                        depth += 1
                    elif x in ")]}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif depth == 0 and x in ",;":
                        break
                    j += 1
                if j < n and t[j][0] == ",":
                    j += 1; continue
                break
            i = max(i + 1, j)
        else:
            i += 1
    return vars_, funcs


def parse_macros(files):
    """name -> (params, body). Includes function-like and object-like."""
    mac = {}
    rx = re.compile(r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)(\([^)]*\))?[ \t]*(.*)$", re.M)
    for s in files:
        for m in rx.finditer(strip_cpp_comments(s.raw)):
            mac.setdefault(m.group(1), (m.group(2), m.group(3).strip()))
    return mac


def strip_cpp_comments(raw):
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", raw, flags=re.S)


# ---------------- reporting ----------------
ROWS = []
SEEN = set()


def add(cls, src, ln, risk, handled, fix, snippet=None):
    key = (cls, src.rel, ln)
    if key in SEEN:
        return
    SEEN.add(key)
    ROWS.append((cls, f"{src.rel}:{ln}", snippet if snippet is not None else src.snip(ln), risk, handled, fix))


def operand_end(t, i):
    """Index after the unary operand starting at token i: ident[(..)|[..]|.x]* | ( .. ) | cast (T) operand."""
    n = len(t)
    if i >= n:
        return i
    if t[i][0] == "(":
        d, j = 0, i
        while j < n:
            if t[j][0] == "(":
                d += 1
            elif t[j][0] == ")":
                d -= 1
                if d == 0:
                    j += 1
                    break
            j += 1
        # cast: (TYPE) operand
        inner = [x[0] for x in t[i + 1:j - 1]]
        if inner and all(x in TYPE_CLASS or x in ("unsigned", "signed", "*") or x.startswith("Enum") for x in inner):
            return operand_end(t, j)
        return j
    j = i + 1
    while j < n and t[j][0] in ("(", "[", ".", "->"):
        if t[j][0] in ("(", "["):
            op, cl = ("(", ")") if t[j][0] == "(" else ("[", "]")
            d = 0
            while j < n:
                if t[j][0] == op:
                    d += 1
                elif t[j][0] == cl:
                    d -= 1
                    if d == 0:
                        j += 1
                        break
                j += 1
        else:
            j += 2
    return j


QUIET = {"SWITCH", "ENUM", "BITFIELD_LOW", "FLOAT", "SIZEOF_PTR"}      # no difference: counted in the log, not listed
KNOWN = ["NOT_BIT", "NOT_UCHAR_CTX", "UCHAR_CMP_NEG", "CHAR_VS_UCHAR_CMP", "UCHAR_SHL_WIDE", "DIV_VAR", "SIGNED_SHR", "WORD_VIEW",
         "UNION", "BITFIELD", "BDATA", "SBIT", "INTRINSIC", "PRAGMA", "STDIO", "LIB_RETURN", "EVAL_ORDER", "ISR_SHARED_NONVOLATILE",
         "FN_SHARED_ISR_MAIN", "INT_TO_BIT", "FUNC_PTR", "ISR_DEF", "ENUM", "SWITCH", "FLOAT", "SIZEOF_PTR"]


def main():
    everything = "--all" in sys.argv
    log(f"scan start: SDK {SDK}, overlay {OVERLAY}, scope {'ALL files' if everything else 'RL6449 build'}")
    files = collect_files(everything)
    log(f"files: {len(files)} ({sum(1 for s in files if s.in_build)} compiled C)")
    gvars, gfuncs = defaultdict(set), defaultdict(set)
    per = {}
    for s in files:
        v, f = parse_decls(s)
        per[s.rel] = (v, f)
        for k, c in v.items():
            gvars[k].add(c)
        for k, c in f.items():
            gfuncs[k].add(c)
    macros = parse_macros(files)
    bitfns = {k for k, c in gfuncs.items() if c == {"bit"}}
    bitvars = {k for k, c in gvars.items() if c == {"bit"}}
    # bit-typed macros: body is (bit) cast, a bit var/fn call, possibly parenthesised / negated with !
    bitmac = set()
    for _ in range(3):
        for name, (par, body) in macros.items():
            b = re.sub(r"^[\s(]+|[\s)]+$", "", body)
            m = re.match(r"^(?:\(\s*bit\s*\)|!)?\s*\(?\s*([A-Za-z_]\w*)", b)
            if body and m and not re.search(r"==|!=|<|>|&&|\|\||[^&]&[^&]|\|[^|]|\+|-|\*", b) and (
                    m.group(1) in bitvars or m.group(1) in bitfns or m.group(1) in bitmac or b.startswith("(bit)")):
                bitmac.add(name)
    log(f"decl table: {len(gvars)} vars, {len(gfuncs)} funcs, {len(bitvars)} bit vars, {len(bitfns)} bit fns, "
        f"{len(bitmac)} bit macros, {len(macros)} macros")

    def cls_of(s, name):
        v, _ = per[s.rel]
        if name in v:
            return v[name]
        g = gvars.get(name)
        if g and len(g) == 1:
            return next(iter(g))
        return None

    def is_bitish(s, name):
        return cls_of(s, name) == "bit" or name in bitfns and cls_of(s, name) is None or name in bitmac

    HANDLED_NOT_BIT = re.compile(r"~(\s*\(?\s*)(b[A-Z]\w*)\b")           # keil2sdcc.py rule (wb-vfreq 2d9835b)
    reg_cmp_hits = Counter()

    cast_members = set()
    for s in files:
        t = s.toks
        n = len(t)
        v, f = per[s.rel]
        for i, (tok, ln) in enumerate(t):
            nxt = t[i + 1][0] if i + 1 < n else ""
            prv = t[i - 1][0] if i else ";"
            unary = prv in ("(", ",", "=", "==", "!=", "&&", "||", "?", ":", "return", "<<", ">>", "&", "|", "^", "[", "<", ">",
                            "<=", ">=", "+", "-", "*", "/", "%", "{", ";", "|=", "&=", "^=", "!", "~")
            # ---- ~ on a bit / unsigned-char operand ----
            if tok == "~" and unary:
                j = i + 1
                core = nxt
                if nxt == "(":                                # ~(x) , ~((BYTE)x)
                    k = i + 2
                    while k < n and t[k][0] in ("(", "BYTE", "bit", ")", "unsigned", "char"):
                        k += 1
                    core = t[k][0] if k < n else ""
                    j = k
                op = ""
                if re.match(r"[A-Za-z_]\w*$", core or ""):
                    op = core
                if op:
                    c = cls_of(s, op)
                    snippet_ln = ln
                    text = s.snip(ln, 400)
                    hand = "yes" if HANDLED_NOT_BIT.search(text) and re.match(r"b[A-Z]", op) else "no"
                    if is_bitish(s, op):
                        add("NOT_BIT", s, ln, "HIGH", hand, "compiler flag", None)
                    elif c == "u8" and not re.match(r"_?BIT|_[A-Z0-9_]+$", op):
                        # Keil keeps ~uchar a byte in compare/boolean/bit-assign contexts; SDCC promotes to int
                        ctx = text
                        if re.search(r"(==|!=|<|>)\s*~\s*\(?\s*(\(BYTE\)\s*)?" + re.escape(op) +
                                     r"|~\s*\(?\s*(\(BYTE\)\s*)?" + re.escape(op) + r"\s*\)?\s*(==|!=|<|>)|"
                                     r"\bif\s*\(\s*~|(?<![&|^+\-*/%<>=!])=\s*~\s*" + re.escape(op) + r"\s*;", ctx) and not re.search(
                                     r"\)\s*~|&\s*~|~\s*\(\s*\w+\s*\)\s*[&|]", ctx):
                            add("NOT_UCHAR_CTX", s, ln, "MED", "no", "compiler flag", None)
            # ---- unsigned char == / != negative constant ----
            if tok in ("==", "!=") and i >= 1 and i + 2 < n:
                a, b = t[i - 1][0], nxt
                if re.match(r"[A-Za-z_]\w*$", a) and cls_of(s, a) == "u8" and b == "-" and re.match(r"\d", t[i + 2][0]):
                    add("UCHAR_CMP_NEG", s, ln, "HIGH", "no", "compiler flag", None)
            # ---- signed char vs unsigned char == / != ----
            if tok in ("==", "!=") and i >= 1 and i + 1 < n:
                a, b = t[i - 1][0], nxt
                if re.match(r"[A-Za-z_]\w*$", a or "") and re.match(r"[A-Za-z_]\w*$", b or ""):
                    ca, cb = cls_of(s, a), cls_of(s, b)
                    if {ca, cb} == {"s8", "u8"}:
                        add("CHAR_VS_UCHAR_CMP", s, ln, "MED", "no", "compiler flag", None)
            # ---- shifts of signed values (info) ----
            if tok == ">>" and i >= 1 and re.match(r"[A-Za-z_]\w*$", t[i - 1][0]) and cls_of(s, t[i - 1][0]) in ("s8", "s16", "s32"):
                add("SIGNED_SHR", s, ln, "LOW", "n/a (both arithmetic, tested)", "none", None)
            # ---- BYTE << >=8 without a wide cast (differs only if Realtek built with NOINTPROMOTE) ----
            if tok == "<<" and i >= 1 and i + 1 < n and re.match(r"\d+$", nxt) and int(nxt) >= 8 \
                    and re.match(r"[A-Za-z_]\w*$", t[i - 1][0]) and cls_of(s, t[i - 1][0]) == "u8":
                k = i - 1
                while k >= 2 and t[k - 1][0] in (".", "->"):
                    k -= 2
                cast = k >= 3 and t[k - 1][0] == ")" and t[k - 2][0] in ("WORD", "DWORD", "int", "long", "SDWORD", "SWORD")
                if not cast and not (t[i - 1][0] in cast_members):
                    add("UCHAR_SHL_WIDE", s, ln, "MED", "open (needs the C51FL option decode: INTPROMOTE default on)", "compiler flag", None)
            # ---- division / modulo with a variable divisor ----
            if tok in ("/", "%", "/=", "%=") and i >= 1 and i + 1 < n and prv not in ("(", ",") and t[i - 1][0] not in ("*",):
                j2 = i + 1
                rhs = t[j2][0]
                while rhs == "(" and j2 + 1 < n:
                    j2 += 1; rhs = t[j2][0]
                if rhs in ("BYTE", "WORD", "DWORD") and j2 + 2 < n and t[j2 + 1][0] == ")":
                    rhs = t[j2 + 2][0]
                isconst = bool(re.match(r"\d", rhs)) or (rhs.isupper() and "(" not in "".join(x[0] for x in t[j2:j2 + 2])) \
                    or rhs.startswith("_") or rhs in ("sizeof",)
                if not isconst and (re.match(r"[A-Za-z_]", rhs)):
                    c = cls_of(s, rhs)
                    big = c in ("u32", "s32", "u16", "s16", "u8", "s8", None)
                    risk = "MED" if c in ("u32", "s32", "u16", "s16", None) else "LOW"
                    add("DIV_VAR", s, ln, risk, "partly (crt_mod0/crt_divulong: x%0=x; 8-bit DIV AB inline as Keil)", "library (crt)", None)
            # ---- pragmas handled elsewhere ----
        # ---- line-based classes ----
        for ln, line in enumerate(s.clean.split("\n"), 1):
            st = line.strip()
            m = re.match(r"#\s*pragma\s+(\w+)", st)
            if m:
                p = m.group(1).lower()
                dropped = p in ("ot", "optimize", "noareas", "noaregs", "aregs", "regparms", "noregparms", "src", "asm", "endasm",
                                "large", "small", "compact", "rom", "code", "debug", "objectextend", "symbols", "nointvector",
                                "intvector")
                if p in ("save", "restore", "warning", "message"):
                    continue
                risk = "LOW" if dropped else "HIGH"
                add("PRAGMA", s, ln, risk, "yes (dropped)" if dropped else "no", "keil2sdcc" if dropped else "compiler flag", None)
            if re.search(r"\b(_crol_|_cror_|_irol_|_iror_|_lrol_|_lror_|_chkfloat_|_getkey|_testbit_|_push_|_pop_|_nop_)\b", line):
                nm = re.search(r"\b(_crol_|_cror_|_irol_|_iror_|_lrol_|_lror_|_chkfloat_|_getkey|_testbit_|_push_|_pop_|_nop_)\b", line).group(1)
                if "define" not in line:
                    ok = nm in ("_nop_", "_crol_", "_cror_", "_irol_", "_iror_", "_lrol_", "_lror_")
                    add("INTRINSIC", s, ln, "LOW" if ok else "HIGH", "yes (fw/sdcc/intrins.h)" if ok else "NO (unresolved)", "keil2sdcc", None)
            if re.search(r"\bbdata\b", line):
                add("BDATA", s, ln, "MED", "no (bdata -> __data in keil_compat.h: not bit-addressable)", "keil2sdcc", None)
            if re.match(r"\s*sbit\b", line):
                add("SBIT", s, ln, "LOW", "yes (rewrite SBIT)", "keil2sdcc", None)
            if re.search(r"\b(float|double)\b", line):
                add("FLOAT", s, ln, "LOW", "n/a (IEEE 32-bit both)", "none", None)
            if re.search(r"\b(printf|sprintf|vsprintf|scanf|sscanf)\s*\(", line):
                add("STDIO", s, ln, "MED", "no (Keil %bd/%bu char modifiers)", "keil2sdcc", None)
            if re.search(r"=\s*(memcpy|memset|strcpy|strcat|memmove)\s*\(", line) or re.search(r"\breturn\s+(memcpy|memset|strcpy)\s*\(", line):
                add("LIB_RETURN", s, ln, "LOW", "no", "library", None)
            if re.search(r"\bunion\b", line):
                add("UNION", s, ln, "MED", "yes if AWTO_SDCC_BE=1 (#15)", "compiler flag (--big-endian)", None)
            if re.search(r"\(\s*(WORD|DWORD|unsigned\s+int|unsigned\s+short)\s*\*\s*\)|\bPDATA_WORD\b|\bPDATA_DWORD\b|\bBYTEPTR\b|\bPDATA_\w*WORD\b", line):
                add("WORD_VIEW", s, ln, "MED", "yes if AWTO_SDCC_BE=1 (#15)", "compiler flag (--big-endian)", None)
            if re.search(r"\b(EnumX)\b", line):
                pass
            m = re.match(r"\s*(?:\w+\s+)*(?:BYTE|WORD|DWORD|unsigned\s+\w+|int|char)\s+(\w+)\s*:\s*(\d+)\s*[;,]", line)
            if m:
                w = int(m.group(2))
                add("BITFIELD", s, ln, "MED" if w > 8 else "LOW",
                    "n/a (Keil C51 LSB-first = SDCC, tested 2026-11-07)" if w <= 8 else "no (field wider than a byte under BE)",
                    "none" if w <= 8 else "compiler flag", None)
            if re.match(r"\s*(?:typedef\s+)?enum\b", line):
                add("ENUM", s, ln, "LOW", "n/a (same size rule, tested)", "none", None)
            if re.search(r"\binterrupt\b", line) and re.search(r"\)\s*interrupt\s+\w+", line):
                add("ISR_DEF", s, ln, "LOW", "yes (rewrite)", "keil2sdcc", None)
            if re.search(r"\bswitch\s*\(", line):
                add("SWITCH", s, ln, "LOW", "n/a (no semantic difference)", "none", None)
            if re.search(r"\(\s*\*\s*\w*\s*\)\s*\(|\(\s*\*\s*\w+\s*\)\s*\(", line) and "if" not in line.split("(")[0]:
                add("FUNC_PTR", s, ln, "LOW", "yes (rewrite, #20)", "keil2sdcc", None)
            if re.search(r"\bsizeof\s*\(\s*[^)]*\*", line):
                add("SIZEOF_PTR", s, ln, "LOW", "n/a (generic ptr 3 B both)", "none", None)

    # ---- bit assignment from integer (info) ----
    bit_assign = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.*);")
    for s in files:
        v, _ = per[s.rel]
        for ln, line in enumerate(s.clean.split("\n"), 1):
            m = bit_assign.match(line)
            if m and cls_of(s, m.group(1)) == "bit":
                rhs = m.group(2)
                if re.search(r"[&|>]|\w\s*\(", rhs) and not re.search(r"==|!=|<=|>=|&&|\|\||^\s*!|\(bit\)", rhs):
                    add("INT_TO_BIT", s, ln, "LOW", "n/a (both: nonzero -> 1, tested)", "none", None)

    # ---- evaluation order: >=2 calls joined by a binary operator in one statement (not arguments of one call) ----
    for s in files:
        if not s.in_build:
            continue
        prep = "\n".join(l if not l.lstrip().startswith("#") else "" for l in s.clean.split("\n"))
        for sm in re.finditer(r"[^;{}]*[;{}]", prep):
            stmt = sm.group(0)
            body = stmt.strip()
            if not body.endswith(";") or "(" not in body:
                continue
            depth, top = 0, []
            for ch in body:
                if ch == "(":
                    depth += 1
                    if depth == 1:
                        top.append("(")
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        top.append(")")
                elif depth == 0:
                    top.append(ch)
            flat = re.sub(r"\s+", " ", "".join(top))
            rhs = flat.split("=", 1)[-1] if re.match(r"^[\w\[\]\.\->* ]+(?:[-+*/%&|^]|<<|>>)?=[^=]", flat) else flat
            calls = re.findall(r"\b([A-Za-z_]\w*)\(\)", rhs)
            if len(calls) >= 2 and re.search(r"\)\s*(?:[-+*/%&|^]|<<|>>|==|!=|<=|>=|<|>|&&|\|\|)\s*(?:\([A-Za-z]+\)\s*)?[A-Za-z_]\w*\(\)", rhs) \
                    and not all(c.isupper() or c.startswith(("GET_", "_")) for c in calls):
                ln = prep.count("\n", 0, sm.start() + len(stmt) - len(stmt.lstrip())) + 1
                add("EVAL_ORDER", s, ln, "MED" if body.count("ScalerGet") >= 2 else "LOW", "no (Keil: rightmost call first for binary ops, observed 2026-11-07)", "compiler flag", re.sub(r"\s+", " ", body)[:110])

    # ---- ~ on bit operands inside macro bodies (the token pass skips # lines) ----
    for s in files:
        for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+(\w+)[^\n]*", s.raw, re.M):
            line = m.group(0)
            if "~" not in line:
                continue
            ln = s.raw.count("\n", 0, m.start()) + 1
            for mm in re.finditer(r"~\s*\(?\s*(?:\(\s*(?:BYTE|bit)\s*\)\s*)?([A-Za-z_]\w*)", line):
                nm = mm.group(1)
                if is_bitish(s, nm):
                    add("NOT_BIT", s, ln, "HIGH", "yes" if re.match(r"b[A-Z]", nm) else "no", "compiler flag", re.sub(r"\s+", " ", line)[:110])

    # ---- ISR-shared non-volatile globals + functions reachable from ISR and main ----
    call_re = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    log("call graph for ISR reachability")
    funcdef = re.compile(r"^(?:[A-Za-z_][\w \t\*]*?)\b([A-Za-z_]\w*)\s*\(([^;{}()]*)\)\s*(?:interrupt\s+\w+)?(?:\s+using\s+\d+)?\s*(?:\n\s*)?\{",
                         re.M)
    bodies, isr_roots = {}, set()
    for s in files:
        if not s.in_build:
            continue
        txt = s.clean
        for m in funcdef.finditer(txt):
            name = m.group(1)
            if name in ("if", "while", "for", "switch", "return", "sizeof"):
                continue
            st = m.end()
            d, k = 1, st
            while k < len(txt) and d:
                d += (txt[k] == "{") - (txt[k] == "}")
                k += 1
            bodies[name] = (s, txt[st:k], txt.count("\n", 0, m.start()) + 1)
            hdr = txt[m.start():st]
            if re.search(r"\binterrupt\b", hdr) or re.search(r"_(EXINT\d|WDINT|T2INT)$", name):
                isr_roots.add(name)
    calls_of = {n: set(call_re.findall(b)) & set(bodies) for n, (_s, b, _l) in bodies.items()}

    def reach(roots):
        seen, stack = set(), list(roots)
        while stack:
            x = stack.pop()
            if x in seen or x not in calls_of:
                continue
            seen.add(x); stack.extend(calls_of[x])
        return seen
    isr_reach = reach(isr_roots)
    main_reach = reach({"main"} | {n for n in bodies if n.endswith("Handler") and False})
    shared = sorted((isr_reach & main_reach) - isr_roots)
    log(f"functions: {len(bodies)} defined, {len(isr_roots)} ISR roots, {len(isr_reach)} ISR-reachable, "
        f"{len(main_reach)} main-reachable, {len(shared)} in both")
    for nme in shared:
        s, _b, ln = bodies[nme]
        add("FN_SHARED_ISR_MAIN", s, ln, "MED", "partly (stateful lib helpers cloned, #19; SDK fns: Keil overlay would also clash)",
            "none (design)", f"{nme}() reachable from ISR and main")
    # globals written in ISR-reachable fns, read in other fns, not volatile
    gdecl = {}
    for s in files:
        v, _ = per[s.rel]
        for m in re.finditer(r"^(?:extern\s+|static\s+)*(volatile\s+)?(bit|BYTE|WORD|DWORD|SBYTE|SWORD|unsigned\s+\w+)\s+(?:xdata\s+|data\s+|idata\s+|pdata\s+|bdata\s+)?([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;",
                             s.clean, re.M):
            if not m.group(1) and m.group(3).startswith("g_"):
                gdecl.setdefault(m.group(3), (s, s.clean.count("\n", 0, m.start()) + 1, m.group(2)))
    vol_rule = re.compile(r"g_b(?:NotifyTimer2Int|WDTimer2Update)\b")
    wr = re.compile(r"\b(g_\w+)\s*(?:\[[^\]]*\])?\s*(?:=(?!=)|\|=|&=|\^=|\+=|-=|\+\+|--)")
    macro_writes = {}
    for name, (par, body) in macros.items():
        w = wr.search(body)
        if w and not par is None:
            macro_writes[name] = w.group(1)
    written, readers = defaultdict(list), defaultdict(set)
    for nme, (s, b, ln) in bodies.items():
        for m in wr.finditer(b):
            if nme in isr_reach:
                written[m.group(1)].append((nme, s, ln + b[:m.start()].count("\n")))
        if nme in isr_reach:
            for mn, var in macro_writes.items():
                for m in re.finditer(r"\b" + re.escape(mn) + r"\s*\(", b):
                    written[var].append((nme, s, ln + b[:m.start()].count("\n")))
        for m in re.finditer(r"\bg_\w+\b", b):
            if nme not in isr_reach:
                readers[m.group(0)].add(nme)
    for var, ws in sorted(written.items()):
        if var in gdecl and readers.get(var):
            fn, s, ln = ws[0]
            ds, dl, dt = gdecl[var]
            handled = "yes (volatile rule)" if vol_rule.search(var) else "partly (--nogenconstprop only)"
            add("ISR_SHARED_NONVOLATILE", ds, dl, "HIGH" if dt == "bit" else "MED", handled, "compiler flag (--keil-compat treat as volatile) or keil2sdcc volatile rule",
                f"{dt} {var}: written in ISR-reachable {fn}() ({s.rel}:{ws[0][2]}), read by {len(readers[var])} non-ISR fn(s)")

    # ---- output ----
    OUT.parent.mkdir(parents=True, exist_ok=True)
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    ROWS.sort(key=lambda r: (r[0], order[r[3]], r[1]))
    with OUT.open("w") as fh:
        fh.write("class\tfile:line\tsnippet\trisk\thandled\tfix_where\n")
        for r in ROWS:
            if r[0] in QUIET or (r[0] == "BITFIELD" and r[3] == "LOW"):
                continue
            fh.write("\t".join(x.replace("\t", " ") for x in r) + "\n")
    summ = defaultdict(Counter)
    for r in ROWS:
        summ[r[0]][(r[3], r[4].startswith(("yes", "n/a")))] += 1
    log(f"wrote {OUT} ({len(ROWS)} rows)")
    log("class | total | HIGH | MED | LOW | unhandled(not yes/n-a)")
    for c in sorted(set(summ) | set(KNOWN)):
        tot = sum(summ[c].values())
        rk = Counter()
        unh = 0
        for (risk, h), k in summ[c].items():
            rk[risk] += k
            unh += 0 if h else k
        log(f"{c}\t{tot}\t{rk['HIGH']}\t{rk['MED']}\t{rk['LOW']}\t{unh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
