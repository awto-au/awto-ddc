#!/usr/bin/env python3
"""Diff two fw_sim_trace.py TSVs (vendor vs ours) over DISPLAY_SETTING -> ACTIVE (#26).

usage: trace_diff.py A.tsv B.tsv [--noise-regs ...]   -> stdout + tmp/logs/trace_diff.log
  Window = first STATE DISPLAY_SETTING .. first following STATE ACTIVE. Compared on (register, index) write streams with
  consecutive repeats collapsed, polling-only registers (OSD port, event clears) dropped.
  Reports: key-event order/time (first write per marker register, CALL markers), registers only in A / only in B,
  final-value differences, first divergence of the ordered streams (difflib).
"""
import argparse, difflib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOISE = {0x0090, 0x0091, 0x0092, 0x0094, 0x006C, 0x006D, 0x0003, 0x0005, 0x4003, 0x0002, 0x000C, 0x0060, 0x0061, 0x0062}
MARK = {"VGIP_CTRL P0_10": 0x0010, "M1 FIFO/SF P0_30": 0x0030, "P0_28 display ctrl": 0x0028, "P0_2F disp DB": 0x002F, "P31_C0 I_DB": 0x31C0,
        "P5_27 CAP DDR ctrl1": 0x0527, "P5_AC DISP ctrl1": 0x05AC, "P1_C3 DPLL cal": 0x01C3, "P0_32 scale": 0x0032, "P31_06 FtoP": 0x3106,
        "P30_00 meas": 0x3000, "P0_7D auto-func": 0x007D}


def load(p):
    rows = [l.rstrip("\n").split("\t") for l in Path(p).read_text().splitlines()[1:]]
    ds = next(i for i, r in enumerate(rows) if r[6] == "STATE" and r[8] == "DISPLAY_SETTING")
    end = next((i for i in range(ds, len(rows)) if rows[i][6] == "STATE" and rows[i][8] == "ACTIVE"), len(rows) - 1)
    return rows, ds, end


def stream(rows, ds, end):
    out = []
    for r in rows[ds:end + 1]:
        if r[6] != "W" or int(r[7], 16) in NOISE:
            continue
        k = (int(r[7], 16), r[9])
        if out and out[-1][0] == k and out[-1][1] == r[10]:
            continue
        out.append((k, r[10], float(r[2]), r[8], r[5]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    a = ap.parse_args()
    L = []
    P = lambda s="": (L.append(s), print(s))
    data = {}
    for tag, p in (("A", a.a), ("B", a.b)):
        rows, ds, end = load(p)
        t0 = float(rows[ds][2])
        data[tag] = (rows, ds, end, t0, stream(rows, ds, end))
        P(f"{tag} {Path(p).name}: DISPLAY_SETTING at fw_ms {t0}, ACTIVE at {rows[end][2]} (+{float(rows[end][2]) - t0:.0f} ms), "
          f"{end - ds + 1} rows, {len(data[tag][4])} collapsed writes")
    P("\n== CALL markers (first call, ms after DISPLAY_SETTING) ==")
    for tag in "AB":
        rows, ds, end, t0, _ = data[tag]
        seen = {}
        for r in rows[ds:end + 1]:
            if r[6] == "CALL":
                seen.setdefault(r[8], []).append(float(r[2]) - t0)
        P(f"{tag}: " + "; ".join(f"{n} x{len(v)} @{v[0]:.0f}" for n, v in sorted(seen.items(), key=lambda kv: kv[1][0])))
    P("\n== first write per marker register (ms after DISPLAY_SETTING: value, count) ==")
    for name, ad in MARK.items():
        cells = []
        for tag in "AB":
            rows, ds, end, t0, _ = data[tag]
            w = [r for r in rows[ds:end + 1] if r[6] == "W" and int(r[7], 16) == ad]
            cells.append(f"{tag}: {float(w[0][2]) - t0:6.0f} {w[0][10]} x{len(w)}" if w else f"{tag}: never")
        P(f"{name:<22} " + " | ".join(cells))
    sa, sb = data["A"][4], data["B"][4]
    ka, kb = {x[0] for x in sa}, {x[0] for x in sb}
    nm = lambda s, k: next(x[3] for x in s if x[0] == k)
    P(f"\n== registers written only by A ({len(ka - kb)}) ==")
    for k in sorted(ka - kb):
        P(f"  {k[0]:04X}{'[' + k[1] + ']' if k[1] else ''} {nm(sa, k)} first value {next(x[1] for x in sa if x[0] == k)}")
    P(f"\n== registers written only by B ({len(kb - ka)}) ==")
    for k in sorted(kb - ka):
        P(f"  {k[0]:04X}{'[' + k[1] + ']' if k[1] else ''} {nm(sb, k)} first value {next(x[1] for x in sb if x[0] == k)}")
    la, lb = {x[0]: x[1] for x in sa}, {x[0]: x[1] for x in sb}
    la = {}; lb = {}
    for x in sa: la[x[0]] = x[1]
    for x in sb: lb[x[0]] = x[1]
    d = [k for k in sorted(la.keys() & lb.keys()) if la[k] != lb[k]]
    P(f"\n== final value differs ({len(d)}) ==")
    for k in d:
        P(f"  {k[0]:04X}{'[' + k[1] + ']' if k[1] else ''} {nm(sa, k)}  A {la[k]}  B {lb[k]}")
    P("\n== first divergence of ordered (reg,idx,value) streams ==")
    ta, tb = [(x[0], x[1]) for x in sa], [(x[0], x[1]) for x in sb]
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    n = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        n += 1
        if n > 25:
            break
        P(f"  {op}: A[{i1}:{i2}] " + " ".join(f"{x[0][0]:04X}{'[' + x[0][1] + ']' if x[0][1] else ''}={x[1]}" for x in sa[i1:i2][:8])
          + f"  |  B[{j1}:{j2}] " + " ".join(f"{x[0][0]:04X}{'[' + x[0][1] + ']' if x[0][1] else ''}={x[1]}" for x in sb[j1:j2][:8]))
    P(f"  ratio {sm.ratio():.3f}")
    (ROOT / "tmp/logs/trace_diff.log").write_text("\n".join(L) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
