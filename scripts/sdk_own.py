#!/usr/bin/env python3
"""One-off migration (awto-ddc#162): turn the keil2sdcc.py behaviour rules + fw/overlay into plain edits of fw/sdk.

usage: sdk_own.py overlay                merge fw/overlay/** into fw/sdk (mechanical rewrite of each overlay file)
       sdk_own.py global                 the global behaviour regexes (audio test, DP version, popup time, T3, host wait, ...)
       sdk_own.py files SUBSTR...        every INSERT / SUB / WRAP of the SDK files whose path contains a SUBSTR
       sdk_own.py check [SUBSTR...]      compare fw/sdk (tokenised, includes expanded, comments dropped) with the baseline port

- Rules come from tag wb-p14ui-ownbase (git archive -> tmp/own-base): the last tree whose build patched the SDK.
- Baseline = tmp/base-src (tmp/sdcc-port/src of that tag's build). Code must match it line for line, comments aside.
- Big inserted blocks (fw/sdcc/*.inc, settings glue) become `#include "x.inc"` lines; the build tag is `@FW_TAG@`.
- Each edit carries `// awto: <what> (#issue)` instead of `[keil2sdcc]`.
Log: tmp/logs/sdk_own.log
"""
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent, capture_output=True, text=True).stdout.strip())
TAG = "wb-p14ui-ownbase"
BASE = ROOT / "tmp" / "own-base"
BASE_SRC = ROOT / "tmp" / "base-src"
FWSDK = ROOT / "fw" / "sdk"
INCDIR = ROOT / "fw" / "sdcc"
LOG = None
sys.path.insert(0, str(Path(__file__).resolve().parent))


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


def load_old():
    if not (BASE / "scripts" / "keil2sdcc.py").exists():
        BASE.mkdir(parents=True, exist_ok=True)
        tar = subprocess.run(["git", "-C", str(ROOT), "archive", TAG, "scripts", "fw"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(BASE)], input=tar, check=True)
    os.environ["AWTO_DDC_REPO"] = str(BASE)
    os.environ["AWTO_FW_TAG"] = "@FW_TAG@"
    os.environ.setdefault("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw-ui")
    sys.path.insert(0, str(BASE / "scripts"))
    import keil2sdcc as old
    old.LOG = open(ROOT / 'tmp' / 'logs' / 'sdk_own_old.log', 'a')
    return old


# ---- inc blocks -> #include lines ----
def inc_blocks():
    """name -> text as the old rules inserted it (longest first so the composite glue wins over its parts)."""
    out = {}
    for p in sorted(INCDIR.glob("*.inc")):
        out[p.name] = p.read_text().rstrip("\n")
    sd = BASE / "fw" / "awto" / "settings"
    gl = (sd / "glue.inc").read_text().rstrip("\n").replace('#include "glue_nv.inc"', (sd / "glue_nv.inc").read_text().rstrip("\n"))
    out["glue.inc"] = gl
    out["glue_key.inc"] = (sd / "glue_key.inc").read_text().rstrip("\n")
    out["glue_nv.inc"] = (sd / "glue_nv.inc").read_text().rstrip("\n")
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


INC = None


def replace_inc(text):
    for name, content in INC.items():
        if content and content in text:
            text = text.replace(content, f'#include "{name}"')
    return text


def expand_inc(text):
    return re.sub(r'^#include "(\w+\.inc)"[^\n]*$', lambda m: INC.get(m.group(1), m.group(0)), text, flags=re.M)


# ---- marker -> `// awto: ...` ----
DESC = [   # (regex on the code part of the line, description, default issue)
]
MISSING = Counter()
MARK = re.compile(r"[ \t]*//\s*\[keil2sdcc\]\s*(insert|sub|wrap|dropped pragma)?\s*(.*)$")


def describe(code, kind, tail):
    iss = re.findall(r"#(\d+)", tail)
    tail_txt = re.sub(r"#\d+", "", tail).strip(" :;,.")
    for rx, d, i in DESC:
        if re.search(rx, code):
            return d, (iss[0] if iss else i)
    if tail_txt:
        return tail_txt, (iss[0] if iss else None)
    MISSING[f"{kind}: {code.strip()[:110]}"] += 1
    return f"{kind} {code.strip()[:50]}", (iss[0] if iss else None)


def convert_markers(text):
    out = []
    for ln in text.split("\n"):
        m = MARK.search(ln)
        if m:
            code = ln[:m.start()]
            d, iss = describe(code, m.group(1) or "edit", m.group(2))
            ln = f"{code}  // awto: {d}" + (f" (#{iss})" if iss else "")
        out.append(ln)
    return "\n".join(out)


# ---- rules ----
def msg_anchor(rx, ids):
    m = re.search(r"AwtoMsgV\\\((0x[0-9A-Fa-f]{4}),", rx)
    if not m:
        return rx
    txt = ids[int(m.group(1), 16)]
    return rx.replace(m.group(0), r"DebugMessage\w+\(\s*\"" + re.escape(txt) + r"\"")


def msg_texts():
    d = {}
    for ln in (ROOT / "fw" / "msgids.tsv").read_text(encoding="utf-8").splitlines():
        f = ln.split("\t")
        d[int(f[0], 16)] = f[3]
    return d


def prep_rules(old):
    ids = msg_texts()
    old.INSERTS[:] = [(r[0], msg_anchor(r[1], ids), replace_inc(r[2])) + tuple(r[3:]) for r in old.INSERTS]
    new = []
    for f, rx, fn, want in old.SUBS:
        rx = msg_anchor(rx, ids)
        if callable(fn):
            fn = (lambda m, fn=fn: replace_inc(fn(m)))
        new.append((f, rx, fn, want))
    old.SUBS[:] = new


GLOBAL = ("_INTERNAL_AUDIO_TEST_SUPPORT", "b1OsdDpD1PortVersion", "_FRC_SUPPORT == _ON", "SEC\\(3\\)", "_PANEL_POWER_ON_T3", "g_bFwHalt")


def global_rules(old):
    return [(rx, rep) for rx, rep in old.RULES if any(g in rx.pattern for g in GLOBAL)]


def rd(p):
    return p.read_bytes().decode("latin-1")


def wr(p, t):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(t.encode("latin-1"))


def rule_files(old):
    fs = set()
    for r in old.WRAPS + old.INSERTS + old.SUBS:
        fs.add(r[0])
    return sorted(fs)


# ---- check ----
def strip(t):
    return [re.sub(r"//.*$", "", l).rstrip() for l in t.split("\n")]


def new_port(old, rel):
    return expand_inc(old.tokenise_messages(rd(FWSDK / rel), Counter(), rel))


def check(old, rels):
    bad = []
    for rel in rels:
        b = rd(BASE_SRC / rel)
        n = new_port(old, rel)
        n = re.sub(r'(#define AWTO_FW_TAG )"[^"]*"', r'\1"T"', n)
        b = re.sub(r'(#define AWTO_FW_TAG )"[^"]*"', r'\1"T"', b)
        sb, sn = strip(b), strip(n)
        if [l.strip() for l in sb if l.strip()] != [l.strip() for l in sn if l.strip()]:
            import difflib
            d = [l for l in difflib.unified_diff(sb, sn, "base", "new", lineterm="", n=0)][:14]
            bad.append(rel)
            log(f"CHECK DIFF {rel}\n    " + "\n    ".join(d))
        elif len(sb) != len(sn):
            log(f"check {rel}: same code, line count {len(sb)} vs {len(sn)} (blank-line shift)")
    log(f"check: {len(rels) - len(bad)}/{len(rels)} files identical to the baseline port")
    return bad


def setup_old():
    global INC
    old = load_old()
    INC = inc_blocks()
    files = [p for p in old.SDK.rglob("*") if p.is_file() and ".git" not in p.parts]
    ov = [p for p in old.OVERLAY.rglob("*") if p.is_file()]
    old.collect_messages(files, ov)                       # message ids exactly as the baseline build assigned them
    prep_rules(old)
    return old


def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "sdk_own.log").open("a")
    cmd, args = sys.argv[1], sys.argv[2:]
    import sdk_import as imp
    old = setup_old()
    if cmd == "overlay":
        idx, sfr, using = imp.scan_mirror()
        for p in sorted((BASE / "fw" / "overlay").rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(BASE / "fw" / "overlay")
            raw = p.read_bytes().decode("latin-1")
            t = imp.rewrite(raw, (imp.SDK / rel).parent, idx, sfr, using, Counter()) if p.suffix in imp.SRC_EXT else raw
            wr(FWSDK / rel, t)
            log(f"overlay: {rel}")
        return 0
    if cmd == "global":
        n = Counter()
        for p in sorted(FWSDK.rglob("*")):
            if p.suffix not in imp.SRC_EXT or not p.is_file():
                continue
            t = rd(p); t0 = t
            for rx, rep in global_rules(old):
                t, k = rx.subn(rep, t)
                n[(rx.pattern[:36], str(p.relative_to(FWSDK)))] += k
            if t != t0:
                wr(p, t)
        for (rx, f), k in sorted(n.items()):
            if k:
                log(f"global {k}x {rx} in {f}")
        return 0
    if cmd == "files":
        done = []
        for rel in rule_files(old):
            if not any(a in rel for a in args):
                continue
            p = FWSDK / rel
            if not p.exists():
                sys.exit(f"{rel}: not in fw/sdk")
            stats = Counter()
            t = rd(p)
            t = old.apply_wraps(rel, t, stats)
            t = old.apply_inserts(rel, t, stats)
            t = old.apply_subs(rel, t, stats)
            t = convert_markers(t)
            wr(p, t)
            done.append(rel)
            log(f"edited {rel}: {dict(stats)}")
        for k, v in MISSING.items():
            log(f"NO DESCRIPTION {v}x {k}")
        if done:
            check(old, done)
        return 0
    if cmd == "check":
        rels = [str(p.relative_to(FWSDK)) for p in sorted(FWSDK.rglob("*"))
                if p.is_file() and p.suffix in imp.SRC_EXT and (not args or any(a in str(p) for a in args))]
        rels = [r for r in rels if (BASE_SRC / r).exists()]
        return 1 if check(old, rels) else 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
