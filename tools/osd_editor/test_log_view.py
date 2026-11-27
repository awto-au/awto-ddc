"""Offscreen test of the log view (#358): fake DDR log of two boots (a long boot of 1400 lines), no hardware.
QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_log_view.py"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HERE))
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import log_view as LV  # noqa: E402
import monitor as MON  # noqa: E402
from test_smoke import FakeBackend  # noqa: E402

WORK = ROOT / "tmp" / "scratch" / "logview"
SHOTS = ROOT / "tmp" / "scratch" / "qt"
WAIT_S = 10.0                       # a fake read is instant; 10 s = a stuck queue


class DdrLog(FakeBackend):
    """`dev.py synclog --dram --json` over a fake DDR log: --last K / --since A [--count K], as dram_log.snapshot"""

    def __init__(self, ents):
        super().__init__()
        self.ents, self.reads = ents, []

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        if not ("synclog" in a and "--dram" in a):
            return super().run(argv, limit_s)
        self.limits.append(limit_s)
        nxt = len(self.ents)
        if "--since" in a:
            lo = int(a[a.index("--since") + 1])
            hi = min(nxt, lo + int(a[a.index("--count") + 1])) if "--count" in a else nxt
        else:
            lo, hi = max(0, nxt - int(a[a.index("--last") + 1])), nxt
        self.reads.append((lo, hi))
        snap = {"dram": True, "serial": "AWT26110003", "gen": 165, "boot": 12, "next": nxt, "slots": 32768, "entries": self.ents[lo:hi]}
        return 0, "2026-11-27T17:00:00+11:00 bus 11: debug link ON\nSYNCJSON " + json.dumps(snap) + "\n"


def fake_log(n_boot11=200, n_boot12=1400):
    """boot 11 (old, uptime only) and boot 12: boot line, a long power-on episode, a switch episode, heartbeats"""
    out, a = [], 0

    def add(boot, ms, i, arg, text, val=0, poll=None):
        nonlocal a
        out.append({"abs": a, "boot": boot, "ms": ms, "id": i, "arg": arg, "val": val, "text": f"{ms / 1000:9.3f}s:{text}", "poll_wall": poll})
        a += 1
    for boot, n, wall in ((11, n_boot11, False), (12, n_boot12, True)):
        add(boot, 5, S_BOOT, 0, "boot: power on, reset by watchdog")
        for k in range(1, n):
            ms = 5 + k * 37 + (300_000 if k >= n // 2 - 1 else 0)              # a 300 s gap before the line above the switch
            poll = f"2026-11-27T16:{(ms // 60000) % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}+11:00" if wall else None
            if k == n // 2:
                add(boot, ms, S_BEGIN, 2, "switch to D1 (KVM)", 0, poll)
            else:
                add(boot, ms, 0xEA, 3, f"monitor: main loop 300 passes/s, line {k}", 0, poll)
    return out


S_BOOT, S_BEGIN = LV.S.BOOT_EV, LV.S.BEGIN_EV


def pump(cond, what, seconds=WAIT_S):
    t0 = time.monotonic()
    while not cond():
        assert time.monotonic() - t0 < seconds, f"timeout waiting for {what}"
        QTest.qWait(5)


def make(name, ents):
    WORK.mkdir(parents=True, exist_ok=True)
    ini = WORK / f"{name}.ini"
    ini.unlink(missing_ok=True)
    fb = DdrLog(ents)
    pg = MON.MonitorPage(fb, WORK / f"{name}.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    lv = LV.LogView(pg)
    pg.log_view = lv
    lv.unit.setCurrentIndex(lv.unit.findData("3"))
    return pg, fb, lv


def idle(pg, lv):
    pump(lambda: not lv.inflight and not any(st.pending for st in pg.states.values()), "log reads done")


def history_chunks_dedupe_and_follow():
    ents = fake_log()
    pg, fb, lv = make("hist", ents)
    lv.range_read = True
    assert lv.read_history("3")
    pump(lambda: lv.logs.get("3") and lv.logs["3"].done, "history complete", 20)
    idle(pg, lv)
    assert all(hi - lo <= LV.CHUNK for lo, hi in fb.reads), fb.reads              # every job bounded
    assert fb.reads[0] == (len(ents) - LV.CHUNK, len(ents)) and fb.reads[-1][0] == 0, fb.reads[:3]
    assert len(lv.logs["3"].ents) == len(ents)
    rows = lv.model.rows
    assert [r["text"] for r in rows if r["sep"]] == ["--- boot 11 ---", "--- boot 12 ---"]
    starts = [r for r in rows if r["start"]]
    assert len(starts) == 4 and starts[0]["delta"] == "+  5 ms" and starts[1]["text"].startswith("switch to D1"), starts[:2]
    assert rows[1]["real"].startswith("u00:00:00.005") and rows[-1]["real"].endswith("~"), (rows[1], rows[-1])
    big = [r for r in rows if r["delta"].endswith(" s") and r["delta"].startswith("+") and "300" in r["delta"]]
    assert big, "a 300 s gap shows as +300 s (32-bit ms, no 16-bit wrap)"
    assert all(fb.limits[i] <= MON.gui_client.synclog_limit(["--dram", "--last", str(LV.CHUNK)])[0] for i in range(len(fb.limits)))
    # follow: new lines appended, already-seen indexes not duplicated
    lv.show()
    QApplication.processEvents()
    idle(pg, lv)                                                                  # the first-show read (nothing new)
    before = len(lv.model.rows)
    ents += [{**ents[-1], "abs": len(ents), "ms": ents[-1]["ms"] + 40, "text": "   9999.000s:monitor: follow line"}]
    lv.tick()
    idle(pg, lv)
    assert fb.reads[-1] == (len(ents) - 1, len(ents)) and len(lv.model.rows) == before + 1, fb.reads[-1]
    lv.ingest("3", {"gen": 165, "slots": 32768, "next": len(ents), "entries": ents[-5:]})                  # overlap: deduped by abs
    assert len(lv.model.rows) == before + 1
    # filter, jump list, save
    lv.filter.setText("switch to")
    assert lv.model.rowCount() == 4 and lv.jump.count() == 1 + 4, (lv.model.rowCount(), lv.jump.count())      # 2 seps + 2 matches
    lv.filter.setText("")
    assert lv.jump.count() == 1 + 2 + 4
    out = lv.save(str(WORK / "saved.log"))
    text = Path(out).read_text()
    assert text.count("\n") == lv.model.rowCount() and "--- boot 12 ---" in text and "follow line" in text
    assert any("log view:" in ln and "new of" in ln for ln in (WORK / "hist.log").read_text().splitlines())
    pg.flash_timer.stop()
    print(f"ok log view: {len(ents)} lines in {len(fb.reads) - 1} history jobs of <= {LV.CHUNK}, boots + 4 red starts, follow appends, deduped, filter / jump / save")
    return pg, lv


def fallback_without_range_read():
    ents = fake_log(10, 1500)
    pg, fb, lv = make("fallback", ents)
    lv.range_read = False
    lv.read_history("3")
    idle(pg, lv)
    assert fb.reads == [(len(ents) - LV.FALLBACK_N, len(ents))] and lv.logs["3"].done and "newest 1000 only" in lv.info.text(), (fb.reads, lv.info.text())
    pg.flash_timer.stop()
    print("ok decoder without a range read: one --last 1000 job, the view says the history is the newest 1000 only")


def yields_to_flash_and_jobs():
    pg, fb, lv = make("yield", fake_log(5, 20))
    lv.range_read = True
    pg.log_hold["3"] = True
    assert lv.can_read("3") == "flashing" and not lv.read_history("3") and not fb.reads
    pg.log_hold.clear()
    pg.states["3"].pending = 1
    assert lv.can_read("3") == "the unit has other jobs" and not lv.read_history("3")
    pg.states["3"].pending = 0
    assert lv.can_read("1") == "" and lv.read_history("3") and lv.can_read("3") == "a log read is running"
    idle(pg, lv)
    lv.follow.setChecked(True)
    n = len(fb.reads)
    lv.hide()
    lv.tick()
    assert len(fb.reads) == n, "no reads while the view is not shown (headless app)"
    pg.flash_timer.stop()
    print("ok log view yields: no read while flashing / held for a flash / the unit has jobs / one in flight; none while hidden")


def screenshot(pg, lv):
    SHOTS.mkdir(parents=True, exist_ok=True)
    lv.resize(1400, 900)
    lv.show()
    rows = lv.model.rows
    i = next(k for k, r in enumerate(lv.model.shown) if rows[r]["sep"] and rows[r]["boot"] == 12)
    lv.table.scrollTo(lv.model.index(i, 0), LV.QTableView.ScrollHint.PositionAtTop)
    QApplication.processEvents()
    p = SHOTS / "log-view.png"
    lv.grab().save(str(p))
    print(f"screenshot {p}")


def real_snapshot(path: Path):
    """--snapshot FILE: render a captured `dev.py synclog --dram --json` output (real unit data) to log-view-real.png"""
    snap = LV.unit_log.parse_output(path.read_text())
    pg, fb, lv = make("real", snap["entries"])
    lv.ingest("3", snap)
    lv.resize(1400, 900)
    lv.show()
    QApplication.processEvents()
    starts = [r for r in lv.model.rows if r["start"]]
    i = lv.model.shown.index(lv.model.rows.index(starts[-1])) if starts else 0
    lv.table.scrollTo(lv.model.index(max(0, i - 3), 0), LV.QTableView.ScrollHint.PositionAtTop)
    QApplication.processEvents()
    out = SHOTS / "log-view-real.png"
    lv.grab().save(str(out))
    print(f"real snapshot: {len(snap['entries'])} entries, {sum(r['sep'] for r in lv.model.rows)} boots, {len(starts)} starts; screenshot {out}")
    pg.flash_timer.stop()


def main():
    app = QApplication([])
    if "--snapshot" in sys.argv:
        SHOTS.mkdir(parents=True, exist_ok=True)
        return real_snapshot(Path(sys.argv[sys.argv.index("--snapshot") + 1]))
    pg, lv = history_chunks_dedupe_and_follow()
    fallback_without_range_read()
    yields_to_flash_and_jobs()
    screenshot(pg, lv)
    app.processEvents()
    print("PASS")


if __name__ == "__main__":
    main()
