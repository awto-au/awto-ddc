"""#96 fault injection: no monitor, relay, I2C adapter or firmware flash required."""
import contextlib
import errno
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dbg_link as D
import flash_state as S
import rtd_flash_image as I
from test_flash_incremental import NIMG, SECTOR, FakeIsp, SigIsp, image, opts


@pytest.fixture(autouse=True)
def no_hardware(monkeypatch, tmp_path):
    monkeypatch.setattr(D.i2cbus, "ROOT", tmp_path)
    monkeypatch.setattr(D, "LOCK_DIR", tmp_path / "link-lock")
    monkeypatch.setattr(D, "log", lambda s: None)
    monkeypatch.setattr(I, "log", lambda s: None)
    # An accidental unmocked hardware access fails the test immediately.
    def forbidden(*a, **kw):
        raise AssertionError("unmocked hardware access")
    monkeypatch.setattr(D.i2cbus, "Bus", forbidden)


class DebugBus:
    """Temporary-link model: off is asynchronous, expiry would swap engines."""
    def __init__(self, linked=True, stuck=False, expiry=1.0):
        self.linked, self.stuck, self.expiry = linked, stuck, expiry
        self.now, self.expires, self.off_at = 0, 0, None
        self.off_commands = 0

    def tick(self, seconds):
        self.now += seconds
        if self.off_at is not None and self.now >= self.off_at:
            self.linked, self.expiry, self.off_at = False, None, None
        if self.linked and self.expiry is not None and self.now >= self.expiry:
            self.expires += 1
            self.linked, self.expiry = False, None

    def __call__(self, bus): return self
    def __enter__(self): return self
    def __exit__(self, *a): pass

    def raw_read(self, addr, n):
        if (addr == D.DBG and self.linked) or (addr == D.DDCCI and not self.linked):
            return bytes(n)
        raise OSError(errno.ENXIO, "address NAK")

    def write(self, addr, reg, data):
        if not self.linked:
            raise OSError(errno.ENXIO, "address NAK")
        if reg == 0x3B:
            self.off_commands += 1
            if not self.stuck:
                self.off_at = self.now + D.MCCS_WAIT_S


def install_bus(monkeypatch, bus):
    monkeypatch.setattr(D.i2cbus, "Bus", bus)
    monkeypatch.setattr(D.time, "sleep", bus.tick)


def test_preflight_cancels_expiry_and_holds_guard_through_flash(monkeypatch):
    bus = DebugBus()
    install_bus(monkeypatch, bus)
    with D.flash_guard(11):
        assert bus.off_commands == 1 and not bus.linked
        bus.tick(3600)  # a flash may take longer than the original link lifetime
        assert bus.expires == 0
        # A second cable must not enable the same scaler's link mid-ISP.
        with pytest.raises(D.FlashPreflightError, match="already active"):
            D.on(15)
    assert not bus.linked  # the previous temporary link is never restored
    with D.bus_guard(15):
        pass  # lock released after exit/reset


def test_preflight_refuses_link_that_will_not_disable(monkeypatch):
    bus = DebugBus(stuck=True, expiry=None)
    install_bus(monkeypatch, bus)
    with pytest.raises(D.FlashPreflightError), D.flash_guard(11):
        pytest.fail("must not enter ISP")


def test_preflight_allows_edid_silent_blank_flash_recovery(monkeypatch):
    bus = DebugBus(linked=False)
    install_bus(monkeypatch, bus)
    # Even 0x37 is silent: only ISP will be required to identify the flash.
    monkeypatch.setattr(D, "ddcci_ok", lambda bus: False)
    with D.flash_guard(11):
        assert bus.off_commands == 0


@pytest.mark.parametrize("err", [errno.EIO, errno.ETIMEDOUT, errno.EAGAIN, errno.EACCES])
def test_i2c_fault_is_not_mistaken_for_debug_silence(monkeypatch, err):
    class Bad(DebugBus):
        def raw_read(self, addr, n): raise OSError(err, "unstable I2C")
    install_bus(monkeypatch, Bad())
    with pytest.raises(D.FlashPreflightError, match="cannot establish"), D.flash_guard(11):
        pytest.fail("must not enter ISP")


def test_intermittent_debug_response_refuses_isp(monkeypatch):
    responses = iter([False, False, True])
    monkeypatch.setattr(D, "debug_responds", lambda bus: next(responses))
    monkeypatch.setattr(D.time, "sleep", lambda seconds: None)
    with pytest.raises(D.FlashPreflightError, match="still answers"), D.flash_guard(11):
        pytest.fail("must not enter ISP")


def test_guard_releases_after_failure_without_restoring_link(monkeypatch):
    bus = DebugBus()
    install_bus(monkeypatch, bus)
    with pytest.raises(RuntimeError, match="failed programming"), D.flash_guard(11):
        raise RuntimeError("failed programming")
    with D.bus_guard(11):
        assert not bus.linked


def test_other_process_cannot_enable_link_on_alternate_cable(tmp_path):
    code = "import dbg_link as d; import sys; from pathlib import Path; d.LOCK_DIR = Path(sys.argv[1]);\nwith d.bus_guard(15): pass"
    env = {**os.environ, "AWTO_DDC_REPO": str(tmp_path),
           "PYTHONPATH": str(Path(D.__file__).parent)}
    with D.bus_guard(11):
        child = subprocess.run([sys.executable, "-c", code, str(D.LOCK_DIR)], env=env, capture_output=True, text=True, timeout=5, check=False)
        assert child.returncode != 0 and "already active" in child.stderr
    child = subprocess.run([sys.executable, "-c", code, str(D.LOCK_DIR)], env=env, capture_output=True, text=True, timeout=5, check=False)
    assert child.returncode == 0


@pytest.mark.parametrize("per_sector", [True, False])
@pytest.mark.parametrize("failure", ["NAK", "timeout", "corruption"])
def test_failed_write_probe_never_erases_the_remaining_image(tmp_path, per_sector, failure):
    class Broken(FakeIsp):
        def program_page(self, addr, data):
            if failure == "NAK": raise OSError(errno.ENXIO, "burst NAK")
            if failure == "timeout": raise TimeoutError("SPI engine busy")
            # A write that reports success but does nothing must also be caught.
    isp = Broken()
    before = bytes(isp.flash)
    with pytest.raises((OSError, TimeoutError, RuntimeError)):
        I.flash(isp, image(), opts(tmp_path, per_sector=per_sector))
    assert set(isp.erased) == {5 * SECTOR}  # first banked sector only
    assert bytes(isp.flash[:5 * SECTOR]) == before[:5 * SECTOR]
    assert bytes(isp.flash[6 * SECTOR:]) == before[6 * SECTOR:]
    assert isp.reprotected is None


def test_write_enable_failure_prevents_every_erase(tmp_path):
    class Locked(FakeIsp):
        def write_enable(self): raise RuntimeError("WEL=0")
    isp = Locked()
    with pytest.raises(RuntimeError, match="WEL"):
        I.flash(isp, image(), opts(tmp_path))
    assert isp.erased == []


def test_short_equal_reads_refuse_before_erase(tmp_path):
    isp = FakeIsp()
    isp.read_flash = lambda addr, n: b""
    with pytest.raises(I.ReadPathUnstable, match="short read"):
        I.flash(isp, image(), opts(tmp_path))
    assert isp.erased == []


def test_unstable_write_proof_stops_before_next_erase(tmp_path):
    class Unstable(FakeIsp):
        proof_reads = 0
        def read_flash(self, addr, n):
            data = super().read_flash(addr, n)
            if addr == 5 * SECTOR and self.erased:
                self.proof_reads += 1
                if self.proof_reads == 3:  # verify, proof read 1, corrupt proof read 2
                    return bytes([data[0] ^ 1]) + data[1:]
            return data
    isp = Unstable()
    with pytest.raises(RuntimeError, match="write-path proof") as exc:
        I.flash(isp, image(), opts(tmp_path))
    assert not isinstance(exc.value, I.ReadPathUnstable)  # must not trigger the no-write rc=5 retry
    assert isp.erased == [5 * SECTOR]
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    assert st.source == "write-failed" and st.sectors[5] is None


def test_default_interrupt_preserves_boot_and_resume(tmp_path):
    isp, img = SigIsp(nth=5), image()
    before = bytes(isp.flash[:5 * SECTOR])
    assert I.flash(isp, img, opts(tmp_path)) == 9
    assert isp.erased == [5 * SECTOR]
    assert bytes(isp.flash[:5 * SECTOR]) == before
    isp.nth = 0
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert bytes(isp.flash[:len(img)]) == img
    assert isp.erased[-1] == 0  # reset-vector sector is the very last erase


def test_blank_sectors_do_not_move_boot_programming_ahead_of_banked_data(tmp_path):
    isp = FakeIsp()
    img = image(n=16)
    img = img[:5 * SECTOR] + b"\xff" * (11 * SECTOR)
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert isp.erased == [*[i * SECTOR for i in range(5, 16)], SECTOR, 2*SECTOR, 3*SECTOR, 4*SECTOR, 0]


def test_legacy_bulk_erase_requires_full_readback_proof(tmp_path):
    class Trace(FakeIsp):
        proof = 0
        def read_flash(self, addr, n):
            if addr == 5 * SECTOR and self.erased:
                self.proof += 1
            return super().read_flash(addr, n)
        def erase_sector(self, addr):
            if self.erased and addr != 5 * SECTOR:
                assert self.proof >= 3  # full verification plus two stable reads
            super().erase_sector(addr)
    isp = Trace()
    assert I.flash(isp, image(), opts(tmp_path, per_sector=False)) == 0


def test_byte_fallback_on_probe_is_used_for_remaining_bulk_run(tmp_path):
    class Fallback(FakeIsp):
        write_mode = "burst"
        _byte_sector = None
        def program_page(self, addr, data):
            if self._byte_sector is None:
                self._byte_sector = addr & ~(SECTOR - 1)
                raise OSError(errno.ENXIO, "burst failed, sector forced to byte")
            if addr // SECTOR != 5:
                assert self.write_mode == "byte"
            super().program_page(addr, data)
    isp = Fallback()
    assert I.flash(isp, image(), opts(tmp_path, per_sector=False)) == 0
    assert isp.write_mode == "byte"


@pytest.mark.parametrize("failed_sector", [5, 9, 0])
def test_abrupt_loss_marks_only_inflight_sector_unknown_and_can_resume(tmp_path, failed_sector):
    class Crash(FakeIsp):
        crash = True
        def program_page(self, addr, data):
            super().program_page(addr, data)
            if self.crash and addr // SECTOR == failed_sector:
                raise KeyboardInterrupt("host lost during page program")
    isp, img = Crash(), image()
    # Start with an accurate old manifest; untouched sectors must retain it.
    st = S.FlashState.empty(tmp_path / "AWT0-flash-state.json", "AWT0")
    old = S.sector_hashes(bytes(isp.flash))
    st.sectors = old[:]
    st.save()
    with pytest.raises(KeyboardInterrupt):
        I.flash(isp, img, opts(tmp_path))
    st = S.FlashState.load(st.path, "AWT0")
    assert st.source == "write-failed" and st.sectors[failed_sector] is None
    for i in range(NIMG):
        if i * SECTOR not in isp.erased:
            assert st.sectors[i] == old[i]
    isp.crash = False
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert bytes(isp.flash[:len(img)]) == img


@pytest.mark.parametrize("fault", ["debug", "isp", "jedec", "unstable-jedec", "program", "success"])
def test_cli_preflight_and_exit_reset(monkeypatch, tmp_path, fault):
    bus = DebugBus(stuck=fault == "debug", expiry=None)
    install_bus(monkeypatch, bus)
    img = tmp_path / "AWT0-test.bin"
    img.write_bytes(image(n=1))
    monkeypatch.setattr(I.F, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(I.i2cbus, "require_unit", lambda *a, **kw: None)  # relay-proven blank recovery
    monkeypatch.setattr(I.disk_guard, "require_free", lambda what: None)
    monkeypatch.setattr(I.unit_lock, "held", lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(sys, "argv", ["rtd_flash_image.py", "11", str(img), "--serial", "AWT0",
                                      "--identity", "unit relay", "--write", "--no-backup"])
    writes, sessions = [], []
    class Session:
        calls = 0
        def __init__(self, adapter):
            assert not bus.linked
            sessions.append(adapter)
        def write(self, reg, value):
            writes.append((reg, value))
            with pytest.raises(D.FlashPreflightError), D.bus_guard(15):
                pytest.fail("guard must cover ISP enable AND reset")
        def read(self, reg):
            if fault == "isp": raise TimeoutError("ISP unavailable")
            return 0x80
        def common(self, *a, **kw):
            self.calls += 1
            return 0 if fault == "jedec" or (fault == "unstable-jedec" and self.calls == 2) else int.from_bytes(I.JEDEC_OK, "big")
    monkeypatch.setattr(I, "Rtd", Session)
    def flash(*a, **kw):
        bus.tick(3600)
        assert bus.expires == 0
        if fault == "program": raise RuntimeError("program failed")
        return 0
    monkeypatch.setattr(I, "flash", flash)
    expected = {"debug": 6, "isp": 7, "jedec": 4, "unstable-jedec": 4, "program": 7, "success": 0}
    assert I.main() == expected[fault]
    if fault == "debug":
        assert sessions == [] and writes == []
    else:
        assert writes == [(0x6F, 0x80), (0xEE, 0x02)]
    with D.bus_guard(15):
        pass  # released even on preflight, JEDEC or programming failure


@pytest.fixture
def dev(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("safety_dev", Path(__file__).resolve().parents[1] / "dev.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "FW", tmp_path)
    (tmp_path / "AWT0-test.bin").write_bytes(b"test")
    monkeypatch.setattr(m, "_layout_watch", lambda: None)
    monkeypatch.setattr(m, "check_image_identity", lambda u, img: None)
    monkeypatch.setattr(m.disk_guard, "require_free", lambda what: None)
    monkeypatch.setattr(m.i2cbus, "adapter_name", lambda bus: "i915")
    monkeypatch.setattr(m.i2cbus, "fast_bus", lambda bus: contextlib.nullcontext(1000))
    return m


@pytest.mark.parametrize("relay", [None, "so-th-1"])
def test_dev_flash_uses_per_sector_with_or_without_relay(dev, monkeypatch, tmp_path, relay):
    unit = {"serial": "AWT0", "relay": relay}
    monkeypatch.setattr(dev, "_unit", lambda extra: ("2", unit))
    seen = []
    monkeypatch.setattr(dev, "_py", lambda script, *args, **kw: seen.append((script, args)) or 0)
    assert dev.cmd_flash(["--bus", "11", str(tmp_path / "AWT0-test.bin")]) == 0
    assert "--per-sector" in seen[0][1]


def test_debug_preflight_refusal_preserves_previous_firmware_tag(dev, monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "_unit", lambda extra: ("2", {"serial": "AWT0", "relay": "so-th-1"}))
    tag = tmp_path / "AWT0-flashed.json"
    tag.write_text('{"tag":"known-good"}')
    calls = []
    monkeypatch.setattr(dev, "_py", lambda *a, **kw: calls.append(a) or 6)
    assert dev.cmd_flash(["--bus", "11", str(tmp_path / "AWT0-test.bin")]) == 6
    assert tag.read_text() == '{"tag":"known-good"}' and len(calls) == 1


def test_recover_defaults_to_byte_mode_and_preserves_bus_override(dev, monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "_unit", lambda extra: ("2", {"serial": "AWT0", "relay": "so-th-1", "connector": "HDMI"}))
    img = tmp_path / "AWT0-test.bin"
    img.write_bytes(b"test")
    monkeypatch.setattr(dev, "_bus", lambda *a, **kw: (_ for _ in ()).throw(SystemExit("EDID silent")))
    monkeypatch.setattr(dev, "cmd_power_cycle", lambda extra: 0)
    monkeypatch.setattr(dev, "_flashed_has_safe_block", lambda unit: False)
    calls = []
    monkeypatch.setattr(dev, "cmd_flash", lambda extra: calls.append(extra) or 0)
    assert dev.cmd_recover(["--bus", "11", str(img)]) == 0
    assert calls[0][calls[0].index("--write-mode") + 1] == "byte"
    assert calls[0][calls[0].index("--verify") + 1] == "readback"
    assert calls[0][calls[0].index("--bus") + 1] == "11"


def test_recover_disk_guard_runs_before_any_bus_reset_or_relay(dev, monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "_unit", lambda extra: ("2", {"serial": "AWT0", "relay": "so-th-1"}))
    def forbidden(*args, **kwargs): pytest.fail("hardware touched before storage guard")
    monkeypatch.setattr(dev, "_bus", forbidden)
    monkeypatch.setattr(dev, "cmd_power_cycle", forbidden)
    monkeypatch.setattr(dev, "_py", forbidden)
    def full(what): raise SystemExit(6)
    monkeypatch.setattr(dev.disk_guard, "require_free", full)
    with pytest.raises(SystemExit) as error:
        dev.cmd_recover([str(tmp_path / "AWT0-test.bin")])
    assert error.value.code == 6


@pytest.mark.parametrize("status", [0, 10])
def test_verified_flash_tag_enospc_reports_warning_status(dev, monkeypatch, tmp_path, status):
    monkeypatch.setattr(dev, "_unit", lambda extra: ("2", {"serial": "AWT0", "relay": "so-th-1"}))
    real_write = Path.write_text
    def write(path, text, *args, **kwargs):
        if path.name == "AWT0-flashed.json" and '"attempted"' not in text:
            raise OSError(errno.ENOSPC, "tag disk full")
        return real_write(path, text, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", write)
    monkeypatch.setattr(dev, "_py", lambda *args, **kwargs: status)
    assert dev.cmd_flash(["--bus", "11", str(tmp_path / "AWT0-test.bin")]) == 10


def test_recovery_reset_interlocks_debug_before_isp(monkeypatch, tmp_path):
    import rtd_reset as reset
    bus = DebugBus(stuck=True, expiry=None)
    install_bus(monkeypatch, bus)
    monkeypatch.setattr(reset.i2cbus, "require_unit", lambda *args: "AWT0")
    monkeypatch.setattr(reset, "Rtd", lambda bus: pytest.fail("entered ISP with debug active"))
    monkeypatch.setenv("AWTO_DDC_REPO", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["rtd_reset.py", "11", "--serial", "AWT0"])
    assert reset.main() == 6


@pytest.mark.parametrize("fault", ["open", "write", "flush", "close"])
def test_parent_log_enospc_still_drains_and_waits_for_flash(dev, monkeypatch, tmp_path, fault):
    import io
    class Full(io.StringIO):
        def write(self, text):
            if fault == "write": raise OSError(errno.ENOSPC, "tee write")
            return super().write(text)
        def flush(self):
            if fault == "flush": raise OSError(errno.ENOSPC, "tee flush")
            super().flush()
        def close(self):
            if fault == "close": raise OSError(errno.ENOSPC, "tee close")
            super().close()
    path = tmp_path / "tee.log"
    monkeypatch.setattr(dev, "_UNIT_LOG", path)
    original_open = Path.open
    def open_tee(p, *args, **kwargs):
        if p == path:
            if fault == "open": raise OSError(errno.ENOSPC, "tee open")
            return Full()
        return original_open(p, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_tee)
    consumed, waited = [], []
    class Child:
        @property
        def stdout(self):
            for index in range(20):
                consumed.append(index)
                yield f"verified sector {index}\n"
        def wait(self):
            assert consumed == list(range(20))
            waited.append(True)
            return 0
    monkeypatch.setattr(dev.subprocess, "Popen", lambda *args, **kwargs: Child())
    assert dev._py("rtd_flash_image.py", shield=True) == 10
    assert waited == [True]
