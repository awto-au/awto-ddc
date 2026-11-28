"""GUI ingestion and job completion using synthetic JSON; no monitor / bus / socket."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/osd_editor'))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
import log_view as LV


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qt_app):
    app = qt_app
    calls = []
    page = SimpleNamespace(cur='3', states={'3': SimpleNamespace(writable=True, flash=False, pending=0)},
                           log_hold={}, say=lambda s: None)
    def job(label, args, _, unit, after):
        calls.append((args, after))
        return len(calls)
    page.synclog_job = job
    v = LV.LogView(page)
    v.timer.stop()
    yield v, calls
    v.close()
    v.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def snap(lo=0, hi=5, gen=3, **kw):
    return {'gen': gen, 'boot': 2, 'slots': 32768, 'next': hi, 'end': hi, 'complete': True,
            'status': 'ok' if hi > lo else 'empty',
            'entries': [{'abs': a, 'boot': 2, 'id': 1, 'arg': 0, 'ms': a, 'val': a,
                         'text': f'{a/1000:.3f}s:line {a}', 'poll_wall': None} for a in range(lo, hi)], **kw}


def test_error_json_preserves_records_cursor_and_visible_error(view):
    v, calls = view
    v.ingest('3', snap())
    before = v.text()
    assert v._read('3', ['--since', '5'], 'follow', lambda s: pytest.fail('failure callback'))
    args, done = calls[-1]
    assert args[-2:] == ['--since-gen', '3']
    done(2, 'SYNCJSON '+json.dumps({'complete': False, 'status': 'error',
                                  'error': {'message': 'header interrupted'}}), 0)
    assert v.logs['3'].next == 5 and v.text() == before
    assert 'header interrupted' in v.info.text() and 'previous lines kept' in v.info.text()


def test_empty_generation_replaces_old_cache_and_records_can_follow(view):
    v, _ = view
    v.ingest('3', snap())
    v.ingest('3', snap(0, 0, gen=4))
    assert v.logs['3'].ents == {} and v.logs['3'].next == 0
    v.ingest('3', snap(0, 2, gen=4))
    assert sorted(v.logs['3'].ents) == [0, 1]


def test_follow_page_cursor_does_not_skip_unread_pages(view):
    v, _ = view
    v.ingest('3', snap(0, 7, next=30, end=7))
    assert v.logs['3'].next == 7 and v.logs['3'].boundary == 30
    v.ingest('3', snap(7, 14, next=30, end=14))
    assert v.logs['3'].next == 14 and sorted(v.logs['3'].ents) == list(range(14))
    v.ingest('3', snap(0, 7, next=30, end=7))
    assert v.logs['3'].next == 14    # old history / overlap cannot move the follow cursor backward


def test_overwritten_range_is_visible_and_exported(view):
    v, _ = view
    v.ingest('3', snap(7, 10, gaps=[{'start': 0, 'end': 7, 'reason': 'ring_overwritten'}]))
    assert 'gap: indexes 0..6 ring_overwritten' in v.text()


def test_error_cannot_be_ingested_directly(view):
    v, _ = view
    v.ingest('3', snap())
    with pytest.raises(OSError):
        v.ingest('3', {'complete': False, 'error': {'message': 'entry failed'}})
    assert v.logs['3'].next == 5
