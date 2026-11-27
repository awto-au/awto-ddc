"""#358 process preflights: image commit in the flashing tree, host-time.service check, unit logs outside any worktree, host_time map + flash guard."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture()
def dev(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("dev_preflight", REPO / "dev.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["dev_preflight"] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "LOG", tmp_path / "dev.log")
    return m


def _git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout.strip()


def _tree(tmp_path: Path) -> tuple[Path, str, str]:
    """a repo with commits A <- B and a side commit C (not in B's history)"""
    t = tmp_path / "tree"
    t.mkdir()
    _git(t, "init", "-q")
    _git(t, "config", "user.email", "t@t")
    _git(t, "config", "user.name", "t")
    (t / "f").write_text("a")
    _git(t, "add", "f")
    _git(t, "commit", "-qm", "A")
    a = _git(t, "rev-parse", "--short=8", "HEAD")
    _git(t, "checkout", "-qb", "side")
    (t / "f").write_text("c")
    _git(t, "commit", "-qam", "C")
    c = _git(t, "rev-parse", "--short=8", "HEAD")
    _git(t, "checkout", "-q", "-")
    (t / "f").write_text("b")
    _git(t, "commit", "-qam", "B")
    return t, a, c


def _image(tmp_path: Path, commit: str | None, dirty: bool = False) -> Path:
    img = tmp_path / "AWT26110003-x-be.bin"
    img.write_bytes(b"\xff" * 16)
    if commit is not None:
        (tmp_path / "AWT26110003-x-be.build.json").write_text(json.dumps({"commit": commit, "dirty": dirty}))
    return img


def test_image_commit_in_history_passes(dev, tmp_path):
    t, a, _c = _tree(tmp_path)
    dev.check_image_tree(_image(tmp_path, a), t)
    dev.check_image_tree(_image(tmp_path, a, dirty=True), t)          # a dirty build of an ancestor: its base commit is checked


def test_image_commit_outside_history_refused_even_with_any_image(dev, tmp_path):
    t, _a, c = _tree(tmp_path)
    for old_ok in (False, True):
        with pytest.raises(SystemExit, match=f"built from {c}, which is not in the history of tree"):
            dev.check_image_tree(_image(tmp_path, c), t, old_ok)


def test_image_without_build_commit(dev, tmp_path):
    t, _a, _c = _tree(tmp_path)
    with pytest.raises(SystemExit, match="has no build commit"):
        dev.check_image_tree(_image(tmp_path, None), t)
    dev.check_image_tree(_image(tmp_path, None), t, True)              # --any-image: WARN only


def test_host_time_service_check(dev, monkeypatch, tmp_path):
    want = next(ln for ln in (REPO / "systemd/host-time.service").read_text().splitlines() if ln.startswith("ExecStart="))
    answers = {}

    def fake_run(argv, **_k):
        out = answers.get(argv[2], "")
        return subprocess.CompletedProcess(argv, 0, out, "")
    monkeypatch.setattr(dev.subprocess, "run", fake_run)
    answers.update({"cat": f"[Service]\n{want}\n", "is-active": "active"})
    assert dev._host_time_service_ok()
    answers["is-active"] = "inactive"
    assert not dev._host_time_service_ok()
    answers.update({"is-active": "active", "cat": "[Service]\nExecStart=/usr/bin/python3 x/host_time.py --loop 60\n"})   # #358: --loop 60, no --unit
    assert not dev._host_time_service_ok()
    assert "--loop 60" in (tmp_path / "dev.log").read_text()


def test_unit_logs_outside_the_worktree(monkeypatch):
    import unit_lock
    import unit_log
    monkeypatch.delenv("AWTO_DDC_REPO", raising=False)
    assert unit_log._shared_root() == unit_lock.lock_root()
    assert ".claude/worktrees" not in str(unit_log._shared_root())
    monkeypatch.setenv("AWTO_DDC_REPO", "/x/main")
    assert unit_log._shared_root() == Path("/x/main")


def test_host_time_debug_link_map_from_flash_record(monkeypatch, tmp_path):
    """send_dbg resolves g_stAwtoHt from the shared flash record's map, not tmp/fw/<serial>-<tag>.map of its own tree"""
    import flash_registry
    import host_time as HT
    seen = {}
    monkeypatch.setattr(flash_registry, "current", lambda s: {"map": tmp_path / "rec.map"})

    def fake_sym(p, name):
        seen["map"] = p
        raise OSError("stop here")
    import sync_log
    monkeypatch.setattr(sync_log, "sym", fake_sym)
    with pytest.raises(OSError, match="stop here"):
        HT.send_dbg({"serial": "AWT26110003", "_n": "3"}, 11)
    assert seen["map"] == tmp_path / "rec.map"
    monkeypatch.setattr(flash_registry, "current", lambda s: {"tag": "", "attempted": "x"})
    with pytest.raises(OSError, match="no map in the flash record"):
        HT.send_dbg({"serial": "AWT26110003", "_n": "3"}, 11)


def test_host_time_skips_a_unit_under_flash(monkeypatch):
    import host_time as HT
    import unit_lock
    monkeypatch.setattr(unit_lock, "read", lambda s: {"owner": "agent", "tool": "rtd_flash_image", "pid": "1"})
    monkeypatch.setattr(unit_lock, "alive", lambda pid: True)
    monkeypatch.setattr(HT.kvm, "find_bus", lambda u: pytest.fail("no bus scan during a flash"))
    assert HT.one("3", {"serial": "AWT26110003"}, None) == (False, None)
    assert HT.booted({"serial": "AWT26110003"}, 11) is False


def test_host_time_nak_line(monkeypatch):
    import errno

    import host_time as HT
    import unit_lock
    lines = []
    monkeypatch.setattr(unit_lock, "read", lambda s: None)
    monkeypatch.setattr(HT, "log", lines.append)
    monkeypatch.setattr(HT, "send", lambda u, b: (_ for _ in ()).throw(OSError(errno.ENXIO, "No such device or address")))
    monkeypatch.setattr(HT, "send_dbg", lambda u, b: True)
    assert HT.one("3", {"serial": "AWT26110003"}, 11) == (True, 11)
    assert any("DDC/CI 0x37 NAK" in x for x in lines)
