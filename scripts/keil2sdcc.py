#!/usr/bin/env python3
"""Port the Realtek RL64xx Keil C51 SDK to SDCC: mechanical source rewrite + per-file compile harness.

usage: keil2sdcc.py port                     SDK -> tmp/sdcc-port/src (rewritten; regenerable)
       keil2sdcc.py compile <uv2> [--target T] [--jobs N] [--only SUBSTR]
                                             compile ONE target's C files (multi-target projects need
                                             --target, e.g. RL6449_Project), bucket errors
       keil2sdcc.py report                   print the last compile's error histogram

- Source of truth = SDK mirror (read-only) + the rules here + fw/sdcc/*.h. Never hand-edit tmp/sdcc-port/src:
  fix a rule or the compat header and re-run `port` (the tree is a derived artifact).
- <uv2> is SDK-relative, e.g. Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2
- Output: tmp/sdcc-port/{src,obj,logs}, tmp/sdcc-port/report.json. Log: tmp/logs/keil2sdcc.log
- Repo is private (Realtek code), see CLAUDE.md. Tracking: awto-ddc#8.
"""
import json, os, re, shutil, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
WORK = ROOT / "tmp" / "sdcc-port"
SRC = WORK / "src"
SHIM = ROOT / "fw" / "sdcc"                    # keil_compat.h, intrins.h (committed)
OVERLAY = ROOT / "fw" / "overlay"              # our board/project files, SDK-relative paths, replace SDK copies
SDCC = "sdcc-sdcc"                             # Fedora package name
# Per-file backstop (sdcc prints nothing while working, so no stall guard). Worst measured: RL6449_Series_DPRx0.c
# 64 s under full parallel load (#8). 3x worst-case rule (awto-dan#53). Expiry -> logged TIMEOUT fail.
COMPILE_TIMEOUT = 200
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


# ---------------- rewrite rules ----------------
SRC_EXT = {".c", ".h"}
RULES = [
    # Keil memory qualifiers that can also be identifiers: only in declarator position
    (re.compile(r"\bcode(?=\s+[\*A-Za-z_])"), "__code"),
    (re.compile(r"\bdata(?=\s+[\*A-Za-z_])"), "__data"),
    # sfr NAME = 0xNN;  ->  __sfr __at(0xNN) NAME;
    (re.compile(r"\bsfr\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr __at(\2) \1;"),
    (re.compile(r"\bsfr16\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr16 __at(\2) \1;"),
    # ISR / register bank, only right after a parameter list: `) interrupt N [using M]`, `) using M`
    (re.compile(r"\)\s*interrupt\s+(\w+)\s+using\s+(\w+)"), r") __interrupt(\1) __using(\2)"),
    (re.compile(r"\)\s*interrupt\s+(\w+)(?=\s*[{;\n])"), r") __interrupt(\1)"),
    (re.compile(r"\)\s*using\s+(\d)(?=\s*[{;\n])"), r") __using(\1)"),
    # TYPE QUAL NAME _at_ ADDR;  ->  __at(ADDR) TYPE QUAL NAME;
    (re.compile(r"^(\s*)([^;\n]*?)\b(\w+(?:\s*\[[^\]\n]*\])?)\s+_at_\s+([^;]+);", re.M), r"\1__at(\4) \2\3;"),
    # Keil-only pragmas (optimiser level, register banks) -> dropped; save/restore are kept (SDCC has them)
    (re.compile(r"^\s*#\s*pragma\s+(OT|OPTIMIZE|NOAREGS|AREGS|REGPARMS|NOREGPARMS|SRC|ASM|ENDASM|"
                r"LARGE|SMALL|COMPACT|ROM|CODE|DEBUG|OBJECTEXTEND|SYMBOLS|NOINTVECTOR|INTVECTOR)\b.*$",
                re.M | re.I), r"// [keil2sdcc] dropped pragma"),
]
# Compile-out rules for SDK code we don't use: (SDK-relative file, start-line regex, end-line regex, switch).
# Lines start..end (first end match after start) get wrapped in #if(switch == _ON). Switches default _OFF
# in fw/overlay/Project/Header/RL6449_Project.h. SDCC's linker keeps unreferenced code, so this saves flash.
OSD = "User/RTD Series/RTD2014Osd/Code/"
WRAPS = [
    # Realtek demo boot logo (call, draw fn, char maps, VLC glyph blobs + loader cases); ours replaces it
    # two single-line wraps: the backlight-on call between them must stay
    (OSD + "RTD2014Osd.c", r"^\s*OsdDispShowLogo\(\);", r"^\s*OsdDispShowLogo\(\);", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014Osd.c", r"ActiveTimerEvent\(SEC\(3\), _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO\);",
     r"_USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO\);", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdDisplay.c", r"^void OsdDispShowLogo\(void\)$", r"^\}", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontTable.c", r"^BYTE __code tiOSD_REALTEK_1BIT_LOGO0\[\]", r"^\};", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontTable.c", r"^BYTE __code tiOSD_REALTEK_1BIT_LOGO1\[\]", r"^\};", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontVLC.c", r"^BYTE __code tICON_REALTEK_1BIT_LOGO0\[\]", r"^\};", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontVLC.c", r"^BYTE __code tICON_REALTEK_1BIT_LOGO1\[\]", r"^\};", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontVLC.c", r"^\s*case _REALTEK_1BIT_LOGO0:", r"^\s*default:", "_AWTO_DEMO_LOGO", "before-end"),
    # DDC RAM arrays: address differs per chip/DDC channel, so the header extern can't get a single __at;
    # hide it from the defining file (SDCC rejects extern-without-__at + __at definition in one TU)
    ("Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonMcuInclude.h",
     r"^#if\(_D0_EMBEDDED_DDCRAM_MAX_SIZE", r"^extern BYTE xdata MCU_DDCRAM_D2\[", "!defined(_AWTO_DDCRAM_DEFINER)"),
    ("Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonMcuInclude.h",
     r"^#if\(_D0_MHL_EMBEDDED_DDCRAM_SIZE", r"^extern BYTE xdata MCU_DDCRAM_MHL_D2\[", "!defined(_AWTO_DDCRAM_DEFINER)"),
]
# Lines inserted before the first line matching anchor: (SDK-relative file, anchor regex, text)
INSERTS = [
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c", r"^#include", "#define _AWTO_DDCRAM_DEFINER"),
]


def apply_inserts(rel: str, text: str, stats) -> str:
    for f, anchor, add in INSERTS:
        if f != rel:
            continue
        lines = text.split("\n")
        i = next((k for k, l in enumerate(lines) if re.search(anchor, l)), None)
        if i is None:
            sys.exit(f"insert rule did not match: {f} {anchor!r}")
        lines.insert(i, add + "  // [keil2sdcc] insert")
        text = "\n".join(lines)
        stats["insert"] += 1
    return text


def apply_wraps(rel: str, text: str, stats) -> str:
    lines = text.split("\n")
    for w in WRAPS:
        f, start, end, sw = w[:4]
        if f != rel:
            continue
        before_end = len(w) > 4 and w[4] == "before-end"      # end line itself stays outside the #if
        s = next((i for i, l in enumerate(lines) if re.search(start, l)), None)
        e = None if s is None else next((i for i in range(s, len(lines)) if re.search(end, lines[i])), None)
        if s is None or e is None:
            sys.exit(f"wrap rule did not match: {f} {start!r}..{end!r} (SDK changed? fix the rule)")
        e = e - 1 if before_end else e
        cond = sw if re.search(r"[()!=<> ]", sw) else f"{sw} == _ON"     # switch name or raw condition
        lines[s:e + 1] = [f"#if({cond})  // [keil2sdcc] wrap"] + lines[s:e + 1] + ["#endif"]
        stats[f"wrap {sw}"] += 1
    return "\n".join(lines)


SBIT = re.compile(r"\bsbit\s+(\w+)\s*=\s*([\w]+)\s*\^\s*(\d)\s*;")
INCLUDE = re.compile(r'^(\s*#\s*include\s*[<"])([^>"]+)([>"])', re.M)


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
        hit = ci_resolve(here, inc)                          # same path, wrong case in some component
        if hit is not None:
            fixed = os.path.relpath(hit, here).replace(os.sep, "/")
            return m.group(1) + fixed + m.group(3)
        hits = idx.get(Path(inc).name.lower())
        if hits and len(hits) == 1:                         # basename unique -> correct the case
            fixed = str(Path(inc).parent / hits[0].name) if "/" in inc else hits[0].name
            return m.group(1) + fixed + m.group(3)
        return m.group(1) + inc + m.group(3)
    return INCLUDE.sub(sub, text)


USING_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*using\s+(\d)\s*\n?\s*\{")
INT_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*interrupt\s+(\w+)(?:\s+using\s+(\d))?\s*\n?\s*\{")


def add_using_to_protos(text, using, stats):
    """SDCC needs the prototype's __interrupt/__using to match the definition (Keil does not).
    Dropping __using is unsafe: the fn runs on an ISR register bank. `using` maps name -> attr string."""
    def sub(m):
        attrs = using.get(m.group(2))
        if attrs is None or "__using" in m.group(0) or "__interrupt" in m.group(0) \
                or re.search(r"\breturn\b", m.group(1)):
            return m.group(0)
        stats["proto attrs added"] += 1
        return f"{m.group(1)}{m.group(2)}({m.group(3)}){attrs};"
    # declaration line: [extern] <type words> [*] name(params);  (a call has no type words before it)
    return re.sub(r"^(\s*(?:extern\s+)?(?:\w+\s+)+\**\s*)(\w+)\s*\(([^;{()]*)\)\s*;", sub, text, flags=re.M)


AT_DEF = re.compile(r"\b(\w+)(?:\s*\[[^\]\n]*\])?\s+_at_\s+([^;]+);")
AT_ADDR = {}                                   # name -> address expr, filled in port pass 1


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


def cmd_port():
    if SRC.exists():
        shutil.rmtree(SRC)
    idx = build_name_index()
    sfr_addr, using_all, at_all = {}, {}, {}
    files = [p for p in SDK.rglob("*") if p.is_file() and ".git" not in p.parts]
    for p in files:                                          # pass 1: sfr addresses, `using`/`_at_` defs
        if p.suffix.lower() in SRC_EXT:
            t = p.read_text(errors="replace")
            for m in re.finditer(r"\bsfr\s+(\w+)\s*=\s*(0[xX][0-9A-Fa-f]+|\d+)\s*;", t):
                sfr_addr[m.group(1)] = int(m.group(2), 0)
            for m in USING_DEF.finditer(t):
                using_all.setdefault(m.group(1), set()).add(f" __using({m.group(2)})")
            for m in AT_DEF.finditer(t):
                at_all.setdefault(m.group(1), set()).add(m.group(2).strip())
            for m in INT_DEF.finditer(t):
                using_all.setdefault(m.group(1), set()).add(
                    f" __interrupt({m.group(2)})" + (f" __using({m.group(3)})" if m.group(3) else ""))
    # 7 chips share names: a name defined differently across files is NOT auto-propagated (wrong-chip risk)
    using = {k: next(iter(v)) for k, v in using_all.items() if len(v) == 1}
    AT_ADDR.clear()
    AT_ADDR.update({k: next(iter(v)) for k, v in at_all.items() if len(v) == 1})
    for kind, d in (("using/interrupt", using_all), ("_at_", at_all)):
        conflicts = sorted(k for k, v in d.items() if len(v) > 1)
        if conflicts:
            log(f"{kind}: {len(conflicts)} names with conflicting definitions not propagated: "
                f"{', '.join(conflicts[:12])}{' ...' if len(conflicts) > 12 else ''}")
    stats = Counter()
    n = 0
    for p in files:
        rel = p.relative_to(SDK)
        dst = SRC / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in SRC_EXT:
            raw = p.read_bytes().decode("latin-1")           # byte-preserving; comments are GBK/Big5
            out = rewrite(raw, p.parent, idx, sfr_addr, using, stats)
            out = apply_wraps(str(rel), out, stats)
            out = apply_inserts(str(rel), out, stats)
            dst.write_bytes(out.encode("latin-1"))
            n += 1
        elif p.suffix.lower() in {".uv2", ".lin", ".a51", ".inc"}:
            shutil.copy2(p, dst)
    ov = [p for p in OVERLAY.rglob("*") if p.is_file()] if OVERLAY.exists() else []
    for p in ov:                                             # our files win over the SDK's
        dst = SRC / p.relative_to(OVERLAY)
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes().decode("latin-1")
        dst.write_bytes(rewrite(raw, (SDK / p.relative_to(OVERLAY)).parent, idx, sfr_addr, using, stats)
                        .encode("latin-1"))
        log(f"overlay: {p.relative_to(OVERLAY)}")
    log(f"port: {n} C/H files rewritten into {SRC}; sfr map {len(sfr_addr)} names; "
        f"{len(using)} fns with `using`; {len(ov)} overlay files")
    for k, v in stats.most_common():
        log(f"  rule {v:6d}  {k}")
    return 0


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


def sdcc_cmd(c: Path, uv2dir: Path, defines, incs, model):
    cmd = [SDCC, "-mmcs51", {0: "--model-small", 1: "--model-medium", 2: "--model-large"}.get(model, "--model-large"),
           "--std-sdcc11", "--opt-code-size",                 # flash is the constraint (Dan: smallest)
           f"-Wp-include,{SHIM / 'keil_compat.h'}", f"-I{SHIM}"]
    cmd += [f"-I{(uv2dir / i).resolve()}" for i in incs]
    cmd += [f"-I{c.parent}"]
    cmd += [f"-D{d}" for d in defines]
    return cmd


ASM_MODE = False                               # compile --asm: emit .asm (-S) for the XDATA overlay pass


def compile_one(c: Path, uv2dir: Path, defines, incs, model):
    rel_dir = uv2dir.relative_to(SRC)
    out = WORK / ("asm" if ASM_MODE else "obj") / rel_dir / (c.stem + (".asm" if ASM_MODE else ".rel"))
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = sdcc_cmd(c, uv2dir, defines, incs, model) + ["-S" if ASM_MODE else "-c", "-o", str(out), str(c)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=COMPILE_TIMEOUT)
        msg, rc = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        msg, rc = f"TIMEOUT after {COMPILE_TIMEOUT}s", 124
    return str(c.relative_to(SRC)), rc, msg


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
    ok = [r for r in res if r[1] == 0]
    bad = [r for r in res if r[1] != 0]
    hist, per_file = Counter(), {}
    for f, rc, msg in bad:
        errs = [l for l in msg.splitlines() if "error" in l.lower() or "TIMEOUT" in l]
        per_file[f] = errs[:20]
        for e in set(norm_err(l) for l in errs):
            hist[e] += 1
    (WORK / "logs").mkdir(parents=True, exist_ok=True)
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
           "per_file": per_file}
    log("segment bytes: " + ", ".join(f"{k}={v}" for k, v in seg.most_common() if v))
    (WORK / "report.json").write_text(json.dumps(rep, indent=1))
    log(f"compiled in {time.time() - t0:.0f}s: ok {len(ok)} fail {len(bad)}")
    print_hist(rep)
    return 0 if not bad else 1


def print_hist(rep, n=25):
    log(f"top errors (files affected) for {rep['uv2']}: ok {rep['ok']} fail {rep['fail']}")
    for e, k in rep["hist"][:n]:
        log(f"  {k:5d}  {e}")


def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "keil2sdcc.log").open("a")
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    if a[0] == "port":
        return cmd_port()
    if a[0] == "compile":
        jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count()
        only = a[a.index("--only") + 1] if "--only" in a else None
        target = a[a.index("--target") + 1] if "--target" in a else None
        global ASM_MODE, COMPILE_TIMEOUT
        ASM_MODE = "--asm" in a
        if "--timeout" in a:                                 # for measuring a slow file once
            COMPILE_TIMEOUT = int(a[a.index("--timeout") + 1])
        return cmd_compile(a[1], jobs, only, target)
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
