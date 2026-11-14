#!/usr/bin/env python3
"""awto-ddc#26: dump all scaler pages of the vendor-dump page set from a frozen failed 4K60 pass, via debug slave 0x35.

usage: freeze_dump.py --unit N --bus B --serial S [--pages 00,01,...|vendor]
  `dev.py mode 4k60`, wait for a failed pass (P0_40==0x24, P0_02&0x61==1), pause main (0x80 01),
  read 256 regs/page with ScalerGetByte (0xPPRR, ~3 ms each, no ISP halt/reset), resume main.
  Out: tmp/regs/<serial>-<ts>-4k-frozen.json (same layout as rtd_reg_dump.py; unread regs = -1). Log: tmp/logs/freeze_dump.log
"""
import argparse, json, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, DBG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "tmp/regs/AWT26110003-20261105-180523.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--pages", default="vendor")
    a = ap.parse_args()
    lf = (ROOT / "tmp/logs/freeze_dump.log").open("a")

    def log(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    pages = sorted(json.load(VENDOR.open())["pages"]) if a.pages == "vendor" else a.pages.upper().split(",")
    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)
    proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
    end = time.monotonic() + 12.0                               # host modeset + DDC storm + several 217 ms passes
    while time.monotonic() < end:
        nxt = time.monotonic() + 0.03
        while time.monotonic() < nxt:
            pass
        p, r40 = rd(d, 0x0002), rd(d, 0x0040)
        if p is not None and r40 == 0x24 and (p & 0x61) == 0x01:
            break
    else:
        log("no failed 4K pass seen; aborting"); proc.wait(); return 1
    d.write(DBG, 0x80, bytes([0x01]))
    log(f"froze main at P0_02={p:02x} P0_40={r40:02x}")
    out, bad = {}, 0
    t0 = time.monotonic()
    for pg in pages:
        row = []
        for r in range(256):
            v = rd(d, int(pg, 16) << 8 | r)
            if v is None:
                v = rd(d, int(pg, 16) << 8 | r)                 # one retry
            row.append(-1 if v is None else v)
        bad += row.count(-1)
        out[pg] = row
    log(f"dumped {len(pages)} pages in {time.monotonic() - t0:.1f}s, {bad} unread regs; P0_02 now {rd(d, 2)}")
    d.write(DBG, 0x80, bytes([0x00])); log("resumed main")
    ts = time.strftime("%Y%m%d-%H%M%S")
    fn = ROOT / f"tmp/regs/{a.serial}-{ts}-4k-frozen.json"
    fn.write_text(json.dumps({"serial": a.serial, "bus": a.bus, "time": isostamp.now(),
                              "note": "frozen failed 4K60 pass, read via 0x35", "pages": out, "ports": {}}))
    log(f"wrote {fn}")
    proc.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
