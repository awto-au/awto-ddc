"""Front-key ADC bands (awto-ddc, Dan 2026-11-19 ADC / GPIO scan review): our table vs the Dahua firmware, edges, key click centres."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import key_bands as B  # noqa: E402


def test_table_equals_dahua():
    assert B.ours() == B.DAHUA


def test_idle_and_extremes_decode_no_key():
    t = B.ours()
    for a0 in (0x00, B.IDLE, 0xFF):
        for a1 in (0x00, B.IDLE, 0xFF):
            assert B.keys_for(t, a0, a1) == set(), (a0, a1)


def test_bands_disjoint_per_ladder_and_on_5bit_codes():
    t = B.ours()
    for lad in ("A0", "A1"):
        rows = sorted((lo, hi, k) for k, (l, lo, hi) in t.items() if l == lad)
        for (lo1, hi1, k1), (lo2, hi2, k2) in zip(rows, rows[1:]):
            assert hi1 <= lo2, f"{k1} and {k2} overlap on {lad}"
    for k, (lad, lo, hi) in t.items():
        assert lo % B.CODE_STEP == 0 and hi % B.CODE_STEP == 0, f"{k}: edges not on 5-bit codes"
        assert (hi - lo) // B.CODE_STEP == 4, f"{k}: band is not 4 codes wide"


def test_one_key_per_code_and_edges():
    t = B.ours()
    for lad, v in B.edge_values(t):
        a0, a1 = (v, B.IDLE) if lad == "A0" else (B.IDLE, v)
        hit = B.keys_for(t, a0, a1)
        want = {k for k, (l, lo, hi) in t.items() if l == lad and lo <= v < hi}
        assert hit == want and len(hit) <= 1, (lad, v, hit)
    for k, (lad, lo, hi) in t.items():           # min / min - 1 / max / max + 1 of every band
        v = lambda x: (x, B.IDLE) if lad == "A0" else (B.IDLE, x)    # noqa: E731
        assert B.keys_for(t, *v(lo)) == {k}
        assert B.keys_for(t, *v(lo - 1)) == set()
        assert B.keys_for(t, *v(hi - 1)) == {k}
        assert B.keys_for(t, *v(hi)) == set()


def test_sim_press_centres_inside_bands():
    import key_sim_test as K
    t = B.ours()
    for k, (reg, v) in K.KEY_ADC.items():
        lad, lo, hi = t[k]
        assert (reg == K.A0) == (lad == "A0") and lo <= v < hi, k
