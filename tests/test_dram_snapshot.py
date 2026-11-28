"""Interrupted / concurrent DDR retrieval, entirely offline (#391)."""
from collections import Counter, defaultdict, deque
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dram_log as D
import sync_log as S
import unit_log as U
from test_dram_log import Ddr, GEN, HDR_U, SLOTS, U0, EU, burst, fill, header

ROWS = S.load_rows(D.ROOT / 'fw/awto/sync.tsv')
NOW = dt.datetime(2026, 11, 28, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(D, 'RETRY_S', 0)


class Reader(Ddr):
    def __init__(self, n=10, hint=0, gen=GEN, boot=2):
        super().__init__()
        self.mem[HDR_U] = header(hint, boot, gen)
        for a in range(n):
            self.put(a, id_=1, arg=a & 255, ms=a, val=a, boot=boot, gen=gen)
        self.calls = Counter()
        self.responses = defaultdict(deque)
        self.hook = None

    def __call__(self, u):
        self.calls[u] += 1
        if self.hook:
            self.hook(self, u)
        if self.responses[u]:
            r = self.responses[u].popleft()
            if isinstance(r, Exception):
                raise r
            return r
        return self.mem.get(u, bytes(16))    # unwritten DDR is not a checksummed entry

    def snap(self, **kw):
        args = dict(last=None, boot=None, serial='T1', fw_now=1000, read_at=NOW,
                    wr_identity=(GEN, 2))
        args.update(kw)
        return {"dram": True, **D.snapshot(self, ROWS, **args)}


def indexes(s):
    return [e['abs'] for e in s['entries']]


@pytest.mark.parametrize('split', range(1, 16))
def test_torn_header_at_every_byte_is_retried(split):
    r = Reader(100, 64)
    old, new = header(64, 1), header(128, 2)
    torn = old[:split] + new[split:]
    # XOR can validate some torn states; use a deliberately interrupted checksum.
    torn = torn[:15] + bytes([D._sum(torn) ^ 1])
    r.responses[HDR_U].extend([torn, r.mem[HDR_U]])
    s = r.snap(wr=100)
    assert s['status'] == 'ok' and indexes(s) == list(range(100))
    assert s['diagnostics']['retries'] == 1 and r.calls[HDR_U] == 3


@pytest.mark.parametrize('bad', [None, b'', b'DL', bytes(16), OSError('interrupted')])
def test_short_or_failed_header_recovers(bad):
    r = Reader()
    r.responses[HDR_U].append(bad)
    assert r.snap(wr=10)['complete']
    assert r.calls[HDR_U] == 3


def test_persistent_header_failure_is_not_an_empty_log():
    r = Reader()
    r.mem[HDR_U] = bytes(16)
    s = r.snap(wr=10)
    assert s['status'] == 'error' and s['retryable'] and s['entries'] == []
    assert s['error']['code'] == 'header_unavailable'
    assert sum(r.calls.values()) == D.READ_ATTEMPTS


def test_final_header_failure_does_not_publish_entries_or_reread_body():
    r = Reader()
    r.responses[HDR_U].extend([r.mem[HDR_U], None, None, None])
    s = r.snap(wr=10)
    assert s['error']['code'] == 'header_unavailable' and not s['complete']
    assert r.calls[U0] == 1


def test_normal_advancing_hint_keeps_large_read_and_transaction_budget():
    r = Reader(6000, 5952)
    r.responses[HDR_U].extend([header(5952), header(8192)])
    s = r.snap(wr=6000)
    assert indexes(s) == list(range(6000)) and s['diagnostics']['hint_advanced']
    assert sum(r.calls.values()) == 6003       # two headers + one wr-1 validation + N entries
    assert r.calls[U0] == 1                   # no restart on a moving hint


@pytest.mark.parametrize('after', [header(0, gen=GEN+1), header(0, boot=3), header(0)])
def test_generation_boot_and_index_regression_reject_mixed_snapshot(after):
    r = Reader(100, 64)
    r.responses[HDR_U].extend([r.mem[HDR_U], after])
    s = r.snap(wr=100)
    assert s['error']['code'] == 'generation_changed' and not s['entries']


def test_interrupted_entry_is_retried_locally_only():
    r = Reader()
    r.responses[U0 + 4*EU].extend([None, b'partial'])
    s = r.snap(wr=10)
    assert indexes(s) == list(range(10)) and r.calls[U0 + 4*EU] == 3
    assert sum(r.calls.values()) == 15


def test_persistent_entry_failure_leaves_saver_state_untouched(tmp_path):
    r = Reader()
    good = r.snap(wr=10)
    good['dram'] = True
    store = U.Store('T1', tmp_path)
    store.ingest(good)
    state, log = store.state.read_bytes(), store.log.read_bytes()
    r.mem[U0 + 4*EU] = bytes(16)
    bad = {**r.snap(wr=10), 'dram': True}
    assert bad['missing'] == [4] and bad['error']['code'] == 'entries_unavailable'
    with pytest.raises(OSError):
        store.ingest(bad)
    assert store.state.read_bytes() == state and store.log.read_bytes() == log


def test_actual_ring_wrap_and_overwritten_range_is_explicit():
    r = Reader(0, SLOTS)
    n = SLOTS + 7
    for a in range(7, n):
        r.put(a, id_=1, arg=0, ms=a, val=a, boot=2)
    s = r.snap(wr=n, since=0, since_gen=GEN, count=10)
    assert indexes(s) == [7, 8, 9] and s['end'] == 10
    assert s['gaps'] == [{'start': 0, 'end': 7, 'reason': 'ring_overwritten'}]


def test_overwrite_during_body_is_reported_not_silently_skipped():
    r = Reader(10)
    def hook(r, u):
        if u == U0 + 4*EU:
            r.put(4 + SLOTS, id_=1, arg=0, ms=0, val=0, boot=2)
    r.hook = hook
    s = r.snap(wr=10)
    assert s['error']['code'] == 'entries_unavailable' and s['missing'] == [4]


def test_24bit_entry_index_rollover_does_not_alias_an_old_lap():
    start = (1 << 24) - 2
    r = Reader(0, start)
    for a in range(start, start+5):
        r.put(a, id_=1, arg=0, ms=0, val=0, boot=2)
    s = r.snap(wr=start+5, since=start, count=5)
    assert indexes(s) == list(range(start, start+5))
    assert D.entry(r, start-SLOTS, GEN) is None


def test_generation_change_between_polls_resets_cursor_without_duplicates(tmp_path):
    store = U.Store('T1', tmp_path)
    a = Reader(100, 64).snap(wr=100)
    store.ingest(a)
    r = Reader(5, gen=GEN+1)
    b = r.snap(wr=5, wr_identity=(GEN+1, 2), since=100, since_gen=GEN)
    assert b['cursor_reset'] and indexes(b) == list(range(5))
    out = store.ingest(b)
    assert 'reset' in out[0] and len(out) == 6
    assert store.ingest(b) == []
    assert json.loads(store.state.read_text())['gen'] == GEN+1


def test_empty_new_generation_is_saved_then_new_records_are_accepted(tmp_path):
    store = U.Store('T1', tmp_path)
    store.ingest(Reader().snap(wr=10))
    r = Reader(0, gen=GEN+1)
    s = r.snap(since=10, since_gen=GEN)
    assert s['status'] == 'empty' and s['cursor_reset']
    store.ingest(s)
    r.put(0, id_=1, arg=0, ms=1, val=0, boot=2, gen=GEN+1)
    s = r.snap(wr=1, wr_identity=(GEN+1, 2), since=0, since_gen=GEN+1)
    assert len(store.ingest(s)) == 1


def test_warm_boot_or_power_save_retains_generation_and_indexes(tmp_path):
    store = U.Store('T1', tmp_path)
    r = Reader()
    store.ingest(r.snap(wr=10))
    r.mem[HDR_U] = header(0, boot=3)
    for a in range(10, 15):
        r.put(a, id_=1, arg=0, ms=a, val=a, boot=3)
    s = r.snap(wr=15, wr_identity=(GEN, 3), since=10, since_gen=GEN)
    assert not s['cursor_reset'] and indexes(s) == list(range(10, 15))
    assert len(store.ingest(s)) == 5
    assert store.ingest(s) == []                # retained DDR after sleep / wake


def test_page_consumes_only_requested_range_and_saver_continues(tmp_path):
    r = Reader(30)
    store = U.Store('T1', tmp_path)
    for lo in (0, 7, 14, 21, 28):
        s = r.snap(wr=30, since=lo, since_gen=GEN, count=7)
        assert s['next'] == 30 and s['end'] == min(30, lo+7)
        store.ingest(s)
        assert json.loads(store.state.read_text())['abs'] == s['end']-1
    assert len(store.log.read_text().splitlines()) == 30


def test_stale_hint_or_unreadable_boundary_is_an_error():
    r = Reader(200)
    assert r.snap()['error']['code'] == 'hint_stale'
    r = Reader(0)
    r.responses[U0].extend([None] * D.READ_ATTEMPTS)
    assert r.snap()['error']['code'] == 'boundary_unavailable'


def test_stale_xdata_identity_cannot_hide_new_generation():
    r = Reader(5, gen=GEN+1)
    s = r.snap(wr=0, wr_identity=(GEN, 2))
    assert indexes(s) == list(range(5))


def test_read_snapshot_reports_ddr_error_without_ring_fallback(monkeypatch):
    from types import SimpleNamespace
    calls = []
    def run(*a, **kw):
        calls.append(a)
        return SimpleNamespace(stdout='SYNCJSON '+json.dumps({'status': 'error', 'complete': False,
                               'error': {'message': 'header interrupted'}}), stderr='', returncode=2)
    monkeypatch.setattr(U.subprocess, 'run', run)
    monkeypatch.setattr(U, '_dram_range', lambda _: [])
    with pytest.raises(OSError, match='header interrupted'):
        U.read_snapshot('3')
    assert len(calls) == 1


def test_short_hardware_buffer_is_retried_without_index_error():
    import ddr_note_read as DN
    regs = DN.regs()
    class Debug:
        def rd(self, a):
            return DN.hdef('AWTO_DDRN_READ_FLAG') if a == regs['AWTO_R_MCU_DC_READ_FLAG_A'] else 0
        def wr(self, *args):
            pass
        def block(self, *args):
            return b'partial'
    stats = {}
    assert D.header(D.ddr_reader(Debug(), regs, stats)) is None
    assert stats['attempts'] == stats['short'] == D.READ_ATTEMPTS
    assert not stats.get('bursts')


def test_first_persistent_body_failure_bounds_work_even_for_full_ring():
    r = Reader(0, SLOTS)
    # A verified XDATA boundary, but port failures once the actual range starts.
    r.put(SLOTS-1, id_=1, arg=0, ms=0, val=0, boot=2)
    r.responses[U0].extend([None] * D.READ_ATTEMPTS)
    s = r.snap(wr=SLOTS)
    assert s['missing'] == [0] and sum(r.calls.values()) == 6


def test_saver_range_carries_generation_and_bounded_page(tmp_path, monkeypatch):
    monkeypatch.setattr(U, 'LOGDIR', tmp_path)
    monkeypatch.setattr(U, 'unit_of', lambda _: '3')
    (tmp_path/'T1-sync.state.json').write_text(json.dumps({'abs': 42, 'gen': 3}))
    args = U._dram_range('3')
    assert args == ['--since', '43', '--since-gen', '3', '--count', str(U.DRAM_PAGE)]


def test_saver_gap_marker_and_dedupe_after_wrap(tmp_path):
    store = U.Store('T1', tmp_path)
    store.ingest(Reader().snap(wr=10))
    r = Reader(0, SLOTS)
    for a in range(15, SLOTS+15):
        r.put(a, id_=1, arg=0, ms=a, val=a, boot=2)
    s = r.snap(wr=SLOTS+15, since=10, since_gen=GEN, count=10)
    out = store.ingest(s)
    assert 'gap: 5 entries' in out[0] and len(out) == 6
    assert store.ingest(s) == []


def test_extra_header_cost_in_debug_link_transactions(monkeypatch):
    """Count actual Dbg protocol calls, without a bus or monitor."""
    import dbg_xdata as X
    import ddr_frame_test as T
    import ddr_note_read as DN
    regs = DN.regs()
    class IO:
        def __init__(self):
            self.calls, self.hi, self.lo, self.chunk = 0, 0, 0, None
        def write(self, dev, sub, data):
            self.calls += 1
            if sub == X.CMD_HI:
                self.hi = data[0]
            elif sub == X.CMD_READ:
                self.lo = data[0]
            elif sub == X.CMD_BLOCK:
                self.chunk = bytes(data)
            return True
        def read(self, dev, sub, n):
            self.calls += 1
            if n == 1:
                addr = (self.hi << 8) | self.lo
                return bytes([DN.hdef('AWTO_DDRN_READ_FLAG') if addr == regs['AWTO_R_MCU_DC_READ_FLAG_A'] else 0])
            lo, hi, size, seq = self.chunk
            return bytes(size) + bytes([(seq + lo + hi) & 255])
    d = T.Dbg.__new__(T.Dbg)
    d.io = IO()
    monkeypatch.setattr(d, '_raw', lambda _: None)
    assert len(D.ddr_reader(d, regs)(HDR_U)) == 16
    assert d.io.calls == 23    # two byte reads (6), five byte writes (15), one block read (2)


def test_torn_xdata_high_byte_cannot_alias_24bit_entry_index():
    r = Reader(10)
    # Both positions have the same 24-bit index; the hint must bound the shortcut.
    s = r.snap(wr=(1 << 24) + 10)
    assert s['next'] == 10 and indexes(s) == list(range(10))
