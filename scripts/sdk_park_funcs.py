#!/usr/bin/env python3
"""Park whole-feature `#if` blocks of function bodies from fw/sdk to fw/sdk-parked (same relative path) (#305, #44).

usage: sdk_park_funcs.py plan                 blocks that would move -> stdout
       sdk_park_funcs.py move                 cut them from fw/sdk, write fw/sdk-parked/<path> (self-contained units)
       sdk_park_funcs.py restore [PATH ...]   append the parked units back to fw/sdk/<path>, delete the parked file
- Block = `#if(<FEATURE> == _ON)` at function level (brace depth 0), no `#else`, >= 1 function definition, FEATURE in FEATURES.
- Unit in the parked file = the block wrapped in its enclosing `#if` lines, so a unit is valid C on its own.
- Headers and local prototypes stay (the build needs them); only bodies move.
Log: ./tmp/logs/sdk_park_funcs.log
"""
import re
import sys

import isostamp
from _repo import ROOT

SDK, PARK = ROOT / "fw/sdk", ROOT / "fw/sdk-parked"
FILES = ["Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c",
         "Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDPRx1.c",
         "Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonSync.c"]
FEATURES = {"_DP_MST_SUPPORT": "mst", "_DP_HDCP_2_2_SUPPORT": "hdcp", "_DP_HDCP14_CTS_SUPPORT": "hdcp",
            "_DP_FREESYNC_SUPPORT": "freesync", "_FREESYNC_SUPPORT": "freesync", "_FREESYNC_II_SUPPORT": "freesync"}
PURE = re.compile(r"^#if\s*\(\s*(\w+)\s*==\s*_ON\s*\)\s*(//.*)?$")
FUNC = re.compile(r"^[A-Za-z_][\w \*]*?\b(\w+)\s*\([^;]*$")
HEADER = "// Parked from fw/sdk/{rel} (#305, #44): append to the live file to restore (scripts/sdk_park_funcs.py restore).\n"
LOG = None


def log(s):
    line = f"{isostamp.now()} {s}"
    print(line)
    LOG.write(line + "\n")
    LOG.flush()


def code_braces(line, in_comment):
    """Net brace count of one line, ignoring comments / strings / chars; returns (net, still_in_block_comment)."""
    net, i, n = 0, 0, len(line)
    while i < n:
        two = line[i:i + 2]
        if in_comment:
            if two == "*/":
                in_comment, i = False, i + 1
        elif two == "/*":
            in_comment, i = True, i + 1
        elif two == "//":
            break
        elif line[i] in "\"'":
            q, i = line[i], i + 1
            while i < n and line[i] != q:
                i += 2 if line[i] == "\\" else 1
        elif line[i] == "{":
            net += 1
        elif line[i] == "}":
            net -= 1
        i += 1
    return net, in_comment


def scan(lines):
    """Return (blocks, funcs): blocks[start] = dict(end, parent, depth0, has_else); funcs = [(line, name, [open starts])]."""
    stack, blocks, funcs, depth, cmt = [], {}, [], 0, False
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not cmt and s.startswith("#if"):
            parent = stack[-1] if stack else None
            blocks[i] = {"end": None, "parent": parent, "depth0": depth == 0, "has_else": False, "cond": s}
            stack.append(i)
        elif not cmt and s.startswith(("#else", "#elif")) and stack:
            blocks[stack[-1]]["has_else"] = True
        elif not cmt and s.startswith("#endif") and stack:
            blocks[stack.pop()]["end"] = i
        m = FUNC.match(raw)
        if m and not cmt and not raw.startswith((" ", "\t", "#")) and i < len(lines) and lines[i].strip() == "{":
            funcs.append((i, m.group(1), list(stack)))
        net, cmt = code_braces(raw, cmt)
        depth += net
    return blocks, funcs


def pick(lines):
    """Outermost feature blocks to move: [(start, end, group, [function names])]."""
    blocks, funcs = scan(lines)
    picked = []
    for start in sorted(blocks):
        b = blocks[start]
        m = PURE.match(b["cond"])
        if not (m and m.group(1) in FEATURES and b["depth0"] and not b["has_else"] and b["end"]):
            continue
        if any(start > p[0] and b["end"] < p[1] for p in picked):
            continue
        names = [n for ln, n, st in funcs if start in st]
        if names:
            picked.append((start, b["end"], FEATURES[m.group(1)], names, blocks))
    return [(s, e, g, n, bl) for s, e, g, n, bl in picked]


def chain(blocks, start):
    out, p = [], blocks[start]["parent"]
    while p is not None:
        out.append(p)
        p = blocks[p]["parent"]
    return out[::-1]


def plan_file(rel):
    lines = (SDK / rel).read_text(encoding="latin-1").split("\n")
    return lines, pick(lines)


def cmd_plan():
    for rel in FILES:
        lines, picked = plan_file(rel)
        for s, e, g, names, _ in picked:
            log(f"{rel.split('/')[-1]} {s}-{e} {g} {e - s + 1} lines {len(names)} fn: {lines[s - 1].strip()}")


def cmd_move():
    for rel in FILES:
        lines, picked = plan_file(rel)
        if not picked:
            continue
        units = []
        for s, e, g, names, blocks in picked:
            wraps = [lines[p - 1] for p in chain(blocks, s)]
            units.append("\n".join(wraps + lines[s - 1:e] + ["#endif"] * len(wraps)))
        cut = {i for s, e, *_ in picked for i in range(s, e + 1)}
        kept = [ln for i, ln in enumerate(lines, 1) if i not in cut]
        (SDK / rel).write_text("\n".join(kept), encoding="latin-1")
        out = PARK / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(HEADER.format(rel=rel) + "\n" + "\n\n".join(units) + "\n", encoding="latin-1")
        log(f"moved {len(picked)} blocks, {len(cut)} lines, {sum(len(p[3]) for p in picked)} functions: {rel} -> fw/sdk-parked")


def cmd_restore(paths):
    for rel in paths or FILES:
        src = PARK / rel
        if not src.exists():
            continue
        body = "".join(ln for ln in src.read_text(encoding="latin-1").splitlines(True) if not ln.startswith("// Parked from"))
        live = SDK / rel
        text = live.read_text(encoding="latin-1").rstrip("\n") + "\n\n" + body.lstrip("\n")
        live.write_text(text, encoding="latin-1")
        src.unlink()
        log(f"restored {rel}")


def main():
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdk_park_funcs.log").open("a")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "plan":
        cmd_plan()
    elif cmd == "move":
        cmd_move()
    elif cmd == "restore":
        cmd_restore(sys.argv[2:])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
