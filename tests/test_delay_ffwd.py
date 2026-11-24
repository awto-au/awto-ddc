"""Current naked-delay equivalence, plus the optional full-firmware boot check.

The portable sweep assembles delay.c directly and compares all C-core state.
The full boot check still needs fw_image and --slow; its expected failure is
retained until an actual full-image run passes (awto-ddc#342).
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")


def test_every_count_of_both_routines_state_identical(tmp_path):
    from test_counted_ffwd import check_current_delay_sequences
    check_current_delay_sequences(tmp_path)


def machine(img, ffwd):
    import fw_sim as S
    bus = S.SimBus(img.with_suffix(".bin"), img.with_suffix(".map"), "ffwdtest", None,
                   boot=False, video="1080p60")
    bus.m.core.set_counted_ffwd(ffwd)
    assert bus.run_until_mode(3)
    bus.dbg_link_on()
    return bus


@pytest.mark.slow
@pytest.mark.xfail(strict=True, reason="awto-ddc#342: full-image native boot equivalence still requires a passing run")
def test_scenario_stays_within_the_stop_granularity_noise(fw_image):
    """Native batching adds no host stops: require exact boot + 3 s equality.

    Keep the historical test name to preserve node IDs. Remove this xfail only
    after a real image run passes, not because the portable sweep passes.
    """
    import hashlib
    res = []
    for on in (False, True):
        bus = machine(fw_image.stem, on)
        try:
            bus.wait(3.0)
            c, m = bus.m.core, bus.m
            h = hashlib.sha256()
            for v in (bytes(c.p), bytes(c.iram), bytes(c.sfr), bytes(c.xram),
                      bytes(c.opcount), bytes(c.cycop), bytes(c.lacc), bytes(c.lmiss)):
                h.update(v)
            res.append((h.hexdigest(), m.instr, m.ticks, m.wall_ms, bus.diag_t2()))
        finally:
            bus.close()
    assert res[0] == res[1], res
