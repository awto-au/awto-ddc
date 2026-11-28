#!/usr/bin/env python3
"""DRAM log in fw_sim (docs/dram-log-design.md): the DDR ring of a `-D _AWTO_DRAM_LOG=_ON` image, read through the sim's MCU_DC port model.

usage: AWTO_SIM_CORE=fast dram_log_sim.py BIN MAP [--fill-lines N]
- boot: header + entries valid, index 0.. contiguous, first line "boot:cold power-up", no lost line, tail + DDR = one ring (sync_log.read_ring).
- stale DDR: a valid-looking old header + entries of another generation before a cold boot: the new generation ignores them.
- wrap: test cmd AWTO_TC_DLOG_FILL (34000 demo lines > 32768 slots): write index, wrap count 1, the newest 32768 lines in order, no line lost or doubled.
- wedged port (#392): reserved opcode in CMD_A: cleared at the next busy expiry, LEN_A rewritten, one line logged.
- port busy (#392): port A held (no qack) during the second fill: the tail overflows, every dropped demo line is counted in 'log overflow'.
- warm reset (watchdog bite, test cmd 0x4C): the previous boot's lines stay, the new boot's lines follow without a gap, boot counter + 1.
Exit 1 on a failed check. Log: tmp/logs/dram_log_sim.log
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dram_log as D
import fw_sim as FS
import osd_render as R
import sync_log as S
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/dram_log_sim.log"
TC_FILL, TC_BITE = 0xB4, 0x4C                           # RL6449_Project.h AWTO_TC_DLOG_FILL; fw/test/testcmd.c watchdog bite
FILL_LINES = 34000                                      # fw/test/testcmd.c AWTO_DLFILL_LINES
FILL_BUDGET = 4_000_000_000                             # instructions: 34000 lines at 4 per pass, ~150 k instr per pass in the sim, x ~1.5
BITE_BUDGET = 60_000_000                                # test cmd 0x4C -> reset = 14 M instr (con_keep_sim BITE_INSTR 40 M)
BUSY_AT_LEFT = 2000                                     # fill lines still to push when the busy spell starts
BUSY_INSTR = 800_000                                    # port A held: ~165 fill lines pushed (6 M dropped 1233, 2026-11-28), the tail (32) overflows, < 255 (counter cap)
TC_NVFLUSH = 0x3D                                       # test cmd: NVRAM flush, logs one line
WEDGE_CMD, WEDGE_LEN = 0x60, 0x0A                      # read on unit 3 2026-11-28T14:56 (#392)
ID_DEMO = 0xE6                                          # sync.tsv: the fill test cmd demo line (value = line number)
ID_LOGLOST = 0x98                                       # sync.tsv: log overflow: N lines lost (DDR busy)
V4 = 4


def say(s: str) -> None:
    _log_line(s, LOG, stamp_stdout=False)


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.s = R.Session(a.bin, a.map, "1080p60")
        self.m = self.s.bus.m
        self.ddr = next(d for d in self.m.devs if isinstance(d, FS.DdrPort))
        self.ring = S.sym(a.map, "g_stAwtoSync")
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        self.rd = lambda u: self.ddr.mem.get(u)

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def cmd(self, c):
        addr = self.s.diag + R.T.TESTCMD_OFF
        b = self.s.bus
        b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))

    def hdr(self) -> bytes:
        return bytes(self.m.rd(self.ring, S.V4_HDR))

    def newest_demo(self) -> int:
        """value of the newest line in the XDATA tail if it is a fill (demo) line, else 0"""
        x = self.hdr()
        e = bytes(self.m.rd(self.ring + S.V4_HDR + ((x[18] - 1) & 31) * 10, 10))
        return int.from_bytes(e[4:8], "big") if e[0] == ID_DEMO else 0

    def ents(self, count: int | None = None):
        """(header dict, next index, entries) from the DDR model + the XDATA header (pending lines are not in the DDR yet)"""
        h = D.header(self.rd)
        x = self.hdr()
        wr, pend = int.from_bytes(x[19:23], "big"), x[16]
        nxt = D.newest(self.rd, h) if h else 0
        return h, x, wr, pend, nxt, (D.entries(self.rd, h, nxt, count or D.C["AWTO_DLOG_SLOTS"]) if h else [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--fill-lines", type=int, default=FILL_LINES)
    a = ap.parse_args()
    say(f"dram_log_sim {a.bin.name}")
    r = Run(a)
    # stale DDR from another generation before the cold boot: a valid header (gen 7) and entries that would continue it
    stale_gen = 7
    r.ddr.mem[D.C["AWTO_DLOG_HDR_UNITS"]] = _hdr_burst(gen=stale_gen, boot=9, hint=0)
    for i in range(40):
        r.ddr.mem[D.C["AWTO_DLOG_UNITS0"] + i * D.C["AWTO_DLOG_ENTRY_UNITS"]] = _entry_burst(i, stale_gen, 9)
    r.s.boot(sync_console=False)

    h, x, wr, pend, nxt, ents = r.ents()
    r.check(x[2] == V4, "XDATA ring is version 4 (the DRAM log image)", f"version {x[2]}")
    r.check(h is not None and h["gen"] == stale_gen + 1, "cold boot: a valid old header of another generation starts generation + 1", str(h))
    r.check(nxt >= 1 and wr + pend >= nxt, "boot: DDR index <= XDATA index (lines pending in the tail are not in the DDR yet)", f"ddr {nxt}, xdata {wr}+{pend}")
    r.check([e["abs"] for e in ents] == list(range(len(ents))) and len(ents) == nxt, "boot: entries 0.. contiguous, none of the old generation", f"{len(ents)}")
    S.DDR_UNIT = r.rd
    raw = S.read_ring(r.m.rd, r.ring)
    rows = S.load_rows(S.tsv_for(a.map))
    _, lines = S.decode(raw, rows, whole=True)
    r.check(any("boot:cold power-up" in ln for ln in lines) and not any("log overflow" in ln for ln in lines), "boot: the cold power-up line is in the ring, no 'log overflow' line", f"{len(lines)} lines")
    r.check(x[17] == 0, "boot: no line dropped (lost counter 0)")
    boot1, gen1 = (h["boot"], h["gen"]) if h else (-1, -1)

    # wrap
    r.s.bus.wait(1.0)
    base = r.ents()[4] + r.hdr()[16]
    r.cmd(TC_FILL)
    used = 0
    while used < FILL_BUDGET:
        r.m.run(5_000_000)
        used += 5_000_000
        x = r.hdr()
        if int.from_bytes(x[19:23], "big") + x[16] >= base + a.fill_lines and x[16] == 0:
            break
    h, x, wr, pend, nxt, ents = r.ents()
    slots = D.C["AWTO_DLOG_SLOTS"]
    r.check(nxt == wr + pend or nxt == wr, "wrap: DDR index = XDATA write index", f"ddr {nxt}, xdata {wr}+{pend}")
    r.check(nxt >= slots + 1 and nxt // slots == 1, "wrap: the index passed the ring size once (wrap count 1)", f"index {nxt} after {used // 1_000_000} M instr")
    fills = [e for e in ents if e["id"] == 0xE6]
    vals = [e["val"] for e in fills]
    r.check(len(ents) == slots and [e["abs"] for e in ents] == list(range(nxt - slots, nxt)), "wrap: the newest 32768 entries read back, oldest first, contiguous", f"{len(ents)}")
    r.check(vals == list(range(vals[0], vals[0] + len(vals))) and vals[-1] == a.fill_lines, "wrap: demo line numbers consecutive up to the last one (none lost or doubled)", f"{vals[:1]}..{vals[-1:]}")
    r.check(r.hdr()[17] == 0, "wrap: no line dropped (lost counter 0)")
    ms = [e["ms"] for e in ents[8:]]
    r.check(all(b >= a for a, b in itertools.pairwise(ms)) and ms[-1] > ms[0], "wrap: 32 bit stamps non-decreasing over the ring", f"{ms[0]}..{ms[-1]} ms")

    # stamps above 65.5 s (the 16 bit ring time wrapped): a second fill after 40 simulated seconds of idle, stamps must keep rising
    r.s.bus.wait(40.0)
    r.cmd(TC_FILL)
    base2 = r.ents()[4] + r.hdr()[16]
    # #392 port A busy near the end of the fill (the newest 32768 lines keep it): the tail fills, every dropped line must be counted
    dl_busy = S.sym(a.map, "g_ucAwtoDlBusy")
    busy0 = busy1 = -1
    done = 0
    used = 0
    while used < FILL_BUDGET:
        r.m.run(5_000_000)
        used += 5_000_000
        done = max(done, r.newest_demo())
        left = a.fill_lines - done
        if busy0 < 0 and left < BUSY_AT_LEFT:
            busy0 = r.m.rd(dl_busy)[0]
            r.ddr.busy = True
            r.m.run(BUSY_INSTR)
            r.ddr.release(r.m)
            busy1 = r.m.rd(dl_busy)[0]
        if busy0 >= 0 and left == 0 and r.hdr()[16] == 0:
            break
    h, x, wr, pend, nxt, ents = r.ents()
    ms = [e["ms"] for e in ents[8:]]
    r.check(all(b >= a for a, b in itertools.pairwise(ms)) and ms[-1] > 70000, "stamps over 65.5 s: 32 bit, non-decreasing", f"{ms[0]}..{ms[-1]} ms")
    r.check(r.hdr()[17] == 0, "second fill: lost counter written out (0)")
    vals2 = sorted(e["val"] for e in ents if e["id"] == ID_DEMO and e["abs"] >= base2)
    missing = len(set(range(vals2[0], a.fill_lines + 1)) - set(vals2)) if vals2 and vals2[-1] == a.fill_lines else -1   # from the oldest kept (the ring wrapped)
    lost = sum(e["val"] for e in ents if e["id"] == ID_LOGLOST and e["abs"] >= base2)
    r.check(busy1 > busy0, "port busy: the log counted its busy spins (g_ucAwtoDlBusy)", f"{busy0} -> {busy1}")
    r.check(missing > 2 and lost >= missing, "port busy: every dropped demo line counted in 'log overflow' (other lines in the spell may add)",
            f"{missing} demo lines missing, {lost} counted")

    # #392 wedged port: a reserved opcode in CMD_A (no qack) and a foreign LEN_A, as unit 3 showed: the next busy expiry clears it, one line says so
    r.m.wr(FS.DdrPort.R_CMD, bytes([WEDGE_CMD, WEDGE_LEN]))
    base3 = r.ents()[4] + r.hdr()[16]
    r.cmd(TC_NVFLUSH)                                   # one line to write: the drain meets the wedged port
    r.s.bus.wait(2.0)
    cmd, ln = r.m.rd(FS.DdrPort.R_CMD, 2)
    h, x, wr, pend, nxt, ents = r.ents()
    fix = [e["val"] for e in ents if e["id"] == ID_LOGLOST and e["arg"] == 0x01 and e["abs"] >= base3]
    r.check(cmd == 0 and ln == 2 and pend == 0, "wedged port: CMD back to NOP, LEN_A 2, the tail drained", f"CMD {cmd:#04x} LEN {ln:#04x} pending {pend}")
    r.check(fix == [WEDGE_CMD << 8 | WEDGE_LEN], "wedged port: one 'reserved command cleared' line with CMD << 8 | LEN", str([hex(v) for v in fix]))

    # warm reset
    before = ents[-8:]
    r.cmd(TC_BITE)
    used = 0
    while r.cr.resets == 0 and used < BITE_BUDGET:
        r.m.run(1_000_000)
        used += 1_000_000
    r.check(r.cr.resets == 1, "warm reset: watchdog bite", f"{used} instr")
    r.s.bus.run_until_mode(3, 160_000_000)
    r.s.bus.wait(1.0)
    h, x, wr, pend, nxt, ents = r.ents(300)
    r.check(h is not None and h["boot"] == (boot1 + 1) & 0xFF and h["gen"] == gen1, "warm reset: boot counter + 1, same generation", str(h))
    old = [e for e in ents if e["boot"] == boot1]
    new = [e for e in ents if e["boot"] == h["boot"]]
    r.check(old and new and [e["abs"] for e in ents] == list(range(ents[0]["abs"], ents[0]["abs"] + len(ents))), "warm reset: previous boot's lines kept, this boot's follow without a gap", f"{len(old)} old + {len(new)} new")
    r.check(all(e in [x2 for x2 in D.entries(r.rd, h, nxt, 4000)] for e in before), "warm reset: the newest lines of the previous boot are unchanged")
    # the ring view holds the newest 88 lines only: a boot with more lines (a timing-dependent console line) pushes the reason line out of it
    lines = [S.line(rows, (e["id"], e["arg"], e["ms"] & 0xFFFF, e["val"]), 0) for e in new]
    r.check(any("boot:watchdog bite" in ln for ln in lines), "warm reset: this boot's reason line says watchdog bite (DDR entries of this boot)", next((ln for ln in lines if "boot:" in ln), ""))
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} dram_log_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


def _hdr_burst(gen: int, boot: int, hint: int) -> bytes:
    b = b"DL" + bytes([1, gen, boot]) + hint.to_bytes(4, "big") + bytes(6)
    return b + bytes([D._sum(b + b"\0")])


def _entry_burst(a: int, gen: int, boot: int) -> bytes:
    b = bytes([0x01, a & 0xFF]) + a.to_bytes(4, "big") + a.to_bytes(4, "big") + a.to_bytes(3, "big") + bytes([gen, boot])
    return b + bytes([D._sum(b + b"\0")])


if __name__ == "__main__":
    sys.exit(main())
