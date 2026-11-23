#!/usr/bin/env python3
"""Common-region audit (#TBD): why each common chunk is common, stub callers by bank, ISR reach. Numbers only.

usage: common_audit.py [--asm tmp/sdcc-port/asm_ovl] [--layout fw/bank_layout.tsv]  -> tmp/logs/common_audit.log
"""
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_bank as B
import sdcc_layout as L

ROOT = Path(__file__).resolve().parent.parent
STUB = 8


def load(asm, lay_path):
    mods = [B.Module(p) for p in sorted(Path(asm).glob("*.asm")) if not p.name.startswith("__")]
    funcs, consts = {}, {}
    for m in mods:
        for c in m.chunks:
            (funcs if c.area == "CSEG" else consts)[c.name] = c
    tmp = ROOT / "tmp/scratch/audit"
    tmp.mkdir(parents=True, exist_ok=True)
    for m in mods:
        idx = {id(c): i for i, c in enumerate(m.chunks)}
        p = tmp / f"{m.name}.asm"
        p.write_text(B.render(m, lambda c, idx=idx: f"S{idx[id(c)]}", {}, {}))
        sz = B.assemble(p)
        for c in m.chunks:
            c.size = sz.get(f"S{idx[id(c)]}", 0)
    B.LOG = (ROOT / "tmp/logs/common_audit.log").open("a")
    B.drop_dead(mods, funcs, consts)
    lay = L.Layout.load(lay_path)
    for (kind, name), (reg, _o, _s) in lay.rows.items():
        t = funcs if kind == "fn" else consts if kind == "const" else None
        if t is not None and name in t:
            t[name].where = reg
    return mods, funcs, consts, lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_ovl"))
    ap.add_argument("--layout", default=str(ROOT / "fw/bank_map.tsv"))
    a = ap.parse_args()
    mods, funcs, consts, lay = load(a.asm, a.layout)
    wh = lambda c: getattr(c, "where", None)
    # ISR reach
    isr = [c for c in funcs.values() if c.isr]
    reach, st = set(), list(isr)
    while st:
        c = st.pop()
        if c.name in reach:
            continue
        reach.add(c.name)
        st.extend(funcs[t] for t in c.calls if t in funcs)
    callers = defaultdict(set)
    for c in funcs.values():
        for t in c.calls | c.refs:
            if t in funcs:
                callers[t].add(c.name)
    print(f"ISR entries {len(isr)}: {', '.join(sorted(c.name for c in isr))}")
    print(f"reachable from ISR: {len(reach)} fns, {sum(funcs[n].size for n in reach)} B; of which banked "
          f"{sum(1 for n in reach if wh(funcs[n]) != 'C')} fns {sum(funcs[n].size for n in reach if wh(funcs[n]) != 'C')} B")
    # common fns by class
    cls = defaultdict(list)
    for c in funcs.values():
        if wh(c) != "C":
            continue
        if c.isr:
            k = "isr_entry"
        elif c.name == "_main":
            k = "main"
        elif c.stack_args:
            k = "stack_args"
        else:
            k = "hot/pin"
        cls[k].append(c)
    print("\ncommon fn classes")
    for k, v in cls.items():
        print(f"  {k}: {len(v)} fns, {sum(c.size for c in v)} B")
    print("\ncommon fn detail: name size class callers(common/banked) in_isr_reach")
    for k, v in cls.items():
        for c in sorted(v, key=lambda c: -c.size):
            cs = callers[c.name]
            nc = sum(1 for x in cs if wh(funcs[x]) == "C")
            banks = {wh(funcs[x]) for x in cs if wh(funcs[x]) != "C"}
            print(f"  {c.name}\t{c.size}\t{k}\tcommon_callers={nc}\tcaller_banks={len(banks)}\tisr_reach={c.name in reach}\tcalls_banked={sum(1 for t in c.calls if t in funcs and wh(funcs[t]) != 'C')}")
    # consts
    cc = [c for c in consts.values() if wh(c) == "C"]
    users = defaultdict(set)
    for c in funcs.values():
        for r in c.refs:
            if r in consts:
                users[r].add(wh(c))
    print(f"\ncommon consts: {len(cc)}, {sum(c.size for c in cc)} B")
    by = Counter()
    for c in cc:
        u = users[c.name]
        k = "used_by_common" if "C" in u else "multi_bank" if len(u) > 1 else "single_bank_escape" if u else "unref_by_fn"
        by[k] += c.size
        print(f"  {c.name}\t{c.size}\t{k}\t{sorted(map(str, u))}")
    print("  const class bytes:", dict(by))
    # stubs
    tgt = defaultdict(lambda: [set(), 0])      # target -> [caller regions, address-taken]
    for c in [*funcs.values(), *consts.values()]:
        for t in c.calls:
            if t in funcs and wh(funcs[t]) != "C" and wh(funcs[t]) != wh(c):
                tgt[t][0].add(wh(c))
        for t in c.refs:
            if t in funcs and wh(funcs[t]) != "C":
                tgt[t][0].add(wh(c))
                tgt[t][1] += 1
    n = len(tgt)
    print(f"\nstubs needed: {n} = {n * STUB} B")
    pair = Counter()
    for t, (rs, _) in tgt.items():
        for r in rs:
            pair[(r, wh(funcs[t]))] += 1
    onlycommon = [t for t, (rs, _) in tgt.items() if rs == {"C"}]
    hascommon = [t for t, (rs, _) in tgt.items() if "C" in rs]
    nobank = [t for t, (rs, _) in tgt.items() if "C" not in rs]
    print(f"  address-taken stubs (any ref, incl. const pointer tables): {sum(1 for v in tgt.values() if v[1])}; "
          f"address-taken only (no call from another bank): {sum(1 for t, v in tgt.items() if v[1] and not any(t in x.calls for x in funcs.values() if wh(x) != wh(funcs[t])))}")
    print(f"  stubs with a common caller: {len(hascommon)} (only common: {len(onlycommon)}); no common caller: {len(nobank)}")
    dist = Counter(len(rs - {"C"}) for t, (rs, _) in tgt.items())
    print("  distinct caller banks per stub:", dict(sorted(dist.items())))
    local = sum(len(tgt[t][0] - {"C"}) for t in nobank)
    print(f"  bank-local stubs for the no-common-caller set: {len(nobank)} common stubs -> {local} bank stubs "
          f"({len(nobank) * STUB} B in common -> {local * STUB} B spread over banks)")
    print("  stub callers by (caller region -> callee bank) top 15:",
          [(f"{r}->{b}", v) for (r, b), v in pair.most_common(15)])
    from_common = Counter()
    for t, (rs, _) in tgt.items():
        if "C" in rs:
            from_common[wh(funcs[t])] += 1
    print("  stubs called from common, by callee bank:", dict(from_common))
    cross = sum(1 for c in funcs.values() for t in c.calls if t in funcs and wh(funcs[t]) != "C" and wh(funcs[t]) != wh(c))
    intra = sum(1 for c in funcs.values() for t in c.calls if t in funcs and wh(funcs[t]) == wh(c) != "C")
    print(f"  call edges: cross/common->banked {cross}, intra-bank {intra}")
    fbank = Counter(wh(c) for c in funcs.values())
    print("  fns per region:", dict(fbank))
    const_audit(mods, funcs, consts, lay)
    helper_audit(mods, funcs, consts, lay)


def const_audit(mods, funcs, consts, lay):
    """Per common CONST: user regions, why it is common, copies if each user bank gets its own (#TBD addition)."""
    wh = lambda c: getattr(c, "where", None)
    for c in funcs.values():
        c.bank = None if wh(c) == "C" else wh(c)
    users = defaultdict(set)
    gptr_x, escaping = {}, set()
    for c in funcs.values():
        code = [ln.split(";", 1)[0] for ln in c.lines]
        for i, ln in enumerate(code):
            rs = [r for r in B.SYM.findall(ln) if r in consts]
            if rs and not B.addr_stays_in_bank(code, i, c, funcs):
                escaping.update(rs)
            if rs:
                t = B.gptr_callee(code, i, funcs)
                if t is not None and not t.common and t.bank != c.bank:
                    for r in rs:
                        gptr_x[r] = (c.name, t.name)
        for r in c.refs:
            if r in consts:
                users[r].add(wh(c))
    for t in consts.values():
        escaping.update(r for r in t.refs if r in consts)
    for m in mods:
        for ln in m.head + m.tail:
            if B.re.match(r"^\s+\.(db|dw|byte|word)\b", ln):
                for r in B.SYM.findall(ln.split(";", 1)[0]):
                    if r in consts:
                        users[r].add("init")
    changed = True
    while changed:
        changed = False
        for t in consts.values():
            for r in t.refs:
                if r in consts and not users[t.name] <= users[r]:
                    users[r] |= users[t.name]
                    changed = True
    cc = [c for c in consts.values() if wh(c) == "C"]
    cls = defaultdict(lambda: [0, 0, 0, 0])      # class -> [consts, bytes, copies needed, bytes if per-user-bank]
    print(f"\nconst audit: {len(cc)} common consts, {sum(c.size for c in cc)} B, slots {sum(L.pad_slot(c.size) for c in cc)} B")
    for c in sorted(cc, key=lambda c: -c.size):
        u = users[c.name]
        banks = sorted(x for x in u if isinstance(x, int))
        if "C" in u or "init" in u:
            k = "common_or_init_user"
        elif c.name in gptr_x:
            k = "gptr_reader_other_bank"
        elif len(banks) > 1:
            k = "multi_bank"
        elif c.name in escaping:
            k = "single_bank_escape"
        else:
            k = "other"
        n = max(1, len(banks))
        r = cls[k]
        r[0] += 1
        r[1] += c.size
        r[2] += n
        r[3] += c.size * n
        print(f"  {c.name}\t{c.size}\t{k}\tuser_banks={banks}{' +common' if 'C' in u else ''}{' +init' if 'init' in u else ''}\t{gptr_x.get(c.name, '')}")
    print("  class: consts, bytes (1 copy), copies, bytes as per-user-bank copies")
    for k, v in cls.items():
        print(f"  {k}: {v}")
    print(f"  today: {sum(c.size for c in cc)} B x 14 copies = {sum(c.size for c in cc) * 14} B flash; per-user-bank: {sum(v[3] for v in cls.values())} B flash")


def helper_audit(mods, funcs, consts, lay):
    wh = lambda c: getattr(c, "where", None)
    callers = defaultdict(set)
    ptr = set()
    for c in [*funcs.values(), *consts.values()]:
        for t in c.calls:
            if t in funcs:
                callers[t].add(wh(c))
        for t in c.refs:
            if t in funcs:
                ptr.add(t)
    print("\nhelper audit A: common fns (no ISR / SP dependency) duplicated into caller banks: name size caller_banks flash_now(x15) flash_dup")
    tot = [0, 0, 0]
    for c in sorted((c for c in funcs.values() if wh(c) == "C"), key=lambda c: -c.size):
        if c.isr or c.name == "_main" or c.stack_args or c.name in ptr:
            continue
        u = callers[c.name]
        banks = {x for x in u if isinstance(x, int)}
        if "C" in u or not banks or c.name in B_PINNED_SP:
            continue
        reach = c.name in isr_reach(funcs)
        print(f"  {c.name}\t{c.size}\tbanks={len(banks)}\tnow={c.size * 15}\tdup={c.size * len(banks)}\tisr_reach={reach}")
        tot[0] += c.size
        tot[1] += c.size * 15
        tot[2] += c.size * len(banks)
    print(f"  total: {tot[0]} B common freed, flash {tot[1]} -> {tot[2]} B")
    print("helper audit B: banked leaf fns (no calls) called cross-bank, duplicated instead of a stub (stub = 8 B per caller bank)")
    for lim in (8, 16, 24, 32, 48, 64):
        n = fl = save = 0
        for c in funcs.values():
            if wh(c) == "C" or c.size == 0 or c.size > lim or c.calls or c.name in ptr or c.stack_args or c.isr:
                continue
            xb = {x for x in callers[c.name] if x != wh(c) and isinstance(x, int)}
            if not xb or "C" in callers[c.name]:
                continue
            n += 1
            fl += len(xb) * c.size
            save += len(xb) * STUB
        print(f"  size <= {lim}: {n} fns, copies cost {fl} B, stubs they replace {save} B (net bank bytes {save - fl:+d})")


B_PINNED_SP = {"_AwtoWaitLog", "_AwtoWaitPump", "_ScalerTimerWaitForEvent", "_AwtoStackPaint", "_AwtoStackCheck", "_AwtoStackDeepTest",
               "_AwtoPutStr", "_AwtoPsPollSite", "_AwtoPassStamp", "_AwtoWdtPoke", "_AwtoDelayLoops", "_AwtoDelayXus", "_AwtoDelayCnt",
               "_AwtoDelayEnd", "_AwtoDelayLong", "_AwtoDbgIsrCmd_EXINT1", "_ScalerSyncDpHpdIrqAssertTimer2EventProc_EXINT"}
_ISR = {}


def isr_reach(funcs):
    if not _ISR:
        st = [c for c in funcs.values() if c.isr]
        while st:
            c = st.pop()
            if c.name in _ISR:
                continue
            _ISR[c.name] = 1
            st.extend(funcs[t] for t in c.calls if t in funcs)
    return _ISR


if __name__ == "__main__":
    main()
