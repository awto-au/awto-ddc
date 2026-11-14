#!/usr/bin/env python3
"""SDK option audit: every option in effect for the RL6449 build, resolved by the preprocessor (awto-ddc#165).

usage: sdk_option_audit.py opts            -> tmp/audit/options.tsv (name, value, defining file:line, raw text)
       sdk_option_audit.py modules         -> tmp/audit/modules.tsv (per module: code bytes, XDATA bytes)
       sdk_option_audit.py linked          -> tmp/audit/linked.tsv (linked code bytes per module, from fw.map)
       sdk_option_audit.py measure         -> linked code / XDATA bytes of tmp/fw/AWT26110002/fw.map
       sdk_option_audit.py toggle TAG NAME[,NAME..] [TAG NAME..]   one fw_build per TAG with NAME(s) _ON -> _OFF
       sdk_option_audit.py patch TAG FILE.json                     one fw_build with a src-patch (trial edits)
  toggle / patch append tmp/audit/toggles.tsv (code, xdata, free bytes per XDATA hole); builds = wb_build's compiler.
- opts: sdcc -E -dD on a probe that includes SysInclude.h with the RL6449_Project target flags (same cmd as
  fw_compile); the active definition = last #define before end (no later #undef). Values from `#if` in the
  probe, so derived expressions (_MHL_SUPPORT = port types ...) are evaluated, not grepped.
- modules: code / XDATA area sizes of tmp/sdcc-port/asm_bank/_size/*.rel (before the bank step drops dead chunks).
- Toggle deltas include the image tag string: compare toggles with each other, not with a wb_build image.
Needs a built tree (fw_build.py) in this checkout. Log: tmp/logs/sdk_option_audit.log
"""
import os, re, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_compile as FC  # noqa: E402

ROOT = FC.ROOT
OUT = ROOT / "tmp/audit"
UV2 = FC.SRC / "STD_FW_1P.Uv2"
TARGET = "RL6449_Project"
PP_TIMEOUT = 60                     # one sdcpp run of SysInclude.h: ~2 s measured; stall backstop
OPT_FILES = re.compile(r"(RL6449_Project\.h|RL6449_Project_Default\.h|RL6449_Pcb_Default\.h|RL6449_Gen_Option\.h|"
                       r"Project_Option\.h|Project_Asm_Option\.h|RL6449_AWTO_JXC4K\.h|User_Project_Option\.h|"
                       r"User_Scaler_Option\.h|Panel_Default\.h|Panel_Option\.h|Pcb_Option\.h|RL6449_Series_Option\.h)$")
LOG = None


def log(s):
    line = f"{isostamp.now()} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def cpp(probe: Path, extra):
    files, defines, incs, model = FC.parse_uv2(UV2, TARGET)
    sysdir = FC.SRC / "Kernel/System/Code"
    cmd = FC.sdcc_cmd(sysdir / "SysMain.c", UV2.parent, defines, incs, model) + [f"-I{sysdir}"] + extra + ["-E", str(probe)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=PP_TIMEOUT)
    if r.stderr.strip():
        LOG.write(r.stderr[-4000:] + "\n")
    return r.stdout


def cmd_opts():
    OUT.mkdir(parents=True, exist_ok=True)
    probe = OUT / "optprobe.c"
    probe.write_text('#include "SysInclude.h"\n')
    txt = cpp(probe, ["-Wp-dD"])
    cur, line_no, active = "?", 0, {}
    for ln in txt.splitlines():
        m = re.match(r'#\s*(?:line\s+)?(\d+)\s+"([^"]+)"', ln)
        if m:
            line_no, cur = int(m.group(1)) - 1, m.group(2); continue
        line_no += 1
        m = re.match(r"#define\s+(_\w+)(\s+(.*))?$", ln)
        if m and OPT_FILES.search(cur):
            active[m.group(1)] = (m.group(3) or "", f"{Path(cur).name}:{line_no}")
        elif m:
            active.pop(m.group(1), None)              # redefined outside the option headers: not an option
        m = re.match(r"#undef\s+(_\w+)", ln)
        if m:
            active.pop(m.group(1), None)
    names = [n for n, (v, _) in active.items() if v and '"' not in v and "{" not in v and not re.match(r"\w+\(", v)]
    body = ['#include "SysInclude.h"']
    for n in names:
        body += [f"#if ({n}) == 1", f"awtoopt_{n} ON", f"#elif ({n}) == 0", f"awtoopt_{n} OFF", "#else",
                 f"awtoopt_{n} VAL {n}", "#endif"]
    probe.write_text("\n".join(body) + "\n")
    res = {}
    for ln in cpp(probe, []).splitlines():
        m = re.match(r"\s*awtoopt_(_\w+)\s+(ON|OFF|VAL)\s*(.*)", ln)
        if m:
            res[m.group(1)] = m.group(2) if m.group(2) != "VAL" else "VAL " + m.group(3).strip()[:60]
    rows = ["name\tvalue\tdefined_at\ttext"]
    for n in sorted(active):
        v, at = active[n]
        rows.append(f"{n}\t{res.get(n, '-')}\t{at}\t{v[:120]}")
    (OUT / "options.tsv").write_text("\n".join(rows) + "\n")
    on = sum(1 for n in res if res[n] == "ON")
    log(f"opts: {len(active)} option macros, {len(res)} resolved, {on} == 1 (ON) -> {OUT / 'options.tsv'}")


def cmd_modules():
    """Per module: code bytes (all code-space areas of its sized .rel, before the bank step's dead-chunk drop)
    and XDATA bytes (XSEG + XISEG). Source: tmp/sdcc-port/asm_bank/_size/*.rel (sizes are hex)."""
    rows, tot = [], [0, 0]
    for f in sorted((ROOT / "tmp/sdcc-port/asm_bank/_size").glob("*.rel")):
        code = xd = 0
        for m in re.finditer(r"^A (\w+) size ([0-9A-Fa-f]+) flags ([0-9A-Fa-f]+)", f.read_text(errors="replace"), re.M):
            size, flags = int(m.group(2), 16), int(m.group(3), 16)
            if m.group(1) in ("XSEG", "XISEG"):
                xd += size
            elif flags & 0x20000 and m.group(1) != "XINIT":
                code += size
        rows.append((f.stem, code, xd)); tot[0] += code; tot[1] += xd
    rows.sort(key=lambda r: -r[1])
    (OUT / "modules.tsv").write_text("module\tcode\txdata\n" + "".join(f"{a}\t{b}\t{c}\n" for a, b, c in rows))
    log(f"modules: {len(rows)}, code {tot[0]} B, xdata {tot[1]} B -> {OUT / 'modules.tsv'}")


def measure(serial="AWT26110002"):
    """(code, xdata) bytes of the linked image: unique map areas by CODE / XDATA attribute (common counted once)."""
    t = (ROOT / f"tmp/fw/{serial}/fw.map").read_text(errors="replace")
    seen = {}
    for m in re.finditer(r"^(\S+)\s+([0-9A-F]{8})\s+[0-9A-F]{8} =\s+(\d+)\. bytes \(([^)]*)\)", t, re.M):
        seen[(m.group(1), m.group(2))] = (int(m.group(3)), m.group(4))
    code = sum(s for s, at in seen.values() if "CODE" in at)
    xd = sum(s for s, at in seen.values() if "XDATA" in at)
    return code, xd


def cmd_linked():
    """Linked code bytes per module: map areas (CODE) -> the asm_bank/*.rel that defines them; -> tmp/audit/linked.tsv."""
    owner = {}
    for f in (ROOT / "tmp/sdcc-port/asm_bank").glob("*.rel"):
        for m in re.finditer(r"^A (\w+) size ([0-9A-Fa-f]+)", f.read_text(errors="replace"), re.M):
            if int(m.group(2), 16):
                owner.setdefault(m.group(1)[:32], f.stem)        # map prints area names cut to 32 chars
    t = (ROOT / "tmp/fw/AWT26110002/fw.map").read_text(errors="replace")
    seen = {}
    for m in re.finditer(r"^(\S+)\s+([0-9A-F]{8})\s+[0-9A-F]{8} =\s+(\d+)\. bytes \(([^)]*)\)", t, re.M):
        if "CODE" in m.group(4):
            seen[(m.group(1), m.group(2))] = int(m.group(3))
    per = {}
    for (area, _), n in seen.items():
        mod = owner.get(area[:32], "(" + re.sub(r"\d+$", "", area) + ")")
        per[mod] = per.get(mod, 0) + n
    rows = sorted(per.items(), key=lambda kv: -kv[1])
    (OUT / "linked.tsv").write_text("module\tlinked_code\n" + "".join(f"{a}\t{b}\n" for a, b in rows))
    log(f"linked: {len(rows)} modules, {sum(per.values())} B -> {OUT / 'linked.tsv'}")


BUILD_ENV = dict(AWTO_SDCC_BE="1", AWTO_SDCCCALL="3", AWTO_SDCC_BIN="/usr/local/bin",
                 AWTO_SDCC_SRC="/usr/local/share/sdcc/awto-src", K2S_SDCC_EXTRA="-D_AWTO_AUDIT_NOP=1")   # = wb_build.py rolled compiler
BUILD_TIMEOUT = 240                 # whole fw_build: 76 s measured cold (2026-11-12) x3 backstop; fw_build has per-step stall guards


def cmd_toggle(names, tag, patch_file=None):
    """fw_build with NAME(s) switched _ON -> _OFF in the derived tree (--src-patch), or with a given src-patch JSON;
    appends tmp/audit/toggles.tsv."""
    opts = {l.split("\t")[0]: l.split("\t") for l in (OUT / "options.tsv").read_text().splitlines()[1:]}
    patch = __import__("json").loads(Path(patch_file).read_text()) if patch_file else []
    for n in ([] if patch_file else names):
        f = opts[n][2].rsplit(":", 1)[0]
        src = next((FC.SRC).rglob(f))
        rel = src.relative_to(FC.SRC).as_posix()
        hits = re.findall(rf"^[ \t]*#define[ \t]+{n}[ \t]+_ON\b.*$", src.read_text(errors="replace"), re.M)
        if len(hits) != 1:
            log(f"toggle {tag}: {n} in {rel}: {len(hits)} '#define {n} _ON' lines, skipped"); return
        patch.append({"file": rel, "old": hits[0], "new": hits[0].replace("_ON", "_OFF", 1)})
    pf = OUT / f"patch_{tag}.json"
    pf.write_text(__import__("json").dumps(patch, indent=1))
    env = dict(os.environ, AWTO_DDC_REPO=str(ROOT), **BUILD_ENV)
    out = ROOT / f"tmp/logs/audit_toggle_{tag}.out"
    t0 = time.monotonic()
    with out.open("w") as fh:
        rc = subprocess.run([sys.executable, "scripts/fw_build.py", "--serial", "AWT26110002", "--src-patch", str(pf)],
                            cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=BUILD_TIMEOUT).returncode
    el = time.monotonic() - t0
    tail = [l for l in out.read_text(errors="replace").splitlines() if "unused row" not in l][-3:]
    code, xd = measure() if rc == 0 else (-1, -1)
    free = re.search(r"free after placement \[([^\]]*)\]", out.read_text(errors="replace"))
    tsv = OUT / "toggles.tsv"
    if not tsv.exists():
        tsv.write_text("tag\toptions\trc\tcode\txdata\txdata_free_per_hole\tseconds\n")
    with tsv.open("a") as fh:
        fh.write(f"{tag}\t{','.join(names)}\t{rc}\t{code}\t{xd}\t{free.group(1) if free else '-'}\t{el:.0f}\n")
    log(f"toggle {tag} {names}: rc={rc} code={code} xdata={xd} free={free.group(1) if free else '-'} {el:.0f}s"
        + ("" if rc == 0 else f" | {' | '.join(tail)[-400:]}"))


def main():
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdk_option_audit.log").open("a")
    a = sys.argv[1:]
    if a and a[0] == "linked":
        cmd_linked(); return 0
    if a and a[0] == "measure":
        log(f"measure: code, xdata = {measure()}"); return 0
    if a and a[0] == "patch" and len(a) == 3:   # patch TAG FILE.json (src-patch format: [{file, old, new}])
        cmd_toggle([Path(a[2]).stem], a[1], a[2]); return 0
    if a and a[0] == "toggle" and len(a) >= 3:   # toggle TAG NAME[,NAME..] [TAG NAME ...]
        for i in range(1, len(a) - 1, 2):
            cmd_toggle(a[i + 1].split(","), a[i])
        return 0
    if not a or a[0] not in ("opts", "modules"):
        print(__doc__); return 2
    {"opts": cmd_opts, "modules": cmd_modules}[a[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
