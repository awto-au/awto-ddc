#!/usr/bin/env python3
"""#165 step 2 / #26: force frame-buffer (memory work) mode at the current timing and read the DDR / FIFO flags.

usage: mem_mode.py --bus 11 --serial AWT26110003 read|frame|sdk
  read   snapshot: M-domain / FIFO status + DDR PHY read-window flags (pages 8F / CF, cleared, re-read after FLAG_WINDOW_S)
  frame  snapshot, test cmd 0x0C (frame buffer forced; FRC image), wait for the new memory select, snapshot
  sdk    the same with test cmd 0x0D (back to the SDK choice: line buffer at 4K60)
- Firmware: fw/test/testcmd.c AwtoMemForce; the firmware logs one sync line per request and per memory-select change (E3).
- Debug link (0x35) must be on (dbg_link.py on BUS); unit lock is the caller's (unit_lock.py acquire).
- Run at steady ACTIVE only (ddr_flags_probe.py rule). Main is not paused.
Log: ./tmp/logs/mem_mode.log
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr  # noqa: E402

TESTCMD = 0xF6F8                     # g_stAwtoDiag (0xF6D0) + 0x28 (docs/diag-block.md)
CMD = {"frame": 0x0C, "sdk": 0x0D}  # RL6449_Project.h AWTO_TC_MEM_FRAME / _SDK
# M-domain status (P0_02 bit0 M1 underflow, bit1 overflow), FIFO / capture-display enables, frame-sync mode, DDR client mux
REGS = [("P0_02", 0x0002), ("P0_0C", 0x000C), ("P0_28", 0x0028), ("P5_27", 0x0527), ("P5_AC", 0x05AC),
        ("P5_B0", 0x05B0), ("P45_B0", 0x45B0), ("P5_2B", 0x052B), ("P45_2B", 0x452B), ("P37_B0", 0x37B0),
        ("P20_F0", 0x20F0), ("P20_F1", 0x20F1), ("P20_F2", 0x20F2), ("P5_49", 0x0549), ("P45_49", 0x4549)]  # rotation line block + cw180
P5_AC_DISP_BITS = 0x06               # P5_AC bits 2:1: line buffer sets bit2 (frame-sync source), ScalerFRCDisplayCtrl clears both (#26)
# Re-run = one display-setting pass, 217 ms measured at 4K60 (#26 meas4k); the SDK gives a set-up 2 s before NOSUPPORT
# (SysJudge), so 1.25 x 2 s = 2.5 s. Expiry: logged with elapsed time and the last P5_AC, exit 1.
SELECT_LIMIT_S, POLL_S = 2.5, 0.05
FLAG_WINDOW_S = 0.5                  # flags return within ~0.5 s with DDR traffic (#26, 2026-11-07); clear, wait, read
f2 = lambda v: "--" if v is None else format(v, "02x")
# page-relative (regdb, DDR2 DLL A/B Part2): VALID_WIN_DET_0 03, VALID_WIN_DET_SLIC0/1 04..0B, INT_STATUS0 EF, INT_STATUS1 F1..F7 =
# RW1C-style flag bytes, cleared here. 14 (VALID_WIN_SEL_ODD_3, a sampling-point SETTING) and 88 / 8A (CAL_OUT, read-only) are read only:
# ddr_flags_probe.py's FLAGS also writes 00 to 14 (a setting), so it is not reused.
FLAGS = [0x03] + list(range(0x04, 0x0C)) + [0xEF] + list(range(0xF1, 0xF8))
READ_ONLY = [0x14, 0x88, 0x8A]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("op", choices=["read", "frame", "sdk"])
    a = ap.parse_args()
    (i2cbus.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (i2cbus.ROOT / "tmp/logs/mem_mode.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)

    def snap(tag):
        log(f"{tag} regs " + " ".join(f"{n}={f2(rd(d, r))}" for n, r in REGS))
        for pg in (0x8F, 0xCF):
            log(f"{tag} P{pg:02X} as-found " + " ".join(f"{r:02x}={f2(rd(d, pg << 8 | r))}" for r in READ_ONLY + FLAGS))
        for pg in (0x8F, 0xCF):
            for r in FLAGS:
                wr(d, pg << 8 | r, 0x00)
            log(f"{tag} P{pg:02X} right after clear " + " ".join(f"{r:02x}={f2(rd(d, pg << 8 | r))}" for r in FLAGS[:3]))
        time.sleep(FLAG_WINDOW_S)
        n = 0
        for pg in (0x8F, 0xCF):
            vals = [rd(d, pg << 8 | r) for r in FLAGS]
            n += sum(1 for v in vals if v)
            log(f"{tag} P{pg:02X} cleared+{FLAG_WINDOW_S}s " + " ".join(f"{r:02x}={f2(v)}" for r, v in zip(FLAGS, vals)))
        log(f"{tag} DDR flag bytes set after clear: {n}")

    log(f"bus {a.bus} serial {a.serial} op {a.op}")
    snap("before" if a.op != "read" else "now")
    if a.op == "read":
        return 0
    want_mem = a.op == "frame"
    if not wr(d, TESTCMD, CMD[a.op]):
        log(f"test cmd 0x{CMD[a.op]:02X} NAK")
        return 1
    log(f"test cmd 0x{CMD[a.op]:02X} sent ({'frame buffer forced' if want_mem else 'SDK memory choice'})")
    t0, v = time.monotonic(), None
    while time.monotonic() - t0 < SELECT_LIMIT_S:
        v = rd(d, 0x05AC)
        if v is not None and (((v & P5_AC_DISP_BITS) == 0) == want_mem):
            break
        time.sleep(POLL_S)
    else:
        log(f"TIMEOUT: P5_AC not {'frame buffer' if want_mem else 'line buffer'} after {time.monotonic() - t0:.2f} s "
            f"(limit {SELECT_LIMIT_S} s), last P5_AC={f2(v)}")
        snap("after-timeout")
        return 1
    log(f"P5_AC={f2(v)} after {time.monotonic() - t0:.2f} s")
    snap("after")
    return 0


if __name__ == "__main__":
    sys.exit(main())
