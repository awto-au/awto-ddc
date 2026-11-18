"""reg_live_scan against a fake debug slave: exclusion list, abort logic, JSON format. No hardware."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dbg_xdata as X  # noqa: E402
import reg_live_scan as S  # noqa: E402


class FakeBus:
    """XDATA = addr & 0xFF except ID_REG = 0xCF; byte path + block path; records every address read."""

    def __init__(self, block=True, fail=lambda addr: False, version=2):
        self.mem = lambda a: S.ID_VALUE if a == S.ID_ADDR else (0xFF if a in (0xF6D0, 0xF6D1) else a & 0xFF)
        self.block, self.fail, self.version = block, fail, version
        self.reads, self.writes = [], []
        self.hi = self.lo = 0
        self.reply = None

    def write(self, dev8, sub, data):
        self.writes.append((sub, bytes(data)))
        if sub == X.CMD_HI:
            self.hi = data[0]
        elif sub == X.CMD_READ:
            a = (self.hi << 8) | data[0]
            self.reads.append(a)
            self.reply = None if self.fail(a) else bytes([self.mem(a)])
        elif sub == X.CMD_BLOCK:
            lo, hi, n, seq = data
            a = lo | hi << 8
            self.reads += range(a, a + n)
            if self.block and not any(self.fail(a + i) for i in range(n)):
                d = bytes(self.mem(a + i) for i in range(n))
                self.reply = d + bytes([(seq + lo + hi + sum(d)) & 0xFF])
            else:
                self.reply = None
        return True

    def read(self, dev8, sub, n):
        return self.reply


def run(bus, pages, block, wall_s=None):
    lines, saves = [], []
    res = S.run_pass(bus, pages, block, lines.append, lambda r: saves.append(json.dumps(r)), wall_s, {0})
    return res, lines, saves


def test_exclusion_table_has_a_reason_per_entry_and_covers_the_named_ranges():
    assert all(why for _, _, why in S.EXCLUDE)
    for a in (0x0024, 0x002B, 0x0092, 0x0099, 0x71C4, 0x72C4, 0xFF22, 0xFF2F, 0xFE60, 0xFE6F, 0xFF00, 0xFF03, 0xFF07,
              0x8FF0, 0x8FF7, 0xCFF0, 0xCFF7, 0x07CA, 0x07D9, 0x0069, 0x006D, 0xBAC4, 0x713A):
        assert S.excluded(a), hex(a)
    for a in (0x0000, 0xFF09, 0xFF0C, 0x06A4, 0xA750, 0xFF01, 0xFF08, 0x8FEF, 0xCFF8):
        assert S.excluded(a) is None, hex(a)


def test_excluded_addresses_are_never_read_byte_and_block_path():
    for block in (False, True):
        bus = FakeBus(block=block)
        res, lines, _ = run(bus, [0x00, 0xFF, 0x8F, 0xCF], block)
        assert res["result"] == "ok"
        assert not [a for a in bus.reads if S.excluded(a)]
        assert any("EXCLUDED" in ln and ln.startswith("FF22") for ln in lines)
        assert res["pages"]["FF"][0x22] is None and res["pages"]["FF"][0x09] == 0x09


def test_block_chunks_split_at_excluded_addresses():
    r = S.runs(0xFF, maxlen=24)
    assert all(n <= 24 for _, n in r)
    covered = {a + i for a, n in r for i in range(n)}
    assert covered == {0xFF00 + i for i in range(256)} - {a for a in range(0xFF00, 0x10000) if S.excluded(a)}


def test_json_format_and_every_read_logged():
    res, lines, saves = run(FakeBus(), [0x10, 0x11], True)
    assert set(res) >= {"path", "pages", "heartbeats", "result", "abort", "calibration", "reads_ok", "reads_failed", "elapsed_s", "wall_s"}
    assert res["path"] == "block" and len(res["pages"]["10"]) == 256 and res["pages"]["10"][5] == 5
    assert [h["tag"] for h in res["heartbeats"]][0] == "before" and res["heartbeats"][-1]["tag"] == "after"
    assert all(h["value"] == 0xCF for h in res["heartbeats"])
    assert len(saves) == 2 and json.loads(saves[-1])["pages"]["11"][7] == 7
    assert sum(1 for ln in lines if ln.startswith("1005 05 ok")) == 1       # one line per byte read
    assert any(ln.startswith("CALIB") for ln in lines)


def test_heartbeat_every_64_reads_on_unknown_pages():
    res, _, _ = run(FakeBus(), [0x20], False)       # known = {0}: page 20 is unknown
    assert len(res["heartbeats"]) >= 2 + 256 // S.HB_UNKNOWN - 1


def test_three_consecutive_failures_abort_and_keep_partial_data():
    bus = FakeBus(block=False, fail=lambda a: 0x1040 <= a < 0x1050)
    res, lines, _ = run(bus, [0x10, 0x11], False)
    assert res["result"] == "aborted" and "3 consecutive" in res["abort"]
    assert res["pages"]["10"][0x3F] == 0x3F and res["pages"]["10"][0x40] is None
    assert "11" not in res["pages"] and 0x1043 not in bus.reads           # stops at once, no retry loop
    assert any(ln.startswith("ABORT") for ln in lines)


def test_two_failures_in_a_row_then_success_does_not_abort():
    bus = FakeBus(block=False, fail=lambda a: a in (0x1040, 0x1041))
    res, _, _ = run(bus, [0x10], False)
    assert res["result"] == "ok" and res["reads_failed"] == 2 and res["pages"]["10"][0x42] == 0x42


def test_failed_heartbeat_aborts():
    bus = FakeBus(block=False)
    bus.mem = lambda a: 0x00 if a == S.ID_ADDR else a & 0xFF
    res, _, _ = run(bus, [0x10], False)
    assert res["result"] == "aborted" and "heartbeat before" in res["abort"] and res["pages"] == {}


def test_wall_bound_aborts():
    res, _, _ = run(FakeBus(block=False), [0x10, 0x11, 0x12], False, wall_s=0.0)
    assert res["result"] == "aborted" and "wall bound" in res["abort"]


def test_per_read_limit_is_1_25_x_calibration_worst_and_far_too_slow_reads_count_as_failures():
    t = [0.0]
    bus = FakeBus(block=False)
    orig = bus.write

    def slow_write(dev8, sub, data):
        t[0] += 0.001                                  # 1 ms per transaction while calibrating
        if sub == X.CMD_READ and data[0] >= 0x80 and bus.hi == 0x10:
            t[0] += 0.100                              # 101 ms > 10 x limit
        return orig(dev8, sub, data)
    bus.write = slow_write
    lines = []
    res = S.run_pass(bus, [0x10], False, lines.append, lambda r: None, 1000.0, {0x10}, clock=lambda: t[0])
    assert abs(res["calibration"]["limit_ms"] - 1.25 * res["calibration"]["worst_ms"]) < 0.01
    assert res["result"] == "aborted" and res["reads_slow"] >= 2
    assert any(" SLOW " in ln for ln in lines)


def test_moderately_slow_reads_are_logged_but_do_not_abort():
    t = [0.0]
    bus = FakeBus(block=False)
    orig = bus.write

    def w(dev8, sub, data):
        t[0] += 0.001
        if sub == X.CMD_READ and bus.hi == 0x10:
            t[0] += 0.004                              # 5 ms vs 1 ms limit-ish: 1..10 x limit
        return orig(dev8, sub, data)
    bus.write = w
    lines = []
    res = S.run_pass(bus, [0x10], False, lines.append, lambda r: None, 1000.0, {0x10}, clock=lambda: t[0])
    assert res["result"] == "ok" and res["reads_slow"] > 100 and res["reads_failed"] == 0


class BehindBusScan(FakeBus):
    """XDATA = addr & 0xFF; on read-behind pages the first read of a new dword returns the previous read's dword byte of the same lane
    (byte path), and every dword start of a block read does (block path)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.last = None
        self.behind = frozenset(X.BEHIND_PAGES)           # the hardware, whatever the scan believes

    def _val(self, a, prev):
        if (a >> 8) in self.behind and prev is not None and (a >> 2) != (prev >> 2):
            return self.mem((prev & ~3) | (a & 3))
        return self.mem(a)

    def write(self, dev8, sub, data):
        if sub == X.CMD_READ:
            a = (self.hi << 8) | data[0]
            v = self._val(a, self.last)
            self.last = a
            self.reads.append(a)
            self.reply = bytes([v])
            return True
        if sub == X.CMD_BLOCK:
            lo, hi, n, seq = data
            a = lo | hi << 8
            self.reads += range(a, a + n)
            d = bytes(self._val(a + i, self.last if i == 0 else a + i - 1) for i in range(n))
            self.last = a + n - 1
            self.reply = d + bytes([(seq + lo + hi + sum(d)) & 0xFF])
            return True
        return super().write(dev8, sub, data)


def test_read_behind_pages_are_discard_read_and_come_out_right_on_both_paths():
    for block in (False, True):
        bus = BehindBusScan(block=block)
        res, lines, _ = run(bus, [0x8E, 0xA0, 0x20], block)
        assert res["result"] == "ok" and res["read_fix"] == "dword-discard" and "8E" in res["behind_pages"]
        for pg in ("8E", "A0", "20"):
            assert all(v == i for i, v in enumerate(res["pages"][pg])), (block, pg)
        assert res["discards"] >= 64 * 2 and sum(1 for ln in lines if "DISCARD" in ln) == res["discards"]
        if block:                                           # clean pages keep the 24-byte transactions
            assert any(ln.endswith("blk24") for ln in lines if ln.startswith("20"))
            assert not any("blk" in ln for ln in lines if ln[:2] in ("8E", "A0"))


def test_without_the_fix_the_fake_bus_corrupts_lane0(monkeypatch):
    bus = BehindBusScan(block=False)
    monkeypatch.setattr(X, "BEHIND_PAGES", frozenset())          # a scan that does not know the page
    rd = S.Reader(bus, False, lambda s: None)
    got = [rd.read(0x8E00 + i, 1)[0] for i in range(8)]
    assert got != list(range(8)) and got[1:4] == [1, 2, 3] and got[4] != 4


def test_heartbeat_is_confirmed_once_before_it_aborts():
    calls = []

    class Hb(FakeBus):
        def write(self, dev8, sub, data):
            ok = super().write(dev8, sub, data)
            if sub == X.CMD_READ and self.hi == 0 and data[0] == 0:
                calls.append(1)
                if len(calls) == 1:
                    self.reply = bytes([0])               # one stale read, the confirm is right
            return ok
    res, lines, _ = run(Hb(block=False), [0x10], False)
    assert res["result"] == "ok" and any("confirm" in ln for ln in lines)


def test_dbg_xdata_read_blocks_uses_the_byte_path_inside_read_behind_pages():
    bus = BehindBusScan(block=True)
    got = X.read_blocks(bus, 0x8DF0, 0x40)                  # crosses 8D -> 8E
    assert got == bytes((0x8DF0 + i) & 0xFF for i in range(0x40))
    assert X.read_bytes(BehindBusScan(), 0x8E10, 16) == bytes(range(0x10, 0x20))
    assert X.read_byte(BehindBusScan(), 0x8E13) == bytes([0x13])
