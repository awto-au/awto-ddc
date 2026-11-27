#!/usr/bin/env python3
"""One-off: add gh_claudia.py allow rules + autoMode entry to ~/.claude/settings.json, drop body-pinned one-offs."""
import json, shutil
from pathlib import Path

P = Path.home() / ".claude" / "settings.json"
shutil.copy(P, P.with_suffix(".json.bak-20261119"))
s = json.loads(P.read_text())

PREFIXES = [
    "/mnt/2tb/git/awto-dan/scripts/gh_claudia.py",
    "python3 /mnt/2tb/git/awto-dan/scripts/gh_claudia.py",
    "./scripts/gh_claudia.py",
    "python3 ./scripts/gh_claudia.py",
]
SUBS = ["gh issue create *", "gh issue comment *", "gh issue edit *",
        "gh pr create *", "gh pr comment *", "gh pr edit *",
        "git add *", "git commit *", "git push *",
        "git -C * add *", "git -C * commit *", "git -C * push *"]
new = [f"Bash({p} {sub})" for p in PREFIXES for sub in SUBS]

allow = [r for r in s["permissions"]["allow"] if "gh_claudia.py" not in r]
allow += new
s["permissions"]["allow"] = allow

ENTRY = ("Agent GitHub writes via the bot wrapper: running scripts/gh_claudia.py (awto-dan, or the awto-l8 shim) with "
         "`gh issue create|comment|edit`, `gh pr create|comment|edit`, and `git add|commit|push` (not force-push) on awto-au / awtoau repos. "
         "Dan authorised this 2026-11-19 to stop per-action approvals; per-repo visibility rules in ~/.claude/CLAUDE.md still apply. "
         "Does NOT cover `gh issue close` (only Dan closes issues), `gh pr merge`, force-push, or deleting repos/branches.")
if ENTRY not in s["autoMode"]["allow"]:
    s["autoMode"]["allow"].append(ENTRY)

P.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
print(f"allow rules: {len(allow)} (added {len(new)}), autoMode.allow: {len(s['autoMode']['allow'])}")
