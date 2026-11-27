#!/usr/bin/env python3
"""Throwaway: print assistant text blocks of a Claude Code transcript that contain KEYWORD within a time window.
usage: search_transcript.py TRANSCRIPT KEYWORD [FROM_ISO] [TO_ISO] [MAXCHARS]   (log: tmp/logs/search_transcript.log)"""
import json, sys
from pathlib import Path

src, kw = Path(sys.argv[1]), sys.argv[2].lower()
t0 = sys.argv[3] if len(sys.argv) > 3 else ""
t1 = sys.argv[4] if len(sys.argv) > 4 else "9"
mx = int(sys.argv[5]) if len(sys.argv) > 5 else 700
n = 0
with src.open(errors="replace") as f:
    for ln in f:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        ts = d.get("timestamp", "")
        if d.get("type") != "assistant" or not (t0 <= ts <= t1):
            continue
        for b in (d.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "text" and kw in b.get("text", "").lower():
                t = b["text"]
                i = max(t.lower().find(kw) - 150, 0)
                print(f"--- {ts}\n{t[i:i + mx]}\n")
                n += 1
log = Path(__file__).resolve().parent / "logs" / "search_transcript.log"
log.parent.mkdir(exist_ok=True)
log.open("a").write(f"{kw!r} {t0}..{t1}: {n} hits\n")
