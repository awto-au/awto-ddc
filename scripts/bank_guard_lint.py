#!/usr/bin/env python3
"""DW8051 lint (awto-ddc#360): banked calls whose callee starts with a state-byte early return. Report only (exit 0).

usage: bank_guard_lint.py [--tree DIR] [--sim STEM] [--video MODE] [--passes N] [--top N]
  Callee: a function whose first statement (after plain declarations) is `if(<guard>) return [CONST];` and <guard> reads
  only state (g_ / s_ / isr_g_ / d_ names, b<PIN> bits, GET_*() macros), its parameters and constants: no other call.
  Call site: an lcall / ljmp from another region (fw/bank_map.tsv; common C -> bank counts) in tmp/sdcc-port/asm (the
  build's per-module asm): that call goes through the trampoline. Fix pattern: test the byte at the call site (#360).
  --sim STEM: fw_sim (DW8051 core) boot to ACTIVE on --video, then --passes main-loop passes; every candidate watched:
  calls per boot and per pass (all callers; a call that does work is counted too: an upper bound).
  Cost per call = trampoline round trip, from the newest docs/speed-bench.tsv row (stub_cyc / stub_entries).
Log: ./tmp/logs/bank_guard_lint.log
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import repo_root

ROOT = repo_root()
LOG = ROOT / "tmp/logs/bank_guard_lint.log"
DEF_RE = re.compile(r"^[A-Za-z_][\w \t\*]*?\b(\w+)\s*\(([^;{}()]*)\)\s*\{", re.MULTILINE)
DECL_RE = re.compile(r"\s*(?:static\s+)?(?:(?:__xdata|__data|__idata|__code|const|volatile|unsigned|signed)\s+)*"
                     r"(?:BYTE|WORD|DWORD|SBYTE|SWORD|bit|char|short|int|long|\w+_t)\b[^;()=]*(?:=[^;()]*)?;")
IF_RE = re.compile(r"\s*if\s*\(")
RET_RE = re.compile(r"\s*(?:\{\s*return\b[^;(]*;\s*\}|return\b[^;(]*;)")
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
STATE_RE = re.compile(r"^(?:g_|s_|isr_g_|d_|GET_)\w*|^b[A-Z][A-Z0-9_]*$")
KEYWORDS = {"sizeof"}
MODE_ACTIVE = 3                                          # isr_g_stModeInfo mode state (fw_sim.SimBus.run_until_mode)


def log(s: str) -> None:
    _log_line(s, LOG)


def strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def paren_end(t: str, i: int) -> int:
    """index after the ')' that closes the '(' at t[i]"""
    d = 0
    for k in range(i, len(t)):
        d += {"(": 1, ")": -1}.get(t[k], 0)
        if d == 0:
            return k + 1
    return -1


def guard_of(body: str, params: set) -> str | None:
    """the early-return guard at the start of a body (text after '{'), or None"""
    i = 0
    while True:
        m = DECL_RE.match(body, i)
        if not m:
            break
        i = m.end()
    m = IF_RE.match(body, i)
    if not m:
        return None
    e = paren_end(body, m.end() - 1)
    if e < 0 or not RET_RE.match(body, e):
        return None
    cond = body[m.end():e - 1]
    toks = IDENT_RE.findall(cond)
    for mt in IDENT_RE.finditer(cond):
        call = re.match(r"\s*\(", cond[mt.end():])
        if call and not mt.group(0).startswith("GET_") and mt.group(0) not in KEYWORDS:
            return None                                  # a real call in the guard: not a plain byte test
    state = [x for x in toks if STATE_RE.match(x)]
    other = [x for x in toks if not STATE_RE.match(x) and x not in params and not re.fullmatch(r"_?[A-Z][A-Z0-9_]*", x) and x not in KEYWORDS]
    if not state or other:
        return None
    return " ".join(cond.split())


def candidates(root: Path, names: set) -> dict:
    """{fn: (file, guard)} for compiled functions (names) with an early-return guard"""
    out = {}
    for p in sorted((root / "fw").rglob("*.c")):
        if "sdk-parked" in p.parts:
            continue
        t = strip_comments(p.read_text(errors="replace"))
        for m in DEF_RE.finditer(t):
            fn = m.group(1)
            if fn not in names or fn in out or fn in ("if", "while", "for", "switch"):
                continue
            params = set(IDENT_RE.findall(m.group(2)))
            g = guard_of(t[m.end():m.end() + 2000], params)
            if g:
                out[fn] = (str(p.relative_to(root)), g)
    return out


def regions(root: Path) -> dict:
    """{fn: region} from fw/bank_map.tsv ('C' = common, else the bank number as text)"""
    out = {}
    for row in csv.reader((root / "fw/bank_map.tsv").open(), delimiter="\t"):
        if row and row[0] == "fn" and len(row) > 2:
            out[row[1].removeprefix("_")] = row[2]
    return out


def call_graph(root: Path) -> dict:
    """{callee: [(caller, sites, loop depth max)]} from the build's per-module asm (sdcc_bank.Module chunks)"""
    import sdcc_bank as SB
    out = defaultdict(list)
    for p in sorted((root / "tmp/sdcc-port/asm").glob("*.asm")):
        if p.name.startswith("__"):
            continue
        for c in SB.Module(p).chunks:
            if c.area != "CSEG":
                continue
            per = defaultdict(list)
            for tgt, depth in c.sites:
                per[tgt.removeprefix("_")].append(depth)
            for tgt, ds in per.items():
                out[tgt].append((c.name.removeprefix("_"), len(ds), max(ds)))
    return out


def tramp_cycles(root: Path) -> tuple[float, str]:
    rows = list(csv.DictReader((root / "docs/speed-bench.tsv").open(), delimiter="\t"))
    for r in reversed(rows):
        try:
            return float(r["stub_cyc"]) / float(r["stub_entries"]), f"{r['image']} {r['date']}"
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return 0.0, "no speed-bench row"


def sim_counts(stem: str, video: str, passes: int, fns: list) -> tuple[dict, dict]:
    import fw_sim as S
    b = Path(stem + ".bin")
    bus = S.SimBus(b, b.with_suffix(".map"), "bguard-" + b.stem, None, boot=False, video=video)
    for f in fns:
        bus.m.watch(f)
    if not bus.run_until_mode(MODE_ACTIVE):
        log("sim: no ACTIVE within the budget; per-boot counts are up to the budget end")
    boot = dict(bus.m.stub_hits)
    hb0 = bus.diag()["hb"]
    while ((bus.diag()["hb"] - hb0) & 0xFFFF) < passes:
        bus.m.run(200_000)
    tot = dict(bus.m.stub_hits)
    bus.close()
    return boot, {f: (tot.get(f, 0) - boot.get(f, 0)) / passes for f in fns}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--sim", default="", help="image stem: count calls per boot / pass in fw_sim")
    ap.add_argument("--video", default="2160p60")
    ap.add_argument("--passes", type=int, default=20)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    root = a.tree.resolve()
    reg = regions(root)
    graph = call_graph(root)
    cand = candidates(root, set(reg))
    hits = []
    for fn, (src, g) in cand.items():
        rc = reg.get(fn)
        if rc is None or rc == "C":
            continue                                     # common callee: a plain lcall from anywhere
        xs = [(c, n, d) for c, n, d in graph.get(fn, []) if reg.get(c) != rc]
        if xs:
            hits.append((fn, rc, src, g, xs))
    cyc, cyc_src = tramp_cycles(root)
    boot, per = sim_counts(a.sim, a.video, a.passes, [h[0] for h in hits]) if a.sim and hits else ({}, {})
    hits.sort(key=lambda h: (-per.get(h[0], 0), -boot.get(h[0], 0), -sum(8 ** min(d, 3) * n for _, n, d in h[4])))
    log(f"=== bank_guard_lint {root.name}: {len(cand)} guarded functions, {len(hits)} reached cross-bank; "
        f"trampoline {cyc:.1f} cycles per call ({cyc_src}); sim {a.sim or '-'} {a.video if a.sim else ''} ===")
    log("rank\tfn\tbank\tcalls/boot\tcalls/pass\tcycles/pass saved (max)\tcross-bank sites\tguard\tsource")
    for k, (fn, rc, src, g, xs) in enumerate(hits[:a.top], 1):
        sites = ", ".join(f"{c} ({reg.get(c, '?')}) x{n}" for c, n, _ in xs[:4]) + (f" +{len(xs) - 4}" if len(xs) > 4 else "")
        pp = per.get(fn)
        log(f"{k}\t{fn}\t{rc}\t{boot.get(fn, '-')}\t{'-' if pp is None else f'{pp:.1f}'}\t"
            f"{'-' if pp is None else f'{pp * cyc:.0f}'}\t{sites}\t{g}\t{src}")
    log(f"report only (awto-ddc#360): {len(hits)} hits; a failure once the baseline is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
