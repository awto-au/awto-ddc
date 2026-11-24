"""warn_policy_renum.py (#143): adjacent rows keep their order; a row a real warning still matches does not move."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import warn_policy_renum as R

ROWS = ["# header",
        "^a$\tSys/S.c\t3278\tok\tr",
        "^b$\tSys/S.c\t3280\tok\tr",
        "^c$\tSys/S.c\t3281\tok\tr"]


def lines(rows):
    return [r.split("\t")[2] for r in rows[1:]]


def test_adjacent_rows_all_shift():
    # #139: all three move by +2; nearest-line pairing took row 3280 for the warning at 3280
    un = [("Sys/S.c", "3280", "a"), ("Sys/S.c", "3282", "b"), ("Sys/S.c", "3283", "c")]
    rows, done, left = R.renumber(ROWS, un)
    assert lines(rows) == ["3280", "3282", "3283"] and done == 3 and not left


def test_same_pattern_adjacent_rows_no_swap():
    # #139 / #129: rows 3278, 3280, 3281 (one pattern, own reasons) all move +1; nearest-line pairing gave the 3281 warning to row 3281
    rows = [f"^w$\tS.c\t{n}\tok\treason{n}" for n in (3278, 3280, 3281)]
    un = [("S.c", "3279", "w"), ("S.c", "3281", "w"), ("S.c", "3282", "w")]
    out, done, _ = R.renumber(rows, un)
    assert [r.split("\t")[::4][0:2] for r in out] == [["^w$", "reason3278"], ["^w$", "reason3280"], ["^w$", "reason3281"]]
    assert [r.split("\t")[2] for r in out] == ["3279", "3281", "3282"] and done == 3


def test_same_pattern_rows_keep_order():
    rows = ["^w$\tF.c\t10\tok\tr", "^w$\tF.c\t11\tok\tr", "^w$\tF.c\t12\tok\tr"]
    un = [("F.c", "13", "w"), ("F.c", "12", "w"), ("F.c", "11", "w")]     # log order is not line order
    out, done, _ = R.renumber(rows, un)
    assert [r.split("\t")[2] for r in out] == ["11", "12", "13"] and done == 3


def test_satisfied_row_stays():
    # row 3280 still matches a real warning at 3280; only row 3278 moved (to 3281)
    rows = ["^w$\tS.c\t3278\tok\tr", "^w$\tS.c\t3280\tok\tr"]
    out, done, _ = R.renumber(rows, [("S.c", "3281", "w")], warnings=[("S.c", "3280", "w")])
    assert [r.split("\t")[2] for r in out] == ["3281", "3280"] and done == 1


def test_unmatched_warning_listed():
    out, done, left = R.renumber(ROWS, [("Sys/S.c", "5", "zzz")])
    assert out == ROWS and done == 0 and left == ["Sys/S.c:5: zzz"]
