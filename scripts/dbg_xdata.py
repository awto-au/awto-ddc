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


# Read-behind (re/regmap/README.md, re/regmap/read_behind.tsv): on these pages the first read of a 32-bit dword can return the
# previous dword's byte of that lane; a second read of the same address is right. Byte path and block path (every dword start).
BEHIND_PAGES = frozenset({0x88, 0x8A, 0x8B, 0x8E, 0x8F, 0x90, 0xA0, 0xA3, 0xA4, 0xA6, 0xA7, 0xA8, 0xAB, 0xAC, 0xAE, 0xAF,
                          0xC8, 0xCA, 0xCB, 0xCE, 0xCF, 0xD0})


def stale_prone(addr: int, last: int | None) -> bool:
    """A read of `addr` right after a read of `last` (None = unknown) can be stale: read-behind page, new dword."""
    return (addr >> 8) in BEHIND_PAGES and (last is None or (addr >> 2) != (last >> 2))


def read_byte(io, addr: int) -> bytes | None:
    """One byte, both stage writes + the read (self-contained: no state from an earlier call). Read-behind pages: read twice."""
    for _ in range(2 if (addr >> 8) in BEHIND_PAGES else 1):
        if not (io.write(DEV8, CMD_HI, bytes([addr >> 8])) and io.write(DEV8, CMD_READ, bytes([addr & 0xFF]))):
            return None
        r = io.read(DEV8, READ_SUB, 1)
    return r


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
    """Byte path: hi staged once per 256-byte page (rtd_diag protocol), 0x3A + read per byte.
    Read-behind pages: the first read of each new dword is repeated and the second result kept."""
    out, hi, last = bytearray(), None, None
    for i in range(n):
        a = (addr + i) & 0xFFFF
        if a >> 8 != hi:
            hi = a >> 8
            if not io.write(DEV8, CMD_HI, bytes([hi])):
                return None
        for _ in range(2 if stale_prone(a, last) else 1):
            if not io.write(DEV8, CMD_READ, bytes([a & 0xFF])):
                return None
            r = io.read(DEV8, READ_SUB, 1)
            if r is None:
                return None
        last = a
        out.append(r[0])
    return bytes(out)


def read_blocks(io, addr: int, n: int) -> bytes | None:
    """Block path in 24-byte chunks; the parts inside read-behind pages go over the byte path (a block has a stale byte at every dword start)."""
    out = bytearray()
    off = 0
    while off < n:
        a = (addr + off) & 0xFFFF
        if (a >> 8) in BEHIND_PAGES:
            m = min(n - off, 256 - (a & 0xFF))
            c = read_bytes(io, a, m)
        else:
            m = min(BLK_MAX, n - off, 256 - (a & 0xFF))
            c = read_chunk(io, a, m)
        if c is None:
            return None
        out += c
        off += m
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
