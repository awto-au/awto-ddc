"""Fakes of a reference monitor's bus for tests/test_reference_mon.py and tools/osd_editor/test_reference_pane.py (no pytest import)."""
from __future__ import annotations

import json
import typing
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PHILIPS = json.loads((REPO / "scripts/devices.json").read_text())["reference"]["philips"]


def xor_sum(*bs):
    c = 0
    for b in bs:
        c ^= b
    return c


def reply(code, cur, mx, rc=0):
    body = bytes([0x6E, 0x88, 0x02, rc, code, 0x00, mx >> 8, mx & 0xFF, cur >> 8, cur & 0xFF])
    return body + bytes([xor_sum(0x50, *body)])


class FakeMonitor:
    """one bus: records (time, addr, bytes) of every write, answers Get VCP from `values` (code -> (cur, max))"""
    log: typing.ClassVar[list] = []
    values: typing.ClassVar[dict] = {}
    clock = None

    def __init__(self, n):
        self.n, self.last = n, None

    def write(self, addr, reg, data):
        frame = bytes([reg]) + bytes(data)
        FakeMonitor.log.append((FakeMonitor.clock.t, addr, frame))
        self.last = frame

    def ops(self, addr, ops):
        FakeMonitor.log.append((FakeMonitor.clock.t, addr, ("read", ops[0])))
        code = self.last[3]
        if code not in FakeMonitor.values:
            return [reply(code, 0, 0, rc=1)]
        return [reply(code, *FakeMonitor.values[code])]

    def close(self):
        pass


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def nap(self, s):
        self.t += s
