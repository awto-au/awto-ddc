"""bank_affinity: deterministic affinity packing, capacity incl. local stubs, groups / pins (awto-ddc#333 follow-up)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bank_affinity as AF


class C:
    def __init__(self, name, size, calls=(), refs=(), area="CSEG"):
        self.name, self.size, self.area = name, size, area
        self.calls, self.refs = set(calls), set(refs)
        self.sites = [(t, 0) for t in calls]
        self.common, self.bank = False, None


def _world():
    """Two call clusters a1..a4 and b1..b4 plus a CONST used by a2 only."""
    fs = [C(f"a{i}", 100, [f"a{i + 1}"] if i < 4 else [], ["ka"] if i == 2 else []) for i in range(1, 5)]
    fs += [C(f"b{i}", 100, [f"b{i + 1}"] if i < 4 else []) for i in range(1, 5)]
    funcs = {c.name: c for c in fs}
    consts = {"ka": C("ka", 50, area="CONST")}
    return funcs, consts


def _run(caps, groups=None, pins=None):
    funcs, consts = _world()
    tot, _ = AF.assign(funcs, consts, groups or {}, pins or [], lambda c: c.common, caps, log=lambda s: None)
    return funcs, consts, tot


def test_clusters_share_a_bank_and_const_follows_user():
    funcs, consts, tot = _run([500, 500])
    assert len({funcs[f"a{i}"].bank for i in range(1, 5)}) == 1
    assert len({funcs[f"b{i}"].bank for i in range(1, 5)}) == 1
    assert consts["ka"].bank == funcs["a2"].bank
    assert all(t <= 500 for t in tot)


def test_deterministic():
    r = [{n: c.bank for n, c in _run([450, 450, 450])[0].items()} for _ in range(3)]
    assert r[0] == r[1] == r[2]


def test_capacity_counts_stub_copies():
    _, _, tot = _run([460, 460, 460])
    assert all(t <= 460 for t in tot)


def test_group_stays_together():
    funcs, consts = _world()
    AF.assign(funcs, consts, {"g": [funcs["a1"], funcs["b4"]]}, [], lambda c: c.common, [500, 500], log=lambda s: None)
    assert funcs["a1"].bank == funcs["b4"].bank


def test_pin_fixed():
    funcs, consts = _world()
    AF.assign(funcs, consts, {}, [(funcs["a1"], 1)], lambda c: c.common, [500, 500], log=lambda s: None)
    assert funcs["a1"].bank == 1


def test_no_room():
    with pytest.raises(SystemExit, match="do not fit"):
        _run([200, 200])
