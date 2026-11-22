"""Repo root for scripts (#303). stdlib only. First hit wins:
1. $AWTO_DDC_REPO  2. git toplevel (a .git next to scripts/ is that toplevel, no subprocess)  3. file-relative.
Template: awto-dan/dev.py-template/_repo.py. Never VSCODE_CWD.
"""
import os
import subprocess
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here.parent / ".git").exists():
        return here.parent
    # local .git read ~1 ms; 2 s covers a cold exec. On expiry/failure: file-relative.
    try:
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2, check=False)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return here.parent


ROOT = repo_root()
