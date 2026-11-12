#!/usr/bin/env python3
"""Clean-room leak gate: does the clean tree share identifiers, code n-grams or comment prose with the vendor SDK? (#65)

usage: cleanroom_lint.py [--tree /mnt/2tb/git/awto-rtdfw] [--rebuild] [--where] [--structural]
  Index (cached, tmp/cleanroom/sdk_index.npz; rebuilt when the SDK HEAD, tainted file set or this script changes):
    - identifiers: every distinctive identifier in SDK code (len >= 4, not all-lowercase, not a C/SDCC keyword)
    - code n-grams: 6 consecutive code tokens (comments dropped, numbers by value) with >= 2 content tokens (identifiers of 2+ chars, numbers > 1)
    - prose n-grams: 8 consecutive words of comments + string literals with >= 5 words of 3+ letters
    Sources: the SDK mirror ($RTD_SDK) + awto-ddc fw/sdk and fw/sdcc (tainted: edited SDK copies / SDK names).
    Hashes only (64-bit): the index holds no SDK text.
  Scan: *.c *.h *.asm *.s *.inc *.md *.py *.txt in --tree. Exempt: facts/, awto_shim/, .git/; identifiers #defined in facts/.
  Allowlist: specs/lint_allow.tsv (kind<TAB>value<TAB>reason; kind ident | code | prose, value = identifier or hit hash).
  --where: for each hit print the first SDK file holding it (spec side only: prints SDK paths).
  --structural: also report (never fail) 20-token runs equal after renaming identifiers/numbers: review input.
  Exit 0 clean, 1 hits. Report: tmp/logs/cleanroom_lint.txt; log tmp/logs/cleanroom_lint.log.
"""
from __future__ import annotations

import argparse, hashlib, os, re, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
TAINTED = [ROOT / "fw" / "sdk", ROOT / "fw" / "sdcc"]
CLEAN = Path(os.environ.get("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw"))
CACHE = ROOT / "tmp" / "cleanroom" / "sdk_index.npz"
ALLOW = ROOT / "specs" / "lint_allow.tsv"
SRC_EXT = {".c", ".h", ".asm", ".s", ".a51", ".inc"}
SCAN_EXT = SRC_EXT | {".md", ".py", ".txt", ".tsv"}
EXEMPT_DIRS = {"facts", "awto_shim", ".git", "tmp", "build"}   # tmp/build: compiler output (generated asm matches SDK asm idioms)
N_CODE, MIN_CONTENT = 6, 2
N_PROSE, MIN_WORDS = 8, 5
N_STRUCT = 20
MUL = np.uint64(0x9E3779B97F4A7C15)
LOG = None

KEYWORDS = set("""
auto break case char const continue default do double else enum extern float for goto if inline int long register
restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Bool _Static_assert
define include ifdef ifndef endif elif undef pragma defined line error
__xdata __code __data __idata __pdata __near __far __bit __sbit __sfr __sfr16 __at __interrupt __using __reentrant
__critical __naked __banked __nonbanked __asm __endasm __sdcc_external_startup
uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t int64_t size_t NULL true false bool stdint stdbool string
memcpy memset memcmp strlen
""".split())
TOKEN = re.compile(r"""
  (?P<ws>\s+)
| (?P<lc>//[^\n]*)
| (?P<bc>/\*.*?(?:\*/|\Z))
| (?P<str>"(?:[^"\\\n]|\\.)*"?)
| (?P<chr>'(?:[^'\\\n]|\\.)*'?)
| (?P<num>0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|[0-9A-Fa-f]+[hH]\b)
| (?P<id>[A-Za-z_$]\w*)
| (?P<op>->|\+\+|--|<<=?|>>=?|[<>!=]=|&&|\|\||[-+*/%&|^]=|\S)
""", re.S | re.X)
ASM_COMMENT = re.compile(r";[^\n]*")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_H = {}


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, file=sys.stderr)
    if LOG:
        LOG.write(line + "\n"); LOG.flush()


def th(tok: str) -> int:
    v = _H.get(tok)
    if v is None:
        v = _H[tok] = int.from_bytes(hashlib.blake2b(tok.encode("latin-1", "replace"), digest_size=8).digest(), "little")
    return v


def distinctive(ident: str) -> bool:
    return len(ident) >= 4 and not ident.islower() and ident not in KEYWORDS and not ident.startswith("__sdcc")


def num_value(t: str) -> int | None:
    s = t.rstrip("uUlL")
    try:
        return int(s[:-1], 16) if s[-1:] in "hH" else int(s, 0)
    except ValueError:
        try:
            return int(s.lstrip("0") or "0")
        except ValueError:
            return None


def lex(text: str, asm: bool):
    """-> code tokens [(norm, line, kind)], prose words [(word, line)]. kind: id | num | op."""
    prose, code = [], []
    if asm:
        for m in ASM_COMMENT.finditer(text):
            ln = text.count("\n", 0, m.start()) + 1
            prose += [(w.lower(), ln) for w in WORD.findall(m.group(0))]
        text = ASM_COMMENT.sub(lambda m: " " * len(m.group(0)), text)
    line = 1
    for m in TOKEN.finditer(text):
        g, s = m.lastgroup, m.group(0)
        if g in ("lc", "bc", "str", "chr"):
            prose += [(w.lower(), line) for w in WORD.findall(s)]
            if g in ("str", "chr"):
                code.append(("STR", line, "op"))
        elif g == "num":
            v = num_value(s)
            code.append((f"#{v:x}" if v is not None else s, line, "num" if v is not None and v > 1 else "op"))
        elif g == "id":
            code.append((s, line, "id" if len(s) > 1 and s not in KEYWORDS else "op"))
        elif g == "op":
            code.append((s, line, "op"))
        line += s.count("\n")
    return code, prose


def windows(h: np.ndarray, n: int) -> np.ndarray:
    if len(h) < n:
        return np.zeros(0, dtype=np.uint64)
    acc = np.zeros(len(h) - n + 1, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for j in range(n):
            acc = acc * MUL + h[j:len(h) - n + 1 + j]
    return acc


def grams(code, prose, structural=False):
    """-> (ident hashes, code n-gram hashes, prose n-gram hashes, struct hashes) + per-window start lines."""
    ids = [th(t) for t, _, k in code if k == "id" and distinctive(t)]
    ch = np.array([th(t) for t, _, _ in code], dtype=np.uint64)
    content = np.array([k != "op" for _, _, k in code], dtype=np.int32)
    cg = windows(ch, N_CODE)
    if len(cg):
        cs = np.convolve(content, np.ones(N_CODE, dtype=np.int32), "valid")
        idn = np.convolve(np.array([k == "id" for _, _, k in code], dtype=np.int32), np.ones(N_CODE, dtype=np.int32), "valid")
        keep = (cs >= MIN_CONTENT) & (idn >= 1)                      # literals + punctuation only carry no expression
        cg, cl = cg[keep], np.nonzero(keep)[0]                       # window start = token index
    else:
        cl = np.zeros(0, dtype=np.int64)
    ph = np.array([th(w) for w, _ in prose], dtype=np.uint64)
    pg = windows(ph, N_PROSE)
    if len(pg):
        long_ = np.array([len(w) >= 3 for w, _ in prose], dtype=np.int32)
        keep = np.convolve(long_, np.ones(N_PROSE, dtype=np.int32), "valid") >= MIN_WORDS
        pg, pl = pg[keep], np.array([prose[i][1] for i in np.nonzero(keep)[0]], dtype=np.int64)
    else:
        pl = np.zeros(0, dtype=np.int64)
    sg, sl = np.zeros(0, dtype=np.uint64), np.zeros(0, dtype=np.int64)
    if structural:
        sh = np.array([th({"id": "ID", "num": "NUM"}.get(k, t)) for t, _, k in code], dtype=np.uint64)
        sg = windows(sh, N_STRUCT)
        if len(sg):
            idn = np.array([k == "id" for _, _, k in code], dtype=np.int32)
            keep = np.convolve(idn, np.ones(N_STRUCT, dtype=np.int32), "valid") >= 6
            sg, sl = sg[keep], np.array([code[i][1] for i in np.nonzero(keep)[0]], dtype=np.int64)
    return np.array(ids, dtype=np.uint64), (cg, cl), (pg, pl), (sg, sl)


def read(p: Path) -> str:
    return p.read_bytes().decode("latin-1").replace("\r\n", "\n")


def index_file(p: str):
    path = Path(p)
    code, prose = lex(read(path), path.suffix.lower() in {".asm", ".s", ".a51", ".inc"})
    ids, (cg, _), (pg, _), (sg, _) = grams(code, prose, structural=True)
    return np.unique(ids), np.unique(cg), np.unique(pg), np.unique(sg)


def sources() -> list[Path]:
    out = []
    for base in [SDK] + TAINTED:
        if base.exists():
            out += sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in SRC_EXT and ".git" not in p.parts)
    return out


def stamp(files) -> str:
    try:
        head = subprocess.check_output(["git", "-C", str(SDK), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head = "nogit"
    h = hashlib.sha256(Path(__file__).read_bytes())
    for f in files:
        if SDK not in f.parents:                            # tainted files change; hash their content
            h.update(str(f).encode()); h.update(f.read_bytes())
    return f"{head}:{len(files)}:{h.hexdigest()[:16]}"


def build_index(force: bool) -> dict:
    files = sources()
    if not any(SDK in f.parents for f in files):
        sys.exit(f"SDK not found at {SDK} (set RTD_SDK); refusing to lint against an empty index")
    st = stamp(files)
    if CACHE.exists() and not force:
        z = np.load(CACHE)
        if str(z["stamp"]) == st:
            return {k: z[k] for k in ("ids", "code", "prose", "struct")}
    t0 = time.time()
    with ProcessPoolExecutor(min(8, os.cpu_count() or 1)) as ex:
        parts = list(ex.map(index_file, map(str, files), chunksize=16))
    idx = {k: np.unique(np.concatenate([p[i] for p in parts])) for i, k in enumerate(("ids", "code", "prose", "struct"))}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, stamp=np.array(st), **idx)
    log(f"index: {len(files)} files, {len(idx['ids'])} identifiers, {len(idx['code'])} code / {len(idx['prose'])} prose / "
        f"{len(idx['struct'])} struct n-grams, {time.time() - t0:.0f} s -> {CACHE}")
    return idx


def load_allow() -> dict:
    allow = {"ident": set(), "code": set(), "prose": set()}
    if ALLOW.exists():
        for line in ALLOW.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                kind, val = (line.split("\t") + [""])[:2]
                if kind in allow:
                    allow[kind].add(val.strip())
    return allow


def facts_names(tree: Path) -> set:
    names = set()
    for p in (tree / "facts").rglob("*.h") if (tree / "facts").exists() else []:
        names |= set(re.findall(r"^#define\s+(\w+)", p.read_text(errors="replace"), re.M))
    return names


def scan_files(tree: Path) -> list[Path]:
    return sorted(p for p in tree.rglob("*") if p.is_file() and p.suffix.lower() in SCAN_EXT
                  and not EXEMPT_DIRS & set(p.relative_to(tree).parts))


def where(kind: str, h: int) -> str:
    """First SDK/tainted file holding hash h (slow: re-lexes the sources)."""
    for f in sources():
        ids, cg, pg, _ = index_file(str(f))
        arr = {"ident": ids, "code": cg, "prose": pg}[kind]
        if np.isin(np.uint64(h), arr):
            return str(f)
    return "?"


def lint(tree: Path, idx: dict, show_where: bool, structural: bool) -> list[str]:
    allow, exempt = load_allow(), facts_names(tree)
    hits, notes = [], []
    for p in scan_files(tree):
        rel = p.relative_to(tree)
        asm = p.suffix.lower() in {".asm", ".s", ".a51", ".inc"}
        if p.suffix.lower() in {".md", ".txt", ".tsv"}:
            text = read(p)                                  # prose doc: all words are prose, `code` spans are identifiers
            code = [(m.group(0), text.count("\n", 0, m.start()) + 1, "id") for m in re.finditer(r"[A-Za-z_]\w*", text)
                    if re.search(r"_|[a-z][A-Z]", m.group(0))]          # prose: only code-shaped words count
            prose = [(m.group(0).lower(), text.count("\n", 0, m.start()) + 1) for m in WORD.finditer(text)]
            code_for_ngrams = []
        else:
            code, prose = lex(read(p), asm)
            code_for_ngrams = code
        seen = set()
        for t, ln, k in code:
            if k == "id" and distinctive(t) and t not in exempt and t not in allow["ident"] and t not in seen:
                if np.isin(np.uint64(th(t)), idx["ids"]):
                    seen.add(t)
                    hits.append(f"{rel}:{ln}: ident {t}" + (f"  [sdk: {where('ident', th(t))}]" if show_where else ""))
        _, (cg, cl), (pg, pl), (sg, sl) = grams(code_for_ngrams, prose, structural)
        toks = [t for t, _, _ in code_for_ngrams]
        lines = [ln for _, ln, _ in code_for_ngrams]
        done = set()
        for kind, g, gl in (("code", cg, cl), ("prose", pg, pl)):
            m = np.isin(g, idx[kind])
            for h, pos in zip(g[m], gl[m]):
                ln = lines[pos] if kind == "code" else int(pos)
                if f"{int(h):016x}" in allow[kind] or (kind, ln) in done:
                    continue                                   # one hit per line and kind; allowlisted hashes skipped
                done.add((kind, ln))
                snip = " ".join(toks[pos:pos + N_CODE]) if kind == "code" else ""
                hits.append(f"{rel}:{ln}: {kind} {int(h):016x} {snip}".rstrip()
                            + (f"  [sdk: {where(kind, int(h))}]" if show_where else ""))
        if structural and len(sg):
            m = np.isin(sg, idx["struct"])
            for ln in sorted(set(sl[m].tolist())):
                notes.append(f"{rel}:{ln}: structural (review, not a failure)")
    return hits + notes


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=CLEAN)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--where", action="store_true")
    ap.add_argument("--structural", action="store_true")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/cleanroom_lint.log").open("a")
    idx = build_index(a.rebuild)
    out = lint(a.tree, idx, a.where, a.structural)
    hits = [o for o in out if "structural" not in o]
    rep = ROOT / "tmp/logs/cleanroom_lint.txt"
    rep.write_text("\n".join(out) + ("\n" if out else ""))
    for o in out[:200]:
        print(o)
    log(f"lint {a.tree}: {len(scan_files(a.tree))} files, {len(hits)} hit(s), {len(out) - len(hits)} structural note(s) -> {rep}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
