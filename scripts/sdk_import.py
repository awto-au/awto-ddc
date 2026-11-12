#!/usr/bin/env python3
"""One-off mechanical Keil C51 -> SDCC port of the Realtek SDK mirror into fw/sdk/ (awto-ddc#162).

usage: sdk_import.py [--out tmp/DIR] [--manifest FILE]    run by hand; the build never calls it

- fw/sdk/ is OUR source (SDCC form, committed). This script reproduces the import commit, or ports a new SDK drop so it
  can be compared with fw/sdk: `sdk_import.py --out tmp/sdk-new`, then diff against fw/sdk. It refuses any --out
  outside tmp/ or a non-empty one, so it can never overwrite fw/sdk (our edited source).
- Mechanical only: Keil keywords (code/data/xdata/sfr/sbit/interrupt/using/_at_), pragmas, pData scratch to xdata,
  storage-first pointer declarations, ISR-flag `volatile bit`, include case fixing, __at on externs, interrupt prototypes.
  No behaviour change; no DebugMessage tokenisation (scripts/msg_tokenise.py does that on every build).
- Files = fw/sdk_files.txt (what the RL6449 build compiles or includes). Mirror = $RTD_SDK or the default below.
- Log: tmp/logs/sdk_import.log
"""
import argparse
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent, capture_output=True, text=True).stdout.strip())
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
SRC_EXT = {".c", ".h"}
DROP_USING = True            # IRAM is the binding limit (#8): ISR register banks 1-3 dropped
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"', re.S)
RULES = [
    (re.compile(r"\bdata(\s+pData(?:_EXINT)?\s*\[)"), r"xdata\1"),
    # Storage-first pointer decls: Keil `code BYTE *t[]` places t in code; SDCC reads it as pointer-to-code
    (re.compile(r"^(\s*(?:extern\s+|static\s+)*)(code|xdata|idata|data|pdata)\s+([A-Za-z_][\w ]*?)\s*(\*+)\s*"
                r"([A-Za-z_]\w*)(?=\s*[\[=;,])", re.M),
     lambda m: (f"{m.group(1)}{m.group(3)} {m.group(4)} {m.group(2)} {m.group(5)}"
                if re.search(r"\b(code|xdata|idata|data|pdata)\b", m.group(3)) else
                f"{m.group(1)}{m.group(3)} {m.group(2)} {m.group(4)} {m.group(2)} {m.group(5)}")),
    (re.compile(r"^(\s*(?:extern\s+|static\s+)*)(code|xdata|idata|data|pdata)\s+([A-Za-z_][\w ]*?)\s*\(\s*\*\s*"
                r"([A-Za-z_]\w*)", re.M), r"\1\3 (* \2 \4"),
    # ISR-written flags polled in main code: non-volatile -> SDCC folds the re-check (warning 110/126, #26)
    (re.compile(r"\bbit(\s+g_b(?:NotifyTimer2Int|WDTimer2Update)\b)"), r"volatile bit\1"),
    (re.compile(r"\bcode(?=\s+[\*A-Za-z_])"), "__code"),
    (re.compile(r"\bdata(?=\s+[\*A-Za-z_])"), "__data"),
    (re.compile(r"\bsfr\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr __at(\2) \1;"),
    (re.compile(r"\bsfr16\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr16 __at(\2) \1;"),
    (re.compile(r"\)\s*interrupt\s+(\w+)\s+using\s+(\w+)"),
     r") __interrupt(\1)" if DROP_USING else r") __interrupt(\1) __using(\2)"),
    (re.compile(r"\)\s*interrupt\s+(\w+)(?=\s*[{;\n])"), r") __interrupt(\1)"),
    (re.compile(r"\)\s*using\s+(\d)(?=\s*[{;\n])"), r")" if DROP_USING else r") __using(\1)"),
    (re.compile(r"^(\s*)([^;\n]*?)\b(\w+(?:\s*\[[^\]\n]*\])?)\s+_at_\s+([^;]+);", re.M), r"\1__at(\4) \2\3;"),
    (re.compile(r"^\s*#\s*pragma\s+(OT|OPTIMIZE|NOAREGS|AREGS|REGPARMS|NOREGPARMS|SRC|ASM|ENDASM|"
                r"LARGE|SMALL|COMPACT|ROM|CODE|DEBUG|OBJECTEXTEND|SYMBOLS|NOINTVECTOR|INTVECTOR)\b.*$",
                re.M | re.I), r"// dropped pragma (Keil only)"),
]
SBIT = re.compile(r"\bsbit\s+(\w+)\s*=\s*([\w]+)\s*\^\s*(\d)\s*;")
INCLUDE = re.compile(r'^(\s*#\s*include\s*[<"])([^>"]+)([>"])', re.M)
USING_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*using\s+(\d)\s*\n?\s*\{")
INT_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*interrupt\s+(\w+)(?:\s+using\s+(\d))?\s*\n?\s*\{")
AT_DEF = re.compile(r"\b(\w+)(?:\s*\[[^\]\n]*\])?\s+_at_\s+([^;]+);")
AT_ADDR = {}


def build_name_index():
    """lower-case basename -> list of SDK-relative paths (Windows includes are case-insensitive)."""
    idx = {}
    for p in SDK.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            idx.setdefault(p.name.lower(), []).append(p.relative_to(SDK))
    return idx


def ci_resolve(base: Path, rel: str):
    """Resolve `rel` under `base` matching each path component case-insensitively (Windows semantics)."""
    p = base
    for part in rel.split("/"):
        if part in (".", ""):
            continue
        if part == "..":
            p = p.parent
            continue
        if (p / part).exists():
            p = p / part
            continue
        hit = next((c for c in p.iterdir() if c.name.lower() == part.lower()), None) if p.is_dir() else None
        if hit is None:
            return None
        p = hit
    return p


def fix_includes(text, here: Path, idx):
    def sub(m):
        inc = m.group(2).replace("\\", "/")
        cand = (here / inc)
        if cand.exists():
            return m.group(1) + inc + m.group(3)
        hit = ci_resolve(here, inc)
        if hit is not None:
            fixed = os.path.relpath(hit, here).replace(os.sep, "/")
            return m.group(1) + fixed + m.group(3)
        hits = idx.get(Path(inc).name.lower())
        if hits and len(hits) == 1:
            fixed = str(Path(inc).parent / hits[0].name) if "/" in inc else hits[0].name
            return m.group(1) + fixed + m.group(3)
        return m.group(1) + inc + m.group(3)
    return INCLUDE.sub(sub, text)


def add_using_to_protos(text, using, stats):
    """SDCC needs the prototype's __interrupt/__using to match the definition (Keil does not)."""
    def sub(m):
        attrs = using.get(m.group(2))
        if attrs is None or "__using" in m.group(0) or "__interrupt" in m.group(0) \
                or re.search(r"\breturn\b", m.group(1)):
            return m.group(0)
        stats["proto attrs added"] += 1
        return f"{m.group(1)}{m.group(2)}({m.group(3)}){attrs};"
    return re.sub(r"^(\s*(?:extern\s+)?(?:\w+\s+)+\**\s*)(\w+)\s*\(([^;{()]*)\)\s*;", sub, text, flags=re.M)


def add_at_to_externs(text, stats):
    """SDCC needs `extern` decls to carry the definition's __at(addr) (Keil does not)."""
    def sub(m):
        addr = AT_ADDR.get(m.group(2))
        if addr is None or "__at" in m.group(0):
            return m.group(0)
        stats["extern __at added"] += 1
        return f"__at({addr}) {m.group(0)}"
    return re.sub(r"\bextern\b[^;\n(]*?\b(?:\w+\s+)+\**\s*()(\w+)\s*(?:\[[^\]\n]*\])?\s*;", sub, text)


def rewrite(text, here, idx, sfr_addr, using, stats):
    text = text.replace("\r\n", "\n")
    text, n = re.subn(r"\\[ \t]+\n", "\\\n", text)           # cpp splices `\ <spaces>\n` anyway (warns): drop the spaces
    stats["backslash-space"] += n
    # "/*" inside a block comment (cpp warns): "/ *" keeps the text, no warning
    text = COMMENT.sub(lambda m: "/*" + m.group(0)[2:-2].replace("/*", "/ *") + "*/"
                       if m.group(0).startswith("/*") else m.group(0), text)
    text = fix_includes(text, here, idx)
    text = add_using_to_protos(text, using, stats)
    text = add_at_to_externs(text, stats)
    for rx, rep in RULES:
        text, n = rx.subn(rep, text)
        if n:
            stats[rx.pattern[:40]] += n

    def sbit(m):
        name, reg, bitn = m.group(1), m.group(2), int(m.group(3))
        base = int(reg, 0) if re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", reg) else sfr_addr.get(reg)
        if base is None:
            stats["sbit unresolved"] += 1
            return m.group(0)
        stats["sbit"] += 1
        return f"__sbit __at(0x{base + bitn:02X}) {name};"
    return SBIT.sub(sbit, text)


def scan_mirror():
    """Pass 1 over the whole mirror: name index, sfr addresses, interrupt attributes, _at_ addresses (fills AT_ADDR)."""
    idx = build_name_index()
    sfr_addr, using_all, at_all = {}, {}, {}
    for p in SDK.rglob("*"):                                  # pass 1: sfr addresses, interrupt defs, _at_ defs (whole SDK)
        if not p.is_file() or ".git" in p.parts or p.suffix.lower() not in SRC_EXT:
            continue
        t = p.read_text(errors="replace")
        for m in re.finditer(r"\bsfr\s+(\w+)\s*=\s*(0[xX][0-9A-Fa-f]+|\d+)\s*;", t):
            sfr_addr[m.group(1)] = int(m.group(2), 0)
        for m in AT_DEF.finditer(t):
            at_all.setdefault(m.group(1), set()).add(m.group(2).strip())
        for m in INT_DEF.finditer(t):
            using_all.setdefault(m.group(1), set()).add(
                f" __interrupt({m.group(2)})" + (f" __using({m.group(3)})" if m.group(3) and not DROP_USING else ""))
    using = {k: next(iter(v)) for k, v in using_all.items() if len(v) == 1}
    AT_ADDR.update({k: next(iter(v)) for k, v in at_all.items()
                    if len(v) == 1 and re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", next(iter(v)))})
    return idx, sfr_addr, using


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "tmp" / "sdk-import",
                    help="new, empty directory under tmp/ (never fw/: fw/sdk is our edited source)")
    ap.add_argument("--manifest", type=Path, default=ROOT / "fw" / "sdk_files.txt")
    a = ap.parse_args()
    out = a.out.resolve()
    # fw/sdk is OUR source now (Dan 2026-11-12): an import may only land in an empty scratch dir under tmp/, then be diffed
    if not out.is_relative_to((ROOT / "tmp").resolve()):
        raise SystemExit(f"sdk_import: --out {out} is outside {ROOT / 'tmp'}; refusing (it would overwrite our code)")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"sdk_import: --out {out} is not empty; refusing (pick a new directory)")
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "sdk_import.log").open("a")
    want = [l.strip() for l in a.manifest.read_text().splitlines() if l.strip() and not l.startswith("#")]
    idx, sfr_addr, using = scan_mirror()
    stats, n, miss = Counter(), 0, []
    for rel in want:
        p = SDK / rel
        if not p.is_file():
            miss.append(rel); continue                        # our own file (no SDK original)
        dst = a.out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes().decode("latin-1")                # byte-preserving; comments are GBK/Big5
        if p.suffix.lower() in SRC_EXT:
            raw = rewrite(raw, p.parent, idx, sfr_addr, using, stats)
        else:
            raw = raw.replace("\r\n", "\n")
        dst.write_bytes(raw.encode("latin-1"))
        n += 1
    log(f"import: {n} files into {a.out}; {len(miss)} manifest entries without a mirror original")
    for k, v in stats.most_common():
        log(f"  rule {v:6d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
