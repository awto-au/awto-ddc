#!/usr/bin/env python3
"""Read-only scaler register dump over ISP (MCU halted, then reset): whole pages + indexed data ports.

usage: rtd_reg_dump.py <bus> --serial AWT2611000N [--pages 00,01,38,39,9C,9E] [--port 2A:2B:0x40 ...]
  --pages  hex page numbers; each read as 256 regs via F4/F5 with page select 0x9F
  --port   ADDR:DATA:N on page 0 (index -> ADDR, read DATA), e.g. display-format port 2A:2B:0x40
  Out: tmp/regs/<serial>-<YYYYMMDD-HHMMSS>.json ({"pages": {"9C": [256 ints]}, "ports": {"2A:2B": [...]}}).
  Purpose: capture the old firmware's live panel/eDP/DPLL setup as hardware facts (#7). Writes only the
  page-select (0x9F), index registers of the ports read, and the final reset (0xEE).
Log: ./tmp/logs/rtd_reg_dump.log
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import Osd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--pages", default="00,01,38,39,9C,9E")
    ap.add_argument("--port", action="append", default=None)
    a = ap.parse_args()
    ports = a.port or ["2A:2B:0x40"]
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/regs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp/logs/rtd_reg_dump.log").open("a")
    pages = [int(p, 16) for p in a.pages.split(",")]
    o = Osd(a.bus)
    P.log(f"=== reg dump bus={a.bus} serial={a.serial} pages={a.pages} ports={ports} ===")
    out = {"serial": a.serial, "bus": a.bus, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pages": {}, "ports": {}}
    o.enter()
    try:
        for p in pages:
            out["pages"][f"{p:02X}"] = [o.rd((p << 8) | r) for r in range(256)]
            P.log(f"page {p:02X} read")
        for spec in ports:
            ai, di, n = spec.split(":")
            ai, di, n = int(ai, 16), int(di, 16), int(n, 0)
            vals = []
            for idx in range(n):
                o.wr(ai, idx)
                vals.append(o.rd(di))
            out["ports"][f"{ai:02X}:{di:02X}"] = vals
            P.log(f"port {ai:02X}:{di:02X} x{n}: {bytes(vals).hex(' ')}")
    finally:
        o.reset()
    f = root / "tmp/regs" / f"{a.serial}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    f.write_text(json.dumps(out))
    P.log(f"saved {f}")
    print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
