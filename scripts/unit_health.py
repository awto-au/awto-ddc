#!/usr/bin/env python3
"""Eyes-free health check of a running unit over debug slave 0x35 at 100 kHz (awto-ddc#11, #38).

usage: unit_health.py <bus> --serial AWT2611000N --map tmp/fw/<tag>.map --gdctl HDMI-2 [--host-mode WxH@HZ]
  One line per check, PASS/FAIL summary, exit 0 only if all pass. Writes: only the OSD test events (info event,
  test byte 0x20) after the EDID unit guard. Never uses rtd_diag --messages (wedged 0x35, 2026-11-06).
  Addresses from the flashed image's map; structs are SDCC big-endian (WORD = high byte first), bit-fields LSB first.
Log: ./tmp/logs/unit_health.log (+ .raw.log)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
import rtd_proto as P  # noqa: E402
import unit_lock  # noqa: E402

DEV8 = 0x6A                                   # 7-bit 0x35
DIAG_OFF = {"magic": 0, "stage": 3, "hb": 0x14, "t2": 0x16, "testcmd": 0x28}
MODE_NAMES = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF",
              "FACTORY"]
POWER_NAMES = ["AC_ON", "OFF", "NORMAL", "SAVING"]
MODE_ACTIVE, POWER_NORMAL = 3, 2
PIN_BACKLIGHT_N, PIN_PANEL = 0xFE2A, 0xFE1A    # P9.2 active low enable, P7.2 panel power; bit 0 = pin level
EVENT_INFO, TESTCMD_DEBUG = 10, 0x20           # EnumOsdEvent info pop-up; ucTestCmd 0x20 = debug pop-up (#34)
# Loop-rate window: 1 s of Timer2 ticks gives ~170 loop counts per window (+-1 %); bus idle in the window.
RATE_WINDOW_S, RATE_REPEATS = 1.0, 3
SIM_RATE_WINDOW_S = 1.0          # 0.1 s windows read 0 / 30 / 1549 right after ACTIVE (OSD pop-up drawing blocks the loop): kept at 1 s
# Consume wait: pop-up draw stalls the debug slave ~0.4 s (#11 comment); limit = 1.25x worst seen, expiry = FAIL.
CONSUME_WAIT_S = 0.5
TIMING_VFREQ_TOL = 5                           # 0.1 Hz units (0.5 Hz): SDK value only (no count); host 60.000 vs measured 60.1
# exact (active-region count) vs host: relative, max(10 mHz, 0.25 %). Sweep 2026-11-07 (#26): -150 ppm on 4K60 (unit 3
# measure clock), up to +2000 ppm on 720p24 / +1100 ppm on 1280x960 (low pixel clocks); a fixed 10 mHz flagged 12 ACTIVE modes.
TIMING_EXACT_TOL_MHZ = 10
TIMING_EXACT_TOL_REL = 0.0025
HDIAG_STAGE = 8
MAP_SYMS = ("isr_g_stAwtoDiag", "isr_g_stModeInfo", "isr_g_stPowerInfo", "g_stMDomainInputData", "g_stOsdInfo", "g_ulInputActiveRegionBackUp")
MAP_SYMS_OPT = (P.AWTO_FREQ_SYM, "g_stAwtoLoop")   # awto_freq.inc (#34); awto_loopsplit.inc (#75)
RETRY_TRIES = 2


class DbgError(Exception):
    pass


def sym_addr(map_text: str, name: str) -> int:
    m = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", map_text)
    if not m:
        raise DbgError(f"_{name} not in map")
    return int(m.group(1), 16) & 0xFFFF


def load_maps(map_text: str) -> dict:
    """Symbol -> XDATA address: MAP_SYMS required, MAP_SYMS_OPT None when the image has none; + osd_ofs."""
    maps = {n: sym_addr(map_text, n) for n in MAP_SYMS}
    for n in MAP_SYMS_OPT:
        try:
            maps[n] = sym_addr(map_text, n)
        except DbgError:
            maps[n] = None
    maps["osd_ofs"] = P.osd_offsets_from_map(map_text)
    return maps


def be16(b: bytes, i: int) -> int:
    return (b[i] << 8) | b[i + 1]


def decode_mode(b: bytes) -> int:
    return b[0] & 0x1F                         # b5ModeState, LSB first


def decode_power(b: bytes) -> tuple[int, int]:
    return b[0] & 0x0F, b[0] >> 4              # b4PowerAction, b4PowerStatus


decode_timing = P.decode_timing                # StructTimingInfo (SDK 0.1 kHz / 0.1 Hz units)


def parse_host_mode(s: str) -> tuple[int, int, float]:
    m = re.fullmatch(r"(\d+)x(\d+)@([\d.]+)", s.strip())
    if not m:
        raise DbgError(f"host mode {s!r} not WxH@HZ")
    return int(m.group(1)), int(m.group(2)), float(m.group(3))


def gdctl_mode(show: str, monitor: str) -> str | None:
    """Current mode of `Monitor <name>` from `gdctl show` text, or None."""
    blk = re.split(r"Logical monitors:", show)[0]
    parts = re.split(r"Monitor ", blk)
    for p in parts:
        if p.startswith(monitor + " "):
            m = re.search(r"Current mode\W*(\d+x\d+@[\d.]+)", p)
            return m.group(1) if m else None
    return None


class Dbg:
    """XDATA reads/writes through the firmware debug slave. Reads use the block path (0x3C, docs/diag-block.md) once
    check_diag saw diag version >= 2, else the byte path (0x01 [hi], 0x3A [lo], read 0x08)."""

    def __init__(self, io, wait=time.sleep, now=time.monotonic):
        self.io, self.wait, self.now, self.retries, self.block = io, wait, now, 0, False

    def _try(self, what: str, fn):
        """0x35 NAKs intermittently at 100 kHz (seen 2026-11-06): one retry per transfer group after 5 ms
        (~1 main-loop pass for the debug ISR to settle); counted and shown in the summary."""
        for attempt in range(RETRY_TRIES):
            r = fn()
            if r is not None and r is not False:
                return r
            self.retries += attempt < RETRY_TRIES - 1
            self.wait(0.005)
        raise DbgError(what)

    def read(self, addr: int, n: int = 1) -> bytes:
        out = bytearray()
        if self.block:
            for off in range(0, n, X.BLK_MAX):
                a, k = (addr + off) & 0xFFFF, min(X.BLK_MAX, n - off)
                out += self._try(f"no ACK/data block-reading 0x{a:04X} x{k}", lambda a=a, k=k: X.read_chunk(self.io, a, k))
            return bytes(out)
        for k in range(n):
            x = (addr + k) & 0xFFFF
            out += self._try(f"no ACK/data reading 0x{x:04X}", lambda x=x: X.read_byte(self.io, x))
        return bytes(out)

    def write(self, addr: int, v: int) -> None:
        self._try(f"no ACK writing 0x{addr:04X}",
                  lambda: (self.io.write(DEV8, 0x01, bytes([addr >> 8])) and self.io.write(DEV8, 0x03, bytes([v]))
                           and self.io.write(DEV8, 0x3B, bytes([addr & 0xFF]))) or None)


class Report:
    def __init__(self, log=None):
        self.rows: list[tuple[str, bool, str]] = []
        self.log = log

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.rows.append((name, ok, detail))
        line = f"{'PASS' if ok else 'FAIL'}  {name:<14} {detail}"
        print(line, flush=True)
        if self.log:
            self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n")
            self.log.flush()
        return ok

    def summary(self, label: str, retries: int = 0) -> int:
        bad = [n for n, ok, _ in self.rows if not ok]
        line = f"HEALTH {label}: {len(self.rows) - len(bad)}/{len(self.rows)} PASS, {retries} bus retries" + (f", FAIL: {', '.join(bad)}" if bad else "")
        print(line, flush=True)
        if self.log:
            self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n")
            self.log.flush()
        return 1 if bad else 0


def guarded(rep: Report, name: str, fn) -> bool:
    try:
        return fn()
    except DbgError as e:
        return rep.add(name, False, f"read failed: {e}")


def check_diag(rep, d: Dbg, base: int, wait=time.sleep) -> bool:
    last = ""
    for attempt in range(2):                   # first read right after a reset can NAK (2026-11-06): retry once
        try:
            d.block = False
            b = d.read(base, 4)
            d.block = X.block_supported(b)
            ok = b[:2] == b"AD" and b[3] == HDIAG_STAGE
            return rep.add("diag stage", ok, f"magic {b[:2]!r} version {b[2]} stage {b[3]} (want {HDIAG_STAGE}); "
                           f"{'block' if d.block else 'byte'} reads" + (" after retry" if attempt else ""))
        except DbgError as e:
            last = str(e)
            wait(0.1)                          # one retry: ~15 main-loop passes for the debug ISR to settle
    return rep.add("diag stage", False, f"read failed twice: {last}")


def loop_rate(d: Dbg, base: int, wait=time.sleep, window: float = RATE_WINDOW_S) -> tuple[float, list[float], float]:
    """(mean rate/s, per-window rates, cumulative rate). Rate = d(hb)/d(Timer2 ticks of 1 ms); bus idle in the window."""
    rates = []
    for _ in range(RATE_REPEATS):
        a = d.read(base + DIAG_OFF["hb"], 4)
        wait(window)
        b = d.read(base + DIAG_OFF["hb"], 4)
        dh = (be16(b, 0) - be16(a, 0)) & 0xFFFF
        dt = (be16(b, 2) - be16(a, 2)) & 0xFFFF
        if dt == 0:
            raise DbgError("Timer2 ISR count did not advance")
        rates.append(dh * 1000.0 / dt)
    cum = be16(b, 0) * 1000.0 / max(be16(b, 2), 1)
    return sum(rates) / len(rates), rates, cum


SLOW_GAP_MAX_MS = 50    # #75: cable / signal changes must be noticed within 50 ms (slow path every 10 ms + one pass)


def check_rate(rep, d, base, wait=time.sleep, min_rate=50.0, window: float = RATE_WINDOW_S, loop_addr=None) -> bool:
    mean, rates, _cum = loop_rate(d, base, wait, window)
    ok, slow = mean >= min_rate, ""
    if loop_addr is not None:              # g_stAwtoLoop (#75 split images): fast, slow rate, runs, max gap (BE words)
        b = d.read(loop_addr, 8)
        fast, srate, gap = be16(b, 0), be16(b, 2), be16(b, 6)
        ok &= 0 < gap <= SLOW_GAP_MAX_MS
        slow = f"; fast {fast}/s, slow path {srate}/s, max gap {gap} ms (limit {SLOW_GAP_MAX_MS})"
    return rep.add("main loop", ok,
                   f"{mean:.1f}/s mean of {len(rates)} x {window:g} s windows ({', '.join(f'{r:.1f}' for r in rates)})" + slow)


def check_state(rep, d, mode_addr, power_addr) -> bool:
    ms = decode_mode(d.read(mode_addr, 1))
    pa, ps = decode_power(d.read(power_addr, 1))
    ok1 = rep.add("mode state", ms == MODE_ACTIVE, f"{ms} {MODE_NAMES[ms] if ms < len(MODE_NAMES) else '?'} (want ACTIVE 3)")
    ok2 = rep.add("power status", ps == POWER_NORMAL, f"{ps} {POWER_NAMES[ps] if ps < len(POWER_NAMES) else '?'} (want NORMAL 2)")
    return ok1 and ok2


def check_timing(rep, d, maps: dict, host: tuple[int, int, float] | None) -> bool:
    t, x, note = P.read_timing(d.read, maps)
    got = P.fmt_timing(t, x) + (f"; {note}" if note else "")
    if host is None:
        return rep.add("input timing", False, f"measured {got}; host mode unknown")
    w, h, hz = host
    ok = (t["hwidth"], t["vheight"]) == (w, h) and (abs(x["vfreq_mhz"] - hz * 1000) <= max(TIMING_EXACT_TOL_MHZ, TIMING_EXACT_TOL_REL * hz * 1000) if x else
                                                     abs(t["vfreq"] - hz * 10) <= TIMING_VFREQ_TOL) and "DISAGREES" not in note
    return rep.add("input timing", ok, f"measured {got} vs host {w}x{h}@{hz:.3f}")


def check_pins(rep, d) -> bool:
    bl, pn = d.read(PIN_BACKLIGHT_N, 1)[0], d.read(PIN_PANEL, 1)[0]
    ok1 = rep.add("backlight en", (bl & 1) == 0, f"P9.2 (0xFE2A) = 0x{bl:02X}, bit0 {bl & 1} (low = on)")
    ok2 = rep.add("panel power", (pn & 1) == 1, f"P7.2 (0xFE1A) = 0x{pn:02X}, bit0 {pn & 1} (high = on)")
    return ok1 and ok2


def consumed(d: Dbg, addr: int, wait=time.sleep, now=time.monotonic) -> tuple[bool, float, int]:
    """Poll `addr` until 0 (consumed). A pop-up draw keeps the debug ISR from answering: those NAKs are counted as
    draw evidence, not failures. -> (consumed, elapsed s, NAKed polls)."""
    t0, naks = now(), 0
    while True:
        try:
            if d.read(addr, 1)[0] == 0:
                return True, now() - t0, naks
        except DbgError:
            naks += 1
        if now() - t0 > CONSUME_WAIT_S:
            return False, now() - t0, naks
        wait(0.005)                            # ~1 main-loop pass between polls


def osd_layout(d, diag_addr, hint):
    """g_stOsdInfo offsets (ofs, note): the firmware's own report (diag 0x2C..0x2E) wins; the map model must agree (#37)."""
    got = P.osd_offsets_from_diag(d.read(diag_addr + P.DIAG_OSD_OFS_AT, 3))
    if got is None:
        return hint, "layout from map (image has no self-report)"
    if got != hint:
        return None, f"firmware reports g_stOsdInfo layout {got} but the map model says {hint}: fix rtd_proto.osd_offsets_from_map"
    return got, "layout = firmware report"


def check_osd(rep, d, osd_addr, diag_addr, hint, wait=time.sleep) -> bool:
    """usOsdState does not move for pop-ups (event path); the evidence is the consume + the debug-slave stall while drawing."""
    ofs, note = osd_layout(d, diag_addr, hint)
    if ofs is None:
        rep.add("osd event", False, note)
        return False
    st0 = be16(d.read(osd_addr + ofs["usOsdState"], 2), 0)
    d.write(osd_addr + ofs["ucOsdEventMsg"], EVENT_INFO)
    ok, dt, naks = consumed(d, osd_addr + ofs["ucOsdEventMsg"], wait, d.now)
    r1 = rep.add("osd event", ok, f"info event {'consumed' if ok else 'NOT consumed'} in {dt * 1000:.0f} ms, "
                 f"{naks} NAKed polls while drawing (limit {CONSUME_WAIT_S * 1000:.0f} ms); usOsdState 0x{st0:04X}; {note}")
    tc = diag_addr + DIAG_OFF["testcmd"]
    d.write(tc, TESTCMD_DEBUG)
    ok, dt, naks = consumed(d, tc, wait, d.now)
    r2 = rep.add("osd test cmd", ok, f"debug test byte 0x{TESTCMD_DEBUG:02X} {'consumed' if ok else 'NOT consumed'} in "
                 f"{dt * 1000:.0f} ms, {naks} NAKed polls (limit {CONSUME_WAIT_S * 1000:.0f} ms)")
    return r1 and r2


def check_delaycal(rep, d: Dbg, base: int, sim: bool = False) -> bool:
    """Delay calibration the firmware ran inside the panel T3 wait (fw/sdcc/awto_delaycal.inc): tick, busy loops, T3 length."""
    import rtd_diag
    blk = bytearray(48)
    blk[0x1A:0x28] = d.read(base + 0x1A, 14)          # ucDelay5usN .. usT3Wait64 only
    cal = rtd_diag.decode(bytes(blk), True)
    rows = rtd_diag.cal_eval(cal, sim)
    bad = [n for n, ok, _ in rows if ok is False]
    return rep.add("delay cal", not bad, "; ".join(f"{n} {det}" for n, ok, det in rows) + (f"  [FAIL: {', '.join(bad)}]" if bad else ""))


def run(d: Dbg, maps: dict, host, rep: Report, wait=time.sleep, sim: bool = False) -> int:
    """All checks, each independent: a failed read marks that check FAIL and the rest still run."""
    base = maps["isr_g_stAwtoDiag"]
    steps = [("diag stage", lambda: check_diag(rep, d, base, wait)),
             ("main loop", lambda: check_rate(rep, d, base, wait, window=SIM_RATE_WINDOW_S if sim else RATE_WINDOW_S,
                                              loop_addr=maps.get("g_stAwtoLoop"))),
             ("mode state", lambda: check_state(rep, d, maps["isr_g_stModeInfo"], maps["isr_g_stPowerInfo"])),
             ("input timing", lambda: check_timing(rep, d, maps, host)),
             ("pins", lambda: check_pins(rep, d)),
             ("osd", lambda: check_osd(rep, d, maps["g_stOsdInfo"], base, maps["osd_ofs"], wait)),
             ("delay cal", lambda: check_delaycal(rep, d, base, sim))]
    for name, fn in steps:
        guarded(rep, name, fn)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int, nargs="?")
    ap.add_argument("--serial")
    ap.add_argument("--map", type=Path)
    ap.add_argument("--gdctl", help="host monitor name for the current mode (gdctl show, read-only)")
    ap.add_argument("--host-mode", help="WxH@HZ instead of gdctl")
    ap.add_argument("--sim", nargs=2, type=Path, metavar=("BIN", "MAP"),
                    help="run against the firmware simulator (fw_sim.SimBus), no hardware; host mode defaults to 1920x1080@60")
    ap.add_argument("--ffwd", action="store_true", help="sim: fast-forward ScalerTimerDelayXms spins (off: it moves d_isr_g_usTimerCounter "
                    "without Timer2, so the delay-cal T3 check reads 593 vs 550 ms)")
    ap.add_argument("--sim-port", default="D2", choices=("D2", "D3"),
                    help="sim: HDMI input carrying the source; the host reads 0x35 on that port's DDC (#28)")
    a = ap.parse_args()
    if a.sim:
        return run_sim(a)
    if a.bus is None or not a.serial or not a.map:
        ap.error("bus, --serial and --map are required (or --sim BIN MAP)")
    with unit_lock.held(a.serial, "unit_health"):                # one work stream per unit (#65)
        return health_hw(a)


def health_hw(a) -> int:
    import i2cbus
    import rtd_i2c_bridge as B
    log = B.setup_logs("unit_health", map=a.map).main
    i2cbus.dev_hint("health", "unit_health.py")
    rep = Report(log)
    if i2cbus.rate_khz() != 100:
        rep.add("bus rate", False, f"{i2cbus.rate_khz()} kHz; 0x35 health runs at 100 kHz only")
        return rep.summary(a.serial)
    i2cbus.require_unit(a.bus, a.serial)
    txt = a.map.read_text(errors="replace")
    maps = load_maps(txt)
    host = None
    mode = a.host_mode
    if not mode and a.gdctl:
        mode = gdctl_mode(subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=10).stdout, a.gdctl)
    if mode:
        host = parse_host_mode(mode)
    rep.add("bus rate", True, f"100 kHz; map {a.map.name}; host mode {mode or 'unknown'}")
    dbg = Dbg(B.Real(a.bus, allow_write=True))
    run(dbg, maps, host, rep)
    return rep.summary(a.serial, dbg.retries)


def run_sim(a) -> int:
    """All checks against the firmware simulator; time = firmware Timer2 time (SimBus.wait / now)."""
    import fw_sim
    binp, mapp = a.sim
    mode = a.host_mode or "1920x1080@60"
    rep = Report()
    w, h, hz = parse_host_mode(mode)
    video = "1080p60" if h == 1080 else ("2160p59.94" if hz < 59.97 else "2160p60")   # fw_sim.HdmiInput preset for the host mode
    bus = fw_sim.SimBus(binp, mapp, video=video, port=a.sim_port, ffwd=a.ffwd)
    bus.run_until_mode(MODE_ACTIVE)                 # the unit under test is already up: let the display setup finish
    try:
        maps = load_maps(mapp.read_text(errors="replace"))
        rep.add("bus rate", True, f"simulated bus; image {binp.name}; host mode {mode} (source model {video} on {a.sim_port})")
        dbg = Dbg(bus, wait=bus.wait, now=bus.now)
        run(dbg, maps, parse_host_mode(mode), rep, wait=bus.wait, sim=True)
        print(f"sim: {bus.ffwd_ms} ms of ScalerTimerDelayXms fast-forwarded (not a check)")
        return rep.summary(binp.stem, dbg.retries)
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main())
