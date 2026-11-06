"""Offline tests for burst page programming (Rtd.program_page_burst / burst_write). No hardware.

The bus is faked at the I2C_RDWR level (Isp._xfer) so the real message construction is exercised.
Run: pytest tests/test_flash_burst.py -q
"""
from __future__ import annotations

import ctypes
import errno
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rtd_flash_image as I  # noqa: E402
import rtd_flash_sector as F  # noqa: E402
from rtd_isp_probe import I2C_M_RD  # noqa: E402

SECTOR, PAGE = F.SECTOR, F.PAGE
BASE = 0x13000


@pytest.fixture(autouse=True)
def _log():
    F.LOG = open(os.devnull, "w")
    yield


class BusRtd(F.Rtd):
    """Real Rtd above _xfer; below it the FakeRtd engine model. Models i915's resend of a NAKed FIRST message
    (intel_gmbus.c do_gmbus_xfer: ret == -ENXIO && i == 0 && try++ == 0 -> restart the whole transfer)."""

    def __init__(self, nak_data_byte=None, nak_once=True):
        self.m = F.FakeRtd(sr=0x00, wp_low=False, base=BASE)
        self.m.partial_ok = True
        self.m.flash[:] = b"\xff" * SECTOR
        self.log = []                       # ("W"|"R", reg, nbytes) per message, in bus order
        self.retries_set = []
        self.nak_data_byte = nak_data_byte  # NAK the first 0x70 write message after this many data bytes
        self.nak_once = nak_once
        self.naks = 0
        self.fifo_resends = 0

    def set_retries(self, n):
        self.retries_set.append(n)

    def _xfer(self, msgs):
        try_ = 0
        while True:
            i, err = self._run(msgs)
            if err is None:
                return
            if err == errno.ENXIO and i == 0 and try_ == 0:
                try_ += 1
                self.fifo_resends += 1
                continue
            raise OSError(err, "NAK")

    def _run(self, msgs):
        for i, mg in enumerate(msgs):
            raw = ctypes.string_at(mg.buf, mg.len) if not mg.flags & I2C_M_RD else None
            if mg.flags & I2C_M_RD:
                reg = self._last_sel
                v = self.m.read(reg)
                self.log.append(("R", reg, mg.len))
                ctypes.memmove(mg.buf, bytes([v]) * mg.len, mg.len)
                continue
            reg, data = raw[0], raw[1:]
            if len(raw) == 1:
                self._last_sel = reg
                self.log.append(("S", reg, 0))
                continue
            self.log.append(("W", reg, len(data)))
            for k, b in enumerate(data):
                if (reg == 0x70 and self.nak_data_byte is not None and k == self.nak_data_byte
                        and (self.naks == 0 or not self.nak_once)):
                    self.naks += 1
                    return i, errno.ENXIO     # bytes before k were accepted (landed in the FIFO)
                self.m.write(reg, b)
        return 0, None


def prog(rtd, addr, pg):
    rtd.program_setup()
    rtd.program_page(addr, pg)


def page(seed=1):
    return bytes(random.Random(seed).getrandbits(8) for _ in range(PAGE))


def test_burst_one_message_per_page_and_lands():
    r = BusRtd()
    r.write_mode = "burst"
    pg = page()
    prog(r, BASE, pg)
    assert bytes(r.m.flash[:PAGE]) == pg
    writes70 = [e for e in r.log if e == ("W", 0x70, 256)]
    assert len(writes70) == 1
    assert max(n for k, rg, n in r.log if k == "W") == 256          # 257 B wire message <= GMBUS 511
    assert r.fifo_resends == 0


def test_burst_chunking_sizes_and_data_order():
    for chunk, want in ((256, [256]), (128, [128, 128]), (100, [100, 100, 56]), (64, [64] * 4), (1, [1] * 256)):
        r = BusRtd()
        r.write_mode, r.burst_chunk = "burst", chunk
        pg = page(chunk)
        prog(r, BASE, pg)
        assert [n for k, rg, n in r.log if k == "W" and rg == 0x70] == want
        assert bytes(r.m.flash[:PAGE]) == pg


def test_message_shape_select_read_then_data():
    """Every 0x70 write is preceded by [select 0x6F][read 1]: the pair absorbs i915's first-message resend."""
    r = BusRtd()
    r.write_mode, r.burst_chunk = "burst", 128
    prog(r, BASE, page())
    i = [n for n, e in enumerate(r.log) if e[:2] == ("W", 0x70)]
    assert len(i) == 2
    for n in i:
        assert r.log[n - 2] == ("S", 0x6F, 0) and r.log[n - 1] == ("R", 0x6F, 1)


def test_wait_sequencing():
    """addr hi, addr mid, buffer-ready poll(s), data bursts, start (0x6F write with bit5), done poll."""
    r = BusRtd()
    r.write_mode = "burst"
    r.program_setup()
    r.log.clear()
    r.program_page(BASE + 0x200, page())
    ops = [(k, rg) for k, rg, n in r.log]
    kinds = []
    for k, rg in ops:
        if (k, rg) not in kinds[-1:]:
            kinds.append((k, rg))
    first70 = kinds.index(("W", 0x70))
    assert kinds[:2] == [("W", 0x64), ("W", 0x65)]
    assert ("R", 0x6F) in kinds[2:first70]                       # buffer-ready polled before any data
    assert kinds.index(("W", 0x6F)) > first70                     # start only after the data
    assert ("R", 0x6F) in kinds[kinds.index(("W", 0x6F)):]         # done polled after the start
    assert r.m.regs[0x66] == 0x00 and (r.m.regs[0x64], r.m.regs[0x65]) == (0x01, 0x32)


def test_page_addresses_all_pages_in_sector():
    r = BusRtd()
    r.write_mode = "burst"
    new = os.urandom(SECTOR)
    r.program_setup()
    for off in range(0, SECTOR, PAGE):
        r.program_page(BASE + off, new[off:off + PAGE])
    assert bytes(r.m.flash) == new


def test_retries_zero_during_burst_restored_after():
    r = BusRtd()
    r.write_mode = "burst"
    prog(r, BASE, page())
    assert r.retries_set == [0, F.I2C_RETRIES_DEFAULT]


def test_default_mode_is_byte_and_unchanged():
    r = BusRtd()
    assert r.write_mode == "byte"
    prog(r, BASE, page())
    n70 = [e for e in r.log if e[:2] == ("W", 0x70)]
    assert len(n70) == PAGE and all(e[2] == 1 for e in n70)


def test_midburst_nak_surfaces_not_resent_and_flushes_buffer():
    r = BusRtd(nak_data_byte=40)
    r.write_mode = "burst"
    with pytest.raises(RuntimeError, match="burst failed"):
        prog(r, BASE, page())
    assert r.fifo_resends == 0                      # NAK on message 2 is NOT resent by the (modelled) i915
    assert r.burst_fails == 1
    assert r.m.pend is None                         # partial page flushed: FIFO pointer restarts at 0
    assert r.retries_set[-1] == F.I2C_RETRIES_DEFAULT


def test_single_message_burst_would_duplicate_prefix():
    """Control: WITHOUT the select/read preface a mid-message NAK is the i == 0 message and i915 resends it,
    duplicating the accepted prefix in the FIFO (the #12 failure). Proves why burst_write has the preface."""
    r = BusRtd(nak_data_byte=40)
    buf = ctypes.create_string_buffer(bytes([0x70]) + page(), 257)
    r.m.regs[0x6F] = 0x80
    r.m.write(0x64, 0); r.m.write(0x6D, F.OP_PROG); r.m.write(0x65, 0x30)
    r._xfer([F.Msg(F.ISP_ADDR, 0, 257, ctypes.addressof(buf))])
    assert r.fifo_resends == 1
    assert len(r.m.pend[1]) == 40 + 256              # 40-byte prefix twice -> shifted page


def test_nak_then_sector_redo_in_byte_mode_verifies():
    """image.write_sector: burst fails on page 3, redo runs the whole sector in byte mode, ends VERIFY OK."""
    r = BusRtd(nak_data_byte=10)
    r.write_mode = "burst"
    new = os.urandom(SECTOR)
    r.m.flash[:] = os.urandom(SECTOR)               # dirty sector: erase must happen
    r.wait_wip = lambda what, limit: None
    r.read_flash = r.m.read_flash
    r.flash_crc = lambda a, n: 0
    I.write_sector(r, BASE, new, crc_ok=False)
    assert bytes(r.m.flash) == new
    assert r.burst_fails == 1 and r._byte_sector == BASE
    # next sector goes back to burst
    r.nak_data_byte = None
    assert (BASE + SECTOR) & ~(SECTOR - 1) != r._byte_sector


def test_burst_fault_in_every_run_never_corrupts_verified_result():
    """Randomised: NAK injected at a random byte on every page of burst mode; sector always ends == new data."""
    rnd = random.Random(5)
    for _ in range(5):
        r = BusRtd(nak_data_byte=rnd.randrange(1, 256), nak_once=False)
        r.write_mode = "burst"
        r.wait_wip = lambda what, limit: None
        r.read_flash = r.m.read_flash
        r.flash_crc = lambda a, n: 0
        new = os.urandom(SECTOR)
        I.write_sector(r, BASE, new, crc_ok=False)
        assert bytes(r.m.flash) == new
