"""Offline protocol model, not a firmware emulator or a hardware speed prediction.

Run `python tests/ddcnet_model.py` to compare policies through ddcnet.loopback,
the existing harness. Models two 128-byte rings, sequence deduplication, ACKs,
one main-loop echo pass per exchange and 100 kHz byte time (9 clocks/byte).
No FIFO/ISR scheduling, clock stretching, controller delay or channel switching.
Firmware contract: docs/ip-over-ddc.md and wb-p14swap awto_net/awto_dbgisr.inc.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ddcnet as N


class ModelIo:
    def __init__(self, limit=27):
        self.limit = limit
        self.rx, self.tx = bytearray(), bytearray()
        self.seq, self.flags, self.ctl = 0, 0, 0
        self.poll_enabled = True
        self.requests = []
        self.accepted = bytearray()
        self.write_faults, self.read_faults = deque(), deque()
        self.reply = b""
        self.t = 0.0
        self.wire_bytes = 0
        self.closed = False

    def _clock(self, n):
        self.wire_bytes += n
        self.t += n * 9 / 100_000

    def _apply(self, seq, ctl, ack, data, rmax):
        self.requests.append((seq, ctl, ack, bytes(data)))
        if seq != self.seq:
            del self.tx[:min(ack, len(self.tx))]
            if ctl & N.CTL_RESET:
                self.rx.clear()
                self.tx.clear()
                self.flags = N.F_RESET
            elif len(data) <= N.RING - len(self.rx):
                self.rx += data
                self.accepted += data
                self.flags = N.F_ACC
            else:
                self.flags = N.F_FULL
            self.seq, self.ctl = seq, ctl & ~N.CTL_RESET
        flags = self.flags | N.F_UP | (N.F_ECHO if self.ctl & N.CTL_ECHO else 0)
        if len(self.tx) > rmax:
            flags |= N.F_MORE
        return flags, N.RING - len(self.rx), bytes(self.tx[:rmax])

    def _poll(self):
        if self.flags & N.F_RESET:
            self.seq, self.flags = 0, 0
        if self.poll_enabled and self.ctl & N.CTL_ECHO:
            n = min(len(self.rx), N.RING - len(self.tx))
            self.tx += self.rx[:n]
            del self.rx[:n]

    def write(self, dev8, sub, q):
        assert (dev8, sub) == (0x6A, 0x3D)
        self._clock(len(q) + 2)
        fault = self.write_faults.popleft() if self.write_faults else None
        if fault == "nak" or len(q) - 4 > self.limit:
            return False
        if fault == "bad":
            f, free, got = N.F_UP | N.F_BAD, N.RING - len(self.rx), b""
        else:
            assert q[-1] == (0x3D + sum(q[:-1])) & 0xFF
            f, free, got = self._apply(q[0], q[1], q[2], q[3:-1], N.B_MAX)
        body = bytes([q[0], f, free, len(got)]) + got.ljust(N.B_MAX, b"\0")
        self.reply = body + bytes([(0x3D + sum(body)) & 0xFF])
        return True

    def _fault(self, reply, ddcci=False):
        fault = self.read_faults.popleft() if self.read_faults else None
        if fault == "drop":
            return None
        if fault == "short":
            return reply[:7]
        if fault == "null":
            return b"\x6e\x80\xbe"
        if fault:
            r = bytearray(reply)
            if fault == "corrupt":
                r[-1] ^= 1
                return bytes(r)
            # Recompute checksum to test semantic rejection, not just checksum rejection.
            if ddcci:
                idx = {"seq": 3, "free": 5, "flags": 4, "length": 1}[fault]
                r[idx] = {"seq": r[3] ^ 1, "free": 129, "flags": N.F_UP | N.F_ACC | N.F_FULL,
                          "length": 0x8E}[fault]
                chk = 0x50
                for b in r[:-1]:
                    chk ^= b
            else:
                idx = {"seq": 0, "free": 2, "flags": 1, "length": 3}[fault]
                r[idx] = {"seq": r[0] ^ 1, "free": 129, "flags": N.F_UP | N.F_ACC | N.F_FULL,
                          "length": 21}[fault]
                chk = (0x3D + sum(r[:-1])) & 0xFF
            r[-1] = chk
            return bytes(r)
        return reply

    def read(self, dev8, sub, n):
        assert (dev8, sub, n) == (0x6A, 0x08, 25)
        self._clock(3 + n)
        r = self._fault(self.reply)
        self._poll()
        return r

    def ddc_write(self, q):
        self._clock(len(q) + 2)
        chk = 0x6E ^ 0x51
        for b in q:
            chk ^= b
        assert chk == 0
        f, free, got = self._apply(q[2], q[3], q[4], q[5:-1], N.A_MAX)
        body = bytes([0x6E, 0x80 | (4 + len(got)), 0xD1, q[2], f, free]) + got
        chk = 0x50
        for b in body:
            chk ^= b
        self.reply = body + bytes([chk])
        return True

    def ddc_read(self, n):
        self._clock(n + 1)
        r = self._fault(self.reply, ddcci=True)
        self._poll()
        return r

    def wait(self, seconds):
        self.t += seconds

    def now(self):
        return self.t

    def close(self):
        self.closed = True


def options(**kw):
    defaults = dict(transport="dbg", wmax=None, adaptive=False, drop=0.0, bytes=600,
                    limit_s=60.0, poll_s=0.002, sim=None, bus="MODEL")
    return SimpleNamespace(**(defaults | kw))


if __name__ == "__main__":
    for n in (600, 60_000):
        for transport, wmax, adaptive in (("dbg", None, False), ("dbg", 27, False),
                                           ("dbg", None, True), ("ddcci", None, False)):
            a = options(transport=transport, wmax=wmax, adaptive=adaptive, bytes=n)
            if N.loopback(a, ModelIo()) != 0:
                raise SystemExit(1)
