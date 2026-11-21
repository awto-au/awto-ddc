"""stall_sim.py: ISR and masked stretches measured from PC hooks in the panel scenario (offline, --slow)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMG = os.environ.get("AWTO_TEST_IMAGE")
pytestmark = [pytest.mark.slow, pytest.mark.skipif(not IMG, reason="set AWTO_TEST_IMAGE=tmp/fw/<stem>")]


def test_isr_and_masked_rows():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/stall_sim.py"), f"{IMG}.bin", f"{IMG}.map"], capture_output=True, text=True,
                       env={**os.environ, "AWTO_SIM_CORE": "fast"}, timeout=300, check=False)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    rows = (ROOT / "tmp/logs/stall_sim.tsv").read_text().splitlines()[1:]
    assert any(x.startswith("isr\tTimer2\t") for x in rows) and any(x.startswith("masked EX0\t") for x in rows), rows[:5]
