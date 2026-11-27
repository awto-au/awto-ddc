#!/usr/bin/env python3
"""DPTx AUX read against a register-level AUX controller model (awto-ddc#247, #248): partial and over-long replies.

usage: dptx_aux_sim.py BIN MAP [--case full,partial,oversize] [--chunk 6]
  Boots to ScalerDisplayDPTxLinkSequence (snapshot), then per case runs the real ScalerDisplayDPTx1AuxRead / AuxWrite against
  AuxCtl (page 9D: request regs, start bit, FIFO, IRQ event W1C) and the dptx_lt_sim DPCD sink, until TrainPatternEnd.
  Cases: full = reply = request; partial = at most --chunk bytes per reply (#248); oversize = first reply of each AuxRead call
  is 31 bytes (FIFO_WR_PTR max, #247), the retry is correct.
  Per AuxRead call (entry -> RET): FAIL on a byte written past buffer + length (GUARD bytes checked), buffer != DPCD on a TRUE
  return, a request not at base + offset with length min(rest, 16), or more than MAX_XACT transactions (runaway).
Log: ./tmp/logs/dptx_aux_sim.log   Exit 1 on any FAIL.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_mem as CM
import dptx_lt_sim as LT
import fw_link_check as L
import fw_sim as S
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/dptx_aux_sim.log"
# AUX TX page 9D (regdb RTD2795T-CG: P9D_A3_AUXTX_TRAN_CTRL ...); bit meanings as ScalerDisplayDPTx1AuxRead uses them
TRAN_CTRL, REQ_CMD, REQ_ADDR_M, REQ_ADDR_L, REQ_LEN, REQ_DATA = 0x9DA3, 0x9DA4, 0x9DA5, 0x9DA6, 0x9DA7, 0x9DA8
REPLY_CMD, REPLY_DATA, FIFO_CTRL, FIFO_WR_PTR, IRQ_EVENT = 0x9DA9, 0x9DAA, 0x9DAB, 0x9DAE, 0x9DB1
START, FIFO_RST = 0x01, 0x03
EV_DONE, EV_RETRY_MAX = 0x20, 0x02
REQ_NATIVE_READ, REQ_NATIVE_WRITE = 0x9, 0x8
FIFO_MAX = 31                       # FIFO_WR_PTR[4:0]
GUARD = 32                          # bytes checked past the buffer: a 31-byte reply into a 1-byte read reaches buffer + 30
MAX_XACT = 40                       # per AuxRead call: the cases need <= 16 + 1 (16 one-byte replies + one retry); 40 = runaway stop
CASES = ("full", "partial", "oversize")
SEQ_INSTR = 160_000_000             # boot to LinkSequence (dptx_lt_sim run_until_mode budget)
CASE_INSTR = 40_000_000             # LinkSequence -> TrainPatternEnd


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def dpcd(sink, addr, n):
    """Sink DPCD bytes addr..addr+n-1 at any offset (dptx_lt_sim.Sink.read answers whole blocks only)."""
    blk = {0x000: LT.SINK_CAPS, 0x202: sink.status(), 0x600: bytes([sink.dpcd.get(0x600, 1)])}
    out = []
    for a in range(addr, addr + n):
        b = sink.dpcd.get(a, 0) if a not in (0x007, 0x107) else 0
        for base, data in blk.items():
            if base <= a < base + len(data):
                b = data[a - base]
        out.append(b)
    return bytes(out)


class AuxCtl(S.Dev):
    """AUX TX controller: a 0 -> 1 start bit sends one request; the reply (done bit, ACK, FIFO per case) lands at the first
    IRQ_EVENT poll after it, as on the unit where it comes after the firmware's 400 us wait, not before its FIFO_WR_PTR check."""

    writes = (TRAN_CTRL, REQ_DATA, FIFO_CTRL, IRQ_EVENT)
    reads = (REPLY_DATA, IRQ_EVENT)

    def __init__(self, sink, case, chunk):
        self.sink, self.case, self.chunk = sink, case, chunk
        self.start, self.ev, self.rx, self.wp, self.tx, self.xact = 0, 0, [], 0, [], []
        self.first, self.x0, self.pend = True, 0, None   # first: next read reply is the long one (oversize); x0: call's first transaction

    def init(self, m):
        self._cells(m)

    def _cells(self, m):
        m.wr(IRQ_EVENT, bytes([self.ev]))
        m.wr(FIFO_WR_PTR, bytes([self.wp & FIFO_MAX]))       # write pointer: reads of REPLY_DATA do not move it
        m.wr(REPLY_DATA, bytes([self.rx[0] if self.rx else 0]))

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == IRQ_EVENT:
            self.ev &= ~v & 0xFF
        elif a == FIFO_CTRL and v & FIFO_RST:
            self.rx, self.wp, self.tx, self.pend = [], 0, [], None
        elif a == REQ_DATA:
            self.tx.append(v)
        elif a == TRAN_CTRL:
            if v & START and not self.start:
                self._xact(m)
            self.start = v & START
        self._cells(m)

    def on_read(self, m, a):
        if a == IRQ_EVENT:
            if self.pend is not None:
                self.rx, self.wp, self.pend = list(self.pend), len(self.pend), None
                m.wr(REPLY_CMD, b"\x00")
                self.ev |= EV_DONE
            self._cells(m)
            return
        if self.rx:
            self.rx.pop(0)
        if self.xact:
            self.xact[-1][4] += 1                    # bytes the firmware copied out of this reply
        self._cells(m)

    def _xact(self, m):
        cmd, am, al, ln = (m.rd(x)[0] for x in (REQ_CMD, REQ_ADDR_M, REQ_ADDR_L, REQ_LEN))
        addr, n = (cmd & 0x0F) << 16 | am << 8 | al, ln + 1
        if sum(1 for x in self.xact[self.x0:] if x[0] == REQ_NATIVE_READ) >= MAX_XACT:
            self.ev |= EV_RETRY_MAX                  # stop a runaway loop: the function's 'HW retry reached' exit
            return
        if cmd >> 4 == REQ_NATIVE_WRITE:
            self.sink.write(addr, bytes(self.tx[:n]))
            self.pend = b""
            self.xact.append([cmd >> 4, addr, n, 0, 0])
        else:
            data = dpcd(self.sink, addr, n)
            if self.case == "partial":
                data = data[: self.chunk]
            elif self.case == "oversize" and self.first:
                data = data + bytes([0xEE] * (FIFO_MAX - n))
            self.first = False
            self.pend = data
            self.xact.append([cmd >> 4, addr, n, len(data), 0])


def ret_pcs(im, name):
    c = next(c for c in im.chunks if c["kind"] == "fn" and c["name"].lstrip("_") == name)
    code, base = im.code(c), c["addr"] & 0xFFFF
    bank = None if c["addr"] < im.common else c["addr"] >> 16
    return bank, c["addr"] & 0xFFFF, [it[1].addr for it in L.sweep(code, base) if it[0] == "i" and it[1].raw[0] == 0x22]


def hook(m, bank, pc, fn):
    m.stubs.setdefault(pc, []).append((bank, "probe", fn))
    m.core.pch[pc] |= 0xFFFF if bank is None else 1 << bank


def parm(m, fn, n):
    """XDATA address of fn's _PARM_n: map names are cut to 32 chars, so the n-th D: line of the cut name (PARM_4, PARM_5)."""
    cut = ("_" + fn + "_PARM_")[:32]
    rows = sorted(int(ln.split()[1], 16) & 0xFFFF for ln in m.map_text.splitlines() if ln.startswith("D:") and ln.split()[2:3] == [cut])
    return rows[n - 4]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", default=",".join(CASES))
    ap.add_argument("--chunk", type=int, default=6, help="partial: bytes per reply (6: 16 -> 6, 6, then the #248 underflow)")
    a = ap.parse_args()
    cases = a.case.split(",")
    im = L.Image(a.bin, a.map, str(L.layout_of(a.bin)), CM.COMMON_END)
    w1c = S.W1C({0xFE69: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, 0xBADC: 0x01})
    ctl = AuxCtl(LT.Sink("fast"), "full", a.chunk)
    bus = S.SimBus(a.bin, a.map, "dptxaux-" + a.bin.stem, None, boot=False, devs=[w1c, ctl], video="1080p60")
    m = bus.m
    for fn in LT.NOOP:
        if "_" + fn in m.sym:
            m.stub(fn, lambda m_, r: {"carry": 1})
    p_len, p_ptr = parm(m, "ScalerDisplayDPTx1AuxRead", 4), parm(m, "ScalerDisplayDPTx1AuxRead", 5)
    h = {"st": None, "ctl": ctl, "seq": False}

    def enter(m_, r):
        st = h["st"]
        if st is None:
            return
        n = m.rd(p_len)[0]
        n = n or 1
        p = m.rd(p_ptr, 3)
        buf = p[1] << 8 | p[2] if bus.be else p[1] << 8 | p[0]
        base = (r["r"][7] & 0x0F) << 16 | r["r"][5] << 8 | r["r"][3]
        st["cur"] = (base, n, buf, bytes(m.rd(buf, n + GUARD)), len(h["ctl"].xact))
        h["ctl"].first, h["ctl"].x0 = True, len(h["ctl"].xact)

    def leave(m_, r):
        st = h["st"]
        if st is None or st["cur"] is None:
            return
        base, n, buf, before, x0 = st["cur"]
        st["cur"] = None
        ok = bool(m.core.sfr[0x50] & 0x80)
        after = bytes(m.rd(buf, n + GUARD))
        xs = [x for x in h["ctl"].xact[x0:] if x[0] == REQ_NATIVE_READ]
        st["calls"].append((base, n, ok, len(xs)))
        tag = f"AuxRead {base:05x} len {n} -> {'TRUE' if ok else 'FALSE'}, {len(xs)} transactions"
        bad = [i for i in range(n, n + GUARD) if after[i] != before[i]]
        if bad:
            st["fails"].append(f"{tag}: {len(bad)} bytes written past the buffer (buffer + {bad[0]} .. + {bad[-1]}) (#247)")
        if len(xs) >= MAX_XACT:
            st["fails"].append(f"{tag}: runaway, the model ended it after {MAX_XACT} transactions (#248)")
        want = dpcd(h["sink"], base, n)
        if ok and after[:n] != want:
            st["fails"].append(f"{tag}: buffer {after[:n].hex()} != DPCD {want.hex()} (#248)")
        off = 0
        for _, xa, xn, got, took in xs:
            exp = (base + off, min(n - off, 16) or 1)
            if (xa, xn) != exp:
                st["fails"].append(f"{tag}: request {xa:05x} len {xn} after {off} bytes, expected {exp[0]:05x} len {exp[1]} (#248)")
                break
            if took > xn:
                st["fails"].append(f"{tag}: copied {took} reply bytes of a {xn}-byte request at {xa:05x} (#247)")
                break
            off += took
        say(f"   {tag}")

    bank, entry, rets = ret_pcs(im, "ScalerDisplayDPTx1AuxRead")
    hook(m, bank, entry, enter)
    for pc in rets:
        hook(m, bank, pc, leave)

    def seq(m_, r):
        if not h["seq"]:
            h["seq"] = True
            m.request_stop()

    def end(m_, r):
        if h["st"] is not None:
            h["st"]["end"] = True
            m.request_stop()

    m.stub("ScalerDisplayDPTxLinkSequence", seq)
    m.stub("ScalerDisplayDPTx1TrainPatternEnd", end)
    used = 0
    while used < SEQ_INSTR and not h["seq"]:
        m.run(1_000_000)
        used += 1_000_000
    if not h["seq"]:
        say(f"{a.bin.name}: FAIL ScalerDisplayDPTxLinkSequence not reached in {SEQ_INSTR} instr")
        return 1
    snap = m.snapshot()
    fails = 0
    for case in cases:
        say(f"{a.bin.name} case {case}" + (f" (chunk {a.chunk})" if case == "partial" else ""))
        m.restore(snap)
        sink = LT.Sink("fast")
        ctl.__init__(sink, case, a.chunk)
        ctl._cells(m)
        h["sink"] = sink
        st = {"calls": [], "cur": None, "fails": [], "end": False}
        h["st"] = st
        used = 0
        while used < CASE_INSTR and not st["end"] and not st["fails"]:
            m.run(1_000_000)
            used += 1_000_000
        if not st["fails"] and not st["end"]:
            st["fails"].append(f"TrainPatternEnd not reached in {CASE_INSTR} instr ({len(st['calls'])} AuxRead calls)")
        if not st["fails"] and not any(c[1] == 16 for c in st["calls"]):
            st["fails"].append("no 16-byte AuxRead (DPCD caps) seen")
        h["st"] = None
        for f in st["fails"]:
            say(f"  FAIL {case}: {f}")
        if not st["fails"]:
            say(f"  PASS {case}: {len(st['calls'])} AuxRead calls, {len(ctl.xact)} transactions, link training reached TrainPatternEnd")
        fails += bool(st["fails"])
    m.close()
    say(f"{a.bin.name}: {'PASS' if not fails else 'FAIL'} ({len(cases) - fails} of {len(cases)} cases pass)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
