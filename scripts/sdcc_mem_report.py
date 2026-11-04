#!/usr/bin/env python3
"""RAM allocation report for an SDCC -S tree: every XDATA/DATA/BIT storage label with size, sorted.

usage: sdcc_mem_report.py [--asm DIR] [--top N] [--kind global|local|all]
- Areas: XSEG (uninit xdata), XISEG (initialised xdata, copied from flash at boot), DSEG/ISEG (internal),
  BSEG (bits). Locals classified via SDCC 'Allocated with name' comments (same as sdcc_overlay.py).
- Flags per global: `init` (XISEG: candidate for __code if never written), `wr=0` when no store to it is
  found in any module (movx @dptr,a after mov dptr,#sym) -> likely read-only -> move to flash.
Output: table to stdout + tmp/sdcc-port/mem_report.json. Log: tmp/logs/sdcc_mem_report.log. Tracking: #8.
"""
import json, os, re, subprocess, sys, time
from collections import Counter, defaultdict
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


AREAS = ("XSEG", "XISEG", "DSEG", "ISEG", "BSEG", "OSEG")


def main():
    a = sys.argv[1:]
    root = repo_root()
    asm_dir = Path(a[a.index("--asm") + 1]) if "--asm" in a else root / "tmp/sdcc-port/asm"
    top = int(a[a.index("--top") + 1]) if "--top" in a else 60
    kind = a[a.index("--kind") + 1] if "--kind" in a else "global"
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/sdcc_mem_report.log").open("a")

    def out(s):
        print(s); log.write(s + "\n")
    items, writes = [], Counter()
    for p in sorted(asm_dir.rglob("*.asm")):
        lines = p.read_text(errors="replace").split("\n")
        local = {m.group(1) for l in lines for m in [re.match(r"^;\w+\s+Allocated with name '(\w+)'", l)] if m}
        area = None
        for i, line in enumerate(lines):
            if line.startswith("\t.area"):
                area = line.split()[1]
                continue
            lab = re.match(r"^(\w+)(::?)$", line)
            if lab and area in AREAS and i + 1 < len(lines) and lines[i + 1].strip().startswith((".ds", ".db")):
                ds = lines[i + 1].split()
                size = int(ds[1], 0) if ds[0] == ".ds" else 1
                if area == "BSEG":
                    size = int(ds[1], 0)                 # bits
                k = "local" if lab.group(1) in local else ("sloc" if "sloc" in lab.group(1) else "global")
                items.append({"sym": lab.group(1), "area": area, "size": size, "kind": k, "module": p.stem})
            # stores: mov dptr,#(sym[+n]) ... movx @dptr,a  (within the next few lines)
            m = re.match(r"^\s+mov\s+dptr,#\(?(_\w+)", line)
            if m and any(re.match(r"^\s+movx\s+@dptr,a", lines[j]) for j in range(i + 1, min(i + 4, len(lines)))):
                writes[m.group(1)] += 1
            m = re.match(r"^\s+mov\s+(_\w+),", line)               # direct DATA store
            if m:
                writes[m.group(1)] += 1
    for it in items:
        it["writes"] = writes.get(it["sym"], 0)
    sel = [it for it in items if kind == "all" or it["kind"] == kind]
    tot = defaultdict(int)
    for it in items:
        tot[(it["area"], it["kind"])] += it["size"]
    out(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {asm_dir}: {len(items)} allocations")
    for (ar, k), v in sorted(tot.items()):
        out(f"  {ar:6s} {k:7s} {v:6d} {'bits' if ar == 'BSEG' else 'B'}")
    by_mod = defaultdict(int)
    for it in items:
        if it["area"] in ("XSEG", "XISEG") and it["kind"] == "global":
            by_mod[it["module"]] += it["size"]
    out("XDATA globals by module (top 20):")
    for mname, v in sorted(by_mod.items(), key=lambda kv: -kv[1])[:20]:
        out(f"  {v:6d}  {mname}")
    out(f"largest {kind} allocations:")
    for it in sorted(sel, key=lambda it: -it["size"])[:top]:
        flag = ("init " if it["area"] == "XISEG" else "") + ("wr=0 READ-ONLY?" if it["writes"] == 0 and
                                                             it["area"] in ("XSEG", "XISEG") else "")
        out(f"  {it['size']:6d} {it['area']:6s} {it['sym']:48s} {it['module']:32s} {flag}")
    ro = [it for it in items if it["area"] in ("XSEG", "XISEG") and it["kind"] == "global" and it["writes"] == 0]
    out(f"globals with no store found: {len(ro)}, {sum(it['size'] for it in ro)} B (verify: pointer writes miss)")
    (root / "tmp/sdcc-port").mkdir(parents=True, exist_ok=True)
    (root / "tmp/sdcc-port/mem_report.json").write_text(json.dumps(items, indent=0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
