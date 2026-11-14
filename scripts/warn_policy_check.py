#!/usr/bin/env python3
"""Rows of fw/warn_policy.tsv against the warnings of a full build: unused rows (stale) and per-row hit counts.

usage: warn_policy_check.py WARNINGS.txt [WARNINGS.txt ...] [--policy fw/warn_policy.tsv] [--prune]
  WARNINGS.txt = fw_compile's tmp/sdcc-port/warnings-<uv2>.txt of every compile of the build (project + Lib)
  --prune  rewrite the policy without the rows no warning matches (comments kept)
Exit 1 if a row is unused (without --prune; only reported when K2S_SDCC_EXTRA is set) or a warning matches no row.
  Optional 6th column `build` = a -D option (e.g. _AWTO_FRC): the row's site exists only in that build; the default build
  does not count it unused (#165). Log: tmp/logs/warn_policy_check.log
"""
import argparse, fnmatch, os, re, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
WARN_RE = re.compile(r"^(.+?):(\d+)(?::\d+)?: warning(?: (\d+))?: (.*)$")   # same as fw_compile.WARN_RE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("warnings", nargs="+")
    ap.add_argument("--policy", default=str(ROOT / "fw/warn_policy.tsv"))
    ap.add_argument("--prune", action="store_true")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/warn_policy_check.log").open("a")

    def log(s):
        print(s); lf.write(f"{isostamp.now()} {s}\n")
    src = str(ROOT / "tmp/sdcc-port/src")
    sites = set()
    for w in a.warnings:
        for l in Path(w).read_text(errors="replace").splitlines():
            m = WARN_RE.match(l)
            if m:
                p = m.group(1)
                sites.add((os.path.relpath(p, src) if p.startswith(src) else p, m.group(2), m.group(4)))
    lines = Path(a.policy).read_text().splitlines()
    rows = [(i, (l.split("\t") + [""] * 5)[:5]) for i, l in enumerate(lines) if l.strip() and not l.startswith("#")]
    opt = {i for i, l in enumerate(lines) if l.strip() and not l.startswith("#") and (l.split("\t") + [""] * 6)[5].strip()}
    hits = {i: 0 for i, _ in rows}
    unmatched = []
    for rel, ln, text in sorted(sites):
        ok = False
        for i, (pat, glob, line, verdict, _) in rows:
            if verdict == "ok" and re.search(pat, text) and fnmatch.fnmatch(rel, glob) and line in ("*", ln):
                hits[i] += 1; ok = True
        if not ok:
            unmatched.append(f"{rel}:{ln}: {text}")
    dead = [i for i, n in hits.items() if not n]
    log(f"{len(sites)} warning sites, {len(rows)} rows: {len(dead)} unused, {len(unmatched)} sites without a row")
    for i in dead:
        log(f"unused row {i + 1}: {lines[i][:160]}")
    for u in unmatched:
        log(f"no row: {u}")
    if a.prune and dead:
        Path(a.policy).write_text("\n".join(l for i, l in enumerate(lines) if i not in set(dead)) + "\n")
        log(f"pruned {len(dead)} rows from {a.policy}")
        dead = []
    if dead and not os.environ.get("K2S_SDCC_EXTRA", "").strip() and opt & set(dead):
        log(f"default build: {len(opt & set(dead))} unused row(s) belong to a -D build option (column 6), not fatal")
        dead = [i for i in dead if i not in opt]
    if dead and os.environ.get("K2S_SDCC_EXTRA", "").strip():   # rows are tuned to the default build; -D builds only report them
        log(f"K2S_SDCC_EXTRA set (non-default build): {len(dead)} unused row(s) reported, not fatal")
        dead = []
    return 1 if dead or unmatched else 0


if __name__ == "__main__":
    sys.exit(main())
