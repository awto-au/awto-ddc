#!/usr/bin/env python3
"""Keil-BL51-style RAM overlay for SDCC mcs51 asm: functions that are never live together share local storage.

usage: sdcc_overlay.py [--asm DIR] [--out DIR] [--xdata] [--xparms] [--xlimit N] [--dlimit N]
  --xdata overlay XDATA locals too (default: DATA spill slots only)
  --xparms overlay XDATA _PARM_ slots (memory-passed args) by the same call graph, locals stay static (plan C8, #11)
  --asm   SDCC -S output tree (default tmp/sdcc-port/asm)
  --out   rewritten tree + __ovl.asm (default tmp/sdcc-port/asm_ovl)
  --xlimit / --dlimit  fail if total XDATA / DATA after overlay exceeds this (bytes; default 8192 / 0 = no check)

Method (awto-ddc#8):
- Per function: XSEG locals (`_fn_var_L_N`) and DSEG/XSEG spill slots (`_fn_slocK_*`) form its frame.
  PARMs (DATA/BIT, XDATA with --xparms) are part of the callee's frame. Sibling risk: a caller writes g's PARM, then
  calls another fn before `lcall g` (its frame may sit on g's slots): such g keep private PARMs (scan per call site).
- Call graph from `lcall/ljmp/acall/ajmp _fn`. Regions: main tree, each ISR (fn with `reti`), each
  address-taken fn (indirect call target). Frame offset = max(caller offset + caller frame) within a region.
- Kept static (own storage): fns reachable from more than one region, fns in call cycles, unattributed labels.
- Rewrite: storage lines removed; every use becomes `(__xovl + off)` / `(__dovl + off)`; __ovl.asm reserves blocks.
Log: tmp/logs/sdcc_overlay.log, report tmp/sdcc-port/overlay.json
"""
import json, os, re, shutil, subprocess, sys, time
from collections import defaultdict
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
LOG = None
MEM = {"XSEG": "x", "DSEG": "d", "BSEG": "b"}       # overlaid areas -> block (__xovl / __dovl / __bovl bits)
BLOCK = {"x": "__xovl", "d": "__dovl", "b": "__bovl"}
MEMS = tuple(BLOCK)
ZERO = lambda: {m: 0 for m in MEMS}
# PARMs share the callee frame: SDCC evaluates all nested-call args into caller temps first, then writes the
# callee's PARMs back-to-back right before its lcall (verified in fw/simtests/siblings_args asm, #10).
# Default: overlay only DATA spill slots (952 B can never fit 256 B IRAM). XDATA fits without it after the
# storage-first + MST/TX fixes (5.7 KB vs ~6.5 KB free), so XDATA overlay is opt-in (--xdata), #8.
OVERLAY_XDATA = "--xdata" in sys.argv
OVERLAY_XPARMS = "--xparms" in sys.argv
PARM_REF = re.compile(r"\b(_\w+?)_PARM_\d+\b")
CALL = re.compile(r"^\s+(?:lcall|ljmp|acall|ajmp)\s+(\w+)\s*$")
FUNC_HDR = re.compile(r"^;\s+function (\w+)\s*$")


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


class Module:
    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text(errors="replace").split("\n")
        self.funcs = {}          # asm label -> {'global': bool, 'calls': set, 'isr': bool}
        self.storage = []        # (line_idx_label, line_idx_ds, label, area, size)
        self.refs = set()        # symbols used outside call position (address-taken candidates)
        self.alloc = {}          # storage label -> (fn asm label, C var name), from SDCC allocation comments
        self.src = None          # C source path (from SDCC line comments)
        self.parm_hazard = []    # (g, X): a PARM of g written, then X called before g (sibling overlap risk)
        self.parse()

    def parse(self):
        area, cur, pending, alloc_fn, pend = None, None, None, None, set()
        globl = set(re.findall(r"^\s+\.globl\s+(\w+)", "\n".join(self.lines), re.M))   # SDCC fns: `_f:` + .globl
        for i, line in enumerate(self.lines):
            if line.startswith("\t.area"):
                area = line.split()[1]
                continue
            am = re.match(r"^;Allocation info for local variables in function '(\w+)'", line)
            if am:
                alloc_fn = "_" + am.group(1)
                continue
            am = re.match(r"^;(\w+)\s+Allocated with name '(\w+)'", line)
            if am and alloc_fn:
                self.alloc[am.group(2)] = (alloc_fn, am.group(1))
                continue
            if self.src is None:
                sm = re.match(r"^;\s+(/\S+\.c):\d+:", line)
                if sm:
                    self.src = sm.group(1)
            m = FUNC_HDR.match(line)
            if m:
                pending = "_" + m.group(1)
                continue
            lab = re.match(r"^(\w+)(::?)$", line)
            if lab and area == "CSEG" and lab.group(1) == pending:
                cur = pending
                self.funcs[cur] = {"global": lab.group(2) == "::" or cur in globl, "calls": set(), "isr": False}
                pending, pend = None, set()
                continue
            if lab and area in MEM and i + 1 < len(self.lines) and self.lines[i + 1].strip().startswith(".ds"):
                if lab.group(2) == ":":                       # module-local storage only
                    self.storage.append((i, i + 1, lab.group(1), area, int(self.lines[i + 1].split()[1], 0)))
                continue
            if area == "CSEG" and cur and not line.lstrip().startswith(";"):
                c = CALL.match(line)
                if c:
                    self.parm_hazard += [(g, c.group(1)) for g in pend if g != c.group(1)]
                    pend.discard(c.group(1))
                else:
                    pend.update(g for g in PARM_REF.findall(line) if g != cur)
                c = CALL.match(line)
                if c and c.group(1) == "sdcc_atomic_maybe_rollback":
                    self.funcs[cur]["isr"] = True                   # ISR epilogue, not a call
                    continue
                if c:
                    self.funcs[cur]["calls"].add(c.group(1))
                    continue
                # SDCC 4.5 ISRs may end with `ljmp sdcc_atomic_maybe_rollback` instead of reti
                if re.match(r"^\s+(reti\b|ljmp\s+sdcc_atomic_maybe_rollback\b)", line):
                    self.funcs[cur]["isr"] = True
            if not line.lstrip().startswith(";"):
                for s in re.findall(r"#\(?[<>]?\(?(_\w+)", line):   # #_f, #(_f + 1), #<_f, #>_f
                    self.refs.add(s)
                if re.match(r"^\s+\.(dw|db|byte|word)\b", line):
                    self.refs.update(re.findall(r"\b(_\w+)\b", line))

    def owner(self, label):
        """(fn, var) owning this storage label. SDCC allocation comments first; bit vars are not listed there,
        so fall back to strict SDCC naming (`_fn_PARM_n` / `_fn_var_L_N`) disambiguated by the C body.
        None = not a fn local (file-scope statics) or ambiguous -> never overlaid."""
        if label in self.alloc:
            return self.alloc[label]
        cands = []
        for f in self.funcs:
            if not label.startswith(f + "_"):
                continue
            rest = label[len(f) + 1:]
            if re.fullmatch(r"PARM_\d+", rest):
                cands.append((f, rest, True))
            else:
                m = re.fullmatch(r"(\w+?)_\d+_\d+", rest)
                if m:
                    cands.append((f, m.group(1), False))
        exact = [c for c in cands if c[2]]
        if len(exact) == 1:
            return exact[0][:2]
        if len(cands) > 1:
            for c in cands:
                self.is_local_static(c[0], c[1])            # side effect: loads that fn's C body
            cands = [c for c in cands if self._csrc and
                     re.search(r"\b" + re.escape(c[1]) + r"\b", self._bodies.get(c[0], ""))]
        return cands[0][:2] if len(cands) == 1 else None

    _bodies = None

    def is_local_static(self, fn, var):
        """True if `var` is declared `static` inside fn's C body (persists across calls: never overlay).
        Unknown source -> True (safe)."""
        if self._bodies is None:
            self._bodies = {}
            try:
                self._csrc = Path(self.src).read_text(errors="replace") if self.src else None
            except OSError:
                self._csrc = None
        if self._csrc is None:
            return True
        if fn not in self._bodies:
            m = re.search(r"\b" + re.escape(fn[1:]) + r"\s*\([^;{]*\)[^;{]*\{", self._csrc)
            body = ""
            if m:
                depth, j = 0, m.end() - 1
                for j in range(m.end() - 1, len(self._csrc)):
                    depth += {"{": 1, "}": -1}.get(self._csrc[j], 0)
                    if depth == 0:
                        break
                body = self._csrc[m.end():j]
            self._bodies[fn] = body
        return re.search(r"\bstatic\b[^;{}]*\b" + re.escape(var) + r"\b", self._bodies[fn]) is not None


def main():
    global LOG
    a = sys.argv[1:]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    asm_dir = Path(opt("--asm", ROOT / "tmp/sdcc-port/asm"))
    out_dir = Path(opt("--out", ROOT / "tmp/sdcc-port/asm_ovl"))
    xlimit, dlimit = int(opt("--xlimit", 8192)), int(opt("--dlimit", 0))
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdcc_overlay.log").open("a")

    mods = [Module(p) for p in sorted(asm_dir.rglob("*.asm"))]
    log(f"{len(mods)} modules from {asm_dir}")

    # ---- graph: node = (module_idx or None for global, label)
    globals_ = {}
    for mi, m in enumerate(mods):
        for f, info in m.funcs.items():
            if info["global"]:
                globals_[f] = (mi, f)

    def resolve(mi, name):
        if name in mods[mi].funcs:
            return (mi, name)
        return globals_.get(name)
    nodes = {(mi, f): info for mi, m in enumerate(mods) for f, info in m.funcs.items()}
    calls = {n: {t for t in (resolve(n[0], c) for c in info["calls"]) if t} for n, info in nodes.items()}
    addr_taken = set()
    for mi, m in enumerate(mods):
        for s in m.refs:
            t = resolve(mi, s)
            if t:
                addr_taken.add(t)
    # an indirect call site (SDCC helper) may reach any address-taken fn: conservative edges, like a
    # BL51 OVERLAY directive covering all pointer targets
    # helper name: __sdcc_call_dptr (<= 4.6) / sdcc_call_dptr (trunk); missing it makes every target a root
    indirect_sites = [n for n, info in nodes.items() if info["calls"] & {"__sdcc_call_dptr", "sdcc_call_dptr"}]
    for n in indirect_sites:
        calls[n] |= addr_taken

    # ---- frames
    frame = defaultdict(ZERO)
    syms = defaultdict(list)       # node -> [(mi, label, mem, size, rel_off)]
    static_bytes = {"x": 0, "d": 0, "b": 0, "parm_x": 0, "unowned": 0, "local_static": 0}
    for mi, m in enumerate(mods):
        for li, ld, label, area, size in m.storage:
            mem = MEM[area]
            if mem == "x" and not (OVERLAY_XDATA or OVERLAY_XPARMS and "_PARM_" in label and not label.startswith("__")):
                continue                                    # XDATA locals stay; so do PARMs of `__` support routines (library callers write them)
            own = m.owner(label)
            if own is None or own[0] not in m.funcs:
                static_bytes["unowned"] += size
                continue
            fn, var = own
            if "_PARM_" in label:
                static_bytes["parm_x" if mem == "x" else mem] += size   # counted, and overlaid with the frame
            if "_PARM_" not in label and "sloc" not in label and m.is_local_static(fn, var):
                static_bytes["local_static"] += size
                continue
            n = (mi, fn)
            syms[n].append((mi, label, mem, size, frame[n][mem]))
            frame[n][mem] += size

    # ---- regions
    roots = []
    mainn = globals_.get("_main")
    if mainn:
        roots.append(("main", mainn))
    roots += [(f"isr:{n[1]}", n) for n, info in nodes.items() if info["isr"]]
    # address-taken fns are separate roots only if nothing calls through a pointer (else reached via edges)
    if not indirect_sites:
        roots += [(f"ind:{n[1]}", n) for n in sorted(addr_taken) if not nodes[n]["isr"]]

    def reach(r):
        seen, st = set(), [r]
        while st:
            n = st.pop()
            if n in seen:
                continue
            seen.add(n)
            st.extend(calls.get(n, ()))
        return seen
    region_of = defaultdict(set)
    reaches = {}
    for name, r in roots:
        reaches[name] = reach(r)
        for n in reaches[name]:
            region_of[n].add(name)
    shared = {n for n, rs in region_of.items() if len(rs) > 1}

    # cycles (Tarjan, iterative) -> SCC ids; cyclic fns keep private storage
    comp_of, cyc = {}, set()
    idx, low, onst, st, counter = {}, {}, set(), [], 0
    for v0 in nodes:
        if v0 in idx:
            continue
        work = [(v0, iter(sorted(calls.get(v0, ()))))]
        idx[v0] = low[v0] = counter; counter += 1; st.append(v0); onst.add(v0)
        while work:
            v, it = work[-1]
            w = next(it, None)
            if w is not None:
                if w not in idx:
                    idx[w] = low[w] = counter; counter += 1; st.append(w); onst.add(w)
                    work.append((w, iter(sorted(calls.get(w, ())))))
                elif w in onst:
                    low[v] = min(low[v], idx[w])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == idx[v]:
                comp = []
                while True:
                    w = st.pop(); onst.discard(w); comp.append(w)
                    if w == v:
                        break
                for w in comp:
                    comp_of[w] = v
                if len(comp) > 1 or v in calls.get(v, ()):
                    cyc.update(comp)
    # PARM written, then another tree fn called before the owner's lcall: owner keeps private storage
    hazard = set()
    for mi, m in enumerate(mods):
        for g, x in m.parm_hazard:
            gn, xn = resolve(mi, g), resolve(mi, x)
            if gn and xn:
                hazard.add(gn)
    keep_static = shared | cyc | hazard

    # offsets per region on the SCC-condensed DAG. Private-storage nodes (cyclic/shared) still pass
    # offsets through with frame 0, so callees reached via them never land on a live caller's frame.
    place = {}                         # node -> (region, {'x': off, 'd': off})
    region_size = {}
    for name, r in roots:
        reach_set = reaches[name]
        cnodes = {comp_of[n] for n in reach_set}
        cmembers = defaultdict(list)
        for n in reach_set:
            cmembers[comp_of[n]].append(n)
        cedges = defaultdict(set)
        for n in reach_set:
            for t in calls.get(n, ()):
                if t in reach_set and comp_of[t] != comp_of[n]:
                    cedges[comp_of[n]].add(comp_of[t])
        cframe = {c: {mem: (0 if any(n in keep_static for n in cmembers[c]) else
                            sum(frame[n][mem] for n in cmembers[c])) for mem in MEMS} for c in cnodes}
        off = {c: ZERO() for c in cnodes}
        indeg = defaultdict(int)
        for c in cnodes:
            for t in cedges[c]:
                indeg[t] += 1
        q = [c for c in cnodes if indeg[c] == 0]
        while q:
            c = q.pop()
            for t in cedges[c]:
                for mem in MEMS:
                    off[t][mem] = max(off[t][mem], off[c][mem] + cframe[c][mem])
                indeg[t] -= 1
                if indeg[t] == 0:
                    q.append(t)
        region_size[name] = {mem: max([off[c][mem] + cframe[c][mem] for c in cnodes] or [0]) for mem in MEMS}
        for c in cnodes:
            for n in cmembers[c]:
                if n not in keep_static:          # non-cyclic SCC = single node
                    place[n] = (name, off[c])

    # dead fns (no root, ISR or address-taken fn reaches them: callers configured out) never run -> offset 0
    dead = [n for n in nodes if n not in region_of and n not in place and any(frame[n].values())]
    if mainn:
        for n in dead:
            place[n] = ("main", ZERO())
    # XDATA/BIT: one block, regions back to back. DATA: one area per region (+ one for static frames) so
    # sdld can fit each into a hole around the bit-addressable bytes (0x20-0x2F), #8
    base, cursor = {}, ZERO()
    dblock, dsize = {}, {}
    for i, (name, _) in enumerate(roots):
        base[name] = dict(cursor); base[name]["d"] = 0
        dblock[name] = f"__dovl{i}"; dsize[dblock[name]] = region_size[name]["d"]
        for mem in ("x", "b"):
            cursor[mem] += region_size[name][mem]
    dsize["__dovls"] = 0
    # static frames (shared/cyclic) get their own slots after all regions
    for n in nodes:
        if n not in place and any(frame[n][mem] for mem in MEMS):
            place[n] = ("static", {mem: 0 for mem in MEMS})
            base.setdefault(("static", n), dict(cursor)); base[("static", n)]["d"] = dsize["__dovls"]
            dsize["__dovls"] += frame[n]["d"]
            for mem in ("x", "b"):
                cursor[mem] += frame[n][mem]
    cursor["d"] = sum(dsize.values())
    dsize = {k: v for k, v in dsize.items() if v}

    # ---- rewrite
    if out_dir.exists() and out_dir.resolve() != asm_dir.resolve():
        shutil.rmtree(out_dir)          # derived; stale modules from earlier selections got linked (#18)
    out_dir.mkdir(parents=True, exist_ok=True)
    sub = defaultdict(dict)            # mi -> {label: expr} (module-local symbols)
    gsub = {}                          # global overlaid symbols (PARMs: callers in other modules write them)
    for n, entries in syms.items():
        region, off = place[n]
        b = base[("static", n)] if region == "static" else base[region]
        for mi, label, mem, size, rel in entries:
            blk = BLOCK[mem] if mem != "d" else ("__dovls" if region == "static" else dblock[region])
            expr = f"({blk} + 0x{b[mem] + off[mem] + rel:X})"
            sub[mi][label] = expr
            if "_PARM_" in label:
                gsub[label] = expr
    for mi, m in enumerate(mods):
        lines = list(m.lines)
        drop = set()
        for li, ld, label, area, size in m.storage:
            if label in sub[mi]:
                drop.update((li, ld))
        table = dict(gsub); table.update(sub[mi])
        rx = re.compile(r"\b(" + "|".join(map(re.escape, table)) + r")\b") if table else None
        new, used = [], False
        for i, line in enumerate(lines):
            if i in drop:
                continue
            g = re.match(r"^\s+\.globl\s+(\w+)\s*$", line)
            if g and g.group(1) in gsub:
                continue                                    # symbol no longer exists
            if rx and not line.lstrip().startswith(";"):
                line2 = rx.sub(lambda mm: table[mm.group(1)], line)
                used |= line2 != line
                line = line2
            new.append(line)
        if used:
            new.insert(1, "\n".join(f"\t.globl {b}" for b in [BLOCK["x"], BLOCK["b"], *dsize]))
        dst = out_dir / m.path.relative_to(asm_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("\n".join(new))
    (out_dir / "__ovl.asm").write_text(
        "\t.module __ovl\n" + "".join(f"\t.globl {b}\n" for b in [BLOCK["x"], BLOCK["b"], *dsize]) +
        f"\t.area XSEG (XDATA)\n__xovl::\n\t.ds 0x{max(cursor['x'], 1):X}\n" +
        "".join(f"\t.area D{k[2:].upper()} (DATA)\n{k}::\n\t.ds 0x{v:X}\n" for k, v in dsize.items()) +
        f"\t.area BSEG (BIT)\n__bovl::\n\t.ds 0x{max(cursor['b'], 1):X}\n")

    before = {mem: sum(f[mem] for f in frame.values()) for mem in MEMS}
    rep = {"modules": len(mods), "functions": len(nodes), "roots": len(roots),
           "isr": sum(1 for _, n in roots if nodes[n]["isr"]), "addr_taken": len(addr_taken),
           "kept_static_fns": len(keep_static), "cyclic_fns": len(cyc), "shared_fns": len(shared),
           "parm_hazard_fns": sorted(n[1] for n in hazard),
           "frames_before": before, "overlay_block": cursor, "static_parm_x": static_bytes["parm_x"],
           "local_static": static_bytes["local_static"],
           "private_frames": sorted(((n[1], dict(frame[n])) for n in nodes
                                     if place.get(n, ("",))[0] == "static" and any(frame[n].values())),
                                    key=lambda kv: -kv[1]["d"]),
           "unowned_storage": static_bytes["unowned"],
           "dead_frames": sorted(((n[1], dict(frame[n])) for n in dead), key=lambda kv: -kv[1]["d"]),
           "data_blocks": dsize,
           "main_region": region_size.get("main"),
           "largest_regions": sorted(((k, v) for k, v in region_size.items()), key=lambda kv: -kv[1]["x"])[:8]}
    (ROOT / "tmp/sdcc-port").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/sdcc-port/overlay.json").write_text(json.dumps(rep, indent=1, default=str))
    log(f"indirect call sites {len(indirect_sites)}")
    log(f"functions {len(nodes)}, roots {len(roots)} (isr {rep['isr']}, address-taken {len(addr_taken)}), "
        f"kept static {len(keep_static)} (shared {len(shared)}, cyclic {len(cyc)}, PARM sibling hazard {len(hazard)})")
    log(f"frames before: XDATA {before['x']} B, DATA {before['d']} B, BIT {before['b']} bits (PARMs included)")
    log(f"DATA blocks {dsize}; dead fns at offset 0: {len(dead)}")
    log(f"overlay blocks: __xovl {cursor['x']} B, __dovl* {cursor['d']} B, __bovl {cursor['b']} bits; "
        f"main region {region_size.get('main')}")
    for k, v in rep["largest_regions"]:
        log(f"  region {k}: {v}")
    bad = (xlimit and cursor["x"] > xlimit) or (dlimit and cursor["d"] > dlimit)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
