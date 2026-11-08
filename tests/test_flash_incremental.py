"""Offline tests for the incremental flash path (scripts/flash_state.py + rtd_flash_image.flash). No hardware.

Run: pytest tests/test_flash_incremental.py -q
"""
from __future__ import annotations

import os
import random
import signal
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flash_state as S  # noqa: E402
import rtd_flash_image as I  # noqa: E402
import rtd_flash_sector as F  # noqa: E402

SECTOR = 4096
NIMG = 24
SENTINEL = b"\xa5" * SECTOR      # contents of sectors beyond the image (settings banks): must never change


@pytest.fixture(autouse=True)
def _log():
    F.LOG = open(os.devnull, "w")
    yield


class FakeIsp:
    """1 MiB NOR flash behind the Rtd method names that rtd_flash_image uses."""
    def __init__(self, tail=SENTINEL, crc_broken=False, sr=0x9C):
        self.flash = bytearray(b"\xff" * (1 << 20))
        for s in range(NIMG, 256):
            self.flash[s * SECTOR:(s + 1) * SECTOR] = tail
        self.crc_broken = crc_broken
        self.sr = sr
        self.erased: list[int] = []
        self.reads = 0                 # read_flash calls
        self.crcs = 0
        self.corrupt: set[int] = set()  # sector addrs whose programming is corrupted (persistent)
        self.corrupt_once: set[int] = set()
        self.reprotected = None
        self._cur = None

    def write(self, reg, val): pass
    def status(self): return self.sr
    def release_wp(self): pass
    def unprotect(self, sr0): self.sr = 0
    def reprotect(self, v): self.reprotected = v
    def write_enable(self): pass
    def wait_wip(self, what, limit): pass
    def program_setup(self): pass

    def erase_sector(self, addr):
        self.erased.append(addr)
        self.flash[addr:addr + SECTOR] = b"\xff" * SECTOR

    def program_page(self, addr, data):
        d = bytearray(data)
        sec = addr & ~(SECTOR - 1)
        if sec in self.corrupt or sec in self.corrupt_once:
            d[3] ^= 0x10
            if addr + 256 == sec + SECTOR:
                self.corrupt_once.discard(sec)
        for i, b in enumerate(d):
            self.flash[addr + i] &= b

    def read_flash(self, addr, n):
        self.reads += 1
        return bytes(self.flash[addr:addr + n])

    def flash_crc(self, addr, n):
        self.crcs += 1
        if self.crc_broken:
            return 0x5A
        return S.crc8(bytes(self.flash[addr:addr + n]))


def image(seed=1, n=NIMG):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n * SECTOR))


def opts(tmp_path, **kw):
    return I.Opts(serial="AWT0", write=True, no_backup=True, manifest=tmp_path / "AWT0-flash-state.json",
                  backup_dir=tmp_path / "bk", seed=7, tag="t", commit="abc", **kw)


def sector_set(addrs):
    return sorted(a // SECTOR for a in addrs)


def test_crc8_known_vector():
    assert S.crc8(b"123456789") == 0xF4          # CRC-8 poly 0x07 check value
    assert S._CRC[1] == 0x07 and S._CRC[2] == 0x0E and S._CRC[255] == 0xF3   # KunYi/RTD266x crc.c table


def test_no_manifest_writes_all_then_second_run_writes_none(tmp_path):
    img, isp = image(), FakeIsp()
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert sector_set(isp.erased) == list(range(NIMG))
    assert bytes(isp.flash[:len(img)]) == img
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    assert st.sectors[:NIMG] == S.sector_hashes(img) and st.sectors[NIMG] is None and st.source == "write"
    isp.erased.clear()
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert isp.erased == []
    assert isp.reprotected == 0x9C


def test_only_changed_sectors_written_and_tail_untouched(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    new = bytearray(img)
    for s in (0, 7, 23):
        new[s * SECTOR + 5] ^= 0xFF
    isp.erased.clear()
    assert I.flash(isp, bytes(new), opts(tmp_path)) == 0
    assert sector_set(isp.erased) == [0, 7, 23]
    assert bytes(isp.flash[:len(new)]) == bytes(new)
    for s in range(NIMG, 256):
        assert bytes(isp.flash[s * SECTOR:(s + 1) * SECTOR]) == SENTINEL


def test_full_flag_ignores_manifest(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    isp.erased.clear()
    I.flash(isp, img, opts(tmp_path, full=True))
    assert sector_set(isp.erased) == list(range(NIMG))


def test_foreign_or_corrupt_manifest_is_ignored(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    p = tmp_path / "AWT0-flash-state.json"
    assert S.FlashState.load(p, "OTHER") is None
    p.write_text("{not json")
    assert S.FlashState.load(p, "AWT0") is None
    isp.erased.clear()
    I.flash(isp, img, opts(tmp_path))
    assert len(isp.erased) == NIMG                  # missing manifest = current behaviour: write all


def test_drift_in_sampled_sector_detected_by_readback(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path, verify="readback"))
    isp.flash[0:4] = b"\x00\x00\x00\x00"            # first sector is always in the sample
    isp.erased.clear()
    o = opts(tmp_path, verify="readback")
    assert I.flash(isp, img, o) == 0
    assert 0 in sector_set(isp.erased)
    assert bytes(isp.flash[:len(img)]) == img


def test_drift_anywhere_detected_by_crc_sweep(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    isp.flash[11 * SECTOR + 100] ^= 0x01            # a middle sector; the CRC sweep covers it even if not sampled
    isp.erased.clear()
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert sector_set(isp.erased) == [11]           # fallback readback diff writes only the bad sector
    assert bytes(isp.flash[:len(img)]) == img


def test_drift_check_cost_is_small(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    isp.reads = 0
    I.flash(isp, img, opts(tmp_path))
    # calibration 2 reads only: the gate is hardware CRC per unchanged run, no readback
    assert isp.reads == 2


def test_pick_sample():
    r = random.Random(1)
    assert S.pick_sample([5, 6, 7], r) == [5, 6, 7]
    s = S.pick_sample(list(range(100)), r)
    assert len(s) == 4 and 0 in s and 99 in s
    assert S.pick_sample([], r) == []


def test_unknown_sectors_are_read_and_only_differing_written(tmp_path):
    img, isp = image(), FakeIsp()
    I.flash(isp, img, opts(tmp_path))
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    for i in (3, 4, 5):
        st.sectors[i] = None
    st.save()
    isp.flash[4 * SECTOR] ^= 0xFF                   # sector 4 really differs, 3 and 5 match
    isp.erased.clear()
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert sector_set(isp.erased) == [4]
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    assert st.sectors[3] == S.sha(img[3 * SECTOR:4 * SECTOR])


def test_bigger_image_than_manifest_reads_the_extra_sectors(tmp_path):
    small, isp = image(1, 10), FakeIsp(tail=b"\xff" * SECTOR)
    for s in range(10, NIMG):
        isp.flash[s * SECTOR:(s + 1) * SECTOR] = b"\xff" * SECTOR
    I.flash(isp, small, opts(tmp_path))
    big = small + image(2, NIMG - 10)
    isp.erased.clear()
    assert I.flash(isp, big, opts(tmp_path)) == 0
    assert sector_set(isp.erased) == list(range(10, NIMG))


def test_crc_verify_catches_bad_program_and_redoes_sector(tmp_path):
    img, isp = image(), FakeIsp()
    isp.corrupt_once = {5 * SECTOR}
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert isp.erased.count(5 * SECTOR) == 2        # redone once
    assert bytes(isp.flash[:len(img)]) == img


def test_persistent_failure_leaves_manifest_safe(tmp_path):
    img, isp = image(), FakeIsp()
    isp.corrupt = {9 * SECTOR}
    with pytest.raises(RuntimeError):
        I.flash(isp, img, opts(tmp_path))
    assert isp.reprotected is None                  # a bad image is never re-protected
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    h = S.sector_hashes(img)
    assert st.sectors[5:9] == h[5:9]                # banked sectors verified before failure
    assert st.sectors[:5] == [None] * 5             # boot/common not reached
    assert st.sectors[9] is None and st.sectors[10] is None   # failed + not reached: unknown
    assert st.source == "write-failed"
    isp.corrupt = set()
    isp.erased.clear()
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert sector_set(isp.erased) == [*range(5), *range(9, NIMG)]     # unknown -> read -> differing/blank rewritten


def test_broken_crc_engine_falls_back_to_readback(tmp_path):
    img, isp = image(), FakeIsp(crc_broken=True)
    isp.corrupt_once = {2 * SECTOR}
    assert I.flash(isp, img, opts(tmp_path)) == 0
    assert isp.crcs >= 1 and bytes(isp.flash[:len(img)]) == img
    assert isp.erased.count(2 * SECTOR) == 2        # readback verify still caught the bad program


def test_manifest_written_after_readback_backup(tmp_path):
    img, isp = image(), FakeIsp()
    o = I.Opts(serial="AWT0", manifest=tmp_path / "AWT0-flash-state.json", backup_dir=tmp_path / "bk", commit="abc")
    assert I.flash(isp, img, o) == 0
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    assert st.source == "readback" and st.sectors[0] == S.sha(bytes(isp.flash[:SECTOR]))
    assert all(s is not None for s in st.sectors)
    assert isp.erased == []                         # dry run


# --- #50.1 / #50.4: Timeout/OSError mid-sector is retried, not fatal ----------------------------------------

class FlakyIsp(FakeIsp):
    """Raises exc on the Nth call (1-based) of the named method, once."""
    def __init__(self, method, nth, exc, **kw):
        super().__init__(**kw)
        self.method, self.nth, self.exc, self.count = method, nth, exc, 0
        orig = getattr(self, method)

        def wrapped(*a, **k):
            self.count += 1
            if self.count == self.nth:
                raise self.exc
            return orig(*a, **k)
        setattr(self, method, wrapped)


@pytest.mark.parametrize("method,nth,exc", [
    ("erase_sector", 3, TimeoutError("erase poll")),            # up-front erase loop
    ("erase_sector", 1, OSError(6, "ENXIO")),
    ("program_page", 20, OSError(6, "ENXIO")),                  # mid-sector, sector 1 page 4
    ("program_page", 5, TimeoutError("engine busy")),
    ("flash_crc", 12, TimeoutError("crc_done")),                # verify of a sector (after calibration/drift CRCs)
])
def test_timeout_and_oserror_mid_sector_are_retried(tmp_path, method, nth, exc):
    img = image()
    isp = FlakyIsp(method, nth, exc)
    nudges = []
    assert I.flash(isp, img, opts(tmp_path), nudge=lambda: nudges.append(1)) == 0
    assert bytes(isp.flash[:len(img)]) == img
    assert nudges, "GMBUS must be nudged after a bus-level error"
    st = S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0")
    assert st.sectors[:NIMG] == S.sector_hashes(img)


def test_persistent_oserror_still_fails_after_tries(tmp_path):
    class Dead(FakeIsp):
        def erase_sector(self, addr):
            raise OSError(6, "ENXIO")
    with pytest.raises(OSError):
        I.flash(Dead(), image(), opts(tmp_path), nudge=lambda: None)


def test_sector_loop_logs_verified_progress(tmp_path):
    lines = []
    F.LOG = type("L", (), {"write": lambda s, x: lines.append(x), "flush": lambda s: None})()
    I.flash(FakeIsp(), image(), opts(tmp_path))
    assert any("written+verified 16/24" in x for x in lines)


# --- #50.6 enter-ISP inside try/finally -----------------------------------------------------------------------

def test_enter_isp_failure_still_sends_reset(monkeypatch, tmp_path):
    img = tmp_path / "AWT0-x.bin"
    img.write_bytes(b"\xff" * SECTOR)
    monkeypatch.setattr(sys, "argv", ["rtd_flash_image.py", "7", str(img), "--serial", "AWT0", "--write"])
    monkeypatch.setattr(I.F, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(I.i2cbus, "require_unit", lambda *a, **k: "AWT0")
    writes = []

    class Bad:
        def __init__(self, bus): pass
        def write(self, reg, val):
            writes.append((reg, val))
        def read(self, reg):
            raise OSError(6, "ENXIO")
    monkeypatch.setattr(I.dbg_link, "flash_guard", lambda bus: __import__("contextlib").nullcontext())
    monkeypatch.setattr(I, "Rtd", Bad)
    assert I.main() == 7
    assert writes[-1] == (0xEE, 0x02)


# --- stop signals never leave erased-unwritten sectors (unit 3 2026-11-07T19:42) ----------------------------------

class SigIsp(FakeIsp):
    """Raises SIGTERM at the process after the nth page program (inside a sector)."""
    def __init__(self, nth, count=1, **kw):
        super().__init__(**kw)
        self.nth, self.count, self.pages = nth, count, 0

    def program_page(self, addr, data):
        super().program_page(addr, data)
        self.pages += 1
        if self.pages == self.nth:
            for _ in range(self.count):
                os.kill(os.getpid(), signal.SIGTERM)


def _erased_unwritten(isp, img):
    return [s for s in sorted({a // SECTOR for a in isp.erased}) if bytes(isp.flash[s * SECTOR:(s + 1) * SECTOR]) == b"\xff" * SECTOR
            and img[s * SECTOR:(s + 1) * SECTOR] != b"\xff" * SECTOR]


def test_sigterm_per_sector_stops_at_boundary_then_rerun_finishes(tmp_path):
    img, isp = image(), SigIsp(nth=16 * 3 + 5)            # mid 4th sector
    assert I.flash(isp, img, opts(tmp_path, per_sector=True)) == 9
    assert _erased_unwritten(isp, img) == []
    assert len(set(isp.erased)) == 4 and isp.reprotected == 0x9C
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    isp.nth = 0
    assert I.flash(isp, img, opts(tmp_path, per_sector=True)) == 0
    assert bytes(isp.flash[:len(img)]) == img


def test_sigterm_erase_all_finishes_the_run(tmp_path):
    img, isp = image(), SigIsp(nth=40)
    assert I.flash(isp, img, opts(tmp_path, per_sector=False)) == 0
    assert bytes(isp.flash[:len(img)]) == img


def test_third_signal_forces_exit_and_marks_manifest(tmp_path):
    img, isp = image(), SigIsp(nth=40, count=3)
    with pytest.raises(KeyboardInterrupt):
        I.flash(isp, img, opts(tmp_path))
    assert S.FlashState.load(tmp_path / "AWT0-flash-state.json", "AWT0").source == "write-failed"


def test_unstable_read_path_refuses_before_any_erase(tmp_path):
    """#71: 1 MHz reads in the low-power state differ run to run; nothing may be erased on such a session."""
    img, isp = image(), FakeIsp()
    n = [0]

    def flaky(addr, k):
        n[0] += 1
        d = bytearray(isp.flash[addr:addr + k])
        d[n[0] % k] ^= 0x01
        return bytes(d)
    isp.read_flash = flaky
    with pytest.raises(I.ReadPathUnstable):
        I.flash(isp, img, opts(tmp_path))
    assert isp.erased == []

