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


def dseg_extent(map_text, rels):
    """Real DSEG (lo, hi): sdld reports a synthetic total from 0x00; real = lowest DSEG symbol + .rel size sum."""
    dsec = re.search(r"^DSEG\s+[0-9A-F]{8}[^\n]*\n(.*?)(?=^Area|\Z)", map_text, re.M | re.S)
    dsyms = [int(a, 16) for a in re.findall(r"^\s+([0-9A-F]{8})\s+\w+", dsec.group(1), re.M)] if dsec else []
    dtot = rel_sizes(rels)[0].get("DSEG", 0)
    return (min(dsyms), min(dsyms) + dtot) if dsyms and dtot else None


def dseg_runs(map_text, rels, mem: Path | None = None):
    """Real DSEG ranges [(lo, hi)]. sdld puts each module's DSEG part in the first free gap, so DSEG splits around the
    bit bytes at 0x20; its map line is a synthetic total from 0x00. From the -M grid (.mem) when present, else lowest
    DSEG symbol + .rel total (contiguous assumption).
    - Grid letters a..z = DATA areax parts in allocation order: DSEG first (every module opens it), then the DDOVL* areas
      (__ovl.asm), shown at sdld's own first fit, not their -b address: trailing letters sized like a DDOVL area drop."""
    if mem is not None and mem.exists():
        g = {}
        for m in re.finditer(r"^0x([0-9a-f]{2}):((?:\|.){16})\|", mem.read_text(errors="replace"), re.M):
            for i, ch in enumerate(m.group(2)[1::2]):
                g[int(m.group(1), 16) + i] = ch
        letters = sorted({ch for ch in g.values() if ch.islower()})
        if "D" not in g.values():                       # 'D' = sdld ran out of letters: order unknown, fall back
            ovl = [v for v in rel_sizes(rels)[2].values() if v]
            size = {ch: sum(1 for x in g.values() if x == ch) for ch in letters}
            while letters and size[letters[-1]] in ovl:   # trailing parts the size of a DDOVL area (sdld may omit some)
                ovl.remove(size[letters.pop()])
            keep = set(letters)
            runs = []
            for a in sorted(x for x, ch in g.items() if ch in keep and x < DIRECT_END):
                if runs and runs[-1][1] == a:
                    runs[-1][1] = a + 1
                else:
                    runs.append([a, a + 1])
            return [tuple(r) for r in runs]
    d = dseg_extent(map_text, rels)
    return [d] if d else []


def holes_from_map(map_text, rels, mem: Path | None = None):
    """Direct-RAM holes left by the areas sdld places itself (it ignores -b for OSEG)."""
    used = []
    for m in MAP_AREA.finditer(map_text):
        lo, n = int(m.group(2), 16), int(m.group(3), 16)
        if m.group(1) == "DSEG":
            continue
        if n and lo < DIRECT_END:
            used.append((lo, lo + n))
    used += dseg_runs(map_text, rels, mem)
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
    mapf, memf = ihx.with_suffix(".map"), ihx.with_suffix(".mem")
    memf.unlink(missing_ok=True)                        # -M grid; absent when _sdld relinked without -M (banked)
    r = run(park + [f"-Wl-aISEG=0x{cur:x}"])
    if r.returncode or not mapf.exists():
        return r, {}
    holes, used = holes_from_map(mapf.read_text(errors="replace"), rels, memf)
    base = {}
    for name, size in sorted(ddovl.items(), key=lambda kv: -kv[1]):
        h = next((h for h in holes if h[1] - h[0] >= size), None)
        if h is None:
            r.returncode = 1
            r.stdout += f"\nIRAM layout: {name} ({size} B) does not fit direct holes {[(hex(a), b - a) for a, b in holes]}\n"
            return r, {"used": used}
        base[name] = h[0]; h[0] += size
    base["ISEG"] = ISEG_BASE
    memf.unlink(missing_ok=True)
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
    iram = [x for x in iram if x[2] != "DSEG"] + [(*d, "DSEG") for d in dseg_runs(mt, rels, memf)]
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
