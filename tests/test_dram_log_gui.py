"""Offscreen GUI integration with fake jobs and generation-aware DRAM snapshots."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/osd_editor"))
import test_log_view as T
from PySide6.QtWidgets import QApplication


@pytest.fixture
def view():
    app = QApplication.instance() or QApplication([])
    pg, fb, lv = T.make("consistency391", T.fake_log(5, 20))
    pg.flash_timer.stop()
    yield app, pg, fb, lv
    lv.close()
    pg.close()


def test_generation_change_retains_old_rows_in_view_and_export(view, tmp_path):
    _app, _pg, _fb, lv = view
    old = {"gen": 3, "slots": 32768, "boot": 12, "next": 25, "entries": T.fake_log(5, 20)}
    lv.ingest("3", old)
    before = len(lv.logs["3"].ents)
    new = {"gen": 4, "slots": 32768, "boot": 1, "next": 3, "entries": T.fake_log(1, 2)}
    lv.ingest("3", new)
    assert len(lv.logs["3"].archive[3]) == before
    assert lv.logs["3"].next == 3
    assert "archived DRAM generation 3" in lv.text()
    dest = tmp_path / "history.log"
    lv.save(str(dest))
    assert "archived DRAM generation 3" in dest.read_text()


def test_partial_read_retains_known_rows_and_queues_hole_retry(view):
    _app, _pg, _fb, lv = view
    ents = T.fake_log(5, 20)
    lv.ingest("3", {"gen": 3, "slots": 32768, "next": 25, "entries": ents})
    lv.ingest("3", {"gen": 3, "slots": 32768, "next": 26, "entries": [], "status": "partial",
                    "diagnostics": {"missing": [{"first": 7, "end": 8, "reason": "io_failure"}]}})
    assert len(lv.logs["3"].ents) == 25
    assert lv.logs["3"].retry == ["--since", "7", "--count", "300"]
    assert lv.logs["3"].next == 26
    lv.ingest("3", {"status": "unavailable", "entries": [], "next": None, "diagnostics": {"header_status": "transient_checksum"}})
    assert len(lv.logs["3"].ents) == 25 and lv.logs["3"].gen == 3


def test_gui_jobs_pass_cursor_generation(view):
    _app, _pg, _fb, lv = view
    lv.ingest("3", {"gen": 3, "slots": 32768, "next": 25, "entries": T.fake_log(5, 20)})
    jobs = []
    pg = _pg
    pg.synclog_job = lambda label, args, unused, **kw: jobs.append(args) or 123
    assert lv._read("3", ["--since", "25"], "follow", lambda snap: None)
    assert jobs[0][-2:] == ["--generation", "3"]
    lv.inflight.clear()
