#!/usr/bin/env python3
"""Sim check (#56): debug messages firing with no host / a silent host must not stall the main loop.

usage: msg_nohost_sim.py BIN MAP   (needs a build with DebugMessage on; reuses fw_sim.SimBus)
  case A: boot, no host: ring filled (seq > 0), heartbeat advances.
  case B: host enables the channel (0x55 0x5A) early in boot, then never reads: boot still reaches the main loop,
          the firmware drops the host after AWTO_MSG_HOST_MS (d_g_bDebugMessageEven off), later messages go to the ring only.
Log: ./tmp/logs/msg_nohost_sim.log
"""
import struct, sys, time
from pathlib import Path

import os
sys.path.insert(0, str(Path(__file__).resolve().parent))
if os.environ.get("AWTO_FWSIM_DIR"):      # branches older than fw_sim.SimBus: point at a checkout that has it
    sys.path.insert(0, os.environ["AWTO_FWSIM_DIR"])
import fw_sim as S  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402


def ring_seq(b) -> int:
    return int.from_bytes(b.xdata(b.addr("g_usAwtoMsgSeq"), 2), "big" if b.be else "little")


def run(binp, mapp, enable_early: bool):
    b = S.SimBus(binp, mapp, tag="msgnohost", boot=False, video="1080p60")
    if enable_early:
        b.m.run(300_000)
        b.write(b.DEV8, 0x55, b"\x5a")
    d = b.boot(passes=5)
    ok = b.run_until_mode(3)
    d2 = b.diag()
    hb = (d2["hb"] - d["hb"]) & 0xFFFF
    for _ in range(3):                      # one m.run(n) can return early on a device event: loop
        b.m.run(1_000_000)
    d3 = b.diag()
    return {"seq": ring_seq(b), "stage": d3["stage"], "hb_after_boot": (d3["hb"] - d2["hb"]) & 0xFFFF, "active": ok}


def main() -> int:
    binp, mapp = Path(sys.argv[1]), Path(sys.argv[2])
    lg = (repo_root() / "tmp/logs/msg_nohost_sim.log").open("a")
    rc = 0
    for name, early in (("A no host", False), ("B silent host", True)):
        r = run(binp, mapp, early)
        good = r["seq"] > 0 and r["stage"] >= 8 and r["hb_after_boot"] > 20 and r["active"]
        line = f"{'PASS' if good else 'FAIL'} {name}: {r}"
        print(line); lg.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n")
        rc |= 0 if good else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
