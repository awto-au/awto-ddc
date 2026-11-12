#!/usr/bin/env python3
"""Gate `rules` (awto-ddc#162): no build step patches the SDK; fw/sdk is the source.

usage: sdk_rules_lint.py [--tree DIR]     exit 1 on any finding

Fails when:
- scripts/keil2sdcc*.py, fw/overlay/ or a fw/awto/*/rules.py exists (the old patch paths);
- a build script (scripts/*.py other than the one-off sdk_import.py / sdk_own.py) defines INSERTS / SUBS / WRAPS / RULES
  / DROP_WRAPS / DROP_SUBS or writes a `[keil2sdcc]` marker;
- fw/sdk still carries a `[keil2sdcc]` marker (a leftover rule-applied edit).
The mechanical Keil->SDCC rewrite lives only in scripts/sdk_import.py (never run by the build); the allow-list of
mechanical rules is docs/keil2sdcc-rules.md. Log: tmp/logs/sdk_rules_lint.log
"""
import argparse
import re
import sys
from pathlib import Path

ONE_OFF = {"sdk_import.py", "sdk_own.py", "sdk_rules_lint.py"}
DEF = re.compile(r"^\s*(INSERTS|SUBS|WRAPS|RULES|DROP_WRAPS|DROP_SUBS)\s*(\+?=|:)", re.M)


def lint(tree: Path):
    bad = []
    for p in sorted((tree / "scripts").glob("keil2sdcc*.py")):
        bad.append(f"{p.relative_to(tree)}: the SDK patcher must not exist")
    if (tree / "fw/overlay").exists():
        bad.append("fw/overlay exists: board and project files live in fw/sdk")
    for p in sorted((tree / "fw/awto").glob("*/rules.py")):
        bad.append(f"{p.relative_to(tree)}: module rule files must not exist")
    for p in sorted((tree / "scripts").glob("*.py")):
        if p.name in ONE_OFF:
            continue
        t = p.read_text(errors="replace")
        m = DEF.search(t)
        if m:
            bad.append(f"{p.relative_to(tree)}:{t.count(chr(10), 0, m.start()) + 1}: defines {m.group(1)} (SDK patch rules)")
        if "[keil2sdcc]" in t:
            bad.append(f"{p.relative_to(tree)}: writes a [keil2sdcc] marker")
    n = 0
    for p in sorted((tree / "fw/sdk").rglob("*")):
        if p.suffix in (".c", ".h") and p.is_file():
            n += 1
            t = p.read_bytes().decode("latin-1")
            if "[keil2sdcc]" in t:
                bad.append(f"{p.relative_to(tree)}: [keil2sdcc] marker (leftover rule-applied edit)")
    return bad, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=Path(__file__).resolve().parents[1])
    a = ap.parse_args()
    bad, n = lint(a.tree)
    log = a.tree / "tmp/logs/sdk_rules_lint.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    msg = [f"sdk_rules_lint: {len(bad)} finding(s); {n} C/H files in fw/sdk checked"] + [f"  {b}" for b in bad]
    log.write_text("\n".join(msg) + "\n")
    print("\n".join(msg))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
