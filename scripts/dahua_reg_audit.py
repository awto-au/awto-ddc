#!/usr/bin/env python3
"""Merge all banks' register reads/writes of the Dahua firmware into one row per register address.

usage: dahua_reg_audit.py [--src DIR] [--out FILE]
- Input: <src>/bank<N>/{regreads,regwrites}.tsv (re/ghidra/ExportRegAccess.java output; src default ~/vendors-analysis jxc-4k).
- DB lookup by address in re/regdb/RTD2795T-CG.tsv.gz (REG + FIELD rows, MCU 0xFFxx included).
- Class: XRAM (0xD700-0xF6FF, not registers), REG (scaler/MCU space), UNRESOLVED ('?' address, indirect pointer) summarised by function.
- Flag rsv1: a write sets a 1 into a field named reserved/dummy (only 'set' value and 'rmw' or_mask are checked).
- ours_w column: write count in our firmware's sim trace (--ours, fw_sim_trace.py TSV.gz; boot -> ACTIVE only, so a gap is not proof).
- '?' rows (export could not name the address) are resolved a second time: (1) DPTR constant propagation with callee summaries
  (scripts/dahua_dptr_flow.py, checked against the 5447 sites the export resolved: 0 disagreements), (2) the Dahua sim traces
  (write site pc-1 == export insn). Extra sites go to columns extra_r / extra_w (unique sites; common code counted once).
Output: re/jxc-4k/reg_audit.tsv, reg_audit_resolved.tsv (site, address, via), reg_audit_unresolved.tsv (remaining '?' sites + reason); log: ./tmp/logs/dahua_reg_audit.log
"""
import argparse, csv, gzip, os, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dahua_dptr_flow as DF  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
SRC = Path("/mnt/2tb/vendors/realtek/analysis/jxc-4k")
DBF = ROOT / "re" / "regdb" / "RTD2795T-CG.tsv.gz"
LOG = ROOT / "tmp" / "logs" / "dahua_reg_audit.log"
RAM = range(0xD700, 0xF700)
BANKS = SRC.parent / "banks"
COMMON = DF.COMMON


def log(msg, fh=[None]):
    if fh[0] is None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        fh[0] = open(LOG, "w")
    print(msg)
    fh[0].write(msg + "\n")
    fh[0].flush()


def load_db():
    regs, fields = {}, defaultdict(list)
    for r in csv.DictReader(gzip.open(DBF, "rt", newline=""), delimiter="\t"):
        a = int(r["address"], 0)
        if r["kind"] == "REG":
            regs.setdefault(a, r["register"])
        else:
            fields[a].append((int(r["bit_high"]), int(r["bit_low"]), r["field"]))
    return regs, fields


def rows(path):
    with open(path, newline="") as f:
        lines = [l for l in f if not l.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def intv(s):
    try:
        return int(s, 0)
    except (ValueError, TypeError):
        return None


def rsv_bits(fields, a):
    m = 0
    for h, l, n in fields.get(a, ()):
        if any(k in n.lower() for k in ("reserved", "dummy", "rsv")):
            m |= ((1 << (h - l + 1)) - 1) << l
    return m


def function_entries(src, b):
    """every Ghidra function entry of one bank program (disassembly.asm headers)"""
    out = set()
    for line in open(src / f"bank{b}" / "disassembly.asm", errors="replace"):
        if line.startswith("; ==== ") and " @ CODE:" in line:
            out.add(int(line.split(" @ CODE:")[1].split()[0], 16))
    return out


def resolve_pending(pend, acc, dynpc, src):
    """second pass over the '?' rows: DPTR flow, caller-supplied DPTR of small helpers, then sim pc. Returns (stat Counter, left list)."""
    banks = {b: (BANKS / f"bank{b}.bin").read_bytes() for b in range(7)}
    fl = DF.Flow(banks)
    for b in range(7):
        for ea in sorted(function_entries(src, b)):
            if b == 0 or ea >= COMMON:
                fl.function(b, ea)
    seen, stat, left, bad, done = set(), Counter(), [], [], []
    for kind, b, r in pend:
        ia, fa = int(r["insn"], 16), int(r["func_addr"], 16)
        key = (kind, ia if ia < COMMON else (b, ia))
        if key in seen:
            continue
        seen.add(key)
        stat[kind + "_sites"] += 1
        op = fl.opcode(b, ia)
        addrs, via, why = [], "", ""
        if op in (0xF0, 0xE0):
            st = fl.site_state(b, fa, ia)
            if isinstance(st, int):
                addrs, via = [st], "flow"
            elif isinstance(st, tuple):
                vals, unk, n = fl.entry_values(b, fa)
                ints = sorted((v + st[1]) & 0xFFFF for v in vals)
                if not n:
                    why = "dptr from caller: no direct caller (indirect call, ISR or table)"
                elif unk:
                    why = f"dptr from caller: {unk} of {n} callers not constant"
                elif len(ints) > 8:
                    why = f"dptr from caller: {len(ints)} different constants (indexed / loop over blocks)"
                else:
                    addrs, via = ints, "caller"
            else:
                why = "dptr not reached" if st is None else f"dptr {st.why}"
        elif op in (0xF2, 0xF3, 0xE2, 0xE3):
            why = "movx @Ri (page in P2)"
        else:
            why = f"{r['kind']} store via {r['callee'] or 'helper'} (dest from caller)"
        pcs = dynpc.get(ia if ia < COMMON else (b, ia)) if kind == "w" else None
        if addrs and pcs:                       # cross-check static result against the sim
            stat["check_sites"] += 1
            if set(pcs) <= set(addrs):
                stat["check_ok"] += 1
            else:
                stat["check_bad"] += 1
                bad.append((via, b, r["insn"], r["func"], sorted(pcs)[:4], addrs[:4]))
        if not addrs and pcs:
            addrs, via = sorted(pcs), "sim"
        if addrs:
            stat[f"{kind}_by_{via}"] += 1
            for a in addrs:
                done.append((("read" if kind == "r" else "write"), 0 if ia < COMMON else b, r["insn"], r["func"], f"{a:04x}", via))
                e = acc[a]
                e["xr" if kind == "r" else "xw"] += 1
                e["banks"].add(0 if ia < COMMON else b)
                e["funcs"][f'{r["func"]}@{b}:{r["func_addr"]}'] += 1
        else:
            stat[f"{kind}_left"] += 1
            left.append((kind, 0 if ia < COMMON else b, r["insn"], r["func_addr"], r["func"], why))
    stat["bad"] = bad
    stat["done"] = done
    return stat, left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--ours", default=str(ROOT / "tmp" / "logs" / "trace_wb-p14kc2-2160p60.tsv.gz"))
    ap.add_argument("--dahua-trace", nargs="*", default=[str(ROOT / "tmp" / "logs" / f"trace_vendor_{m}.tsv.gz") for m in ("2160p60", "1080p60")])
    ap.add_argument("--out", default=str(ROOT / "re" / "jxc-4k" / "reg_audit.tsv"))
    a = ap.parse_args()
    src = Path(a.src)
    regs, fields = load_db()
    acc = defaultdict(lambda: {"r": 0, "w": 0, "banks": set(), "funcs": Counter(), "rsv": 0, "xr": 0, "xw": 0})
    unres = Counter()
    pend = []
    for b in range(7):
        for r in rows(src / f"bank{b}" / "regreads.tsv"):
            if r["reg_addr"] == "?":
                unres[("r", f'{b}:{r["func_addr"]}', r["func"])] += 1
                pend.append(("r", b, r))
                continue
            e = acc[int(r["reg_addr"], 16)]
            e["r"] += 1; e["banks"].add(b); e["funcs"][f'{r["func"]}@{b}:{r["func_addr"]}'] += 1
        for r in rows(src / f"bank{b}" / "regwrites.tsv"):
            if r["reg_addr"] == "?":
                unres[("w", f'{b}:{r["func_addr"]}', r["func"])] += 1
                pend.append(("w", b, r))
                continue
            ad = int(r["reg_addr"], 16)
            e = acc[ad]
            e["w"] += 1; e["banks"].add(b); e["funcs"][f'{r["func"]}@{b}:{r["func_addr"]}'] += 1
            rb = rsv_bits(fields, ad)
            v = intv(r["value"]) if r["kind"] in ("set", "dword", "callarg") else intv(r["or_mask"]) if r["kind"] == "rmw" else None
            if rb and v is not None and v & rb:
                e["rsv"] += 1
    ours = Counter()
    if Path(a.ours).exists():
        for r in csv.DictReader(gzip.open(a.ours, "rt", newline=""), delimiter="\t"):
            if r["kind"] == "W":
                ours[int(r["addr"], 16)] += 1
    dyn = Counter()
    dynpc = defaultdict(set)
    for f in a.dahua_trace:
        if Path(f).exists():
            for r in csv.DictReader(gzip.open(f, "rt", newline=""), delimiter="\t"):
                if r["kind"] == "W":
                    dyn[int(r["addr"], 16)] += 1
                    pc = int(r["pc"], 16) - 1          # trace pc = next insn; MOVX is 1 byte
                    dynpc[pc if pc < COMMON else (int(r["bank"]), pc)].add(int(r["addr"], 16))
    stat, left = resolve_pending(pend, acc, dynpc, src)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    hdr = ["addr", "class", "db_name", "reads", "writes", "banks", "nfuncs", "top3_funcs", "rsv1_writes", "ours_w", "dahua_sim_w", "extra_r", "extra_w", "db_fields"]
    cnt = Counter()
    notin = []
    with open(out, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(hdr)
        for ad in sorted(acc):
            e = acc[ad]
            cls = "XRAM" if ad in RAM else "REG"
            name = regs.get(ad, "")
            fl = "; ".join(f"[{h}:{l}]{n}" if h != l else f"[{h}]{n}" for h, l, n in sorted(fields.get(ad, ()), reverse=True))[:200]
            top = ", ".join(n for n, _ in e["funcs"].most_common(3))
            w.writerow([f"{ad:04x}", cls, name or ("" if cls == "XRAM" else "NOT IN DB"), e["r"], e["w"],
                        ",".join(map(str, sorted(e["banks"]))), len(e["funcs"]), top, e["rsv"], ours.get(ad, 0), dyn.get(ad, 0), e["xr"], e["xw"], fl])
            cnt[cls] += 1
            if cls == "REG":
                cnt["in_db" if name else "not_in_db"] += 1
                if not name:
                    notin.append((ad, e))
    nread = sum(e["r"] for e in acc.values()); nwr = sum(e["w"] for e in acc.values())
    log(f"rows resolved: reads {nread} writes {nwr}; unresolved ('?' addr): reads {sum(v for k, v in unres.items() if k[0]=='r')} "
        f"writes {sum(v for k, v in unres.items() if k[0]=='w')} in {len({k[1] for k in unres})} functions")
    log(f"distinct addresses {len(acc)}: REG {cnt['REG']} (in DB {cnt['in_db']}, NOT in DB {cnt['not_in_db']}), XRAM {cnt['XRAM']}")
    log(f"registers with rsv1 writes: {sum(1 for e in acc.values() if e['rsv'])}")
    dw = {ad for ad, e in acc.items() if (e["w"] or e["xw"]) and ad not in RAM}
    ow = {ad for ad in ours if ad not in RAM}
    log(f"our sim trace: {len(ow)} distinct addresses written; Dahua writes {len(dw)}; Dahua-only {len(dw - ow)}; ours-only {len(ow - dw)}; both {len(dw & ow)}")
    for tag, st in (("DAHUA-ONLY", dw - ow), ("OURS-ONLY", ow - dw)):
        log(f"{tag} (>=0xFE00 or pin/IR/audio/ADC pages 10xx 23xx 06xx):")
        for ad in sorted(st):
            if ad >= 0xFE00 or 0x1000 <= ad < 0x1100 or 0x2300 <= ad < 0x2400 or 0x06c0 <= ad < 0x0700:
                log(f"  {ad:04x} {regs.get(ad, 'NOT IN DB')}")
    exported = {ad for ad, e in acc.items() if e["r"] or e["w"]}
    dyn_only = {ad for ad in dyn if ad not in RAM and ad not in exported}
    log(f"Dahua fw in the sim (boot->ACTIVE, 2 modes): {len([a_ for a_ in dyn if a_ not in RAM])} addresses written; "
        f"{len(dyn_only)} of them never seen by the static export (indirect/pointer writes), in DB {sum(1 for x in dyn_only if x in regs)}")
    log("  dynamic-only, not in DB: " + " ".join(f"{x:04x}" for x in sorted(dyn_only) if x not in regs))
    log("  dynamic-only outside video pages (>=0xFE00, 10xx, 23xx, 06xx): " + " ".join(f"{x:04x}" for x in sorted(dyn_only) if x >= 0xFE00 or 0x1000 <= x < 0x1100 or 0x2300 <= x < 0x2400 or 0x600 <= x < 0x700))
    # '?' resolver report
    uniq_r, uniq_w = stat["r_sites"], stat["w_sites"]
    log(f"'?' sites (unique; common code 0x0000-0x2585 counted once): reads {uniq_r}, writes {uniq_w} (rows incl. 7x copies of common code: {sum(unres.values())})")
    for k in ("r", "w"):
        log(f"  {'reads' if k == 'r' else 'writes'}: resolved by DPTR flow {stat[k + '_by_flow']}, by constant DPTR at all callers {stat[k + '_by_caller']}, "
            f"by sim pc {stat[k + '_by_sim']}, left {stat[k + '_left']}")
    log(f"  cross-check against the sim (write sites resolved statically and executed in the sim): {stat['check_sites']}, "
        f"sim addresses all inside the static set {stat['check_ok']}, not {stat['check_bad']}")
    for x in stat["bad"][:10]:
        log(f"    MISMATCH {x}")
    def group(w):
        if "different constants" in w:
            return "caller passes many different constants (indexed / loop over register blocks)"
        if "callers not constant" in w:
            return "caller passes a non-constant DPTR (pointer / index computed by the caller)"
        if "no direct caller" in w:
            return "no direct caller (indirect call, ISR, jump table)"
        return w.split(" via ")[0]
    why = Counter(group(x[5]) for x in left)
    log("  left by reason: " + "; ".join(f"{k} {v}" for k, v in why.most_common()))
    byfn = Counter((x[4], x[3]) for x in left)
    log("  left, top functions: " + "; ".join(f"{n}@{fa} {c}" for (n, fa), c in byfn.most_common(15)))
    newun = sorted(ad for ad, e in acc.items() if (e["xr"] or e["xw"]) and not (e["r"] or e["w"]))
    log(f"  addresses first seen through the resolver: {len(newun)} (REG {sum(1 for x in newun if x not in RAM)}, XRAM {sum(1 for x in newun if x in RAM)}); "
        f"not in DB: {' '.join(f'{x:04x}' for x in newun if x not in RAM and x not in regs) or 'none'}")
    res_f = out.with_name("reg_audit_resolved.tsv")
    with open(res_f, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["kind", "bank", "insn", "func", "addr", "via"])
        for x in sorted(stat["done"], key=lambda x: (x[1], int(x[2], 16), x[4])):
            w.writerow(x)
    log(f"wrote {res_f}")
    unr = out.with_name("reg_audit_unresolved.tsv")
    with open(unr, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["kind", "bank", "insn", "func_addr", "func", "reason"])
        for x in sorted(left, key=lambda x: (x[1], int(x[2], 16))):
            w.writerow(["read" if x[0] == "r" else "write", *x[1:]])
    log(f"wrote {unr}")
    log("NOT IN DB:")
    for ad, e in notin:
        log(f"  {ad:04x} r{e['r']} w{e['w']} banks{sorted(e['banks'])} {', '.join(n for n, _ in e['funcs'].most_common(3))}")
    log(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
