#!/usr/bin/env python3
"""Trace equivalence, reference image vs clean-room build: register-write traces (fw_sim_trace.py TSV.gz), reset -> ACTIVE (#65).

usage: trace_equiv.py REF.tsv.gz OURS.tsv.gz [--rules specs/<mod>.equiv ...] [--ds-slack-ms 0] [--full] [--out PATH]
  Must match (exit 1 otherwise):
    - phase order: first entry into boot, search, ds, active, in that order, in both traces
    - final state per phase: shadow register state (regdb reset as the start value) at the end of each phase, over every
      register either trace wrote in that phase. Redundant writes and RMW splits are invisible by construction.
    - barrier order: per phase, the sequence of barrier events (consecutive repeats collapsed)
    - indexed-port bursts: per phase and data port, the ordered (index, value) data writes
    - action registers: per phase, the ordered values written
    - delays: each `delay` rule holds in OURS (gap >= min)
    - DS->ACTIVE time: OURS <= REF + --ds-slack-ms
  May differ (reported, never a failure): order within a phase outside barriers, redundant writes, RMW splits, poll counts
  (no reads in the trace), W1C registers, port index registers, timer/interrupt SFRs, absolute times.
  Rules file (one per line, `#` comments; ADDR hex, KEY = ADDR or ADDR[IDX]):
    barrier ADDR[=VAL]     writes to ADDR (with VAL) are ordering points
    action  ADDR           compare the write sequence, not the state (self-clearing / trigger registers)
    ignore  KEY            may differ
    port-final ADDR        data port compared by final value per index instead of the burst sequence
    port-autoinc ADDR      index "X+N" in the trace means X+N (port auto-increments); default: kept as written
    delay   KEY[=VAL] KEY[=VAL] MIN_US   in OURS every write matching the first is followed by the second >= MIN_US later
Report: tmp/logs/trace_equiv_<tag>.txt (log line per run in tmp/logs/trace_equiv.log)
"""
from __future__ import annotations

import argparse, csv, gzip, re, sys, time
import isostamp  # noqa: E402
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trace_full_diff import load, ROOT  # noqa: E402

PHASES = ("boot", "search", "ds", "active")
# data port -> its index register(s); same map as fw_sim_trace.PORTS (kept here: fw_sim_trace imports the simulator)
PORTS = {0x0025: (0x24,), 0x002B: (0x2A,), 0x0031: (0x30,), 0x0034: (0x33,), 0x005D: (0x5C,), 0x0061: (0x60,), 0x0065: (0x64,),
         0x008E: (0x8D,), 0x07CF: (0x7CE,), 0x07D3: (0x7D2,), 0x15A4: (0x15A3,), 0x2AAD: (0x2AAC,), 0x2AFC: (0x2AFB,),
         0x4025: (0x4024,), 0x68AD: (0x68AC,), 0x68FC: (0x68FB,), 0x713A: (0x7139,), 0x723A: (0x7239,), 0x71CA: (0x71C9,),
         0x72CA: (0x72C9,), 0xB7C4: (0xB7C1, 0xB7C2, 0xB7C3), 0xBAC4: (0xBAC1, 0xBAC2, 0xBAC3), 0x0069: (0x68,), 0x006D: (0x6C,)}
INDEX_REGS = {a for al in PORTS.values() for a in al}
SFR_STATE = {0x80, 0x90, 0xA0, 0xB0}             # port pins: state compared; other SFRs (IE/TCON/T2CON/...) may differ
COL = dict(seq=0, instr=1, ms=2, func=5, kind=6, addr=7, reg=8, idx=9, val=10, phase=11)


class Rules:
    def __init__(self):
        self.barrier, self.action, self.ignore = [], set(), set()
        self.port_final, self.autoinc, self.delay = set(), set(), []

    @staticmethod
    def key(s: str):
        m = re.fullmatch(r"(?:0x)?([0-9A-Fa-f]+)(?:\[([0-9A-Fa-f+]+)\])?", s)
        if not m:
            raise ValueError(f"bad register key {s!r}")
        return int(m.group(1), 16), (m.group(2) or "").lower()

    @staticmethod
    def match(s: str):
        k, _, v = s.partition("=")
        return Rules.key(k), (int(v, 16) if v else None)

    def load(self, p: Path):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            w = line.split("#", 1)[0].split()
            if not w:
                continue
            try:
                if w[0] == "barrier":
                    self.barrier.append(self.match(w[1]))
                elif w[0] == "action":
                    self.action.add(self.key(w[1])[0])
                elif w[0] == "ignore":
                    self.ignore.add(self.key(w[1]))
                elif w[0] == "port-final":
                    self.port_final.add(self.key(w[1])[0])
                elif w[0] == "port-autoinc":
                    self.autoinc.add(self.key(w[1])[0])
                elif w[0] == "delay":
                    self.delay.append((self.match(w[1]), self.match(w[2]), float(w[3])))
                else:
                    raise ValueError(f"unknown rule {w[0]!r}")
            except (IndexError, ValueError) as e:
                sys.exit(f"{p}:{n}: {e}")
        return self


def regdb_facts():
    """-> reset {(addr, idx_hex)}: value, w1c {addr}. Facts only (address, index, reset, access)."""
    reset, w1c = {}, set()
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if not r["address"].startswith("0x"):
                continue
            a = int(r["address"], 16)
            idx = f"{int(r['port_idx']):x}" if r["port_idx"] else ""
            if r["kind"] == "REG" and re.fullmatch(r"0x[0-9A-Fa-f]{1,2}", r["reset"] or ""):
                reset.setdefault((a, idx), int(r["reset"], 16))
            if r["access"] == "W1C":
                w1c.add(a)
    return reset, w1c


def norm_idx(addr: int, idx: str, rules: Rules) -> str:
    if "+" in idx and addr in rules.autoinc:
        b, n = idx.split("+")
        return f"{int(b, 16) + int(n):x}"
    return idx


def classify(kind: str, addr: int, idx: str, rules: Rules, w1c: set) -> str:
    if kind == "SFR":
        return "state" if addr in SFR_STATE else "may:sfr"
    if (addr, idx) in rules.ignore or (addr, "") in rules.ignore:
        return "may:ignore"
    if addr in w1c:
        return "may:w1c"
    if addr in INDEX_REGS:
        return "may:index-reg"
    if addr in rules.action:
        return "action"
    if addr in PORTS and addr not in rules.port_final:
        return "port"
    return "state"


def events(rows, rules: Rules, w1c: set, full: bool):
    """-> list of (phase, kind, (k, addr, idx), value, instr, cls, name); phase = monotonic phase (first entries only)."""
    ds = next((i for i, r in enumerate(rows) if r[6] == "STATE" and r[8] == "DISPLAY_SETTING"), None)
    end = len(rows) - 1 if full else next((i for i in range(ds or 0, len(rows)) if rows[i][6] == "STATE" and rows[i][8] == "ACTIVE"),
                                          len(rows) - 1)
    out, cur, entered = [], "boot", ["boot"]
    for r in rows[:end + 1]:
        if r[6] == "STATE":
            ph = {"SEARCH": "search", "DISPLAY_SETTING": "ds", "ACTIVE": "active"}.get(r[8])
            if ph and ph not in entered and PHASES.index(ph) > PHASES.index(cur):
                cur = ph; entered.append(ph)
            out.append((cur, "STATE", ("STATE", 0, ""), r[8], int(r[1]), "state-row", r[8]))
            continue
        if r[6] not in ("W", "SFR"):
            continue
        a = int(r[7], 16)
        idx = norm_idx(a, r[9].lower(), rules)
        out.append((cur, r[6], (r[6], a, idx), int(r[10], 16), int(r[1]), classify(r[6], a, idx, rules, w1c), r[8]))
    return out, entered


def is_barrier(ev, rules: Rules) -> bool:
    _, kind, (k, a, idx), v, *_ = ev
    return kind == "W" and any(a == ba and (not bi or bi == idx) and (bv is None or bv == v) for (ba, bi), bv in rules.barrier)


def per_phase(evs, rules: Rules, reset: dict):
    """-> phase -> dict(state={key: value at phase end}, written, barriers, ports={addr: [(idx, v)]}, actions={addr: [v]}, may)."""
    shadow = {}
    res = {ph: dict(written=set(), barriers=[], ports=defaultdict(list), actions=defaultdict(list), may=defaultdict(int))
           for ph in PHASES}
    cur = "boot"
    for ph, kind, key, v, _, cls, _ in evs:
        if ph != cur:
            for p in PHASES[PHASES.index(cur):PHASES.index(ph)]:
                res[p]["state"] = dict(shadow)              # end of phase p (and of any phase skipped over)
            cur = ph
        if kind == "STATE":
            continue
        P = res[ph]
        if is_barrier((ph, kind, key, v), rules):
            b = (key[1], key[2], v)
            if not P["barriers"] or P["barriers"][-1] != b:
                P["barriers"].append(b)
        if cls == "state":
            shadow[key] = v; P["written"].add(key)
        elif cls == "port":
            P["ports"][key[1]].append((key[2], v))
        elif cls == "action":
            P["actions"][key[1]].append(v)
        else:
            P["may"][cls] += 1
    for p in PHASES[PHASES.index(cur):]:
        res[p]["state"] = dict(shadow)
    return res


def start_value(key, reset):
    if key[0] != "W":
        return None
    return reset.get((key[1], key[2].split("+")[0] if key[2] else ""))


def ds_active_us(evs, us_per_instr: float):
    t_ds = next((e[4] for e in evs if e[1] == "STATE" and e[3] == "DISPLAY_SETTING"), None)
    t_ac = next((e[4] for e in evs if e[1] == "STATE" and e[3] == "ACTIVE" and t_ds is not None and e[4] >= t_ds), None)
    return None if t_ds is None or t_ac is None else (t_ac - t_ds) * us_per_instr


def us_scale(rows) -> float:
    r = next((r for r in reversed(rows) if float(r[2]) > 0), None)
    return float(r[2]) * 1000 / int(r[1]) if r else 0.0


def check_delays(evs, rules: Rules, us_per_instr: float):
    fails, n = [], 0
    for (ka, va), (kb, vb), lim in rules.delay:
        hit = lambda e, k, v: e[1] == "W" and e[2][1] == k[0] and (not k[1] or e[2][2] == k[1]) and (v is None or e[3] == v)
        for i, e in enumerate(evs):
            if not hit(e, ka, va):
                continue
            nxt = next((f for f in evs[i + 1:] if hit(f, kb, vb)), None)
            if nxt is None:
                continue
            n += 1
            gap = (nxt[4] - e[4]) * us_per_instr
            if gap < lim:
                fails.append(f"delay {ka[0]:04X}->{kb[0]:04X}: {gap:.1f} us < {lim} us (at instr {e[4]}, {e[6]})")
    return fails, n


def compare(ref_rows, our_rows, rules: Rules, ds_slack_ms: float, full: bool):
    reset, w1c = regdb_facts()
    R, rph = events(ref_rows, rules, w1c, full)
    O, oph = events(our_rows, rules, w1c, full)
    PR, PO = per_phase(R, rules, reset), per_phase(O, rules, reset)
    names = {e[2]: e[6] for e in R + O if e[1] != "STATE"}
    pw = lambda s, i: f"[{s[i][0]}]={s[i][1]:02x}" if i < len(s) else "-"
    fmt = lambda k: f"{'SFR ' if k[0] == 'SFR' else ''}{k[1]:04X}" + (f"[{k[2]}]" if k[2] else "")
    L, fails = [], 0
    P = L.append
    P(f"phases ref {rph} ours {oph}")
    if rph != oph:
        fails += 1; P("  FAIL phase order differs")
    for ph in PHASES:
        a, b = PR[ph], PO[ph]
        keys = sorted(a["written"] | b["written"])
        bad = []
        for k in keys:
            va, vb = a["state"].get(k, start_value(k, reset)), b["state"].get(k, start_value(k, reset))
            if va != vb:
                bad.append(f"    {fmt(k)} {names.get(k, '')}: ref {'-' if va is None else f'{va:02x}'} ours {'-' if vb is None else f'{vb:02x}'}")
        P(f"\n## {ph}: {len(keys)} registers written; state mismatches {len(bad)}")
        L.extend(bad[:200]); fails += len(bad)
        if a["barriers"] != b["barriers"]:
            fails += 1
            P(f"  FAIL barrier order: ref {[f'{x:04X}={v:02x}' for x, _, v in a['barriers']][:20]} ours "
              f"{[f'{x:04X}={v:02x}' for x, _, v in b['barriers']][:20]}")
        for port in sorted(set(a["ports"]) | set(b["ports"])):
            sa, sb = a["ports"].get(port, []), b["ports"].get(port, [])
            if sa != sb:
                fails += 1
                i = next((i for i, (x, y) in enumerate(zip(sa, sb)) if x != y), min(len(sa), len(sb)))
                P(f"  FAIL port {port:04X} burst: ref {len(sa)} writes, ours {len(sb)}; first difference at #{i}: "
                  f"ref {pw(sa, i)} ours {pw(sb, i)}")
        for reg in sorted(set(a["actions"]) | set(b["actions"])):
            if a["actions"].get(reg) != b["actions"].get(reg):
                fails += 1
                P(f"  FAIL action {reg:04X}: ref {a['actions'].get(reg, [])[:16]} ours {b['actions'].get(reg, [])[:16]}")
        may = {k: (a["may"].get(k, 0), b["may"].get(k, 0)) for k in sorted(set(a["may"]) | set(b["may"]))}
        if may:
            P("  may differ (writes ref/ours): " + ", ".join(f"{k[4:]} {x}/{y}" for k, (x, y) in may.items()))
    usr, uso = us_scale(ref_rows), us_scale(our_rows)
    dfail, dn = check_delays(O, rules, uso)
    P(f"\n## delays: {len(rules.delay)} rules, {dn} occurrences checked in ours, {len(dfail)} short")
    L.extend("  FAIL " + d for d in dfail); fails += len(dfail)
    tr, to = ds_active_us(R, usr), ds_active_us(O, uso)
    if tr is None or to is None:
        P(f"\n## DS->ACTIVE: not measurable (ref {tr}, ours {to})")
        fails += to is None and tr is not None
    else:
        ok = to <= tr + ds_slack_ms * 1000
        P(f"\n## DS->ACTIVE: ref {tr / 1000:.1f} ms, ours {to / 1000:.1f} ms (slack {ds_slack_ms} ms): {'ok' if ok else 'FAIL'}")
        fails += not ok
    return L, fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref"); ap.add_argument("ours")
    ap.add_argument("--rules", type=Path, action="append", default=[])
    ap.add_argument("--ds-slack-ms", type=float, default=0.0)
    ap.add_argument("--full", action="store_true", help="whole trace, not only reset -> first ACTIVE")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rules = Rules()
    for p in a.rules:
        rules.load(p)
    (_, ref), (_, ours) = load(a.ref), load(a.ours)
    L, fails = compare(ref, ours, rules, a.ds_slack_ms, a.full)
    tag = Path(a.ours).name.replace("trace_", "").replace(".tsv.gz", "")
    out = a.out or ROOT / f"tmp/logs/trace_equiv_{tag}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    head = f"trace_equiv ref {a.ref} ours {a.ours} rules {[str(p) for p in a.rules]}: {'PASS' if not fails else f'FAIL ({fails})'}"
    out.write_text(head + "\n" + "\n".join(L) + "\n")
    with (ROOT / "tmp/logs/trace_equiv.log").open("a") as f:
        f.write(f"{isostamp.now()} {head} -> {out}\n")
    print(head, "->", out)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
