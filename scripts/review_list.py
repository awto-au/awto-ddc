#!/usr/bin/env python3
"""One markdown page of every issue waiting for Dan's review: needs-dan, needs-test, ready-to-close (+ recently closed on request).

usage: review_list.py [--closed N,N,...] [--out FILE] [--files DIR]
- Per issue: number, title, labels, URL, first lines of the newest 🤖 comment (the evidence).
- --files DIR: also one markdown file per issue (body + all comments) for opening in the editor.
Log: tmp/logs/review_list.log
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from _log import log_line
from _repo import repo_root

ROOT = repo_root()
LOG = ROOT / "tmp" / "logs" / "review_list.log"
GH_TIMEOUT_S = 30        # one gh API call: normally < 2 s; expiry -> logged and the issue is skipped
LABELS = ("needs-dan", "needs-test", "ready-to-close")


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT_S, check=False)
    if r.returncode:
        log_line(f"gh {' '.join(args)} rc={r.returncode}: {r.stderr.strip()[:200]}", LOG)
    return r.stdout


def excerpt(number: int) -> str:
    comments = json.loads(gh("issue", "view", str(number), "--json", "comments") or '{"comments": []}')["comments"]
    mine = [c["body"] for c in comments if c["body"].startswith("🤖")]
    body = (mine or [c["body"] for c in comments] or [""])[-1]
    return "\n".join("  > " + ln for ln in body.splitlines()[:8])


def issue_file(number: int, directory: Path) -> Path:
    d = json.loads(gh("issue", "view", str(number), "--json", "number,title,state,labels,url,body,comments") or "{}")
    lines = [f"# #{number} {d.get('title', '')}", "", f"{d.get('state', '')} | {', '.join(x['name'] for x in d.get('labels', []))} | {d.get('url', '')}", "", d.get("body", ""), ""]
    for c in d.get("comments", []):
        lines += ["---", f"**{c['author']['login']} {c['createdAt']}**", "", c["body"], ""]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{number}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--closed", default="", help="comma list of recently closed issue numbers to include")
    ap.add_argument("--out", default=str(ROOT / "tmp" / "review.md"))
    ap.add_argument("--files", default="", help="directory for one markdown file per open issue")
    a = ap.parse_args()
    out = ["# Issues waiting for review", ""]
    seen: set[int] = set()
    for label in LABELS:
        rows = json.loads(gh("issue", "list", "--state", "open", "--label", label, "--limit", "100", "--json", "number,title,url") or "[]")
        out += [f"## {label} ({len(rows)})", ""]
        for r in sorted(rows, key=lambda x: x["number"]):
            n = r["number"]
            note = " (listed above)" if n in seen else ""
            out += [f"- **#{n}** {r['title']}{note}", f"  {r['url']}"]
            if n not in seen:
                out.append(excerpt(n))
            seen.add(n)
        out.append("")
    closed = [int(x) for x in a.closed.split(",") if x.strip()]
    if closed:
        out += [f"## closed on request ({len(closed)}; reopen with `gh issue reopen N` if you wanted to review first)", ""]
        for n in closed:
            row = json.loads(gh("issue", "view", str(n), "--json", "number,title,url") or "{}")
            if row:
                out += [f"- **#{n}** {row['title']}", f"  {row['url']}", excerpt(n)]
        out.append("")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    if a.files:
        for n in sorted(seen):
            print(issue_file(n, Path(a.files)))
    log_line(f"wrote {a.out}: {len(seen)} open + {len(closed)} closed", LOG)
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
