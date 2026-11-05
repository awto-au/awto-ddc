#!/usr/bin/env python3
"""SDCC mcs51 link with an explicit internal-RAM layout (shared by sim_test.py and fw_build.py).

sdld places the stack right after the areas it knows (DSEG/OSEG/BSEG_BYTES/ISEG) and ignores other DATA
areas such as the per-region overlay blocks DDOVL* (sdcc_overlay.py); `--stack-loc` is deprecated/ignored.
sdld also ignores -b for OSEG. So: pass 1 parks DDOVL* in idata and reads where sdld put DSEG/OSEG/bits/
register banks; pass 2 fits DDOVL* (largest first) into the remaining direct holes < 0x80; ISEG at 0x80,
stack after it (sdld).
usage (library): link(cmd, ihx, rels) -> (CompletedProcess, layout dict)
"""
import re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_tools as T  # noqa: E402

LINK_TIMEOUT = 120          # full firmware link ~20 s (2026-11-04); stall guard, awto-dan#53
DIRECT_END = 0x80           # direct addressing above 0x7F hits SFRs
ISEG_BASE = 0x80


def rel_sizes(rels):
    tot, ovr, ddovl = {}, {}, {}
    for r in rels:
        for m in re.finditer(r"^A (\w+) size (\w+) flags (\w+)", Path(r).read_text(errors="replace"), re.M):
            name, size, flags = m.group(1), int(m.group(2), 16), int(m.group(3), 16)
            if name.startswith("DDOVL"):
                ddovl[name] = ddovl.get(name, 0) + size
            elif flags & 0x04:                                 # OVR: areas overlap, size = max
                ovr[name] = max(ovr.get(name, 0), size)
            else:
                tot[name] = tot.get(name, 0) + size
    return tot, ovr, ddovl


def _sdld(cmd, ihx: Path):
    """sdcc link; if the only error is sdld's -M ROM summary (wrong for code above 64 KB: it wraps banks onto
    each other), relink with sdld directly without -M. Verified 2026-11-04 on a 2-bank test: ihx correct."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=LINK_TIMEOUT)
    errs = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "ERROR" in l]
    if r.returncode and errs and all("Insufficient ROM" in l for l in errs) and ihx.with_suffix(".lk").exists():
        lk = ihx.with_suffix(".lk")
        nolk = ihx.with_name(ihx.stem + "_nom.lk")
        nolk.write_text("\n".join(l for l in lk.read_text().splitlines() if l.strip() != "-M") + "\n")
        r = subprocess.run([T.tool("sdld"), "-nf", str(nolk)], capture_output=True, text=True, timeout=LINK_TIMEOUT)
        if r.returncode == 2 and "Error" not in r.stdout + r.stderr:      # rc 2 = warnings only
            r.returncode = 0
    return r


MAP_AREA = re.compile(r"^(REG_BANK_\d|DSEG|OSEG|BSEG_BYTES|BIT_BANK)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", re.M)


def holes_from_map(map_text):
    """Direct-RAM holes left by the areas sdld places itself (it ignores -b for OSEG)."""
    used = []
    for m in MAP_AREA.finditer(map_text):
        lo, n = int(m.group(2), 16), int(m.group(3), 16)
        if n and lo < DIRECT_END:
            used.append((lo, lo + n))
    holes, cur = [], 0
    for lo, hi in sorted(used):
        if lo > cur:
            holes.append([cur, lo])
        cur = max(cur, hi)
    holes.append([cur, DIRECT_END])
    return holes, used


def link(cmd, ihx: Path, rels):
    """Pass 1: overlay areas parked in idata, read where sdld put DSEG/OSEG/bits/banks.
    Pass 2: overlay areas first fit (largest first) into the direct holes; ISEG at 0x80, stack after it."""
    _, _, ddovl = rel_sizes(rels)
    run = lambda wl: _sdld(list(map(str, cmd)) + wl, ihx)
    park, cur = [], ISEG_BASE
    for k, v in ddovl.items():
        park.append(f"-Wl-a{k}=0x{cur:x}"); cur += v
    r = run(park + [f"-Wl-aISEG=0x{cur:x}"])
    mapf = ihx.with_suffix(".map")
    if r.returncode or not mapf.exists():
        return r, {}
    holes, used = holes_from_map(mapf.read_text(errors="replace"))
    base = {}
    for name, size in sorted(ddovl.items(), key=lambda kv: -kv[1]):
        h = next((h for h in holes if h[1] - h[0] >= size), None)
        if h is None:
            r.returncode = 1
            r.stdout += f"\nIRAM layout: {name} ({size} B) does not fit direct holes {[(hex(a), b - a) for a, b in holes]}\n"
            return r, {"used": used}
        base[name] = h[0]; h[0] += size
    base["ISEG"] = ISEG_BASE
    r = run([f"-Wl-a{k}=0x{v:x}" for k, v in base.items()])
    if r.returncode:
        return r, {}
    mt = mapf.read_text(errors="replace")
    m = re.search(r"^\s+([0-9A-F]{8})\s+__start__stack\b", mt, re.M)
    stack = int(m.group(1), 16) if m else None
    # own overlap check (the -M summary that would do it is skipped for banked links)
    iram = [(int(a, 16), int(a, 16) + int(n, 16), k) for k, a, n in
            re.findall(r"^(REG_BANK_\d|DSEG|OSEG|ISEG|BSEG_BYTES|BIT_BANK|DDOVL\w*)\s+([0-9A-F]{8})\s+([0-9A-F]{8})", mt, re.M)
            if int(n, 16)]
    # sdld reports DSEG from 0x00 (over REG_BANK_0); real extent = first DSEG symbol + .rel total
    iram = [x for x in iram if x[2] != "DSEG"]
    dsec = re.search(r"^DSEG\s+[0-9A-F]{8}.*?\n(?=\S)(.*?)(?=^Area|\Z)", mt, re.M | re.S)
    dsyms = [int(a, 16) for a in re.findall(r"^\s+([0-9A-F]{8})\s+\w+", dsec.group(1), re.M)] if dsec else []
    dtot = rel_sizes(rels)[0].get("DSEG", 0)
    if dsyms and dtot:
        iram.append((min(dsyms), min(dsyms) + dtot, "DSEG"))
    iram = sorted(set(iram))
    clash = [(x[2], y[2]) for x, y in zip(iram, iram[1:]) if y[0] < x[1] and not (x[2] == y[2])]
    top = max((hi for _, hi, _ in iram), default=0)
    if clash or stack is None or stack < top:
        r.returncode = 1
        r.stdout += f"\nIRAM check: overlaps {clash}, stack {stack} vs top 0x{top:x}\n"
    info = {"base": {k: hex(v) for k, v in base.items()}, "used": [(hex(a), b - a) for a, b in used],
            "free_direct": [(hex(a), b - a) for a, b in holes if b > a], "stack_start": stack,
            "stack_bytes": 0x100 - (stack or 0x100)}
    return r, info


if __name__ == "__main__":
    print(__doc__); sys.exit(0)
