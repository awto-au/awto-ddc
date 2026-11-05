#!/usr/bin/env python3
"""Byte cost of arg 2+ passing (_X_PARM_n) in the built firmware, and what a Keil-like register ABI would save.

Input: tmp/sdcc-port/asm_bank/*.rst (exact encodings), tmp/fw/AWT26110003/fw.map.
Output: tmp/param_cost.json, tmp/logs/param_cost.log. Read-only; no build/hardware. See awto-au/awto-sdcc#2.
Model assumptions are listed in ASSUMPTIONS and printed in the log.
"""
import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parent, check=True)
        return Path(out.stdout.strip())
    except Exception:
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
ASM = ROOT / "tmp/sdcc-port/asm_bank"
MAP = ROOT / "tmp/fw/AWT26110003/fw.map"
BUILD = ROOT / "tmp/fw/AWT26110003/build.json"
OUT = ROOT / "tmp/param_cost.json"
LOG = ROOT / "tmp/logs/param_cost.log"

ASSUMPTIONS = [
    "Eligible: arg 2,3 with size<=2 (char/int/enum); Keil regs R5/R3 (char), R4:R5/R2:R3 (int). Arg 4+, ptr/long args stay in memory.",
    "Arg 1 long (4 B, R4-R7) makes arg 2,3 ineligible (Keil rule); arg 1 type parsed from the C signature comment.",
    "Caller new cost/byte: optimistic 1 B (value computed into Rn); pessimistic = 2 B for mov a,src feeders (mov Rn,src), else 1 B.",
    "Callee: linear-order approximation; sites before the first call consume the register, sites after need a spill (loops ignored).",
    "Callee optimistic: pre-call sites 0 B, spill to direct slot (2 B/byte store, 2 B/byte reload). Pessimistic: pre-call sites 1 B/byte (mov a,Rn), xdata spill 5 B/byte, reloads unchanged.",
    "Not modeled: caller push/pop of Rn around calls, __bs_call clobbering R3-R6 (needs rework to preserve args), stub changes.",
]

INSN = re.compile(r"^\s+([0-9A-F]{6})((?: [0-9A-F]{2})+)\s+\[\d+\]\s+\d+\s+(.*)$")
LABEL = re.compile(r"^\s+([0-9A-F]{6})\s+\d+ (\S+):\s*$")
FUNC = re.compile(r"^\s+\d+ ;\t function (\w+)")
SIGL = re.compile(r"\.c:\d+: (.*)$")
DS = re.compile(r"\.ds\s+(\d+)")
PARM_SYM = re.compile(r"#(_\w+?_PARM_\d+)(?:\+(\d+))?")
PARM_NAME = re.compile(r"^_(\w+?)_PARM_(\d+)$")
LOCAL_SYM = re.compile(r"#(_\w+_\d{4,6}_\d+)(?:\+(\d+))?$")
BRANCH = re.compile(r"^(sjmp|ljmp|ajmp|jz|jnz|jc|jnc|jb|jnb|jbc|cjne|djnz|ret|reti|jmp)\b")
LONG_T = re.compile(r"\b(DWORD|ULONG|SDWORD|long|float|UINT32|INT32)\b")


def split_ops(text):
    text = text.split(";")[0].strip()
    m = re.match(r"(\S+)\s*(.*)$", text)
    if not m:
        return "", []
    return m.group(1), [o.strip() for o in m.group(2).split(",")] if m.group(2) else []


class Fn:
    def __init__(self, name, src, sig):
        self.name, self.src, self.sig = name, src, sig
        self.ins = []  # (addr, nbytes, mnemonic, ops, text)


def parse_rst(path, parm_defs):
    fns, cur, last_sig, pending_label = [], None, "", None
    lines = path.read_text(errors="replace").splitlines()
    for ln in lines:
        m = SIGL.search(ln)
        if m and "(" in m.group(1):
            last_sig = m.group(1)
        m = FUNC.match(ln)
        if m:
            cur = Fn(m.group(1), path.name, last_sig if m.group(1) + "(" in last_sig.replace(" (", "(") else "")
            fns.append(cur)
            continue
        m = LABEL.match(ln)
        if m:
            lab, addr = m.group(2), int(m.group(1), 16)
            if lab.startswith("__bs_") or lab.startswith("_CONST"):
                cur = None
            pm = PARM_NAME.match(lab)
            pending_label = (lab, addr) if pm else None
            continue
        if pending_label and DS.search(ln):
            parm_defs[pending_label[0]] = (pending_label[1], int(DS.search(ln).group(1)))
            pending_label = None
            continue
        if cur is not None:
            m = INSN.match(ln)
            if m:
                nb = len(m.group(2).split())
                mn, ops = split_ops(m.group(3))
                cur.ins.append((int(m.group(1), 16), nb, mn, ops, m.group(3).split(";")[0].strip()))
    return fns


def first_arg_long(sig):
    if not sig:
        return False
    s = sig[sig.index("(") + 1: sig.rindex(")")] if "(" in sig and ")" in sig else ""
    first = s.split(",")[0]
    return bool(LONG_T.search(first)) and "*" not in first


def analyse(fn, parm_by_addr, parm_defs):
    """Return per-function events. Roles per instruction index for validation."""
    ins = fn.ins
    role = [""] * len(ins)
    ev = {"store": defaultdict(list), "load": defaultdict(list), "selfw": defaultdict(list)}
    locals_ = {"load": 0, "store": 0, "prologue_store": 0}
    calls = [i for i, x in enumerate(ins) if x[2] in ("lcall", "acall")]
    state = None  # ("parm", addr) / ("local",)
    i = 0
    while i < len(ins):
        addr, nb, mn, ops, text = ins[i]
        if mn == "mov" and ops and ops[0] == "dptr":
            state = None
            pm = PARM_SYM.search(text)
            lm = LOCAL_SYM.search(ops[1]) if len(ops) > 1 else None
            if pm and pm.group(1) in parm_defs:
                a = parm_defs[pm.group(1)][0] + int(pm.group(2) or 0)
                state = ("parm", a)
                key = parm_by_addr.get(a)
                if key:
                    owner_is_self = key[0] == fn.name
                    ev["_dptr"] = ev.get("_dptr", [])
                    ev["_dptr"].append((i, key, nb, owner_is_self))
                    role[i] = "dptr->PARM_%d(%s)" % (key[1], key[0])
            elif lm:
                state = ("local", i)
                locals_["_pend"] = nb
                role[i] = "dptr->local"
        elif mn == "mov" and ops and ops[0] in ("dpl", "dph"):
            state = None
        elif mn == "inc" and ops == ["dptr"] and state:
            if state[0] == "parm":
                key = parm_by_addr.get(state[1])
                state = ("parm", state[1] + 1)
                key2 = parm_by_addr.get(state[1]) or key
                if key2:
                    ev["_inc"] = ev.get("_inc", [])
                    ev["_inc"].append((i, key2, nb, key2[0] == fn.name))
                    role[i] = "inc->PARM_%d" % key2[1]
            else:
                locals_["_pend"] = locals_.get("_pend", 0) + nb
                role[i] = "inc->local"
        elif mn == "movx" and state and (ops == ["@dptr", "a"] or ops == ["a", "@dptr"]):
            is_store = ops[0] == "@dptr"
            if state[0] == "parm":
                key = parm_by_addr.get(state[1])
                if key:
                    selfp = key[0] == fn.name
                    if is_store:
                        # feeder: last A writer within 4 insns, not crossing movx/call/branch
                        feeder = None
                        for j in range(i - 1, max(i - 5, -1), -1):
                            jm, jo = ins[j][2], ins[j][3]
                            if jm in ("lcall", "acall", "movx") or BRANCH.match(jm) or (jm == "inc" and jo == ["dptr"]):
                                break
                            if (jm == "mov" and jo and jo[0] == "a") or (jm == "clr" and jo == ["a"]):
                                feeder = j
                                break
                            if jm in ("orl", "anl", "xrl", "add", "addc", "subb", "swap", "rl", "rr", "cpl", "inc", "dec") and jo and jo[0] == "a":
                                break
                        simple = False
                        fb = 0
                        if feeder is not None:
                            fm, fo = ins[feeder][2], ins[feeder][3]
                            simple = (fm == "clr") or (len(fo) == 2 and fm == "mov" and not fo[1].startswith("@"))
                            if simple:
                                fb = ins[feeder][1]
                                role[feeder] = "feeder->PARM_%d" % key[1]
                        (ev["selfw"] if selfp else ev["store"])[key].append((i, nb + fb, 1, 2 if simple else 1))
                        role[i] = "store PARM_%d(%s)" % (key[1], key[0])
                    else:
                        cons = 0
                        if i + 1 < len(ins) and ins[i + 1][2] == "mov" and len(ins[i + 1][3]) == 2 \
                                and ins[i + 1][3][1] == "a" and re.match(r"^(r[0-7]|ar[0-7])$", ins[i + 1][3][0]):
                            cons = ins[i + 1][1]
                            role[i + 1] = "consumer<-PARM_%d" % key[1]
                        ev["load"][key].append((i, nb + cons, 1, 1))
                        role[i] = "load PARM_%d(%s)" % (key[1], key[0])
            elif state[0] == "local":
                b = locals_.pop("_pend", 0) + nb
                locals_["store" if is_store else "load"] += b
                if is_store and state[1] < 12:
                    locals_["prologue_store"] += b
                role[i] = "local %s" % ("store" if is_store else "load")
        elif BRANCH.match(mn) or mn in ("lcall", "acall"):
            state = None
        i += 1
    # attach dptr/inc bytes to the parm of the next movx event in the same group
    extra = defaultdict(int)
    for tag in ("_dptr", "_inc"):
        for (i, key, nb, selfp) in ev.get(tag, []):
            extra[(i, key)] += nb
    # sum dptr/inc bytes into the nearest following movx event of that parm
    allev = []
    for kind in ("store", "load", "selfw"):
        for key, lst in ev[kind].items():
            for e in lst:
                allev.append((kind, key, e))
    unmatched = 0
    for tag in ("_dptr", "_inc"):
        for (i, key, nb, selfp) in ev.get(tag, []):
            tgt = None
            for kind, k2, e in allev:
                if e[0] > i and (tgt is None or e[0] < tgt[2][0]):
                    tgt = (kind, k2, e)
            # the covered address may be an adjacent parm: bind to the movx at/after i
            if tgt is None or tgt[2][0] - i > 3:
                unmatched += nb
                continue
            kind, k2, e = tgt
            lst = ev[kind][k2]
            idx = lst.index(e)
            lst[idx] = (e[0], e[1] + nb, e[2], e[3])
    return role, ev, locals_, calls, unmatched


def first_arg_cost(fn):
    """Callee reads of dpl/dph/b near entry + caller writes before each call; see ASSUMPTIONS."""
    ins = fn.ins
    callee = 0
    for k in range(min(8, len(ins))):
        mn, ops = ins[k][2], ins[k][3]
        if mn == "mov" and len(ops) == 2 and ops[1] in ("dpl", "dph", "b"):
            callee += ins[k][1]
    caller = 0
    for c, x in enumerate(ins):
        if x[2] not in ("lcall", "ljmp") or not (x[3] and x[3][0].startswith("_")):
            continue
        for j in range(c - 1, max(c - 9, -1), -1):
            mn, ops = ins[j][2], ins[j][3]
            if mn in ("lcall", "acall") or BRANCH.match(mn):
                break
            if mn == "mov" and len(ops) == 2 and ops[0] in ("dpl", "dph", "b"):
                caller += ins[j][1]
            elif mn == "mov" and ops[:1] == ["dptr"] and "_PARM_" not in ins[j][4] and not LOCAL_SYM.search(ops[1]):
                nxt = ins[j + 1][2] if j + 1 < len(ins) else ""
                if nxt != "movx" and ins[j][4].startswith("mov\tdptr,#") or (nxt != "movx" and "#" in ins[j][4]):
                    caller += ins[j][1]
    return caller, callee


def map_totals():
    vals = {}
    for ln in MAP.read_text(errors="replace").splitlines():
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(l_(?:CSEG|CONST|BANK\d+))\s*$", ln)
        if m:
            vals[m.group(2)] = int(m.group(1), 16)
    banks = {k: v for k, v in vals.items() if k.startswith("l_BANK")}
    return {"l_CSEG": vals.get("l_CSEG", 0), "l_CONST": vals.get("l_CONST", 0), "banks": banks,
            "code_total": vals.get("l_CSEG", 0) + sum(banks.values())}


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.FileHandler(LOG, mode="w"), logging.StreamHandler(sys.stdout)])
    log = logging.info
    parm_defs = {}
    fns = []
    for p in sorted(ASM.glob("*.rst")):
        fns += parse_rst(p, parm_defs)
    parm_by_addr = {}
    for sym, (a, sz) in parm_defs.items():
        m = PARM_NAME.match(sym)
        for k in range(sz):
            parm_by_addr[a + k] = (m.group(1), int(m.group(2)))
    log("functions=%d parm_syms=%d" % (len(fns), len(parm_defs)))
    sigs = {}
    for f in fns:
        sigs[f.name] = f.sig

    # classify residency per map
    mapaddr = {}
    for ln in MAP.read_text(errors="replace").splitlines():
        m = re.match(r"^D:\s+([0-9A-F]{8})\s+(_\w+_PARM_\d+)\b", ln)
        if m:
            mapaddr[m.group(2)] = int(m.group(1), 16)
    mism = [s for s, (a, _) in parm_defs.items() if s in mapaddr and mapaddr[s] != a]
    log("parm syms in map=%d, address mismatch rst vs map=%d" % (len(mapaddr), len(mism)))

    def resid(sym):
        a = parm_defs[sym][0]
        return "xdata" if a >= 0x100 else "direct"

    P = defaultdict(lambda: {"caller_bytes": 0, "caller_stores": 0, "caller_new_opt": 0, "caller_new_pess": 0,
                             "callee_bytes": 0, "callee_loads": 0, "callee_selfw_bytes": 0, "pre_loads": 0,
                             "post_loads": 0, "pre_bytes": 0, "post_bytes": 0})
    LOC = defaultdict(lambda: {"load": 0, "store": 0, "prologue_store": 0})
    first = {"caller": 0, "callee": 0}
    unmatched_total = 0
    analysed = {}
    for f in fns:
        role, ev, loc, calls, um = analyse(f, parm_by_addr, parm_defs)
        analysed[(f.src, f.name)] = (f, role)
        unmatched_total += um
        for k in ("load", "store", "prologue_store"):
            LOC[f.name][k] += loc[k]
        c, e = first_arg_cost(f)
        first["caller"] += c
        first["callee"] += e
        fc = calls[0] if calls else 10 ** 9
        for key, lst in ev["store"].items():
            d = P[key]
            for (i, b, n, newp) in lst:
                d["caller_bytes"] += b
                d["caller_stores"] += 1
                d["caller_new_opt"] += 1
                d["caller_new_pess"] += newp
        for key, lst in ev["selfw"].items():
            for (i, b, n, newp) in lst:
                P[key]["callee_selfw_bytes"] += b
        for key, lst in ev["load"].items():
            d = P[key]
            for (i, b, n, _) in lst:
                d["callee_bytes"] += b
                d["callee_loads"] += 1
                if i < fc:
                    d["pre_loads"] += 1
                    d["pre_bytes"] += b
                else:
                    d["post_loads"] += 1
                    d["post_bytes"] += b

    # ABI model per parm
    rows = []
    for key, d in P.items():
        owner, n = key
        sym = "_%s_PARM_%d" % key
        size = parm_defs[sym][1] if sym in parm_defs else 1
        a1long = first_arg_long(sigs.get(owner, ""))
        elig = n in (2, 3) and size <= 2 and not a1long
        today = d["caller_bytes"] + d["callee_bytes"]
        if elig:
            spill = d["post_loads"] > 0
            opt = d["caller_new_opt"] + d["pre_loads"] * 0 + (d["post_loads"] * 2 + size * 2 if spill else 0)
            pess = d["caller_new_pess"] + d["pre_loads"] * 1 + (d["post_bytes"] + size * 5 if spill else 0)
        else:
            opt = pess = today
        rows.append({"fn": owner, "n": n, "size": size, "resid": resid(sym) if sym in parm_defs else "?",
                     "eligible": elig, "arg1_long": a1long, **d, "today": today,
                     "new_opt": opt, "new_pess": pess, "save_max": today - opt, "save_min": today - pess})

    tot = defaultdict(int)
    for r in rows:
        for k in ("caller_bytes", "callee_bytes", "callee_selfw_bytes", "today", "new_opt", "new_pess", "save_max", "save_min"):
            tot[k] += r[k]
        tot["caller_" + r["resid"]] += r["caller_bytes"]
        tot["callee_" + r["resid"]] += r["callee_bytes"]
        if r["eligible"]:
            tot["elig_today"] += r["today"]
    byfn = defaultdict(lambda: {"today": 0, "save_min": 0, "save_max": 0, "parms": 0})
    for r in rows:
        b = byfn[r["fn"]]
        b["today"] += r["today"]
        b["save_min"] += r["save_min"]
        b["save_max"] += r["save_max"]
        b["parms"] += 1
    top = sorted(byfn.items(), key=lambda kv: -kv[1]["save_max"])[:20]

    mt = map_totals()
    build = json.loads(BUILD.read_text())
    locsum = {k: sum(v[k] for v in LOC.values()) for k in ("load", "store", "prologue_store")}
    img = mt["code_total"]
    res = {
        "assumptions": ASSUMPTIONS,
        "parm_syms": len(parm_defs),
        "residency": {"xdata": sum(1 for s in parm_defs if resid(s) == "xdata"),
                      "direct": sum(1 for s in parm_defs if resid(s) == "direct")},
        "today_bytes": {"caller_stores": tot["caller_bytes"], "callee_loads": tot["callee_bytes"],
                        "xdata_caller": tot["caller_xdata"], "xdata_callee": tot["callee_xdata"],
                        "direct_caller": tot["caller_direct"], "direct_callee": tot["callee_direct"],
                        "total": tot["today"], "callee_self_writes_unchanged": tot["callee_selfw_bytes"],
                        "unmatched_dptr_bytes": unmatched_total},
        "eligible_today_bytes": tot["elig_today"],
        "saving_bytes": {"min_conservative": tot["save_min"], "max_optimistic": tot["save_max"]},
        "image": {"code_total_cseg_plus_banks": img, "common_cseg": mt["l_CSEG"], "bin_bytes": build["bin_bytes"],
                  "common_end": build["common_end"]},
        "saving_pct_of_code": {"min": round(100.0 * tot["save_min"] / img, 2), "max": round(100.0 * tot["save_max"] / img, 2)},
        "first_arg_today": {"caller_writes_est": first["caller"], "callee_reads_est": first["callee"]},
        "xdata_local_bytes": locsum,
        "top20": [{"fn": k, **v} for k, v in top],
        "per_parm": sorted(rows, key=lambda r: -r["save_max"]),
    }
    OUT.write_text(json.dumps(res, indent=1))

    log("\n== validation (3 functions) ==")
    pick = ["ScalerOsdAddrSet"]
    cands = sorted([(len(f.ins), f.name) for (_, _), (f, role) in analysed.items()
                    if any(r.startswith("store PARM") for r in role) and len(f.ins) < 60])
    pick += [n for _, n in cands if n not in pick][:1]
    c2 = sorted([(len(f.ins), f.name) for (_, _), (f, role) in analysed.items()
                 if any(r.startswith("load PARM") for r in role) and any("PARM_3" in r for r in role) and len(f.ins) < 40])
    pick += [n for _, n in c2 if n not in pick][:1]
    for (_, name), (f, role) in analysed.items():
        if name in pick:
            pick.remove(name)
            log("\n-- %s (%s) --" % (name, f.src))
            for (a, nb, mn, ops, text), r in zip(f.ins, role):
                log("%06X %d  %-34s %s" % (a, nb, text, r))
            if not pick:
                pass
    log("\n== summary ==")
    log("parm symbols: %d (xdata %d, direct %d)" % (res["parm_syms"], res["residency"]["xdata"], res["residency"]["direct"]))
    log("today arg2+ bytes: caller stores %d (xdata %d, direct %d) + callee loads %d (xdata %d, direct %d) = %d"
        % (tot["caller_bytes"], tot["caller_xdata"], tot["caller_direct"], tot["callee_bytes"],
           tot["callee_xdata"], tot["callee_direct"], tot["today"]))
    log("saving: conservative %d B (%.2f%%), optimistic %d B (%.2f%%) of code %d B"
        % (tot["save_min"], res["saving_pct_of_code"]["min"], tot["save_max"], res["saving_pct_of_code"]["max"], img))
    log("first-arg today (est): caller %d B, callee %d B" % (first["caller"], first["callee"]))
    log("xdata local bytes: loads %d, stores %d (prologue stores %d)" % (locsum["load"], locsum["store"], locsum["prologue_store"]))
    log("%-40s %7s %7s %7s" % ("top20 callee", "today", "saveMin", "saveMax"))
    for k, v in top:
        log("%-40s %7d %7d %7d" % (k, v["today"], v["save_min"], v["save_max"]))
    log("assumptions:")
    for a in ASSUMPTIONS:
        log(" - " + a)


if __name__ == "__main__":
    main()
