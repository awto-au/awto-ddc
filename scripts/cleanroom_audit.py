#!/usr/bin/env python3
"""Audit implementer session transcripts for forbidden paths / tools (#65, docs/cleanroom.md "Contamination rules").

usage: cleanroom_audit.py [--projects ~/.claude/projects] [--match -mnt-2tb-git-awto-rtdfw] [FILE.jsonl ...]
  Scans every tool call (tool_use input) in the transcripts of sessions whose project dir matches --match.
  A hit = a forbidden path substring in any input field, or a forbidden tool (web, gh, subagents).
  Tool RESULTS are scanned too: a denied read leaves no content, an allowed one does (that is the leak).
  Exit 0 clean, 1 hits. Report: tmp/logs/cleanroom_audit.txt; log tmp/logs/cleanroom_audit.log.
"""
from __future__ import annotations

import argparse, json, os, re, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

FORBIDDEN_PATHS = ["/mnt/2tb/git_mirror", "RTD-Scaler", "Kingdomwhisky", "/mnt/2tb/git/awto-ddc", "awto-au/awto-ddc",
                   "vendors/realtek", "/mnt/2tb/git/awto-sdcc", "-mnt-2tb-git-awto-ddc", "asmlib",
                   "worktree-agent-a2e2a42cc8a983a00"]
FORBIDDEN_TOOLS = re.compile(r"^(WebFetch|WebSearch|Agent|mcp__playwrong.*|mcp__codex.*)$")
FORBIDDEN_CMD = re.compile(r"(^|[\s;&|(])(gh|curl|wget)\s")


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)
    elif isinstance(obj, str):
        yield obj


def audit(files) -> list[str]:
    hits = []
    for f in files:
        for n, line in enumerate(Path(f).read_text(errors="replace").splitlines(), 1):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict) or c.get("type") not in ("tool_use", "tool_result"):
                    continue
                where = f"{Path(f).name}:{n}"
                if c.get("type") == "tool_use":
                    name = c.get("name", "")
                    if FORBIDDEN_TOOLS.match(name):
                        hits.append(f"{where}: tool {name}")
                    cmd = (c.get("input") or {}).get("command", "")
                    if isinstance(cmd, str) and FORBIDDEN_CMD.search(cmd):
                        hits.append(f"{where}: command {cmd[:120]!r}")
                for s in walk(c.get("input") if c.get("type") == "tool_use" else c.get("content")):
                    for p in FORBIDDEN_PATHS:
                        if p in s:
                            hits.append(f"{where}: {c['type']} mentions {p!r}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects")
    ap.add_argument("--match", default="-mnt-2tb-git-awto-rtdfw")
    a = ap.parse_args()
    files = a.files or sorted(p for d in a.projects.glob(f"*{a.match}*") for p in d.rglob("*.jsonl"))
    hits = audit(files)
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/logs/cleanroom_audit.txt").write_text("\n".join(hits) + ("\n" if hits else ""))
    with (root / "tmp/logs/cleanroom_audit.log").open("a") as f:
        f.write(f"{isostamp.now()} {len(files)} transcripts, {len(hits)} hits\n")
    for h in hits[:100]:
        print(h)
    print(f"{len(files)} transcripts, {len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
