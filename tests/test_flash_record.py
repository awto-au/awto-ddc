"""Shared flash record (scripts/flash_registry.py, docs/flash-record.md). No hardware."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import flash_registry as R
import fw_probe
import unit_lock

SER = "AWT26110001"


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "base", lambda: tmp_path / "main" / "tmp" / "flashed")
    monkeypatch.setattr(R, "debris_dir", lambda: tmp_path / "main" / "build-debris" / "images")
    return tmp_path


def _img(d: Path, tag: str, body: bytes = b"fw", serial: str = SER) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{serial}-{tag}-be"
    (d / f"{stem}.bin").write_bytes(body)
    (d / f"{stem}.map").write_text(f"map of {tag}")
    (d / f"{stem}.sync.tsv").write_text("s")
    (d / f"{stem}.settings_table.py").write_text("t")
    (d / f"{stem}.build.json").write_text("{}")
    return d / f"{stem}.bin"


def test_record_current_round_trip(reg):
    img = _img(reg / "wt1/tmp/fw", "aaa", b"one")
    rec = R.record(SER, img)
    cur = R.current(SER)
    assert cur["tag"] == f"{SER}-aaa-be" and cur["sha256"] == rec["sha256"]
    assert cur["map"].read_text() == "map of aaa" and cur["bin"].read_bytes() == b"one"
    assert cur["settings_table_py"].is_file() and cur["sync_tsv"].is_file() and cur["build_json"].is_file()
    assert {"built", "commit", "worktree", "flashed"} <= set(cur)
    assert R.map_for(SER) == cur["map"]


def test_copy_survives_deleting_the_source(reg):
    img = _img(reg / "wt1/tmp/fw", "aaa", b"one")
    R.record(SER, img)
    for f in img.parent.iterdir():
        f.unlink()
    cur = R.current(SER)
    assert cur["map"].read_text() == "map of aaa" and cur["bin"].read_bytes() == b"one"
    assert not any(p.is_symlink() for p in R.base().rglob("*"))


def test_same_tag_different_bytes_do_not_overwrite(reg):
    a = R.record(SER, _img(reg / "w1", "def", b"v1"))
    b = R.record(SER, _img(reg / "w2", "def", b"v2"))
    assert a["images_dir"] != b["images_dir"]
    assert (R.images_dir() / a["images_dir"] / f"{SER}-def-be.bin").read_bytes() == b"v1"


def test_two_worktrees_share_one_registry(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git = lambda *a, cwd=main: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    wt = tmp_path / "wt"
    git("worktree", "add", "-q", "-b", "b", str(wt))
    assert unit_lock.lock_root(wt) == unit_lock.lock_root(main) == main.resolve()


def test_stale_detection_with_a_fake_reader(reg):
    R.record(SER, _img(reg / "w1", "old"))
    R.store(_img(reg / "w2", "new", b"x2"))                      # a known image that is not the record
    R.store(_img(reg / "w3", "other", b"x3"))
    runs = lambda m: Path(m).read_text() in ("map of new",)      # the unit really runs `new`
    r = R.check(SER, runs)
    assert not r["ok"] and r["tag"] == f"{SER}-old-be" and r["matches"] == [f"{SER}-new-be"]
    msg = R.stale_message(SER, r)
    assert "registry stale" in msg and f"{SER}-new-be" in msg
    assert R.check(SER, lambda m: "old" in Path(m).read_text())["ok"]
    r = R.check(SER, lambda m: False)
    assert r["matches"] == [] and "no known map answers" in R.stale_message(SER, r)


def test_map_for_unknown_fails_clearly(reg):
    with pytest.raises(SystemExit, match="no flash record"):
        R.map_for(SER)
    R.store(_img(reg / "w1", "known"))
    with pytest.raises(SystemExit, match=f"Known images: {SER}-known-be"):
        R.map_for(SER)
    with pytest.raises(SystemExit, match="not found"):
        R.map_for(SER, reg / "nosuch.map")
    assert R.map_for(SER, reg / "w1" / f"{SER}-known-be.map").is_file()


def test_invalidated_record_has_no_map_but_keeps_the_image(reg):
    img = _img(reg / "w1", "aaa")
    R.record(SER, img)
    snap = R.snapshot(SER)
    R.invalidate(SER, img, f"{SER}-bbb-be")
    cur = R.current(SER)
    assert cur["tag"] == "" and cur["image"] == str(img)
    with pytest.raises(SystemExit, match="was not completed"):
        R.map_for(SER)
    R.restore(SER, snap)
    assert R.current(SER)["tag"] == f"{SER}-aaa-be"


def test_find_tag_falls_back_to_build_debris(reg):
    deb = R.debris_dir()
    _img(deb, "dd")
    assert R.find_tag(f"{SER}-dd-be")["map"].parent == deb
    assert R.find_tag("nosuch") is None
    assert [c["tag"] for c in R.candidates(SER)] == [f"{SER}-dd-be"]


class _IO:
    """debug slave stand-in: XDATA bytes by address"""
    def __init__(self, mem: dict[int, int]):
        self.mem, self.sel = mem, 0

    def write(self, dev8, sub, data):
        if sub == 0x01:
            self.hi = data[0]
        elif sub == 0x3A:
            self.sel = self.hi << 8 | data[0]
        return True

    def read(self, dev8, sub, n):
        return bytes([self.mem.get(self.sel, 0)])


def test_layout_probe_reads_the_magics_at_the_map_addresses():
    m = "00000100  _isr_g_stAwtoDiag\n00000200  _vcp_box\n"
    assert fw_probe.layout_ok(_IO({0x100: 0x41, 0x101: 0x44, 0x200: 0x56}), m)
    assert not fw_probe.layout_ok(_IO({0x100: 0x41, 0x101: 0x44}), m)
    assert not fw_probe.layout_ok(_IO({0x100: 0x41, 0x101: 0x44, 0x200: 0x56}), "00000300  _isr_g_stAwtoDiag\n00000200  _vcp_box\n")
    assert not fw_probe.layout_ok(_IO({}), "no symbols")


def test_no_other_code_reads_the_old_per_worktree_record():
    pat = re.compile(r"-flashed\.json|flashed\.json")
    skip = {"tests/test_flash_record.py"}
    hits = []
    for pth in [REPO / "dev.py", *(REPO / "scripts").glob("*.py"), *(REPO / "tools").rglob("*.py")]:
        if str(pth.relative_to(REPO)) in skip:
            continue
        for n, ln in enumerate(pth.read_text(errors="replace").splitlines(), 1):
            if pat.search(ln):
                hits.append(f"{pth.relative_to(REPO)}:{n}: {ln.strip()}")
    assert not hits, "per-worktree flashed.json is gone; use flash_registry:\n" + "\n".join(hits)


def test_readers_resolve_through_the_registry():
    users = ["dev.py", "scripts/msg_table.py", "scripts/cold_boot.py", "scripts/selector_switch_unit.py", "scripts/disk_guard.py"]
    for u in users:
        assert "flash_registry" in (REPO / u).read_text(), u
