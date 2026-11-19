"""The -D _AWTO_OSD_HWTEST image builds on the tracked layouts and leaves them untouched (#268). Run: pytest --slow tests/test_hwtest_build.py"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ("fw/bank_layout.tsv", "fw/xdata_layout.tsv")


@pytest.mark.slow
def test_hwtest_image_builds_and_layouts_stay():
    before = [(ROOT / f).read_bytes() for f in TRACKED]
    r = subprocess.run([sys.executable, str(ROOT / "dev.py"), "build", "--unit", "3", "--tag", "hwtest-ci", "-D", "_AWTO_OSD_HWTEST=_ON"],
                       cwd=ROOT, capture_output=True, text=True, check=False)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    assert before == [(ROOT / f).read_bytes() for f in TRACKED]
