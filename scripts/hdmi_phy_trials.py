#!/usr/bin/env python3
"""awto-ddc#55: freeze a failed 4K60 pass, read SCDC char-error rates + RX PHY pages, try vendor PHY values per group.

usage: hdmi_phy_trials.py --unit N --bus B --serial S [--only P1,P2] [--n 12]
  Freeze as freeze_trials.py (main paused 0x80 01, writes via debug slave 0x35). SCDC (host DDC 0x54) error counters
  clear on read: rate = count / elapsed since the previous read. Per trial: baseline rate, write group, rate, P0_02 burst,
  restore. Log: tmp/logs/hdmi_phy_trials.log; frozen PHY pages 7A-7C: tmp/regs/<serial>-<ts>-phy-frozen.json
"""
import argparse, json, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr, DBG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
f2 = lambda v: "--" if v is None else format(v, "02x")
LANES = [(0x7BAA, 0x7BA4, 0x7BA5), (0x7BBA, 0x7BB4, 0x7BB5), (0x7BCA, 0x7BC4, 0x7BC5)]
# Vendor 4K60 ACTIVE values (tmp/regs/AWT26110003-20261105-180523.json) that differ from our frozen failed pass
TRIALS = {
    "P1_cmu05": [(0x7B1F, 0x06)],
    "P2a_tap0": [(0x7BA4, 0x07), (0x7BC4, 0x06), ("reload", 0x01)],
    "P2b_le_tap1": [(0x7BA5, 0x12), (0x7BB5, 0x14), (0x7BC5, 0x12), ("reload", 0x02)],
    "P2_init": [(0x7BA4, 0x07), (0x7BA5, 0x12), (0x7BB5, 0x14), (0x7BC4, 0x06), (0x7BC5, 0x12), ("reload", 0x03)],
    "P3_anacdr": [(0x7B32, 0x70), (0x7B34, 0x70), (0x7B37, 0x6F)],
    "P4_all": [(0x7B1F, 0x06), (0x7BA4, 0x07), (0x7BA5, 0x12), (0x7BB5, 0x14), (0x7BC4, 0x06), (0x7BC5, 0x12),
               (0x7B32, 0x70), (0x7B34, 0x70), (0x7B37, 0x6F), ("reload", 0x03)],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--only")
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    lf = (ROOT / "tmp/logs/hdmi_phy_trials.log").open("a")

    def log(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)
    sb = i2cbus.Bus(a.bus)

    def scdc():
        try:
            e = sb.read(0x54, 0x50, 6)
            return [(e[2 * i + 1] << 8 | e[2 * i]) for i in range(3)]
        except OSError:
            return None

    def rate(tag, win=1.0):
        # Counter is a snapshot refreshed about once per frame and cleared on read: poll every ~20 ms for `win` s
        scdc(); t0 = time.monotonic(); tot = [0, 0, 0]; bad = nr = 0
        while time.monotonic() - t0 < win:
            nxt = time.monotonic() + 0.02
            while time.monotonic() < nxt:
                pass
            c = scdc(); nr += 1
            if c is None:
                bad += 1; continue
            for i in range(3):
                tot[i] += c[i] & 0x7FFF
        dt = time.monotonic() - t0
        log(f"{tag}: SCDC {nr} reads in {dt:.2f} s (fail {bad}); errors ch0/1/2 = {tot} -> /s = {[round(x / dt) for x in tot]}")
        return tot

    def burst(tag):
        wr(d, 0x0002, 0xFF)
        vals = [rd(d, 0x0002) for _ in range(20)]
        flags = {v for v in vals if v}
        log(f"{tag}: P0_02 x20 = " + " ".join(f2(v) for v in vals) + f"  -> {'CLEAN' if not flags else 'flags ' + ','.join(f2(f) for f in sorted(flags))}")

    proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
    end = time.monotonic() + 12.0
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
    cfg, scr, st = sb.read(0x54, 0x20, 1)[0], sb.read(0x54, 0x21, 1)[0], sb.read(0x54, 0x40, 1)[0]
    log(f"SCDC cfg 0x{cfg:02x} scrambler status {scr & 1} flags 0x{st:02x}")
    pages = {f"{pg:02X}": [rd(d, (pg << 8) | i) if True else None for i in range(256)] for pg in (0x7B,)}
    out = ROOT / f"tmp/regs/{a.serial}-{time.strftime('%Y%m%d-%H%M%S')}-phy-frozen.json"
    out.write_text(json.dumps({"serial": a.serial, "time": isostamp.now(), "pages": pages}))
    log(f"7B page dumped: {out.name}")
    rate("baseline0")

    sel = a.only.split(",") if a.only else list(TRIALS)
    for name in sel:
        regs = TRIALS[name]
        b = rate(f"{name} baseline")
        orig = [(ad, rd(d, ad)) for ad, _ in regs if ad != "reload"]
        for ad, v in regs:
            if ad == "reload":
                for r8, _, _ in LANES:
                    wr(d, r8, v); wr(d, r8, 0x00)            # INIT_8 bit0 = reload tap0, bit1 = LE+tap1
                continue
            if not any(wr(d, ad, v) for _ in range(3)):
                log(f"  write {ad:04X} failed")
        log("  wrote " + " ".join(f"{ad:04X}={f2(rd(d, ad))}" for ad, _ in regs if ad != "reload"))
        c = rate(f"{name} candidate")
        burst(f"{name}")
        for ad, v in orig:
            if v is not None:
                wr(d, ad, v)
        if any(ad == "reload" for ad, _ in regs):
            for r8, _, _ in LANES:
                wr(d, r8, 0x03); wr(d, r8, 0x00)
        rate(f"{name} restored")
    d.write(DBG, 0x80, bytes([0x00])); log("resumed main")
    proc.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
