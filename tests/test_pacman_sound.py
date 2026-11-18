"""pacman_sound.py: pitch quantisation, data format round trip, WAV, generated include. No hardware."""
from __future__ import annotations

import math
import re
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
    for fn in ("PsOff", "PsPrio", "PsLoops"):
        assert f" {fn}(BYTE ucTrack)" in t


def test_new_tracks_present_with_priorities():
    names = [n for n, _ in P.TRACKS]
    assert names[:4] == ["intro", "waka", "death", "alert"]
    pr = P.PRIORITY
    assert pr["ghost"] > pr["death"] > pr["fruit"] > pr["waka"] > pr["fright"] > pr["siren1"]
    assert pr["intro"] == pr["alert"] == max(pr.values())
    assert set(pr) == set(names)


def test_ghost_sweep_rises_and_fruit_falls_then_rises():
    ghost = [hz for hz, _ in P.decode(P.encode("ghost", K)[0], K)]
    assert all(b > a for a, b in zip(ghost, ghost[1:])) and ghost[0] < 400 and ghost[-1] > 1500
    fruit = [hz for hz, _ in P.decode(P.encode("fruit", K)[0], K) if hz > 0]
    assert fruit[0] > fruit[11] and fruit[-1] > fruit[12]


def test_siren_speeds_up_same_pitch_range():
    loops = dict(P.TRACKS)
    cycle = [sum(ms for _, ms in P.decode(P.encode(f"siren{i}", K)[0], K)) for i in (1, 2, 3)]
    assert cycle[0] > cycle[1] > cycle[2]
    for i in (1, 2, 3):
        hz = [h for h, _ in P.decode(P.encode(f"siren{i}", K)[0], K)]
        assert 500 < min(hz) < 540 and 760 < max(hz) < 800
        assert loops[f"siren{i}"]
    assert loops["fright"] and loops["waka"] and not loops["ghost"] and not loops["fruit"]


def test_firmware_ids_match_track_order():
    c = (Path(__file__).resolve().parents[1] / "fw/test/pacman_sound.c").read_text()
    ids = {n: int(re.search(rf"#define AWTO_PS_TRACK_{n}\s+(\d+)", c).group(1)) for n in ("INTRO", "WAKA", "ALERT", "GHOST", "FRUIT", "BG0")}
    names = [n for n, _ in P.TRACKS]
    assert [ids[n.upper()] for n in ("intro", "waka", "alert", "ghost", "fruit")] == [names.index(n) for n in ("intro", "waka", "alert", "ghost", "fruit")]
    assert names[ids["BG0"]:] == ["siren1", "siren2", "siren3", "fright"]
    assert int(re.search(r"#define AWTO_PS_PRIO_TOP\s+(\d+)", c).group(1)) == max(P.PRIORITY.values())


def test_game_events_include_ghost_fruit_and_siren_speeds():
    import gen_pacman_classic as G
    ev = G.build(260)[3]
    assert G.EV_GHOST in [e & 0x0F for e in ev] and G.EV_FRUIT in [e & 0x0F for e in ev]
    bg = [e >> G.BG_SHIFT for e in ev]
    assert {G.BG_SIREN_1, G.BG_SIREN_2, G.BG_FRIGHT} <= set(bg)
    assert all(bg[i] == 0 for i, e in enumerate(ev) if (e & 0x0F) in (G.EV_INTRO, G.EV_DEATH, G.EV_STOP))
