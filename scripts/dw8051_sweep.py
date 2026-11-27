"""DW8051 rules sweep report (internal; ./dev.py rules-report). Rules: awto-dan docs/embedded/dw8051-rules.md, gates: #361.

- Counts per rule class over our files (magic_lint.our_files) and, where named, the SDK; numbers only, no thresholds.
- Needs the tree's last build (tmp/sdcc-port/asm, asm_bank .rst) and its image for --profile.
- --profile: fw_profile idle main-loop passes with the guard-ret addresses watched: per-site call rate + no-op fraction (#360).
Log: tmp/logs/dw8051_sweep.log; guard sites: tmp/dw8051/guard_sites.tsv
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import chip_mem as CM
from _log import Logger
from _repo import repo_root

ROOT = repo_root()
LABEL = re.compile(r"^\s+([0-9A-F]{6})\s+(?:[0-9A-F]{2}\s)*\s*\d+\s+(_\w+):\s*$")
INSTR = re.compile(r"^\s+([0-9A-F]{6})\s+((?:[0-9A-F]{2} ?)+)\s+\[\s*\d+\]\s+\d+\s+(\S+)\s*(.*?)\s*(?:;.*)?$")
LOCAL = re.compile(r"^\s+([0-9A-F]{6})\s+\d+\s+(\d+\$):")
CALL = re.compile(r"^(lcall|ljmp)$")
GUARD_LOAD = re.compile(r"^(?:dptr,#(_\w+)|a,(_\w+))$")
COND = ("jz", "jnz", "jc", "jnc", "jb", "jnb", "cjne", "djnz", "jbc")
SINGLE_BIT = re.compile(r"&\s*(\(?_BIT\d\)?|0x(?:0?1|0?2|0?4|0?8|10|20|40|80)\b)\s*\)\s*[!=]=\s*\1(?![\w])")
GUARD_HEAD = 6     # code instructions read for an early-return guard


def our_files() -> list[Path]:
    import magic_lint
    return magic_lint.our_files(ROOT)


def _text(p: Path) -> str:
    return p.read_text(errors="replace")


def rst_functions(asm_dir: Path) -> dict:
    """{name: {"addr", "file", "ins": [(addr, mnem, ops)], "locals": {label: addr}}} from the post-bank .rst listings."""
    fns, cur = {}, None
    for f in sorted(asm_dir.glob("*.rst")):
        cur = None
        for ln in _text(f).split("\n"):
            m = LABEL.match(ln)
            if m and not m.group(2).startswith("__bs_"):
                cur = fns.setdefault(m.group(2), {"addr": int(m.group(1), 16), "file": f.stem, "ins": [], "locals": {}})
                continue
            if cur is None:
                continue
            m = LOCAL.match(ln)
            if m:
                cur["locals"][m.group(2)] = int(m.group(1), 16)
                continue
            m = INSTR.match(ln)
            if m:
                cur["ins"].append((int(m.group(1), 16), m.group(3).lower(), m.group(4).replace(" ", "").replace("\t", "")))
    return fns


def region(addr: int) -> str:
    return "common" if addr < CM.COMMON_END else f"b{addr >> 16}"


def guard_candidates(fns: dict) -> dict:
    """Functions in a bank that start with a test of a global (not a _PARM_ slot) and an early `ret` (#360 pattern)."""
    out = {}
    for name, f in fns.items():
        ins = f["ins"]
        if f["addr"] < CM.COMMON_END or len(ins) <= GUARD_HEAD:
            continue
        head = ins[:GUARD_HEAD]
        m = GUARD_LOAD.match(f"{head[0][2]}") if head[0][1] == "mov" else None
        bitsym = re.match(r"^\(?(_\w+)", head[0][2]) if head[0][1] in ("jb", "jnb") else None
        sym = (m.group(1) or m.group(2)) if m else bitsym.group(1) if bitsym else None
        if not sym or "_PARM_" in sym:
            continue
        rets = [a for a, mn, _o in head if mn == "ret"]
        if not rets or not any(mn in COND for _a, mn, _o in head[:head.index(next(x for x in head if x[1] == "ret"))]):
            continue
        out[name] = {"sym": sym, "rets": rets, "addr": f["addr"], "file": f["file"]}
    return out


def call_sites(fns: dict, targets: set) -> list:
    """[(caller, caller region, callee, call kind)]: lcall/ljmp of a target, direct or through its __bs_ stub."""
    sites = []
    for name, f in fns.items():
        for _a, mn, ops in f["ins"]:
            if mn not in ("lcall", "ljmp"):
                continue
            t = re.sub(r"_b\d+$", "", ops[4:]) if ops.startswith("__bs_") else ops
            t = t if t.startswith("_") else "_" + t
            if t in targets:
                sites.append((name, region(f["addr"]), t, ("stub " if ops.startswith("__bs_") else "direct ") + mn))
    return sites


def isr_banked(fns: dict) -> list:
    """[(isr, caller, stub target, depth)]: every banked (__bs_) call reachable from an ISR (functions ending in reti)."""
    isrs = [n for n, f in fns.items() if any(mn == "reti" for _a, mn, _o in f["ins"])]
    out = []
    for r in isrs:
        seen, st = set(), [(r, 0)]
        while st:
            n, d = st.pop()
            if n in seen or n not in fns:
                continue
            seen.add(n)
            for _a, mn, ops in fns[n]["ins"]:
                if mn not in ("lcall", "ljmp", "acall", "ajmp"):
                    continue
                if ops.startswith("__bs_") and ops not in ("__bs_call", "__bs_ret"):
                    t = "_" + re.sub(r"_b\d+$", "", ops[5:])
                    out.append((r, n, t, d + 1))
                    st.append((t, d + 1))
                elif ops.startswith("_") and not ops.startswith("__"):
                    st.append((ops, d))
    return out


def parm_slots(asm_dir: Path, stems: set) -> list:
    """[(module, function, n, area, references in its module)] of the _PARM_n slots of our modules."""
    rows = []
    for f in sorted(asm_dir.glob("*.asm")):
        if f.stem not in stems:
            continue
        t, area = _text(f), ""
        for ln in t.split("\n"):
            a = re.match(r"^\s*\.area\s+(\w+)", ln)
            if a:
                area = a.group(1)
            m = re.match(r"^(_\w+?)_PARM_(\d+):", ln)
            if m:
                lab = f"{m.group(1)}_PARM_{m.group(2)}"
                rows.append((f.stem, m.group(1)[1:], int(m.group(2)), area, len(re.findall(re.escape(lab) + r"\b", t)) - 1))
    return rows


def static_counts(files: list[Path]) -> dict:
    src = {p: _text(p) for p in files if p.is_file()}
    sdk = [p for p in (ROOT / "fw/sdk").rglob("*") if p.suffix in (".c", ".h") and p not in src]
    shared = [(str(p.relative_to(ROOT)), ln.strip()[:90]) for p in [*src, *sdk] for ln in _text(p).split("\n")
              if "[[awto::isr_shared" in ln and "volatile" not in ln.split("[[")[0] and not ln.lstrip().startswith("static")]
    return {"constexpr": sum(len(re.findall(r"\bconstexpr\b", t)) for t in src.values()),
            "sfr16": sum(len(re.findall(r"__sfr16", t)) for t in src.values()),
            "single_bit_ours": [(str(p.relative_to(ROOT)), i + 1) for p, t in src.items() for i, ln in enumerate(t.split("\n")) if SINGLE_BIT.search(ln)],
            "single_bit_sdk": sum(len(SINGLE_BIT.findall(_text(p))) for p in sdk),
            "critical_ours": sum(len(re.findall(r"__critical\b", t)) for t in src.values()),
            "isr_shared_only": shared}


def _same(a: str, b: str) -> bool:
    """Map names cut at 32 chars (stub symbols), bank-local stub suffix _b<n>: equal, or one a >= 28-char prefix of the other."""
    a, b = re.sub(r"_b\d+$", "", a), re.sub(r"_b\d+$", "", b)
    return a == b or (min(len(a), len(b)) >= 28 and (a.startswith(b) or b.startswith(a)))


def profile_sites(stem: Path, cands: dict) -> dict:
    import fw_profile
    watch = {a for c in cands.values() for a in c["rets"]}
    with (ROOT / "tmp/logs/fw_profile.log").open("a") as lg:
        return fw_profile.profile(stem.with_suffix(".bin"), stem.with_suffix(".map"), 12, "-be" in stem.name, lg, 0, watch)


def main(argv: list[str], *, say=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="dev.py rules-report")
    ap.add_argument("--image", help="tmp/fw/<stem> of the tree's last build (for --profile)")
    ap.add_argument("--profile", action="store_true", help="#360 sites: fw_profile idle passes with the guard rets watched")
    a = ap.parse_args(argv)
    say = say or Logger(ROOT / "tmp/logs/dw8051_sweep.log").say
    files = our_files()
    sc = static_counts(files)
    say(f"constexpr in our files: {sc['constexpr']}; __sfr16: {sc['sfr16']}; __critical in our files: {sc['critical_ours']} (irq_masks gate checks them)")
    say(f"single-bit (x & M) == M: ours {len(sc['single_bit_ours'])} {sc['single_bit_ours'][:10]}; SDK files {sc['single_bit_sdk']}")
    say(f"isr_shared without volatile (non-static): {len(sc['isr_shared_only'])}")
    for f, ln in sc["isr_shared_only"]:
        say(f"  {f}: {ln}")
    stems = {p.stem for p in files if p.suffix == ".c"}
    parms = parm_slots(ROOT / "tmp/sdcc-port/asm", stems)
    by_area = defaultdict(int)
    for r in parms:
        by_area[r[3]] += 1
    say(f"_PARM_n slots in our modules: {len(parms)} {dict(by_area)}")
    for r in parms:
        say("  parm\t" + "\t".join(map(str, r)))
    fns = rst_functions(ROOT / "tmp/sdcc-port/asm_bank")
    ib = isr_banked(fns)
    say(f"banked calls reachable from ISRs: {len(ib)} edges, {len({x[2] for x in ib})} targets")
    for r in sorted(set(ib)):
        say("  isrbank\t" + "\t".join(map(str, r)))
    st = subprocess.run([sys.executable, str(ROOT / "scripts/fw_stack.py")], capture_output=True, text=True, cwd=ROOT, check=False).stdout
    say(f"recursion (fw_stack call-graph cycles): {json.loads(st[st.index('{'):st.rindex('}') + 1])['cycles'] if '{' in st else 'fw_stack failed'}")
    cands = guard_candidates(fns)
    sites = call_sites(fns, set(cands))
    say(f"#360 guard candidates: {len(cands)} banked functions, {len(sites)} call sites")
    prof = profile_sites(ROOT / a.image, cands) if a.profile and a.image else None
    out = ROOT / "tmp/dw8051/guard_sites.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = ["# calls = lcall entries per idle main pass (tail ljmp entries not counted); noop = executions of the guard ret\ncaller\tcaller_region\tcallee\tcallee_region\tguard_sym\tkind\tsite_calls_per_pass\tcallee_calls_per_pass\tnoop_per_pass\tnoop_fraction"]
    edges = (prof or {}).get("edges", {})
    for caller, creg, callee, kind in sorted(sites):
        c = cands[callee]
        ent = sum(v for k, v in edges.items() if _same(k.split()[-1], callee))
        site = sum(v for k, v in edges.items() if _same(k.split()[0], caller) and _same(k.split()[-1], callee))
        noop = sum((prof or {}).get("watch", {}).get(r, 0) for r in c["rets"])
        p = f"{noop / ent:.3f}" if ent else ""
        rows.append("\t".join(map(str, [caller, creg, callee, region(c["addr"]), c["sym"], kind,
                                        f"{site:.2f}" if prof else "", f"{ent:.2f}" if prof else "", f"{noop:.2f}" if prof else "", p])))
    out.write_text("\n".join(rows) + "\n")
    say(f"guard sites: {out}" + (f" (profile {prof['passes']} idle passes, {prof['cycles_per_pass']:.0f} cycles/pass)" if prof else ""))
    return 0


if __name__ == "__main__":
    sys.exit("dw8051_sweep.py is internal: run ./dev.py rules-report")
