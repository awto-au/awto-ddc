#!/usr/bin/env python3
"""Read-only scaler register dump over ISP (MCU halted, then reset): whole pages + indexed data ports.

usage: rtd_reg_dump.py <bus> --serial AWT2611000N [--pages 00,01,38,39,9C,9E] [--port 2A:2B:0x40 ...]
  --pages  hex page numbers; each read as 256 regs via F4/F5 with page select 0x9F
  --pages all  every page with a REG row in the regdb (RTD2795T-CG)
  --ports all  every regdb indexed port in PORT_ADDR, at the regdb-defined indices only (no sweeps)
  --port   ADDR:DATA:N on page 0 (index -> ADDR, read DATA), e.g. display-format port 2A:2B:0x40
  --resume FILE  continue an interrupted run into FILE; pages/ports already in it are skipped
  Out: tmp/regs/<serial>-<YYYYMMDD-HHMMSS>.json ({"pages": {"9C": [256 ints]}, "ports": {"2A:2B": [...]}}),
  rewritten after every page/port.
  Purpose: capture the old firmware's live panel/eDP/DPLL setup as hardware facts (#7). Writes only the
  page-select (0x9F), index registers of the ports read, and the final reset (0xEE).
Log: ./tmp/logs/rtd_reg_dump.log
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_isp_probe as P
import rtd_proto
import regdb_query as Q
from rtd_osd import Osd

# data reg16 -> index/address reg16s (high..low); only ports whose ADDR reg the regdb names.
PORT_ADDR = {0x0025: [0x24], 0x002B: [0x2A], 0x0031: [0x30], 0x0034: [0x33], 0x005D: [0x5C], 0x0061: [0x60],
             0x0065: [0x64], 0x008E: [0x8D], 0x07CF: [0x7CE], 0x07D3: [0x7D2], 0x15A4: [0x15A3],
             0x2AAD: [0x2AAC], 0x2AFC: [0x2AFB], 0x4025: [0x4024], 0x68AD: [0x68AC], 0x68FC: [0x68FB],
             0x713A: [0x7139], 0x723A: [0x7239], 0x71CA: [0x71C9], 0x72CA: [0x72C9],
             0xB7C4: [0xB7C1, 0xB7C2, 0xB7C3], 0xBAC4: [0xBAC1, 0xBAC2, 0xBAC3]}
# Skipped (not read): 0069 dither (ADDR reg unclear), 006D bg colour (no ADDR; write-pointer reset),
# 0092 OSD RAM + 0099/009D (auto-increment / ctrl-gated), 07CA DCC (idx>255), 07D9 DCR (ADDR reg holds
# measure_start), 71C4/72C4 HDCP keys (auto-increment, secret).


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--pages", default="00,01,38,39,9C,9E")
    ap.add_argument("--port", action="append", default=None)
    ap.add_argument("--ports")
    ap.add_argument("--resume", help="JSON from an interrupted run; pages/ports already in it are skipped")
    a = ap.parse_args()
    i2cbus.dev_hint("dump", "rtd_reg_dump.py")
    i2cbus.require_unit(a.bus, a.serial)
    ports = [] if a.ports else a.port or ["2A:2B:0x40"]
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/regs").mkdir(parents=True, exist_ok=True)
    P.LOG = rtd_proto.setup_logs("rtd_reg_dump").main
    rows = [r for r in Q.load("RTD2795T-CG") if r["kind"] == "REG"]
    pages = sorted({int(r["page"], 16) for r in rows}) if a.pages == "all" else [int(p, 16) for p in a.pages.split(",")]
    allp = a.ports == "all"
    if allp:
        a.ports = {}
        for r in rows:
            if r["port_idx"] and int(r["address"], 0) in PORT_ADDR:
                a.ports.setdefault(int(r["address"], 0), set()).add(int(r["port_idx"], 0))
    o = Osd(a.bus)
    P.log(f"=== reg dump bus={a.bus} serial={a.serial} pages={a.pages} ports={ports} ===")
    if a.resume:
        f = Path(a.resume)
        out = json.loads(f.read_text())
    else:
        f = root / "tmp/regs" / f"{a.serial}-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out = {"serial": a.serial, "bus": a.bus, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pages": {}, "ports": {}}

    def save() -> None:   # after every page/port: an interrupted run keeps what it read
        tmp = f.with_suffix(".part")
        tmp.write_text(json.dumps(out))
        tmp.replace(f)

    o.enter()
    try:
        for p in pages:
            if f"{p:02X}" in out["pages"]:
                continue
            out["pages"][f"{p:02X}"] = [o.rd((p << 8) | r) for r in range(256)]
            save()
            P.log(f"page {p:02X} read")
        for spec in ports:
            ai, di, n = spec.split(":")
            ai, di, n = int(ai, 16), int(di, 16), int(n, 0)
            vals = []
            for idx in range(n):
                o.wr(ai, idx)
                vals.append(o.rd(di))
            out["ports"][f"{ai:02X}:{di:02X}"] = vals
            save()
            P.log(f"port {ai:02X}:{di:02X} x{n}: {bytes(vals).hex(' ')}")
        for data, idxs in sorted(a.ports.items() if allp else []):
            if f"{data:04X}" in out["ports"]:
                continue
            vals = {}
            for idx in sorted(idxs):
                for reg, b in zip(PORT_ADDR[data], idx.to_bytes(len(PORT_ADDR[data]), "big")):
                    o.wr(reg, b)
                vals[idx] = o.rd(data)
            out["ports"][f"{data:04X}"] = vals
            save()
            P.log(f"port {data:04X} x{len(vals)} read")
    finally:
        o.reset()
    P.log(f"saved {f}")
    print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
