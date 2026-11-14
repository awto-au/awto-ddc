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
  a stub `__bs_<fn>` emitted in the fn's own module (common): mov r0,#bank; mov dptr,#fn; ljmp __bs_call (8 B; R1-R7 and
  C untouched = Keil arguments/returns survive; scratch R0, A, B, DPTR; fw/sdcc/bank.asm).
- CONST moves to a user bank only if every ref is `mov dptr,#_t` in a chunk with no cross-bank call (#16).
- Fails on: CONST referenced from a bank it is not in (after the common rule), a module larger than a bank.
Log: tmp/logs/sdcc_bank.log, report tmp/sdcc-port/bank.json
"""
import argparse, json, os, re, shutil, subprocess, sys, time
import isostamp  # noqa: E402
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import sdcc_tools as T  # noqa: E402
import sdcc_layout as L  # noqa: E402
import sdcc_cluster as SC  # noqa: E402
import msg_table as MT  # noqa: E402

ROOT = repo_root()
LOG = None
FUNC_HDR = re.compile(r"^;\s+function (\w+)\s*$")
LABEL = re.compile(r"^(\w+)(::?)\s*$")
CALL = re.compile(r"^(\s+)(lcall|ljmp)(\s+)(\w+)\s*$")
SYM = re.compile(r"(?<![\w$])(_\w+)")
MOVC = re.compile(r"^\s+movc\s+a,\s*@a\+dptr")
SAVE = re.compile(r"^\s+(push\b|movx\s+@|mov\s+(a?r[0-7]|@r[01]),\s*(a|dpl|dph|b)\b)")
CALLJ = re.compile(r"^\s+(lcall|ljmp|acall)\s+(\w+)")
SCAN_MAX = 30             # lines from an address load to its consumer; longer = give up (stays common)
AR_EQU = re.compile(r"^\s*(ar[0-7]|rbank0)\s*=")
BANK_SIZE = 0x10000
MSG_RESERVE = {MT.MSG_BANK: MT.MSG_SIZE}   # top of one bank = fixed debug-message block (#56), never code
HOT_BANKS = 3             # helper called from at least this many other banks
HOT_SIZE = 384            # and its banked callee closure no larger than this
STUB_SIZE = 8             # mov r0,#bank; mov dptr,#target; ljmp __bs_call (2+3+3 B); R1-R7 untouched (Keil args)
ASM_TIMEOUT = 30          # one sdas8051 run: largest module assembles in < 2 s; stall = broken input


def log(s):
    line = f"{isostamp.now()} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def addr_stays_in_bank(code, i, c, funcs):
    """True if a CONST address loaded at code[i] is consumed by movc, or passed to a callee that reads
    in this bank (same-bank / library / common leaf). Saves to variables or registers escape (#16)."""
    if re.match(r"^\s+(mov\s+(a?r[0-7]|@r[01]),\s*#|\.(db|dw|byte|word)\b)", code[i]):
        return False
    for l in code[i + 1:i + 1 + SCAN_MAX]:
        if MOVC.match(l):
            return True
        m = CALLJ.match(l)
        if m:
            t = funcs.get(m.group(2))
            if t is None or t.bank == c.bank:
                return True
            if t.bank is None:                               # common callee: ok unless it calls a banked fn
                return not any(x in funcs and funcs[x].bank is not None for x in t.calls)
            return False
        if SAVE.match(l):
            return False
        if re.match(r"^\s+(ret|reti|sjmp|jmp)\b", l):
            return False
    return False


JMP = re.compile(r"^\s+(?:sjmp|ljmp|ajmp|djnz|jnz|jz|jc|jnc|jb|jnb|jbc|cjne)\b[^;]*?,?\s*(\d+\$)\s*(?:;.*)?$|"
                 r"^\s+(?:sjmp|ljmp|ajmp)\s+(\d+\$)\s*(?:;.*)?$")


def gptr_callee(code, i, funcs):
    """Callee that receives the CONST address loaded at code[i] (first call within SCAN_MAX; param stores in between
    are skipped) when it reads generic pointers (__gptrget): it reads in ITS bank, so the CONST must be common or there (#46)."""
    for l in code[i + 1:i + 1 + SCAN_MAX]:
        m = CALLJ.match(l)
        if m:
            t = funcs.get(m.group(2))
            return t if t is not None and t.gptr else None
        if re.match(r"^\s+(ret|reti|sjmp|ljmp|jmp)\b", l):
            return None
    return None


def call_sites(lines):
    """(callee, loop depth) per lcall/ljmp-to-function in a chunk. Loop = span from a local label (`00101$`) to a later
    jump back to it; depth at a site = number of spans containing it (asm has no loop info; this is the static proxy)."""
    lab, spans = {}, []
    for i, l in enumerate(lines):
        m = re.match(r"^(\d+\$):", l)
        if m:
            lab[m.group(1)] = i
        j = JMP.match(l.split(";", 1)[0])
        if j:
            t = j.group(1) or j.group(2)
            if t in lab:
                spans.append((lab[t], i))
    out = []
    for i, l in enumerate(lines):
        c = CALL.match(l.split(";", 1)[0]) if not l.startswith(";") else None
        if c:
            out.append((c.group(4), sum(a <= i <= b for a, b in spans)))
    return out


STACKREAD = re.compile(r"^\s+mov\s+(a|ar[0-7]|r[0-7]|dpl|dph|b),\s*sp\b|^\s+mov\s+_bp,\s*sp\b|\b_bp\b")


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
        # reads its stack-passed args via SP/_bp: a banked call goes through a stub that leaves 4 more bytes
        # between args and callee (caller ret + restore entry), so the offsets are wrong (#11)
        self.stack_args = any(STACKREAD.search(l.split(";", 1)[0]) for l in lines)
        self.gptr = any(re.match(r"^\s+[la]call\s+__gptrget", l) for l in lines)   # reads a generic (code) pointer in ITS bank
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
        self.sites = call_sites(lines)                       # [(target, loop depth)], for --cluster


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


def render(mod, area_of, stubs_needed, extra_globl, stub_area=lambda f: "CSEG"):
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
    for f in stubs:
        out += [f"\t.area {stub_area(f)}    (CODE)", f"\t.globl __bs{f}", f"__bs{f}:", f"\tmov\tr0,#({f} >> 16)",
                f"\tmov\tdptr,#{f}", "\tljmp\t__bs_call"]
    out.extend(mod.tail)
    return "\n".join(out)


def load_weights(path, funcs):
    """{(caller, callee): calls/pass}; names cut at 32 chars by the map resolve by unique prefix."""
    def full(n):
        if n in funcs:
            return n
        m = [f for f in funcs if f.startswith(n)]
        return m[0] if len(m) == 1 else None
    out = {}
    for k, v in json.loads(Path(path).read_text())["edges"].items():
        a, b = (full(x) for x in k.split())
        if a and b:
            out[(a, b)] = out.get((a, b), 0) + v
    log(f"cluster weights {path}: {len(out)} edges, {sum(out.values()):.1f} calls/pass")
    return out


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
    ap.add_argument("--cluster", choices=["module", "fn"], default="",
                    help="call-graph-aware placement (sdcc_cluster.py): merge units with heavy call edges into one bank so "
                         "calls need no stub; module = module granularity, fn = per function. Default: DFS first fit")
    ap.add_argument("--cluster-weights", default="", help="JSON {edges: {'caller callee': calls/pass}} from fw_profile: "
                    "measured call counts added to the --cluster edge weights (sdcc_cluster.DYN_W each)")
    ap.add_argument("--pin-common", default="", help="comma list of fns forced into common (small ISR-called handlers: "
                    "the ISR -> banked call needs a stub otherwise); counted against nothing, common must fit")
    ap.add_argument("--keep-dead", action="store_true", help="keep chunks unreachable from main/ISRs")
    ap.add_argument("--layout", default="", help="sticky layout file (fw/bank_layout.tsv): fixed slot per chunk, reused "
                    "between builds; missing/empty file = create from the packing below (sdcc_layout.py)")
    ap.add_argument("--layout-out", default=str(ROOT / "tmp/sdcc-port/bank_layout.new.tsv"),
                    help="where the (possibly updated) layout is written; the caller promotes it onto --layout only after "
                         "link + layout check pass (#51.4). --layout itself is never written here")
    ap.add_argument("--fill-target", type=float, default=0.80,
                    help="layout creation: per-bank fill limit (fraction of the bank, slot pads included); "
                         "raised in 1%% steps only until everything fits")
    ap.add_argument("--resid-end", type=lambda x: int(x, 0), default=0x0C00,
                    help="layout: common bytes [0, this) kept for vectors/HOME/GSINIT/library/XINIT; chunk slots follow")
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
        if c.isr or c.name == "_main" or c.stack_args:       # stack_args: callable only by direct lcall (#11)
            c.common = True
    for n in filter(None, a.pin_common.split(",")):
        if n not in funcs:
            sys.exit(f"--pin-common: no function {n}")
        funcs[n].common = True
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
    sticky = bool(a.layout)
    lay = L.Layout.load(a.layout) if sticky else L.Layout()
    reuse = sticky and bool(lay.rows)                        # existing layout: placement comes from it
    if a.cluster and not (sticky and not reuse):             # #51.6: it only acts while a layout is created
        sys.exit("--cluster is ignored unless a layout is being created (--layout FILE missing or empty); refusing")
    if reuse:
        lay.check_header(a.common_max, a.resid_end, a.layout)   # #51.3
    fill = [0] * a.banks

    def first_fit(limit, sizeof, split=False):
        fl = [0] * a.banks
        todo = list(units)
        while todo:                                          # first fit in call-graph order
            u = todo.pop(0)
            n = sum(sizeof(c) for c in u)
            b = next((i for i in range(a.banks) if fl[i] + n <= limit), None)
            if b is None and split and len(u) > 1:           # layout creation: a unit that fits nowhere is split per fn
                todo = [[c] for c in u] + todo
                continue
            if b is None:
                return None, (u, n, fl)
            for c in u:
                c.bank = b
            fl[b] += n
        return fl, None

    allc = [c for m in mods for c in m.chunks if c.area == "CSEG"]
    dyn = load_weights(a.cluster_weights, funcs) if a.cluster_weights else None
    if reuse:
        slot_fill = defaultdict(int)
        for (k, nm), (rg, off, sl) in lay.rows.items():
            slot_fill[rg] += sl
        by_mod = defaultdict(lambda: defaultdict(int))       # module -> bank -> bytes already placed there
        for m in mods:
            for c in m.chunks:
                row = lay.rows.get(("fn" if c.area == "CSEG" else "const", c.name))
                if row and row[0] != "C" and c.size:
                    by_mod[m.name][row[0]] += c.size
        newc = []
        for m in mods:
            for c in m.chunks:
                if c.common or not c.size:
                    continue
                row = lay.rows.get(("fn" if c.area == "CSEG" else "const", c.name))
                if row and row[0] == "C":
                    c.common = True
                elif row:
                    c.bank = row[0]
                else:                                        # new chunk: bank where its module already lives
                    mb = by_mod[m.name]
                    c.bank = max(mb, key=lambda b: (mb[b], -b)) if mb else min(range(a.banks), key=lambda b: slot_fill[b])
                    slot_fill[c.bank] += L.pad_slot(c.size)
                    newc.append(c.name)
        log(f"sticky layout {a.layout}: {len(lay.rows)} rows, {len(newc)} new chunks: {', '.join(sorted(newc)[:20])}")
    elif sticky:
        f = a.fill_target
        while True:
            fill, fail = first_fit(int(cap * f), lambda c: L.pad_slot(c.size))
            if fill is not None and a.cluster:               # clustered at creation only; reuse keeps the sticky rows
                log(f"cross-bank calls, first-fit packing: {SC.stats(allc, funcs)}")
                keep = {id(c): c.bank for m in mods for c in m.chunks}
                cu = units if a.cluster == "module" else [[c] for u in units for c in u]
                f2 = SC.assign(cu, funcs, a.banks, int(cap * f), lambda c: L.pad_slot(c.size), consts, dyn)
                if f2 is None:
                    log(f"cluster: does not fit at fill {f:.2f}")
                    for m in mods:
                        for c in m.chunks:
                            c.bank = keep[id(c)]
                    fill = None
                else:
                    fill = f2
                    log(f"cluster[{a.cluster}]: {SC.stats(allc, funcs)}")
            if fill is not None:
                break
            f += 0.01
            if f > 1.0:
                u, n, fl = fail
                sys.exit(f"out of banks placing {u[0].module.name}:{u[0].name} ({n} B); fill={fl}")
        log(f"layout creation: per-bank fill limit {f:.2f} of {cap} B (slot pads included; target {a.fill_target})")
    else:
        fill, fail = first_fit(cap - a.pack_margin, lambda c: c.size)
        if fill is None:
            u, n, fl = fail
            sys.exit(f"out of banks placing {u[0].module.name}:{u[0].name} ({n} B); fill={fl}")
    log("bank fill: " + ", ".join(f"{i}:{f}" for i, f in enumerate(fill) if f))
    for m in mods:
        for c in m.chunks:
            if c.common:
                c.bank = None
    def slot_items(fixed_consts):
        its = []
        for m in mods:
            for c in m.chunks:
                if c.size:
                    kind = "fn" if c.area == "CSEG" else "const"
                    it = L.Item(kind, c.name, c.size, "C" if c.bank is None else c.bank, m.name)
                    it.fixed = fixed_consts and kind == "const"
                    its.append(it)
        return its

    def apply_placed(placed):
        lay.rows = {k: v for k, v in placed.items()}

    if reuse:                                                # pass A: re-home fns whose bank has no room left
        its = slot_items(True)
        for (kind, nm) in [k for k in lay.rows if k[0] == "stub"]:        # keep stub slots reserved
            st = L.Item("stub", nm, STUB_SIZE, "C", "", slot=STUB_SIZE)
            st.fixed = True
            its.append(st)
        placed, rehomed = L.assign(its, lay, a.resid_end, a.common_max, a.banks, cap, log, reserve=MSG_RESERVE)
        for (kind, name), rid in rehomed.items():
            if kind == "fn" and rid != "C":
                funcs[name].bank = rid
        log(f"pass A: fns re-homed to another bank: {sorted(n for (k, n) in rehomed if k == 'fn')}")
        apply_placed(placed)                                 # stub rows stay: their slots are what keeps common stable
    # (a sticky layout already holds this decision: hot helpers are its common fn rows)
    # hot small helpers -> common with their banked callees: called from >= HOT_BANKS banks, closure <= HOT_SIZE B.
    # Saves 3 stack bytes + a bank switch per call level (fw_stack.py), and stubs. Budget --hot-budget.
    callers = defaultdict(set)
    for m in mods:
        for c in m.chunks:
            for t in c.calls:
                if t in funcs:
                    callers[t].add(c.bank)
    budget, moved = a.hot_budget, []
    changed = not reuse
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
    log(f"cross-bank calls after hot helpers: {SC.stats(allc, funcs)}")
    log(f"hot helpers -> common: {len(moved)} ({a.hot_budget - budget} B): {', '.join(moved[:30])}")

    # CONST used from more than one bank (or from common / data initialisers) -> common;
    # used from exactly one other bank -> placed in that bank
    users = defaultdict(set)
    escaping = set()                                         # address may reach another bank (#16)
    gptr_x = {}                                              # CONST -> (caller, gptr-reading callee in another bank) (#46)
    for m in mods:
        for c in m.chunks:
            if c.area != "CSEG":
                continue
            code = [l.split(";", 1)[0] for l in c.lines]
            for i, l in enumerate(code):
                rs = [r for r in SYM.findall(l) if r in consts]
                if rs and not addr_stays_in_bank(code, i, c, funcs):
                    escaping.update(rs)
                if rs:
                    t = gptr_callee(code, i, funcs)
                    if t is not None and not t.common and t.bank != c.bank:
                        for r in rs:
                            gptr_x[r] = (c.name, t.name)
            for r in c.refs:
                if r in consts:
                    users[r].add(c.bank)
    for t in consts.values():                                # pointer tables hand out their targets
        escaping.update(r for r in t.refs if r in consts)
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
    moved, stopped, stay_escape = 0, [], []
    for r, u in users.items():
        c = consts[r]
        if not u:
            continue                                         # unreferenced: stays with its module
        if len(u) > 1 or None in u or r in gptr_x:
            c.common, c.bank = True, None
            if r in gptr_x and len(u) <= 1 and None not in u:
                log(f"const {r} -> common: passed by {gptr_x[r][0]} to gptr reader {gptr_x[r][1]} in another bank (#46)")
        elif u != {c.bank}:
            if r in escaping:
                c.common, c.bank = True, None; stopped.append(r)
            else:
                c.bank = next(iter(u)); moved += 1
        elif r in escaping:
            stay_escape.append(r)
    log(f"common consts: {sum(c.common for c in consts.values())}; consts moved to user bank: {moved}; "
        f"kept common (address escapes, #16): {len(stopped)}: {', '.join(sorted(stopped))}")
    log(f"in own bank, address escapes (not moved, unchanged): {len(stay_escape)}: {', '.join(sorted(stay_escape))}")

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

    aname, bases, stub_slot = {}, {}, {}
    if sticky:                                               # pass B: every slot (chunks, consts, stubs), no re-homing
        its = slot_items(True)
        for it in its:
            it.fixed = True
        for f_, (mn, bk) in sorted(stubs.items()):
            st = L.Item("stub", f_, STUB_SIZE, "C", mn, slot=STUB_SIZE)
            st.fixed = True
            its.append(st)
        placed, _ = L.assign(its, lay, a.resid_end, a.common_max, a.banks, cap, log, reserve=MSG_RESERVE)
        apply_placed(placed)
        placed_slot = {("ST" if k[0] == "stub" else "CH") + k[1]: v[2] for k, v in placed.items()}
        lay.header.update({"common": hex(a.common_max), "resid_end": hex(a.resid_end), "slot_pad": "size+4+size/32,4B"})
        for (kind, name), (rid, off, sl) in placed.items():
            an = ("ST" if kind == "stub" else "CH") + name
            aname[(kind, name)] = an
            bases[an] = off if rid == "C" else rid * BANK_SIZE + a.common_max + off
        st_ = L.stats(placed, a.banks, a.resid_end, a.common_max, cap, MSG_RESERVE)
        log("slot fill (used/capacity): " + ", ".join(f"{k}:{u}/{c}" for k, (u, c) in st_.items() if u))
        (ROOT / "tmp/sdcc-port/area_bases.json").write_text(json.dumps(
            {"areas": bases, "banks": sorted({r for r, _, _ in placed.values() if r != "C"}),
             "slots": {an: placed[k][2] for k, an in aname.items()}}, indent=0))

    def area_of(c):
        if sticky and c.size:
            return aname[("fn" if c.area == "CSEG" else "const", c.name)]
        return c.area if c.bank is None else f"BANK{c.bank}"

    common_size, final = 0, [0] * a.banks
    for m in mods:
        p = out / f"{m.name}.asm"
        p.write_text(render(m, area_of, stubs, extra, (lambda f_: aname[("stub", f_)]) if sticky else (lambda f_: "CSEG")))
        sz = assemble(p)
        common_size += sz.get("CSEG", 0) + sz.get("CONST", 0)
        for k, v in sz.items():
            if k.startswith("BANK"):
                final[int(k[4:])] += v
            elif sticky and (k.startswith("CH") or k.startswith("ST")):
                if v > (STUB_SIZE if k.startswith("ST") else placed_slot[k]):
                    sys.exit(f"slot overflow: area {k} is {v} B")
    log("final bank sizes: " + ", ".join(f"{i}:{v}" for i, v in enumerate(final) if v))
    over = {i: v for i, v in enumerate(final) if v > cap}
    if over:
        sys.exit(f"bank overflow after CONST placement (cap {cap}): {over}; raise --pack-margin")
    log(f"common CSEG+CONST from modules: {common_size} B (limit {a.common_max})")
    if common_size > a.common_max:
        sys.exit("common area overflow")
    if sticky:
        Path(a.layout_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.layout_out).write_text(lay.text())
        log(f"layout written: {a.layout_out} ({len(lay.rows)} rows; not yet promoted onto {a.layout})")
    bank_of = {m.name: sorted({c.bank for c in m.chunks if c.bank is not None}) for m in mods}
    rep = {"banks": {i: f for i, f in enumerate(fill) if f}, "bank_of": bank_of, "stubs": len(stubs),
           "common_fns": sorted(n for n, c in funcs.items() if c.common), "common_bytes_modules": common_size,
           "common_consts": sorted(n for n, c in consts.items() if c.common)}
    (ROOT / "tmp/sdcc-port").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/sdcc-port/bank.json").write_text(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
