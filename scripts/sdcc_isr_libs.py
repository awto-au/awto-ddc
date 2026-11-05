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
Priority: EXINT0 (IP=0x81) and Timer2 (IP=0xA0) are each high in one IP state, so they get `_isr1` / `_isr2` copies
where another class reaches the same helper; all other ISRs share `_isr`.
"""
import argparse, json, os, re, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
from sdcc_bank import Module, render  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = repo_root()
LIBSRC = Path(os.environ.get("AWTO_SDCC_SRC") or "/mnt/2tb/git/awto-sdcc") / "device/lib"
OURS = {"__modulong": "fw/sdcc/crt_mod0.c", "__moduint": "fw/sdcc/crt_mod0.c",
        "__divulong": "fw/sdcc/crt_divulong.c"}   # our overrides of lib symbols
# mcs51-large Makefile: CFLAGS + MODELFLAGS + --opt-code-speed
LIBFLAGS = ["-mmcs51", "--model-large", "--std-c23", "--opt-code-speed"]
CC_TIMEOUT = 60           # one tiny lib file compiles in < 2 s; stall = broken input
TOKEN = re.compile(r"(?<![\w$.])[A-Za-z_][\w$]*")
CALL = re.compile(r"^\s+(?:lcall|ljmp)\s+(\w+)\s*$")
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


# IP state: 0xA0 -> Timer2 high, 0x81 -> EXINT0 high (SDK writes both; EIP never written). Class "" = always low.
PRIO_CLASS = {0: "1", 5: "2"}


def isr_name(n: str, sfx: str = "_isr") -> str:
    m = re.match(r"^(.*)_PARM_(\d+)$", n)
    return f"{m.group(1)}{sfx}_PARM_{m.group(2)}" if m else n + sfx


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

    # priority class per ISR: "" = low in every IP state; EXINT0 / Timer2 are high in one IP state each
    vec = {}
    for m in mods:
        for n, v in re.findall(r"void (\w+)\s*\(void\)\s*__interrupt\s*\(\s*(\d+)\s*\)", "\n".join(l for c in m.chunks for l in c.lines)):
            vec["_" + n] = int(v)
    cls_of = lambda r: PRIO_CLASS.get(vec.get(r.name, -1), "")
    reach_c = {r.name: reach([r], funcs) for r in isr_roots}
    classes = sorted({cls_of(r) for r in isr_roots})
    chunk_cls = defaultdict(set)                            # chunk -> priority classes reaching it
    for r in isr_roots:
        for n in reach_c[r.name]:
            chunk_cls[n].add(cls_of(r))

    # helpers (undefined in the project) called per class, + helpers the clones call (e.g. divslong -> divulong)
    done, deps = {}, {}

    def stems_for(called):
        got, pending = set(), sorted(called)
        while pending:
            src = src_of(pending.pop())
            if src is None or src.stem in got:
                continue
            got.add(src.stem)
            if src.stem not in done:
                done[src.stem] = compile_lib(src, out / f"{src.stem}.asm")
                deps[src.stem] = set(re.findall(r"^\s+(?:lcall|ljmp)\s+(\w+)", done[src.stem], re.M))
            pending += sorted(deps[src.stem])
        return got
    need = {k: stems_for({t for r in isr_roots if cls_of(r) == k for c in reach_c[r.name].values()
                          for t in c.calls if t not in funcs}) for k in classes}
    keep = sorted(st for st in done if not stateful(done[st]))
    live = sorted(set(done) - set(keep))
    owners = {st: [k for k in classes if st in need[k]] for st in live}

    def suffix(st, k):                                      # second copy only where two priority levels reach it
        return "_isr" if len(owners[st]) < 2 or k == "" else f"_isr{k}"
    owner_of = {g: st for st in live for g in defined_globals(done[st])}
    maps = {k: {g: isr_name(g, suffix(st, k)) for g, st in owner_of.items()} for k in classes}
    for st in done:
        (out / f"{st}.asm").unlink(missing_ok=True)
    for st in live:
        for k in owners[st]:
            sfx = suffix(st, k)
            if (out / f"{st}{sfx}.asm").exists():
                continue                                    # one-owner stems share the plain name
            txt = TOKEN.sub(lambda x: maps[k].get(x.group(0), x.group(0)), done[st])
            txt = re.sub(r"\.area\s+OSEG\s+\(OVR,DATA\)", ".area DSEG    (DATA)", txt)   # OVR would share IRAM with the original
            txt = re.sub(r"\.area XSEG \(XDATA\)", ".area XSEG    (XDATA)", txt)   # inline-asm spelling; fw_build.split_xseg
            txt = re.sub(r"^(\s+\.module\s+)(\S+)", lambda x: f"{x.group(1)}{x.group(2)}{sfx}", txt, flags=re.M)
            (out / f"{st}{sfx}.asm").write_text(txt)
            log(f"clone {st}{sfx}.asm (priority class '{k or 'low'}'; reached by {[o or 'low' for o in owners[st]]})")
    log(f"cloned helper files: {live}; skipped (no state): {keep}")
    dup = {st: [o or "low" for o in owners[st]] for st in live if len(owners[st]) > 1}
    log(f"helpers with >1 copy (reached from several priority classes): {dup}")

    # rewrite ISR-only chunks; chunks shared with main stay original and are reported
    changed, used, shared_hits, multi_hits = defaultdict(set), defaultdict(set), [], []
    for m in mods:
        for c in m.chunks:
            if c.name not in isr_reach or c.area != "CSEG":
                continue
            hit = (c.calls | c.refs) & set(owner_of)
            if not hit:
                continue
            if c.name in main_reach:
                shared_hits.append((c.name, sorted(hit)))
                continue
            ks = sorted(chunk_cls[c.name])
            if len(ks) > 1 and any(len({maps[x][h] for x in ks}) > 1 for h in hit):
                multi_hits.append((c.name, sorted(hit)))    # one body cannot pick a copy per priority level
                continue
            mapping = maps[ks[0]]
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
        mp = maps[cls_of(r)]
        by_root[r.name] = sorted({mp[t] for c in reach_c[r.name].values() for t in c.calls if t in mp})
    for name, h in shared_hits:
        log(f"WARNING shared ISR+main chunk calls non-reentrant helper, NOT rewritten: {name} {h}")
    for name, h in multi_hits:
        log(f"ERROR chunk reached from several priority classes calls a per-class helper: {name} {h}")
    if multi_hits:
        return 1
    rep = {"cloned": live, "isr_helpers": by_root, "shared_not_rewritten": shared_hits,
           "chunks_rewritten": {k: sorted(v) for k, v in changed.items()}}
    (Path(a.out).parent / "isr_libs.json").write_text(json.dumps(rep, indent=1))
    for r, h in by_root.items():
        if h:
            log(f"ISR {r}: {', '.join(h)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
