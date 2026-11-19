"""audio_sim.order_violations: the pop-free order (#249). Catches: amp cut / enabled with signal, no wake gap, generator change with the amp open."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audio_sim as A

ON, OFF = A.AFCR_AUDIO_TEST_ENABLE, 0x40


def EN(t, v):
    return (t, "pin", "amp_en", v)


def MUTE(t, v):
    return (t, "pin", "amp_mute", v)


def GAIN(t, v):
    return (t, "dvc", "gain", v)


def AFCR(t, v):
    return (t, "reg", A.IDX_AFCR, v)


def PITCH(t):
    return (t, "reg", A.IDX_CMCR, A.CMCR_DBDCB)


# new order: gen on (gain 0), EN, wake, unmute, gain up | gate, pitch, ungate | gate, gain 0, gen off, EN off
NEW = [AFCR(0.0, ON), EN(0.001, 1), GAIN(0.002, 0x1000), MUTE(0.025, 0), MUTE(0.100, 1), PITCH(0.103), MUTE(0.110, 0),
       MUTE(0.500, 1), GAIN(0.503, 0), AFCR(0.504, OFF), EN(0.505, 0)]
# old order: gain up, then EN and MUTE together; pitch change with the amp open; EN and MUTE together at the end with the tone running
OLD = [AFCR(0.0, ON), GAIN(0.001, 0x1000), EN(0.002, 1), MUTE(0.002, 0), PITCH(0.100), EN(0.500, 0), MUTE(0.500, 1), GAIN(0.9, 0), AFCR(0.91, OFF)]


def test_new_order_is_clean():
    assert A.order_violations(NEW) == []


def test_old_order_fails_each_invariant():
    v = A.order_violations(OLD)
    assert any("unmuted less than" in x for x in v)                  # no wake gap
    assert any("pitch change" in x for x in v)                       # generator moved with the amp open
    assert any("amp disabled before the mute settled" in x for x in v)
    assert any("enabled while unmuted signal" in x for x in A.order_violations([AFCR(0, ON), GAIN(0.001, 5), MUTE(0.002, 0), EN(0.003, 1)]))


def test_delays_match_firmware():
    src = (Path(__file__).resolve().parents[1] / "fw/audio/audio.c").read_text()
    ms = {k: int(re.search(rf"#define {k}\s+(\d+)", src).group(1)) for k in ("AWTO_AMP_MUTE_MS", "AWTO_AMP_WAKE_MS")}
    assert (ms["AWTO_AMP_MUTE_MS"] / 1e3, ms["AWTO_AMP_WAKE_MS"] / 1e3) == (A.ORDER["amp_mute_s"], A.ORDER["amp_wake_s"])
