#!/usr/bin/env python3
"""#165 step 2 in fw_sim: test cmds 0x0C (frame buffer forced) / 0x0D (SDK memory choice) at the sim's timing.

usage: AWTO_SIM_CORE=fast mem_mode_sim.py BIN MAP [--mode 2160p60] [--no-frc]
- Boot to ACTIVE, 0x0C, 0x0D; each step's sync-log lines decoded by scripts/sync_log.py (the image's .sync.tsv).
- FRC image: 0x0C -> 'frame buffer forced' + 'memory select:frame-sync frame buffer' + back to ACTIVE;
  0x0D -> 'back to the SDK choice' + 'memory select:frame-sync line buffer'.
- --no-frc (default build): 0x0C -> 'refused: FRC not built', no memory-select line.
- DDR status polls are not modelled in the sim (#26): this checks the firmware path, not the DDR.
Log: tmp/logs/mem_mode_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R
import osd_test as T
import sync_log as S
from _log import shared
from _repo import ROOT

LOG = ROOT / "tmp/logs/mem_mode_sim.log"
BOOT_S = 3.0      # boot to ACTIVE at 4K60 in the sim ~2 s firmware time (h2160 gate) x 1.25, rounded up
STEP_S = 1.0      # one display-setting re-run: 217 ms on hardware (#26 meas4k), FineTune + IVS waits; x ~4 for the frame-buffer path


def say(s):
    shared(LOG).say(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60")
    ap.add_argument("--no-frc", action="store_true")
    a = ap.parse_args()
    say(f"mem_mode_sim {a.bin.name} mode {a.mode}{' (FRC off)' if a.no_frc else ''}")
    s = R.Session(a.bin, a.map, a.mode)
    rows, ring, fails, last = S.load_rows(S.tsv_for(a.map)), S.sym(a.map, "g_stAwtoSync"), 0, None

    def new_lines(title):                     # ring keeps 24 entries: new = after the last line seen (lines carry ms stamps)
        nonlocal last
        _h, lines = S.decode(S.read_ring(s.bus.m.rd, ring), rows)
        out = lines[lines.index(last) + 1:] if last in lines else lines
        last = lines[-1] if lines else last
        say(f"  {title}: {len(out)} new lines")
        for ln in out:
            say(f"    {ln}")
        return "\n".join(out)

    def check(ok, what):
        nonlocal fails
        say(f"  {'PASS' if ok else 'FAIL'} {what}")
        fails += 0 if ok else 1

    def cmd(c):
        addr = s.diag + T.TESTCMD_OFF
        b = s.bus
        if not (b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))):
            say(f"  test cmd 0x{c:02X} NAK")
        b.wait(STEP_S)

    try:
        s.boot()
        s.bus.wait(BOOT_S)
        t = new_lines("boot")
        check("ACTIVE" in t, "boot reaches ACTIVE")
        cmd(0x0C)
        t = new_lines("test cmd 0x0C")
        if a.no_frc:
            check("refused: FRC not built" in t, "0x0C refused in the FRC-off image")
            check("memory select" not in t, "no memory-select change")
        else:
            check("frame buffer forced" in t, "0x0C request line")
            check("memory select:frame-sync frame buffer" in t, "memory select -> frame-sync frame buffer")
            check("->ACTIVE:display set" in t, "back to ACTIVE in frame-buffer mode")
            check("test cmd 0x0C / 0x0D (memory mode)" in t, "request line names the memory test cmd")
            cmd(0x0C)
            check("already forced" in new_lines("test cmd 0x0C again"), "repeat logged as already")
            cmd(0x0D)
            t = new_lines("test cmd 0x0D")
            check("back to the SDK choice" in t, "0x0D request line")
            check("memory select:frame-sync line buffer" in t, "memory select -> line buffer")
            check("->ACTIVE:display set" in t, "back to ACTIVE in line-buffer mode")
        cmd(0x0D)
        check("already" in new_lines("test cmd 0x0D again"), "0x0D with nothing forced logged as already")
    finally:
        s.bus.close()
    say(f"mem_mode_sim: {'PASS' if not fails else f'FAIL ({fails})'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
