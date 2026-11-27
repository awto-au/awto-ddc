"""fw_profile.py on a real image (#11): cycle accounting is self-consistent. Offline; image: fixture fw_image."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_profile_accounts_every_cycle(fw_image):
    IMG = fw_image.stem
    import fw_profile as P
    with open("/dev/null", "w") as _f:
        r = P.profile(IMG.with_suffix(".bin"), IMG.with_suffix(".map"), 3, True, _f)
    assert r["passes"] == 3
    assert abs(sum(r["excl"].values()) - r["cycles_per_pass"]) < 1       # exclusive cycles sum to the pass total
    assert r["counts"]["stub_entries"] > 10 and r["region"]["__bs_call"] > 0
    # the shadow stack's base frame _main encloses the whole pass, whatever callee the window starts in (#356: was layout dependent)
    assert abs(r["incl"]["_main"] - r["cycles_per_pass"]) < 1
    assert max(r["incl"].values()) < r["cycles_per_pass"] + 1             # no frame counted twice
