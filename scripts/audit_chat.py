#!/usr/bin/env python3
"""Extract genuine human messages, pop-up answers, assistant text and compaction summaries from a session JSONL.
Usage: audit_chat.py <session.jsonl> [outdir]   (default outdir tmp/scratch)
Logs to tmp/logs/audit_chat.log."""
import json
import os
import re
import subprocess
import sys


def repo():
    r = os.environ.get("AWTO_DDC_REPO")
    if r: return r
    try: return subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    except (subprocess.CalledProcessError, OSError): return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP = ("[SYSTEM NOTIFICATION", "<system-reminder", "Another Claude session sent a message",
        "<task-notification", "Full Settings JSON", "Hooks Configuration", "Constructing a Hook", "Settings Schema Reference", "Base directory for this skill", "<command-", "<local-command", "<browser_instruction", "Caveat:", "[Request interrupted")

def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str): return [{"type": "text", "text": c}]
    return c or []

def main():
    src = sys.argv[1]; R = repo()
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(R, "tmp/scratch")
    os.makedirs(out, exist_ok=True); os.makedirs(os.path.join(R, "tmp/logs"), exist_ok=True)
    users, answers, asst, summ = [], [], [], []
    seen = set(); n = 0
    with open(src, errors="replace") as _f:
        for line in _f:
            n += 1
            try: e = json.loads(line)
            except json.JSONDecodeError: continue
            t = e.get("type"); ts = e.get("timestamp", "")
            if t == "user" and not e.get("isSidechain"):
                m = e.get("message", {})
                for b in blocks(m):
                    if b.get("type") == "text":
                        tx = b["text"].strip()
                        if not tx: continue
                        if tx.startswith(SKIP): continue
                        if e.get("isCompactSummary") or tx.startswith("This session is being continued"):
                            summ.append((ts, tx)); continue
                        k = (e.get("uuid"), tx)
                        if k in seen: continue
                        seen.add(k); users.append((ts, tx))
                    elif b.get("type") == "tool_result":
                        c = b.get("content"); tx = c if isinstance(c, str) else " ".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                        if re.search(r"User has answered|The user answered|user answered your question", tx or ""):
                            answers.append((ts, tx.strip()))
            elif t == "assistant" and not e.get("isSidechain"):
                tx = "\n".join(b.get("text", "") for b in blocks(e.get("message", {})) if b.get("type") == "text").strip()
                if tx: asst.append((ts, tx))
    # dedupe consecutive identical (resumed sessions replay)
    def dd(l):
        o = []; s = set()
        for ts, tx in l:
            if tx in s: continue
            s.add(tx); o.append((ts, tx))
        return o
    users = dd(users); answers = dd(answers); asst = dd(asst)
    with open(os.path.join(out, "chat-user-messages.md"), "w") as f:
        f.write(f"# Genuine user messages ({len(users)}), source {os.path.basename(src)}\n\n")
        for i, (ts, tx) in enumerate(users, 1): f.write(f"## {i} {ts}\n{tx}\n\n")
    with open(os.path.join(out, "chat-popup-answers.md"), "w") as f:
        f.write(f"# Pop-up answers ({len(answers)})\n\n")
        for i, (ts, tx) in enumerate(answers, 1): f.write(f"## P{i} {ts}\n{tx}\n\n")
    with open(os.path.join(out, "chat-assistant-text.md"), "w") as f:
        for ts, tx in asst: f.write(f"## {ts}\n{tx}\n\n")
    with open(os.path.join(out, "chat-compaction-summaries.md"), "w") as f:
        for ts, tx in summ: f.write(f"## {ts}\n{tx}\n\n")
    msg = f"lines={n} users={len(users)} answers={len(answers)} assistant={len(asst)} summaries={len(summ)}"
    print(msg)
    with open(os.path.join(R, "tmp/logs/audit_chat.log"), "a") as lf:
        lf.write(msg + "\n")

if __name__ == "__main__": main()
