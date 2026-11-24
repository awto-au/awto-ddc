#!/usr/bin/env python3
"""Affinity bank assignment for sdcc_bank.py --repack (awto-ddc#333 follow-up): fewer banks, fewer stubs. Deterministic.

- Unit = chunks that must share a bank: #pragma place group / pin members, a CONST with its only user fn.
- Edge weight: call sites (8 ** loop depth, sdcc_cluster), measured calls (--cluster-weights), CONST refs.
- Initial: heavy-edge agglomeration + first-fit-decreasing (shrinking cluster limit until it fits), then
  move / swap refinement on the cut weight. Capacity per bank = size - headroom - msg block, minus 8 B per local stub copy.
- Common fns / consts (current map, ISR, SP-readers) are not touched: not units.
"""
from collections import defaultdict

import sdcc_cluster as SC

STUB = 8


class Unit:
    def __init__(self, uid):
        self.uid, self.chunks, self.size, self.pin = uid, [], 0, None


def build_units(funcs, consts, place_groups, place_pins, is_common, pairs=()):
    """-> units, owner {chunk name: unit}. Chunks: fn and CONST objects (Chunk) that are not common."""
    chunks = {n: c for n, c in {**funcs, **consts}.items() if c.size and not is_common(c)}
    parent = {n: n for n in chunks}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for g, cs in sorted(place_groups.items()):
        names = [c.name for c in cs if c.name in chunks]
        for n in names[1:]:
            union(names[0], n)
    pinned = defaultdict(list)
    for c, b in place_pins:
        if c.name in chunks and b != "C":
            pinned[b].append(c.name)
    for b, names in pinned.items():
        for n in names[1:]:
            union(names[0], n)
    users = defaultdict(set)                                 # CONST -> fn chunks naming it, closed over pointer tables
    for c in funcs.values():
        for r in c.refs:
            if r in consts:
                users[r].add(c.name)
    changed = True
    while changed:
        changed = False
        for t in consts.values():
            for r in t.refs:
                if r in consts and not users[t.name] <= users[r]:
                    users[r] |= users[t.name]
                    changed = True
    for r, u in sorted(users.items()):
        fu = [n for n in u if n in chunks]
        if r in chunks and fu:                               # every user in the CONST's bank: a split const would have to go to common
            for n in fu:
                union(fu[0], n)
            union(fu[0], r)
    for f, t, r in sorted(pairs):                            # link gate: a CONST pointer and the fn it is passed to share a bank
        if f in chunks and t in chunks and r in chunks:
            union(f, t)
    units, owner = {}, {}
    for n in sorted(chunks):
        r = find(n)
        u = units.setdefault(r, Unit(r))
        u.chunks.append(chunks[n])
        u.size += chunks[n].size
        owner[n] = u
    for b, names in pinned.items():
        owner[names[0]].pin = b
    return list(units.values()), owner, users


def edges(units, owner, funcs, consts, users, dyn):
    """{(ui, uj): weight} on unit indices, i < j."""
    idx = {u.uid: i for i, u in enumerate(units)}
    e = defaultdict(int)

    def add(a, b, w):
        if a is None or b is None or a is b:
            return
        i, j = idx[a.uid], idx[b.uid]
        e[(min(i, j), max(i, j))] += w

    for u in units:
        for c in u.chunks:
            if c.area == "CSEG":
                for t, depth in c.sites:
                    add(u, owner.get(t), SC.site_weight(depth))
                for r in c.refs:
                    if r in consts and len(users[r]) > 1:
                        add(u, owner.get(r), SC.CONST_W)
    for (a, b), n in (dyn or {}).items():
        add(owner.get(a), owner.get(b), int(n * SC.DYN_W))
    return e


class State:
    """Assignment unit -> bank with exact per-bank fill including local stub copies (kept incrementally)."""

    def __init__(self, units, owner, funcs, caps):
        self.units, self.caps, self.n = units, caps, len(caps)
        self.bank = [None] * len(units)
        self.fns = [[c.name for c in u.chunks if c.area == "CSEG"] for u in units]
        self.size = [u.size for u in units]
        self.callees, self.taken = [], []                    # per unit: banked fns called in another unit / address-taken by its CONSTs
        for u in units:
            d, tk = set(), set()
            for c in u.chunks:
                d.update(t for t in c.calls if t in owner and t in funcs and owner[t] is not u)
                if c.area != "CSEG":
                    tk.update(t for t in c.refs if t in owner and t in funcs)    # a pointer table: every target has a stub in the table's bank
            self.callees.append(sorted(d))
            self.taken.append(sorted(tk))
        self.fnbank = {}
        self.cnt = [defaultdict(int) for _ in range(self.n)]   # bank -> callee fn -> units there calling it
        self.tcnt = [defaultdict(int) for _ in range(self.n)]  # bank -> fn -> tables there pointing at it
        self.pres = [set() for _ in range(self.n)]             # bank -> fns with a stub copy there
        self.base = [0] * self.n

    def _refresh(self, b, f):
        has = (self.cnt[b][f] > 0 and self.fnbank.get(f) != b) or self.tcnt[b][f] > 0
        (self.pres[b].add if has else self.pres[b].discard)(f)

    def stubs(self):
        return sum(len(p) for p in self.pres)

    def total(self, b):
        return self.base[b] + STUB * len(self.pres[b])

    def start(self, assign):
        for i, b in enumerate(assign):
            self.bank[i] = b
            self.base[b] += self.size[i]
            for f in self.fns[i]:
                self.fnbank[f] = b
            for f in self.callees[i]:
                self.cnt[b][f] += 1
            for f in self.taken[i]:
                self.tcnt[b][f] += 1
        for b in range(self.n):
            for f in {*self.cnt[b], *self.tcnt[b]}:
                self._refresh(b, f)

    def move(self, i, b):
        a = self.bank[i]
        for f in self.callees[i]:
            self.cnt[a][f] -= 1
            self.cnt[b][f] += 1
        for f in self.taken[i]:
            self.tcnt[a][f] -= 1
            self.tcnt[b][f] += 1
        self.base[a] -= self.size[i]
        self.base[b] += self.size[i]
        for f in self.fns[i]:
            self.fnbank[f] = b
        self.bank[i] = b
        for f in {*self.callees[i], *self.taken[i]}:
            self._refresh(a, f)
            self._refresh(b, f)
        for f in self.fns[i]:                                # the callee moved: every bank calling it changes its stub
            for x in range(self.n):
                if self.cnt[x][f] > 0:
                    self._refresh(x, f)

    def over(self):
        return [b for b in range(self.n) if self.total(b) > self.caps[b]]


def initial(units, e, caps, sizes, limit_steps=(1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.0)):
    """Agglomerate to a limit (fraction of the smallest cap), FFD the clusters; pinned units placed first."""
    n = len(caps)
    for fr in limit_steps:
        limit = int(min(caps) * fr)
        cl = SC.agglomerate(sizes, e, max(limit, 1)) if fr else [[i] for i in range(len(units))]
        fill = [0] * n
        out = [None] * len(units)
        for i, u in enumerate(units):
            if u.pin is not None:
                out[i] = u.pin
                fill[u.pin] += sizes[i]
        ok = all(fill[b] <= caps[b] for b in range(n))
        order = sorted(cl, key=lambda c: (-sum(sizes[i] for i in c), min(c)))
        for c in order:
            if not ok:
                break
            free = [i for i in c if out[i] is None]
            if not free:
                continue
            tot = sum(sizes[i] for i in free)
            pinb = {out[i] for i in c if out[i] is not None}
            cand = sorted(pinb) + [b for b in range(n) if b not in pinb]
            b = next((b for b in cand if fill[b] + tot <= caps[b]), None)
            if b is None:                                     # does not fit whole: place its units one by one
                for i in sorted(free, key=lambda i: (-sizes[i], i)):
                    b2 = min((b for b in range(n) if fill[b] + sizes[i] <= caps[b]), key=lambda b: (caps[b] - fill[b] - sizes[i], b), default=None)
                    if b2 is None:
                        ok = False
                        break
                    out[i] = b2
                    fill[b2] += sizes[i]
            else:
                for i in free:
                    out[i] = b
                fill[b] += tot
        if ok:
            return out, fr
    return None, None


def cut(e, bank):
    return sum(w for (i, j), w in e.items() if bank[i] != bank[j])


STUB_W = 6                  # one stub copy costs as much as this many plain call sites in the objective


def refine(st, e, passes=12, stub_w=STUB_W):
    """Move / swap units between banks while cut weight + stub_w * stub copies drops and every bank stays within its cap."""
    adj = defaultdict(list)
    for (i, j), w in e.items():
        adj[i].append((j, w))
        adj[j].append((i, w))

    def conns(i):
        c = defaultdict(int)
        for j, w in adj[i]:
            c[st.bank[j]] += w
        return c

    for _ in range(passes):
        moved = 0
        for i in sorted(range(len(st.units)), key=lambda i: (-st.size[i], i)):
            if st.units[i].pin is not None:
                continue
            a, conn = st.bank[i], conns(i)
            s0, best = st.stubs(), None
            for b in range(st.n):
                if b == a:
                    continue
                st.move(i, b)
                ok = st.total(b) <= st.caps[b] and st.total(a) <= st.caps[a]
                gain = conn[b] - conn[a] + stub_w * (s0 - st.stubs())
                st.move(i, a)
                if ok and gain > 0 and (best is None or gain > best[0]):
                    best = (gain, b)
            if best is not None:
                st.move(i, best[1])
                moved += 1
                continue
            for b in sorted((b for b in range(st.n) if b != a), key=lambda b: -conn[b]):     # swap with a smaller unit of bank b
                if conn[b] <= conn[a]:
                    break
                for j in sorted((j for j in range(len(st.units)) if st.bank[j] == b and st.units[j].pin is None and st.size[j] <= st.size[i]),
                                key=lambda j: (-st.size[j], j))[:40]:
                    cj = conns(j)
                    gain = conn[b] - conn[a] + cj[a] - cj[b] - 2 * sum(w for k, w in adj[i] if k == j)
                    st.move(i, b)
                    st.move(j, a)
                    gain += stub_w * (s0 - st.stubs())
                    if gain > 0 and st.total(a) <= st.caps[a] and st.total(b) <= st.caps[b]:
                        moved += 1
                        break
                    st.move(j, b)
                    st.move(i, a)
                else:
                    continue
                break
        if not moved:
            break
    return st


def assign(funcs, consts, place_groups, place_pins, is_common, caps, pairs=(), dyn=None, log=print, spread=0.0):
    """caps: per-bank usable bytes (bank size - common - msg block - headroom). Sets c.bank on every non-common chunk;
    returns (per-bank totals incl. local stubs, cut weight before / after refinement)."""
    units, owner, users = build_units(funcs, consts, place_groups, place_pins, is_common, pairs)
    e = edges(units, owner, funcs, consts, users, dyn)
    sizes = [u.size for u in units]
    if spread:                                                # dev layout: every bank gets about its share, the rest is free tail
        share = int(sum(sizes) / len(caps) * (1 + spread))
        caps = [min(c, share) for c in caps]
    for slack in (0.06, 0.04, 0.03, 0.02, 0.01, 0.0):          # room for the stub copies the sizes do not include
        out, fr = initial(units, e, [int(c * (1 - slack)) for c in caps], sizes)
        if out is None:
            continue
        st = State(units, owner, funcs, caps)
        st.start(out)
        if not st.over():
            break
    if out is None:
        raise SystemExit(f"affinity: {sum(sizes)} B of units do not fit {len(caps)} banks of caps {caps}")
    before = cut(e, st.bank)
    if st.over():                                             # stubs pushed a bank over: shed its lightest-attached units
        for b in st.over():
            for i in sorted((i for i in range(len(units)) if st.bank[i] == b and units[i].pin is None), key=lambda i: st.size[i]):
                if st.total(b) <= caps[b]:
                    break
                tgt = min((x for x in range(st.n) if x != b and st.total(x) + st.size[i] <= caps[x]), key=lambda x: (st.total(x), x), default=None)
                if tgt is not None:
                    st.move(i, tgt)
    refine(st, e)
    if st.over():
        raise SystemExit(f"affinity: banks {st.over()} over their cap after refinement: {[st.total(b) for b in range(st.n)]} vs {caps}")
    for i, u in enumerate(units):
        for c in u.chunks:
            c.bank, c.common = st.bank[i], False
    log(f"affinity: per bank base {st.base}, stub copies {[len(p) for p in st.pres]}")
    log(f"affinity: {len(units)} units, {len(e)} edges, initial cluster limit {fr}, cut {before} -> {cut(e, st.bank)}")
    return [st.total(b) for b in range(st.n)], (before, cut(e, st.bank))
