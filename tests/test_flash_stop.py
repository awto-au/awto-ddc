"""#177: time budget before the first erase, no reset onto a mixed image, byte -> burst on DP AUX. No hardware.

Fake bus: FakeIsp (test_flash_incremental) + a fake clock; costs per I2C message modelled on NVIDIA DP AUX
(write 21 ms, read 42 ms, #71) so byte mode projects ~90 s per sector and burst ~6 s.
Run: pytest tests/test_flash_stop.py -q
"""
from __future__ import annotations

import os
import signal
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_state as S
import i2cbus
import rtd_flash_image as I
import rtd_flash_sector as F
from test_flash_incremental import NIMG, SECTOR, FakeIsp, image, opts

T_WR, T_RD = 0.021, 0.042                   # NVIDIA DP AUX per message (#71)
PAGE_S = {"byte": 256 * T_WR + 7 * T_WR, "burst": 0.33}


class Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(I, "time", types.SimpleNamespace(monotonic=c.monotonic, strftime=I.time.strftime))
    F.LOG = open(os.devnull, "w")
    return c


class AuxIsp(FakeIsp):
    """FakeIsp whose operations advance the fake clock like a DP AUX bus; counts real (non-0xFF) programs."""
    def __init__(self, clock, mode="byte", slow_after_erase=1.0, **kw):
        super().__init__(**kw)
        self.clock, self.write_mode, self.slow = clock, mode, slow_after_erase
        self.burst_fails, self._byte_sector = 0, None

    def _k(self):
        return self.slow if self.erased else 1.0

    def write(self, reg, val):
        self.clock.t += T_WR * self._k()

    def read(self, reg):
        self.clock.t += T_RD * self._k()
        return 0x90

    def program_page(self, addr, data):
        self.clock.t += PAGE_S[self.write_mode] * self._k()
        super().program_page(addr, data)


def test_budget_refuses_before_any_erase(clock, tmp_path):
    img, isp = image(), AuxIsp(clock, "byte")
    before = bytes(isp.flash)
    assert I.flash(isp, img, opts(tmp_path, per_sector=True, max_min=0.5)) == 8
    assert isp.erased == [] and bytes(isp.flash) == before
    assert not I.RUN.mixed                       # flash_main would reset: old image intact


def test_byte_over_budget_switches_to_burst(clock, tmp_path):
    img, isp = image(), AuxIsp(clock, "byte")
    assert I.flash(isp, img, opts(tmp_path, per_sector=True, max_min=4)) == 0   # byte ~36 min, burst ~3 min for 24 sectors
    assert isp.write_mode == "burst" and bytes(isp.flash[:len(img)]) == img and I.RUN.complete


def test_dry_page_leaves_flash_unchanged_and_checks_it(clock, tmp_path):
    img, isp = image(), AuxIsp(clock, "burst")
    isp.flash[:len(img)] = image(seed=2)
    before = bytes(isp.flash)
    addr = (NIMG - 1) * SECTOR + SECTOR - 256
    I.dry_page(isp, addr, crc_ok=True)
    assert bytes(isp.flash) == before and not isp.dry
    isp.flash[addr:addr + 256] = b"\xff" * 256
    isp.corrupt.add((NIMG - 1) * SECTOR)         # model: the 0xFF page lands as 0xEF somewhere
    I.RUN.__init__()
    with pytest.raises(RuntimeError, match="changed after the 0xFF dry page"):
        I.dry_page(isp, addr, crc_ok=False)
    assert I.RUN.touched                         # never reset onto an unknown sector


def test_dry_page_burst_failure_is_not_flushed():
    """A failed burst normally kicks the half-filled page (stale SRAM) into the sector about to be redone; the dry
    page targets a live sector, so no kick (#177)."""
    r = F.FakeRtd(sr=0x00, wp_low=False, base=0)
    r.write_mode, r.dry = "burst", True
    kicks = []
    r._start_page = lambda addr: kicks.append(addr)
    r._stage_page = lambda addr: None

    def bad(reg, data):
        raise OSError(6, "ENXIO")
    r.burst_write = bad
    r.is_i915 = lambda: True
    with pytest.raises(RuntimeError, match="burst failed"):
        r.program_page_burst(0, b"\xff" * 256)
    assert kicks == []
    r.dry = False
    with pytest.raises(RuntimeError):
        r.program_page_burst(0, b"\xff" * 256)
    assert kicks == [0]                          # the normal path still flushes


def test_no_time_stop_once_writing(clock, tmp_path):
    """Projection fits, the real run is 50x slower (unit 3: projected after 5 sectors, stopped, reset): it must finish."""
    img, isp = image(), AuxIsp(clock, "burst", slow_after_erase=50.0)
    assert I.flash(isp, img, opts(tmp_path, per_sector=True, max_min=10)) == 0
    assert bytes(isp.flash[:len(img)]) == img and len(set(isp.erased)) == NIMG


def test_boot_last_order():
    per = I.BANK // SECTOR
    c = I.COMMON_END // SECTOR
    diff = [0, 1, c, c + 1, per, per + c, 2 * per + c, 2 * per]
    got = I.boot_last(diff)
    assert got == [per + c, 2 * per + c, c, c + 1, per, 2 * per, 0, 1]   # banked 1.., bank 0 banked, common 1.., bank 0 common


# --- flash_main exit: reset only onto a whole image -------------------------------------------------------------

class MainIsp(AuxIsp):
    """Bus-level stand-in for Rtd in flash_main: logs register writes; JEDEC ok; SIGTERM after `stop_after` pages."""
    inst = None

    def __init__(self, bus):
        super().__init__(MainIsp.clock, MainIsp.mode)
        self.flash[:] = MainIsp.flash0
        self.writes, self.pages, self.read_chunk, self.burst_chunk = [], 0, 64, 256
        MainIsp.inst = self

    def write(self, reg, val):
        self.writes.append((reg, val))
        super().write(reg, val)

    def common(self, typ, op, nr=0, nw=0, val=0, limit=0.3):
        return int.from_bytes(F.JEDEC_OK, "big")

    def program_page(self, addr, data):
        super().program_page(addr, data)
        if data != b"\xff" * F.PAGE:
            self.pages += 1
            if MainIsp.stop_after and self.pages == MainIsp.stop_after:
                os.kill(os.getpid(), signal.SIGTERM)
        if MainIsp.fail_at is not None and addr == MainIsp.fail_at:
            raise OSError(6, "ENXIO")


def _main(monkeypatch, tmp_path, img, *extra, mode="burst"):
    p = tmp_path / "AWT0-x.bin"
    p.write_bytes(img)
    monkeypatch.setattr(sys, "argv", ["rtd_flash_image.py", "7", str(p), "--serial", "AWT0", "--write", "--no-backup",
                                      "--per-sector", "--write-mode", mode, "--manifest", str(tmp_path / "m.json"), "--direct", *extra])
    monkeypatch.setattr(I.F, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(I.i2cbus, "require_unit", lambda *a, **k: "AWT0")
    monkeypatch.setattr(I.i2cbus, "rate_khz", lambda: 100)
    monkeypatch.setattr(I.i2cbus, "gmbus_nudge", lambda bus: None)    # no real bus traffic
    monkeypatch.setattr(I.disk_guard, "require_free", lambda *a, **k: None)
    monkeypatch.setattr(I, "Rtd", MainIsp)
    lines = []
    real = I.F.log
    monkeypatch.setattr(I.F, "log", lambda s: lines.append(s) or real(s))
    monkeypatch.setattr(I, "log", lambda s: lines.append(s) or real(s))
    rc = I.main()
    return rc, MainIsp.inst, lines


@pytest.fixture()
def main_env(clock):
    MainIsp.clock, MainIsp.mode, MainIsp.stop_after, MainIsp.fail_at = clock, "burst", 0, None
    MainIsp.flash0 = bytes(FakeIsp().flash)
    yield


RESET = (0xEE, 0x02)


def test_signal_stop_mid_run_sends_no_reset_then_rerun_finishes_and_resets(main_env, monkeypatch, tmp_path):
    img = image()
    MainIsp.stop_after = 16 * 3 + 5              # inside the 4th sector
    rc, isp, lines = _main(monkeypatch, tmp_path, img, "--bus-kind", "ddc")
    assert rc == 9 and RESET not in isp.writes
    assert any("UNIT STATE: MIXED" in x for x in lines)
    assert S.FlashState.load(tmp_path / "m.json", "AWT0").source == "write-in-progress"
    MainIsp.stop_after, MainIsp.flash0 = 0, bytes(isp.flash)
    rc, isp, lines = _main(monkeypatch, tmp_path, img, "--bus-kind", "ddc")
    assert rc == 0 and isp.writes[-1] == RESET and bytes(isp.flash[:len(img)]) == img
    assert any("UNIT STATE: new image verified" in x for x in lines)


def test_error_mid_run_sends_no_reset(main_env, monkeypatch, tmp_path):
    MainIsp.fail_at = 5 * SECTOR                 # every program of sector 5 fails: SECTOR_TRIES exhausted
    rc, isp, lines = _main(monkeypatch, tmp_path, image(), "--bus-kind", "ddc")
    assert rc == 10 and RESET not in isp.writes and any("UNIT STATE: MIXED" in x for x in lines)


def test_budget_refusal_on_clean_unit_resets_old_image(main_env, monkeypatch, tmp_path):
    rc, isp, lines = _main(monkeypatch, tmp_path, image(), "--max-min", "0.01", "--bus-kind", "ddc")
    assert rc == 8 and isp.erased == [] and isp.writes[-1] == RESET
    assert any("UNIT STATE: flash unchanged" in x for x in lines)


def test_budget_refusal_on_mixed_unit_sends_no_reset(main_env, monkeypatch, tmp_path):
    st = S.FlashState.empty(tmp_path / "m.json", "AWT0")
    st.save(image="AWT0-x", image_size=NIMG * SECTOR, source="write-in-progress", commit="abc")
    rc, isp, lines = _main(monkeypatch, tmp_path, image(), "--max-min", "0.01", "--bus-kind", "ddc")
    assert rc == 8 and isp.erased == [] and RESET not in isp.writes
    assert any("earlier session part-way" in x for x in lines)


def test_byte_on_dp_aux_is_switched_to_burst(main_env, monkeypatch, tmp_path):
    rc, isp, lines = _main(monkeypatch, tmp_path, image(), "--bus-kind", "dp-aux", mode="byte")
    assert rc == 0 and isp.write_mode == "burst"
    assert any("byte on DP AUX" in x for x in lines)


@pytest.mark.parametrize("name,hint,want", [
    ("i915 gmbus tc3", None, "ddc"), ("AUX USBC2/DDI TC2/PHY C", None, "dp-aux"),
    ("NVIDIA i2c adapter 6 at 1:00.0", "dp-aux", "dp-aux"), ("NVIDIA i2c adapter 3 at 1:00.0", None, "unknown"),
])
def test_bus_kind(monkeypatch, name, hint, want):
    monkeypatch.setattr(i2cbus, "adapter_name", lambda b: name)
    monkeypatch.setattr(i2cbus, "Path", lambda p: Path("/nonexistent"))
    assert i2cbus.bus_kind(99, hint) == want
