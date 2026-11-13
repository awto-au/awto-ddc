#!/usr/bin/env python3
"""#164 PIP hands-on: read / poke scaler registers over debug slave 0x35 with a restore stack.

usage: pip_try.py BUS --serial AWT26110003 snap LABEL        read the PIP-relevant register set -> tmp/pip/snap-LABEL.tsv
       pip_try.py BUS --serial ... poke [--label L] ADDR=VAL...   write (old value saved on tmp/pip/restore.json), read back
       pip_try.py BUS --serial ... restore                   write every saved old value back (reverse order), read back
       pip_try.py BUS --serial ... get ADDR[:N]...           read only
  ADDR/VAL hex. Debug link must be on (dbg_link.py on BUS). Test unit only (unit 3).
Log: ./tmp/logs/pip_try.log (one line per read / write with time, old, new, readback)
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_i2c_bridge as B  # noqa: E402
import i2cbus  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402

DBG = 0x35 << 1
# [regdb] RTD2795T-CG: P31 input select / E-O split, M1 + M2 VGIP, P30 measure select, M2 capture / display counts
SETS = [(0x3100, 0x3110), (0x0010, 0x001F), (0x4010, 0x401F), (0x4023, 0x4023), (0x3000, 0x3003),
        (0x451F, 0x4522), (0x45A2, 0x45A5), (0x4549, 0x4549), (0x0005, 0x0005)]


def rd(dev, addr):
    ok = dev.write(DBG, 0x01, bytes([addr >> 8])) and dev.write(DBG, 0x3A, bytes([addr & 0xFF]))
    r = dev.read(DBG, 0x08, 1) if ok else None
    return r[0] if r else None


def wr(dev, addr, val):
    return (dev.write(DBG, 0x01, bytes([addr >> 8])) and dev.write(DBG, 0x03, bytes([val]))
            and dev.write(DBG, 0x3B, bytes([addr & 0xFF])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("cmd", choices=["snap", "poke", "restore", "get"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/pip").mkdir(parents=True, exist_ok=True)
    logf = (root / "tmp/logs/pip_try.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); logf.write(line + "\n"); logf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    dev = B.Real(a.bus, allow_write=True)
    rf = root / "tmp/pip/restore.json"
    stack = json.loads(rf.read_text()) if rf.exists() else []
    if a.cmd == "snap":
        out = []
        for lo, hi in SETS:
            for ad in range(lo, hi + 1):
                v = rd(dev, ad)
                out.append(f"{ad:04X}\t{'--' if v is None else f'{v:02X}'}")
        (root / f"tmp/pip/snap-{a.args[0]}.tsv").write_text("\n".join(out) + "\n")
        log(f"snap {a.args[0]}: {len(out)} regs")
    elif a.cmd == "get":
        for it in a.args:
            n, _, c = it.partition(":")
            base = int(n, 16)
            log(f"get 0x{base:04X}: " + " ".join(
                "--" if (v := rd(dev, base + k)) is None else f"{v:02X}" for k in range(int(c or 1))))
    elif a.cmd == "poke":
        for it in a.args:
            ad, v = (int(x, 16) for x in it.split("="))
            old = rd(dev, ad)
            ok = wr(dev, ad, v)
            new = rd(dev, ad)
            stack.append([ad, old])
            rf.write_text(json.dumps(stack))
            log(f"poke {a.label}: 0x{ad:04X} old={old if old is None else f'{old:02X}'} <- {v:02X} "
                f"{'ok' if ok else 'NO ACK'} readback={new if new is None else f'{new:02X}'}")
    else:
        while stack:
            ad, old = stack.pop()
            if old is not None:
                ok = wr(dev, ad, old)
                log(f"restore: 0x{ad:04X} <- {old:02X} {'ok' if ok else 'NO ACK'} readback={rd(dev, ad):02X}")
            rf.write_text(json.dumps(stack))
    return 0


if __name__ == "__main__":
    sys.exit(main())
