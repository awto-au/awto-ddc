"""Offline tests for the DP-AUX fast page path (Rtd.enable_aux_fast / write_regs / program_page_aux, #254). No hardware.

The bus is faked at the I2C_RDWR level (Rtd._xfer) with per-message addresses: 0x4A = fixed register, 0x4B = auto-increment.
Run: pytest tests/test_flash_aux_fast.py -q
"""
from __future__ import annotations

import ctypes
import errno
import os
import random
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import i2cbus
import rtd_flash_sector as F
from i2cbus import I2C_M_RD

SECTOR, PAGE, BASE = F.SECTOR, F.PAGE, 0x13000


@pytest.fixture(autouse=True)
def _log(monkeypatch):
    F.LOG = open(os.devnull, "w")  # noqa: SIM115 - test-lifetime null sink
    monkeypatch.setattr(i2cbus, "adapter_name", lambda bus: "AUX USBC2/DDI TC2/PHY C")
    yield


class AuxRtd(F.Rtd):
    def __init__(self, inc=True, nak_data_byte=None):
        self.m = F.FakeRtd(sr=0x00, wp_low=False, base=BASE)
        self.m.partial_ok = True
        self.bus = types.SimpleNamespace(bus=15)
        self.inc, self.nak_data_byte = inc, nak_data_byte
        self.log = []                                   # (addr, reg, nbytes) per write message, ("R", reg) per read
        self.write_mode = "burst"

    def set_retries(self, n):
        pass

    def write(self, reg, val):
        self._xfer_ops([(0x4A, bytes([reg, val]))])

    def read(self, reg):
        return self._xfer_ops([(0x4A, bytes([reg])), (0x4A, 1)])

    def _xfer(self, msgs):
        sel = None
        for mg in msgs:
            if mg.flags & I2C_M_RD:
                v = self.m.read(sel)
                self.log.append(("R", sel))
                ctypes.memmove(mg.buf, bytes([v]) * mg.len, mg.len)
                continue
            raw = ctypes.string_at(mg.buf, mg.len)
            reg, data = raw[0], raw[1:]
            if not data:
                sel = reg
                continue
            self.log.append((mg.addr, reg, len(data)))
            for k, b in enumerate(data):
                if reg == 0x70 and self.nak_data_byte is not None and k == self.nak_data_byte:
                    self.nak_data_byte = None
                    raise OSError(errno.ENXIO, "NAK")
                self.m.write(reg + k if (mg.addr == 0x4B and self.inc) else reg, b)

    def _xfer_ops(self, ops):
        out = i2cbus.run_ops(self._xfer, 0x4A, [(a, o) for a, o in ops])
        return out[0][0] if out else None   # first byte of the first read buffer


def page(seed=1):
    return bytes(random.Random(seed).getrandbits(8) for _ in range(PAGE))


def test_probe_on_and_off(monkeypatch):
    r = AuxRtd()
    assert r.enable_aux_fast() and r.aux_fast
    r = AuxRtd(inc=False)
    assert not r.enable_aux_fast() and not r.aux_fast          # 0x4B without auto-increment: stay on the burst path
    monkeypatch.setattr(i2cbus, "adapter_name", lambda bus: "i915 gmbus tc3")
    assert not AuxRtd().enable_aux_fast()


def test_page_message_shape_and_lands():
    r = AuxRtd()
    r.enable_aux_fast()
    r.log.clear()
    pg = page()
    r.program_setup()
    r.log.clear()
    r.program_page(BASE, pg)
    assert bytes(r.m.flash[:PAGE]) == pg
    writes = [e for e in r.log if e[0] != "R"]
    assert writes[0] == (0x4B, 0x64, 2)                          # address in one auto-increment message
    assert (0x4A, 0x70, 256) in writes                          # whole page in one message
    assert writes.index((0x4A, 0x70, 256)) == 1 and writes[2][:2] == (0x4A, 0x6F)   # start is its own transfer, after the data


def test_sector_of_pages_lands_with_few_reads():
    r = AuxRtd()
    r.enable_aux_fast()
    r.program_setup()
    sec = b"".join(page(i) for i in range(SECTOR // PAGE))
    for off in range(0, SECTOR, PAGE):
        r.program_page(BASE + off, sec[off:off + PAGE])
    assert bytes(r.m.flash) == sec
    assert r.aux_pages == 16
    reads = [e for e in r.log if e[0] == "R"]
    assert len(reads) <= 16 + 1 + 2                              # one done-poll per page + first-page ready poll (+ probe reads)


def test_nak_mid_data_flushes_and_redoes_on_burst_path():
    r = AuxRtd(nak_data_byte=100)
    r.enable_aux_fast()
    r.program_setup()
    with pytest.raises(RuntimeError, match="aux-fast write failed"):
        r.program_page(BASE, page())
    assert r._legacy_sector == BASE and r.burst_fails == 1
    r.m.flash[:] = b"\xff" * SECTOR                              # the sector is erased and redone
    pg = page(2)
    r.program_setup()
    r.program_page(BASE, pg)                                     # legacy burst path now, no 0x4B
    assert bytes(r.m.flash[:PAGE]) == pg
    assert not any(e[0] == 0x4B for e in r.log[-6:])


def test_write_regs_and_crc_erase_addresses():
    r = AuxRtd()
    r.enable_aux_fast()
    r.log.clear()
    r.write_regs(0x64, [1, 2, 3])
    assert r.log == [(0x4B, 0x64, 3)]
    assert [r.m.regs[k] for k in (0x64, 0x65, 0x66)] == [1, 2, 3]
    off = AuxRtd()
    off.write_regs(0x64, [1, 2, 3])
    assert off.log == [(0x4A, 0x64, 1), (0x4A, 0x65, 1), (0x4A, 0x66, 1)]                     # no fast path: one message per register
