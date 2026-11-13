#!/usr/bin/env python3
"""Preprocessor audit of the BUILT sources: conditionals that silently pick the wrong branch (hidden SDK customer code, #162).

usage: pp_audit.py [--check] [--report FILE.md] [--jobs N]

- TUs = every C file fw_build compiles (STD_FW_1P.Uv2 target RL6449_Project, the Lib Uv2, the SDK boundary shim), with their
  build flags, from tmp/sdcc-port/src (msg_tokenise port: line-for-line copy of fw/sdk, so file:line is fw/sdk file:line).
  Run after the port step (fw_build runs it there). Each TU: sdcpp -E -Wundef -dD.
- Checks (file:line, name, and the branch compiled now):
  undef     #if / #elif names an undefined identifier (sdcpp -Wundef, incl. inside && / ||); "defined later" when the TU defines
            it after the test. Also a hard error in every build (fw_compile.py).
  nodef     #ifdef / #ifndef / defined(X) on a name never #defined anywhere (fw/sdk, fw/sdk-parked, fw/sdcc, generated headers, -D,
            compiler).
  value     #if / #elif uses a name whose definition is empty or not an integer expression (string, float, cast).
  family    A == / != B of two macros whose values come from different option families (prefix) and happen to be equal.
  redef     a macro gets two values in one TU (redefinition or #undef + #define) and an #if tests it under the earlier value.
- Branch: "taken" = code / #define / #include lines of that group reach the TU output, "skipped" = they do not,
  "no code" = the group has none (blank / comment / nested directives only).
- --check: exit 1 on any hit not in fw/pp_audit_allow.tsv (check, file, name, reason; a reviewed row per site); stale rows fail.
  `undef` rows are also the allow list of the build's own -Wundef error (fw_compile.py undef_gate).
Log: ./tmp/logs/pp_audit.log
"""
import bisect
import functools
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_compile as FC  # noqa: E402

ROOT, SRC = FC.ROOT, FC.SRC
SDK = ROOT / "fw/sdk"
ALLOW = ROOT / "fw/pp_audit_allow.tsv"
LIB_UV2 = "Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2"
UNDEF_RE = re.compile(r'^(.+?):(\d+):\d+: (?:warning|error): "(\w+)" is not defined, evaluates to 0')
MARK_RE = re.compile(r'^#(?:line)? (\d+) "((?:[^"\\]|\\.)*)"(?: \d)*$')
DIR_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif|define|undef|include)\b(.*)$")
ID_RE = re.compile(r"\b[A-Za-z_]\w*\b")
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n")
    LOG.flush()


def rel(p) -> str:
    """Source path as the repo names it: fw/sdk/... for the port copy, repo-relative otherwise."""
    p = os.path.normpath(str(p))
    if p.startswith(str(SRC) + os.sep):
        return "fw/sdk/" + os.path.relpath(p, SRC)
    if p.startswith(str(ROOT) + os.sep):
        return os.path.relpath(p, ROOT)
    return p


def tus():
    """(source, cmd) for every built C file, with the build's own flags."""
    out = []
    for uv2_rel, target in (("STD_FW_1P.Uv2", "RL6449_Project"), (LIB_UV2, None)):
        uv2 = SRC / uv2_rel
        files, defines, incs, model = FC.parse_uv2(uv2, target)
        for f in files:
            c = (uv2.parent / f).resolve()
            if c.exists():
                out.append((c, FC.sdcc_cmd(c, uv2.parent, defines, incs, model)))
    srcs = FC.awto_sources()                       # clean tree + shim: the flags of fw_compile.cmd_awto
    uv2 = SRC / "STD_FW_1P.Uv2"
    _, defines, incs, model = FC.parse_uv2(uv2, "RL6449_Project")
    inc = FC.CLEAN / "awto" / "include"
    for cs in srcs.values():
        for c in cs:
            cmd = [x for x in FC.sdcc_cmd(c, uv2.parent, [], [], model) if not x.startswith(("-Wp-include", "-I"))]
            out.append((c, cmd + [f"-I{inc}", f"-I{FC.CLEAN / 'facts'}", f"-I{c.parent}", "-D__data=__xdata"]))
    if srcs and FC.SHIM_C.exists():
        out.append((FC.SHIM_C, FC.sdcc_cmd(FC.SHIM_C, uv2.parent, defines, incs, model) + [f"-I{inc}", f"-I{FC.SHIM_C.parent}"]
                    + [f"-I{FC.CLEAN / 'awto' / m}" for m in srcs]))
    return out


def preprocess(job):
    c, cmd = job
    r = subprocess.run(cmd + ["-Wp-Wundef", "-Wp-dD", "-E", str(c)], capture_output=True, text=True, errors="replace",
                       timeout=FC.COMPILE_TIMEOUT)
    return c, r.returncode, r.stdout, r.stderr


def walk_output(text):
    """Live (file, line) set of one TU output, its #define / #undef stream, and the order index of each (file, line)."""
    live, defs, order = set(), [], {}
    f, ln, stack = None, 0, []
    for raw in text.splitlines():
        m = MARK_RE.match(raw)
        if m:                                           # sdcpp: `#line N "file"`, no enter / return flags
            newf, newln = os.path.normpath(m.group(2)), int(m.group(1))
            if newf != f:
                if newf in stack:                       # back in an includer: its #include line is live
                    del stack[stack.index(newf) + 1:]
                    live.add((newf, newln - 1))
                else:
                    stack.append(newf)
            f, ln = newf, newln
            continue
        if raw.strip() and f:
            live.add((f, ln))
            order.setdefault((f, ln), len(order))
            d = re.match(r"^#define (\w+)(\([^)]*\))?\s?(.*)$", raw)
            if d:
                defs.append(("define", d.group(1), d.group(3).strip(), bool(d.group(2)), f, ln))
            u = re.match(r"^#undef (\w+)", raw)
            if u:
                defs.append(("undef", u.group(1), "", False, f, ln))
        ln += 1
    return live, defs, order


def strip_comments(s, in_comment):
    """Line without /* */ and // comments (strings kept); in_comment carries an open /* to the next line."""
    out, i, q = [], 0, None
    while i < len(s):
        if in_comment:
            j = s.find("*/", i)
            if j < 0:
                return "".join(out), True
            i, in_comment = j + 2, False
            out.append(" ")
            continue
        ch = s[i]
        if q:
            out.append(ch)
            if ch == "\\" and i + 1 < len(s):
                out.append(s[i + 1]); i += 1
            elif ch == q:
                q = None
        elif ch in "\"'":
            q = ch; out.append(ch)
        elif s.startswith("//", i):
            break
        elif s.startswith("/*", i):
            in_comment, i = True, i + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out), in_comment


@functools.lru_cache(maxsize=None)
def file_lines(path):
    try:
        return Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return []


def scan_file(path):
    """Directives of one file (continuations joined): [(line, kind, text)] and the conditional groups:
    {directive line: (body first, body last, group index, chain lines)}."""
    lines = file_lines(path)
    dirs, i = [], 0
    in_comment = False
    while i < len(lines):
        start, s = i + 1, lines[i]
        while s.endswith("\\") and i + 1 < len(lines):
            i += 1
            s = s[:-1] + " " + lines[i]
        i += 1
        t, in_comment = strip_comments(s, in_comment)
        m = DIR_RE.match(t)
        if m:
            dirs.append((start, m.group(1), m.group(2).strip()))
    groups, stack = {}, []
    for ln, kind, _ in dirs:
        if kind in ("if", "ifdef", "ifndef"):
            stack.append([ln])
        elif kind in ("elif", "else") and stack:
            stack[-1].append(ln)
        elif kind == "endif" and stack:
            chain = stack.pop() + [ln]
            for k in range(len(chain) - 1):
                groups[chain[k]] = (chain[k] + 1, chain[k + 1] - 1, k, chain)
    return dirs, groups


def body_state(path, grp, live, dirlines):
    """taken / skipped / no code for the body lines grp = (first, last) of path."""
    first, last = grp[0], grp[1]
    lines = file_lines(path)
    has_code = False
    for ln in range(first, last + 1):
        if (path, ln) in live:
            return "taken"
        s = lines[ln - 1].strip() if ln - 1 < len(lines) else ""
        if s and not s.startswith(("//", "/*", "*")) and ln not in dirlines:
            has_code = True
        if s.startswith("#") and re.match(r"#\s*(define|undef|include)", s):
            has_code = True
    return "skipped" if has_code else "no code"


def branch(path, line, live, scans):
    """'if: taken, else: skipped' style description of the chain the directive at path:line belongs to."""
    dirs, groups = scans[path]
    g = groups.get(line)
    if not g:                                       # token on a continuation line: the directive that starts above it
        starts = [d[0] for d in dirs if d[1] in ("if", "elif") and d[0] <= line]
        g = groups.get(max(starts)) if starts else None
    if not g:
        return "?"
    dl = {d[0] for d in dirs}
    kinds = {d[0]: d[1] for d in dirs}
    parts = []
    for k in range(len(g[3]) - 1):
        a = g[3][k]
        st = body_state(path, groups[a], live, dl)
        parts.append(f"{kinds[a]}@{a}: {st}")
    return "; ".join(parts)


def int_value(name, table, depth=0):
    """Integer value of a macro from its last definition (simple expressions only); None when not an integer."""
    if depth > 12 or name not in table:
        return None
    v = table[name]
    if v is None:
        return None
    expr = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\b", lambda m: str(int(m.group(1), 0)), v)

    def sub(m):
        w = m.group(0)
        r = int_value(w, table, depth + 1)
        return "0" if r is None else str(r)
    expr = ID_RE.sub(sub, expr)
    expr = expr.replace("&&", " and ").replace("||", " or ").replace("!=", "<>").replace("!", " not ").replace("<>", "!=")
    if not re.fullmatch(r"[\d\s()+\-*/%<>=&|^~andortn!]*", expr) or not expr.strip():
        return None
    try:
        return int(eval(expr.replace("/", "//"), {"__builtins__": {}}))   # noqa: S307 (digits and operators only)
    except Exception:
        return None


def family(name):
    """Option family = name up to its second word: _PCB_X -> _PCB, _CUS_MINDRAY -> _CUS."""
    m = re.match(r"^(_*[A-Za-z0-9]+)", name)
    return m.group(1) if m else name


def value_ident(name, table, depth=0):
    """Last identifier in the value chain of name (_PANEL_TYPE -> _AU_LVDS_..): the option it is set to."""
    v = table.get(name)
    if depth > 12 or v is None:
        return name
    v = v.strip().strip("()").strip()
    if re.fullmatch(r"[A-Za-z_]\w*", v):
        return value_ident(v, table, depth + 1)
    return name


def main() -> int:
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/pp_audit.log").open("a")
    a = sys.argv[1:]
    check = "--check" in a
    report = Path(a[a.index("--report") + 1]) if "--report" in a else None
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count()
    if not (SRC / "STD_FW_1P.Uv2").exists():
        log("no tmp/sdcc-port/src: run the build's port step first (msg_tokenise.py port)")
        return 2
    t0 = time.time()
    js = tus()
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(preprocess, js))
    bad = [r for r in res if r[1]]
    for c, rc, _, err in bad:
        log(f"preprocess failed rc={rc}: {rel(c)}: {err.strip()[-400:]}")
    # per TU
    live_all, files_all = set(), set()
    tu_info = []
    for c, rc, out, err in res:
        live, defs, order = walk_output(out)
        live = {(os.path.normpath(f), ln) for f, ln in live if f}
        live_all |= live
        files = {f for f in {f for f, _ in live} if os.path.isabs(f) and Path(f).exists()}
        files_all |= files
        tu_info.append((c, err, live, defs, order))
    ours = [f for f in files_all if f.startswith((str(SRC), str(ROOT / "fw"), str(FC.CLEAN)))]
    scans = {f: scan_file(f) for f in ours}
    # every #define in our trees + the -D flags + compiler predefines
    defined = set()
    import fw_dirs
    for base in (SDK, ROOT / "fw/sdk-parked", ROOT / "fw/sdcc", SRC, ROOT / "fw/awto", *fw_dirs.our_dirs(ROOT)):   # parked sources count (#165)
        for p in base.rglob("*"):
            if p.suffix.lower() in (".c", ".h", ".inc") and p.is_file():
                defined |= set(re.findall(r"^\s*#\s*define\s+(\w+)", p.read_text(errors="replace"), re.M))
    cmdline = set()
    for _, cmd in js:
        cmdline |= {x[2:].split("=")[0] for x in cmd if x.startswith("-D")}
    defined |= cmdline
    pre = subprocess.run(js[0][1] + ["-Wp-dM", "-E", "-"], input="", capture_output=True, text=True)
    defined |= set(re.findall(r"^#define (\w+)", pre.stdout, re.M))
    for (_, defs) in [(0, d) for *_, d, _o in tu_info]:
        defined |= {d[1] for d in defs if d[0] == "define"}

    hits = []                                       # (check, file, line, name, branch, note)

    # (a) undef
    seen = set()
    for c, err, live, defs, order in tu_info:
        later = {d[1] for d in defs if d[0] == "define"}
        for l in err.splitlines():
            m = UNDEF_RE.match(l)
            if not m:
                continue
            f, ln, name = os.path.normpath(m.group(1)), int(m.group(2)), m.group(3)
            key = (f, ln, name)
            if key in seen:
                continue
            seen.add(key)
            note = "defined later in the TU" if name in later else ("defined elsewhere" if name in defined else "never defined")
            hits.append(("undef", f, ln, name, branch(f, ln, live_all, scans) if f in scans else "?", note))

    # textual checks over the directives of every included file of ours
    last_val = {}                                   # name -> last value seen in any TU (None = function-like)
    for *_, defs, _o in tu_info:
        for kind, name, val, fn, _f, _l in defs:
            if kind == "define":
                last_val[name] = None if fn else val
    multi = defaultdict(dict)                       # TU-local value sequences: name -> {tu: [(value, file, line, order)]}
    for c, err, live, defs, order in tu_info:
        seq = defaultdict(list)
        for kind, name, val, fn, f, ln in defs:
            seq[name].append((val if kind == "define" else "<undef>", os.path.normpath(f), ln,
                              order.get((f, ln), -1)))
        for name, s in seq.items():
            vals = [v for v, *_ in s if v != "<undef>"]
            if len(set(vals)) > 1:
                multi[name][c] = (s, order)

    _bf = {}

    def by_file(c, order):
        """file -> (sorted lines, their order indices) of one TU, built once."""
        if c not in _bf:
            m = defaultdict(list)
            for (ff, l2), o in order.items():
                m[ff].append((l2, o))
            _bf[c] = {ff: ([a for a, _ in sorted(v)], [b for _, b in sorted(v)]) for ff, v in m.items()}
        return _bf[c]

    def idents(expr):
        e = re.sub(r"\bdefined\s*\(?\s*\w+\s*\)?", " ", expr)
        e = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\b", " ", e)
        return ID_RE.findall(e)

    for f in sorted(scans):
        dirs, groups = scans[f]
        for ln, kind, text in dirs:
            if kind in ("ifdef", "ifndef") or (kind in ("if", "elif") and "defined" in text):
                names = [text.split()[0]] if kind in ("ifdef", "ifndef") and text.split() else \
                    re.findall(r"\bdefined\s*\(?\s*(\w+)", text)
                for n in names:
                    if n not in defined:
                        hits.append(("nodef", f, ln, n, branch(f, ln, live_all, scans), f"#{kind} {text}"))
            if kind not in ("if", "elif"):
                continue
            for n in set(idents(text)):
                v = last_val.get(n, "<absent>")
                if v == "<absent>":
                    continue
                if v is None:
                    hits.append(("value", f, ln, n, branch(f, ln, live_all, scans), "function-like macro in #if"))
                elif v == "" or re.search(r'"|\'|\d\.\d|\(\s*(BYTE|WORD|DWORD|bit|char|int|long|unsigned)\b', v):
                    hits.append(("value", f, ln, n, branch(f, ln, live_all, scans), f"defined as {v!r}"))
            for m in re.finditer(r"\(?\s*([A-Za-z_]\w*)\s*\)?\s*(==|!=)\s*\(?\s*([A-Za-z_]\w*)\b", text):
                lhs, op, rhs = m.group(1), m.group(2), m.group(3)
                if lhs not in last_val or rhs not in last_val:
                    continue
                vi, vr = value_ident(lhs, last_val), value_ident(rhs, last_val)
                if vi == vr or family(vi) == family(vr) or vi == lhs:
                    continue
                lv, rv = int_value(lhs, last_val), int_value(rhs, last_val)
                if lv is not None and lv == rv:
                    hits.append(("family", f, ln, f"{lhs} {op} {rhs}", branch(f, ln, live_all, scans),
                                 f"{lhs} = {vi} ({lv}), {rhs} = {rv}: different families, same value"))
            for n in set(idents(text)) & set(multi):
                for c, (s, order) in multi[n].items():
                    # order index of this directive = first live line of f after it
                    idx = by_file(c, order).get(f)
                    if not idx:
                        continue
                    k = bisect.bisect_right(idx[0], ln)
                    if k >= len(idx[0]):
                        continue
                    pos = min(idx[1][k:])
                    defs_before = [v for v, _f, _l, o in s if 0 <= o < pos]
                    defs_after = [v for v, _f, _l, o in s if o >= pos]
                    if defs_before and defs_after and set(defs_after) - {"<undef>"} and \
                            defs_before[-1] not in defs_after:
                        hits.append(("redef", f, ln, n, branch(f, ln, live_all, scans),
                                     f"tested as {defs_before[-1]!r}, later {defs_after[-1]!r} ({rel(c)})"))
                        break
    # dedup
    uniq = {}
    for h in hits:
        uniq.setdefault((h[0], h[1], h[2], h[3]), h)
    hits = sorted(uniq.values(), key=lambda h: (h[0], rel(h[1]), h[2]))
    allow = set()
    if ALLOW.exists():
        for row in ALLOW.read_text().splitlines():
            if row.strip() and not row.startswith("#"):
                p = row.split("\t")
                if len(p) >= 4 and p[3].strip():
                    allow.add((p[0], p[1], p[2]))
    new, used = [], set()
    for h in hits:
        k = (h[0], rel(h[1]), h[3])
        if k in allow:
            used.add(k)
        else:
            new.append(h)
    stale = sorted(k for k in allow - used if not (k[0] == "nodef" and k[2] in cmdline))     # opt-in -D build: its nodef rows idle
    by = defaultdict(int)
    for h in hits:
        by[h[0]] += 1
    log(f"{len(js)} TUs, {len(ours)} source files of ours, {len(defined)} names defined; "
        f"hits: {dict(by)}; not allowed: {len(new)}; stale allow rows: {len(stale)} ({time.time() - t0:.0f} s)")
    for h in hits:
        tag = "NEW " if h in new else "ok  "
        log(f"{tag}{h[0]:6s} {rel(h[1])}:{h[2]}: {h[3]} [{h[4]}] {h[5]}")
    for s in stale:
        log(f"STALE allow row: {s[0]}\t{s[1]}\t{s[2]}")
    if report:
        with report.open("w") as fh:
            fh.write("| check | site | name | branch compiled now | note |\n|---|---|---|---|---|\n")
            for h in hits:
                fh.write(f"| {h[0]} | `{rel(h[1])}:{h[2]}` | `{h[3]}` | {h[4]} | {h[5]} |\n")
        log(f"report {report}")
    if bad:
        return 1
    return 1 if check and (new or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
