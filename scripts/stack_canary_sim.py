#!/usr/bin/env python3
"""Stack canary gate (#203): boot to ACTIVE, the canary is quiet; test cmd 0x3F (AWTO_TC_STACK_DEEP) pushes into the guard
zone; the next main pass must flag it (g_ucAwtoStackFatal = 1, high-water >= guard) and halt the main loop.

usage: stack_canary_sim.py BIN [MAP]
Log: tmp/logs/stack_canary_sim.log
"""
import os, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "scripts"))
import fw_sim as S  # noqa: E402

LOG = ROOT / "tmp/logs/stack_canary_sim.log"
BOOT_INSTR = 160_000_000            # boot to ACTIVE budget, as boot_sim
MODE_ACTIVE = 3
TESTCMD = 0xF6F8                    # isr_g_stAwtoDiag + 0x28 (osd_test TESTCMD_OFF)
STACK_DEEP = 0x3F                   # RL6449_Project.h AWTO_TC_STACK_DEEP
GUARD = 0xF0                        # AWTO_STACK_GUARD
SETTLE_S = 0.5                      # sim seconds for the test byte to be taken and the next main pass to check
PASS_SYM = "isr_g_stAwtoDiag"       # diag block: main-loop heartbeat at +0x14 (docs/diag-block.md), big-endian build
PASS_OFF = 0x14


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    binp = Path(sys.argv[1]).resolve()
    mapp = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else binp.with_suffix(".map")
    bus = S.SimBus(binp, mapp, "canary-" + binp.stem, None, boot=False, devs=[], video="1080p60")
    m = bus.m
    if not bus.run_until_mode(MODE_ACTIVE, BOOT_INSTR):
        say("FAIL: never reached ACTIVE"); return 1
    hi, fatal = m.addr("g_ucAwtoStackHigh"), m.addr("g_ucAwtoStackFatal")
    h0, f0 = m.rd(hi)[0], m.rd(fatal)[0]
    say(f"ACTIVE: high-water 0x{h0:02X}, fatal {f0}")
    if f0 != 0 or h0 >= GUARD or h0 < 0x80:
        say("FAIL: canary state wrong before the test"); return 1
    m.wr(TESTCMD, bytes([STACK_DEEP]))
    bus.wait(SETTLE_S)
    h1, f1 = m.rd(hi)[0], m.rd(fatal)[0]
    p_diag = m.addr(PASS_SYM) + PASS_OFF
    pa = int.from_bytes(m.rd(p_diag, 2), "big")
    bus.wait(SETTLE_S)
    pb = int.from_bytes(m.rd(p_diag, 2), "big")
    say(f"after 0x{STACK_DEEP:02X}: high-water 0x{h1:02X}, fatal {f1}, main passes {pa} -> {pb} in {SETTLE_S} s")
    ok = f1 == 1 and h1 >= GUARD and pa == pb
    say("PASS stack canary" if ok else "FAIL stack canary")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
