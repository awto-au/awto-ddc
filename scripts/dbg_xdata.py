#!/usr/bin/env python3
"""XDATA reads over the firmware debug slave 0x35: byte path and block path (awto-ddc#38). Protocol: docs/diag-block.md.

Byte path (every firmware):  0x01 [hi] stage, 0x3A [lo] -> read 0x08 x1                       (2 writes + 1 read per byte)
Block path (diag version 2): 0x3C [lo, hi, len, seq] -> read 0x08 x (len + 1): data + checksum    (1 write + 1 read per chunk)
  checksum = (seq + lo + hi + sum(data)) & 0xFF; a stale or garbled reply fails it and is retried.
`io` is rtd_i2c_bridge.Real / Emu: write(dev8, sub, data) -> bool, read(dev8, sub, n) -> bytes | None.
"""
from __future__ import annotations

DEV8 = 0x6A                                 # 7-bit 0x35
CMD_HI, CMD_READ, CMD_BLOCK, READ_SUB = 0x01, 0x3A, 0x3C, 0x08
BLK_MAX = 24                                # RL6449_Project.h _AWTO_DBGISR_BLK_MAX: bytes the ISR loads into the IIC data FIFO
VERSION_BLOCK = 2                           # diag block byte 2 (ucVersion): firmware answers 0x3C


def read_byte(io, addr: int) -> bytes | None:
    """One byte, both stage writes + the read (self-contained: no state from an earlier call)."""
    if not (io.write(DEV8, CMD_HI, bytes([addr >> 8])) and io.write(DEV8, CMD_READ, bytes([addr & 0xFF]))):
        return None
    return io.read(DEV8, READ_SUB, 1)


_seq = 0
CHUNK_TRIES = 3                             # per chunk: a 1 MHz reply raced by the ISR fails the checksum ~8 % (#38)


def chunk_cmd(addr: int, n: int, seq: int) -> bytes:
    return bytes([addr & 0xFF, (addr >> 8) & 0xFF, n, seq])


def chunk_ok(addr: int, n: int, seq: int, reply: bytes | None) -> bool:
    """reply = n data bytes + checksum."""
    return (reply is not None and len(reply) == n + 1
            and (seq + (addr & 0xFF) + (addr >> 8) + sum(reply[:n])) & 0xFF == reply[n])


def read_chunk(io, addr: int, n: int, tries: int = CHUNK_TRIES) -> bytes | None:
    """1..BLK_MAX bytes in one read transaction, checksum verified; None after `tries` NAKs / bad replies."""
    global _seq
    if not 1 <= n <= BLK_MAX:
        raise ValueError(f"block length {n} outside 1..{BLK_MAX}")
    for _ in range(tries):
        _seq = (_seq + 1) & 0xFF
        if not io.write(DEV8, CMD_BLOCK, chunk_cmd(addr, n, _seq)):
            continue
        r = io.read(DEV8, READ_SUB, n + 1)
        if chunk_ok(addr, n, _seq, r):
            return r[:n]
    return None


def read_bytes(io, addr: int, n: int) -> bytes | None:
    """Byte path: hi staged once per 256-byte page (rtd_diag protocol), 0x3A + read per byte."""
    out, hi = bytearray(), None
    for i in range(n):
        a = (addr + i) & 0xFFFF
        if a >> 8 != hi:
            hi = a >> 8
            if not io.write(DEV8, CMD_HI, bytes([hi])):
                return None
        if not io.write(DEV8, CMD_READ, bytes([a & 0xFF])):
            return None
        r = io.read(DEV8, READ_SUB, 1)
        if r is None:
            return None
        out.append(r[0])
    return bytes(out)


def read_blocks(io, addr: int, n: int) -> bytes | None:
    out = bytearray()
    for off in range(0, n, BLK_MAX):
        c = read_chunk(io, (addr + off) & 0xFFFF, min(BLK_MAX, n - off))
        if c is None:
            return None
        out += c
    return bytes(out)


def read(io, addr: int, n: int, block: bool) -> bytes | None:
    return read_blocks(io, addr, n) if block else read_bytes(io, addr, n)


def block_supported(header: bytes) -> bool:
    """header = the first 3+ bytes of the diag block (magic 'AD', version)."""
    return len(header) >= 3 and header[:2] == b"AD" and header[2] >= VERSION_BLOCK


def probe(io, diag_base: int) -> bool | None:
    """Does the running firmware advertise the block read? Byte path read of the diag header; None if unreadable."""
    h = read_bytes(io, diag_base, 3)
    return None if h is None else block_supported(h)
