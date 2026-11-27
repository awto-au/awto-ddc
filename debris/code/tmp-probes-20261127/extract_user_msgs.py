#!/usr/bin/env python3
"""Throwaway: pull the user's own messages out of a Claude Code transcript (jsonl) for a handover review.
usage: extract_user_msgs.py TRANSCRIPT OUT.tsv   (log: tmp/logs/extract_user_msgs.log)"""
import json, re, sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
log = Path(__file__).resolve().parent / "logs" / "extract_user_msgs.log"
log.parent.mkdir(exist_ok=True)
SKIP = re.compile(r"^\s*(<system-reminder|\[SYSTEM NOTIFICATION|<task-notification|<local-command|<command-name|Another Claude session sent|This session is being continued|Caveat:)")
rows, seen, bad = [], set(), 0
with src.open(errors="replace") as f:
    for ln in f:
        try:
            d = json.loads(ln)
        except ValueError:
            bad += 1
            continue
        if d.get("type") != "user":
            continue
        c = (d.get("message") or {}).get("content")
        texts = [c] if isinstance(c, str) else [b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type") == "text"]
        for t in texts:
            if not t or SKIP.match(t):
                continue
            # the real message is often followed by hook/system text: keep the first paragraph block only
            t = re.split(r"\n\s*(?:UserPromptSubmit hook|<system-reminder|\[SYSTEM NOTIFICATION)", t)[0].strip()
            if not t or t in seen:
                continue
            seen.add(t)
            rows.append((d.get("timestamp", ""), t.replace("\t", " ").replace("\n", " ⏎ ")[:600]))
out.write_text("\n".join(f"{a}\t{b}" for a, b in rows))
msg = f"{src.name}: {len(rows)} user messages, {bad} unparsable lines -> {out}"
print(msg)
log.open("a").write(msg + "\n")
