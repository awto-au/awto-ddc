#!/usr/bin/env python3
"""Compile / link harness for the SDCC build of fw/sdk (awto-ddc#162; was the compile half of keil2sdcc.py).

usage: fw_compile.py compile <uv2> [--target T] [--jobs N] [--only SUBSTR] [--asm]
                                             compile ONE target's C files from tmp/sdcc-port/src (msg_tokenise.py port),
                                             bucket errors, run the warning gate (fw/warn_policy.tsv)
       fw_compile.py awto [--jobs N]         clean-room tree + SDK boundary shim to asm (#68)
       fw_compile.py pp <uv2> --only S       preprocess one file with a target's flags
       fw_compile.py report                  print the last compile's error histogram

- <uv2> is src-relative, e.g. Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2 (fw/sdk/*.Uv2 = the file lists).
- Output: tmp/sdcc-port/{obj,asm,logs}, report.json. Log: tmp/logs/fw_compile.log
- Called by fw_build.py; edits to the SDK sources go in fw/sdk, never here.
"""
import fnmatch, hashlib, json, os, re, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_tools as T  # noqa: E402


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
WORK = ROOT / "tmp" / "sdcc-port"
SRC = WORK / "src"
SHIM = ROOT / "fw" / "sdcc"                    # keil_compat.h, intrins.h, awto_*.inc (committed)
SDCC = str(T.BIN / "sdcc")                     # awto-sdcc (scripts/sdcc_tools.py)
# Per-file backstop (sdcc prints nothing while working, so no stall guard). Worst measured: RL6449_Series_DPRx0.c
# 64 s under full parallel load (#8). 3x worst-case rule (awto-dan#53). Expiry -> logged TIMEOUT fail.
COMPILE_TIMEOUT = 200
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


def _resolve_clean():
    """Clean tree for the mixed build: $AWTO_RTDFW_REPO as is (live dir), else the commit in fw/awto/clean_ref.txt exported
    to tmp/clean-pin (HEAD of awto-rtdfw may be ahead of what links; the pin moves by an explicit edit of the file)."""
    env = os.environ.get("AWTO_RTDFW_REPO")
    if env:
        return Path(env)
    repo = Path("/mnt/2tb/git/awto-rtdfw")
    refp = ROOT / "fw" / "awto" / "clean_ref.txt"
    if not refp.exists() or not repo.is_dir():
        return repo
    ref = refp.read_text().split("#")[0].strip()
    dst = ROOT / "tmp" / "clean-pin"
    if not (dst / ".ref").exists() or (dst / ".ref").read_text() != ref:
        import shutil
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        tar = subprocess.run(["git", "-C", str(repo), "archive", ref, "awto", "facts"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dst)], input=tar, check=True)
        (dst / ".ref").write_text(ref)
    return dst


CLEAN = _resolve_clean()
# SDK name -> clean symbol macros and functions kept in common memory: fw/awto/boundary.py
sys.path.insert(0, str(ROOT / "fw" / "awto"))
from boundary import ALIASES, PIN_COMMON  # noqa: E402



# ---------------- uVision2 project ----------------
def parse_uv2(uv2: Path, target=None):
    """C files + C51DEF + INCC5 + memory model of ONE target. Multi-target projects: groups/files whose
    `Options T,G,F` block has IncBld=0 are excluded for target T (only that target is ever built)."""
    txt = uv2.read_bytes().decode("latin-1")
    blocks = {(int(m.group(1)), int(m.group(2)), int(m.group(3))): m.group(5)
              for m in re.finditer(r"^Options (\d+),(\d+),(\d+)\s*// (Target|Group|File)[^\n]*\n(.*?)^EndOpt",
                                   txt, re.M | re.S)}
    tnames = {int(m.group(1)): m.group(2) for m in re.finditer(r"^Options (\d+),0,0\s*// Target '([^']+)'", txt, re.M)}
    if target is None:
        if len(tnames) > 1:
            sys.exit(f"{uv2.name} has targets {sorted(tnames.values())}: pass --target")
        t = next(iter(tnames), 1)
    else:
        t = next((k for k, v in tnames.items() if v == target), None)
        if t is None:
            sys.exit(f"target {target!r} not in {sorted(tnames.values())}")
    tb = blocks.get((t, 0, 0), txt)

    def excluded(g, f):
        for key in ((t, g, 0), (t, g, f)):
            b = blocks.get(key)
            if b and re.search(r"^\s*IncBld=0", b, re.M):
                return True
        return False
    files, nth = [], Counter()
    for m in re.finditer(r"^File (\d+),(\d+),<([^>]+)>", txt, re.M):
        g = int(m.group(1)); nth[g] += 1
        if m.group(2) == "1" and not excluded(g, nth[g]):
            files.append(m.group(3).replace("\\", "/"))
    defs = re.search(r"C51DEF \((.*)\)", tb)
    incs = re.search(r"INCC5 \((.*)\)", tb)
    defines = [d.replace(" ", "") for d in defs.group(1).split(",")] if defs and defs.group(1) else []
    inc = [i.replace("\\", "/") for i in incs.group(1).split(";")] if incs and incs.group(1) else []
    model = re.search(r"MODEL5=(\d)", tb)
    return files, defines, inc, int(model.group(1)) if model else 2


def norm_err(line):
    """Strip location/identifiers so equal problems bucket together."""
    s = re.sub(r"^.*?:\d+:\s*", "", line)
    s = re.sub(r"'[^']*'", "'X'", s)
    s = re.sub(r"\b0x[0-9a-fA-F]+\b|\b\d+\b", "N", s)
    return s.strip()[:120]


# Per-file compiler workarounds (basename -> extra flags); each one names its awto-sdcc issue
FILE_FLAGS = {
    "ScalerCommonIOSC.c": ["--noinduction"],   # trunk r17139 ICE validateOpType @ SDCCopt.c (awto-sdcc#3)
    # GCSE temps of the WD-ISR handlers spill to DATA (sloc, 23 B); direct RAM is the binding limit (#8)
    "ScalerCommonTimerFunction.c": ["--nogcse"],
}


_KC = None


def keil_compat():
    """--keil-compat, refusing a compiler without it: sdcc only warns on an unknown option, and the ~bit rule is gone."""
    global _KC
    if _KC is None:
        r = subprocess.run([SDCC, "--help"], capture_output=True, text=True, timeout=30)
        if "--keil-compat" not in r.stdout + r.stderr:
            sys.exit(f"{SDCC} has no --keil-compat (awto-sdcc#25): Keil ~bit semantics would be lost")
        _KC = ["--keil-compat"]
    return _KC


def sdcc_cmd(c: Path, uv2dir: Path, defines, incs, model):
    cmd = [SDCC, "-mmcs51", {0: "--model-small", 1: "--model-medium", 2: "--model-large"}.get(model, "--model-large"),
           "--std-sdcc11", "--opt-code-size",                 # flash is the constraint (Dan: smallest)
           "--fsigned-char",                                  # Keil: plain char signed; SDK SBYTE = char (awto-sdcc#3)
           "--norestartseqatomics",                           # trunk: else every ISR exits via sdcc_atomic_maybe_rollback
           "--nooverlay",                                     # `data` locals -> DSEG for sdcc_overlay (call-graph aware), not OSEG
           "--noinvariant",                                   # hoisted loop invariants become DATA spill slots (#8)
           "--nogenconstprop",                                # SDK polls ISR-set non-volatile flags; trunk folded the delay loop away (#23)
           *keil_compat(),                                    # Keil ~bit (replaces the ~bX -> !bX rule, #26), /0, loop re-read, eval order (awto-sdcc#25)
           "-Wp-Wundef",                                      # undefined name in #if = 0: a build error unless allowed (undef_gate, #162)
           f"-Wp-include,{SHIM / 'keil_compat.h'}", f"-I{SHIM}"]
    if awto_alias_header():
        cmd.append(f"-Wp-include,{awto_alias_header()}")
    cmd += [f"-I{(uv2dir / i).resolve()}" for i in incs]
    cmd += [f"-I{c.parent}"]
    cmd += [f"-D{d}" for d in defines]
    cmd += FILE_FLAGS.get(c.name, [])
    cmd += [f"-D_AWTO_NEW_{m.upper()}" for m in awto_modules()]   # per-module WRAPS compile-out (#68)
    cmd += T.CFLAGS_EXTRA                                      # --big-endian when AWTO_SDCC_BE=1
    cmd += os.environ.get("K2S_SDCC_EXTRA", "").split()      # experiments, e.g. --max-allocs-per-node N
    return cmd


ASM_MODE = False                               # compile --asm: emit .asm (-S) for the XDATA overlay pass


def _run_stage(cmd, **kw):
    """One compiler stage; returns (stdout + stderr, rc). Stages never share a stderr pipe, so lines never interleave."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=COMPILE_TIMEOUT, **kw)
        return r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return f"TIMEOUT after {COMPILE_TIMEOUT}s", 124


def _cache_dir() -> Path | None:
    """Compile cache shared by every worktree (one-file change = one compile): $AWTO_SDCC_CACHE, else the main checkout's
    tmp/sdcc-cache (git common dir's parent); AWTO_SDCC_CACHE=off disables it."""
    env = os.environ.get("AWTO_SDCC_CACHE")
    if env == "off":
        return None
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    return Path(r.stdout.strip()).parent / "tmp/sdcc-cache" if r.returncode == 0 else ROOT / "tmp/sdcc-cache"


CACHE = _cache_dir()
_COMPILER_ID = None
STATS = Counter()                              # cache_hit / cache_miss per compile run


def _compiler_id() -> str:
    """Compiler identity in the cache key: size + mtime of every file in the install's bin and libexec dirs."""
    global _COMPILER_ID
    if _COMPILER_ID is None:
        inst = Path(SDCC).resolve().parent.parent
        parts = [f"{p.relative_to(inst)}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                 for d in ("bin", "libexec") for p in sorted((inst / d).rglob("*")) if p.is_file()]
        _COMPILER_ID = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return _COMPILER_ID


def _cache_key(pp: bytes, args: list) -> str:
    """Preprocessed source (worktree root replaced, so all worktrees share entries) + compiler flags (paths stripped) +
    compiler identity + output kind/name."""
    root = str(ROOT).encode()
    h = hashlib.sha256(pp.replace(root, b"@ROOT@"))
    h.update("\0".join(a.replace(str(ROOT), "@ROOT@") for a in args).encode())
    h.update(_compiler_id().encode())
    return h.hexdigest()


def compile_one(c: Path, uv2dir: Path, defines, incs, model):
    """Two stages: cpp (-E to a .i file), then the compiler proper on that file (--c1mode). In one `sdcc` run the cpp
    and the compiler write the same stderr concurrently and their lines interleave, splitting warning text (#51.7, #47).
    Message = cpp output, then compiler output. Stage 2 runs in the output dir with a bare -o: --c1mode names the
    .module from the -o path (bare = same name as a normal run)."""
    rel_dir = uv2dir.relative_to(SRC)
    out = WORK / ("asm" if ASM_MODE else "obj") / rel_dir / (c.stem + (".asm" if ASM_MODE else ".rel"))
    out.parent.mkdir(parents=True, exist_ok=True)
    pp = out.with_suffix(".i")
    base = sdcc_cmd(c, uv2dir, defines, incs, model)
    msg, rc = _run_stage(base + ["-E", "-o", str(pp), str(c)])
    if rc == 0:
        c1 = base + ["--c1mode"] + ([] if ASM_MODE else ["-c"]) + ["-o", out.name]
        key = _cache_key(pp.read_bytes(), c1) if CACHE else None
        hit = CACHE / f"{key}{out.suffix}" if key else None
        if hit and hit.exists() and hit.with_suffix(".msg").exists():
            root = str(ROOT).encode()
            out.write_bytes(hit.read_bytes().replace(b"@ROOT@", root))
            msg += hit.with_suffix(".msg").read_text(errors="replace").replace("@ROOT@", str(ROOT))
            STATS["cache_hit"] += 1
        else:
            with open(pp, "rb") as fh:
                m2, rc = _run_stage(c1, stdin=fh, cwd=out.parent)
            msg += m2
            if hit and rc == 0:                              # only successful compiles are cached (msg = c1 stage)
                CACHE.mkdir(parents=True, exist_ok=True)
                tmp = hit.with_name(hit.name + f".{os.getpid()}")
                tmp.write_bytes(out.read_bytes().replace(str(ROOT).encode(), b"@ROOT@"))
                hit.with_suffix(".msg").write_text(m2.replace(str(ROOT), "@ROOT@"))
                tmp.replace(hit)                             # entry visible only when complete (.msg first)
            STATS["cache_miss"] += 1
    pp.unlink(missing_ok=True)
    return str(c.relative_to(SRC)), rc, msg


# ---------------- clean-room mixed build (#65, #68) ----------------
SHIM_C = ROOT / "fw" / "awto" / "awto_shim" / "sdk_boundary.c"   # integrator-owned SDK<->clean bridge


def awto_sources():
    """{module: [.c]} of the clean tree: awto/<mod>/**/*.c (awto/include excluded). Empty = SDK-only build."""
    out = {}
    for p in sorted((CLEAN / "awto").glob("*/**/*.c")) + sorted((CLEAN / "awto").glob("*.c")):
        mod = p.relative_to(CLEAN / "awto").parts[0] if p.parent != CLEAN / "awto" else "core"
        if mod != "include":
            out.setdefault(mod, []).append(p)
    return out


def awto_alias_header():
    """SDK name -> clean symbol as a macro (thin boundary: callers reach the clean function directly, no wrapper hop).
    Only for modules present in the clean tree. Returns the header path or None."""
    mods = set(awto_modules())
    lines = [f"#define {a} {b}" for a, b, m in ALIASES if m in mods]
    if not lines:
        return None
    h = WORK / "awto_alias.h"
    h.parent.mkdir(parents=True, exist_ok=True)
    text = "/* generated by fw_compile.py from the ALIASES of fw/awto/boundary.py */\n" + "\n".join(lines) + "\n"
    if not h.exists() or h.read_text() != text:
        h.write_text(text)
    return h


def awto_modules():
    return sorted(awto_sources())


def cmd_awto(jobs):
    """Compile clean sources (only awto/include + facts visible, SDK flags) and the shim (SDK includes) to asm in
    tmp/sdcc-port/asm/awto_<mod>_<file>.asm, where fw_build's select_lib picks them up as project modules."""
    (WORK / "asm").mkdir(parents=True, exist_ok=True)
    for old in (WORK / "asm").glob("awto_*.asm"):
        old.unlink()
    srcs = awto_sources()
    (WORK / "pin_common.txt").write_text("")
    if not srcs:
        log("awto: no clean sources (SDK-only build)"); return 0
    uv2 = SRC / "STD_FW_1P.Uv2"
    _, defines, incs, model = parse_uv2(uv2, "RL6449_Project")
    jobs_l = []                                              # (src, out, cmd)
    for mod, cs in srcs.items():
        for c in cs:
            cmd = [x for x in sdcc_cmd(c, uv2.parent, [], [], model) if not x.startswith(("-Wp-include", "-I"))]   # no Keil shim
            cmd += [f"-I{CLEAN / 'awto' / 'include'}", f"-I{CLEAN / 'facts'}", f"-I{c.parent}"]
            cmd += ["-D__data=__xdata"]            # direct RAM is full on this board (#8): clean DATA working sets live in XDATA
            jobs_l.append((c, WORK / "asm" / f"awto_{mod}_{c.stem}.asm", cmd))
    if SHIM_C.exists():                                      # may name SDK symbols: full project flags
        cmd = sdcc_cmd(SHIM_C, uv2.parent, defines, incs, model) + [f"-I{CLEAN / 'awto' / 'include'}", f"-I{SHIM_C.parent}"] \
            + [f"-I{CLEAN / 'awto' / m}" for m in srcs]
        jobs_l.append((SHIM_C, WORK / "asm" / "awto_shim_sdk_boundary.asm", cmd))

    def one(j):
        c, out, cmd = j
        try:
            r = subprocess.run(cmd + ["-S", "-o", str(out), str(c)], capture_output=True, text=True, errors="replace",
                               timeout=COMPILE_TIMEOUT)
            return c, r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return c, 124, f"TIMEOUT after {COMPILE_TIMEOUT}s"
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(one, jobs_l))
    res, undef_bad = undef_gate(res)
    for u in undef_bad:
        log(f"UNDEF-GATE awto: {u}")
    res = [(c, rc or (1 if undef_bad else 0), msg) for c, rc, msg in res]
    for c, rc, msg in res:
        for l in msg.splitlines():
            log(f"awto {c.name}: {l}")
    # fw_build passes this to sdcc_bank --pin-common: names defined in the shim or in a clean module (#68: aliased hot leaves)
    sh = "\n".join(p.read_text(errors="replace") for p in sorted((WORK / "asm").glob("awto_*.asm")))
    (WORK / "pin_common.txt").write_text(",".join("_" + n for n in PIN_COMMON if re.search(rf"^_{n}:", sh, re.M)))
    bad = [c for c, rc, _ in res if rc]
    log(f"awto: modules {', '.join(awto_modules())}; {len(res) - len(bad)}/{len(res)} files ok")
    return 1 if bad else 0


def cmd_compile(uv2_rel, jobs, only, target):
    uv2 = SRC / uv2_rel
    files, defines, incs, model = parse_uv2(uv2, target)
    cs = [(uv2.parent / f).resolve() for f in files]
    if only:
        cs = [c for c in cs if only.lower() in str(c).lower()]
    missing = [c for c in cs if not c.exists()]
    cs = [c for c in cs if c.exists()]
    log(f"compile {uv2_rel}: {len(cs)} C files ({len(missing)} missing), defines {defines}, model {model}")
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda c: compile_one(c, uv2.parent, defines, incs, model), cs))
    res, undef_bad = undef_gate(res)
    ok = [r for r in res if r[1] == 0]
    bad = [r for r in res if r[1] != 0]
    hist, per_file = Counter(), {}
    for f, rc, msg in bad:
        errs = [l for l in msg.splitlines() if "error" in l.lower() or "TIMEOUT" in l]
        per_file[f] = errs[:20]
        for e in set(norm_err(l) for l in errs):
            hist[e] += 1
    (WORK / "logs").mkdir(parents=True, exist_ok=True)
    whist, wfile = Counter(), {}                             # warnings of every file, ok or not (#26)
    for f, _, msg in res:
        ws = [l for l in msg.splitlines() if "warning" in l.lower()]
        if ws:
            wfile[f] = ws
            for w in set(norm_err(l) for l in ws):
                whist[w] += 1
    wtxt = "".join(f"== {f}\n" + "\n".join(ws) + "\n" for f, ws in sorted(wfile.items()))
    (WORK / "warnings.txt").write_text(wtxt)
    (WORK / f"warnings-{Path(uv2_rel).stem}.txt").write_text(wtxt)    # per compile: scripts/warn_policy_check.py
    unreviewed = warn_gate(res)
    seg = Counter()                                          # area sizes summed over ok files
    for f, _, _ in ok:
        if ASM_MODE:                                         # XSEG split: globals vs fn locals/params
            asm = WORK / "asm" / uv2.parent.relative_to(SRC) / (Path(f).stem + ".asm")
            area, label = None, None
            for line in asm.read_text(errors="replace").splitlines():
                if line.startswith("\t.area"):
                    area = line.split()[1]
                elif area in ("XSEG", "DSEG", "OSEG", "ISEG") and re.match(r"^\w+::?$", line):
                    label = line
                elif area in ("XSEG", "DSEG", "OSEG", "ISEG") and line.strip().startswith(".ds") and label:
                    kind = ("global" if label.endswith("::") else
                            "sloc" if "sloc" in label else "local")
                    seg[f"{area}_{kind}"] += int(line.split()[1], 0)
            continue
        rel = WORK / "obj" / uv2.parent.relative_to(SRC) / (Path(f).stem + ".rel")
        for m in re.finditer(r"^A (\w+) size (\w+)", rel.read_text(errors="replace"), re.M):
            seg[m.group(1)] += int(m.group(2), 16)
    rep = {"uv2": uv2_rel, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ok": len(ok), "fail": len(bad),
           "missing": [str(m) for m in missing], "segments": dict(seg), "hist": hist.most_common(),
           "per_file": per_file, "warn_hist": whist.most_common(), "warn_files": len(wfile),
           "warn_unreviewed": unreviewed}
    log("segment bytes: " + ", ".join(f"{k}={v}" for k, v in seg.most_common() if v))
    (WORK / "report.json").write_text(json.dumps(rep, indent=1))
    log(f"compiled in {time.time() - t0:.0f}s: ok {len(ok)} fail {len(bad)}; cache {STATS['cache_hit']} hit / {STATS['cache_miss']} miss ({CACHE or 'off'})")
    print_hist(rep)
    for u in unreviewed:
        log(f"WARN-GATE unreviewed: {u}")
    if unreviewed:
        log(f"WARN-GATE: {len(unreviewed)} warning site(s) not in fw/warn_policy.tsv -> build fails (#26)")
    for u in undef_bad:
        log(f"UNDEF-GATE: {u}")
    if undef_bad:
        log(f"UNDEF-GATE: {len(undef_bad)} #if test(s) of an undefined name not in fw/pp_audit_allow.tsv -> build fails (#162)")
    return 0 if not bad and not unreviewed and not undef_bad else 1


UNDEF_RE = re.compile(r'^(.+?):(\d+):\d+: warning: "(\w+)" is not defined, evaluates to 0')


def undef_allow():
    """(file, name) pairs of fw/pp_audit_allow.tsv rows with check `undef` (file = fw/sdk/..., as pp_audit.py names it)."""
    f = ROOT / "fw" / "pp_audit_allow.tsv"
    rows = [ln.split("\t") for ln in f.read_text().splitlines() if ln.strip() and not ln.startswith("#")] if f.exists() else []
    return {(r[1], r[2]) for r in rows if len(r) >= 4 and r[0] == "undef" and r[3].strip()}


def undef_gate(res):
    """-Wundef hits leave the warning stream (and its 2 caret lines); a hit not allowed fails the build."""
    allow, bad, out = undef_allow(), set(), []
    for f, rc, msg in res:
        keep, skip = [], 0
        for l in msg.splitlines():
            if skip and re.match(r"^\s*\d*\s*\|", l):
                skip -= 1
                continue
            skip = 0
            m = UNDEF_RE.match(l)
            if m:
                skip = 2
                path = os.path.normpath(m.group(1))
                rel = "fw/sdk/" + os.path.relpath(path, SRC) if path.startswith(str(SRC) + os.sep) else os.path.relpath(path, ROOT)
                if (rel, m.group(3)) not in allow:
                    bad.add(f"{rel}:{m.group(2)}: {m.group(3)} is not defined (evaluates to 0)")
                continue
            keep.append(l)
        out.append((f, rc, "\n".join(keep)))
    return out, sorted(bad)


WARN_RE = re.compile(r"^(.+?):(\d+)(?::\d+)?: warning(?: (\d+))?: (.*)$")


def warn_gate(res):
    """Every compiler/cpp warning must match a fw/warn_policy.tsv rule; returns the unmatched ones.
    Rule columns: pattern (regex on text) | file glob (src-relative) | line (* or N) | verdict | reason."""
    rules = []
    for ln in (ROOT / "fw" / "warn_policy.tsv").read_text().splitlines():
        if ln.strip() and not ln.startswith("#"):
            pat, glob, line, verdict, _reason = (ln.split("\t") + [""] * 5)[:5]
            if verdict == "ok":
                rules.append((re.compile(pat), glob, line))
    out = set()
    for _f, _rc, msg in res:
        for l in msg.splitlines():
            m = WARN_RE.match(l)
            if not m:
                continue
            path, line, text = m.group(1), m.group(2), m.group(4)
            rel = os.path.relpath(path, SRC) if path.startswith(str(SRC)) else path
            if not any(p.search(text) and fnmatch.fnmatch(rel, g) and lr in ("*", line) for p, g, lr in rules):
                out.add(f"{rel}:{line}: {text}")
    return sorted(out)


def print_hist(rep, n=25):
    log(f"top errors (files affected) for {rep['uv2']}: ok {rep['ok']} fail {rep['fail']}")
    for e, k in rep["hist"][:n]:
        log(f"  {k:5d}  {e}")
    log(f"warnings (files affected) in {rep.get('warn_files', 0)} files; full list tmp/sdcc-port/warnings.txt")
    for e, k in rep.get("warn_hist", [])[:n]:
        log(f"  {k:5d}  {e}")



def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "fw_compile.log").open("a")
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    if a[0] == "compile":
        jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count()
        only = a[a.index("--only") + 1] if "--only" in a else None
        target = a[a.index("--target") + 1] if "--target" in a else None
        global ASM_MODE, COMPILE_TIMEOUT
        ASM_MODE = "--asm" in a
        if "--timeout" in a:                                 # for measuring a slow file once
            COMPILE_TIMEOUT = int(a[a.index("--timeout") + 1])
        return cmd_compile(a[1], jobs, only, target)
    if a[0] == "awto":
        return cmd_awto(int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count())
    if a[0] == "pp":                                         # preprocess one file with a target's flags
        target = a[a.index("--target") + 1] if "--target" in a else None
        uv2 = SRC / a[1]
        files, defines, incs, model = parse_uv2(uv2, target)
        c = next((uv2.parent / f).resolve() for f in files if a[a.index("--only") + 1].lower() in f.lower())
        out = WORK / "pp" / (c.stem + ".i")
        out.parent.mkdir(parents=True, exist_ok=True)
        extra = ["-Wp-dM"] if "--macros" in a else []           # --macros: dump #defines instead
        r = subprocess.run(sdcc_cmd(c, uv2.parent, defines, incs, model) + extra + ["-E", str(c)],
                           capture_output=True, text=True, errors="replace", timeout=COMPILE_TIMEOUT)
        out.write_text(r.stdout)
        log(f"pp {c.name} -> {out} ({len(r.stdout)} chars) {r.stderr[-300:]}"); return r.returncode
    if a[0] == "report":
        print_hist(json.loads((WORK / "report.json").read_text()), 60); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
