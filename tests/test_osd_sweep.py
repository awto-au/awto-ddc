"""scripts/osd_sweep.py: the case table stays inside the register envelope and mirrors the firmware struct."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import osd_sweep as S


def test_every_case_is_inside_the_envelope():
    for group, lst in S.cases().items():
        names = [c.name for c in lst]
        assert len(names) == len(set(names)), group
        for c in lst:
            assert S.check_case(c) is None, (c.name, S.check_case(c))


def test_envelope_refuses():
    for bad in (S.Case("a", fff1=0x10), S.Case("b", ffbc=32), S.Case("c", fffb=256), S.Case("d", n=8193), S.Case("e", n=100),
                S.Case("f", S.M_BURST, chunk=100), S.Case("g", S.M_BURST, chunk=S.BUF, n=1848)):
        assert S.check_case(bad), bad.name


def test_sweeps_cover_every_legal_value():
    g = S.cases()
    assert sorted(c.fff1 for c in g["fff1"] if c.fff1 < 0x80) == list(range(16))
    assert 0 in [c.fffb for c in g["fffb"]] and 255 in [c.fffb for c in g["fffb"]]
    assert next(c.ffbc for c in g["ffbc"]) == 15 and [c.ffbc for c in g["ffbc"]][-1] == 0      # reset value first, undocumented 0 last


def test_struct_offsets_are_sequential():
    offs = [S.W_GO, S.W_SEQ, S.W_STATE, S.W_REFUSE, S.W_APPLY, S.W_FFF1, S.W_FFFB, S.W_FFBC, S.W_MODE, S.W_FLAGS, S.W_SEED, S.W_REPS,
            S.W_ADDR, S.W_N, S.W_CHUNK, S.W_HOLD, S.W_MS, S.W_NOW_F1, S.W_NOW_FB, S.W_NOW_BC, S.W_STK_F1, S.W_STK_FB, S.W_STK_BC,
            S.W_PASSES, S.W_RESTARTS, S.W_FIFO_PRE, S.W_FIFO_POST, S.W_NOWMS]
    assert offs == sorted(offs) and len(set(offs)) == len(offs)
    assert S.W_NOWMS + 2 == S.W_SIZE and S.W_FIFO_POST + S.FIFO_N == S.W_NOWMS
    assert len(S.params(S.Case("x"), 1, 0)) == S.W_MS - S.W_APPLY


def test_params_encoding():
    p = S.params(S.Case("x", S.M_BURST, fff1=3, fffb=7, chunk=S.BUF), 9, 0x3C, 1234)
    assert p[0] == S.A_F1 | S.A_FB and p[1] == 3 and p[2] == 7 and p[4] == S.M_BURST and p[6] == 0x3C and p[7] == 9
    assert int.from_bytes(p[8:10], "big") == S.ADDR_TOP and int.from_bytes(p[10:12], "big") == S.N_BURST and int.from_bytes(p[14:16], "big") == 1234


def test_reps_keep_the_op_inside_the_firmware_limit():
    for lst in S.cases().values():
        for c in lst:
            r = S.reps_for(c, False)
            assert 1 <= r <= 255
            assert r * c.nbytes * S.EST_US[c.mode] / 1000 < S.FW_MAX_MS or r == 1, c.name


def test_best_values_and_combos():
    rows = [{"pass": True, "mode": S.MODE_NAMES[S.M_TRIPLE], "fff1": "0", "fffb": "None", "ffbc": "None", "us_per_b": "1.0"},
            {"pass": True, "mode": S.MODE_NAMES[S.M_TRIPLE], "fff1": "2", "fffb": "None", "ffbc": "None", "us_per_b": "1.2"},
            {"pass": True, "mode": S.MODE_NAMES[S.M_TRIPLE], "fff1": "None", "fffb": "1", "ffbc": "None", "us_per_b": "0.9"},
            {"pass": False, "mode": S.MODE_NAMES[S.M_TRIPLE], "fff1": "None", "fffb": "None", "ffbc": "0", "us_per_b": "0.1"}]
    best = S.best_values(rows)
    assert best == {"fff1": 0, "fffb": 1}
    assert [c.name for c in S.combo_cases(best)] == ["combo_fff1_fffb"]


def test_fifo_new_only_reports_new_bits():
    pre, post = bytes([0, 1, 0, 0, 0]), bytes([2, 1, 0, 0, 0x40])
    assert S.fifo_new(pre, post) == "dispM1:02,status0:40"
