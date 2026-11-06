#!/usr/bin/env python3
"""Merge the per-bank names TSVs (+ phase-3 overrides) into one effective TSV per bank program.

usage: ghidra_names_merge.py            -> ./tmp/names_merged_bank<N>.tsv (5 columns, what ApplyNames/ApplySdkTypes read), log ./tmp/logs/ghidra_names_merge.log
import: merged(bank) -> {addr_lower: row dict}   (used by ghidra_re.py, ghidra_globals_map.py, verify scripts)
Rules (append-only source files, newest row wins):
- `#` and blank lines are skipped. Per file, the LAST row for an address wins (a name `-` retracts the address: it is reset to Ghidra's default name).
- re/jxc-4k/ghidra_names_phase3.tsv is applied after all bank files. Columns: addr name type comment status confidence bank
  (bank = N for a CODE row of one bank, `-` = every bank). Retraction: name `-`.
- CODE rows: own bank + bank-0 rows below 0x28C6 (common area, identical bytes in every bank).
- EXTMEM rows (XDATA map is the same in every bank): rows of ALL banks apply to every program; one address, one winner:
  phase3 > confidence (hand [fw]/[lib] > high > med > low) > later bank file.
- `bcall_*` thunk rows (bank-switch trampolines in the common area): the name is regenerated as bcall_<final name of the target in
  its bank> (target and bank parsed from the row comment: `DPTR=0xXXXX ... bank N`), `bcall_b<N>_<hex>` when the target is unnamed.
- Confidence goes into the comment prefix (`[high] `) so the 5-column format ApplyNames/ExportAll read stays unchanged.
"""
import os, re, sys
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
DATA = ROOT / "re" / "jxc-4k"
COMMON_END = 0x28C6
RANK = {"[fw]": 5, "[lib]": 5, "high": 4, "med": 3, "[guess]": 2, "low": 2, "[auto-sdk]": 1, "": 1, "[?]": 0}


def rank(r):
    return RANK.get(r["conf"] or r["status"], 1) if r["status"] in ("[re-agent]", "[phase3]") else RANK.get(r["status"], 1)


def read(path, phase3=False):
    out = []
    if not path.exists():
        return out
    for i, l in enumerate(path.read_text().splitlines()):
        if not l.strip() or l.startswith("#"):
            continue
        f = l.split("\t")
        if len(f) < 3:
            continue
        f += [""] * (7 - len(f))
        out.append(dict(addr=f[0].lower(), name=f[1], type=f[2], comment=f[3], status=f[4], conf=f[5],
                        bank=(f[6] if phase3 else ""), order=i))
    return out


def last_wins(rows):
    d = {}
    for r in rows:
        d[r["addr"]] = r
    return d


def load_all():
    banks = [last_wins(read(DATA / f"ghidra_names_bank{b}.tsv")) for b in range(7)]
    p3 = read(DATA / "ghidra_names_phase3.tsv", True)
    return banks, p3


def merged(bank, banks=None, p3=None, log=None):
    if banks is None:
        banks, p3 = load_all()
    res = {}
    # CODE: own bank + common area of bank 0
    for src in (banks[0], banks[bank]) if bank else (banks[0],):
        for a, r in src.items():
            if a.startswith("code:") and (src is banks[bank] or int(a[5:], 16) < COMMON_END):
                res[a] = r
    # EXTMEM: all banks, one winner per address
    ext = {}
    for b in range(7):
        for a, r in banks[b].items():
            if a.startswith("extmem:"):
                if a in ext and rank(r) < rank(ext[a]):
                    if log is not None and ext[a]["name"] != r["name"]:
                        log.append(f"extmem {a}: kept {ext[a]['name']} over {r['name']} (bank {b})")
                    continue
                if log is not None and a in ext and ext[a]["name"] != r["name"]:
                    log.append(f"extmem {a}: {r['name']} (bank {b}) replaces {ext[a]['name']}")
                ext[a] = r
    res.update(ext)
    for r in p3:
        if a_is_code(r["addr"]) and r["bank"] not in ("-", "", str(bank)) and not (int(r["addr"][5:], 16) < COMMON_END):
            continue
        res[r["addr"]] = r
    for a, r in res.items():   # retraction: back to Ghidra's default name (a label/function cannot be un-created by ApplyNames)
        if r["name"] == "-":
            res[a] = dict(r, name=("FUN_CODE_" if a.startswith("code:") else "DAT_EXTMEM_") + a.split(":")[1], type="func" if a.startswith("code:") else "var",
                          comment="retracted: " + r["comment"])
    return res


def a_is_code(a):
    return a.startswith("code:")


def regen_thunks(allm):
    """allm: bank -> merged dict. Rewrites bcall_* names in place from final target names."""
    changed = 0
    for b, m in allm.items():
        for a, r in m.items():
            if not r["name"].startswith("bcall_"):
                continue
            mm = re.search(r"DPTR=0x([0-9A-Fa-f]{4}).*?bank (\d)", r["comment"])
            if not mm:
                continue
            t, tb = mm.group(1).lower(), int(mm.group(2))
            tgt = allm[tb].get(f"code:{t}")
            new = "bcall_" + (tgt["name"] if tgt and not tgt["name"].startswith("bcall_") else f"b{tb}_{t}")
            if new != r["name"]:
                m[a] = dict(r, name=new); changed += 1
    return changed


def write(bank, m):
    p = ROOT / "tmp" / f"names_merged_bank{bank}.tsv"
    lines = [f"# merged names for bank {bank} (generated by scripts/ghidra_names_merge.py; do not edit)"]
    for a, r in sorted(m.items(), key=lambda kv: (kv[0][:3] != "cod", kv[0])):
        c = r["comment"]
        if r["conf"]:
            c = f"[{r['conf']}] " + c
        lines.append("\t".join([a.replace("code:", "CODE:").replace("extmem:", "EXTMEM:"), r["name"], r["type"], c, r["status"]]))
    p.write_text("\n".join(lines) + "\n")
    return p


def main():
    banks, p3 = load_all()
    log = []
    allm = {b: merged(b, banks, p3, log if b == 0 else None) for b in range(7)}
    n = regen_thunks(allm)
    for b in range(7):
        write(b, allm[b])
    # duplicate names inside one bank program (different addresses)
    for b in range(7):
        seen = {}
        for a, r in allm[b].items():
            if r["type"] == "func":
                seen.setdefault(r["name"], []).append(a)
        for nme, v in seen.items():
            if len(v) > 1:
                log.append(f"bank{b}: duplicate func name {nme}: {v}")
    log.append(f"thunk names regenerated: {n}")
    allnames = set()
    for b in range(7):
        for r in list(banks[b].values()) + p3:
            if r["type"] == "func":
                allnames.add(r["name"])
    for b in range(7):   # old thunk names too (bcall_* before regeneration)
        for r in banks[b].values():
            if r["name"].startswith("bcall_"):
                allnames.add(r["name"])
    (ROOT / "tmp" / "names_all.txt").write_text("\n".join(sorted(allnames - {"-"})) + "\n")
    msg = "\n".join(log)
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp" / "logs" / "ghidra_names_merge.log").write_text(msg + "\n")
    print(msg)


if __name__ == "__main__":
    main()
