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
  Text starting 0x01 = token: bytes 1-2 big-endian id -> the table inside the flashed image (--serial/--table,
  scripts/msg_table.py, #56), else fw/msgids.tsv (id, category, file:line, text).
Block layout, little-endian (SDCC; low byte first), from fw/sdk/Project/Header/RL6449_Project.h StAwtoDiag:
  00 'A' 'D' | 02 version | 03 stage | 04..13 u16 stage ms[8] | 14 hb u16 | 16 t2 isr u16 | 18 ex1 isr u16
  | 1A ucDelay5usN | 1B u16 10 ticks of ScalerTimerDelayXms, counts/4 | 1D u16 10 x DELAY_5US raw counts | 1F RCAP2H
  | 20 u16 DELAY_XUS(100) | 22 u16 DELAY_XUS_EXINT(100) | 24 u16 10 x DELAY_5US_EXINT | 26 u16 panel T3 wait total, counts/64
  | 28 u8 test cmd | 29 u8 dbg popup | 2A u16 loop/s | 2C u8x3 g_stOsdInfo offsets state,event,key (#37) | 2F hold
  Delay-calibration counts are raw Timer2 counts (EA off, overhead of an empty snapshot pair subtracted); fw/diag/delaycal.c.
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
# #63 order (images from wb-port 2026-11-07 on): VDD comes right after pin-share, so 5 = VDD, 6 = first main-loop pass,
# 7 = eDP link done, 8 = backlight on. Stages 1-4 are coarse: Timer2 starts inside McuInitial (pre-main not counted).
STAGES = ["", "BOOT (start of main)", "GPIO init done (in McuInitial)", "McuInitial done", "pin-share done",
          "panel VDD on", "main loop first pass", "eDP link done", "backlight on"]
STAGES_OLD = ["", "BOOT (start of main)", "GPIO init done (in McuInitial)", "McuInitial done", "pin-share done",
              "main loop first pass", "panel power on", "DPTx link start", "DPTx link done"]
BOOTING_MS = 2000      # cold boot reaches stage 8 at ~0.5 s (#63, wb-port7); under 2 s uptime a missing stage = still booting
PERIOD = {0xE3: 7309, 0xFB: 1194}   # Timer2 counts per 1 ms tick, keyed by RCAP2H (see docstring)
# Delay calibration rows: (key, label, calls in the measured body, nominal us per call, lo, hi). A busy delay shorter than
# nominal breaks the minimum waits it stands for (PHY settle, SDK `DELAY_XUS`); longer only costs time. So strict low,
# loose high: lo 97 % (boot self-cal targets 105 %; one count step ~4 %), hi 150 % catches a broken loop, not layout
# drift (126-132 % seen on 2026-11-07, #54).
CAL_ROWS = (("d5us10", "DELAY_5US", 10, 5.0, 0.97, 1.50),
            ("xus100", "DELAY_XUS(100)", 1, 100.0, 0.97, 1.50),
            ("xusisr100", "DELAY_XUS_EXINT(100)", 1, 100.0, 0.97, 1.50),
            ("d5isr10", "DELAY_5US_EXINT", 10, 5.0, 0.97, 1.50))
# 10 ticks vs the reload period: catches a lost / extra tick (+-10 %) or a wrong reload. Half a tick: the snapshots follow
# the Timer2 ISR return, so per-tick ISR length (~50 us, code-dependent) lands in the result (#54)
CAL_TICK_TOL = 0.05
CAL_T3_FAST_MAX_MS = 100   # fast boot (#63): 20 ms own-pattern T3 + the ~40 ms delay test inside it, x~1.5
CAL_T3_MS, CAL_T3_TOL_MS = 550, 1.5  # panel T3 (_PANEL_POWER_ON_T3): ScalerTimerDelayXms granularity 1 tick + 64-count resolution
IDLE_POLL_S = 0.002   # a status read is ~0.3 ms at 100 kHz; 2 ms bounds the stall added per message (fw halts until fetched)
MSG_ENABLE, MSG_FETCH, MSG_END, MSG_DONE = 0x55, 0x25, 0x2A, 0x2F
ST_NONE, ST_PENDING = 0xFC, 0xF1
REARM_S = 0.5   # idle re-enable period: a re-arm after a 100 ms fw timeout loses < 0.5 s of messages (they stay in the fw ring)
LOG = None


def log(s: str) -> None:
    LOG.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n"); LOG.flush()


def read_block(io) -> bytes | None:
    return read_bytes(io, 0, SIZE)


def decode(b: bytes, be: bool = False) -> dict:
    m0, m1, ver, stage = b[0], b[1], b[2], b[3]
    ts = list(struct.unpack_from(("> " if be else "<")[0] + "8H", b, 4))
    hb, t2, ex1 = struct.unpack_from(("> " if be else "<")[0] + "3H", b, 20)
    e = ("> " if be else "<")[0]
    d5, xms, d5us10 = b[26], *struct.unpack_from(e + "2H", b, 27)
    xus100, xusisr100, d5isr10, t3_64 = struct.unpack_from(e + "4H", b, 32)
    return {"xus100": xus100, "xusisr100": xusisr100, "d5isr10": d5isr10, "t3_64": t3_64, "magic_ok": (m0, m1) == (0x41, 0x44), "ver": ver, "stage": stage, "ts": ts, "hb": hb, "t2": t2,
            "ex1": ex1, "d5": d5, "xms4": xms, "d5us10": d5us10, "rcap2h": b[31], "wdt": b[0x29]}


def report(d: dict, prev: dict | None, dt: float | None) -> str:
    L = []
    if not d["magic_ok"]:
        return f"magic not 'AD' (version {d['ver']}): firmware without the diag block, or read path failed"
    st = d["stage"]
    names = STAGES if d.get("new_stages", True) else STAGES_OLD
    booting = st < 8 and d["t2"] < BOOTING_MS
    L.append(f"version {d['ver']}  stage {st}: {names[st] if st < len(names) else '?'}"
             + (f"  (boot in progress, uptime {d['t2']} ms)" if booting else "")
             + f"  WDT_TEST at boot 0x{d['wdt']:02x}{' (WATCHDOG RESET)' if d['wdt'] & 0x80 else ''}")
    for n in range(1, 9):
        reached = n <= st or d["ts"][n - 1]
        L.append(f"  stage {n} {names[n]:32s} " + (f"{d['ts'][n - 1]:6d} ms" if reached else
                                                    ("   not yet (booting)" if booting else "   not reached")))
    if prev is not None and dt:                            # u16 wrap-safe deltas
        w = lambda k: (d[k] - prev[k]) & 0xFFFF
        L.append(f"main loop {w('hb') / dt:9.1f} /s   Timer2 ISR {w('t2') / dt:7.1f} /s   EXINT1 ISR {w('ex1') / dt:7.1f} /s"
                 f"   (over {dt:.2f} s)")
    else:                                                  # one read: counters are u16, wrap independently every ~65 s
        L.append("main loop rate: needs two reads (u16 counters wrap independently; one-read ratio is meaningless "
                 "after 65 s uptime): use --watch or ./dev.py health")
    L.append(f"Timer2 ISR count {d['t2']}   main-loop count {d['hb']}   EXINT1 count {d['ex1']}")
    L += [f"delay cal {'ok  ' if ok else 'FAIL' if ok is False else '-   '} {name}: {detail}" for name, ok, detail in cal_eval(d)]
    return "\n".join(L)


def cal_eval(d: dict, sim: bool = False) -> list:
    """Delay calibration rows [(name, ok, detail)] from a decoded block. ok None = not applicable. sim: the simulator's
    Timer2 counts ucsim machine cycles, so the busy-loop rows are not timed there; tick and T3 rows are (same reload)."""
    per = PERIOD.get(d["rcap2h"])
    if per is None and sim:                               # fw_sim._scale_t2 rewrites RCAP2 to k x the firmware's count
        per = PERIOD[0xE3] * round((256 - d["rcap2h"]) * 256 / PERIOD[0xE3])
    if not d["xms4"]:
        return [("run", False, f"not run: the panel T3 wait was never reached, or ScalerTimerDelayXms never returned (RCAP2H 0x{d['rcap2h']:02X})")]
    if per is None:
        return [("run", False, f"RCAP2H 0x{d['rcap2h']:02X} not in the Timer2 table")]
    rows = []
    ticks = d["xms4"] * 4 / per                           # ms, expected 10
    rows.append(("tick", abs(ticks - 10) <= 10 * CAL_TICK_TOL,
                 f"10 ticks = {ticks:.3f} ms (limit +-{CAL_TICK_TOL * 100:.1f} %)"))
    for key, label, calls, nom, lo, hi in CAL_ROWS:
        us = d[key] / per * 1000.0 / calls
        if sim:
            rows.append((label, None, f"{us:.2f} us/call (sim, not timed; nominal {nom:g})"))
            continue
        rows.append((label, nom * lo <= us <= nom * hi,
                     f"{us:.2f} us/call, {us / nom * 100:.0f} % of {nom:g} (limit {lo * 100:.0f}..{hi * 100:.0f} %)"))
    t3 = d["t3_64"] * 64 / per
    if sim:                                               # dilated Timer2 (x3): the u16 of counts/64 wraps; compare mod 2^16
        err = ((d["t3_64"] - CAL_T3_MS * per // 64 + 0x8000) & 0xFFFF) - 0x8000
        t3 = CAL_T3_MS + err * 64 / per
    fast = (not sim) and 0 < t3 <= CAL_T3_FAST_MAX_MS      # #63 fast boot: T3 = one frame while the scaler shows its own pattern
    rows.append(("T3 wait", d["t3_64"] != 0 and (fast or abs(t3 - CAL_T3_MS) <= CAL_T3_TOL_MS),
                 f"{t3:.2f} ms incl. the test (limit {CAL_T3_MS} +-{CAL_T3_TOL_MS} ms, or <= {CAL_T3_FAST_MAX_MS} ms own-pattern fast boot)"))
    return rows


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


def messages(io, root: Path, secs: float | None = MSG_SECS, serial=None, table=None) -> int:
    import msg_table
    ids, src = msg_table.load_ids(root, serial, table)      # image table (#56) first, fw/msgids.tsv last
    print(f"message ids: {len(ids)} from {src}", flush=True); log(f"message ids: {len(ids)} from {src}")
    if not io.write(DEV8, MSG_ENABLE, b"\x5a"):
        print("enable failed (no ACK from 0x35)"); return 1
    t0 = t_en = time.monotonic()
    try:
        while secs is None or time.monotonic() - t0 < secs:
            st = io.read(DEV8, READ_SUB, 1)
            if st is None:
                print("read failed"); return 1
            if st[0] != ST_PENDING:
                time.sleep(IDLE_POLL_S)
                if time.monotonic() - t_en > REARM_S:      # fw drops a host silent for 100 ms (#56): re-arm
                    io.write(DEV8, MSG_ENABLE, b"\x5a"); t_en = time.monotonic()
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


def timing_line(io, root: Path, map_path: str | None) -> str | None:
    """'input 3840x2160@59.940 Hz (H 134.865 kHz, pclk 593.407 MHz; ...)' from the active-region count (#34); None = no map."""
    import rtd_proto as P
    mp = Path(map_path) if map_path else P.default_map(root)
    if not mp or not Path(mp).exists():
        return None
    import unit_health as H
    try:
        maps = H.load_maps(Path(mp).read_text(errors="replace"))
    except H.DbgError as e:
        return f"input timing: {e}"

    def rd(a, n):
        b = X.read(io, a, n, _BLOCK)
        if b is None:
            raise H.DbgError(f"read 0x{a:04X}+{n} failed")
        return b
    try:
        t, x, note = P.read_timing(rd, maps)
    except H.DbgError as e:
        return f"input timing: {e}"
    return f"input {P.fmt_timing(t, x)}" + (f"; {note}" if note else "") + f"  [map {Path(mp).name}]"


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
    ap.add_argument("--serial", help="--messages: take the id table from this unit's flashed image (tmp/fw/<serial>-flashed.json)")
    ap.add_argument("--table", type=Path, help="--messages: id table block or firmware image (scripts/msg_table.py)")
    ap.add_argument("--trace", action="store_true", help="poll the function-entry trace ring (fw/trace_files.txt)")
    ap.add_argument("--ids", help="trace id TSV of the flashed image (default tmp/sdcc-port/trace_ids.tsv)")
    ap.add_argument("--safe", action="store_true", help="read the safe-boot/WDT-canary block (0xF6B0)")
    ap.add_argument("--hold", action="store_true",
                    help="poll until the fw answers, then hold it in the safe window (no inputs/display)")
    ap.add_argument("--hold-wait", type=float, default=HOLD_WAIT_S, metavar="S",
                    help=f"--hold gives up after S seconds (default {HOLD_WAIT_S:g}: 2.5x the 2 s safe window)")
    ap.add_argument("--unhold", action="store_true", help="release the safe-window hold (fw continues booting)")
    ap.add_argument("--map", help="image .map: also print the input timing with exact frequencies (default $AWTO_DDC_MAP, else the newest tmp/fw/*/fw.map)")
    ap.add_argument("--be", action="store_true", default=os.environ.get("AWTO_SDCC_BE") == "1",
                    help="block written by a --big-endian build (u16 MSB first); default from $AWTO_SDCC_BE")
    ap.add_argument("--sync", action="store_true", help="print the sync / power-on log ring (#139, scripts/sync_log.py; needs --map)")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = B.setup_logs("rtd_diag").main          # decoded I2C + this tool's lines; byte trace in rtd_diag.raw.log
    if a.sync:
        import rtd_proto as P
        import sync_log as S
        mp = Path(a.map) if a.map else P.default_map(root)
        if not mp or not Path(mp).exists():
            print("--sync needs --map (the flashed image's .map; its .sync.tsv beside it)"); return 1
        w = IO = B.Real(a.bus, allow_write=True, regread=True)     # a debug read sets the address by a write
        raw = S.read_ring(lambda ad, n: X.read_blocks(w, ad, n), S.sym(Path(mp), "g_stAwtoSync"))
        if raw is None:
            print("sync: read over 0x35 failed"); return 1
        S.set_map(Path(mp))                       # #29: boot reason PC as symbol + offset
        h, lines = S.decode(bytes(raw), S.load_rows(S.tsv_for(Path(mp))))
        ht, t2 = S.read_ht(w, Path(mp))          # #157: host time per line from the latest DDC/CI time sync
        lines = S.stamp(h, lines, ht, t2)
        pin = None
        try:                                      # #150: the boot reason, kept outside the ring
            pin = S.pin_line(X.read_blocks(w, S.sym(Path(mp), "g_stAwtoSyncPin"), S.EV), S.load_rows(S.tsv_for(Path(mp))))
        except SystemExit:
            pass
        txt = "\n".join(([f"boot reason (pinned): {pin}"] if pin else []) + [S.ht_line(ht, t2)] +
                        [f"sync episode: {S.KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines"] + ["  " + ln for ln in lines])
        print(txt); log(txt)
        return 0
    io = IO = B.Real(a.bus, allow_write=False, regread=True)
    if a.release:
        ok = _release(io)
        print("released" if ok else "release: no ACK from 0x35"); return 0 if ok else 1
    if a.messages:
        for sig in (signal.SIGTERM, signal.SIGHUP):             # terminal closed / killed: run the finally (release)
            signal.signal(sig, lambda *_: sys.exit(0))
        return messages(io, root, a.secs or None, a.serial, a.table)
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
        tl = timing_line(io, root, a.map)
        if tl:
            txt += "\n" + tl
        print(f"--- {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n{txt}", flush=True)
        log(txt)
        prev, tprev = d, t
        if not a.watch:
            return 0
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
