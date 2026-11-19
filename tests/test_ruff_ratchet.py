"""Ruff ratchet (#269): per-rule error counts in dev.py, scripts/, tests/ may only go down.
Baseline: tests/ruff_baseline.json. Lower it (run this file with RUFF_BASELINE_WRITE=1) after fixing a rule.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(__file__).with_name("ruff_baseline.json")
PATHS = ["dev.py", "scripts", "tests"]
RUFF_TIMEOUT_S = 30   # ruff over ~600 files measured ~1 s; 30 s = hung


def counts() -> dict[str, int]:
    r = subprocess.run(["ruff", "check", *PATHS, "--output-format", "json", "--exit-zero"],
                       cwd=ROOT, capture_output=True, text=True, timeout=RUFF_TIMEOUT_S, check=True)
    out: dict[str, int] = {}
    for d in json.loads(r.stdout):
        out[d["code"]] = out.get(d["code"], 0) + 1
    return dict(sorted(out.items()))


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_ruff_counts_do_not_grow():
    now = counts()
    if os.environ.get("RUFF_BASELINE_WRITE"):
        BASE.write_text(json.dumps(now, indent=1) + "\n")
    base = json.loads(BASE.read_text())
    grew = {c: (base.get(c, 0), n) for c, n in now.items() if n > base.get(c, 0)}
    assert not grew, f"ruff errors grew (rule: baseline, now): {grew}"
