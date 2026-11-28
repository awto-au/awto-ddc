#!/usr/bin/env python3
"""Read-only DDC/CI vendor-identity read of the Philips 288E2: scaler name, BOM, firmware version, factory selectors (#383, #384).

Authorised by Dan 2026-11-28: READ-ONLY on his own 288E2 (firmware-compatibility RE).
- Sends only Get-form frames (opcode 0x01) to 0x37. NEVER a Set (0x03), ISP 0x49, SERDB 0x59 or 0x4A.
- Bus: Intel i915 gmbus only, proven by EDID serial UK52307000611. NVIDIA is never used (it ACKs every address, #381).
- Pace: >= GAP_S between transactions (TPV drops faster traffic, #381). Reply read REPLY_WAIT_S after the request.

Frames: the exact 9-byte frames SmartControl 7.2.0 sends, recovered from Zeasn.Monitor.Lib.dll field blobs
(`6E 51 86 01 FE E1 ..`; payload after 0x51/len = `01 FE E1 ..`). All are opcode 0x01 (Get). Reads only.
- Version      01 FE E1 E6 06 00        reply ASCII string (confirmed "V1.02" on the wire)
- ScalerName   01 FE E1 E8 00 00
- BOM / panel / AI are among 01 FE E1 {A7 07 00, A1 01 00, A1 01 01, A1 01 02, E6 35 01, E6 1D 00}, 01 FE E9 0D 00 00
  (which is which is decided on the wire by the reply shape; BOM = byte[4] 'P'/'A', ~17 ASCII chars per the app parser).
- Factory read 01 FE EF <sel> 00 <len>   reply <len> raw bytes, no opcode byte; selectors 00-07, 10-14 (#384)

Output: tmp/logs/philips_bom.log and /vendors/philips/288E2/analysis/bom.md (ASCII + hex per read).

Pacing uses time.sleep for the DDC/CI inter-frame gap and the reply delay: that is MCCS protocol spacing
(a fixed minimum between transactions), the same mechanism unit_ops.DdcSession uses, not an event-wait.
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import reference_mon as R
import unit_ops as U

SERIAL = "UK52307000611"
ADDR = 0x37
GAP_S = 0.110            # >= 110 ms between DDC/CI transactions: TPV drops faster traffic (#381, prior work paces 110-120 ms)
REPLY_WAIT_S = 0.040     # MCCS: a Get reply is ready >= 40 ms after the request (unit_ops GET_WAIT_S; ddcutil waits the same)

# (label, *data-after-opcode) ; opcode 0x01 (Get) is prepended by ddcci_frame. All reads.
# The exact frames SmartControl sends (Zeasn.Monitor.Lib.dll blobs). Named frames first, then the identity group to classify.
IDENT = [
    ("Version",      0xFE, 0xE1, 0xE6, 0x06, 0x00),   # confirmed "V1.02"
    ("ScalerName",   0xFE, 0xE1, 0xE8, 0x00, 0x00),
    ("FE E1 A7 07 00", 0xFE, 0xE1, 0xA7, 0x07, 0x00),
    ("FE E1 A1 01 00", 0xFE, 0xE1, 0xA1, 0x01, 0x00),
    ("FE E1 A1 01 01", 0xFE, 0xE1, 0xA1, 0x01, 0x01),
    ("FE E1 A1 01 02", 0xFE, 0xE1, 0xA1, 0x01, 0x02),
    ("FE E1 E6 35 01", 0xFE, 0xE1, 0xE6, 0x35, 0x01),
    ("FE E1 E6 1D 00", 0xFE, 0xE1, 0xE6, 0x1D, 0x00),
    ("FE E9 0D 00 00", 0xFE, 0xE9, 0x0D, 0x00, 0x00),
]
# BOM is whichever of the above returns a BOM-shaped ASCII string (app parser: byte[4] 'P'/'A', ~17 chars).

FACTORY_SELECTORS = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x10, 0x11, 0x12, 0x13, 0x14]
FACTORY_LEN = 0x20       # the app reads len 0x20; reply is <len> bytes, no opcode byte. Frame: 01 FE EF <sel> 00 <len>.
SELECTOR_HINT = {0x13: "factory serial (EDID serial, #381; confirmed on the wire)"}


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class Log:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("a")

    def say(self, msg: str) -> None:
        line = f"{now()} {msg}"
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()

    def close(self) -> None:
        self.fh.close()


def find_bus() -> int:
    """Intel bus carrying the Philips EDID serial; NVIDIA is never used (reference_mon.find_bus enforces both)."""
    return R.find_bus(R.load()["philips"])


def ascii_of(buf: bytes) -> str:
    return "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in buf)


def read_frame(bus: i2cbus.Bus, clock, nap, state: dict, payload: tuple[int, ...]) -> bytes:
    """Send one Get-form frame (opcode 0x01 + payload) to 0x37, wait, read the reply. Read-only.
    Length-aware read: 2-byte header 6E <0x80|len>, then <len>+1 (body + checksum). Over-reading past the
    scaler's queued reply desyncs its reply FIFO (replies shift on the next read), so we read only what it sent.
    state['last'] holds the last-transaction time for GAP_S pacing."""
    last = state.get("last")
    if last is not None:
        wait = GAP_S - (clock() - last)
        if wait > 0:
            nap(wait)
    frame = U.ddcci_frame(U.OP_GET, *payload)          # opcode 0x01: a Get; never OP_SET
    assert frame[2] == U.OP_GET, "refusing: non-Get opcode"
    bus.raw_write(ADDR, frame)
    nap(REPLY_WAIT_S)
    try:
        hdr = bus.raw_read(ADDR, 2)
        if len(hdr) == 2 and hdr[0] == 0x6E:
            n = hdr[1] & 0x7F
            rep = hdr + bus.raw_read(ADDR, n + 1)      # body (n) + checksum (1); read exactly what it queued
        else:                                          # bad header = the responder is mid-stream/desynced.
            rep = hdr                                  # do NOT read more (over-reading is what desyncs it); flag + pace
            state["desync"] = True
    except OSError as e:
        rep = b""
        state["err"] = str(e)
    state["last"] = clock()
    return rep


def body_of(rep: bytes) -> bytes:
    """The DDC/CI reply body: 6E <0x80|len> <len bytes> <chk>, then a stale over-read tail we drop.
    Returns the <len bytes> (header 6E + len byte removed, checksum and tail removed)."""
    if len(rep) < 3 or rep[0] != 0x6E:
        return b""
    n = rep[1] & 0x7F
    if 2 + n + 1 > len(rep):
        return rep[2:]
    return rep[2:2 + n]


def decode_vendor_string(rep: bytes) -> tuple[str, str]:
    """Vendor string reply: body = 02 <echo 2-3 bytes> <ascii...>. Report the full body ascii + hex;
    the leading 02 + echo shows as '.' in ascii, the string follows."""
    body = body_of(rep)
    return ascii_of(body), body.hex(" ")


def decode_factory(rep: bytes) -> tuple[str, str]:
    """Factory read reply: body = <len bytes>, no opcode byte (#381)."""
    body = body_of(rep)
    return ascii_of(body), body.hex(" ")


def looks_like_bom(body: bytes) -> bool:
    """SmartControl's BOM parser: a run of printable ASCII, >= 8 chars, with byte[4] 'P' or 'A'.
    The reply body starts 02 <echo>; the string sits after it. Scan for the printable run."""
    # longest printable run in the body
    best = b""
    cur = b""
    for b in body:
        if 0x20 <= b < 0x7F:
            cur += bytes([b])
            if len(cur) > len(best):
                best = cur
        else:
            cur = b""
    return len(best) >= 8 and (len(best) <= 4 or best[4:5] in (b"P", b"A"))


def run(log: Log, md: list[str], clock=time.monotonic, nap=time.sleep) -> dict:
    bus_no = find_bus()
    log.say(f"bus /dev/i2c-{bus_no} ({i2cbus.adapter_name(bus_no)!r}), EDID serial {SERIAL} proven")
    md.append(f"- Bus: Intel `/dev/i2c-{bus_no}` ({i2cbus.adapter_name(bus_no)}), EDID serial {SERIAL}, {now()}")
    out: dict = {}
    state: dict = {}
    bus = i2cbus.Bus(bus_no)
    try:
        # 1. Identity frames (the exact SmartControl frames); classify BOM from the reply shape
        md.append("\n## Vendor identity frames (01 ...) ")
        bom_hits = []
        for label, *payload in IDENT:
            rep = read_frame(bus, clock, nap, state, tuple(payload))
            body = body_of(rep)
            txt, hexs = decode_vendor_string(rep)
            fr = " ".join(f"{b:02X}" for b in (U.OP_GET, *payload))
            is_bom = looks_like_bom(body)
            log.say(f"{label}: req 01 {fr}  rep {rep.hex(' ')}  -> body ascii {txt!r}{'  <-- BOM-shaped' if is_bom else ''}")
            md.append(f"\n### {label}\n- Frame: `01 {fr}`\n- Body ASCII: `{txt}`\n- Body hex: `{hexs}`"
                      f"\n- Raw reply: `{rep.hex(' ')}`" + ("\n- Classified: BOM-shaped (byte[4] P/A, >=8 ASCII)" if is_bom else ""))
            out[label] = {"ascii": txt, "hex": hexs, "bom_shaped": is_bom}
            if is_bom:
                bom_hits.append((label, txt, body))
        if bom_hits:
            # BOM string = the printable run in the body
            run_s = max((bytes(c for c in b if 0x20 <= c < 0x7F) for _l, _t, b in bom_hits), key=len)
            bom = ascii_of(run_s)
            out["BOM"] = bom
            out["BOM_frame"] = bom_hits[0][0]
            log.say(f"BOM = {bom!r} (frame {bom_hits[0][0]})")
            md.append(f"\n## BOM = `{bom}` (frame `01 {bom_hits[0][0]}`)")
        else:
            log.say("BOM: no identity frame returned a BOM-shaped string")

        # 2. Factory read selectors (#384): frame 01 FE EF <sel> 00 <len>
        log.say("factory selectors FE EF (read-only):")
        md.append("\n## Factory selectors (01 FE EF <sel> 00 20)")
        factory = {}
        for sel in FACTORY_SELECTORS:
            rep = read_frame(bus, clock, nap, state, (0xFE, 0xEF, sel, 0x00, FACTORY_LEN))
            txt, hexs = decode_factory(rep)
            hint = SELECTOR_HINT.get(sel, "")
            log.say(f"  sel {sel:02X}{(' ('+hint+')') if hint else ''}: rep {rep.hex(' ')}  ascii {txt!r}")
            md.append(f"- sel `{sel:02X}`{(' ('+hint+')') if hint else ''}: ascii `{txt}` | hex `{hexs}`")
            factory[f"{sel:02X}"] = {"ascii": txt, "hex": hexs}
        out["factory"] = factory
    finally:
        bus.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="repo root (else $AWTO_DDC_REPO / file-relative)")
    a = ap.parse_args()
    root = Path(a.repo) if a.repo else i2cbus.ROOT
    log = Log(root / "tmp/logs/philips_bom.log")
    log.say("=== philips_bom: read-only vendor-identity + factory read of the Philips 288E2 (#383, #384)")
    md = [f"# Philips 288E2 vendor identity (DDC/CI reads, {now()})",
          "Read-only over Intel HDMI DDC (i915 gmbus), EDID serial UK52307000611. Frames: SmartControl 7.2.0 RE (#381).",
          "No Set / ISP / SERDB. Vendor firmware identity: this file lives in the vendor store, not the repo."]
    try:
        run(log, md)
    except SystemExit as e:
        log.say(f"STOP: {e}")
        log.close()
        raise
    bom_md = Path("/vendors/philips/288E2/analysis/bom.md")
    bom_md.parent.mkdir(parents=True, exist_ok=True)
    bom_md.write_text("\n".join(md) + "\n")
    log.say(f"wrote {bom_md}")
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
