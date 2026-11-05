#!/usr/bin/env python3
"""ISR-private copies of SDCC's non-reentrant mcs51 arithmetic helpers (awto-ddc#19).

usage: sdcc_isr_libs.py [--asm DIR] [--out DIR]
  --asm  asm tree rewritten IN PLACE (default tmp/sdcc-port/asm_ovl, between sdcc_overlay and sdcc_bank)
  --out  cloned helper asm (default tmp/sdcc-port/isr_libs/*.asm; fw_build assembles them into common code)
Why: __mullong/__divulong/... keep arg 2+ in fixed XDATA (`<fn>_PARM_n`) and static locals; an ISR landing
between main's PARM store and the call corrupts main's result.
Method:
- ISR roots = chunks with `reti` (sdcc_bank.Chunk.isr); closure over lcall/ljmp = ISR-reachable chunks.
- Helpers called there that have a library source (device/lib/<name>.c, or fw/sdcc/crt_mod0.c) and keep state
  are compiled with the library flags; every global they define gets `_isr` (`__mullong_isr_PARM_2`).
- In ISR-reachable chunks only, those symbols are renamed. Chunks reachable from ISR AND main/address-taken
  are NOT rewritten and are reported (tmp/sdcc-port/isr_libs.json). Log: tmp/logs/sdcc_isr_libs.log
Caveat: one copy serves all ISRs; a high-priority ISR (IP) preempting a low-priority one still shares it.
"""
import argparse, json, os, re, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
from sdcc_bank import Module, render  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = repo_root()
LIBSRC = T.LIBSRC
OURS = {"__modulong": "fw/sdcc/crt_mod0.c", "__moduint": "fw/sdcc/crt_mod0.c",
        "__divulong": "fw/sdcc/crt_divulong.c"}   # our overrides of lib symbols
# mcs51-large Makefile: CFLAGS + MODELFLAGS + --opt-code-speed
LIBFLAGS = ["-mmcs51", "--model-large", "--std-c23", "--opt-code-speed", *T.CFLAGS_EXTRA]
CC_TIMEOUT = 60           # one tiny lib file compiles in < 2 s; stall = broken input
TOKEN = re.compile(r"(?<![\w$.])[A-Za-z_][\w$]*")
CALL = re.compile(r"^\s+(?:lcall|ljmp)\s+(\w+)\s*$")
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def isr_name(n: str) -> str:
    m = re.match(r"^(.*)_PARM_(\d+)$", n)
    return f"{m.group(1)}_isr_PARM_{m.group(2)}" if m else n + "_isr"


def src_of(sym: str):
    if sym in OURS:
        return ROOT / OURS[sym]
    p = LIBSRC / f"{sym[1:]}.c"                     # asm `__mullong` = C `_mullong` = _mullong.c
    return p if p.exists() else None


def compile_lib(src: Path, out: Path) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [T.tool("sdcc"), *LIBFLAGS, f"-I{LIBSRC.parent / 'include'}", f"-I{LIBSRC.parent / 'include/mcs51'}",
           "-S", "-o", str(out), str(src)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=CC_TIMEOUT)
    if r.returncode:
        sys.exit(f"compile {src} failed:\n{r.stdout}{r.stderr}")
    return out.read_text()


def defined_globals(asm: str) -> set:
    g = set(re.findall(r"^\s+\.globl\s+(\w+)", asm, re.M))
    return g & set(re.findall(r"^(\w+)::?\s*$", asm, re.M))


def stateful(asm: str) -> bool:
    """Reserves RAM in a data area (PARM / static locals); REG_BANK .ds does not count."""
    area = None
    for l in asm.split("\n"):
        m = re.match(r"^\s+\.area\s+(\w+)", l)
        if m:
            area = m.group(1)
        elif area in ("XSEG", "DSEG", "OSEG", "ISEG", "BSEG", "PSEG") and re.match(r"^\s+\.ds\s", l):
            return True
    return False


def reach(roots, funcs):
    seen, st = {}, list(roots)
    while st:
        c = st.pop()
        if c.name in seen:
            continue
        seen[c.name] = c
        st.extend(funcs[t] for t in sorted(c.calls) if t in funcs)
    return seen


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_ovl"))
    ap.add_argument("--out", default=str(ROOT / "tmp/sdcc-port/isr_libs"))
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdcc_isr_libs.log").open("a")
    out = Path(a.out)
    for f in out.glob("*.asm") if out.exists() else []:
        f.unlink()                                          # derived
    mods = [Module(p) for p in sorted(Path(a.asm).glob("*.asm")) if not p.name.startswith("__")]
    funcs = {c.name: c for m in mods for c in m.chunks if c.area == "CSEG"}

    isr_roots = [c for c in funcs.values() if c.isr]
    isr_reach = reach(isr_roots, funcs)
    addr_taken = {r for m in mods for c in m.chunks for r in c.refs if r in funcs}
    main_reach = reach([funcs[n] for n in ["_main", *sorted(addr_taken)] if n in funcs], funcs)
    shared = sorted(set(isr_reach) & set(main_reach))
    log(f"ISR roots {len(isr_roots)}, ISR-reachable chunks {len(isr_reach)}, main-side {len(main_reach)}, both {len(shared)}")

    # helpers (undefined in the project) called from ISR-reachable chunks
    called = {t for c in isr_reach.values() for t in c.calls if t not in funcs}
    done, pending = {}, sorted(called)
    while pending:                                          # + helpers the clones call (e.g. divslong -> divulong)
        src = src_of(pending.pop())
        if src is None or src.stem in done:
            continue
        done[src.stem] = compile_lib(src, out / f"{src.stem}.asm")
        pending += sorted(set(re.findall(r"^\s+(?:lcall|ljmp)\s+(\w+)", done[src.stem], re.M)))
    stems = sorted(done)
    mapping, keep = {}, []
    for stem in stems:
        p = out / f"{stem}.asm"
        txt = p.read_text()
        if not stateful(txt):
            p.unlink(); keep.append(stem); continue         # register-only helper: reentrant already
        for g in defined_globals(txt):
            mapping[g] = isr_name(g)
    live = sorted(set(stems) - set(keep))
    for stem in live:                                       # rename every global the clone set defines
        p = out / f"{stem}.asm"
        txt = p.read_text()
        txt = TOKEN.sub(lambda x: mapping.get(x.group(0), x.group(0)), txt)
        txt = re.sub(r"\.area\s+OSEG\s+\(OVR,DATA\)", ".area DSEG    (DATA)", txt)   # OVR would share IRAM with the original
        txt = re.sub(r"\.area XSEG \(XDATA\)", ".area XSEG    (XDATA)", txt)   # inline-asm spelling; fw_build.split_xseg
        txt = re.sub(r"^(\s+\.module\s+)(\S+)", lambda x: f"{x.group(1)}{x.group(2)}_isr", txt, flags=re.M)
        p.with_name(f"{stem}_isr.asm").write_text(txt)
        p.unlink()
    log(f"cloned helper files: {live}; skipped (no state): {keep}")
    log(f"renamed globals: {len(mapping)}; e.g. {sorted(k for k in mapping if 'PARM' in k)[:6]}")

    # rewrite ISR-only chunks; chunks shared with main stay original and are reported
    changed, used, shared_hits = defaultdict(set), defaultdict(set), []
    for m in mods:
        for c in m.chunks:
            if c.name not in isr_reach or c.area != "CSEG":
                continue
            hit = (c.calls | c.refs) & set(mapping)
            if not hit:
                continue
            if c.name in main_reach:
                shared_hits.append((c.name, sorted(hit)))
                continue
            new = []
            for l in c.lines:
                code, sep, cmt = l.partition(";")
                new.append(TOKEN.sub(lambda x: mapping.get(x.group(0), x.group(0)), code) + sep + cmt)
            c.lines = new
            changed[m.name].add(c.name)
            used[m.name] |= {mapping[h] for h in hit}
    for m in mods:
        if m.name in changed:
            Path(a.asm, f"{m.name}.asm").write_text(render(m, lambda c: c.area, {}, used))
    log(f"rewrote {sum(len(v) for v in changed.values())} chunks in {len(changed)} modules")

    by_root = {}
    for r in isr_roots:
        by_root[r.name] = sorted({mapping[t] for c in reach([r], funcs).values() for t in c.calls if t in mapping})
    for name, h in shared_hits:
        log(f"WARNING shared ISR+main chunk calls non-reentrant helper, NOT rewritten: {name} {h}")
    rep = {"cloned": live, "isr_helpers": by_root, "shared_not_rewritten": shared_hits,
           "chunks_rewritten": {k: sorted(v) for k, v in changed.items()}}
    (Path(a.out).parent / "isr_libs.json").write_text(json.dumps(rep, indent=1))
    for r, h in by_root.items():
        if h:
            log(f"ISR {r}: {', '.join(h)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
