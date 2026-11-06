#!/usr/bin/env python3
"""Read and decode the firmware boot-stage / timing diag block (48 B at XDATA 0xF6D0) over debug slave 0x35.

usage: rtd_diag.py <bus> [--watch N | --messages [--secs S] | --release | --trace]
  Reads only: stage hi byte (cmd 0x01), then per byte cmd 0x3A [lo] + 1-byte read (SDK ScalerCommonDebug.c
  ScalerDebug: 0x01 -> data[2] = hi, 0x3A -> ScalerGetByte(hi << 8 | lo) into IIC data-out). Writes pass
  rtd_i2c_bridge.Real.regread_ok (staging + read cmds only). 65 transfers per block.
  The read phase is [write 0x08][read 1]; cmd 0x08 matches no dispatcher case and carries no data byte, so it never runs.
--messages: runs at most --secs (default 60); SIGINT/SIGTERM/SIGHUP/expiry/any error end with a retried 0x2A + 0x2F release.
  Poll the SDK debug-message channel (ScalerCommonDebug.c ScalerDebugMessage), print `text = value`.
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
Log: ./tmp/logs/rtd_diag.log (decoded), ./tmp/logs/rtd_diag.raw.log (I2C trace). Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, os, signal, struct, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
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


RELEASE_TRIES = 5                   # per command: a transfer is ~0.3 ms; 5 tries cover an i915 GMBUS timeout burst (~10 ms apart)
RELEASE_GAP_S = 0.01                # lets the adapter fall back out of bit-bang between tries


def _send(io, cmd: int) -> bool:
    for n in range(1, RELEASE_TRIES + 1):
        if io.write(DEV8, cmd, b""):
            return True
        log(f"release: cmd 0x{cmd:02X} no ACK, try {n}/{RELEASE_TRIES}")
        time.sleep(RELEASE_GAP_S)
    return False


def _release(io, done: bool = True) -> bool:
    """0x2A (end message: fw resumes) then, if `done`, 0x2F (stop). Retried; a firmware left halted wedges the unit (#37),
    so every exit path of --messages ends here. False + a log line when it never ACKed."""
    ok = _send(io, MSG_END)
    if done:
        ok = _send(io, MSG_DONE) and ok
    if not ok:
        log("release FAILED: firmware may be left halted; ./dev.py diag --release, else power-cycle + flash")
    return ok


def fetch_message(io):
    """One pending message -> (text bytes, value) or None. Always ends with 0x2A (retried) so the firmware resumes."""
    try:
        return _fetch_message(io)
    finally:
        _release(io, done=False)


def _fetch_message(io):
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
    if (0x0F + ln + sum(val) + sum(text)) & 0xFF != h[7]:
        log(f"message header checksum mismatch: {h.hex()} text {bytes(text).hex()}")
    return bytes(text), int.from_bytes(val, "big")


MSG_SECS = 60.0     # default --messages run length: an interactive look, not a daemon; expiry = clean release, rc 0


def messages(io, root: Path, secs: float | None = MSG_SECS) -> int:
    ids = load_msgids(root)
    if not io.write(DEV8, MSG_ENABLE, b"\x5a"):
        print("enable failed (no ACK from 0x35)"); return 1
    t0 = time.monotonic()
    try:
        while secs is None or time.monotonic() - t0 < secs:
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
        log(f"messages: --secs {secs:g} reached")
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        _release(io)                          # every exit path: a halted firmware wedges the unit (#37)


TRACE_OFF = 0x28                    # ucTraceSeq, ucSpare, usTrace[3] (RL6449_Project.h StAwtoDiag)
TRACE_DEAD = 20                     # consecutive failed reads = chip gone (~20 x 2 transfers, well past any ISR latency)


_BLOCK = None                       # firmware answers the 0x3C block read (diag version >= 2), probed once per run


def read_bytes(io, off: int, n: int) -> bytes | None:
    global _BLOCK
    if _BLOCK is None:
        _BLOCK = X.probe(io, BASE)
        if _BLOCK is None:
            return None
    return X.read(io, BASE + off, n, _BLOCK)


SAFE = 0xF6B0                       # StAwtoSafe, 32 B (RL6449_Project.h): survives a warm reset
SAFE_HOLD, SAFE_MARKER = 0xA55A, 0x5AFE
# --hold follows a relay power-on that dev.py has already verified: scaler answers 0x35 ~1-2 s after power and the safe
# window ends 2 s later (_AWTO_SAFE_BOOT_MS). 5 s = 2.5x the window; expiry: "hold: no ACK", rc 1 (flash goes on over ISP).
HOLD_WAIT_S = 5.0
HOLD_POLL_S = 0.05                  # 40 tries inside the 2 s safe window (_AWTO_SAFE_BOOT_MS)


def read_safe(io, be: bool) -> dict | None:
    b = read_bytes(io, SAFE - BASE, 32)
    if b is None:
        return None
    e = ">" if be else "<"
    hold, marker = struct.unpack_from(e + "2H", b, 0)
    return {"hold": hold, "marker": marker, "flags": b[4], "prev_seq": b[5],
            "prev_trace": struct.unpack_from(e + "3H", b, 6), "prev_last": struct.unpack_from(e + "H", b, 12)[0],
            "last": struct.unpack_from(e + "H", b, 14)[0], "max": struct.unpack_from(e + "H", b, 16)[0],
            "prev_max": struct.unpack_from(e + "H", b, 18)[0], "wdt": b[20], "key_rst": b[21], "prev_key_rst": b[22],
            "bus_resets": b[27], "prev_bus_resets": b[28]}


def safe_report(s: dict, names: dict) -> str:
    warm = s["flags"] & 2
    L = [f"hold 0x{s['hold']:04x}{' (HELD in safe mode)' if s['hold'] == SAFE_HOLD else ''}  "
         f"in safe window: {'yes' if s['flags'] & 1 else 'no'}  marker {'ok' if s['marker'] == SAFE_MARKER else 'BAD'}",
         f"this boot: longest main-loop pass {s['max']} ms, last pass at {s['last']} ms; WDT_TEST at boot 0x{s['wdt']:02x}",
         f"bus-watchdog releases this boot: {s['bus_resets']}",
         f"last reset: {'WARM (WDT, power-key hold or ISP 0xEE)' if warm else 'power-on'}"]
    if warm:
        L.append(f"previous boot: {'ENDED BY POWER-KEY RESET, ' if s['prev_key_rst'] else ''}bus releases {s['prev_bus_resets']}, "
                 f"last pass at {s['prev_last']} ms, longest pass {s['prev_max']} ms, trace seq {s['prev_seq']}: "
                 + " > ".join(names.get(i, f"#{i:04X}") for i in s["prev_trace"]))
    return "\n".join(L)


def set_hold(w, value: int, be: bool) -> bool:
    """usHold at SAFE via debug cmds 0x01 [hi] (stage), 0x03 [val] (stage), 0x3B [lo] -> ScalerSetByte. Only this write.
    `w` = one open B.Real(allow_write=True), reused across tries (a new fd per 50 ms try hit EMFILE, #52.1)."""
    for off, val in ((0, value >> 8), (1, value & 0xFF)) if be else ((0, value & 0xFF), (1, value >> 8)):
        if not (w.write(DEV8, 0x01, bytes([SAFE >> 8])) and w.write(DEV8, 0x03, bytes([val]))
                and w.write(DEV8, 0x3B, bytes([(SAFE + off) & 0xFF]))):
            return False
    return True


def load_trace_names(root: Path, ids: str | None) -> dict:
    names = {}
    f = Path(ids) if ids else root / "tmp/sdcc-port/trace_ids.tsv"
    if f.exists():
        for line in f.read_text().splitlines():
            i, path, fn = line.split("\t")
            names[int(i, 16)] = f"{fn} ({Path(path).name})"
    return names


def trace(io, root: Path, be: bool, ids: str | None) -> int:
    """Poll the function-entry trace ring until Ctrl-C or TRACE_DEAD failed reads; print each new entry."""
    names = load_trace_names(root, ids)
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


IO = None                           # the read handle of this run, closed by main()


def main() -> int:
    try:
        return _main()
    finally:
        if IO is not None:
            IO.close()


def _main() -> int:
    global LOG, IO
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    # 1 s: block read is ~65 short transfers (tens of ms); 1 s keeps rates well above one read's noise
    ap.add_argument("--watch", type=float, metavar="N", help="re-read every N seconds (Ctrl-C to stop)")
    ap.add_argument("--messages", action="store_true", help="poll the debug-message channel")
    ap.add_argument("--release", action="store_true", help="send end (0x2A) + stop (0x2F), retried, to un-halt the firmware")
    ap.add_argument("--secs", type=float, default=MSG_SECS, metavar="S",
                    help=f"--messages stops after S seconds (default {MSG_SECS:g}; 0 = until interrupted)")
    ap.add_argument("--trace", action="store_true", help="poll the function-entry trace ring (fw/trace_files.txt)")
    ap.add_argument("--ids", help="trace id TSV of the flashed image (default tmp/sdcc-port/trace_ids.tsv)")
    ap.add_argument("--safe", action="store_true", help="read the safe-boot/WDT-canary block (0xF6B0)")
    ap.add_argument("--hold", action="store_true",
                    help="poll until the fw answers, then hold it in the safe window (no inputs/display)")
    ap.add_argument("--hold-wait", type=float, default=HOLD_WAIT_S, metavar="S",
                    help=f"--hold gives up after S seconds (default {HOLD_WAIT_S:g}: 2.5x the 2 s safe window)")
    ap.add_argument("--unhold", action="store_true", help="release the safe-window hold (fw continues booting)")
    ap.add_argument("--be", action="store_true", default=os.environ.get("AWTO_SDCC_BE") == "1",
                    help="block written by a --big-endian build (u16 MSB first); default from $AWTO_SDCC_BE")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = B.setup_logs("rtd_diag").main          # decoded I2C + this tool's lines; byte trace in rtd_diag.raw.log
    io = IO = B.Real(a.bus, allow_write=False, regread=True)
    if a.release:
        ok = _release(io)
        print("released" if ok else "release: no ACK from 0x35"); return 0 if ok else 1
    if a.messages:
        for sig in (signal.SIGTERM, signal.SIGHUP):             # terminal closed / killed: run the finally (release)
            signal.signal(sig, lambda *_: sys.exit(0))
        return messages(io, root, a.secs or None)
    if a.trace:
        return trace(io, root, a.be, a.ids)
    if a.hold or a.unhold:
        val = SAFE_HOLD if a.hold else 0
        t0 = time.monotonic()
        w = B.Real(a.bus, allow_write=True)
        try:
            # --hold races the 2 s safe window after power-on: retry every write attempt until it lands
            while not set_hold(w, val, a.be):
                if not a.hold or time.monotonic() - t0 > a.hold_wait:
                    el = time.monotonic() - t0
                    print(f"{'hold' if a.hold else 'unhold'}: no ACK from 0x35 after {el:.1f} s (limit {a.hold_wait:g} s)")
                    return 1
                time.sleep(HOLD_POLL_S)
        finally:
            w.close()
        line = f"{'hold set' if a.hold else 'hold released'} after {time.monotonic() - t0:.1f} s"
        print(line); log(line)
    if a.safe or a.hold or a.unhold:
        s = read_safe(io, a.be)
        if s is None:
            print("safe block read failed (no ACK from 0x35)"); return 1
        txt = safe_report(s, load_trace_names(root, a.ids))
        print(txt); log(txt)
        return 0
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
