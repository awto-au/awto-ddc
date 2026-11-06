"""unit_health.py offline: decoders and checks against a fake XDATA (#11, #38). No hardware."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unit_health as H  # noqa: E402

MAPS = {"g_stAwtoDiag": 0xF6D0, "g_stModeInfo": 0xF2A5, "g_stPowerInfo": 0xF2B0, "g_stMDomainInputData": 0xF0D9,
        "g_stOsdInfo": 0xEA89}
TIMING = bytes.fromhex("03 0547 1130 0f00 0226 000b 0259 08ca 0870 004e 0003".replace(" ", ""))


class FakeIo:
    """Debug slave model: 0x01 stage hi, 0x3A stage lo -> read, 0x03 stage value, 0x3B write. consume_after: reads of
    the event/test byte before the firmware clears it (None = never)."""

    def __init__(self, mem, consume_after=1, fail_first=0):
        self.mem, self.hi, self.lo, self.val = mem, 0, 0, 0
        self.consume_after, self.pending, self.fail_first = consume_after, {}, fail_first
        self.blk, self.blk_reads = None, 0

    def write(self, dev8, sub, data):
        if self.fail_first:
            self.fail_first -= 1
            return False
        if sub == 0x01:
            self.hi = data[0]
        elif sub == 0x03:
            self.val = data[0]
        elif sub == 0x3A:
            self.lo = data[0]
        elif sub == 0x3C:
            self.blk = ((data[1] << 8) | data[0], min(data[2], 24), data[3], data[0], data[1])
            self.blk_reads += 1
        elif sub == 0x3B:
            a = (self.hi << 8) | data[0]
            self.mem[a] = self.val
            if a in (MAPS["g_stOsdInfo"] + 5, MAPS["g_stAwtoDiag"] + 0x28):
                self.pending[a] = self.consume_after
                if a == MAPS["g_stOsdInfo"] + 5:
                    self.mem[MAPS["g_stOsdInfo"] + 4] = self.mem.get(MAPS["g_stOsdInfo"] + 4, 0) ^ 0x01   # osd state moves
        return True

    def _byte(self, a):
        if a in self.pending and self.pending[a] is not None:
            self.pending[a] -= 1
            if self.pending[a] < 0:
                self.mem[a] = 0
        return self.mem.get(a, 0)

    def read(self, dev8, sub, n):
        if self.blk is not None:                                       # 0x3C block: n bytes in one transaction
            (a, _, seq, lo, hi), self.blk = self.blk, None
            d = bytes(self._byte(a + i) for i in range(n - 1))
            return d + bytes([(seq + lo + hi + sum(d)) & 0xFF])
        return bytes([self._byte((self.hi << 8) | self.lo)])


def healthy_mem():
    m = {}
    d = MAPS["g_stAwtoDiag"]
    m[d], m[d + 1], m[d + 3] = 0x41, 0x44, 8
    m[MAPS["g_stModeInfo"]] = 0x43
    m[MAPS["g_stPowerInfo"]] = 0x2F
    for i, b in enumerate(TIMING):
        m[MAPS["g_stMDomainInputData"] + i] = b
    m[0xFE2A], m[0xFE1A] = 0x00, 0x01
    return m


class Clock:
    """wait() advances the fake Timer2/hb counters in the memory by `rate` loops/s."""

    def __init__(self, mem, rate=172):
        self.mem, self.rate, self.hb, self.t2 = mem, rate, 1000, 5000
        self.t = 0.0
        self.sync()

    def sync(self):
        d = MAPS["g_stAwtoDiag"]
        self.mem[d + 0x14], self.mem[d + 0x15] = self.hb >> 8, self.hb & 255
        self.mem[d + 0x16], self.mem[d + 0x17] = self.t2 >> 8, self.t2 & 255

    def wait(self, s):
        self.t += s
        self.hb = (self.hb + int(self.rate * s)) & 0xFFFF
        self.t2 = (self.t2 + int(1000 * s)) & 0xFFFF
        self.sync()

    def now(self):
        return self.t


def run_all(mem, host=(3840, 2160, 60.0), consume_after=1, rate=172, fail_first=0):
    clk = Clock(mem, rate)
    rep = H.Report()
    H.run(H.Dbg(FakeIo(mem, consume_after, fail_first)), MAPS, host, rep, wait=clk.wait)
    return rep


def names(rep):
    return {n: ok for n, ok, _ in rep.rows}


def test_decoders():
    assert H.decode_mode(bytes([0x46])) == 6 and H.decode_mode(bytes([0x43])) == 3
    assert H.decode_power(bytes([0x2F])) == (0xF, 2)
    t = H.decode_timing(TIMING)
    assert (t["hwidth"], t["vheight"], t["vfreq"], t["hfreq"]) == (3840, 2160, 601, 1351)
    assert H.parse_host_mode("3840x2160@60.000") == (3840, 2160, 60.0)


def test_gdctl_mode():
    show = ("Monitors:\n├──Monitor DP-4 (AWT 27\")\n│  ├──Current mode\n│  │   └──3840x2160@60.000\n"
            "└──Monitor HDMI-2 (AWT 27\")\n   ├──Current mode\n   │   └──1920x1080@50.000\n\nLogical monitors:\n")
    assert H.gdctl_mode(show, "HDMI-2") == "1920x1080@50.000"
    assert H.gdctl_mode(show, "DP-4") == "3840x2160@60.000"
    assert H.gdctl_mode(show, "HDMI-9") is None


def test_all_pass():
    rep = run_all(healthy_mem())
    assert all(ok for _, ok, _ in rep.rows), rep.rows
    assert rep.summary("t") == 0


def test_power_saving_fails():
    m = healthy_mem()
    m[MAPS["g_stModeInfo"]] = 0x46
    m[0xFE2A], m[0xFE1A] = 1, 0
    r = names(run_all(m))
    assert not r["mode state"] and not r["backlight en"] and not r["panel power"] and r["power status"]


def test_timing_mismatch_and_unknown_host():
    assert not names(run_all(healthy_mem(), host=(1920, 1080, 60.0)))["input timing"]
    assert not names(run_all(healthy_mem(), host=None))["input timing"]


def test_osd_not_consumed():
    r = names(run_all(healthy_mem(), consume_after=None))
    assert not r["osd event"] and not r["osd test cmd"]


def test_diag_retry_once():
    r = names(run_all(healthy_mem(), fail_first=1))        # first stage write NAKs, retry works
    assert r["diag stage"]
    r = names(run_all(healthy_mem(), fail_first=40))
    assert not r["diag stage"]


def test_slow_loop_fails():
    assert not names(run_all(healthy_mem(), rate=10))["main loop"]


def test_block_path_used_when_version_2():
    mem = healthy_mem()
    mem[MAPS["g_stAwtoDiag"] + 2] = 2
    clk = Clock(mem)
    io, rep = FakeIo(mem), H.Report()
    H.run(H.Dbg(io), MAPS, (3840, 2160, 60.0), rep, wait=clk.wait)
    assert all(names(rep).values()), rep.rows
    assert io.blk_reads > 10
    assert "block reads" in dict((n, d) for n, _, d in rep.rows)["diag stage"]


def test_byte_path_when_version_1():
    mem = healthy_mem()
    mem[MAPS["g_stAwtoDiag"] + 2] = 1
    io, rep = FakeIo(mem), H.Report()
    H.run(H.Dbg(io), MAPS, (3840, 2160, 60.0), rep, wait=Clock(mem).wait)
    assert all(names(rep).values()) and io.blk_reads == 0
