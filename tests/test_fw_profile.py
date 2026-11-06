"""fw_profile.py on a real image (#11): cycle accounting is self-consistent. Offline; skips when the image is absent."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
IMG = ROOT / "tmp/fw/AWT26110003-wb-sc1-be"
pytestmark = pytest.mark.skipif(not IMG.with_suffix(".bin").exists() or not IMG.with_suffix(".map").exists(),
                                reason="image tmp/fw/AWT26110003-wb-sc1-be.{bin,map} absent")


def test_profile_accounts_every_cycle():
    import fw_profile as P
    r = P.profile(IMG.with_suffix(".bin"), IMG.with_suffix(".map"), 3, True, open("/dev/null", "w"))
    assert r["passes"] == 3
    assert abs(sum(r["excl"].values()) - r["cycles_per_pass"]) < 1       # exclusive cycles sum to the pass total
    assert r["counts"]["stub_entries"] > 10 and r["region"]["__bs_call"] > 0
    assert r["incl"]["_main"] >= r["cycles_per_pass"] * 0.99             # main encloses the pass
