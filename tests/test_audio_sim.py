"""audio_sim.py: a known S code renders the expected tone, muted / generator off render silence. No simulator, no hardware."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import itertools

import audio_sim as A

K = A.MODEL["k_hz"]
RATE = A.WAV_RATE
SC = 40                                                         # K / 40 = 1200 Hz, 600 Hz with the octave flag
AFCR_ON_FULL = A.AFCR_AUDIO_TEST_ENABLE | A.AFCR_TST_I2S_SW     # tst_i2s_sw = 1: f = K / sc
AFCR_ON_OCT = A.AFCR_AUDIO_TEST_ENABLE                          # tst_i2s_sw = 0: f = K / 2 / sc


def events(afcr: int, sc: int, mute: int = 0, en: int = 1):
    return [(0.0, "pin", "amp_en", en), (0.0, "pin", "amp_mute", mute),
            (0.1, "reg", A.IDX_AFCR, afcr), (0.1, "reg", A.IDX_SCAPR, 0x80 | sc), (0.1, "reg", A.IDX_CMCR, A.CMCR_DBDCB)]


def peak_hz(pcm: np.ndarray) -> float:
    spec = np.abs(np.fft.rfft(pcm.astype(float) * np.hanning(len(pcm))))
    return float(np.argmax(spec)) * RATE / len(pcm)


def test_tone_frequency_full_and_octave():
    for afcr, want in ((AFCR_ON_FULL, K / SC), (AFCR_ON_OCT, K / 2 / SC)):
        pcm = A.synth(events(afcr, SC), 0.2, 1.2)               # 1 s window: 1 Hz bins
        assert abs(peak_hz(pcm) - want) <= 1.0, (peak_hz(pcm), want)
        assert np.abs(pcm).max() > 0.25 * 32767


def test_silent_before_latch_muted_or_generator_off():
    assert not A.synth(events(AFCR_ON_FULL, SC), 0.0, 0.09).any()          # before the CMCR latch
    assert not A.synth(events(AFCR_ON_FULL, SC, mute=1), 0.2, 1.2).any()    # amp muted
    assert not A.synth(events(AFCR_ON_FULL, SC, en=0), 0.2, 1.2, model={"assume_amp_en": False}).any()   # amp disabled
    assert A.synth(events(AFCR_ON_FULL, SC, en=0), 0.2, 1.2).any()          # default: EN pin assumed on (see MODEL)
    assert not A.synth(events(0x40, SC), 0.2, 1.2).any()                    # generator bit off


def test_pitch_change_and_mute_gating():
    ev = events(AFCR_ON_FULL, SC) + [(1.0, "pin", "amp_mute", 1), (1.5, "pin", "amp_mute", 0),
                                     (1.5, "reg", A.IDX_SCAPR, 0x80 | 30), (1.5, "reg", A.IDX_CMCR, A.CMCR_DBDCB)]
    pcm = A.synth(ev, 0.2, 2.5)
    at = lambda t0, t1: pcm[int((t0 - 0.2) * RATE):int((t1 - 0.2) * RATE)]
    assert abs(peak_hz(at(0.2, 1.0)) - K / SC) <= 1.5
    assert not at(1.05, 1.45).any()
    assert abs(peak_hz(at(1.55, 2.5)) - K / 30) <= 1.5


def test_alert_track_bytes_render_rising_pitches():
    import snd_data_gen as P
    data = P.encode("alert", K)[0]
    ev, t, want = [(0.0, "pin", "amp_en", 1), (0.0, "pin", "amp_mute", 0)], 0.1, []
    for i in range(0, len(data) - 2, 2):
        sc, ms = data[i] & 0x7F, data[i + 1] * P.PS_TICK_MS
        octave = bool(data[i] & P.PS_OCT_FLAG)
        if sc == 0:                                             # rest
            t += ms / 1000.0
            continue
        ev += [(t, "reg", A.IDX_AFCR, AFCR_ON_OCT if octave else AFCR_ON_FULL), (t, "reg", A.IDX_SCAPR, 0x80 | sc), (t, "reg", A.IDX_CMCR, A.CMCR_DBDCB)]
        want.append((t, t + ms / 1000.0, K / (2 if octave else 1) / sc))
        t += ms / 1000.0
    pcm = A.synth(ev, 0.1, t)
    got = [peak_hz(pcm[int((a - 0.1) * RATE):int((b - 0.1) * RATE)]) for a, b, _ in want]
    assert len(got) == 3
    assert all(y > x for x, y in itertools.pairwise(got))
    assert all(abs(g - f) / f < 0.12 for g, (_, _, f) in zip(got, want))


def test_write_wav(tmp_path):
    info = A.write_wav(tmp_path / "t.wav", events(AFCR_ON_FULL, SC), 0.0, 1.0)
    with wave.open(str(tmp_path / "t.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, RATE, RATE)
    assert 0.8 < info["tone_s"] < 0.95
