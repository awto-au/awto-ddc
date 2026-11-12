#!/usr/bin/env python3
"""DebugMessage tokenisation + the port step of the build: fw/sdk -> tmp/sdcc-port/src (awto-ddc#25 #26 #162).

usage: msg_tokenise.py port          every build (fw_build.py); regenerable, never hand-edit tmp/sdcc-port/src

- fw/sdk is our source in SDCC form. This step only turns each DebugMessage<Cat>("text", v) into AwtoMsg0(id) /
  AwtoMsgV(id, v) (fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/AwtoMsg.h), drops sites not in fw/msg_enable.txt,
  writes fw/msgids.tsv, and sets the build tag (`@FW_TAG@` in fw/sdk).
- Wire bytes {0x01, HH, LL, 0}, HH/LL in 1..255 so the NUL-terminated protocol never sees a 0. Text lives in fw/msgids.tsv.
- Log: tmp/logs/msg_tokenise.log
"""
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
FWSDK = ROOT / "fw" / "sdk"
SRC = ROOT / "tmp" / "sdcc-port" / "src"
SRC_EXT = {".c", ".h"}
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


def fw_tag(root) -> str:
    """No --dirty, fixed abbrev: rebuilding one commit gives identical bytes (#51.5); AWTO_FW_TAG overrides."""
    return os.environ.get("AWTO_FW_TAG") or subprocess.run(
        ["git", "describe", "--always", "--abbrev=7"], cwd=root, capture_output=True, text=True).stdout.strip() or "nogit"


MSG_TSV = ROOT / "fw" / "msgids.tsv"
MSG_ENABLE = ROOT / "fw" / "msg_enable.txt"
MSG_CATS = None                                # category -> Debug.h flag name, read from fw/sdk Debug.h
MSG_FLAG_ON = {}                               # flag name -> bool
MSG_RULES = []                                 # (kind, value) from msg_enable.txt
MSG_IDS = {}                                   # (category, text) -> id, filled by collect_messages
_STR = r'"(?:[^"\\\n]|\\.)*"'
MSG_CALL = re.compile(r"\bDebugMessage(\w+)\s*\(")
MSG_LIT = re.compile(rf"\s*((?:{_STR}\s*)+),")
COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"', re.S)
ESC = {"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11, "\\": 92, '"': 34, "'": 39, "?": 63}
# side effects: a call to a mixed-case function, ++/--, assignment (ALL-CAPS macros are the SDK's GET_*/PDATA_* reads)
SIDE_EFFECT = re.compile(r"\b\w*[a-z]\w*\s*\(|\+\+|--|(?<![=!<>])=(?!=)")


def c_unescape(lit: str) -> str:
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c != "\\":
            out.append(c); i += 1; continue
        m = re.match(r"\\(x[0-9A-Fa-f]+|[0-7]{1,3}|.)", lit[i:], re.S)
        e = m.group(1)
        out.append(chr((int(e[1:], 16) if e[0] == "x" else int(e, 8) if e[0] in "01234567" else ESC.get(e, ord(e))) & 0xFF))
        i += len(m.group(0))
    return "".join(out)


def mask_comments(text: str) -> str:
    """Blank out comments (same length, newlines kept) so offsets match the original; strings stay."""
    return COMMENT.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else re.sub(r"[^\n]", " ", m.group(0)), text)


def call_end(masked: str, i: int) -> int:
    """Index of the ')' closing the call whose '(' precedes i (strings and char literals skipped), or -1."""
    depth = 1
    while i < len(masked):
        c = masked[i]
        if c in "\"'":
            m = re.compile(rf"{c}(?:[^{c}\\\n]|\\.)*{c}").match(masked, i)
            i = m.end() if m else i + 1
            continue
        depth += (c == "(") - (c == ")")
        if depth == 0:
            return i
        i += 1
    return -1


def msg_sites(text: str, full=False):
    """Yield (start, end, category, text) per DebugMessage<Cat>(<literals>, ...) call; text[start:end] is the
    literal run. A call whose first argument is not purely string literals yields (None, None, category, head).
    full=True: literal calls only, yields (call_start, call_end, category, text, value_expr)."""
    masked = mask_comments(text)
    for m in MSG_CALL.finditer(masked):
        if m.group(1) not in MSG_CATS:
            continue
        ls = masked.rfind("\n", 0, m.start()) + 1
        if re.match(r"\s*#\s*define", masked[ls:m.start()]):
            continue
        lit = MSG_LIT.match(masked, m.end())
        if lit is None:
            if not full:
                yield None, None, m.group(1), masked[m.end():m.end() + 60].split("\n")[0]
            continue
        val = "".join(c_unescape(x[1:-1]) for x in re.findall(_STR, lit.group(1)))
        if full:
            e = call_end(masked, lit.end())
            if e >= 0:
                yield m.start(), e + 1, m.group(1), val, text[lit.end():e].strip()
        else:
            yield m.end(), lit.end() - 1, m.group(1), val


def assign_msg_ids(keys, pinned):
    """16-bit id per (category, text): the id already in fw/msgids.tsv stays (a message never changes id); a new one is the
    sha1 of category+text, each byte folded into 1..255, re-salted on a collision. Keys processed in sorted order."""
    import hashlib
    ids, used, collisions = {}, {}, 0
    for key in sorted(k for k in keys if k in pinned and pinned[k] not in used):
        ids[key] = pinned[key]; used[pinned[key]] = key
    for key in sorted(keys):
        if key in ids:
            continue
        for salt in range(1000):
            d = hashlib.sha1(f"{key[0]}\0{key[1]}\0{salt}".encode("latin-1")).digest()
            v = ((d[0] % 255 + 1) << 8) | (d[1] % 255 + 1)
            if v not in used:
                break
            collisions += 1
        else:
            sys.exit(f"msg id: no free id for {key!r}")
        used[v] = key; ids[key] = v
    return ids, collisions


def pinned_ids():
    """(category, text) -> id from the committed fw/msgids.tsv (before this run rewrites it)."""
    out = {}
    if MSG_TSV.exists():
        unesc = lambda s: s.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace("\\\\", "\\")
        for ln in MSG_TSV.read_text(encoding="utf-8", errors="replace").splitlines():
            f = ln.split("\t")
            if len(f) >= 4:
                out[(f[1], unesc(f[3]))] = int(f[0], 16)
    return out


def load_msg_rules():
    MSG_RULES.clear()
    for n, line in enumerate(MSG_ENABLE.read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, val = line.partition(":")
        if kind not in ("cat", "file", "id") or not val.strip():
            sys.exit(f"{MSG_ENABLE}:{n}: bad rule {line!r}")
        MSG_RULES.append((kind, int(val, 16) if kind == "id" else val.strip()))


def msg_enabled(cat: str, rel: str, mid: int) -> bool:
    """Category flag ON in Debug.h (else the SDK already dropped the call) and some allowlist rule matches (cat / file glob / id)."""
    import fnmatch
    if not MSG_FLAG_ON.get(MSG_CATS[cat], False):
        return False
    return any((k == "cat" and v == cat) or (k == "id" and v == mid) or (k == "file" and fnmatch.fnmatch(rel, v))
               for k, v in MSG_RULES)


def collect_messages(srcs):
    """Pre-pass over fw/sdk: assign ids, write fw/msgids.tsv. srcs = {src-relative path: file}."""
    global MSG_CATS
    dbg = (FWSDK / "Kernel/Common/Debug.h").read_text(errors="replace")
    MSG_CATS = {c: f for f, c in re.findall(
        r"#if\(\s*(\w+)\s*==\s*_ON\)\s*\n#define\s+DebugMessage(\w+)\(x,\s*y\)", dbg)}
    MSG_FLAG_ON.clear()
    MSG_FLAG_ON.update({f: v == "_ON" for f, v in re.findall(r"#define\s+(_DEBUG_MESSAGE_\w+)\s+(_ON|_OFF)\b", dbg)})
    load_msg_rules()
    sites, skipped, skip_sample = [], 0, []
    for rel, p in srcs.items():
        t = p.read_bytes().decode("latin-1").replace("\r\n", "\n")
        for a, b, cat, txt in msg_sites(t):
            if a is None:
                skipped += 1; skip_sample.append(f"{rel}: DebugMessage{cat}({txt}"); continue
            sites.append((cat, rel, t.count("\n", 0, a) + 1, txt))
    keys = {(c, x) for c, _, _, x in sites}
    MSG_IDS.clear()
    ids, coll = assign_msg_ids(keys, pinned_ids())
    MSG_IDS.update(ids)
    rows = sorted((ids[(c, x)], c, f"{r}:{ln}", x, int(msg_enabled(c, r, ids[(c, x)]))) for c, r, ln, x in sites)
    esc = lambda s: s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    MSG_TSV.write_text("".join(f"{i:04x}\t{c}\t{f}\t{esc(x)}\t{en}\n" for i, c, f, x, en in rows),
                       encoding="utf-8", errors="replace")
    log(f"msgids: {len(sites)} call sites, {len(keys)} unique ids, {coll} collisions re-salted, "
        f"{skipped} skipped (not a single literal), {sum(r[4] for r in rows)} enabled -> {MSG_TSV}")
    for s_ in skip_sample[:8]:
        log(f"  msg skipped: {s_}")
    return len(sites), skipped


def tokenise_messages(text: str, stats, rel: str) -> str:
    out, last = [], 0
    for a, b, cat, txt, val in msg_sites(text, full=True):
        mid = MSG_IDS[(cat, txt)]
        if msg_enabled(cat, rel, mid):
            zero = re.fullmatch(r"0[xX]?0*[uUlL]*", val) is not None
            new = f"AwtoMsg0(0x{mid:04X})" if zero else f"AwtoMsgV(0x{mid:04X}, {val})"
            stats["msg enabled"] += 1
        elif MSG_FLAG_ON.get(MSG_CATS[cat], False) and SIDE_EFFECT.search(val):
            new = f"(void)({val})"                           # may have side effects: keep it evaluated
            stats["msg dropped, value kept"] += 1
            log(f"  msg dropped, value expr kept: {rel}:{text.count(chr(10), 0, a) + 1} DebugMessage{cat}: {val}")
        else:
            new = "((void)0)"
            stats["msg dropped"] += 1
        out.append(text[last:a]); out.append(new); last = b
    out.append(text[last:])
    return "".join(out)



def cmd_port():
    """fw/sdk -> tmp/sdcc-port/src: tokenised .c/.h, other files as they are, build tag substituted."""
    if SRC.exists():
        shutil.rmtree(SRC)
    srcs = {str(p.relative_to(FWSDK)): p for p in sorted(FWSDK.rglob("*")) if p.is_file() and p.suffix.lower() in SRC_EXT}
    collect_messages(srcs)
    tag, stats = fw_tag(ROOT), Counter()
    for p in sorted(FWSDK.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(FWSDK))
        dst = SRC / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in SRC_EXT:
            t = tokenise_messages(p.read_bytes().decode("latin-1"), stats, rel).replace("@FW_TAG@", tag)
            dst.write_bytes(t.encode("latin-1"))
        else:
            shutil.copy2(p, dst)
    log(f"port: {len(srcs)} C/H files from {FWSDK} into {SRC}, tag {tag}")
    for k, v in stats.most_common():
        log(f"  {v:6d}  {k}")
    return 0


def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "msg_tokenise.log").open("a")
    if sys.argv[1:] == ["port"]:
        return cmd_port()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
