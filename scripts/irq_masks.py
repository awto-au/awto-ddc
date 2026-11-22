#!/usr/bin/env python3
"""Inventory of every interrupt-masked section of the linked firmware, and the gate that keeps it complete (docs/irq-masks.md, #281).

usage: irq_masks.py --write [--tree DIR] [--map MAP]   regenerate docs/irq-masks.tsv from the tree's last build (hand columns kept by key)
       irq_masks.py --check [--tree DIR] [--map MAP]   FAIL on a linked site missing from the TSV, a static worst case over its budget, no reason on a raised budget
       irq_masks.py --sim-merge tmp/logs/stall_sim.tsv  fill sim_us of the TSV from a stall_sim run
Source: the SDCC listings (tmp/sdcc-port/asm_bank/*.rst): `clr bit`, `mov IE,#v`, `anl IE`, `mov bit,c` ... of IE / EIE. A section runs from the clear to the next
  enable of the same bit in the same function (none -> open: restored elsewhere). Length = longest forward path (back edges cut: a loop body counts once)
  in machine clocks at the default MCU clock plus the callees' longest path; delay sites (delay_inventory rows) count at their written / bound value.
Nesting hazard: an unconditional `setb bit` (no `mov c,bit` save, no clr of the bit before it in the function) that a masked section can reach through its calls.
Key = file | function | bit | kind | ordinal. Log: ./tmp/logs/irq_masks.log
"""
import argparse
import collections
import csv
import os
import re
import sys
import types
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "docs/irq-masks.tsv"
LOG = ROOT / "tmp/logs/irq_masks.log"
COLS = ["key", "id", "file", "line", "function", "bit", "sources", "kind", "restore", "static_us", "path", "waits", "loops", "escape", "nested", "context", "starves",
        "sim_us", "hw_us", "budget_us", "action", "reason"]
HAND = ("sim_us", "hw_us", "budget_us", "action", "reason")
SOURCES = {"SCALER_IRQ": "all scaler IRQs into EXINT0 (P0_04[7] ScalerGlobalIRQControl)", "EA": "all", "EX0": "EXINT0 (DP AUX, TMDS)", "EX1": "EXINT1 (debug I2C)", "ET0": "Timer0", "ET1": "Timer1", "ET2": "Timer2 (1 ms tick)", "ES": "Serial",
           "EX2": "WDT warning (EIE.0)", "IE": "IE byte write", "EIE": "EIE byte write"}
LIMIT_US = {"WDT warning": 146000, "Timer2 tick": 1000, "EXINT0 AUX reply": 300}   # starvation limits: docs/delays.md (WDT margin), 1 ms tick, DP AUX reply
DEFAULT_BUDGET_US = 100                  # non-PHY masked section; a longer one needs budget_us + reason in docs/irq-masks.tsv
MCU_KHZ = 350791                         # default MCU clock (delay_audit clock_states); 12 clocks per machine cycle are the listing's [n]
CLR = re.compile(r"(?:clr|jbc)\s+_?(EA|EX0|EX1|ET0|ET1|ET2|ES|EX2)\b(?:$|,)", re.IGNORECASE)          # jbc ea,L = SDCC __critical
SET = re.compile(r"setb\s+_?(EA|EX0|EX1|ET0|ET1|ET2|ES|EX2)$", re.IGNORECASE)
MOVB = re.compile(r"mov\s+_?(EA|EX0|EX1|ET0|ET1|ET2|ES|EX2),c$", re.IGNORECASE)
SAVE = re.compile(r"mov\s+c,_?(EA|EX0|EX1|ET0|ET1|ET2|ES|EX2)$", re.IGNORECASE)
BYTEW = re.compile(r"(mov|anl|orl)\s+_(IE|EIE)\b(.*)")
PRIO = re.compile(r"mov\s+_IP,#(0x[0-9a-f]+)")
JUMPS = re.compile(r"(sjmp|ajmp|ljmp|jz|jnz|jc|jnc|jb|jnb|jbc|cjne|djnz)\s+(.*)$")
ASMCLK = re.compile(r"^\s+([0-9A-F]{6})\s+(?:[0-9A-F]{2}\s)+\s*\[(\d+)\]")
LABEL_OPD = re.compile(r"(\d+\$|_?\w+)$")
CALLS = re.compile(r"(lcall|acall)\s+([A-Za-z_]\w*)")


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def clocks(tree: Path) -> dict:
    out = {}
    for f in (tree / "tmp/sdcc-port/asm_bank").glob("*.rst"):
        for line in f.open(errors="replace"):
            m = ASMCLK.match(line)
            if m:
                out[int(m.group(1), 16)] = int(m.group(2))
    return out


class Model:
    """functions with a CFG cost: longest forward path in us, delay rows added at their address"""

    def __init__(self, tree: Path, mapp: Path):
        import delay_inventory as DI
        self.DI = DI
        self.rows, self.fns, self.g = DI.build_rows(types.SimpleNamespace(build=str(tree), map=str(mapp)))
        self.clk = clocks(tree)
        self.wait = collections.defaultdict(dict)                      # function name -> {addr: us}
        self.var = collections.defaultdict(list)                       # function -> [addr] of waits with no value
        self.rowat = collections.defaultdict(dict)
        for r in self.rows:
            if r["linked"] != "yes" or not r["addr"]:
                continue
            fn = "_" + r["function"]
            a = int(str(r["addr"]), 16)
            self.rowat[fn][a] = r
            if r["kind"] in ("delay_ms", "poll", "wait_event"):
                us = self._us(r, 1000.0)
            elif r["kind"] == "delay_us":
                us = self._us(r, 1.0)
            else:
                continue
            self.wait[fn][a] = max(self.wait[fn].get(a, 0.0), us)
        self.stub_idx = collections.defaultdict(list)
        for n in self.fns:
            self.stub_idx["__bs_" + n[1:]].append(n)
        self.memo, self.busy = {}, set()
        self.index = {n: self._index(f) for n, f in self.fns.items()}

    @staticmethod
    def _us(r, mult):
        try:
            return float(r["value"]) * mult
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _index(f):
        return {a: i for i, (a, _) in enumerate(f.ins)}

    def callee(self, raw):
        return self.DI.resolve_callee(raw, set(self.fns), self.stub_idx)

    def ins_extra(self, fn, i):
        """us added by instruction i of fn beyond its own clocks: callee path (or the delay row at this address)"""
        f = self.fns[fn]
        a, t = f.ins[i]
        ex = self.wait[fn].get(a, 0.0)
        m = CALLS.match(t)
        if m:
            if a in self.rowat[fn] or re.search(r"AwtoDelay|AwtoGap|ScalerTimer(?:DelayXms|PollingFlag|WaitFor)", m.group(2)):
                return ex
            ex += max((self.fn_cost(c) for c in self.callee(m.group(2))), default=0.0)
        return ex

    def succ(self, fn, i):
        f = self.fns[fn]
        t = f.ins[i][1]
        if t.startswith(("ret", "reti")):
            return [], False
        m = JUMPS.match(t)
        nxt = [i + 1] if i + 1 < len(f.ins) else []
        if not m:
            return nxt, False
        op = m.group(2).split(",")[-1].strip()
        tgt = f.labels.get(op)
        out = []
        if tgt is not None and tgt in self.index[fn]:
            out.append(self.index[fn][tgt])
        elif m.group(1) in ("ljmp", "ajmp", "sjmp"):
            return [], True                                          # tail jump out of the function
        if m.group(1) in ("sjmp", "ajmp", "ljmp"):
            return out, False
        return out + nxt, False

    def path(self, fn, start, stops=None):
        """(us, escaped, loops): longest forward path from instruction index start; a path ends at a stop index (the enable of the bit) or at a return.
        escaped = some path returns without reaching a stop (the mask outlives the function)"""
        f = self.fns[fn]
        n = len(f.ins)
        best, escf, loops = {}, {}, 0
        for i in range(n - 1, start - 1, -1):
            a, t = f.ins[i]
            cost = self.clk.get(a, 12) * 1000.0 / MCU_KHZ + self.ins_extra(fn, i)      # us = clocks x 1000 / kHz
            if stops and i in stops and i != start:
                best[i], escf[i] = cost, False
                continue
            nxt, tail = self.succ(fn, i)
            if tail:
                tgt = JUMPS.match(t).group(2).split(",")[-1].strip()
                cost += max((self.fn_cost(c) for c in self.callee(tgt)), default=0.0)
            best_s, esc = 0.0, not nxt
            for s in nxt:
                if s <= i:
                    loops += 1
                    continue
                best_s = max(best_s, best.get(s, 0.0))
                esc = esc or escf.get(s, False)
            best[i], escf[i] = cost + best_s, esc
        return best.get(start, 0.0), escf.get(start, False), loops

    def region(self, fn, start, stops):
        """instruction indexes reachable from start without passing a stop (the masked instructions; forward and backward edges)"""
        seen, todo = set(), [start]
        while todo:
            i = todo.pop()
            if i in seen:
                continue
            seen.add(i)
            if i in (stops or ()) and i != start:
                continue
            todo.extend(self.succ(fn, i)[0])
        return seen

    def fn_cost(self, fn):
        if fn in self.memo:
            return self.memo[fn]
        if fn in self.busy or fn not in self.fns or not self.fns[fn].ins:
            return 0.0
        self.busy.add(fn)
        us = self.path(fn, 0)[0]
        self.busy.discard(fn)
        self.memo[fn] = us
        return us


def stmt_at(f, a):
    best = None
    for file, line, _, ins in f.stmts:
        if ins and ins[0][0] <= a and (best is None or ins[0][0] >= best[2]):
            best = (file, line, ins[0][0])
    return best or ("", 0, 0)


DEF = re.compile(r"^(?:static\s+|inline\s+|__\w+\s+)*[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\(")
_SRC = {}


def c_function(file: str, line: int, fallback: str) -> str:
    """enclosing C function of a source line: static functions have no map symbol, the listing files them under the previous symbol"""
    try:
        if file not in _SRC:
            _SRC[file] = Path(file).read_text(errors="replace").splitlines()
        for k in range(line - 1, -1, -1):
            t = _SRC[file][k]
            if t[:1].isalpha() and not t.startswith(("if", "for", "while", "return", "else", "switch", "#")) and DEF.match(t) and not t.rstrip().endswith(";"):
                return DEF.match(t).group(1)
    except OSError:
        pass
    return fallback


def short(file: str) -> str:
    r = os.path.relpath(file, ROOT) if file and os.path.isabs(file) else file
    return r.replace("tmp/sdcc-port/src/", "")


def find_sites(M: Model):
    sites = []
    unc = []
    for fn, f in sorted(M.fns.items()):
        n = len(f.ins)
        seq = collections.Counter()
        for i, (a, t) in enumerate(f.ins):
            m = CLR.match(t) or None
            bit, kind = (m.group(1).upper(), "jbc (__critical)" if t.startswith("jbc") else "clr") if m else (None, "")
            mc = re.match(r"lcall\s+(?:__bs)?_ScalerGlobalIRQControl$", t)
            if mc and any(re.match(r"clr\s+\(__bovl \+ 0x0\)", x[1]) for x in f.ins[max(0, i - 3):i]):
                bit, kind = "SCALER_IRQ", "ScalerGlobalIRQControl(_DISABLE)"
            mp = PRIO.match(t)
            if mp:
                file, line, _ = stmt_at(f, a)
                seq[("IP", "priority")] += 1
                sites.append({"function": c_function(file, line, fn[1:]), "symbol": fn[1:], "file": short(file), "line": line, "addr": a, "bit": "IP", "kind": "priority " + mp.group(1),
                              "restore": "-", "static_us": 0.0, "waits": "", "loops": 0, "escape": "", "calls": [], "ord": seq[("IP", "priority")], "start": i, "end": i + 1, "nodes": set()})
            if not m and not bit:
                mb = BYTEW.match(t)
                if mb and mb.group(1) != "orl":
                    bit, kind = mb.group(2), "byte-write"
            if bit:
                if bit == "SCALER_IRQ":
                    stops = {k for k in range(i + 1, n) if re.match(r"lcall\s+(?:__bs)?_(ScalerGlobalSetIRQControl|ScalerGlobalIRQControl)$", f.ins[k][1])}
                else:
                    stops = {k for k in range(i + 1, n) if (SET.match(f.ins[k][1]) or MOVB.match(f.ins[k][1])) and (SET.match(f.ins[k][1]) or MOVB.match(f.ins[k][1])).group(1).upper() == bit} if kind != "byte-write" else {k for k in range(i + 1, n) if BYTEW.match(f.ins[k][1]) and BYTEW.match(f.ins[k][1]).group(2) == bit}
                us, esc, loops = M.path(fn, i, stops)
                j = max(stops) if stops else None
                file, line, _ = stmt_at(f, a)
                nodes = M.region(fn, i, stops)
                addrs = {f.ins[k][0] for k in nodes}
                waits = [(ad, w) for ad, w in M.wait[fn].items() if ad in addrs and w]
                calls = sorted({c[1:] for k in nodes if CALLS.match(f.ins[k][1]) for c in M.callee(CALLS.match(f.ins[k][1]).group(2))})
                restore = "none (open)" if j is None else ("saved value" if MOVB.match(f.ins[j][1]) else "setb") + (" + escapes" if esc and j is not None else "")
                seq[(bit, kind)] += 1
                sites.append({"function": c_function(file, line, fn[1:]), "symbol": fn[1:], "file": short(file), "line": line, "addr": a, "bit": bit, "kind": kind,
                              "restore": restore, "static_us": us, "waits": ";".join(f"{w:.0f}us" for _, w in waits), "loops": loops, "escape": "yes" if esc else "",
                              "calls": calls, "ord": seq[(bit, kind)], "start": i, "end": j, "nodes": nodes})
            ms = SET.match(t)
            if ms:
                bit = ms.group(1).upper()
                saved = any((SAVE.match(x[1]) and SAVE.match(x[1]).group(1).upper() == bit) or (CLR.match(x[1]) and CLR.match(x[1]).group(1).upper() == bit) for x in f.ins[:i])
                if not saved:
                    file, line, _ = stmt_at(f, a)
                    unc.append({"function": c_function(file, line, fn[1:]), "symbol": fn[1:], "bit": bit, "file": file, "line": line, "addr": a})
    return sites, unc


def reach_calls(M, fn, nodes):
    """functions a section (its instruction indexes in fn) can reach through calls"""
    f = M.fns[fn if fn.startswith("_") else "_" + fn]
    roots = set()
    for k in nodes:
        m = CALLS.match(f.ins[k][1])
        if m:
            roots.update(M.callee(m.group(2)))
    return {x[1:] for x in M.DI.reach(M.g, list(roots))}


def build(tree: Path, mapp: Path):
    M = Model(tree, mapp)
    sites, unc = find_sites(M)
    ctx, _ = M.DI.contexts(M.fns, M.g)
    byfn = collections.defaultdict(list)
    for u in unc:
        byfn[u["symbol"]].append(u)
    out = []
    for s in sites:
        fnk = "_" + s["symbol"]
        reach = reach_calls(M, s["symbol"], s["nodes"])
        hz = sorted({f"{u['function']}:{u['file'].split('/')[-1]}:{u['line']}" for r in reach for u in byfn.get(r, []) if u["bit"] == s["bit"] or s["bit"] in ("EA", "IE")})
        file = s["file"]
        src = SOURCES.get(s["bit"], s["bit"])
        us = s["static_us"]
        starves = []
        if s["bit"] in ("EA", "IE", "EIE") and us > LIMIT_US["WDT warning"]:
            starves.append("WDT warning")
        if s["bit"] in ("EA", "IE", "EIE", "ET2") and us > LIMIT_US["Timer2 tick"]:
            starves.append("Timer2 tick")
        if s["bit"] in ("EA", "IE", "EIE", "EX0") and us > LIMIT_US["EXINT0 AUX reply"]:
            starves.append("EXINT0 AUX reply")
        out.append({"key": f"{file}|{s['function']}|{s['bit']}|{s['kind']}|{s['ord']}", "file": file, "line": s["line"], "function": s["function"], "bit": s["bit"], "sources": src,
                    "kind": s["kind"], "restore": s["restore"], "static_us": f"{us:.1f}", "path": ";".join(s["calls"][:6]) + ("..." if len(s["calls"]) > 6 else ""),
                    "waits": s["waits"], "loops": s["loops"], "escape": s["escape"], "nested": ";".join(hz[:4]), "context": ",".join(ctx.get(fnk, [])[:2]),
                    "starves": ";".join(starves)})
    unc_rows = [{"function": u["function"], "bit": u["bit"], "file": u["file"], "line": u["line"]} for u in unc]
    return out, unc_rows


def load():
    if not TSV.exists():
        return {}
    return {r["key"]: r for r in csv.DictReader(TSV.open(), delimiter="\t")}


def write(tree, mapp):
    old = load()
    rows, unc = build(tree, mapp)
    nxt = max((int(r["id"][1:]) for r in old.values()), default=0) + 1
    out = []
    for r in rows:
        o = old.get(r["key"])
        if o:
            r["id"] = o["id"]
            for c in HAND:
                r[c] = o[c]
        else:
            r["id"], nxt = f"M{nxt:03d}", nxt + 1
            for c in HAND:
                r[c] = ""
        out.append(r)
    out.sort(key=lambda r: r["id"])
    with TSV.open("w", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    say(f"wrote {TSV} ({len(out)} sites; {len(unc)} unconditional enables seen)")
    return 0


def judge(rows, old):
    """(missing keys, over-budget messages) of the linked sections against the TSV"""
    missing = sorted({r["key"] for r in rows} - set(old))
    over = []
    for r in rows:
        o = old.get(r["key"], {})
        cap = float(o["budget_us"]) if o.get("budget_us") else DEFAULT_BUDGET_US
        if o.get("budget_us") and not o.get("reason", "").strip():
            over.append(f"{r['function']} {r['bit']}: budget row without reason")
        if float(r["static_us"]) > cap:
            over.append(f"{r['function']} {r['bit']} {float(r['static_us']):.0f} us > {cap:.0f}")
    return missing, over


def check(tree, mapp):
    old = load()
    rows, _ = build(tree, mapp)
    missing, over = judge(rows, old)
    stale = sorted(set(old) - {r["key"] for r in rows})
    ok = not missing and not over
    say(f"  {'PASS' if ok else 'FAIL'} {len(rows)} interrupt-masked sections, all in docs/irq-masks.tsv, each within its budget (default {DEFAULT_BUDGET_US} us): "
        f"{len(missing)} missing, {len(over)} over{(': ' + '; '.join((missing + over)[:6])) if not ok else ''}")
    if stale:
        say(f"  info {len(stale)} TSV rows no longer linked (run --write to drop)")
    return 0 if ok else 1


def sim_merge(path):
    sim = {}
    for r in csv.DictReader(Path(path).read_text().splitlines(), delimiter="\t"):
        if r["class"].startswith("masked"):
            k = (re.sub(r"^CH_", "", r["site"]), r["class"].split()[-1])
            sim[k] = max(sim.get(k, 0.0), float(r["longest_ms_x10"]) * 100.0)         # tsv unit 0.1 ms -> us
    old = load()
    n = 0
    for k, r in old.items():
        v = sim.get((r["function"], r["bit"]))
        if v is not None:
            r["sim_us"] = f"{v:.0f}"
            n += 1
    with TSV.open("w", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(old.values(), key=lambda r: r["id"]))
    say(f"sim_us filled for {n} rows")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sim-merge")
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--map", type=Path)
    a = ap.parse_args()
    if a.sim_merge:
        return sim_merge(a.sim_merge)
    mapp = a.map or max((a.tree / "tmp/fw").glob("*-be.map"), key=lambda p: p.stat().st_mtime)
    return write(a.tree, mapp) if a.write else check(a.tree, mapp)


if __name__ == "__main__":
    sys.exit(main())
