"""scripts/ddr_levels.py: byte stream <-> levels <-> frame (awto-ddc#347)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ddr_levels as L

N = len(L.load_table()[0])


@pytest.mark.parametrize("ln", [0, 1, 2, 30, 31, 32, 61, 62, 63, 1000, 4097])
def test_round_trip_lengths(ln):
    data = np.random.default_rng(ln).integers(0, 256, ln, dtype=np.uint8).tobytes()
    lv = L.to_levels(data, N)
    assert lv.max(initial=0) < N and len(lv) % L.digits_per_chunk(N) == 0
    assert L.from_levels(lv, N) == data


def test_all_ff_and_zero_chunks():
    for b in (0x00, 0xFF):
        data = bytes([b]) * 93
        assert L.from_levels(L.to_levels(data, N), N) == data


def test_table_edges_and_monotonic():
    sent, stored = L.load_table()
    assert stored[0] == 16 and stored[-1] == 234
    assert all(stored[i] < stored[i + 1] for i in range(len(stored) - 1))
    assert len(set(sent.tolist())) == len(sent) and all(sent[i] < sent[i + 1] for i in range(len(sent) - 1))


def test_digits_fit_248_bits():
    d = L.digits_per_chunk(N)
    assert N ** d >= 1 << 248 > N ** (d - 1)


def test_bad_level_and_bad_header():
    lv = L.to_levels(b"abc", N)
    bad = lv.copy()
    bad[0] = N
    with pytest.raises(ValueError):
        L.from_levels(bad, N)
    with pytest.raises(ValueError):
        L.from_levels(lv[:-1], N)


def test_frame_layout_round_trip():
    data = np.random.default_rng(5).integers(0, 256, 100_000, dtype=np.uint8).tobytes()
    lv = L.memory_levels(data, 7)
    f = L.frame_from_levels(lv)
    assert f.shape == (2160, 3840, 3)
    assert (f[0::2] == f[1::2]).all()
    sent, stored = L.load_table()
    # memory (line, pixel, channel) = frame row 2*line, x 3839 - pixel; the capture stores stored[level]
    mem = np.empty((1080, 3840, 3), np.uint8)
    lut = np.zeros(256, np.uint8)
    lut[sent] = stored
    mem[:] = lut[f[0::2, ::-1, :]]
    back = L.levels_from_stored(mem.reshape(-1))
    assert (back == lv).all()
    assert L.from_levels(back[:len(L.to_levels(data, N))], N) == data


def test_levels_from_stored_flags_unknown():
    assert L.levels_from_stored(np.array([15, 16, 235], np.uint8)).tolist() == [255, 0, 255]


def test_capacity():
    assert L.capacity_bytes(N) == 12_052_792
