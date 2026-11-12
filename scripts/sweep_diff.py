#!/usr/bin/env python3
"""Before/after table of two mode_sweep TSVs (first row per mode; the rest-mode repeats are skipped).

usage: sweep_diff.py BEFORE.tsv AFTER.tsv [--md] [--offered WxH@HZ,...]
  Mode absent from AFTER: "not offered" if the host no longer lists it (--offered = the host's list now), else "not run"
  (partial sweep); neither is a failure. --md: GitHub table.
  Prints verdict counts per side and the changed rows first. Log: ./tmp/logs/sweep_diff.log
"""
import sys
from collections import Counter
from pathlib import Path


def load(p: Path) -> dict:
    out = {}
    for ln in p.read_text().splitlines()[1:]:
        f = ln.split("\t")
        if len(f) > 1 and (f[0] not in out or out[f[0]] == "SETFAIL"):    # a --resume row replaces a SETFAIL
            out[f[0]] = f[1]
    return out


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    md = "--md" in sys.argv
    b, c = load(Path(a[0])), load(Path(a[1]))
    off = sys.argv[sys.argv.index("--offered") + 1].split(",") if "--offered" in sys.argv else None
    a = [x for x in a if off is None or x != ",".join(off)]
    gone = lambda m: "not run" if off is not None and m in off else "not offered"     # noqa: E731
    modes = list(b) + [m for m in c if m not in b]
    rows = [(m, b.get(m, "not offered"), c.get(m) or gone(m)) for m in modes]
    rows.sort(key=lambda r: r[1] == r[2])                 # changed first, host order kept inside each group
    lines = [f"before {Path(a[0]).name}: {dict(Counter(b.values()))}", f"after  {Path(a[1]).name}: {dict(Counter(c.values()))}"]
    if md:
        lines += ["", "| mode | before | after |", "|---|---|---|"] + [f"| {m} | {x} | {'**' + y + '**' if x != y else y} |" for m, x, y in rows]
    else:
        lines += [f"{m:<18} {x:<12} {y:<12}{'  <-' if x != y else ''}" for m, x, y in rows]
    txt = "\n".join(lines)
    print(txt)
    log = Path(__file__).resolve().parent.parent / "tmp/logs/sweep_diff.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.open("a").write(txt + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
