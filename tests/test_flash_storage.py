"""#82 storage faults injected into the real flash session; no hardware."""
import contextlib
import errno
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flash_io
import flash_state as S
import rtd_flash_image as I
import rtd_proto as P
from test_flash_incremental import SECTOR, FakeIsp, image, opts


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(I.F, "LOG", io.StringIO())
    monkeypatch.setattr(I.F, "DETAIL", io.StringIO())
    monkeypatch.setattr(I.F, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(P, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(I.i2cbus, "ROOT", tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("unmocked hardware access")
    monkeypatch.setattr(I.i2cbus, "Bus", forbidden)
    yield
    P.TAPS.clear()


def prior_state(tmp_path, isp):
    state = S.FlashState.empty(tmp_path / "AWT0-flash-state.json", "AWT0")
    state.sectors = S.sector_hashes(bytes(isp.flash))
    state.save(source="old")
    return state


@pytest.mark.parametrize("sink", ["main", "detail", "raw", "unit", "stdout", "stderr"])
@pytest.mark.parametrize("operation", ["write", "flush"])
def test_enospc_logging_finishes_program_verify_and_reset(monkeypatch, tmp_path, sink, operation):
    armed, writes = [], []
    class Faulty:
        def __init__(self, wrapped, name):
            self.wrapped, self.name = wrapped, name
        def write(self, text):
            if armed and sink == self.name and operation == "write":
                raise OSError(errno.ENOSPC, "injected disk full")
            return self.wrapped.write(text)
        def flush(self):
            if armed and sink == self.name and operation == "flush":
                raise OSError(errno.ENOSPC, "injected flush disk full")
            return self.wrapped.flush()
        def __getattr__(self, name): return getattr(self.wrapped, name)
        def __enter__(self): return self
        def __exit__(self, *args):
            self.flush()
            self.wrapped.close()

    real_open = Path.open
    def open_path(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        name = {"rtd_flash_image.log": "main", "rtd_flash_image.detail.log": "detail",
                "rtd_flash_image.raw.log": "raw", "unit-AWT0.log": "unit"}.get(path.name)
        return Faulty(stream, name) if name else stream
    monkeypatch.setattr(Path, "open", open_path)
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", Faulty(stdout, "stdout"))
    monkeypatch.setattr(sys, "stderr", Faulty(stderr, "stderr"))
    monkeypatch.setattr(I.unit_lock, "held", lambda *args: contextlib.nullcontext())
    monkeypatch.setattr(I.dbg_link, "flash_guard", lambda *args: contextlib.nullcontext())
    monkeypatch.setattr(I.i2cbus, "require_unit", lambda *args: "AWT0")
    monkeypatch.setattr(I.i2cbus, "gmbus_nudge", lambda *args: None)
    monkeypatch.setattr(I.i2cbus, "rate_khz", lambda: 100)
    monkeypatch.setattr(I.disk_guard, "require_free", lambda what: None)
    monkeypatch.setenv("AWTO_RAW_TRACE", "1")
    img = image(n=8)
    path = tmp_path / "AWT0-test.bin"
    path.write_bytes(img)
    isp = FakeIsp()
    isp.read = lambda reg: 0x80
    isp.common = lambda *args, **kwargs: int.from_bytes(I.JEDEC_OK, "big")
    def write(reg, value):
        writes.append((reg, value))
        P.trace(0x4A, "w", reg, bytes([value]))
    isp.write = write
    original_page = isp.program_page
    def page(addr, data):
        armed.append(True)
        original_page(addr, data)
        # Exercise protocol logging as an I2C transaction returns, during a page.
        P.trace(0x4A, "w", 0x70, data)
        I.F.dlog("page completed")
        print("page diagnostic", file=sys.stderr, flush=True)
    isp.program_page = page
    monkeypatch.setattr(I, "Rtd", lambda bus: isp)
    monkeypatch.setattr(sys, "argv", ["rtd_flash_image.py", "11", str(path), "--serial", "AWT0",
                                     "--write", "--no-backup", "--verify", "readback"])
    assert I.main() == 10
    assert bytes(isp.flash[:len(img)]) == img
    assert isp.erased[-1] == 0 and isp.reprotected == 0x9C
    assert writes[-1] == (0xEE, 0x02)
    state = S.FlashState.load(tmp_path / "tmp/fw/AWT0-flash-state.json", "AWT0")
    assert state.source == "write" and state.sectors[:8] == S.sector_hashes(img)
    assert "diagnostics incomplete" in stdout.getvalue() + stderr.getvalue()


def test_failed_invalidation_never_erases_next_sector_and_resume_keeps_verified_sector(monkeypatch, tmp_path):
    isp, img = FakeIsp(), image()
    previous = prior_state(tmp_path, isp)
    save = S.FlashState.save
    def fail_next(state, **kwargs):
        if isp.erased and state.sectors[6] is None:
            raise OSError(errno.ENOSPC, "cannot invalidate next sector")
        return save(state, **kwargs)
    monkeypatch.setattr(S.FlashState, "save", fail_next)
    with pytest.raises(OSError, match="cannot invalidate"):
        I.flash(isp, img, opts(tmp_path))
    assert isp.erased == [5 * SECTOR]
    persisted = S.FlashState.load(previous.path, "AWT0")
    assert persisted.sectors[5] is None and persisted.sectors[6] == previous.sectors[6]
    monkeypatch.setattr(S.FlashState, "save", save)
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert isp.erased.count(5 * SECTOR) == 1
    assert bytes(isp.flash[:len(img)]) == img


def test_enospc_after_verified_sector_stops_before_next_erase(monkeypatch, tmp_path):
    isp, img = FakeIsp(), image()
    prior_state(tmp_path, isp)
    save = S.FlashState.save
    def fail_checkpoint(state, **kwargs):
        if isp.erased and not kwargs:
            raise OSError(errno.ENOSPC, "checkpoint disk full")
        return save(state, **kwargs)
    monkeypatch.setattr(S, "SAVE_EVERY", 1)
    monkeypatch.setattr(S.FlashState, "save", fail_checkpoint)
    assert I.flash(isp, img, opts(tmp_path)) == 11
    assert isp.erased == [5 * SECTOR]
    assert I.DONE.startswith("1/24 sectors verified; 0 erase-intent")
    assert bytes(isp.flash[5 * SECTOR:6 * SECTOR]) == img[5 * SECTOR:6 * SECTOR]
    assert isp.reprotected == 0x9C


def test_enospc_after_explicit_bulk_erase_finishes_all_erased_sectors(monkeypatch, tmp_path):
    isp, img = FakeIsp(), image()
    previous = prior_state(tmp_path, isp)
    save = S.FlashState.save
    def fail_after_bulk(state, **kwargs):
        if len(isp.erased) > 1:
            raise OSError(errno.ENOSPC, "disk filled after bulk erase")
        return save(state, **kwargs)
    monkeypatch.setattr(S, "SAVE_EVERY", 1)
    monkeypatch.setattr(S.FlashState, "save", fail_after_bulk)
    assert I.flash(isp, img, opts(tmp_path, per_sector=False)) == 10
    assert bytes(isp.flash[:len(img)]) == img and isp.reprotected == 0x9C
    persisted = S.FlashState.load(previous.path, "AWT0")
    assert persisted.sectors[5] == S.sector_hashes(img)[5]
    assert all(persisted.sectors[i] is None for i in range(len(img) // SECTOR) if i != 5)
    monkeypatch.setattr(S.FlashState, "save", save)
    erased = list(isp.erased)
    assert I.flash(isp, img, opts(tmp_path)) == 0 and isp.erased == erased


def test_storage_error_does_not_mask_interrupted_page_program(monkeypatch, tmp_path):
    isp, img = FakeIsp(), image()
    prior_state(tmp_path, isp)
    save = S.FlashState.save
    def fail_failure_save(state, **kwargs):
        if kwargs.get("source") == "write-failed":
            raise OSError(errno.ENOSPC, "cannot save failure")
        return save(state, **kwargs)
    def interrupted(addr, data): raise KeyboardInterrupt("injected interrupted write")
    monkeypatch.setattr(S.FlashState, "save", fail_failure_save)
    isp.program_page = interrupted
    with pytest.raises(KeyboardInterrupt, match="injected interrupted write"):
        I.flash(isp, img, opts(tmp_path))
    assert isp.erased == [5 * SECTOR]
    assert I.DONE.startswith("0/24 sectors verified; 1 erase-intent")
    assert S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0").sectors[5] is None


@pytest.mark.parametrize("stage", ["write", "file-sync", "rename", "directory-sync"])
def test_atomic_manifest_failures_leave_old_or_conservative_state(monkeypatch, tmp_path, stage):
    isp = FakeIsp()
    state = prior_state(tmp_path, isp)
    old = state.path.read_bytes()
    state.sectors[5] = None
    def fail(*args): raise OSError(errno.ENOSPC, stage)
    if stage == "write":
        fdopen = S.os.fdopen
        @contextlib.contextmanager
        def unwritable(fd, *args):
            with fdopen(fd, *args):
                class Full:
                    write = staticmethod(fail)
                yield Full()
        monkeypatch.setattr(S.os, "fdopen", unwritable)
    elif stage == "rename":
        monkeypatch.setattr(S.os, "replace", fail)
    else:
        fsync, calls = S.os.fsync, []
        def sync(fd):
            calls.append(fd)
            if len(calls) == (1 if stage == "file-sync" else 2): fail()
            fsync(fd)
        monkeypatch.setattr(S.os, "fsync", sync)
    with pytest.raises(OSError): state.save(source="write-in-progress")
    if stage == "directory-sync":
        assert S.FlashState.load(state.path, "AWT0").sectors[5] is None
    else:
        assert state.path.read_bytes() == old
    assert not list(tmp_path.glob("*.tmp"))


def test_backup_enospc_prevents_erasure(monkeypatch, tmp_path):
    isp = FakeIsp()
    def fail(*args): raise OSError(errno.ENOSPC, "backup disk full")
    monkeypatch.setattr(Path, "write_bytes", fail)
    options = I.Opts(serial="AWT0", write=True, manifest=tmp_path / "state.json", backup_dir=tmp_path / "backup")
    with pytest.raises(OSError, match="backup disk full"):
        I.flash(isp, image(), options)
    assert isp.erased == []


def test_full_flash_retains_known_hashes_beyond_image(tmp_path):
    isp = FakeIsp()
    previous = prior_state(tmp_path, isp)
    assert I.flash(isp, image(), opts(tmp_path, full=True)) == 0
    assert S.FlashState.load(previous.path, "AWT0").sectors[24:] == previous.sectors[24:]


def test_unit_lock_logging_failure_cannot_mask_result(monkeypatch, tmp_path):
    monkeypatch.setattr(I.unit_lock, "ROOT", tmp_path)
    monkeypatch.setattr(I.unit_lock, "LOCKS", tmp_path / "locks")
    original = Path.open
    def failed_log(path, *args, **kwargs):
        if path.name == "unit_lock.log": raise OSError(errno.ENOSPC, "log full")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", failed_log)
    with I.unit_lock.held("AWT0", "test"):
        assert I.unit_lock.read("AWT0") is not None
    assert I.unit_lock.read("AWT0") is None


def test_broken_output_report_is_best_effort():
    class Broken(io.StringIO):
        def write(self, text): raise BrokenPipeError("lost parent")
        def flush(self): raise OSError(errno.ENOSPC, "full redirect")
    diagnostics = flash_io.Diagnostics()
    out = diagnostics.stream(Broken(), "stdout")
    out.write("page complete")
    out.flush()
    assert "stdout" in diagnostics.failures
