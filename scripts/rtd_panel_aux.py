#!/usr/bin/env python3
"""Read the panel's DPCD + EDID through the scaler's DPTX TX1 AUX MAC (MCU halted, then reset). Panel identity (#3).

usage: rtd_panel_aux.py <bus> --serial AWT2611000N [--edid-blocks 2]
  Writes only AUX MAC registers on page 9D, the page-select (0x9F) and the final reset (0xEE).
  On the wire: native AUX reads of DPCD 0x000..0x00F and 0x400..0x40B, then I2C-over-AUX at 0x50 (EDID);
  the only write on the panel side is the EDID offset byte (standard EDID read). Never writes DPCD.
  Out: tmp/regs/<serial>-panel-aux-<YYYYMMDD-HHMMSS>.json + .edid.bin; sanity: DPCD 0x002[4:0] lanes, 0x001 link rate.
  Regs (regdb RTD2795T-CG, page 9D): A3 tran ctrl, A4 cmd|addr[19:16], A5/A6 addr, A7 len, A8 tx data,
  A9 reply cmd|len, AA reply data, AB fifo ctrl, AC fifo status.
Log: ./tmp/logs/rtd_panel_aux.log
"""
import argparse, json, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import Osd

CTRL, CMD, ADDR_M, ADDR_L, LEN, TXD, RCMD, RDATA, FIFO, FSTAT, FSM = (0x9D00 + x for x in
                                                                     (0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xA2))
NATIVE_RD, I2C_WR_MOT, I2C_RD_MOT, I2C_RD = 0x9, 0x4, 0x5, 0x1
# Completion: AUX timeout ~0.4 ms (27 MHz x 21 x 512) x (1 + retry 7) = ~3.2 ms worst case in hardware;
# each ISP read is ~1 ms, so 20 polls (~20 ms) is >5x the hardware bound. On expiry: abort with op/limit/elapsed.
POLL_MAX = 20


class AuxError(RuntimeError):
    pass


def xfer(o: Osd, cmd: int, addr: int, n: int, data: bytes = b"") -> bytes:
    """One AUX transaction. n = bytes requested (read) or len(data) (write); length field = n-1 (unverified, checked via reply)."""
    o.wr(FIFO, o.rd(FIFO) | 0x03)                                   # reset I2C + native FIFOs (write-1-to-clear)
    o.wr(CMD, (cmd << 4) | ((addr >> 16) & 0xF))
    o.wr(ADDR_M, (addr >> 8) & 0xFF)
    o.wr(ADDR_L, addr & 0xFF)
    o.wr(LEN, (n - 1) & 0xF)
    for b in data:
        o.wr(TXD, b)
    o.wr(CTRL, o.rd(CTRL) | 0x01)                                   # tx_start, hardware clears when finished
    t0 = time.monotonic()
    for _ in range(POLL_MAX):
        if not (o.rd(CTRL) & 1) and not (o.rd(FSM) & 0x10):
            break
    else:
        raise AuxError(f"AUX cmd={cmd:#x} addr={addr:#x} did not finish in {POLL_MAX} polls ({time.monotonic()-t0:.3f}s)")
    rc = o.rd(RCMD)
    reply, rlen = rc >> 4, rc & 0xF
    if cmd in (NATIVE_RD, I2C_RD_MOT, I2C_RD):
        out = bytes(o.rd(RDATA) for _ in range(n))
    else:
        out = b""
    P.log(f"aux cmd={cmd:#x} addr={addr:#07x} n={n} -> reply={reply:#x} rlen={rlen} data={out.hex(' ')}")
    if reply != 0:
        raise AuxError(f"AUX cmd={cmd:#x} addr={addr:#x}: reply {reply:#x} (0=ACK, 1=NACK, 2=DEFER) fsm={o.rd(FSM):#04x}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--edid-blocks", type=int, default=2)
    a = ap.parse_args()
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (root / "tmp/regs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp/logs/rtd_panel_aux.log").open("a")
    P.log(f"=== panel aux bus={a.bus} serial={a.serial} ===")
    res = {"serial": a.serial, "time": isostamp.now()}
    base = root / "tmp/regs" / f"{a.serial}-panel-aux-{time.strftime('%Y%m%d-%H%M%S')}"
    o = Osd(a.bus)
    o.enter()
    try:
        P.log(f"AUX_TX_CTRL(9DA0)={o.rd(0x9DA0):#04x} TRAN_CTRL(9DA3)={o.rd(CTRL):#04x}")
        res["dpcd_000"] = xfer(o, NATIVE_RD, 0x000, 16).hex()
        d = bytes.fromhex(res["dpcd_000"])
        res["dpcd_rev"], res["max_link_rate_code"], res["max_lanes"] = f"{d[0]:#04x}", f"{d[1]:#04x}", d[2] & 0x1F
        P.log(f"DPCD rev={res['dpcd_rev']} max_link_rate={res['max_link_rate_code']} (0x14=HBR2) lanes={res['max_lanes']}")
        res["dpcd_400_sink_oui_devid"] = xfer(o, NATIVE_RD, 0x400, 12).hex()
        b = bytes.fromhex(res["dpcd_400_sink_oui_devid"])
        P.log(f"sink OUI={b[:3].hex()} device-id={b[3:9]!r} hw/fw rev={b[9:12].hex()}")
        edid = bytearray()
        xfer(o, I2C_WR_MOT, 0x50, 1, b"\x00")                       # EDID offset 0
        for off in range(0, 128 * a.edid_blocks, 16):
            last = off + 16 >= 128 * a.edid_blocks
            edid += xfer(o, I2C_RD if last else I2C_RD_MOT, 0x50, 16)
        res["edid"] = bytes(edid).hex()
        Path(str(base) + ".edid.bin").write_bytes(bytes(edid))
    except AuxError as e:
        res["error"] = str(e)
        P.log(f"ERROR {e}")
    finally:
        o.reset()
        Path(str(base) + ".json").write_text(json.dumps(res, indent=1))
    P.log(f"saved {base}.json")
    print(f"{base}.json")
    return 1 if "error" in res else 0


if __name__ == "__main__":
    sys.exit(main())
