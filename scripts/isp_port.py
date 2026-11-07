#!/usr/bin/env python3
"""Which input port is active, read over ISP 0x4A (works where debug slave 0x35 does not, #28). Optional tech panel.

usage: isp_port.py <bus> --serial AWT2611000N [--map tmp/fw/<tag>.map] [--tag TEXT] [--draw] [--reset]
  default  enter ISP (MCU halted), read, reset the scaler (~1 s blink).
  --draw   also draw a panel with the result (rtd_tech_osd draw path); MCU stays HALTED, OSD up until a
           later run with --draw --reset (EDID may read silent while
           halted: pass --identity). No --reset given with --draw = left up.
  --reset  with --draw: skip reading/drawing, just reset (clears a panel left up).
Reads (hardware, no firmware dependency):
- HDMI Rx2 (D2) = page 0x71, Rx3 (D3) = page 0x72 (SDK RL6449_Series_TMDSRx2/3.c): SCDC 0x20 (TMDS config the
  host writes: bit1 clock ratio 1/40, bit0 scrambling, set for > 340 MHz) and 0x21 bit0 scrambling status, via
  index port P7x_39 / data P7x_3A; FREQDET_CTRL P7x_E6 (bit6 done, bit2 unstable), RESULT P7x_ED/EE.
- FF22 IIC_CH_SEL[2:0] = DDC channel of the DDC-CI / debug IIC engine (0 ADC, 1 DDC0, 2 DDC1, 3 DDC2, 4 DDC3).
Reads (firmware RAM, needs the flashed image's --map): g_ucSearchIndex, g_pucSourceSearchPriority[] -> port
(SDK SysSourceGetInputPort: port = priority[index]; 4 = D1, 5 = D2, 6 = D3), g_pstSourceInfo[] raw bytes.
Log: ./tmp/logs/isp_port.log
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_isp_probe as P
import rtd_proto
import rtd_tech_osd as T

PORTS = {3: "D0", 4: "D1 (DP)", 5: "D2 (HDMI)", 6: "D3 (HDMI)", 10: "NONE"}
CH = {0: "ADC", 1: "DDC0", 2: "DDC1", 3: "DDC2", 4: "DDC3"}
RX = {"D2": 0x71, "D3": 0x72}


def map_syms(path: Path, names) -> dict:
    out = {}
    for m in re.finditer(r"^D:\s+([0-9A-F]{8})\s+_(\w+)\s", path.read_text(errors="replace"), re.M):
        if m.group(2) in names:
            out[m.group(2)] = int(m.group(1), 16)
    return out


def read_rx(o, page: int) -> dict:
    r = {}
    for idx in (0x20, 0x21):
        o.wr(page << 8 | 0x39, idx)
        r[f"scdc{idx:02x}"] = o.rd(page << 8 | 0x3A)
    r["fdet"] = o.rd(page << 8 | 0xE6)
    r["fres"] = (o.rd(page << 8 | 0xF7) << 16) | (o.rd(page << 8 | 0xED) << 8) | o.rd(page << 8 | 0xEE)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--identity", help="how the bus was proven when the EDID is silent (MCU halted by a --draw)")
    a = ap.parse_args()
    (P.repo_root() / "tmp/logs").mkdir(parents=True, exist_ok=True)
    P.LOG = rtd_proto.setup_logs("isp_port").main
    i2cbus.require_unit(a.bus, a.serial, a.identity)
    t = T.TechOsd(a.bus)
    if a.draw and a.reset:
        P.log(f"=== isp_port bus={a.bus} {a.serial}: reset only (clear panel) ===")
        t.enter(); t.reset()
        return 0
    syms = map_syms(Path(a.map), {"g_ucSearchIndex", "g_pucSourceSearchPriority", "g_pstSourceInfo"}) if a.map else {}
    P.log(f"=== isp_port bus={a.bus} {a.serial} map={a.map or '-'} syms={ {k: hex(v) for k, v in syms.items()} } ===")
    t.enter()
    keep = False
    try:
        o = t.o
        ch = o.rd(0xFF22) & 7
        slave = o.rd(0xFF23)
        rx = {k: read_rx(o, p) for k, p in RX.items()}
        fw_port = None
        if len(syms) == 3:
            si = o.rd(syms["g_ucSearchIndex"])
            prio = [o.rd(syms["g_pucSourceSearchPriority"] + i) for i in range(4)]
            src = [o.rd(syms["g_pstSourceInfo"] + i) for i in range(4)]
            fw_port = prio[si] if si < len(prio) else None
            P.log(f"fw: search index {si}, priority {prio}, source info {[hex(v) for v in src]} -> port "
                  f"{fw_port} = {PORTS.get(fw_port, '?')}")
        for k, r in rx.items():
            P.log(f"{k}: SCDC20=0x{r['scdc20']:02x} SCDC21=0x{r['scdc21']:02x} FREQDET_CTRL=0x{r['fdet']:02x} "
                  f"RESULT=0x{r['fres']:06x}")
        P.log(f"IIC engine: FF22 ch_sel {ch} = {CH.get(ch, '?')}, FF23 slave 0x{slave:02x} (7-bit 0x{slave >> 1:02x})")
        hw = [k for k, r in rx.items() if r["scdc21"] & 1 or r["scdc20"] & 3]
        verdict = f"ACTIVE PORT (HW SCDC): {' + '.join(hw) if hw else 'NONE SCRAMBLED'}"
        P.log(verdict)
        if a.draw:
            L = [("h", "AWTO PORT CHECK (ISP)"),
                 ("kv", f"UNIT|{a.serial}"),
                 ("kv", f"FIRMWARE|{a.tag.upper() or '?'}"),
                 ("kv", f"HW ACTIVE|{' + '.join(hw) if hw else 'NONE'} (SCDC SCRAMBLE)"),
                 ("kv", f"FW PORT|{PORTS.get(fw_port, '?')}"),
                 ("kv", f"DEBUG IIC|{CH.get(ch, '?')} SLAVE 0X{slave >> 1:02X}")]
            for k, r in rx.items():
                L.append(("kv", f"{k} SCDC 20/21|0X{r['scdc20']:02X} / 0X{r['scdc21']:02X}"))
            L.append(("h", "CHECK"))
            L.append(("t", "WHICH HDMI SOCKET IS THE CABLE IN?"))
            L.append(("t", "MCU HALTED: PANEL STAYS UNTIL RESET"))
            rows = T.render_rows(L)
            t.setup(rows, 1, (3840, 2160))
            keep = True
            P.log("panel drawn; MCU halted, OSD up until `isp_port.py ... --draw --reset`")
    finally:
        if not keep:
            t.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
