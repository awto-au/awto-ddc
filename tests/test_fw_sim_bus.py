"""fw_sim.SimBus: debug slave 0x35 of the real image in the simulator, read through the host tools (#38). Offline."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="module")
def bus(fw_image):
    import fw_sim
    b = fw_sim.SimBus(fw_image.bin, fw_image.map)
    yield b
    b.close()


def test_block_and_byte_reads_match_xdata(bus):
    import dbg_xdata as X
    base = bus.diag_base
    want = bus.xdata(base, 4)                       # magic, version, stage: constant once stage 8 is reached
    assert want[:2] == b"AD" and want[3] == 8
    assert X.read_blocks(bus, base, 4) == want       # 0x3C block path, checksum verified by dbg_xdata
    assert X.read_bytes(bus, base, 4) == want        # 0x01/0x3A byte path
    mode = bus.addr("isr_g_stModeInfo")
    assert len(X.read_blocks(bus, mode, 30)) == 30   # 2 chunks (24 + 6)


def test_wrong_device_and_empty_read_nak(bus):
    assert bus.write(0x70, 0x3C, b"\x00") is False
    assert bus.read(bus.DEV8, 0x08, 1) is None       # nothing staged: no reply FIFO content
