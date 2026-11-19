"""reg_behind_probe against a fake debug slave with the read-behind artifact. No hardware."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dbg_xdata as X
import reg_behind_probe as P
import reg_live_scan as S


def truth(a):
    return S.ID_VALUE if a == S.ID_ADDR else (a * 37 + (a >> 8) * 11 + 1) & 0xFF


class BehindBus:
    """Byte path: on `behind` pages the first read in a new 32-bit dword returns the same lane of the previous dword.
    Block path: `block_ok` = clean chunk, else the byte at every dword start (and the first) is stale."""

    def __init__(self, behind=(), block_ok=True):
        self.behind, self.block_ok = set(behind), block_ok
        self.hi = 0
        self.latch = 0
        self.last = None
        self.reply = None
        self.reads = []

    def _byte(self, a):
        self.reads.append(a)
        newdw = self.last is None or (a >> 2) != (self.last >> 2)
        out = truth((self.last & ~3) | (a & 3)) if (a >> 8) in self.behind and newdw and self.last is not None else truth(a)
        self.last = a
        return out

    def write(self, dev8, sub, data):
        if sub == X.CMD_HI:
            self.hi = data[0]
        elif sub == X.CMD_READ:
            self.reply = bytes([self._byte((self.hi << 8) | data[0])])
        elif sub == X.CMD_BLOCK:
            lo, hi, n, seq = data
            a = lo | hi << 8
            self.reads += range(a, a + n)
            d = bytes(truth(a + i) if self.block_ok or (a + i) & 3 else truth(a + i - 4) for i in range(n))
            self.reply = d + bytes([(seq + lo + hi + sum(d)) & 0xFF])
            self.last = a + n - 1
        return True

    def read(self, dev8, sub, n):
        return self.reply


def run(bus, pages, block=True):
    lines = []
    res = P.run_probe(bus, pages, block, lines.append, lambda r: None, 1e9)
    return res, lines


def test_dword_rule_is_found_and_the_repeat_read_is_right():
    res, _ = run(BehindBus(behind={0x10}), [0x00, 0x10, 0x11], block=False)
    assert res["result"] == "ok"
    assert P.verdict(res["pages"]["11"])[0] == "no"
    r = res["pages"]["10"]
    v, txt = P.verdict(r)
    assert v == "yes" and "same dword: wrong 0 of" in txt
    assert r["new_dword"]["wrong"] > 100 and r["same_dword"]["wrong"] == 0
    assert r["far2"]["stale"] + r["far2"]["lane"] + r["far2"]["other"] == 0
    assert r["new_dword"]["kinds"]["lane"] > 100 and r["new_dword"]["kinds"]["other"] == 0


def test_block_dword_start_staleness_is_reported_per_position():
    res, _ = run(BehindBus(block_ok=False), [0x20])
    b = res["pages"]["20"]["block"]
    assert b["b1_dwstart_lane"] > 20 and b["b1_inside_lane"] == 0 and b["b1_inside_ok"] > 50
    res, _ = run(BehindBus(block_ok=True), [0x20])
    b = res["pages"]["20"]["block"]
    assert b["b1_dwstart_lane"] == 0 and b["b1_dwstart_ok"] > 20


def test_time_varying_register_is_not_counted_as_read_behind():
    bus = BehindBus()
    orig = bus._byte
    n = [0]

    def moving(a):
        v = orig(a)
        if a == 0x3010:
            n[0] += 1
            return (v + n[0] // 2) & 0xFF
        return v
    bus._byte = moving
    res, _ = run(bus, [0x30], block=False)
    assert res["pages"]["30"]["tv"] >= 1 and P.verdict(res["pages"]["30"])[0] == "no"


def test_excluded_addresses_are_never_read_and_heartbeat_aborts():
    bus = BehindBus()
    run(bus, [0xFF, 0x8F], block=True)
    assert not [a for a in bus.reads if S.excluded(a) and a != S.ID_ADDR]
    bad = BehindBus()
    bad.latch = 0
    orig = bad._byte
    bad._byte = lambda a: 0x00 if a == S.ID_ADDR else orig(a)
    res, _ = run(bad, [0x10], block=False)
    assert res["result"] == "aborted" and "heartbeat" in res["abort"]


def test_every_read_is_logged():
    _res, lines = run(BehindBus(), [0x12], block=False)
    assert sum(1 for ln in lines if " d1 prev=" in ln) == 256
    assert any("farpre" in ln for ln in lines)


def test_targeted_block_test_sees_a_stale_dword_start_inside_a_block():
    bad, _ = run(BehindBus(block_ok=False), [0x21])
    t = bad["pages"]["21"]["block"]["targeted"]
    assert t["in_block_lane"] > 5 and t["in_block_ok"] == 0
    good, _ = run(BehindBus(block_ok=True), [0x21])
    t = good["pages"]["21"]["block"]["targeted"]
    assert t["in_block_ok"] > 5 and t["in_block_lane"] == 0 and t["first_after_far_ok"] > 5


def test_tool_page_set_matches_the_typed_result_file():
    import regmap_lib as L
    assert set(X.BEHIND_PAGES) == L.read_behind_pages("live")
    assert L.read_behind_pages("isp") <= L.read_behind_pages("live")


def test_old_reads_of_read_behind_pages_are_dropped_fixed_scans_kept():
    import regmap_lib as L
    vals = {"8E10": 1, "8E11": 2, "A711": 3, "2000": 4, "8E10:01": 5}
    old, n = L.strip_behind({"method": "live"}, dict(vals))
    assert n == 3 and set(old) == {"2000", "8E10:01"}
    meta = {"method": "live"}
    L.strip_behind(meta, dict(vals))
    assert "pages=8E,A7" in meta["read_behind_stripped"]
    assert L.strip_behind(meta, dict(vals))[1] == 0                     # idempotent: stamped pages are done
    assert L.strip_behind({"method": "live", "read_fix": "dword-discard"}, dict(vals))[1] == 0
    isp, n = L.strip_behind({"method": "isp"}, {"A711": 3, "8E11": 2})   # A pages read clean over ISP
    assert n == 1 and set(isp) == {"A711"}
