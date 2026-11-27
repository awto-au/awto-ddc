"""Control-port client and flash job parsing, no Qt (the offscreen port tests: tools/osd_editor/test_control_port.py; #276)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flash_job
import gui_client as GC
import i2c_raw


def test_translate_ddc_and_settings():
    assert GC.translate("ddc", ["get", "0x62", "0x8D"], "1") == [("vcp", {"unit": "1", "link": "hdmi", "op": "get", "codes": ["0x62", "0x8D"]})]
    assert GC.translate("ddc", ["set", "0x62", "30", "--dp"], "2")[0][1]["link"] == "dp"
    assert GC.translate("ddc", ["sleep"], "1")[0][0] == "passthrough"
    assert GC.translate("settings", ["set", "gamma", "2", "--no-confirm"], "3")[0] == (
        "set", {"unit": "3", "link": "hdmi", "name": "gamma", "value": "2", "confirm": True})
    assert GC.translate("settings", ["list"], "1")[0][0] == "get"
    assert GC.translate("settings", ["save"], "1")[0][0] == "save"
    assert GC.translate("settings", ["defaults"], "1")[0][0] == "passthrough"


def test_translate_refuses_what_the_port_cannot_carry():
    with pytest.raises(GC.PortCannotCarry):
        GC.translate("kvm", ["hdmi1"], "1")                       # no --units: the port acts on named test units only
    with pytest.raises(GC.PortCannotCarry):
        GC.translate("ddc", ["get", "0x62", "--force"], "1")
    assert [m for m, _ in GC.translate("kvm", ["D2", "--units", "1,3", "--verify"], "1")] == ["kvm", "kvm"]


def test_is_write():
    assert GC.is_write("ddc", ["set", "0x62", "3"]) and not GC.is_write("ddc", ["get", "0x62"])
    assert GC.is_write("settings", ["save"]) and not GC.is_write("settings", ["get", "gamma"])
    assert GC.is_write("flash", []) and GC.is_write("kvm", ["D1"]) and not GC.is_write("synclog", [])
    assert GC.is_write("i2c", ["0x34", "0x22"]) and not GC.is_write("i2c", ["0x34", "--read", "2"])


def test_gui_forms():
    reqs, _ = GC.parse_gui(["--serial", "S", "--kvm", "hdmi-1", "--save"])
    assert reqs == [("kvm", {"serial": "S", "target": "hdmi-1"}), ("save", {"serial": "S", "verify": ["input"]})]
    reqs, _ = GC.parse_gui(["get", "volume", "--unit", "1"])
    assert reqs == [("get", {"unit": "1", "names": ["volume"]})]
    reqs, _ = GC.parse_gui(["list"], default_unit="1")
    assert reqs == [("list", {})]                                  # no unit invented for a list
    reqs, _ = GC.parse_gui(["set", "mute", "on"], default_unit="2")
    assert reqs[0][1]["unit"] == "2"
    with pytest.raises(GC.PortCannotCarry):
        GC.parse_gui(["--bogus"])


def test_i2c_args_are_bounded():
    for bad in (["--addr", "0x80", "--write", "1"], ["--addr", "0x34"], ["--addr", "0x34", "--write", "256"]):
        with pytest.raises(SystemExit):
            i2c_raw.parse_args(["--bus", "1", "--serial", "S", *bad])


def test_flash_progress_parse():
    p = flash_job.Progress(time.time() - 10)
    for ln in ("per-sector mode: 4 sectors, boot/common last", "written+verified 2/4 sectors (3s)",
               "0x001000: 'x'; try 1/3", "ERROR: boom", "redo sector alone", "recover (x): ok",
               "burst failures redone in byte mode: 2; ISP recoveries 3; aux"):
        p.feed(ln)
    s = p.snapshot()
    assert (s["total"], s["written"], s["percent"], s["phase"]) == (4, 2, 50.0, "write")
    assert s["errors"] == 1 and (s["redo"], s["recoveries"]) == (2, 3) and s["eta_s"] > 0
    p.rc = 7
    assert p.snapshot()["phase"] == "failed" and p.snapshot()["eta_s"] is None


def test_flash_progress_erase_all_mode():
    p = flash_job.Progress(time.time())
    p.feed("erased 8/8 sectors (1s)")
    p.feed("written+verified 4/8 sectors (2s)")
    assert p.percent() == 75.0


def test_job_without_pid_is_lost_not_running():
    """a job file whose wrapper never started (no pid, no rc) used to count as running forever: os.kill(0, 0) succeeds (2026-11-20)"""
    job = {"id": "x", "serial": "S", "unit": "1"}
    assert not flash_job.running(job) and flash_job.lost(job)


def test_failed_spawn_leaves_a_finished_job(tmp_path, monkeypatch):
    """Popen failing (interpreter of a deleted venv) = rc 255 recorded and a clear refusal, no stuck 'running' job"""
    monkeypatch.setattr(flash_job, "JOBS", tmp_path)
    monkeypatch.setattr(flash_job.unit_lock, "read", lambda serial: None)
    with pytest.raises(SystemExit, match="could not start"):
        flash_job.start("S1", "1", ["true"], python=str(tmp_path / "no-such-python"))
    job = flash_job.load("S1")
    assert job["rc"] == 255 and not flash_job.running(job)


def test_event_stream_survives_repeated_read_timeouts(tmp_path):
    """flash client: the 5 s event read timed out twice and the second read raised OSError (dead makefile reader), crashing the client mid-flash"""
    import json
    import socket
    sock = tmp_path / "s.sock"
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(str(sock))
    srv.listen(1)
    sock.chmod(0o600)
    c = GC.Client(sock, timeout=0.05)
    conn, _ = srv.accept()
    ev = c.events()
    assert next(ev) is None and next(ev) is None          # two timeouts in a row
    conn.sendall(json.dumps({"event": "flash"}).encode() + b"\n" + b'{"event": "fl')
    assert next(ev) == {"event": "flash"}
    conn.sendall(b'ash_done"}\n')
    assert next(ev) == {"event": "flash_done"}            # a line split across reads is joined
    c.close()
    conn.close()
    srv.close()


def _repo(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tools/osd_editor").mkdir(parents=True)
    (tmp_path / "dev.py").write_text("a")
    (tmp_path / "scripts/x.py").write_text("a")
    return tmp_path


def test_code_stamp_changes_with_the_code(tmp_path):
    r = _repo(tmp_path)
    a = GC.code_stamp(r)
    assert a == GC.code_stamp(r)
    (r / "scripts/x.py").write_text("bb")
    assert GC.code_stamp(r) != a


def test_stale_app_reasons(tmp_path):
    r = _repo(tmp_path)
    ok = {"root": str(r), "code": GC.code_stamp(r)}
    assert GC.stale_reason(ok, r) is None
    assert "no version" in GC.stale_reason({"pid": 1}, r)                           # an app older than the handshake
    assert "gone" in GC.stale_reason({"root": str(tmp_path / "deleted-worktree"), "code": "x"}, r)
    assert "changed" in GC.stale_reason({**ok, "code": "other"}, r)
    other = tmp_path / "other"
    other.mkdir()
    assert "another tree" in GC.stale_reason({"root": str(other), "code": "x"}, r)   # another live worktree's app: restarted / refused (#358)


def test_synclog_limit_is_sized_from_the_request():
    base = GC.LIMIT_MULT * GC.SYNC_BASE_S
    lim, why = GC.synclog_limit(["--dram", "--last", "200"])
    assert lim == round(base + GC.LIMIT_MULT * 200 / GC.DRAM_RATE, 1) and "200 entries" in why and "1.25 x" in why
    assert GC.synclog_limit(["--dram"])[0] == GC.synclog_limit(["--dram", "--last", "64"])[0]
    assert GC.synclog_limit(["--dram", "--all"])[0] == round(base + GC.LIMIT_MULT * GC.hdr_int("AWTO_DLOG_SLOTS", 0) / GC.DRAM_RATE, 1)
    assert GC.synclog_limit(["--whole"])[0] < GC.synclog_limit([])[0]           # ring view 88 < one episode up to 175 from the DDR
    assert GC.request_limit_s("ping", {}) == GC.SERVER_LIMIT_S
    assert GC.request_limit_s("synclog", {"whole": False}) == GC.synclog_limit([])[0] + GC.SERVER_LIMIT_S


def test_stale_job_record_is_closed_not_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(flash_job, "JOBS", tmp_path)
    flash_job.save({"id": "x", "serial": "S9", "unit": "9", "started_mono_wall": time.time() - 100})   # wrapper never started
    job = flash_job.load("S9")
    assert job["rc"] == 255 and "stale" in job["error"] and not flash_job.running(job)
    flash_job.save({"id": "y", "serial": "S8", "unit": "8", "started_mono_wall": time.time()})          # just written: spawn in progress
    assert "rc" not in flash_job.load("S8")


def test_clean_removes_finished_and_stale_records(tmp_path, monkeypatch):
    monkeypatch.setattr(flash_job, "JOBS", tmp_path)
    flash_job.save({"id": "x", "serial": "S9", "unit": "9", "started_mono_wall": 1.0})
    flash_job.save({"id": "z", "serial": "S7", "unit": "7", "rc": 0, "reported": True})
    assert sorted(flash_job.clean()) == ["S7", "S9"]
    assert flash_job.load("S9") is None and flash_job.load("S7") is None
