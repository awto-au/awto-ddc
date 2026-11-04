#!/usr/bin/env python3
"""Keil-BL51-style RAM overlay for SDCC mcs51 asm: functions that are never live together share local storage.

usage: sdcc_overlay.py [--asm DIR] [--out DIR] [--xlimit N] [--dlimit N]
  --asm   SDCC -S output tree (default tmp/sdcc-port/asm)
  --out   rewritten tree + __ovl.asm (default tmp/sdcc-port/asm_ovl)
  --xlimit / --dlimit  fail if total XDATA / DATA after overlay exceeds this (bytes; default 8192 / 0 = no check)

Method (awto-ddc#8):
- Per function: XSEG locals (`_fn_var_L_N`) and DSEG/XSEG spill slots (`_fn_slocK_*`) form its frame.
  PARMs stay static: callers write them, possibly while evaluating other calls' args (sibling overlap risk).
- Call graph from `lcall/ljmp/acall/ajmp _fn`. Regions: main tree, each ISR (fn with `reti`), each
  address-taken fn (indirect call target). Frame offset = max(caller offset + caller frame) within a region.
- Kept static (own storage): fns reachable from more than one region, fns in call cycles, unattributed labels.
- Rewrite: storage lines removed; every use becomes `(__xovl + off)` / `(__dovl + off)`; __ovl.asm reserves blocks.
Log: tmp/logs/sdcc_overlay.log, report tmp/sdcc-port/overlay.json
"""
import json, os, re, subprocess, sys, time
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
MEM = {"XSEG": "x", "DSEG": "d"}                    # overlaid areas -> block (x = __xovl, d = __dovl)
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
        self.parse()

    def parse(self):
        area, cur, pending, alloc_fn = None, None, None, None
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
                pending = None
                continue
            if lab and area in MEM and i + 1 < len(self.lines) and self.lines[i + 1].strip().startswith(".ds"):
                if lab.group(2) == ":":                       # module-local storage only
                    self.storage.append((i, i + 1, lab.group(1), area, int(self.lines[i + 1].split()[1], 0)))
                continue
            if area == "CSEG" and cur:
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
        """(fn, var) owning this storage label, from SDCC's allocation comments; None = not a fn local
        (file-scope statics are never listed, so never overlaid)."""
        return self.alloc.get(label)

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
    indirect_sites = [n for n, info in nodes.items() if "__sdcc_call_dptr" in info["calls"]]
    for n in indirect_sites:
        calls[n] |= addr_taken

    # ---- frames
    frame = defaultdict(lambda: {"x": 0, "d": 0})
    syms = defaultdict(list)       # node -> [(mi, label, mem, size, rel_off)]
    static_bytes = {"x": 0, "d": 0, "parm_x": 0, "unowned": 0, "local_static": 0}
    for mi, m in enumerate(mods):
        for li, ld, label, area, size in m.storage:
            mem = MEM[area]
            own = m.owner(label)
            if own is None or own[0] not in m.funcs:
                static_bytes["unowned"] += size
                continue
            fn, var = own
            if "_PARM_" in label:
                static_bytes["parm_x" if mem == "x" else mem] += size
                continue
            if "sloc" not in label and m.is_local_static(fn, var):
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
    keep_static = shared | cyc

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
                            sum(frame[n][mem] for n in cmembers[c])) for mem in ("x", "d")} for c in cnodes}
        off = {c: {"x": 0, "d": 0} for c in cnodes}
        indeg = defaultdict(int)
        for c in cnodes:
            for t in cedges[c]:
                indeg[t] += 1
        q = [c for c in cnodes if indeg[c] == 0]
        while q:
            c = q.pop()
            for t in cedges[c]:
                for mem in ("x", "d"):
                    off[t][mem] = max(off[t][mem], off[c][mem] + cframe[c][mem])
                indeg[t] -= 1
                if indeg[t] == 0:
                    q.append(t)
        region_size[name] = {mem: max([off[c][mem] + cframe[c][mem] for c in cnodes] or [0]) for mem in ("x", "d")}
        for c in cnodes:
            for n in cmembers[c]:
                if n not in keep_static:          # non-cyclic SCC = single node
                    place[n] = (name, off[c])

    base, cursor = {}, {"x": 0, "d": 0}
    for name, _ in roots:
        base[name] = dict(cursor)
        for mem in ("x", "d"):
            cursor[mem] += region_size[name][mem]
    # static frames (shared/cyclic/unreached) get their own slots after all regions
    for n in nodes:
        if n not in place and (frame[n]["x"] or frame[n]["d"]):
            place[n] = ("static", {mem: 0 for mem in ("x", "d")})
            base.setdefault(("static", n), dict(cursor))
            for mem in ("x", "d"):
                cursor[mem] += frame[n][mem]

    # ---- rewrite
    out_dir.mkdir(parents=True, exist_ok=True)
    sub = defaultdict(dict)            # mi -> {label: expr}
    for n, entries in syms.items():
        region, off = place[n]
        b = base[("static", n)] if region == "static" else base[region]
        for mi, label, mem, size, rel in entries:
            blk = "__xovl" if mem == "x" else "__dovl"
            sub[mi][label] = f"({blk} + 0x{b[mem] + off[mem] + rel:X})"
    for mi, m in enumerate(mods):
        lines = list(m.lines)
        drop = set()
        for li, ld, label, area, size in m.storage:
            if label in sub[mi]:
                drop.update((li, ld))
        rx = re.compile(r"\b(" + "|".join(map(re.escape, sub[mi])) + r")\b") if sub[mi] else None
        new = []
        for i, line in enumerate(lines):
            if i in drop:
                continue
            if rx and not line.lstrip().startswith(";"):
                line = rx.sub(lambda mm: sub[mi][mm.group(1)], line)
            new.append(line)
        if sub[mi]:
            new.insert(1, "\t.globl __xovl\n\t.globl __dovl")
        dst = out_dir / m.path.relative_to(asm_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("\n".join(new))
    (out_dir / "__ovl.asm").write_text(
        "\t.module __ovl\n\t.globl __xovl\n\t.globl __dovl\n"
        f"\t.area XSEG (XDATA)\n__xovl::\n\t.ds 0x{max(cursor['x'], 1):X}\n"
        f"\t.area DSEG (DATA)\n__dovl::\n\t.ds 0x{max(cursor['d'], 1):X}\n")

    before = {mem: sum(f[mem] for f in frame.values()) for mem in ("x", "d")}
    rep = {"modules": len(mods), "functions": len(nodes), "roots": len(roots),
           "isr": sum(1 for _, n in roots if nodes[n]["isr"]), "addr_taken": len(addr_taken),
           "kept_static_fns": len(keep_static), "cyclic_fns": len(cyc), "shared_fns": len(shared),
           "frames_before": before, "overlay_block": cursor, "static_parm_x": static_bytes["parm_x"],
           "local_static": static_bytes["local_static"],
           "unowned_storage": static_bytes["unowned"],
           "main_region": region_size.get("main"),
           "largest_regions": sorted(((k, v) for k, v in region_size.items()), key=lambda kv: -kv[1]["x"])[:8]}
    (ROOT / "tmp/sdcc-port").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/sdcc-port/overlay.json").write_text(json.dumps(rep, indent=1, default=str))
    log(f"indirect call sites {len(indirect_sites)}")
    log(f"functions {len(nodes)}, roots {len(roots)} (isr {rep['isr']}, address-taken {len(addr_taken)}), "
        f"kept static {len(keep_static)} (shared {len(shared)}, cyclic {len(cyc)})")
    log(f"frames before: XDATA {before['x']} B, DATA {before['d']} B; PARM (static) XDATA {static_bytes['parm_x']} B")
    log(f"overlay blocks: __xovl {cursor['x']} B, __dovl {cursor['d']} B; main region {region_size.get('main')}")
    for k, v in rep["largest_regions"]:
        log(f"  region {k}: {v}")
    bad = (xlimit and cursor["x"] > xlimit) or (dlimit and cursor["d"] > dlimit)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
