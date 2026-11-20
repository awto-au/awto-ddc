"""Unit log saver (scripts/unit_log.py): append, dedupe by ring sequence, reset / loss markers, host notes, flash guard, parsing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import unit_log as U

WRAP, N = 240, 80


def ent(seq: int, text: str = "", id_: int = 0x01, val: int = 0, wall: str | None = None) -> dict:
    raw = bytes([id_, seq & 0xFF, 0, 1, 0, 0, 0, val & 0xFF]).hex()
    return {"seq": seq % WRAP, "raw": raw, "text": text or f"line {seq}", "id": id_, "val": val, "wall": wall, "sure": wall is not None}


def snap(first: int, count: int, read: str = "2026-11-21T10:00:00.000+10:00", **kw) -> dict:
    ents = [ent(first + k) for k in range(count)][-N:]
    return {"serial": "T1", "read": read, "seq": (first + count) % WRAP, "n": N, "wrap": WRAP, "ep_seq": 0, "kind": "power on",
            "lost": 0, "entries": ents, **kw}


def lines(d: Path) -> list[str]:
    return (d / "T1-sync.log").read_text().splitlines()


def test_first_read_saves_everything_then_only_new_lines(tmp_path):
    s = U.Store("T1", tmp_path)
    assert len(s.ingest(snap(0, 10))) == 10
    assert s.ingest(snap(0, 10)) == []                              # same ring: nothing appended
    out = s.ingest(snap(0, 13, read="2026-11-21T10:00:30.000+10:00"))
    assert [x.split()[-1] for x in out] == ["10", "11", "12"]
    assert len(lines(tmp_path)) == 13


def test_survives_console_open_close_and_reads_between(tmp_path):
    s = U.Store("T1", tmp_path)
    for first, count in ((0, 5), (0, 5), (0, 9), (0, 9), (0, 20)):  # a console open / close does not touch the ring: same snapshots
        s.ingest(snap(first, count))
    assert [x.split()[1] for x in lines(tmp_path)] == [str(k) for k in range(20)]


def test_ring_wrap_inside_the_window_is_continuous(tmp_path):
    s = U.Store("T1", tmp_path)
    s.ingest(snap(0, 70))
    out = s.ingest(snap(0, 110))                                     # 40 more lines, ring holds the last 80
    assert [x.split()[1] for x in out] == [str(k % WRAP) for k in range(70, 110)]


def test_lost_lines_marker_when_more_than_n_between_polls(tmp_path):
    s = U.Store("T1", tmp_path)
    s.ingest(snap(0, 10))
    out = s.ingest(snap(60, 100))
    assert out[0].startswith("#") and "gap" in out[0]
    assert len(out) == 1 + N


def test_cold_restart_marker_and_all_entries_again(tmp_path):
    s = U.Store("T1", tmp_path)
    s.ingest(snap(0, 50))
    fresh = snap(0, 4)
    fresh["entries"] = [ent(k, f"new {k}", val=9) for k in range(4)]  # different bytes at the saved tail position
    out = s.ingest(fresh)
    assert "gap" in out[0] and len(out) == 5


def test_warm_reset_keeps_ring_so_it_continues(tmp_path):
    s = U.Store("T1", tmp_path)
    s.ingest(snap(0, 60))
    out = s.ingest(snap(0, 70))                                      # the new boot's lines follow the old ones in the same ring
    assert len(out) == 10 and not any(x.startswith("#") for x in out)


def test_unit_reset_survival_of_saver_state(tmp_path):
    U.Store("T1", tmp_path).ingest(snap(0, 8))
    out = U.Store("T1", tmp_path).ingest(snap(0, 9))                 # a new Store (saver restarted) reads the state file
    assert len(out) == 1 and (tmp_path / "T1-sync.state.json").exists()


def test_host_time_marks(tmp_path):
    s = U.Store("T1", tmp_path)
    e = ent(0, wall="2026-11-21T09:59:59.500+10:00")
    out = s.ingest({**snap(0, 1), "entries": [e, {**ent(1)}], "seq": 2})
    assert out[0].startswith("2026-11-21T09:59:59.500+10:00 ") and out[1].startswith("2026-11-21T10:00:00.000+10:00~")


def test_host_note_text_is_kept_and_ring_entry_not_duplicated(tmp_path):
    U.note_written("T1", 7, "mark 1", tmp_path)
    s = U.Store("T1", tmp_path)
    out = s.ingest({**snap(0, 1), "entries": [ent(0, "text overwritten", id_=U.NOTE_EV, val=7), ent(1, "text overwritten", id_=U.NOTE_EV, val=8)], "seq": 2})
    assert len(out) == 1 and out[0].endswith("text overwritten") and " 1 " in out[0]      # note 8 was not written by host_note: its ring line stays
    assert any("host note 7: mark 1" in x for x in lines(tmp_path))


def test_parse_output_finds_the_json_line_behind_dev_py_prefix():
    s = snap(0, 2)
    out = "2026-11-21T10:00:00+10:00 bus 11: debug link ON\n2026-11-21T10:00:01+10:00 SYNCJSON " + json.dumps(s) + "\nbus 11: debug link OFF"
    assert U.parse_output(out)["seq"] == 2
    assert U.parse_output("nothing") is None


def test_no_poll_while_a_flash_runs(tmp_path):
    called = []
    out = U.poll_once("3", store_for=lambda ser: U.Store(ser, tmp_path), read=lambda u: called.append(u) or snap(0, 3), busy=lambda u: True)
    assert out == [] and called == []
    out = U.poll_once("3", store_for=lambda ser: U.Store(ser, tmp_path), read=lambda u: snap(0, 3), busy=lambda u: False)
    assert len(out) == 3
