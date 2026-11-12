"""dbg_xdata block/byte read paths and the rtd_proto decode of 0x3C against a fake debug slave (#38). No hardware."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dbg_xdata as X  # noqa: E402
import rtd_proto as P  # noqa: E402

MEM = {0xF6D0 + i: (i * 7 + 3) & 0xFF for i in range(48)}
MEM[0xF6D0], MEM[0xF6D1], MEM[0xF6D2] = 0x41, 0x44, 2


class Slave:
    """Firmware model: byte path stages hi/lo then a 1-byte read; 0x3C stages lo, hi, len (clamped to BLK_MAX)."""

    def __init__(self, nak_after=None):
        self.hi, self.fifo, self.writes, self.reads, self.nak_after, self.corrupt = 0, b"", 0, 0, nak_after, 0

    def write(self, dev8, sub, data):
        self.writes += 1
        if self.nak_after is not None and self.writes > self.nak_after:
            return False
        if sub == 0x01:
            self.hi = data[0]
        elif sub == 0x3A:
            self.fifo = bytes([MEM.get((self.hi << 8) | data[0], 0)])
        elif sub == 0x3C:
            a, n = (data[1] << 8) | data[0], min(data[2], X.BLK_MAX)
            d = bytes(MEM.get(a + i, 0) for i in range(n))
            self.fifo = d + bytes([(data[3] + data[0] + data[1] + sum(d)) & 0xFF])
            if self.corrupt:
                self.corrupt -= 1
                self.fifo = bytes([self.fifo[0] ^ 1]) + self.fifo[1:]
        return True

    def read(self, dev8, sub, n):
        self.reads += 1
        r, self.fifo = self.fifo[:n], b""
        return r if len(r) == n else None


def test_paths_agree_and_transfer_counts():
    a, b = Slave(), Slave()
    byte = X.read(a, 0xF6D0, 48, block=False)
    blk = X.read(b, 0xF6D0, 48, block=True)
    assert byte == blk == bytes(MEM[0xF6D0 + i] for i in range(48))
    assert a.writes + a.reads == 1 + 48 * 2                       # hi once + 48 x (stage, read)
    assert b.writes + b.reads == 4                                # 2 chunks x (write, read)


def test_bad_checksum_retried_then_fails():
    s = Slave(); s.corrupt = 1
    assert X.read_chunk(s, 0xF6D0, 24) == bytes(MEM[0xF6D0 + i] for i in range(24)) and s.writes == 2
    s = Slave(); s.corrupt = 3
    assert X.read_chunk(s, 0xF6D0, 24) is None and s.writes == 3


def test_chunking_and_bounds():
    s = Slave()
    assert X.read_blocks(s, 0xF6D0, 25) is not None and s.writes == 2
    try:
        X.read_chunk(s, 0xF6D0, X.BLK_MAX + 1)
        assert False
    except ValueError:
        pass


def test_nak_returns_none():
    assert X.read_blocks(Slave(nak_after=1), 0xF6D0, 48) is None
    assert X.read_bytes(Slave(nak_after=5), 0xF6D0, 48) is None


def test_probe_versions():
    assert X.probe(Slave(), 0xF6D0) is True
    MEM[0xF6D2] = 1
    try:
        assert X.probe(Slave(), 0xF6D0) is False
    finally:
        MEM[0xF6D2] = 2
    assert X.probe(Slave(nak_after=0), 0xF6D0) is None


def test_decoder_coalesces_block_read():
    out = []
    d = P.Decoder(lambda ts, tag, text: out.append(text))
    d.feed(P.Txn("t", 0x35, "w", 0x3C, bytes([0xD0, 0xF6, 4, 9]), 0))
    d.feed(P.Txn("t", 0x35, "r", 0x08, bytes([0x41, 0x44, 2, 8, 0x77]), 5))
    d.flush()
    assert len(out) == 1 and "F6D0" in out[0].upper() and "41 44 02 08" in out[0].upper(), out
