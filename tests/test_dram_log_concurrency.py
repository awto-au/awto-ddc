"""Deterministic host/firmware interleavings, virtual minutes, no monitor access.

The 5,142-row fixture has 2,866 historical and 2,276 current-boot rows. It
reproduces the reported counts; it does not claim to reconstruct the exact
hardware bus interleaving from #391 (no raw capture was provided).
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter

import pytest
from test_dram_log import EU, GEN, HDR_U, SLOTS, U0, D, Ddr, S, U, burst, fill, header

ROWS = S.load_rows(S.ROOT / "fw/awto/sync.tsv")
NOW = dt.datetime(2026, 11, 28, tzinfo=dt.UTC)
SHADOW = HDR_U - EU


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch):
    monkeypatch.setattr(D, "RETRY_S", 0)


def hdr2(hint, boot=2, gen=GEN, publication=1):
    b = bytearray(header(hint, boot, gen))
    b[2], b[11:14] = 2, publication.to_bytes(3, "big")
    b[14:16] = D._header_crc(b).to_bytes(2, "big")
    return bytes(b)


def snap(read, **kw):
    return D.snapshot(read, ROWS, None, None, "T1", 10000, NOW, **kw)


def fixture5142():
    d = Ddr()
    fill(d, 5142)
    for a in range(2866):
        d.put(a, id_=1, arg=a & 255, ms=a, val=a, boot=1)
    d.mem[HDR_U] = header(5120)
    return d


def test_391_transient_header_preserves_5142_not_only_2276_current_rows():
    d, calls = fixture5142(), Counter()

    def read(u):
        calls[u] += 1
        if u == HDR_U and calls[u] == 1:
            return d(u)[:15] + bytes([d(u)[15] ^ 1])
        return d(u)

    got = snap(read)
    assert got["status"] == "ok"
    assert got["diagnostics"]["header_retries"] == 1
    assert len(got["entries"]) == 5142
    assert sum(e["boot"] == 2 for e in got["entries"]) == 2276
    assert [e["abs"] for e in got["entries"]] == list(range(5142))


def test_391_count_reproducer_recovers_individual_transient_checksums():
    d, calls = fixture5142(), Counter()

    def read(u):
        calls[u] += 1
        if U0 <= u < U0 + 2866 * EU and calls[u] == 1:
            return d(u)[:15] + bytes([d(u)[15] ^ 1])
        return d(u)

    # The previous single-read decoder discards the historical portion.
    legacy = [a for a in range(5142) if (b := read(U0 + a * EU)) and D._sum(b) == b[15]]
    assert len(legacy) == 2276
    calls.clear()
    got = snap(read)
    assert len(got["entries"]) == 5142
    assert got["diagnostics"]["entry_retries"] == 2866


@pytest.mark.parametrize("failure, expected", [(None, "io_failure"), (b"short", "io_failure"),
                                                 (bytes(16), "absent"), (b"bad header bytes", "invalid")])
def test_header_unavailable_is_not_cold_boot(failure, expected):
    diag = {}
    assert D.header(lambda u: failure, diag) is None
    assert diag["header_status"] == expected


def test_changing_invalid_headers_are_reported_as_transient():
    calls = Counter()

    def read(u):
        calls[u] += 1
        return bytes([calls[u]]) * 16
    diag = {}
    assert D.header(read, diag) is None
    assert diag["header_status"] == "transient_checksum"


def test_failed_header_leaves_saver_state_and_history_untouched(tmp_path):
    store = U.Store("T1", tmp_path)
    store.ingest({"dram": True, **snap(fixture5142())})
    before = store.state.read_bytes(), store.log.read_bytes()
    with pytest.raises(OSError, match="unavailable"):
        store.ingest({"dram": True, **snap(lambda u: None)})
    assert before == (store.state.read_bytes(), store.log.read_bytes())


@pytest.mark.parametrize("pub1,pub2,new", [(3, 2, 64), (3, 4, 128), (0xFFFFFF, 0, 128)])
def test_dual_header_selects_latest_even_across_serial_wrap(pub1, pub2, new):
    d = Ddr()
    d.mem[HDR_U], d.mem[SHADOW] = hdr2(64, publication=pub1), hdr2(128, publication=pub2)
    assert D.header(d)["hint"] == new


@pytest.mark.parametrize("bad_unit", [HDR_U, SHADOW])
def test_dual_header_survives_torn_or_unread_new_copy(bad_unit):
    d = Ddr()
    d.mem[HDR_U], d.mem[SHADOW] = hdr2(64, publication=3), hdr2(128, publication=4)
    good = SHADOW if bad_unit == HDR_U else HDR_U
    valid = d(good)
    for cut in range(16):
        d.mem[bad_unit] = d(bad_unit)[:cut] + bytes(16 - cut)
        # If the torn update is invalid the untouched copy remains usable.
        if D._header(d(bad_unit)) is None:
            assert D.header(d) == D._header(valid)
    d.mem[bad_unit] = None
    assert D.header(d) == D._header(valid)


def test_v1_primary_wins_after_downgrade_and_ignores_stale_v2_shadow():
    d = Ddr()
    d.mem[HDR_U], d.mem[SHADOW] = header(64, gen=9), hdr2(128, gen=8, publication=100)
    assert D.header(d) == {"gen": 9, "boot": 2, "hint": 64}


def test_virtual_minutes_of_logging_do_not_restart_history():
    d = fixture5142()
    calls, virtual_seconds = Counter(), 0

    def read(u):
        nonlocal virtual_seconds
        calls[u] += 1
        if u >= U0:
            virtual_seconds += 1 / 15               # > 5 minutes for the body
            # Publish a different hint every body read. This must not restart.
            n = 5142 + int(virtual_seconds)
            d.mem[HDR_U] = header(n // 64 * 64)
        return d(u)
    got = snap(read, wr=5142)
    assert virtual_seconds > 300
    assert got["status"] == "ok" and got["next"] == 5142
    assert len(got["entries"]) == 5142
    assert calls[HDR_U] == 2
    assert max(calls[u] for u in calls if u >= U0) <= 2


def test_persistent_body_failure_keeps_later_rows_and_saver_revisits_hole(tmp_path):
    d, failed = fixture5142(), U0 + 20 * EU
    got = snap(lambda u: None if u == failed else d(u), wr=5142)
    assert got["status"] == "partial" and len(got["entries"]) == 5141
    assert got["resume"] == 20
    assert got["diagnostics"]["missing"] == [{"first": 20, "end": 21, "reason": "io_failure"}]
    store = U.Store("T1", tmp_path)
    store.ingest({"dram": True, **got})
    state = json.loads(store.state.read_text())
    assert state["abs"] == 19
    fixed = snap(d, wr=5142, since=20, expected_gen=GEN)
    added = store.ingest({"dram": True, **fixed})
    assert len(added) == 1 and "    20 " in added[0]
    assert json.loads(store.state.read_text())["abs"] == 5141


def test_newest_burst_failure_does_not_shorten_a_snapshot():
    d = fixture5142()
    got = snap(lambda u: None if u == U0 + 5125 * EU else d(u))
    assert got["status"] == "unavailable"
    assert got["entries"] == [] and got["next"] is None
    assert "boundary_error" in got["diagnostics"]


def test_stale_zero_xdata_does_not_hide_history():
    got = snap(fixture5142(), wr=0)
    assert got["next"] == 5142 and len(got["entries"]) == 5142


def test_generation_change_retains_old_entries_and_new_namespace(tmp_path):
    d = fixture5142()

    def read(u):
        b = d(u)
        if u == U0 + 1000 * EU:
            d.mem[HDR_U] = header(0, boot=1, gen=GEN + 1)
        return b
    old = snap(read, wr=5142)
    assert old["status"] == "generation_changed"
    assert len(old["entries"]) == 5142
    assert all(e["poll_wall"] is None for e in old["entries"])
    for a in range(10):
        d.mem[U0 + a * EU] = burst(1, 0, a, a, a, 1, GEN + 1)
    new = snap(d, since=5142, expected_gen=GEN)
    assert new["gen"] == GEN + 1 and new["next"] == 10
    assert new["diagnostics"]["cursor_reset"]
    store = U.Store("T1", tmp_path)
    store.ingest({"dram": True, **old})
    added = store.ingest({"dram": True, **new})
    assert len(added) == 11 and "generation changed" in added[0]
    assert json.loads(store.state.read_text())["abs"] == 9


def test_warm_boot_change_keeps_history_but_drops_clock_association():
    d = fixture5142()
    calls = Counter()

    def read(u):
        calls[u] += 1
        if u == HDR_U and calls[u] == 2:
            return header(5120, boot=3)
        return d(u)
    got = snap(read, wr=5142)
    assert got["status"] == "boot_changed" and len(got["entries"]) == 5142
    assert all(e["poll_wall"] is None for e in got["entries"])


def test_ring_overwrite_is_distinct_from_burst_failure():
    d = Ddr()
    fill(d, 200)
    d.mem[HDR_U] = header(192)
    calls = Counter()

    def read(u):
        calls[u] += 1
        if u == U0:
            for a in range(SLOTS, SLOTS + 50):
                d.put(a, id_=1, arg=0, ms=a, val=a, boot=2)
            d.mem[HDR_U] = header(SLOTS + 50)
        return d(u)
    got = snap(read, wr=200)
    assert got["status"] == "partial"
    assert len(got["entries"]) == 150
    assert got["diagnostics"]["missing"] == [{"first": 0, "end": 50, "reason": "overwritten"}]
    assert got["resume"] == 200


def test_range_below_overwrite_floor_does_not_return_an_unrequested_later_page():
    d = Ddr()
    assert D.entries(d, {"gen": GEN}, SLOTS + 1000, 100, first=0) == []


def test_random_unwritten_slot_is_a_boundary_after_bounded_identical_reads():
    d = fixture5142()
    d.mem[U0 + 5142 * EU] = bytes(range(16))
    got = snap(d)
    assert got["status"] == "ok" and len(got["entries"]) == 5142


def test_transient_body_io_recovers_without_a_hole():
    d, calls = fixture5142(), Counter()

    def read(u):
        calls[u] += 1
        return None if u == U0 + 10 * EU and calls[u] == 1 else d(u)
    got = snap(read, wr=5142)
    assert got["status"] == "ok" and len(got["entries"]) == 5142
    assert got["diagnostics"]["entry_retries"] == 1


def test_post_read_header_failure_preserves_rows_and_does_not_advance_saver(tmp_path):
    d, calls = fixture5142(), Counter()

    def read(u):
        calls[u] += 1
        return None if u == HDR_U and calls[u] > 1 else d(u)
    got = snap(read, wr=5142)
    assert got["status"] == "unverified" and len(got["entries"]) == 5142
    assert all(e["poll_wall"] is None for e in got["entries"])
    store = U.Store("T1", tmp_path)
    store.ingest({"dram": True, **got})
    assert json.loads(store.state.read_text())["abs"] == -1
    assert store.ingest({"dram": True, **snap(d, wr=5142)}) == []
    assert json.loads(store.state.read_text())["abs"] == 5141


def test_standalone_cli_reports_unavailable_without_claiming_cold_boot(monkeypatch, tmp_path):
    import ddr_frame_test as T
    import ddr_note_read as DN
    logs = []
    monkeypatch.setattr(T, "Dbg", lambda unit, bus: object())
    monkeypatch.setattr(DN, "regs", dict)
    monkeypatch.setattr(D, "ddr_reader", lambda *args: lambda u: None)
    monkeypatch.setattr(D, "log", logs.append)
    monkeypatch.setattr(S, "tsv_for", lambda path: S.ROOT / "fw/awto/sync.tsv")
    monkeypatch.setattr(D.sys, "argv", ["dram_log.py", "--map", str(tmp_path / "unused.map")])
    assert D.main() == 2
    assert "io_failure" in " ".join(logs)
    assert "cold" not in " ".join(logs)


def test_saver_does_not_fallback_to_small_xdata_ring_on_header_failure(monkeypatch):
    calls = []
    bad = {"dram": True, "status": "unavailable", "diagnostics": {"header_status": "io_failure"}, "entries": []}

    def run(argv, **kw):
        from types import SimpleNamespace
        calls.append(argv)
        return SimpleNamespace(stdout="SYNCJSON " + json.dumps(bad), stderr="", returncode=2)
    monkeypatch.setattr(U.subprocess, "run", run)
    assert U.read_snapshot("3") == bad
    assert len(calls) == 1 and "--dram" in calls[0]


def test_reset_between_clock_read_and_initial_header_drops_clock_join():
    got = snap(fixture5142(), wr=5142, clock_identity=(GEN, 1))
    assert got["status"] == "ok" and got["diagnostics"]["clock_identity_changed"]
    assert all(e["poll_wall"] is None for e in got["entries"])
