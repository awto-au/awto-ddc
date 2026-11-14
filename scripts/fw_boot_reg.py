#!/usr/bin/env python3
"""Boot an image in the simulator (native banking, as fw_sim --boot-check) to diag stage 8, then print XDATA bytes.

usage: fw_boot_reg.py BIN MAP ADDR[,ADDR...] [--expect ADDR=VAL ...]   ADDR/VAL hex; exit 1 on a mismatch or no boot
Registers are plain XDATA in this model (no peripheral side effects): the value is the last firmware write.
Log: tmp/logs/fw_boot_reg.log
"""
import argparse, re, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim  # noqa: E402
import rtd_diag  # noqa: E402

ROOT = fw_sim.ROOT
CHUNK, MAX_INSTR = 1_000_000, 40_000_000     # boot-check passes at ~16 M instr; 2.5x


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin"); ap.add_argument("map"); ap.add_argument("addrs")
    ap.add_argument("--expect", nargs="*", default=[], metavar="ADDR=VAL")
    ap.add_argument("--be", action="store_true", default=True)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/fw_boot_reg.log").open("a")
    lf.write(f"{isostamp.now()} {a.bin}\n")
    img, binp = Path(a.bin).read_bytes(), Path(a.bin)
    sym, _where = fw_sim.parse_map(Path(a.map).read_text(errors="replace"), img)
    gsinit = sym.get("__sdcc_gsinit_startup")
    flash = fw_sim.FlashPort(img)
    s = fw_sim.open_native(img, ROOT / "tmp/fwsim" / binp.stem, lf, flash, [gsinit] if gsinit is not None else [])
    done, ok, hb0 = 0, False, None
    while done < MAX_INSTR and not ok:
        fw_sim.run_chunk(s, flash, CHUNK); done += CHUNK
        blk = fw_sim.read_diag(s)
        d = rtd_diag.decode(blk, a.be) if blk else None
        if d and d["stage"] >= 8:                 # same pass rule as fw_sim --boot-check: heartbeat advances 50
            hb0 = d["hb"] if hb0 is None else hb0
            ok = (d["hb"] - hb0) & 0xFFFF >= 50
    vals = {}
    if ok:
        for ad in a.addrs.split(","):
            n = int(ad, 16)
            s.send(f"dump xram 0x{n:x} 0x{n:x}")
            out = s.read_until(rb"(?m)^0x%04x +[0-9a-f]{2}[^\n]*\n" % n, 30)
            m = re.search(r"^0x%04x\s+([0-9a-f]{2})" % n, out or "", re.M)
            vals[n] = int(m.group(1), 16) if m else None
    s.send("quit")
    rc = 0 if ok else 1
    print(f"boot {'stage 8' if ok else 'FAILED'} after ~{done} instr; " + " ".join(f"{k:04X}={v:02X}" if v is not None else f"{k:04X}=?" for k, v in vals.items()))
    for e in a.expect:
        k, v = (int(x, 16) for x in e.split("="))
        if vals.get(k) != v:
            print(f"MISMATCH {k:04X}: got {vals.get(k)}, expected {v:02X}"); rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
