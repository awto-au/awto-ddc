#!/usr/bin/env python3
"""Assemble a clean-room implementer brief: BRIEF_TEMPLATE + specs/<mod>.md + its vectors (#65, docs/cleanroom.md).

usage: cleanroom_brief.py MOD [--out FILE]      (stdout by default)
  Vectors: every specs/vectors/*.tsv named in the spec text, inlined. Refuses a spec still marked TO WRITE, and a brief
  that fails the leak lint (SDK identifiers / n-grams; lint run on a temp copy of the brief).
Log: tmp/logs/cleanroom_brief.log
"""
from __future__ import annotations

import argparse, re, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanroom_lint as CL  # noqa: E402

ROOT = CL.ROOT
SPECS = ROOT / "specs"


def assemble(mod: str) -> str:
    spec = (SPECS / f"{mod}.md").read_text()
    if re.search(r"^Status: TO WRITE", spec, re.M):
        sys.exit(f"spec {mod} is not written yet")
    vec = []
    for name in sorted(set(re.findall(r"specs/vectors/([\w.-]+\.tsv)", spec))):
        vec.append(f"### {name}\n```\n{(SPECS / 'vectors' / name).read_text().rstrip()}\n```")
    tpl = (SPECS / "BRIEF_TEMPLATE.md").read_text()
    spec = spec.replace("specs/vectors/", "vectors section: ")       # no paths into the spec side
    return tpl.replace("{mod}", mod).replace("{spec}", spec.strip()).replace("{vectors}", "\n\n".join(vec) or "none")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mod")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    text = assemble(a.mod)
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as d:
        (Path(d) / "brief.md").write_text(text)
        hits = [h for h in CL.lint(Path(d), CL.build_index(False), False, False) if "structural" not in h]
    if hits:
        sys.exit("brief fails the leak lint:\n  " + "\n  ".join(hits[:40]))
    (a.out.write_text(text) if a.out else sys.stdout.write(text))
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    with (ROOT / "tmp/logs/cleanroom_brief.log").open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} brief {a.mod}: {len(text)} chars -> {a.out or 'stdout'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
