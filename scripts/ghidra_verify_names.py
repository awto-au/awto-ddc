#!/usr/bin/env python3
"""Independent check of named functions: vendor callee names vs the SDK function's own callee identifiers.

usage: ghidra_verify_names.py  -> ./tmp/verify_calls.tsv (one row per SDK-named func row), log ./tmp/logs/ghidra_verify_names.log
For every merged `func` row whose name is an SDK function (RL6449 series + common/user sources of tmp/sdcc-port/src):
- vendor callees = LCALL/LJMP/ACALL targets inside the function's disassembly blocks (bank thunks resolved to bank<k>:<target>),
  mapped to merged names;
- sdk callees = identifiers followed by `(` in the SDK body (macros not expanded: weak);
- match = vendor callees whose name is an SDK callee; conflict = vendor callees with an SDK-function name that is NOT in the body
  (excluding keil_*, bcall_ wrappers, the function itself, fragments).
Verdict hint (the final verdict in re/jxc-4k/phase2_verification.tsv also needs register/constant evidence):
  call-confirmed = match >= 2 and conflict == 0; call-conflict = conflict > match; weak = otherwise.
"""
import os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghidra_names_merge as M

ROOT = M.ROOT
VEND = Path.home() / "vendors/realtek/analysis/jxc-4k"
SRC = ROOT / "tmp/sdcc-port/src"
OTHER = re.compile(r"RL6(?!449)\d{3}_Series")


REGM = re.compile(r"\b(?:P([0-9A-F]{1,2})_([0-9A-F]{2})|[A-Z0-9]+_([0-9A-F]{4}))_[A-Z0-9_]+")


def regs_of(text):
    out = set()
    for m in REGM.finditer(text):
        out.add(int(m.group(3), 16) if m.group(3) else int(m.group(1), 16) << 8 | int(m.group(2), 16))
    return out


def vendor_regs(bank):
    d = {}
    for f in ("regwrites.tsv", "regreads.tsv"):
        for l in (VEND / f"bank{bank}" / f).read_text().splitlines():
            if l.startswith("#") or l.startswith("bank"):
                continue
            c = l.split("\t")
            try:
                d.setdefault(c[1], set()).add(int(c[4], 16))   # insn -> reg
            except ValueError:
                pass
    return d


def sdk_funcs():
    out = {}
    ident = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    deffn = re.compile(r"(?m)^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\(([^;{}()]*(?:\([^)]*\)[^;{}()]*)*)\)\s*\{")
    for p in SRC.rglob("*.c"):
        if OTHER.search(str(p)):
            continue
        t = p.read_text(errors="replace")
        t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        t = re.sub(r"//[^\n]*", "", t)
        for m in deffn.finditer(t):
            i, d = m.end(), 1
            while i < len(t) and d:
                d += (t[i] == "{") - (t[i] == "}"); i += 1
            body = t[m.end():i]
            out.setdefault(m.group(1), set()).update(x for x in ident.findall(body))
            SDKREGS.setdefault(m.group(1), set()).update(regs_of(body))
    return out


SDKREGS = {}


def blocks(bank):
    """addr -> list of (insn_addr, text) per `; ====` header block (address of header)."""
    cur, res, code = None, {}, {}
    for l in (VEND / f"bank{bank}" / "disassembly.asm").read_text(errors="replace").splitlines():
        m = re.match(r"; ==== .* @ CODE:([0-9a-f]{4}) ====", l)
        if m:
            cur = m.group(1); res[cur] = []; continue
        m = re.match(r"CODE:([0-9a-f]{4}):\s+(.*)", l)
        if m:
            code[m.group(1)] = m.group(2)
            if cur: res[cur].append((m.group(1), m.group(2)))
    return res, code


CALLRE = re.compile(r"(LCALL|LJMP|ACALL)\s+0x([0-9a-f]{4})$")
# Hand verdicts (id = bank:addr) from reading the code; they override the automatic ones. verdict, evidence
MANUAL = {}
MANUAL_FILE = ROOT / "re/jxc-4k/phase2_verification_manual.tsv"


def load_manual():
    out = {}
    if MANUAL_FILE.exists():
        for l in MANUAL_FILE.read_text().splitlines():
            if l and not l.startswith("#"):
                c = l.split("\t")
                out[c[0].lower()] = (c[1], c[2], c[3] if len(c) > 3 else "")
    return out


MACRO_WRAPPED = {"ScalerTimerDelayXms", "ScalerTimerWaitForEvent", "ScalerTimerPollingFlagProc", "ScalerTimerPollingFlagProc_EXINT0"}  # SDK calls them via macros


def main():
    sdk = sdk_funcs()
    sdk = {k: v | MACRO_WRAPPED for k, v in sdk.items()}
    allsdk = set(sdk)
    sdk_callers = {}
    for f, cs in sdk.items():
        for c in cs:
            sdk_callers.setdefault(c, set()).add(f)
    banks, p3 = M.load_all()
    allm = {b: M.merged(b, banks, p3) for b in range(7)}
    M.regen_thunks(allm)
    manual = load_manual()
    # vendor call graph by final names (bcall_ thunks stripped, so cross-bank calls resolve)
    callees_of, callers_of, info = {}, {}, {}
    for b in range(7):
        names = {a[5:]: r["name"] for a, r in allm[b].items() if a.startswith("code:")}
        blk, _ = blocks(b)
        for ad, ins in blk.items():
            me = names.get(ad)
            if not me or me.startswith("bcall_"):
                continue
            for _ia, t in ins:
                m = CALLRE.match(t)
                if not m:
                    continue
                tn = names.get(m.group(2), "")
                tn = tn[6:] if tn.startswith("bcall_") else tn
                if tn and tn != me:
                    callees_of.setdefault((b, me), set()).add(tn)
                    callers_of.setdefault(tn, set()).add(me)
        info[b] = (names, blk, vendor_regs(b))
    rows, vrows = [], []
    for b in range(7):
        names, blk, vr = info[b]
        for a, r in sorted(allm[b].items()):
            if not a.startswith("code:") or r["type"] != "func":
                continue
            ad = a[5:]
            if b and int(ad, 16) < M.COMMON_END:
                continue
            nm, st = r["name"], r["status"]
            if st not in ("[re-agent]", "[auto-sdk]", "[lib]") or nm.startswith("bcall_"):
                continue
            ins = blk.get(ad, [])
            ev = []
            verdict = "PLAUSIBLE"
            if nm in sdk:
                cs = callees_of.get((b, nm), set())
                match = sorted(c for c in cs if c in sdk[nm] and c not in MACRO_WRAPPED)
                conflict = sorted(c for c in cs if c in allsdk and c not in sdk[nm] and not c.startswith("keil_") and "_frag" not in c)
                cm = sorted(c for c in callers_of.get(nm, set()) if c in sdk_callers.get(nm, set()) and nm not in MACRO_WRAPPED)
                cc = sorted(c for c in callers_of.get(nm, set()) if c in allsdk and c not in sdk_callers.get(nm, set()) and c != nm)
                vset = set().union(*(vr.get(ia, set()) for ia, _t in ins)) if ins else set()
                sset = SDKREGS.get(nm, set())
                inter = vset & sset
                prec = len(inter) / len(vset) if vset else 0.0
                rec = len(inter) / len(sset) if sset else 0.0
                regok = len(vset) >= 3 and prec >= 0.8 and rec >= 0.5
                ev.append(f"callees match {len(match)}/conflict {len(conflict)}" + (f" ({','.join(match[:4])})" if match else "")
                          + (f" conflict ({','.join(conflict[:3])})" if conflict else ""))
                ev.append(f"callers match {len(cm)}/conflict {len(cc)}" + (f" ({','.join(cm[:3])})" if cm else ""))
                ev.append(f"regs vendor/sdk/both {len(vset)}/{len(sset)}/{len(inter)}")
                graph = len(match) + len(cm)
                if st == "[lib]":
                    verdict = "CONFIRMED"; ev.insert(0, "exact OMF signature of the Realtek lib module")
                elif graph >= 2 and not conflict and not cc:
                    verdict = "CONFIRMED"
                elif regok and st != "[auto-sdk]":
                    verdict = "CONFIRMED"; ev.insert(0, "register set of the SDK function matches (prec>=0.8, recall>=0.5)")
                elif conflict and len(conflict) + len(cc) > graph:
                    verdict = "PLAUSIBLE"; ev.insert(0, "graph conflicts exceed matches, needs hand check")
            else:
                ev.append("role name (no SDK function of that name); evidence is the agent's comment only")
                if st == "[lib]":
                    verdict = "CONFIRMED"
            conf = r["conf"] or ("lib" if st == "[lib]" else "")
            key = f"{b}:{ad}"
            if key in manual:
                verdict, mev, _ = manual[key]
                ev.insert(0, mev)
            if verdict == "PLAUSIBLE" and st == "[auto-sdk]" and not manual.get(key):
                ev.append("fingerprint-only [auto-sdk]: not graph-verified, downgraded")
            vrows.append((key, nm, st, conf, verdict, "; ".join(ev)))
    for k, (v, e, _x) in manual.items():
        if not any(r[0] == k for r in vrows):
            vrows.append((k, "", "manual", "", v, e))
    out = ROOT / "re/jxc-4k/phase2_verification.tsv"
    hdr = ("# phase2_verification.tsv - phase 3 re-check of every phase-2/auto-sdk/lib function name (generated by scripts/ghidra_verify_names.py).\n"
           "# Columns: id (bank:addr)<TAB>name<TAB>source status<TAB>agent confidence<TAB>verdict<TAB>evidence\n"
           "# CONFIRMED = independent evidence (exact lib signature, call graph both ways vs SDK, register set, or a hand-checked constant/sequence).\n"
           "# PLAUSIBLE = role or name rests on the agent's reading or one weak signal: do not drive firmware work from it.\n"
           "# REFUTED = contradicted; the row is superseded in ghidra_names_phase3.tsv.\n"
           "# Hand verdicts: re/jxc-4k/phase2_verification_manual.tsv (override the automatic ones).\n")
    out.write_text(hdr + "\n".join("\t".join(r) for r in vrows) + "\n")
    from collections import Counter
    c = Counter(r[4] for r in vrows)
    msg = f"{len(vrows)} rows verified: {dict(c)} -> {out}"
    (ROOT / "tmp/logs/ghidra_verify_names.log").write_text(msg + "\n")
    print(msg)


if __name__ == "__main__":
    main()
