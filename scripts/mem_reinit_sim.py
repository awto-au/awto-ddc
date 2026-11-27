#!/usr/bin/env python3
"""#353 in fw_sim: memory power cycle after failed frame-buffer M-domain set-ups (SysJudge.c SysMachineMemReinit).

usage: AWTO_SIM_CORE=fast mem_reinit_sim.py BIN MAP [--mode 2160p60]
- Boot to ACTIVE, test cmd 0x0C (frame buffer forced, as Rotate 180 at 4K60), then a sticky FIFO underflow (P0_02 bit 0,
  fw_sim FAULTS) makes the ACTIVE judge and every display setting fail its ScalerMDomainMemoryCheck.
- Case recover: the fault is cleared as soon as the 'memory re-init' line shows -> 'passed after it' + ACTIVE.
- Case stuck: the fault stays -> exactly one 'memory re-init' line per display-setting episode, then the judge timer's
  NO SUPPORT (the existing path; no second power cycle in the episode).
- The sim has no DDR model (#26): this checks the firmware path (counter, bound, log lines), not the DDR.
Log: tmp/logs/mem_reinit_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as F
import osd_render as R
import osd_test as T
import sync_log as S
from _log import shared
from _repo import ROOT

LOG = ROOT / "tmp/logs/mem_reinit_sim.log"
BOOT_S = 3.0        # boot to ACTIVE at 4K60 in the sim ~2 s firmware time (h2160 gate) x 1.25, rounded up (mem_mode_sim)
STEP_S = 1.0        # one frame-buffer display-setting re-run (mem_mode_sim STEP_S)
POLL_S = 0.02       # ring poll step: well under one ~250 ms set-up pass, so the fault clears before the next pass
# fault on -> re-init line: ACTIVE judge fail -> SEARCH (~0.4 s) + 2 failed passes (2 x ~0.25 s) = ~0.9 s, x1.25 -> 1.2 s
REINIT_S = 1.2
# re-init -> ACTIVE: one passing frame-buffer set-up (~0.25 s) + the active wait (~0.1 s) = ~0.35 s, x1.25 -> 0.45 s
RECOVER_S = 0.45
# re-init -> NO SUPPORT: judge timer 2.5 s from the DISPLAY SETTING entry, less the ~0.5 s already spent, x1.25 -> 2.5 s
STUCK_S = 2.5
UNDERFLOW = F.FAULTS["underflow"]


def say(s):
    shared(LOG).say(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60")
    a = ap.parse_args()
    say(f"mem_reinit_sim {a.bin.name} mode {a.mode}")
    s = R.Session(a.bin, a.map, a.mode)
    rows, ring, fails, seen = S.load_rows(S.tsv_for(a.map)), S.sym(a.map, "g_stAwtoSync"), 0, set()
    w1c = next(d for d in s.bus.m.devs if isinstance(d, F.W1C))

    def new_lines():                          # ring keeps 24 entries: new = lines not seen yet in this episode
        h, lines = S.decode(S.read_ring(s.bus.m.rd, ring), rows)
        key = h.get("ep_seq")                 # stamps are ms since the episode start: two episodes can log identical lines (#375)
        out = [ln for ln in lines if (key, ln) not in seen]
        seen.update((key, ln) for ln in out)
        for ln in out:
            say(f"    {ln}")
        return out

    def until(what, limit_s):
        """poll until a new line holds `what`; on expiry log the wait, its limit and the elapsed sim time"""
        t0, got = s.bus.now(), []
        while s.bus.now() - t0 < limit_s:
            s.bus.wait(POLL_S)
            got += new_lines()
            if any(what in ln for ln in got):
                return got
        say(f"  timeout waiting for '{what}': limit {limit_s:.2f} s, elapsed {s.bus.now() - t0:.2f} s (sim)")
        return got

    def fault(on):                            # sticky = re-raised after each clear; the flag itself is raised now too
        w1c.sticky = dict(UNDERFLOW) if on else {}
        for adr, bits in UNDERFLOW.items():
            v = s.bus.m.rd(adr)[0]
            s.bus.m.wr(adr, bytes([(v | bits) if on else (v & ~bits & 0xFF)]))

    def check(ok, what):
        nonlocal fails
        say(f"  {'PASS' if ok else 'FAIL'} {what}")
        fails += 0 if ok else 1

    def cmd(c):
        addr = s.diag + T.TESTCMD_OFF
        b = s.bus
        if not (b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))):
            say(f"  test cmd 0x{c:02X} NAK")

    try:
        s.boot()
        s.bus.wait(BOOT_S)
        new_lines()
        cmd(0x0C)
        got = until("->ACTIVE:display set", STEP_S)
        if any("FRC not built" in ln for ln in got):
            say("mem_reinit_sim: no frame buffer in this image (_AWTO_FRC off): the re-init path is not built, nothing to test")
            return 0
        check(any("memory select:frame-sync frame buffer" in ln for ln in got), "0x0C: frame-sync frame buffer")

        say("  case recover: sticky underflow on, cleared at the re-init line")
        fault(True)
        got = until("memory re-init:", REINIT_S)
        fault(False)
        ri = [ln for ln in got if "memory re-init:" in ln]
        check(len(ri) == 1 and "2 frame-buffer M-domain set-ups failed" in ri[0], "one re-init line after 2 failed set-ups")
        got = until("->ACTIVE:display set", RECOVER_S)
        check(any("passed after it (set-up try 3)" in ln for ln in got), "set-up try 3 passes after the re-init")
        check(any("->ACTIVE:display set" in ln for ln in got), "back to ACTIVE")
        try:
            off = s.bus.m.rd(s.bus.m.addr("g_ucAwtoDdrOff"))[0]
        except Exception:                     # noqa: BLE001 - core-specific lookup error
            off = None                        # an image without the DRAM log guard
        check(off in (None, 0) and not any("log overflow" in ln for ln in got),
              f"#358: memory up again (g_ucAwtoDdrOff {off}), no DRAM log line dropped across the power cycle")

        say("  case stuck: sticky underflow stays")
        fault(True)
        got = until("memory re-init:", REINIT_S)
        got += until("->NO SUPPORT", STUCK_S)
        fault(False)
        n = sum("memory re-init:" in ln and "set-ups failed" in ln for ln in got)
        check(n == 1, f"exactly one re-init in the episode (saw {n})")
        check(not any("passed after it" in ln for ln in got), "no 'passed' line while the fault stays")
        check(any("->NO SUPPORT" in ln for ln in got), "judge timer NO SUPPORT as before")
    finally:
        s.bus.close()
    say(f"mem_reinit_sim: {'PASS' if not fails else f'FAIL ({fails})'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
