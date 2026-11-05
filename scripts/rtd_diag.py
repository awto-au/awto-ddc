#!/usr/bin/env python3
"""Read and decode the firmware boot-stage / timing diag block (48 B at XDATA 0xF6D0) over debug slave 0x35.

usage: rtd_diag.py <bus> [--watch N | --messages | --release | --trace]
  Reads only: stage hi byte (cmd 0x01), then per byte cmd 0x3A [lo] + 1-byte read (SDK ScalerCommonDebug.c
  ScalerDebug: 0x01 -> data[2] = hi, 0x3A -> ScalerGetByte(hi << 8 | lo) into IIC data-out). Writes pass
  rtd_i2c_bridge.Real.regread_ok (staging + read cmds only). 65 transfers per block.
  The read phase is [write 0x08][read 1]; cmd 0x08 matches no dispatcher case and carries no data byte, so it never runs.
--messages: poll the SDK debug-message channel (ScalerCommonDebug.c ScalerDebugMessage), print `text = value`.
  Host sequence: write 0x55 [0x5A] (enable, reply 0xE7); status read: 0xFC none, 0xF1 message pending (fw halted until
  0x2A); write 0x25 [0x00] + read 9 = FA F5 len v3 v2 v1 v0 c1 c2; per 15-char chunk k write 0x25 [k] + read n+1 (text
  + checksum k+0x0F+sum); write 0x2A (end, reply 0xF7, releases fw); on exit write 0x2F. Only these staging/read cmds.
  --release: send 0x2A + 0x2F only; frees a firmware left halted by a killed --messages run (reads then echo one byte).
  Text starting 0x01 = token: bytes 1-2 big-endian id -> fw/msgids.tsv (id, category, file:line, text).
Block layout, little-endian (SDCC; low byte first), from fw/overlay/Project/Header/RL6449_Project.h StAwtoDiag:
  00 'A' 'D' | 02 version | 03 stage | 04..13 u16 stage ms[8] | 14 hb u16 | 16 t2 isr u16 | 18 ex1 isr u16
  | 1A ucDelay5usN | 1B u16 DelayXms(10) counts/4 | 1D u16 200x5us counts/4 | 1F RCAP2H
  | 20 u16 x1000 mov a,dir | 22 u16 x1000 movx | 24 u16 x1000 mov a,@r0 | 26 u16 x1000 empty djnz loop
  | 28 trace seq | 29 WDT_TEST (FFEB) at boot, bit7 = watchdog reset | 2A u16 trace id[3], [2] newest (--trace; ids in tmp/sdcc-port/trace_ids.tsv)
  Bench counts are raw Timer2 counts (1000 iterations, EA off); (x - empty) / 1000 = counts per instruction.
Timer2 constants (SDK ScalerCommonTimerFunction.c, 351 MHz M2PLL, flash div 4, MCU div 1, 14.318 MHz xtal):
  M2PLL: 701582 / 96 = 7308 -> reload 0xE373, 7309 counts per 1 ms tick; xtal (initial mode): 14318 / 12 = 1193
  -> reload 0xFB56, 1194 counts per tick. RCAP2H in the block selects the row.
Log: ./tmp/logs/rtd_diag.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, os, signal, struct, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_i2c_bridge as B  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402

DEV8 = 0x6A                         # 7-bit 0x35
BASE = 0xF6D0
SIZE = 48
CMD_HI, CMD_READ, READ_SUB = 0x01, 0x3A, 0x08
STAGES = ["", "BOOT (start of main)", "GPIO init done (in McuInitial)", "McuInitial done", "pin-share done",
          "main loop first pass", "panel power on", "DPTx link start", "DPTx link done"]
PERIOD = {0xE3: 7309, 0xFB: 1194}   # Timer2 counts per 1 ms tick, keyed by RCAP2H (see docstring)
NOM_XMS_MS, NOM_BUSY_US = 10, 1000  # nominal lengths of the two self-test delays
# DW8051 machine cycles per instruction: (name, cycles); djnz cost is taken from the empty loop (2-3 cycles)
BENCH = (("mov a,dir", 2), ("movx a,@dptr", 2), ("mov a,@r0", 1))
CLOCKS_PER_CYCLE = 4                # DW8051: 4 clocks per machine cycle
MCU_MHZ = {0xE3: 14.318 * 49 / 2 / 4, 0xFB: 14.318}   # expected MCU clock by RCAP2H: M2PLL 350.79 / flash div 4
IDLE_POLL_S = 0.002   # a status read is ~0.3 ms at 100 kHz; 2 ms bounds the stall added per message (fw halts until fetched)
MSG_ENABLE, MSG_FETCH, MSG_END, MSG_DONE = 0x55, 0x25, 0x2A, 0x2F
ST_NONE, ST_PENDING = 0xFC, 0xF1
LOG = None


def log(s: str) -> None:
    LOG.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n"); LOG.flush()


def read_block(io) -> bytes | None:
    return read_bytes(io, 0, SIZE)


def decode(b: bytes, be: bool = False) -> dict:
    m0, m1, ver, stage = b[0], b[1], b[2], b[3]
    ts = list(struct.unpack_from(("> " if be else "<")[0] + "8H", b, 4))
    hb, t2, ex1 = struct.unpack_from(("> " if be else "<")[0] + "3H", b, 20)
    d5, xms, busy = b[26], *struct.unpack_from(("> " if be else "<")[0] + "2H", b, 27)
    bench = list(struct.unpack_from(("> " if be else "<")[0] + "4H", b, 32)) if len(b) >= 40 else None
    return {"bench": bench, "magic_ok": (m0, m1) == (0x41, 0x44), "ver": ver, "stage": stage, "ts": ts, "hb": hb, "t2": t2,
            "ex1": ex1, "d5": d5, "xms4": xms, "busy4": busy, "rcap2h": b[31], "wdt": b[0x29]}


def report(d: dict, prev: dict | None, dt: float | None) -> str:
    L = []
    if not d["magic_ok"]:
        return f"magic not 'AD' (version {d['ver']}): firmware without the diag block, or read path failed"
    st = d["stage"]
    L.append(f"version {d['ver']}  stage {st}: {STAGES[st] if st < len(STAGES) else '?'}"
             f"  WDT_TEST at boot 0x{d['wdt']:02x}{' (WATCHDOG RESET)' if d['wdt'] & 0x80 else ''}")
    for n in range(1, 9):
        reached = n <= st or d["ts"][n - 1]
        L.append(f"  stage {n} {STAGES[n]:32s} " + (f"{d['ts'][n - 1]:6d} ms" if reached else "   not reached"))
    if prev is not None and dt:                            # u16 wrap-safe deltas
        w = lambda k: (d[k] - prev[k]) & 0xFFFF
        L.append(f"main loop {w('hb') / dt:9.1f} /s   Timer2 ISR {w('t2') / dt:7.1f} /s   EXINT1 ISR {w('ex1') / dt:7.1f} /s"
                 f"   (over {dt:.2f} s)")
    elif d["t2"]:                                          # one read: rate vs Timer2 ISR count (1 ms each)
        L.append(f"main loop {d['hb'] * 1000.0 / d['t2']:9.1f} /s   EXINT1 ISR {d['ex1'] * 1000.0 / d['t2']:7.1f} /s"
                 f"   (cumulative over {d['t2']} Timer2 ticks)")
    L.append(f"Timer2 ISR count {d['t2']}   main-loop count {d['hb']}   EXINT1 count {d['ex1']}")
    per = PERIOD.get(d["rcap2h"])
    if not d["xms4"]:
        L.append(f"self-test: not run, or ScalerTimerDelayXms(10) never returned  (5us base N={d['d5']}, RCAP2H 0x{d['rcap2h']:02X})")
    elif per is None:
        L.append(f"self-test: RCAP2H 0x{d['rcap2h']:02X} not in the constants table; raw counts "
                 f"DelayXms(10) {d['xms4'] * 4}, 200x5us {d['busy4'] * 4}")
    else:
        xms = d["xms4"] * 4 / per                          # ms
        busy = d["busy4"] * 4 / per * 1000                 # us
        L.append(f"self-test (5us base N={d['d5']}, Timer2 {per} counts/ms):")
        L.append(f"  ScalerTimerDelayXms({NOM_XMS_MS}): {xms:7.3f} ms  vs {NOM_XMS_MS} nominal  ({xms / NOM_XMS_MS * 100:5.1f} %)")
        L.append(f"  200 x 5us busy-wait:    {busy:7.1f} us  vs {NOM_BUSY_US} nominal  ({busy / NOM_BUSY_US * 100:5.1f} %)")
    if d.get("bench") and per:
        L += bench_lines(d["bench"], per, d["rcap2h"])
    return "\n".join(L)


def bench_lines(bn, per, rcap2h) -> list:
    """bn = raw Timer2 counts for 1000x direct, movx, idata, empty. Cycle rate comes from each instruction's known
    cycle count; MHz = cycles/s x clocks per cycle. djnz row assumes 3 cycles (2 if the MHz rows say 2)."""
    cnt_s = per * 1000.0                                   # Timer2 counts per second (1 tick = 1 ms)
    e = bn[3]
    L = [f"micro-bench, 1000 iterations, Timer2 {per} counts/ms (expected MCU clock {MCU_MHZ.get(rcap2h, 0):.1f} MHz):",
         f"  empty djnz loop: {e} counts = {e / 1000:.3f} counts/iter = {e / 1000 / cnt_s * 1e9:.1f} ns/iter"]
    for (name, cyc), x in zip(BENCH, bn[:3]):
        net = (x - e) / 1000.0                             # counts per instruction
        if net <= 0:
            L.append(f"  {name:13s} raw {x}: not above the empty loop (net {net:.3f} counts)")
            continue
        sec = net / cnt_s
        L.append(f"  {name:13s} raw {x}: {net:.3f} counts = {sec * 1e9:6.1f} ns -> {cyc} cycles @ {cyc * CLOCKS_PER_CYCLE / sec / 1e6:6.1f} MHz,"
                 f" or {sec * MCU_MHZ.get(rcap2h, 0) * 1e6 / CLOCKS_PER_CYCLE:.2f} cycles at the expected clock (expect {cyc})")
    sec = e / 1000.0 / cnt_s
    L.append(f"  djnz: {sec * MCU_MHZ.get(rcap2h, 0) * 1e6 / CLOCKS_PER_CYCLE:.2f} cycles at the expected clock (expect 2-3)")
    return L


def load_msgids(root: Path) -> dict:
    """fw/msgids.tsv: id (hex), category, file:line, text[, enabled]; extra columns ignored, header skipped. Missing file -> {}."""
    out = {}
    f = root / "fw/msgids.tsv"
    if f.exists():
        for line in f.read_text().splitlines():
            c = line.split("\t")
            try:
                out[int(c[0], 16)] = (c[2], c[3]) if len(c) >= 4 else (c[2] if len(c) > 2 else "", "")
            except ValueError:
                pass
    return out


def fetch_message(io):
    """One pending message -> (text bytes, value) or None. Ends with 0x2A so the firmware resumes."""
    if not io.write(DEV8, MSG_FETCH, b"\x00"):
        return None
    h = io.read(DEV8, READ_SUB, 9)
    if h is None or h[0] != 0xFA or h[1] != 0xF5:
        return None
    ln, val = h[2], bytes(h[3:7])
    text = bytearray()
    for k in range(1, (ln + 14) // 15 + 1):
        n = min(15, ln - (k - 1) * 15)
        io.write(DEV8, MSG_FETCH, bytes([k]))
        c = io.read(DEV8, READ_SUB, n + 1)
        if c is None or (k + 0x0F + sum(c[:n])) & 0xFF != c[n]:
            log(f"message chunk {k} bad checksum/short: {None if c is None else c.hex()}")
        text += c[:n] if c else b""
    io.write(DEV8, MSG_END, b"")
    if (0x0F + ln + sum(val) + sum(text)) & 0xFF != h[7]:
        log(f"message header checksum mismatch: {h.hex()} text {bytes(text).hex()}")
    return bytes(text), int.from_bytes(val, "big")


def messages(io, root: Path) -> int:
    ids = load_msgids(root)
    if not io.write(DEV8, MSG_ENABLE, b"\x5a"):
        print("enable failed (no ACK from 0x35)"); return 1
    try:
        while True:
            st = io.read(DEV8, READ_SUB, 1)
            if st is None:
                print("read failed"); return 1
            if st[0] != ST_PENDING:
                time.sleep(IDLE_POLL_S)
                continue
            m = fetch_message(io)
            if m is None:
                continue
            text, val = m
            if text[:1] == b"\x01" and len(text) >= 3:
                mid = int.from_bytes(text[1:3], "big")
                loc, txt = ids.get(mid, (None, None))
                label = f"{loc} {txt}" if loc else f"#{mid}"
            else:
                label = text.decode("latin-1")
            line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {label} = {val}"
            print(line, flush=True); log(line)
    except KeyboardInterrupt:
        return 0
    finally:
        io.write(DEV8, MSG_END, b""); io.write(DEV8, MSG_DONE, b"")   # 0x2A too: killed mid-message leaves fw halted


TRACE_OFF = 0x28                    # ucTraceSeq, ucSpare, usTrace[3] (RL6449_Project.h StAwtoDiag)
TRACE_DEAD = 20                     # consecutive failed reads = chip gone (~20 x 2 transfers, well past any ISR latency)


def read_bytes(io, off: int, n: int) -> bytes | None:
    if not io.write(DEV8, CMD_HI, bytes([(BASE + off) >> 8])):
        return None
    out = bytearray()
    for i in range(n):
        if not io.write(DEV8, CMD_READ, bytes([(BASE + off + i) & 0xFF])):
            return None
        r = io.read(DEV8, READ_SUB, 1)
        if r is None:
            return None
        out.append(r[0])
    return bytes(out)


def trace(io, root: Path, be: bool, ids: str | None) -> int:
    """Poll the function-entry trace ring until Ctrl-C or TRACE_DEAD failed reads; print each new entry."""
    names = {}
    f = Path(ids) if ids else root / "tmp/sdcc-port/trace_ids.tsv"
    if f.exists():
        for line in f.read_text().splitlines():
            i, path, fn = line.split("\t")
            names[int(i, 16)] = f"{fn} ({Path(path).name})"
    last, fails, n = None, 0, 0
    try:
        while True:
            b = read_bytes(io, TRACE_OFF, 8)
            if b is None:
                if n == 0:
                    continue                    # not up yet (rebooting / ISP): only count fails after a good read
                fails += 1
                if fails == 1:
                    log(f"trace read failed after {n} reads; last ring {last}")
                if fails >= TRACE_DEAD:
                    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} chip stopped answering ({fails} failed reads); last ring: {last}"
                    print(line, flush=True); log(line); return 1
                continue
            fails, n = 0, n + 1
            seq, ids = b[0], struct.unpack_from((">" if be else "<") + "3H", b, 2)
            ring = (seq, tuple(names.get(i, f"#{i:04X}") for i in ids))
            if ring != last:
                line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} seq {seq:3d}  " + " > ".join(ring[1])
                print(line, flush=True); log(line)
                last = ring
    except KeyboardInterrupt:
        return 0


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    # 1 s: block read is ~65 short transfers (tens of ms); 1 s keeps rates well above one read's noise
    ap.add_argument("--watch", type=float, metavar="N", help="re-read every N seconds (Ctrl-C to stop)")
    ap.add_argument("--messages", action="store_true", help="poll the debug-message channel")
    ap.add_argument("--release", action="store_true", help="send end (0x2A) + stop (0x2F) to un-halt the firmware")
    ap.add_argument("--trace", action="store_true", help="poll the function-entry trace ring (fw/trace_files.txt)")
    ap.add_argument("--ids", help="trace id TSV of the flashed image (default tmp/sdcc-port/trace_ids.tsv)")
    ap.add_argument("--be", action="store_true", default=os.environ.get("AWTO_SDCC_BE") == "1",
                    help="block written by a --big-endian build (u16 MSB first); default from $AWTO_SDCC_BE")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp/logs/rtd_diag.log").open("a")
    B.log = lambda s: LOG.write(f"{time.strftime('%H:%M:%S')} {s}\n")      # bridge logs to file only
    io = B.Real(a.bus, allow_write=False, regread=True)
    if a.release:
        ok = io.write(DEV8, MSG_END, b"") and io.write(DEV8, MSG_DONE, b"")
        print("released" if ok else "release: no ACK from 0x35"); return 0 if ok else 1
    if a.messages:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # run the finally (0x2F) when killed
        return messages(io, root)
    if a.trace:
        return trace(io, root, a.be, a.ids)
    prev, tprev = None, None
    while True:
        t = time.monotonic()
        blk = read_block(io)
        if blk is None:
            print("read failed (no ACK from 0x35: debug slave off, or ISP mode); see tmp/logs/rtd_diag.log")
            return 1
        log(f"bus {a.bus} block {blk.hex()}")
        d = decode(blk, a.be)
        txt = report(d, prev, (t - tprev) if tprev else None)
        print(f"--- {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n{txt}", flush=True)
        log(txt)
        prev, tprev = d, t
        if not a.watch:
            return 0
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
