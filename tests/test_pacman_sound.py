"""pacman_sound.py: pitch quantisation, data format round trip, WAV, generated include. No hardware."""
from __future__ import annotations

import math
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pacman_sound as P  # noqa: E402

K = P.PS_K_DEFAULT_HZ


def test_note_hz():
    assert abs(P.note_hz("A4") - 440.0) < 1e-9
    assert abs(P.note_hz("B5") - 987.77) < 0.01


def test_all_tracks_encode_within_range_and_in_tune():
    for name, _ in P.TRACKS:
        data, plan = P.encode(name, K)
        assert data[-2:] == b"\x00\x00" and len(data) % 2 == 0
        for hz, chip, _ in plan:
            if hz > 0:
                assert abs(1200 * math.log2(chip / hz)) < 40      # within 40 cents
        for i in range(0, len(data) - 2, 2):
            sc = data[i] & 0x7F
            assert sc == 0 or P.PS_SC_MIN <= sc <= P.PS_SC_MAX
            assert 1 <= data[i + 1] <= P.PS_DUR_MAX


def test_roundtrip_duration_matches_plan():
    data, plan = P.encode("intro", K)
    assert sum(ms for _, ms in P.decode(data, K)) == sum(ms for _, _, ms in plan)


def test_octave_flag_for_low_notes():
    sc, oct_ = P.to_sc(250.0, K)
    assert oct_ == 1 and abs(P.chip_hz(sc, oct_, K) - 250.0) < 5
    assert P.to_sc(1000.0, K)[1] == 0
    assert P.to_sc(0, K) == (0, 0)


def test_k_scales_pitch():
    sc1, _ = P.to_sc(1000.0, K)
    sc2, _ = P.to_sc(1000.0, K / 2 * 1.0)
    assert sc2 * 2 in (sc1 - 1, sc1, sc1 + 1) or abs(sc2 * 2 - sc1) <= 1


def test_wav_written(tmp_path):
    data, _ = P.encode("waka", K)
    p = tmp_path / "waka.wav"
    P.write_wav(p, P.decode(data, K), "square")
    with wave.open(str(p)) as w:
        assert w.getframerate() == P.PS_WAV_RATE
        assert abs(w.getnframes() / w.getframerate() - 0.240) < 0.01


def test_inc_has_tracks_and_size():
    t = P.inc_text(K)
    for name, _ in P.TRACKS:
        assert f"AWTO_PS_OFF_{name.upper()}" in t
    n = sum(len(P.encode(name, K)[0]) for name, _ in P.TRACKS)
    assert f"#define AWTO_PS_BYTES {n}" in t
