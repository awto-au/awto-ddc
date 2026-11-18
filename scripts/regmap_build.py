#!/usr/bin/env python3
"""Regenerate / check the register knowledge base (re/regmap/README.md).

usage: regmap_build.py --write                      regenerate regs.tsv + fields.tsv (hand columns kept by key)
       regmap_build.py --check                      FAIL on a stale file, a bad hand column, an unknown key / test / tag, a bad observation file
       regmap_build.py --set KEY col=val ...        set hand columns of a register row (KEY = PPAA or PPAA:II), then --write
       regmap_build.py --set-field KEY[hi:lo] col=val ...   same for a field row
       regmap_build.py --stats                      row counts by status / class
Generated columns come from re/regdb (primary + other chips), the SDK headers, AwtoRegs.h and the observation store re/regmap/obs.
Log: ./tmp/logs/regmap.log
"""
import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regmap_lib as L  # noqa: E402

OBS_BUDGET = 1_500_000      # bytes, whole obs/ directory (README: size budget)
REGS_BUDGET = 4_000_000     # bytes, regs.tsv


def short(chip):
    return L.chip_short(chip)


def hand_of(row, cols):
    return {c: row.get(c, "") for c in cols}


def build(old_regs, old_flds):
    """-> (regs rows, fields rows, errors)"""
    reg, ports = L.load_regdb(L.PRIMARY)
    others = {c: L.load_regdb(c)[0] for c in L.OTHER_CHIPS}
    sdk, uses = L.load_sdk()
    ours = L.load_ours()
    obs = L.load_obs()
    summ = L.summarise(obs)
    hand = {r["key"]: hand_of(r, L.HAND_REG) for r in old_regs if any(r.get(c) for c in L.HAND_REG)}
    keys = {f"{a:04X}" for a in reg} | {f"{a:04X}" for a in sdk} | {f"{a:04X}" for a in ours} | set(hand)
    keys |= {k for k, s in summ.items() if ":" not in k and s["obs_nonzero"] == "1"}
    rows = []
    for k in sorted(keys, key=L.sort_key):
        base, _, idx = k.partition(":")
        if not L.KEY_RE.match(k):
            continue
        a = int(base, 16)
        r = {"key": k, "page": k[:2], "addr": k[2:4]}
        if idx:
            nm = ports.get((a, int(idx, 16)), "")
            r.update(regdb_name=nm, regdb_status="documented" if nm else "no-row")
        else:
            e = reg.get(a)
            r.update(regdb_name=e["name"] if e else "", regdb_status=L.regdb_status(e), regdb_reset=e["reset"] if e else "",
                     regdb_fields=L.field_summary(e) if e else "", access=L.access_summary(e) if e else "")
            sy = sdk.get(a, [])
            r["sdk_name"] = ",".join(sy)
            n = sum(uses.get(s, 0) for s in sy)
            r["sdk_status"] = "none" if not sy else ("used" if n else "defined")
            r["sdk_uses"] = str(n) if sy else ""
            r["our_name"] = ",".join(ours.get(a, []))
            oc = []
            for c in L.OTHER_CHIPS:
                oe = others[c].get(a)
                if oe and L.named_fields(oe):
                    oc.append(short(c) if oe["name"] == r["regdb_name"] else f"{short(c)}={oe['name']}")
            r["other_chips"] = " ".join(oc)
        r.update(summ.get(k, {}))
        r.update(hand.get(k, {}))
        rows.append(r)
    rowkeys = {r["key"] for r in rows}
    frows, errs = [], []
    for f in old_flds:
        if not any(f.get(c) for c in L.HAND_FLD):
            continue
        fk = f["fkey"]
        if not L.FKEY_RE.match(fk):
            errs.append(f"fields: bad fkey {fk!r}")
            continue
        key, _, rng = fk.partition("[")
        hi, lo = (int(x) for x in rng.rstrip("]").split(":"))
        if hi < lo:
            errs.append(f"fields: {fk} hi < lo")
        if key not in rowkeys:
            errs.append(f"fields: {fk} register row {key} missing")
        r = {"fkey": fk, "key": key, "hi": str(hi), "lo": str(lo)}
        e = reg.get(int(key.partition(":")[0], 16)) if ":" not in key else None
        if e:
            ov = [x for x in e["fields"] if x[2] and not L.RESERVED.match(x[2]) and not (x[0] < lo or x[1] > hi)]
            ex = [x for x in ov if x[0] == hi and x[1] == lo]
            m = ex[0] if ex else (ov[0] if ov else None)
            r["regdb_field"] = ";".join(x[2] for x in ov)
            if m:
                r["regdb_access"], r["regdb_reset"], r["regdb_text"] = m[3], m[4], L.text_line(m[5])
        r.update(hand_of(f, L.HAND_FLD))
        frows.append(r)
    frows.sort(key=lambda r: (L.sort_key(r["key"]), -int(r["hi"]), int(r["lo"])))
    return rows, frows, errs


def validate(rows, frows, errs):
    tests = L.known_test_ids()
    for r in rows:
        errs += L.check_hand(r, r["key"], tests)
        if r["regdb_status"] not in L.REGDB_STATUS:
            errs.append(f"{r['key']}: regdb_status {r['regdb_status']!r}")
        if r.get("sdk_status", "none") not in L.SDK_STATUS:
            errs.append(f"{r['key']}: sdk_status {r['sdk_status']!r}")
    for r in frows:
        errs += L.check_hand(r, r["fkey"], tests)
    cols, trows = L.read_tsv(L.TESTS)
    if trows and cols != L.TEST_COLS:
        errs.append(f"tests.tsv columns {cols}")
    for t in trows:
        if t["state"] not in L.TEST_STATES:
            errs.append(f"tests.tsv {t['id']}: state {t['state']!r}")
    sizes = sum(p.stat().st_size for p in L.OBS.glob("*.tsv.gz"))
    if sizes > OBS_BUDGET:
        errs.append(f"obs/ is {sizes} bytes, budget {OBS_BUDGET}")
    for o in L.load_obs():
        for need in ("unit", "label", "state", "method", "time"):
            if not o.meta.get(need):
                errs.append(f"{o.sid}: header #{need}= missing")
        if o.meta.get("method") not in ("isp", "live", "regdump"):
            errs.append(f"{o.sid}: method {o.meta.get('method')!r}")
        bad = sorted(k for k in o.vals if k.partition(":")[0] in L.EXCLUDE_KEYS)
        if bad:
            errs.append(f"{o.sid}: excluded (HDCP) keys present: {bad[:3]}")
    return errs


def load_old():
    _, regs = L.read_tsv(L.REGS)
    _, flds = L.read_tsv(L.FIELDS)
    return regs, flds


def texts(rows, frows):
    return L.tsv_text(L.REG_COLS, rows), L.tsv_text(L.FLD_COLS, frows)


def parse_kv(items):
    d = {}
    for it in items:
        k, eq, v = it.partition("=")
        if not eq:
            sys.exit(f"{it!r}: expected col=val")
        d[k] = v
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--stats", action="store_true")
    g.add_argument("--set", nargs="+", metavar="KEY col=val")
    g.add_argument("--set-field", nargs="+", metavar="FKEY col=val")
    a = ap.parse_args()
    old_regs, old_flds = load_old()
    if a.set:
        d = parse_kv(a.set[1:])
        bad = set(d) - set(L.HAND_REG)
        if bad:
            sys.exit(f"not hand columns: {sorted(bad)}; hand columns: {L.HAND_REG}")
        row = next((r for r in old_regs if r["key"] == a.set[0]), None)
        if row is None:
            row = {"key": a.set[0]}
            old_regs.append(row)
        row.update(d)
    if a.set_field:
        d = parse_kv(a.set_field[1:])
        bad = set(d) - set(L.HAND_FLD)
        if bad:
            sys.exit(f"not hand columns: {sorted(bad)}; hand columns: {L.HAND_FLD}")
        row = next((r for r in old_flds if r["fkey"] == a.set_field[0]), None)
        if row is None:
            row = {"fkey": a.set_field[0]}
            old_flds.append(row)
        row.update(d)
    rows, frows, errs = build(old_regs, old_flds)
    errs = validate(rows, frows, errs)
    if a.stats:
        c = collections.Counter((r["regdb_status"], r.get("status", "")) for r in rows)
        print(f"regs {len(rows)}, fields {len(frows)}, obs files {len(list(L.OBS.glob('*.tsv.gz')))}")
        for k, v in sorted(c.items()):
            print(f"  regdb {k[0]:15} status {k[1] or '-':10} {v}")
        return 0
    rt, ft = texts(rows, frows)
    if a.check:
        for name, p, t in (("regs.tsv", L.REGS, rt), ("fields.tsv", L.FIELDS, ft)):
            cur = p.read_text() if p.is_file() else ""
            if cur != t:
                a_, b_ = cur.split("\n"), t.split("\n")
                n = next((i for i, (x, y) in enumerate(zip(a_, b_)) if x != y), min(len(a_), len(b_)))
                errs.append(f"{name} is stale (first difference at line {n + 1}): run scripts/regmap_build.py --write")
        if len(rt) > REGS_BUDGET:
            errs.append(f"regs.tsv {len(rt)} bytes over budget {REGS_BUDGET}")
        if errs:
            for e in errs[:40]:
                L.log("regmap FAIL: " + e)
            L.log(f"regmap: {len(errs)} problem(s)")
            return 1
        L.log(f"regmap: OK ({len(rows)} registers, {len(frows)} fields, {len(L.load_obs())} observation files)")
        return 0
    if errs:
        for e in errs[:40]:
            L.log("regmap: " + e)
        L.log("regmap: not written (fix the hand columns first)")
        return 1
    L.REGMAP.mkdir(parents=True, exist_ok=True)
    L.REGS.write_text(rt)
    L.FIELDS.write_text(ft)
    L.log(f"regmap: wrote {len(rows)} registers, {len(frows)} fields (git {L.git_sha()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
