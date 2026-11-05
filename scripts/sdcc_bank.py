#!/usr/bin/env python3
"""Keil-BL51-style code banking for SDCC mcs51 asm on RL6449 (whole 64 KB banked, bank reg XDATA 0xFFFF).

usage: sdcc_bank.py [--asm DIR] [--out DIR] [--banks N] [--common-max BYTES]
  --asm  input asm tree (default tmp/sdcc-port/asm_ovl, output of sdcc_overlay.py)
  --out  rewritten tree + rel files (default tmp/sdcc-port/asm_bank)
  --banks       code banks available (default 14: banks 14-15 hold data, #8)
  --common-max  fail if common code exceeds this (default 0x6000)

Method (awto-ddc#8):
- Chunks: CSEG split per function, CONST split per label. Everything else (HOME, GSINIT, XINIT, data) stays.
- Common (area CSEG/CONST, copied into every bank image): ISR entry fns, main, and CONST used by common
  code or by more than one bank. Library code (not in any module) is common.
- Rest: module granularity, area BANK<n>; modules packed into banks in input order (first fit).
- Calls/jumps to a fn in another bank, from common to banked, and every address-taken banked fn go through
  a stub `__bs_<fn>` emitted in the fn's own module (common): mov r0/r1/r2,#fn24; ljmp __bs_call (fw/sdcc/bank.asm).
- Fails on: CONST referenced from a bank it is not in (after the common rule), a module larger than a bank.
Log: tmp/logs/sdcc_bank.log, report tmp/sdcc-port/bank.json
"""
import argparse, json, os, re, shutil, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import sdcc_tools as T  # noqa: E402

ROOT = repo_root()
LOG = None
FUNC_HDR = re.compile(r"^;\s+function (\w+)\s*$")
LABEL = re.compile(r"^(\w+)(::?)\s*$")
CALL = re.compile(r"^(\s+)(lcall|ljmp)(\s+)(\w+)\s*$")
SYM = re.compile(r"(?<![\w$])(_\w+)")
AR_EQU = re.compile(r"^\s*(ar[0-7]|rbank0)\s*=")
BANK_SIZE = 0x10000
HOT_BANKS = 3             # helper called from at least this many other banks
HOT_SIZE = 384            # and its banked callee closure no larger than this
ASM_TIMEOUT = 30          # one sdas8051 run: largest module assembles in < 2 s; stall = broken input


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


class Chunk:
    def __init__(self, area, name, lines, module):
        self.area, self.name, self.lines, self.module = area, name, lines, module
        self.common = False
        self.bank = None         # None = common
        self.size = 0

    def finish(self):
        """Derive ISR flag, call targets and symbol refs once the body is complete."""
        lines = self.lines
        self.isr = any(re.match(r"^\s+(reti\b|ljmp\s+sdcc_atomic_maybe_rollback\b)", l) for l in lines)
        self.calls, self.refs = set(), set()
        for l in lines:
            s = l.split(";", 1)[0]
            if not s.strip():
                continue
            c = CALL.match(s)
            if c:
                self.calls.add(c.group(4))
            else:
                self.refs.update(SYM.findall(s))
        self.refs.discard(self.name)


class Module:
    def __init__(self, path: Path):
        self.path, self.name = path, path.stem
        self.head, self.tail, self.chunks = [], [], []     # head: before first CSEG/CONST chunk; tail: rest
        self.parse(path.read_text(errors="replace").split("\n"))

    def parse(self, lines):
        """Split CSEG at function starts (incl. their preceding comment block) and CONST at labels."""
        out, area, cur, pending_cmt = self.head, None, None, []
        # SDCC emits `arN = rbank0+N` inside the first fn using it; drop_dead must not take it along (#17)
        equ = list(dict.fromkeys(l for l in lines if AR_EQU.match(l)))
        lines = [l for l in lines if not AR_EQU.match(l)]
        self.head.extend(equ)
        for line in lines:
            if line.startswith("\t.area"):
                area = line.split()[1]
                if cur is not None:
                    cur.lines.extend(pending_cmt); pending_cmt = []
                cur = None
                out = self.tail if self.chunks else self.head
                out.append(line)
                continue
            if area in ("CSEG", "CONST"):
                lab = LABEL.match(line)
                if line.startswith(";") and area == "CSEG":
                    pending_cmt.append(line)
                    if FUNC_HDR.match(line):
                        cur = None                     # next label opens the function chunk
                    continue
                if lab and (area == "CONST" or cur is None):
                    cur = Chunk(area, lab.group(1), pending_cmt + [line], self)
                    pending_cmt = []
                    self.chunks.append(cur)
                    continue
                if cur is None:
                    out.extend(pending_cmt); pending_cmt = []
                    out.append(line)
                else:
                    cur.lines.extend(pending_cmt); pending_cmt = []
                    cur.lines.append(line)
                continue
            if pending_cmt:
                (cur.lines if cur else out).extend(pending_cmt); pending_cmt = []
            out.append(line)
        if pending_cmt:
            (cur.lines if cur else out).extend(pending_cmt)
        for c in self.chunks:
            c.finish()

    def globls(self):
        return set(re.findall(r"^\s+\.globl\s+(\w+)", "\n".join(self.head + self.tail), re.M))


def assemble(asm: Path) -> dict:
    rel = asm.with_suffix(".rel")
    r = subprocess.run([T.tool("sdas8051"), "-plosgffw", str(rel), str(asm)],
                       capture_output=True, text=True, timeout=ASM_TIMEOUT)
    if r.returncode:
        sys.exit(f"sdas8051 failed on {asm}:\n{r.stdout}{r.stderr}")
    sizes = {}
    for m in re.finditer(r"^A (\w+) size (\w+)", rel.read_text(errors="replace"), re.M):
        sizes[m.group(1)] = sizes.get(m.group(1), 0) + int(m.group(2), 16)
    return sizes


def drop_dead(mods, funcs, consts):
    """Remove fn/CONST chunks unreachable from main, ISRs and non-chunk lines (XINIT/GSINIT); like LX51
    REMOVEUNUSED. Their .globl lines go too, so nothing references a dropped symbol."""
    allc = {**funcs, **consts}
    roots = {"_main"} | {c.name for c in funcs.values() if c.isr}
    for m in mods:
        for l in m.head + m.tail:
            s = l.split(";", 1)[0]
            if s.strip() and not re.match(r"^\s*\.(globl|area|module|optsdcc)\b", s) and not LABEL.match(s):
                roots.update(SYM.findall(s))
    seen, st = set(), [n for n in roots if n in allc]
    while st:
        n = st.pop()
        if n in seen:
            continue
        seen.add(n)
        st.extend(t for t in allc[n].calls | allc[n].refs if t in allc and t not in seen)
    dead = {n for n in allc if n not in seen}
    nb = {"CSEG": 0, "CONST": 0}
    for n in dead:
        nb[allc[n].area] += allc[n].size
        (funcs if allc[n].area == "CSEG" else consts).pop(n)
    for m in mods:
        m.chunks = [c for c in m.chunks if c.name not in dead]
        m.head = [l for l in m.head if not (re.match(r"^\s+\.globl\s+(\w+)", l) and l.split()[1] in dead)]
    log(f"dead chunks dropped: {len(dead)} ({nb['CSEG']} B code, {nb['CONST']} B const); kept {len(seen)}")


def render(mod, area_of, stubs_needed, extra_globl):
    """Module text with each chunk in the area area_of(chunk) gives; calls/refs to stubbed fns rewritten."""
    out = list(mod.head)
    for g in sorted(extra_globl.get(mod.name, ())):
        out.append(f"\t.globl {g}")
    groups = defaultdict(list)
    for c in mod.chunks:
        lines = []
        for l in c.lines:
            m = CALL.match(l.split(";", 1)[0]) if not l.startswith(";") else None
            if m and m.group(4) in stubs_needed and stubs_needed[m.group(4)][1] != c.bank:
                l = f"{m.group(1)}{m.group(2)}{m.group(3)}__bs{m.group(4)}"
            elif not l.lstrip().startswith(";") and not m and not LABEL.match(l):
                l = SYM.sub(lambda x: f"__bs{x.group(1)}" if x.group(1) in stubs_needed else x.group(1), l)
            lines.append(l)
        groups[area_of(c)].extend(lines)
    for area, lines in groups.items():
        out.append(f"\t.area {area}    (CODE)")
        out.extend(lines)
    stubs = [f for f in sorted(stubs_needed) if stubs_needed[f][0] == mod.name]
    if stubs:
        out.append("\t.area CSEG    (CODE)")
        for f in stubs:
            out += [f"\t.globl __bs{f}", f"__bs{f}:", f"\tmov\tr0,#{f}", f"\tmov\tr1,#({f} >> 8)",
                    f"\tmov\tr2,#({f} >> 16)", "\tljmp\t__bs_call"]
    out.extend(mod.tail)
    return "\n".join(out)


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_ovl"))
    ap.add_argument("--out", default=str(ROOT / "tmp/sdcc-port/asm_bank"))
    ap.add_argument("--banks", type=int, default=14)
    ap.add_argument("--common-max", type=lambda x: int(x, 0), default=0x6000)
    ap.add_argument("--hot-budget", type=lambda x: int(x, 0), default=0xC00,
                    help="common bytes for hot helpers moved out of banks")
    ap.add_argument("--pack-margin", type=lambda x: int(x, 0), default=0x600,
                    help="bytes kept free per bank at packing for CONST moved in afterwards")
    ap.add_argument("--keep-dead", action="store_true", help="keep chunks unreachable from main/ISRs")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdcc_bank.log").open("a")
    src, out = Path(a.asm), Path(a.out)
    if out.exists() and out.resolve() != src.resolve():
        shutil.rmtree(out)                                   # derived; stale rels were linked (#18)
    out.mkdir(parents=True, exist_ok=True)
    mods = [Module(p) for p in sorted(src.glob("*.asm")) if not p.name.startswith("__")]
    log(f"bank: {len(mods)} modules from {src}")

    funcs, consts = {}, {}                                   # symbol -> chunk
    for m in mods:
        for c in m.chunks:
            (funcs if c.area == "CSEG" else consts)[c.name] = c
    # common = ISR entry fns + main only; what they call is reached through stubs (bank saved/restored),
    # like Keil's ?B_SWITCH from interrupt code (old fw common is only 0x28C6 B)
    for c in funcs.values():
        if c.isr or c.name == "_main":
            c.common = True
    for c in funcs.values():
        if c.common:
            for r in c.refs:
                if r in consts:
                    consts[r].common = True
    ncommon = sum(c.common for c in funcs.values())
    log(f"common fns (ISR entries + main): {ncommon}")

    # per-chunk sizes: each chunk assembled in its own area
    tmp = out / "_size"; tmp.mkdir(exist_ok=True)
    for m in mods:
        idx = {id(c): i for i, c in enumerate(m.chunks)}
        p = tmp / f"{m.name}.asm"
        p.write_text(render(m, lambda c: f"S{idx[id(c)]}", {}, {}))
        sz = assemble(p)
        for c in m.chunks:
            c.size = sz.get(f"S{idx[id(c)]}", 0)
    if not a.keep_dead:
        drop_dead(mods, funcs, consts)
    cap = BANK_SIZE - a.common_max
    # packing units: a module's banked chunks together; a module over a bank splits into its chunks
    # module order = DFS preorder of the call graph from main and the ISRs (callees right after callers), so
    # call chains share a bank: each cross-bank level costs 3 more stack bytes (scripts/fw_stack.py, #8)
    mod_calls = defaultdict(lambda: defaultdict(int))
    for m in mods:
        for c in m.chunks:
            for t in c.calls:
                if t in funcs and funcs[t].module is not m:
                    mod_calls[m.name][funcs[t].module.name] += 1
    by_name = {m.name: m for m in mods}
    order, seen = [], set()
    starts = [funcs["_main"].module.name] if "_main" in funcs else []
    starts += [c.module.name for c in funcs.values() if c.isr]
    for st in starts + [m.name for m in mods]:
        stack = [st]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n); order.append(by_name[n])
            nxt = sorted(mod_calls[n].items(), key=lambda kv: kv[1])     # most-called pushed last = visited first
            stack.extend(k for k, _ in nxt if k not in seen)
    # ISR-only code (reached from an ISR, never from main or through a pointer) first, in ISR DFS order, one
    # chunk per unit: an interrupt then crosses banks once instead of at every call level
    def closure(roots):
        seen, st = set(), list(roots)
        while st:
            c = st.pop()
            if c.name in seen:
                continue
            seen.add(c.name)
            st.extend(funcs[t] for t in sorted(c.calls) if t in funcs)
        return seen
    addr_taken = {r for m in mods for c in m.chunks for r in c.refs if r in funcs}
    main_side = closure([funcs[n] for n in ["_main", *sorted(addr_taken)] if n in funcs])
    isr_order, seen = [], set()
    for root in [c for c in funcs.values() if c.isr]:
        st = [root]
        while st:
            c = st.pop()
            if c.name in seen:
                continue
            seen.add(c.name)
            if not c.common and c.name not in main_side and c.size:
                isr_order.append(c)
            st.extend(funcs[t] for t in sorted(c.calls, reverse=True) if t in funcs)
    isr_set = {id(c) for c in isr_order}
    log(f"ISR-only fns packed first: {len(isr_order)} ({sum(c.size for c in isr_order)} B)")
    units = [[c] for c in isr_order]
    for m in order:
        cs = [c for c in m.chunks if not c.common and c.size and id(c) not in isr_set]
        tot = sum(c.size for c in cs)
        if tot > cap - a.pack_margin:
            log(f"split {m.name} ({tot} B > bank {cap - a.pack_margin} B) at function granularity")
            units += [[c] for c in cs]
        elif cs:
            units.append(cs)
    fill = [0] * a.banks
    for u in units:                                          # first fit in call-graph order
        n = sum(c.size for c in u)
        b = next((i for i in range(a.banks) if fill[i] + n <= cap - a.pack_margin), None)
        if b is None:
            sys.exit(f"out of banks placing {u[0].module.name}:{u[0].name} ({n} B); fill={fill}")
        for c in u:
            c.bank = b
        fill[b] += n
    log("bank fill: " + ", ".join(f"{i}:{f}" for i, f in enumerate(fill) if f))
    for m in mods:
        for c in m.chunks:
            if c.common:
                c.bank = None
    # hot small helpers -> common with their banked callees: called from >= HOT_BANKS banks, closure <= HOT_SIZE B.
    # Saves 3 stack bytes + a bank switch per call level (fw_stack.py), and stubs. Budget --hot-budget.
    callers = defaultdict(set)
    for m in mods:
        for c in m.chunks:
            for t in c.calls:
                if t in funcs:
                    callers[t].add(c.bank)
    budget, moved = a.hot_budget, []
    changed = True
    while changed:
        changed = False
        def banked_closure(c):
            seen, st = {}, [c]
            while st:
                x = st.pop()
                if x.name in seen or x.common:
                    continue
                seen[x.name] = x
                st.extend(funcs[t] for t in x.calls if t in funcs)
            return list(seen.values())
        cand = []
        for c in funcs.values():
            if c.common or len(callers[c.name] - {c.bank}) < HOT_BANKS:
                continue
            cl = banked_closure(c)
            if sum(x.size for x in cl) <= HOT_SIZE:
                cand.append((c, cl))
        for c, cl in sorted(cand, key=lambda t: (-len(callers[t[0].name]), sum(x.size for x in t[1]))):
            cl = [x for x in cl if not x.common]
            n = sum(x.size for x in cl)
            if not cl or n > budget:
                continue
            for x in cl:
                fill[x.bank] -= x.size; x.common, x.bank = True, None; moved.append(x.name)
            budget -= n; changed = True
    log(f"hot helpers -> common: {len(moved)} ({a.hot_budget - budget} B): {', '.join(moved[:30])}")

    # CONST used from more than one bank (or from common / data initialisers) -> common;
    # used from exactly one other bank -> placed in that bank
    users = defaultdict(set)
    for m in mods:
        for c in m.chunks:
            if c.area != "CSEG":
                continue
            for r in c.refs:
                if r in consts:
                    users[r].add(c.bank)
    for m in mods:                                           # pointer in an xdata initialiser: any bank
        for l in m.head + m.tail:
            if re.match(r"^\s+\.(db|dw|byte|word)\b", l):
                for r in SYM.findall(l.split(";", 1)[0]):
                    if r in consts:
                        users[r].add(None)
    changed = True                                           # pointer tables: pointee used where the table is
    while changed:
        changed = False
        for t in consts.values():
            for r in t.refs:
                if r in consts and not users[t.name] <= users[r]:
                    users[r] |= users[t.name]; changed = True
    moved = 0
    for r, u in users.items():
        c = consts[r]
        if not u:
            continue                                         # unreferenced: stays with its module
        if len(u) > 1 or None in u:
            c.common, c.bank = True, None
        elif u != {c.bank}:
            c.bank = next(iter(u)); moved += 1
    log(f"common consts: {sum(c.common for c in consts.values())}; consts moved to user bank: {moved}")

    # stubs: cross-bank / common->banked calls and every address-taken banked fn. fn -> (module, bank)
    stubs = {}
    for m in mods:
        for c in m.chunks:
            for t in c.calls:
                if t in funcs and funcs[t].bank is not None and funcs[t].bank != c.bank:
                    stubs[t] = (funcs[t].module.name, funcs[t].bank)
            for r in c.refs:
                if r in funcs and funcs[r].bank is not None:
                    stubs[r] = (funcs[r].module.name, funcs[r].bank)
    extra = defaultdict(set)                                 # modules referencing another module's stub
    for m in mods:
        for c in m.chunks:
            for x in c.calls | c.refs:
                if x in stubs and stubs[x][0] != m.name:
                    extra[m.name].add(f"__bs{x}")
    log(f"stubs: {len(stubs)}")

    common_size, final = 0, [0] * a.banks
    for m in mods:
        p = out / f"{m.name}.asm"
        p.write_text(render(m, lambda c: c.area if c.bank is None else f"BANK{c.bank}", stubs, extra))
        sz = assemble(p)
        common_size += sz.get("CSEG", 0) + sz.get("CONST", 0)
        for k, v in sz.items():
            if k.startswith("BANK"):
                final[int(k[4:])] += v
    log("final bank sizes: " + ", ".join(f"{i}:{v}" for i, v in enumerate(final) if v))
    over = {i: v for i, v in enumerate(final) if v > cap}
    if over:
        sys.exit(f"bank overflow after CONST placement (cap {cap}): {over}; raise --pack-margin")
    log(f"common CSEG+CONST from modules: {common_size} B (limit {a.common_max})")
    if common_size > a.common_max:
        sys.exit("common area overflow")
    bank_of = {m.name: sorted({c.bank for c in m.chunks if c.bank is not None}) for m in mods}
    rep = {"banks": {i: f for i, f in enumerate(fill) if f}, "bank_of": bank_of, "stubs": len(stubs),
           "common_fns": sorted(n for n, c in funcs.items() if c.common), "common_bytes_modules": common_size,
           "common_consts": sorted(n for n, c in consts.items() if c.common)}
    (ROOT / "tmp/sdcc-port/bank.json").write_text(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
