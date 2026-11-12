#!/usr/bin/env python3
"""Full register write-trace diff, vendor vs ours, reset -> ACTIVE (#26). Input: fw_sim_trace.py TSV.gz (all pages + SFR).

usage: trace_full_diff.py VENDOR.tsv.gz OURS.tsv.gz [--out tmp/logs/full_diff_<tag>.txt] [--tsv tmp/logs/full_diff_<tag>.tsv.gz]
  Per trace: final value per (addr, idx) at ACTIVE (rows up to the first ACTIVE after DISPLAY_SETTING), first-write order,
  per-phase write sets. Classes: A vendor-only, B final value differs, C ours-only, D order (first-write sequence of the
  common registers, difflib blocks). Known-benign registers are listed in their own section, not dropped.
  Ranking: keyword score on the regdb register/field names (M1 line buffer / FIFO / D-domain / DDR / clock / power / path).
"""
import argparse, csv, difflib, gzip, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENIGN_ADDR = {0x0002: "status/W1C", 0x000C: "status/W1C", 0x1603: "status/W1C", 0x1616: "status/W1C", 0x3003: "status/W1C",
               0x3016: "status/W1C", 0x0037: "P0_37 (ruled out)"}
ROT = {0x20F0, 0x0549, 0x4549, 0x05AE, 0x0026, 0x4026, 0x01DC, 0x37B0}
BENIGN_NAME = re.compile(r"HDMI|DPRX|DP_RX|_RX|RX_|AUX|MHL|CBUS|SCDC|EDID|PORT_PAGE7|PHY_RX|TMDS|CDR|DFE|IIC_|SCA_INF|AAR_|DPCD|HPD|TIMER|WATCH|\bIR_|_IR_|AUDIO|I2S|SPDIF|OSD|ACCESS_FLASH|FLASH_|DEBUG|UART|PWM|ADC|HDCP|DDC|CEC|EEPROM", re.I)
RANK = [(re.compile(r"M1|M2|FIFO|LINE_?BUF|SD_|FRC|MEM_?|MBIST|DDR|DCLK|DPLL|MPLL|M2PLL|CLK|CLOCK|ISO|POWER|PWR|LDO|GATE|DOMAIN|SPLIT|TWO|2P|PATH|BW|BANDWIDTH|MAIN_DOWN|DISPLAY_FORMAT|DEN|DVTOTAL|HTOTAL|DHTOTAL|SCALING|CAPTURE|DISP", re.I), 3)]
CLASS = [("line buffer / FIFO / M-domain", r"FIFO|LINE_?BUF|\bM1\b|_M1|M1_|M2_|MEM|SD_|MDOMAIN|FRC|MBIST"),
         ("DDR client / bandwidth", r"DDR|BW|BANDWIDTH|DDR_CLIENT|PHY"),
         ("D-domain / display format / timing gen", r"DISPLAY_FORMAT|DEN_|DVTOTAL|DHTOTAL|DH_|DV_|DCLK|DDOMAIN|D_DOMAIN|DISP"),
         ("clock / PLL / gating", r"PLL|CLK|CLOCK|GATE|SSC"),
         ("power / isolation", r"POWER|PWR|ISO|LDO|PD_|_PD"),
         ("path enable / split / scaler", r"SPLIT|2P|TWO|PATH|SCALE|SF_|EN_?$|ENABLE|MUX|SEL")]


def load(p):
    rows = [l.split("\t") for l in gzip.open(p, "rt").read().splitlines()]
    return rows[0], rows[1:]


def reduce(rows):
    """-> dict: key -> {final, first_seq, first_phase, phases:set, name, nwr, firstv}, ordered by first write; stats."""
    ds = next((i for i, r in enumerate(rows) if r[6] == "STATE" and r[8] == "DISPLAY_SETTING"), None)
    end = next((i for i in range(ds or 0, len(rows)) if rows[i][6] == "STATE" and rows[i][8] == "ACTIVE"), len(rows) - 1)
    out, order = {}, []
    for r in rows[:end + 1]:
        if r[6] not in ("W", "SFR"):
            continue
        k = (r[6], int(r[7], 16), r[9])
        e = out.get(k)
        if e is None:
            e = out[k] = dict(final=r[10], first=r[10], seq=len(order), phase=r[11], phases=set(), name=r[8], n=0, ms=r[2], fn=r[5])
            order.append(k)
        e["final"] = r[10]; e["n"] += 1; e["phases"].add(r[11])
    return out, order, rows[end][2]


def regdb():
    names, fields = {}, defaultdict(list)
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if not r["address"].startswith("0x"):
                continue
            a = int(r["address"], 16)
            if r["kind"] == "REG":
                names[a] = r["register"]
            elif r["kind"] == "FIELD":
                fields[a].append((int(r["bit_high"]), int(r["bit_low"]), r["field"], r["access"]))
    return names, fields


def bitdiff(fields, a, v1, v2):
    x = int(v1, 16) ^ int(v2, 16)
    hit = [f"{n}[{h}:{l}]" for h, l, n, _ in fields.get(a, []) if x & (((1 << (h - l + 1)) - 1) << l)]
    return ",".join(hit) if hit else f"xor={x:02x}"


def klass(name, key, fields):
    txt = name
    for c, rx in CLASS:
        if re.search(rx, txt, re.I):
            return c
    return "other"


def benign(key, name):
    a = key[1]
    if key[0] == "SFR":
        return "SFR pin/MCU"
    if a in BENIGN_ADDR:
        return BENIGN_ADDR[a]
    if a in ROT:
        return "rotation path"
    if a in (0xB7C4, 0xBAC4, 0x71CA, 0x72CA, 0x713A, 0x723A, 0x71C4, 0x72C4) or 0xB700 <= a < 0xBB00 and BENIGN_NAME.search(name):
        return "DP/HDMI RX ports"
    if 0xFE00 <= a < 0xFE80 and re.search(r"PIN_REG|PORT\d+_PIN", name):
        return "pin/GPIO (board)"
    if 0xFF78 <= a <= 0xFF7F:
        return "flash port"
    if a >> 8 == 0 and 0x90 <= a <= 0x9F:
        return "OSD port"
    if BENIGN_NAME.search(name):
        return "timer/IR/audio/OSD/misc"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vendor"); ap.add_argument("ours")
    ap.add_argument("--out"); ap.add_argument("--tsv")
    ap.add_argument("--hw-vendor", help="ISP dump JSON (rtd_reg_dump) of the vendor image at ACTIVE; with --hw-ours adds HW columns")
    ap.add_argument("--hw-ours")
    a = ap.parse_args()
    tag = Path(a.ours).name.replace("trace_", "").replace(".tsv.gz", "")
    outp = Path(a.out or ROOT / f"tmp/logs/full_diff_{tag}.txt")
    names, fields = regdb()
    (_, rv), (_, ro) = load(a.vendor), load(a.ours)
    V, ordv, endv = reduce(rv)
    O, ordo, endo = reduce(ro)
    L = []
    P = lambda s="": L.append(s)
    P(f"vendor {Path(a.vendor).name}: {len(rv)} rows, {len(V)} registers written reset->ACTIVE (ACTIVE at fw_ms {endv})")
    P(f"ours   {Path(a.ours).name}: {len(ro)} rows, {len(O)} registers written reset->ACTIVE (ACTIVE at fw_ms {endo})")
    import json
    HW = [json.load(open(x)) if x else None for x in (a.hw_vendor, a.hw_ours)]

    def hw(k, w):
        d = HW[w]
        if d is None or k[0] != "W":
            return "--"
        try:
            if k[2]:
                i = k[2].split("+")[0]
                v = d["ports"].get(f"{k[1]:04X}", {}).get(str(int(i, 16)))
            else:
                v = d["pages"].get(f"{k[1] >> 8:02X}", [None] * 256)[k[1] & 255]
        except (ValueError, IndexError, TypeError):
            v = None
        return "--" if v is None else f"{v:02x}"
    nm = lambda e, k: names.get(k[1], e["name"]) if k[0] == "W" else e["name"]
    fmt = lambda k: f"{k[0] if k[0] != 'W' else ''}{k[1]:04X}" + (f"[{k[2]}]" if k[2] else "")

    A = [k for k in ordv if k not in O]
    Cc = [k for k in ordo if k not in V]
    B = [k for k in ordv if k in O and V[k]["final"] != O[k]["final"]]
    rowsout = []
    sections = {}
    for lab, keys, src in (("A vendor-only", A, V), ("B final differs", B, V), ("C ours-only", Cc, O)):
        rel, ben = [], []
        for k in keys:
            e = src[k]
            b = benign(k, nm(e, k))
            (ben if b else rel).append((k, e, b))
        sections[lab] = (rel, ben)
        P(f"\n## {lab}: {len(keys)} total, {len(rel)} relevant, {len(ben)} known-benign")
    for lab in sections:
        rel, ben = sections[lab]
        P(f"\n## {lab} - relevant, by class")
        byc = defaultdict(list)
        for k, e, _ in rel:
            byc[klass(nm(e, k), k, fields)].append((k, e))
        for c in [c for c, _ in CLASS] + ["other"]:
            if c not in byc:
                continue
            P(f"\n### {c} ({len(byc[c])})")
            for k, e in byc[c]:
                if lab.startswith("B"):
                    o = O[k]
                    P(f"  {fmt(k)} {nm(e, k)}  HW v/o {hw(k, 0)}/{hw(k, 1)}  vendor {e['final']} (first {e['first']} x{e['n']} {e['phase']})  ours {o['final']} (first {o['first']} x{o['n']} {o['phase']})  bits: {bitdiff(fields, k[1], e['final'], o['final'])}")
                    rowsout.append((lab[0], c, fmt(k), nm(e, k), e["final"], o["final"], e["phase"], o["phase"], bitdiff(fields, k[1], e["final"], o["final"])))
                else:
                    P(f"  {fmt(k)} {nm(e, k)}  HW v/o {hw(k, 0)}/{hw(k, 1)}  final {e['final']} (first {e['first']} x{e['n']}, phase {e['phase']}, +{e['ms']} ms, {e['fn']})")
                    rowsout.append((lab[0], c, fmt(k), nm(e, k), e["final"] if lab[0] == "A" else "", e["final"] if lab[0] == "C" else "", e["phase"], "", ""))
        P(f"\n### {lab} - known-benign, listed")
        cnt = defaultdict(list)
        for k, e, b in ben:
            cnt[b].append(f"{fmt(k)}={e['final']}" + (f"/{O[k]['final']}" if lab.startswith("B") else ""))
        for b, l in sorted(cnt.items()):
            P(f"  {b} ({len(l)}): " + " ".join(l[:60]) + (" ..." if len(l) > 60 else ""))

    if HW[0]:
        P("\n## SHORTLIST: relevant A/B/C registers whose ISP-dump value differs vendor-ACTIVE vs ours-failing (or not dumped)")
        for lab in sections:
            for k, e, _ in sections[lab][0]:
                hv, ho = hw(k, 0), hw(k, 1)
                if hv != ho or hv == "--":
                    P(f"  {lab[0]} {fmt(k)} {nm(e, k)}  HW v/o {hv}/{ho}  sim vendor {V[k]['final'] if k in V else '-'} ours {O[k]['final'] if k in O else '-'}")
    # D: order of first writes among common relevant keys
    cv = [k for k in ordv if k in O and not benign(k, nm(V[k], k)) and k[0] == "W"]
    co = [k for k in ordo if k in V and not benign(k, nm(O[k], k)) and k[0] == "W"]
    sm = difflib.SequenceMatcher(None, cv, co, autojunk=False)
    P(f"\n## D order of first writes, common relevant registers (vendor {len(cv)} / ours {len(co)}; ratio {sm.ratio():.3f})")
    n = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        n += 1
        if n > 60:
            P("  ... (more)"); break
        P(f"  {op}: vendor[{i1}:{i2}] " + " ".join(fmt(k) for k in cv[i1:i2][:10]) + f"  |  ours[{j1}:{j2}] " + " ".join(fmt(k) for k in co[j1:j2][:10]))

    # per-phase write sets
    P("\n## per-phase distinct registers written (W only, benign excluded)")
    for tg, S_ in (("vendor", V), ("ours", O)):
        c = defaultdict(int)
        for k, e in S_.items():
            if k[0] == "W" and not benign(k, nm(e, k)):
                for ph in e["phases"]:
                    c[ph] += 1
        P(f"  {tg}: " + ", ".join(f"{p} {c[p]}" for p in ("boot", "search", "ds", "active", "other")))
    P("\n## counts: " + "; ".join(f"{lab}: rel {len(r)} / benign {len(b)}" for lab, (r, b) in sections.items()))
    outp.write_text("\n".join(L) + "\n")
    if a.tsv:
        with gzip.open(a.tsv, "wt") as f:
            f.write("class_AB_C\tgroup\treg\tname\tvendor\tours\tvphase\tophase\tbits\n" + "\n".join("\t".join(r) for r in rowsout) + "\n")
    print("\n".join(L[:3] + L[-1:]), "->", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
