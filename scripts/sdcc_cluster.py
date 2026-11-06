"""Call-graph-aware bank placement for sdcc_bank.py (--cluster): caller and callee in one bank = plain lcall, no stub.

Method (awto-ddc#8, awto-sdcc#2):
- Graph: unit = module's banked chunks (or one chunk each, mode `fn`); edge weight = sum over call sites of
  WEIGHT**loop depth (Chunk.sites; depth = nesting of local backward-jump spans, a static hotness proxy).
- Agglomeration: repeatedly merge the cluster pair with the heaviest summed edge whose joint size fits one bank.
- Packing: clusters first-fit-decreasing into banks. Returns None if they do not fit (caller keeps the default packing).
Calls from common code (main, ISR entries) and address-taken functions always need a stub; they are not edges.
"""
from collections import defaultdict

CONST_W = 64         # fn -> CONST ref: a CONST used from several banks goes to common, so keep users together
WEIGHT = 8           # one loop level = 8x as hot as straight-line code; depth capped at MAX_DEPTH
MAX_DEPTH = 3


def site_weight(depth):
    return WEIGHT ** min(depth, MAX_DEPTH)


def edges_of(units, funcs, consts=None):
    """{(i, j): weight} between units i < j, from call sites of banked chunks into other banked units."""
    owner = {id(c): i for i, u in enumerate(units) for c in u}
    e = defaultdict(int)
    for i, u in enumerate(units):
        for c in u:
            for t, depth in getattr(c, "sites", ()):
                tc = funcs.get(t)
                j = owner.get(id(tc)) if tc is not None else None
                if j is not None and j != i:
                    e[(min(i, j), max(i, j))] += site_weight(depth)
            for r in getattr(c, "refs", ()) if consts else ():
                rc = consts.get(r)
                j = owner.get(id(rc)) if rc is not None else None
                if j is not None and j != i:
                    e[(min(i, j), max(i, j))] += CONST_W
    return e


def agglomerate(sizes, edges, limit):
    """Heavy-edge merging; returns list of clusters (lists of unit indices)."""
    cl = {i: [i] for i in range(len(sizes))}
    csize = dict(enumerate(sizes))
    of = list(range(len(sizes)))
    while True:
        w = defaultdict(int)
        for (i, j), x in edges.items():
            a, b = of[i], of[j]
            if a != b:
                w[(min(a, b), max(a, b))] += x
        merged = set()
        did = False
        for (a, b), x in sorted(w.items(), key=lambda kv: (-kv[1], kv[0])):
            if a in merged or b in merged or csize[a] + csize[b] > limit:
                continue
            cl[a] += cl.pop(b)
            csize[a] += csize.pop(b)
            for k in cl[a]:
                of[k] = a
            merged.update((a, b))
            did = True
        if not did:
            return list(cl.values())


def assign(units, funcs, nbanks, limit, sizeof, consts=None):
    """Sets c.bank for every chunk of `units`; returns per-bank fill list or None when it does not fit."""
    sizes = [sum(sizeof(c) for c in u) for u in units]
    clusters = agglomerate(sizes, edges_of(units, funcs, consts), limit)
    fill = [0] * nbanks
    placed = {}
    for cl in sorted(clusters, key=lambda cl: -sum(sizes[i] for i in cl)):
        n = sum(sizes[i] for i in cl)
        b = next((b for b in range(nbanks) if fill[b] + n <= limit), None)
        if b is None:
            return None
        fill[b] += n
        for i in cl:
            placed[i] = b
    for i, u in enumerate(units):
        for c in u:
            c.bank = placed[i]
    return fill


def stats(chunks, funcs):
    """Crossing statistics for the current c.bank assignment (bank None = common)."""
    sites = cross = 0
    weighted = cross_w = 0
    stubbed = set()
    for c in chunks:
        for t, depth in getattr(c, "sites", ()):
            tc = funcs.get(t)
            if tc is None:
                continue
            sites += 1
            w = site_weight(depth)
            weighted += w
            if tc.bank is not None and tc.bank != c.bank:
                cross += 1
                cross_w += w
                stubbed.add(t)
    return {"sites": sites, "cross": cross, "weighted": weighted, "cross_weighted": cross_w, "stubs": len(stubbed)}
