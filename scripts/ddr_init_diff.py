#!/usr/bin/env python3
"""DDR2 init sequence, vendor vs ours, from fw_sim_trace.py --ddr traces (#26).

usage: ddr_init_diff.py VENDOR.tsv.gz OURS.tsv.gz [--until-ms 400] [--out tmp/logs/ddr_init_diff.txt]
  Per trace: DDR-page writes collapsed to DWORD stores (consecutive byte writes to one aligned DWORD; big-endian, lowest
  address = MSB) + DDR/delay/poll CALL rows, in order, with sim fw_ms and the delta to the previous step.
  Diff: difflib on (reg, value) of the DWORD stores; value-only differences, missing/extra stores and order changes listed.
  fw_ms is sim time (instr / 12.6 k): relative step spacing, not hardware time; polls never see lock in the sim.
Log: tmp/logs/ddr_init_diff.log (+ --out)
"""
import argparse, difflib, gzip, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(p, until_ms):
    rows = [l.split("\t") for l in gzip.open(p, "rt").read().splitlines()][1:]
    seq, cur = [], None
    for r in rows:
        ms = float(r[2])
        if ms > until_ms:
            break
        if r[6] == "CALL":
            cur = None
            seq.append(dict(kind="CALL", ms=ms, name=r[8], args=r[9], instr=int(r[1])))
            continue
        if r[6] != "W":
            continue
        a, v = int(r[7], 16), int(r[10], 16)
        base = a & ~3
        if cur and cur["base"] == base and a not in cur["bytes"] and a > max(cur["bytes"]):
            cur["bytes"][a] = v
            cur["end_ms"] = ms
            continue
        cur = dict(kind="W", ms=ms, end_ms=ms, base=base, bytes={a: v}, fn=r[5].split("+")[0], instr=int(r[1]))
        seq.append(cur)
    for e in seq:
        if e["kind"] == "W":
            b = e["bytes"]
            e["reg"] = f"{e['base']:04X}" + ("" if len(b) == 4 else "." + "".join(f"{x & 3}" for x in sorted(b)))
            e["val"] = "".join(f"{b[x]:02x}" if x in b else "--" for x in range(e["base"], e["base"] + 4))
    return seq


def fmt(e, prev):
    d = f"+{(e['instr'] - prev) / 12600:.3f}" if prev is not None else ""
    if e["kind"] == "CALL":
        return f"{e['ms']:9.3f} {d:>9}  CALL {e['name']}  {e['args']}"
    return f"{e['ms']:9.3f} {d:>9}  W {e['reg']:<8} {e['val']}  {e['fn']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vendor"); ap.add_argument("ours")
    ap.add_argument("--until-ms", type=float, default=400.0, help="cut the traces here (sim fw_ms; boot DDR init is < 200)")
    ap.add_argument("--out", default=str(ROOT / "tmp/logs/ddr_init_diff.txt"))
    a = ap.parse_args()
    V, O = load(a.vendor, a.until_ms), load(a.ours, a.until_ms)
    L = []
    for tag, S in (("vendor", V), ("ours", O)):
        L.append(f"## {tag}: {sum(e['kind'] == 'W' for e in S)} DWORD stores, {sum(e['kind'] == 'CALL' for e in S)} calls (<= {a.until_ms} ms)")
        prev = None
        for e in S:
            L.append("  " + fmt(e, prev)); prev = e["instr"]
    kv = [(e["reg"], e["val"]) for e in V if e["kind"] == "W"]
    ko = [(e["reg"], e["val"]) for e in O if e["kind"] == "W"]
    sm = difflib.SequenceMatcher(None, kv, ko, autojunk=False)
    L.append(f"\n## diff of DWORD stores (reg, value): vendor {len(kv)} / ours {len(ko)}, ratio {sm.ratio():.4f}")
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            L.append(f"  {op}: vendor[{i1}:{i2}] " + " ".join(f"{r}={v}" for r, v in kv[i1:i2]) + f"  |  ours[{j1}:{j2}] " + " ".join(f"{r}={v}" for r, v in ko[j1:j2]))
    fv = {}
    for r, v in kv:
        fv[r] = v
    fo = {}
    for r, v in ko:
        fo[r] = v
    L.append("\n## final value per DWORD (sim, at --until-ms), differences only")
    for r in sorted(set(fv) | set(fo)):
        if fv.get(r) != fo.get(r):
            L.append(f"  {r}: vendor {fv.get(r, '-')} ours {fo.get(r, '-')}")
    Path(a.out).write_text("\n".join(L) + "\n")
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/logs/ddr_init_diff.log").write_text("\n".join(L) + "\n")
    print("\n".join(l for l in L if l.startswith("##")), "->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
