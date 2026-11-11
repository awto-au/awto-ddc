#!/usr/bin/env python3
"""Watchdog test runner (awto-ddc#138, docs/watchdog.md): the same cases on fw_sim and on unit 2.

usage: AWTO_SIM_CORE=fast wdt_test.py --sim BIN MAP [--cases a,b] [--baseline-s 10]
       wdt_test.py --unit 2 --map MAP [--cases a,b]          (bus from devices.json by EDID serial; 100 kHz)
       wdt_test.py --list
       (debug: WDT_TEST_SUB=label,... runs only those sub-cases of t0_arm_from_isr)
- Cases (CASES table: test cmd, expected, deadline = 1.25 x the expected worst case, checks); ea_off runs last.
  A case the image does not implement (no test cmd / symbol) is SKIP with the reason.
- Reset detection on the unit: in-process 0x35 poll every POLL_S (one byte read of the diag magic, 3 messages,
  ~12 bytes = ~1.1 ms of the 100 kHz bus: ~5 % at 20 ms); a reboot drops 0x35 (the firmware parks it, DDC/CI 0x37 owns
  the DDC). Link back with dbg_link.on; reset time = link-back time - diag uptime (usT2Isr, ms since ScalerMcuInitial).
  Monitor-return deadline: expected reset + RETURN_S (5 s, memory rule). No return: HANG (power-cycle unit 2 by hand).
- Sim: fw_sim ChipReset model (hardware WDT behaviour ASSUMED there, docs/watchdog.md); times in fw ms of the model.
Log: tmp/logs/wdt_test.log (one decoded line per step), tmp/logs/wdt_test.raw.log (unit: I2C bytes)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_crash as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/wdt_test.log"
CNT3_MS = 4096 * 2048 / 14318.18          # regdb CNT3 12 bit x 2048 XTAL clocks
TICK_MS = 2048 / 14318.18
N, THR = 2, 0xC00                          # RL6449_Project.h AWTO_WDT_N / AWTO_WDT_THR (read from --header if given)
CMD_MS = 100                               # test cmd written -> consumed: one main-loop pass (sim ~0.1 s, crash_sim_test)
POLL_S = 0.020                             # unit reset poll period (cost above)
RETURN_S = 5.0                             # monitor back after a reset (memory rule monitor-wait-5s)
PROBE_SPIN_MS = 1500                       # AWTO_WDT_PROBE_MS: the probe gives up and restores the watchdog
# before a case: settled mode (ACTIVE / NOSUPPORT / NOSIGNAL / POWER_SAVING / OFF). Worst = no signal after a flash: EDID back 5 s
# (dev.py RECOVER_BUS_WAIT_S) + boot 1.7 s + search 3 ports x 2 s + no-signal judge 1 s = 13.7 s x 1.25 -> 17 s
SETTLE_S = 17.0
SETTLED_MODES = (3, 4, 5, 6, 7)
NVSAVE_GAP_MS = 1000                       # between saves: one save + its OSD event < 1 pass (~0.5 s) x 2
# 0x35 is silent while the MCU is halted on a flash op: a save's ops (sector erase 200 + WRSR 40 + 16 x 3 ms program, MX25L8006E
# max) = 288 ms x 1.25 -> reads retried for 360 ms
FLASH_OP_MS = 360
TESTCMD_OFF = 0x28                         # g_stAwtoDiag + 0x28 (osd_test.TESTCMD_OFF)


def warn_ms():
    return (N - 1) * CNT3_MS + THR * TICK_MS


def reset_ms():
    return N * CNT3_MS


# name, cmd, expected, worst-case ms (deadline = 1.25 x), checks
CASES = [
    ("baseline", 0x29, "no reset for --baseline-s, with an NVRAM save (0x29 debug messages off, saved)", None,
     "link alive, record bites / warm unchanged; max pass / poke ages"),
    ("stall", 0x4C, "warning capture + sof_rst", lambda: warn_ms() + CMD_MS, "reset; record STALL TEST, bites + 1, PC in AwtoWdtHang"),
    ("pass", 0x4D, "nothing: 0x4D is gone (#138: a loop around a poking wait must be bounded; audit rule)", None,
     "no reset for 3 s"),
    ("probe", 0x49, "decides the unknowns: threshold IRQ in normal mode? reset at CNT1 = 1 (585.9 ms)?",
     lambda: PROBE_SPIN_MS + CMD_MS, "probe byte: IRQ / RESET / NO-RESET / WDTI (then 0x4F: timer mode)"),
    ("snapshot", None, "reset-vector register snapshot per reset type; diffs printed", None, "needs _g_stAwtoSnap"),
    ("reason", None, "first sync-log line after each reboot names the cause", None, "needs the #29 reason line"),
    ("clear", None, "host clear -> invalid; a soft reboot (ISP 0xEE / sof_rst) gives a fresh record, bites 0", lambda: 0.0,
     "record invalid after clear; after the reboot valid, bites 0"),
    ("t0_timing", 0x2A, "each Timer0 event at +-10 % (rebuild 30, RR D2 / D3 10) on the M2PLL and the PS reload (0x5A/5B)",
     lambda: 30 * 1.1 + CMD_MS, "fire time vs arm time (sim only: needs the fire instant)"),
    ("t0_clock_switch", 0x2E, "PS reload and back while pending (0x2E rebuild, 0x2F RR): still +-10 %", lambda: 30 * 1.1 + CMD_MS,
     "fire time (sim only)"),
    ("t0_multi", 0x5C, "0x2D two pending; 0x5C RR D3 10 / rebuild 30 / RR D2 5 armed out of order, RR D3 cancelled at 2 ms",
     lambda: 30 * 1.1 + CMD_MS, "fire order by deadline, cancelled one never fires (sim only)"),
    ("t0_arm_from_isr", 0x5D, "EXINT0 hook arms RR D2: alone, during a Timer0 ISR (same level), with TF0 + IE0 together, "
     "and with IP = 0x81 (EXINT0 high, preempts Timer0)", lambda: 10 * 1.1 + 5, "fires == arms, each at 10 ms +-10 % (sim only)"),
    ("prio_t0_vs_exint", 0x5E, "a 2-3 ms low-priority EXINT0 spin delays a pending Timer0 event by at most its length; Timer2 not delayed",
     lambda: 10 + 3, "RR fire 10..13 ms; max Timer2 interval <= 1.1 period (sim only)"),
    ("prio_wdt_preempts", 0x5F, "stuck EXINT0 (0x5F) / stuck Timer0 handler (0x24): WDT warning (high) preempts, PC captured; "
     "IP = 0x81 (EXINT0 high): no preemption, hardware reset", lambda: reset_ms() + CMD_MS,
     "capture PC in AwtoT0EvTestIsr / AwtoT0EvFire at the warning; no capture at the reset (0x24 also on the unit)"),
    ("prio_inversion", None, "shared data between Timer0, EXINT0 and main: guards listed", None, "inspection (docs/watchdog.md)"),
    ("tick_load", None, "Timer2 ISR cycles (now and on --before image), Timer0 ISR idle / fire tick, per-pass poke", None,
     "cycles measured in the fast core (sim only)"),
    ("nvsave", 0x29, "5 NVRAM saves in a row (#150): no reset", None, "flash-op sync lines, max poke gap + site"),
    ("stress", None, "saves x5, menu open / close, D3 (no signal, power saving), D2, D1 DP, D2 (#150)", None,
     "no reset; max poke gap + site, max pass (Dan sets the warning from it)"),
    ("ea_off", 0x4E, "hardware-only reset (EA off, no IRQ, no capture)", lambda: reset_ms() + CMD_MS,
     "reset; bites unchanged, warm + 1, boot WARM"),
]
EVENT_IDS = {"RX1_DP_REBUILD_PHY": 1, "RX2_HDMI_RR_RETRY": 4, "RX3_HDMI_RR_RETRY": 5, "RX5_HDMI_RR_RETRY": 7}   # enum order, this build
SHARED = (   # prio_inversion: data shared between contexts and its guard (fw/sdcc/awto_t0ev.inc)
    ("s_pusAwtoT0Ms[]", "Timer0 ISR (dec), EXINT0 (arm, cancel), main (cancel, test arm)",
     "Timer0: EA off per element; main: __critical; EXINT0: no guard needed (Timer0 same or lower level cannot preempt it)"),
    ("TR0 / TH0 / TL0", "Timer0 ISR (reload, stop), EXINT0 (start), main (clock rescale)",
     "stop check + TR0 = 0 under EA off; main under __critical; reload in the ISR (EXINT0 high in PS may start: only if TR0 = 0)"),
    ("s_usAwtoT0Rl", "Timer0 ISR, arm (start), clock rescale", "written with TR0 handling, same guards as TR0"),
    ("g_stAwtoWdt live bytes", "main pass (pass time, max), pokes (max poke: main, bounded loops), WDT IRQ (capture reads)",
     "single bytes; the capture runs with EA off and never returns"),
    ("g_ucAwtoT0Test / Arms", "main (test cmd), EXINT0 hook", "single bytes (tests only)"),
)


class Log:
    def __init__(self):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.f = LOG.open("a")

    def __call__(self, s: str):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True)
        self.f.write(line + "\n"); self.f.flush()


class SimTarget:
    """fw_sim: SimBus (HDMI D2 1080p60) booted to ACTIVE; resets from the ChipReset model."""
    name = "sim"

    def __init__(self, binp: Path, mapp: Path, say):
        import fw_sim as S
        import osd_test as T
        self.S, self.say = S, say
        self.bus = S.SimBus(binp, mapp, video="1080p60")
        self.m = self.bus.m
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        self.map_text = mapp.read_text(errors="replace")
        self.diag = T.diag_addr(mapp)
        if not self.bus.run_until_mode(3):
            raise SystemExit("sim: no ACTIVE after boot")
        self.bus.dbg_link_on()

    @property
    def io(self):
        return self.bus

    def now_ms(self) -> float:
        return self.cr.advance(self.m)

    def wait(self, s: float):
        self.bus.wait(s)

    def cmd(self, c: int) -> bool:
        a = self.diag + TESTCMD_OFF
        return self.bus.write(0x6A, 0x01, bytes([a >> 8])) and self.bus.write(0x6A, 0x03, bytes([c])) and \
            self.bus.write(0x6A, 0x3B, bytes([a & 0xFF]))

    def wait_reset(self, deadline_ms: float) -> tuple[str, float | None]:
        """('reset', ms from now to the reset) | ('none', None) within deadline_ms + RETURN_S."""
        n0, t0 = self.cr.resets, self.now_ms()
        while self.cr.resets == n0 and self.now_ms() - t0 < deadline_ms:
            self.m.run(100_000)
        if self.cr.resets == n0:
            return "none", None
        dt = self.cr.at_clock[n0] - t0
        self.reboot()
        return "reset", dt

    def reboot(self):
        used = 0
        while self.bus.mode_state() == 3 and used < 20_000_000:      # g_stModeInfo is RAM: ACTIVE stays until init rewrites it
            self.m.run(200_000); used += 200_000
        if not self.bus.run_until_mode(3):
            raise SystemExit("sim: no ACTIVE after the reset")
        self.bus.dbg_link_on()

    def soft_reset(self):
        self.cr.advance(self.m)
        self.cr.reset(self.m)
        self.reboot()

    def stage(self) -> int:
        return self.bus.diag()["stage"]

    def mode(self) -> int:
        return self.bus.mode_state()

    def uptime(self) -> int:
        return self.bus.diag_t2()

    def ddcci(self) -> bool:
        return True

    def fw_ms(self) -> float:
        """Firmware time: Timer2 ISR count (diag usT2Isr) + the running fraction of the period (TF2 pending = +1)."""
        m = self.m
        tl, th, rl, rh = *m.rd(0xCC, 2, "sfr"), *m.rd(0xCA, 2, "sfr")
        cnt, rc = th << 8 | tl, rh << 8 | rl
        frac = min(max((cnt - rc) / (0x10000 - rc), 0.0), 1.0) if rc else 0.0
        return self.bus.diag_t2() + (1 if m.rd(0xC8, 1, "sfr")[0] & 0x80 else 0) + frac

    def watch(self, name: str, fn):
        """fn(regs) at each entry of _name (no change to the run); a name missing from the map raises."""
        self.m.stub(name, lambda m_, r: (fn(r), None)[1])

    def unwatch(self, name: str):
        """drop only this name's stubs: another bank's stub can sit at the same 16-bit PC"""
        v = self.m.sym["_" + name] & 0xFFFF
        self.m.stubs[v] = [s for s in self.m.stubs.get(v, []) if s[1] != name]
        if not self.m.stubs[v]:
            del self.m.stubs[v]
        self.m._restub(v)

    def run_ms(self, ms: float, step: int = 5_000):
        t0 = self.fw_ms()
        while (self.fw_ms() - t0) % 65536 < ms:
            self.m.run(step)

    def sfr(self, a: int, v: int | None = None) -> int:
        if v is not None:
            self.m.wr(a, bytes([v]), "sfr")
        return self.m.rd(a, 1, "sfr")[0]

    def close(self):
        self.bus.close()


class UnitTarget:
    """Unit over I2C: debug slave 0x35 (dbg_link on), resets seen as a link drop, timed by the diag uptime."""
    name = "unit"

    def __init__(self, unit: str, mapp: Path, say):
        import i2cbus
        import kvm
        import rtd_i2c_bridge as B
        import dbg_link
        self.say, self.i2cbus, self.dbg_link, self.B = say, i2cbus, dbg_link, B
        u = json.loads((ROOT / "scripts/devices.json").read_text())["units"][unit]
        if not u.get("test"):
            raise SystemExit(f"unit {unit} is not a test unit (devices.json test=false)")
        self.bus_n = kvm.find_bus(u)
        if self.bus_n is None:
            raise SystemExit(f"unit {unit} ({u['serial']}): no bus with its EDID serial and DDC/CI")
        i2cbus.require_unit(self.bus_n, u["serial"])
        if i2cbus.rate_khz() != 100:
            raise SystemExit(f"bus rate {i2cbus.rate_khz()} kHz; 0x35 runs at 100 kHz only")
        self.logs = B.setup_logs("wdt_test", map=str(mapp), detail=True)   # decoded I2C -> wdt_test.detail.log, bytes -> .raw.log
        self.map_text = mapp.read_text(errors="replace")
        m = re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stAwtoDiag\b", self.map_text, re.M)
        self.diag = int(m.group(1), 16) & 0xFFFF if m else 0xF6D0
        self.serial = u["serial"]
        self.link()
        self.io = B.Real(self.bus_n, allow_write=True)

    def link(self):
        st = self.dbg_link.on(self.bus_n)
        if st not in ("swapped", "already"):
            raise SystemExit(f"debug link: {st}")

    def now_ms(self) -> float:
        return time.monotonic() * 1000

    def wait(self, s: float):
        time.sleep(s)

    def cmd(self, c: int) -> bool:
        a = self.diag + TESTCMD_OFF
        return self.io.write(0x6A, 0x01, bytes([a >> 8])) and self.io.write(0x6A, 0x03, bytes([c])) and \
            self.io.write(0x6A, 0x3B, bytes([a & 0xFF]))

    def alive(self) -> bool:
        """One byte read of the diag magic 'A' (byte path: 0x01 hi, 0x3A lo, read 0x08)."""
        a = self.diag
        if not (self.io.write(0x6A, 0x01, bytes([a >> 8])) and self.io.write(0x6A, 0x3A, bytes([a & 0xFF]))):
            return False
        r = self.io.read(0x6A, 0x08, 1)
        return r == b"A"

    def stage(self) -> int:
        import dbg_xdata as X
        b = X.read_bytes(self.io, self.diag + 0x03, 1)
        return b[0] if b else 0

    def ddcci(self) -> bool:
        import kvm
        return kvm._ddcci_acks(self.bus_n)

    def mode(self) -> int | None:
        import dbg_xdata as X
        m = re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stModeInfo\b", self.map_text, re.M)
        b = X.read_bytes(self.io, int(m.group(1), 16) & 0xFFFF, 1) if m else None
        return b[0] & 0x1F if b else None

    def uptime(self) -> int | None:
        return self.uptime_ms()

    def uptime_ms(self) -> int | None:
        import dbg_xdata as X
        b = X.read_bytes(self.io, self.diag + 0x16, 2)
        return None if b is None else b[0] << 8 | b[1]

    def wait_reset(self, deadline_ms: float) -> tuple[str, float | None]:
        """('reset', ms from now to the first failed 0x35 read, POLL_S polls) | ('none', None) | ('hang', None) = DDC/CI 0x37
        silent for RETURN_S after the expected reset | ('nolink', None) = 0x37 back, 0x35 not. last_up_dt: reset time from
        the diag uptime (for EA-off hangs, where 0x35 drops at the hang, not at the reset)."""
        t0 = self.now_ms()
        drop = None
        self.last_up_dt = None
        while self.now_ms() - t0 < deadline_ms:
            if not self.alive():
                drop = self.now_ms()
                break
            time.sleep(POLL_S)
        if drop is None:
            return "none", None
        self.say(f"  first failed 0x35 read {drop - t0:.0f} ms after the command (poll {POLL_S * 1000:.0f} ms)")
        import kvm
        end = t0 + deadline_ms + RETURN_S * 1000
        while self.now_ms() < end and not kvm._ddcci_acks(self.bus_n):
            time.sleep(0.05)                     # 50 ms: one DDC/CI probe
        if not kvm._ddcci_acks(self.bus_n):
            return "hang", None
        back = self.relink(self.now_ms() + RETURN_S * 1000)
        if back is None:
            return "nolink", None
        up = self.uptime_ms()
        if up is not None and up < back - t0:
            self.last_up_dt = back - up - t0
        return "reset", drop - t0

    def relink(self, end_ms: float) -> float | None:
        """After a reset: wait for DDC/CI 0x37 (the firmware's main loop runs), then debug link on, retried until 0x35
        answers; NAKs while it boots are expected. Returns the time 0x35 answered, None if not by end_ms."""
        import kvm
        while self.now_ms() < end_ms and not kvm._ddcci_acks(self.bus_n):
            time.sleep(0.05)                     # 50 ms: one DDC/CI probe; boot to the main loop ~0.3-0.5 s (docs/delays.md)
        while self.now_ms() < end_ms:
            try:
                if self.dbg_link.on(self.bus_n, 10) in ("swapped", "already") and self.alive():
                    return self.now_ms()
            except (OSError, SystemExit):
                pass
            time.sleep(0.1)
        return None

    def soft_reset(self):
        from rtd_flash_sector import Rtd
        isp = Rtd(self.bus_n)
        isp.write(0x6F, 0x80)
        isp.write(0xEE, 0x02)                    # rtd_reset.py: ISP enable, scaler reset
        t0 = self.now_ms()
        while self.now_ms() - t0 < 2000 and self.alive():
            time.sleep(0.02)                     # the reset drops 0x35 within one main-loop pass
        if self.relink(self.now_ms() + RETURN_S * 1000) is None:
            raise SystemExit("unit not back 5 s after the ISP reset")

    def close(self):
        try:
            self.dbg_link.off(self.bus_n)
        except (Exception, SystemExit) as e:             # the summary is already out; a link left on times out by itself
            self.say(f"  debug link off failed: {e!r}")
        finally:
            self.io.close()
            self.logs.close()


class Runner:
    def __init__(self, t, say, a):
        self.t, self.say, self.a = t, say, a
        self.addr, self.syms = C.map_addr(t.map_text), C.load_syms(t.map_text)
        self.rows = []

    def rec(self, tries: int = 5) -> dict:
        for _ in range(tries):
            b = C.read(self.t.io, self.addr)
            if b is not None:
                d = C.decode(b)
                self.say(f"  record: {C.line(d, self.syms)}")
                return d
            self.t.wait(0.3)
        raise OSError("record read failed (0x35 silent)")

    WANT = {"cold": "cold", "stall": "watchdog bite", "ea_off": "no capture", "probe": "probe",
            "clear": "cold", "prio": "watchdog bite"}            # cause words, not the exact text

    def after_reset(self, label: str):
        """#29: snapshot + first sync-log line of this boot (images that have them)"""
        sa = C.snap_addr(self.t.map_text)
        if sa is not None:
            import dbg_xdata as X
            s = C.snap_decode(X.read_blocks(self.t.io, sa, C.SNAP_N))
            self.snaps = getattr(self, "snaps", []) + [(label, s)]
            self.say(f"  snapshot after {label}: {C.snap_line(s)}")
        if self.has("AwtoBootReason"):
            import sync_log as SL
            import dbg_xdata as X
            SL.set_map(self.a.map_path)
            ring = int(re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stAwtoSync\b", self.t.map_text, re.M).group(1), 16) & 0xFFFF
            raw = X.read_blocks(self.t.io, ring, SL.HDR + SL.N * SL.EV)
            _, lines = SL.decode(raw, SL.load_rows(SL.tsv_for(self.a.map_path))) if raw else ({}, [])
            got = lines[0].split(" ms ", 1)[-1] if lines else "(no line)"
            want = self.WANT.get(label.split("-")[0], "boot:")
            self.reasons = getattr(self, "reasons", []) + [(want, got)]
            self.say(f"  first sync line after {label}: {got}")

    def has(self, sym: str) -> bool:
        return re.search(rf"\b_{sym}\b", self.t.map_text) is not None

    def row(self, name, verdict, detail):
        self.rows.append((name, verdict, detail))
        self.say(f"{verdict:4s} {name}: {detail}")

    def hang_case(self, name, cmd, want_ms, lo_ms):
        dl = 1.25 * want_ms
        before = self.rec()
        self.say(f"  cmd 0x{cmd:02X}; reset expected {lo_ms:.1f}..{want_ms:.1f} ms, deadline 1.25 x {want_ms:.1f} = {dl:.0f} ms")
        if not self.t.cmd(cmd):
            return self.row(name, "FAIL", "test cmd NAK"), None, None
        kind, dt = self.t.wait_reset(dl)
        if kind != "reset":
            why = {"hang": "DDC/CI 0x37 silent 5 s after the expected reset: POWER-CYCLE UNIT 2",
                   "nolink": "monitor back (0x37), debug link 0x35 not re-established", "none": f"no reset by {dl:.0f} ms"}
            return self.row(name, "HANG" if kind == "hang" else "FAIL", why.get(kind, kind)), None, None
        after = self.rec()
        self.after_reset(name)
        return None, (before, after, dt), dl

    def site(self) -> str:
        sa = C.site_addr(self.t.map_text)
        if sa is None:
            return "site n/a"
        import dbg_xdata as X
        b = X.read_bytes(self.t.io, sa, 1)
        return f"ended by {C.SITES.get(b[0], b[0])}" if b else "site ?"

    def ages(self, d) -> str:
        poke = ">=586" if d["max_poke"] == 255 else str(round(d["max_poke"] * C.POKE_MS))
        return f"max pass {d['max_pass'] * 32} ms, max poke gap {poke} ms {self.site()} (warning at {warn_ms():.1f} ms)"

    def settle(self):
        """before a case: past the first main-loop pass (stage >= 6), mode settled, DDC/CI answering; SETTLE_S deadline"""
        t0 = time.monotonic()
        st = md = None
        while time.monotonic() - t0 < SETTLE_S:
            try:
                st, md = self.t.stage(), self.t.mode()
                if st >= 6 and md in SETTLED_MODES and self.t.ddcci():
                    return True
            except (OSError, SystemExit, TypeError):
                pass
            self.t.wait(0.2)
        self.say(f"  not settled within {SETTLE_S} s (stage {st}, mode {md})")
        return False

    def same_boot(self, before: dict, up0: int | None, host0: float) -> tuple[bool, str]:
        """no reset since `before`: record bites / warm unchanged and the diag uptime moved on (0x35 may be silent for a
        flash op: reads retried for FLASH_OP_MS)"""
        end = time.monotonic() + FLASH_OP_MS / 1000.0
        up = d = None
        while up is None or d is None:
            try:
                up = self.t.uptime() if up is None else up
                d = self.rec(tries=1) if d is None else d
            except (OSError, SystemExit):
                pass
            if (up is None or d is None) and time.monotonic() > end:
                break
            if up is None or d is None:
                self.t.wait(0.05)
        if up is None or d is None:
            return False, "no answer"
        dt_host = (time.monotonic() - host0) * 1000
        cont = up0 is None or ((up - up0) & 0xFFFF) >= dt_host * 0.5
        ok = d["bites"] == before["bites"] and d["warm"] == before["warm"] and cont
        return ok, f"uptime {up0}->{up} in {dt_host:.0f} ms host, bites {before['bites']}->{d['bites']} warm {before['warm']}->{d['warm']}"

    def c_nvsave(self):
        """#150: 5 NVRAM saves in a row (test cmd 0x29: debug messages off, saved), 1 s apart: no reset"""
        d0 = self.rec()
        fh = next((x for x in getattr(getattr(self.t, "m", None), "devs", []) if type(x).__name__ == "FlashHalt"), None)
        if fh:
            fh.use_max, n0 = True, len(fh.halts)        # sim: every flash op at its datasheet max (long save)
        kinds = []
        for k in range(5):
            up0, h0 = self.t.uptime(), time.monotonic()
            self.t.cmd(0x29)
            self.t.wait(NVSAVE_GAP_MS / 1000.0)
            same, why = self.same_boot(d0, up0, h0)
            kinds.append("none" if same else "reset")
            self.say(f"  save {k + 1}: {'same boot' if same else 'RESET?'} ({why})")
        if fh:
            fh.use_max = False
            hs = fh.halts[n0:]
            self.say(f"  sim flash halts: {len(hs)} ops, {sum(h[1] for h in hs):.0f} ms, counted by the WDT: "
                     f"{sum(h[1] for h in hs if h[2]):.0f} ms (FFEA[5] {'off' if any(h[2] for h in hs) else 'on'})")
        d1 = self.rec()
        ok = all(k == "none" for k in kinds) and d1["bites"] == d0["bites"] and d1["warm"] == d0["warm"]
        nv = self.nv_lines()
        self.row("nvsave", "PASS" if ok else "FAIL", f"5 saves: {kinds}; {self.ages(d1)}; flash ops {nv}")

    def nv_lines(self) -> str:
        """#150 sync lines of the NVRAM saves (ms since the last poke at each step)"""
        if not self.has("AwtoNvEv"):
            return "n/a"
        import sync_log as SL
        import dbg_xdata as X
        ring = int(re.search(r"^(?:D:\s+|\s+)([0-9A-Fa-f]{8})\s+_g_stAwtoSync\b", self.t.map_text, re.M).group(1), 16) & 0xFFFF
        raw = None
        for _ in range(5):                               # flash-op silences: retry
            raw = X.read_blocks(self.t.io, ring, SL.HDR + SL.N * SL.EV)
            if raw:
                break
            self.t.wait(FLASH_OP_MS / 1000.0)
        _, lines = SL.decode(raw, SL.load_rows(SL.tsv_for(self.a.map_path)), whole=True) if raw else ({}, [])
        nv = [ln for ln in lines if "NVRAM" in ln or "flash erase" in ln]
        for ln in nv:
            self.say(f"    {ln}")
        return f"{len(nv)} lines (log)"

    def c_stress(self):
        """#150: saves, menu, input switches D2 / D3 / D1, no-signal power saving and back; max poke gap with its site"""
        d0 = self.rec()
        steps = [(0x29, 1.0)] * 5 + [(0x01, 1.0), (0x04, 0.5), (0x05, 1.0), (0x33, 8.0), (0x32, 6.0), (0x31, 6.0), (0x32, 6.0)]
        kinds = []
        for c, s in steps:
            up0, h0 = self.t.uptime(), time.monotonic()
            self.t.cmd(c)
            self.t.wait(s)
            same, why = self.same_boot(d0, up0, h0)
            kinds.append("none" if same else "reset")
            self.say(f"  step 0x{c:02X}: {'same boot' if same else 'RESET?'} ({why})")
        d1 = self.rec()
        ok = all(k == "none" for k in kinds) and d1["bites"] == d0["bites"] and d1["warm"] == d0["warm"]
        self.row("stress", "PASS" if ok else "FAIL", f"{len(steps)} steps, resets {sum(k != 'none' for k in kinds)}; {self.ages(d1)}")

    def c_baseline(self):
        if not getattr(self, "_cold_done", False):
            self._cold_done = True
            self.after_reset("cold" if self.t.name == "sim" else "current")
        d0 = self.rec()
        self.t.cmd(0x29)                            # debug messages off: an NVRAM save (flash erase + program) inside the window
        kind, _ = self.t.wait_reset(self.a.baseline_s * 1000)
        d1 = self.rec()
        ok = kind == "none" and d1["bites"] == d0["bites"] and d1["warm"] == d0["warm"]
        self.row("baseline", "PASS" if ok else "FAIL", f"{self.a.baseline_s:.0f} s, {kind}; {self.ages(d1)}")

    def c_stall(self):
        bad, r, dl = self.hang_case("stall", 0x4C, warn_ms() + CMD_MS, warn_ms())
        if bad is not None or r is None:
            return
        before, after, dt = r
        sym = C.symbolize(self.syms, after["bank"], after["pc"])
        ok = (warn_ms() - 50 <= dt <= dl and after["valid"] and after["bites"] == before["bites"] + 1
              and after["cause"] & 0xBF == 0x81 and sym.startswith("AwtoWdtHang+"))
        self.row("stall", "PASS" if ok else "FAIL", f"reset {dt:.1f} ms after the cmd; cause 0x{after['cause']:02X}, "
                 f"bites {before['bites']} -> {after['bites']}, PC {C.where(after, after['pc'])} {sym}")

    def c_pass(self):
        if self.has("AwtoWdtCheck"):
            return self.row("pass", "SKIP", "pre-#138 image: 0x4D = the #131 PASS hang (5.4 s); not run here")
        self.t.cmd(0x4D)
        kind, _ = self.t.wait_reset(3000)
        self.row("pass", "PASS" if kind == "none" else "FAIL", f"0x4D ignored by design: {kind} in 3 s")

    def c_probe(self):
        if not self.has("AwtoWdtProbe"):
            return self.row("probe", "SKIP", "image without AwtoWdtProbe (pre-#138)")
        for cmd, mode in ((0x49, "normal"), (0x4F, "timer")):
            want = PROBE_SPIN_MS + CMD_MS
            self.say(f"  probe cmd 0x{cmd:02X} ({mode} mode): IRQ expected 36.6 ms, reset 585.9 ms; deadline 1.25 x {want} ms")
            self.t.cmd(cmd)
            kind, dt = self.t.wait_reset(1.25 * want)
            if kind == "hang":
                return self.row("probe", "HANG", f"{mode}: link gone, unit not back: POWER-CYCLE UNIT 2")
            if kind == "none":
                self.t.wait(0.2)
            d = self.rec()
            if kind == "reset":
                self.after_reset(f"probe-{mode}")
            got = "|".join(n for bit, n in C.PROBE if d["probe"] & bit)
            decided = bool(d["probe"] & 0x18)
            self.row(f"probe-{mode}", "PASS" if decided else "FAIL",
                     f"{kind}{'' if dt is None else f' at {dt:.0f} ms'}; probe 0x{d['probe']:02X} {got}")

    def c_snapshot(self):
        if not self.has("g_stAwtoSnap"):
            return self.row("snapshot", "SKIP", "image without the reset-vector snapshot (_g_stAwtoSnap, #29 task 5)")
        snaps = getattr(self, "snaps", [])
        ok = bool(snaps) and all(s is not None for _, s in snaps)
        self.row("snapshot", "PASS" if ok else "FAIL", f"{len(snaps)} snapshots ({', '.join(k for k, _ in snaps)}); "
                 f"differs between them: {C.snap_diff([s for _, s in snaps])}")

    def c_reason(self):
        if not self.has("AwtoBootReason"):
            return self.row("reason", "SKIP", "image without the #29 boot reason line")
        reasons = getattr(self, "reasons", [])
        ok = bool(reasons) and all(want in got for want, got in reasons)
        self.row("reason", "PASS" if ok else "FAIL", "; ".join(f"{w!r} in {g!r}" for w, g in reasons) or "no reboot seen")

    def c_clear(self):
        ok1 = C.clear(self.t.io, self.addr)
        d = self.rec()
        ok1 = ok1 and not d["valid"]
        self.t.soft_reset()
        d2 = self.rec()
        self.after_reset("clear")
        ok = ok1 and d2["valid"] and d2["bites"] == 0
        self.row("clear", "PASS" if ok else "FAIL", f"after clear valid={d['valid']}; after a soft reboot valid={d2['valid']} "
                 f"bites {d2['bites']} warm {d2['warm']}")

    def c_ea_off(self):
        self.say("!!! ea_off: interrupts off on the unit. If no reset comes by the deadline + 5 s, Dan must power-cycle unit 2.")
        bad, r, dl = self.hang_case("ea_off", 0x4E, reset_ms() + CMD_MS, reset_ms())
        if bad is not None or r is None:
            return
        before, after, dt = r
        if getattr(self.t, "last_up_dt", None) is not None:
            self.say(f"  unit: 0x35 dropped at the hang ({dt:.0f} ms, EA off); reset time from the diag uptime")
            dt = self.t.last_up_dt
        ok = (reset_ms() - 50 <= dt <= dl and after["bites"] == before["bites"] and after["warm"] == before["warm"] + 1
              and after["boot"] & 0x10)
        self.row("ea_off", "PASS" if ok else "FAIL", f"reset {dt:.1f} ms after the cmd; bites {before['bites']} -> {after['bites']}, "
                 f"warm {before['warm']} -> {after['warm']}, boot 0x{after['boot']:02X}")

    # ---- interrupt-model cases (sim: the fast core models DW8051 IP/EIP levels, natural order, EXINT2) ----
    def _sim(self, name) -> bool:
        if self.t.name != "sim":
            self.row(name, "SKIP", "sim only (needs the fire instant / cycle counts)")
            return False
        if not self.has("AwtoT0EvFire"):
            self.row(name, "SKIP", "image without the Timer0 scheduler (pre-#138)")
            return False
        if not getattr(self, "_hooked", False):
            self._hooked, self.fired, self.armed, self.t2_at, self.isr_arm = True, [], [], [], []
            t = self.t
            t.watch("AwtoT0EvFire", lambda r: self.fired.append((r["r"][7] if t.m.keil else r["a1"] & 255, t.fw_ms())))
            t.watch("AwtoT0EvTest", lambda r: self.armed.append(t.fw_ms()))
            self._ip_back = None
            t.watch("AwtoT0EvTestIsr", lambda r: self._on_hook())
        return True

    def _on_hook(self):
        self.isr_arm.append(self.t.fw_ms())

    def _ip_restore(self):
        """IP back once no interrupt is active (main context, as the SDK changes it): restoring it inside EXINT0 flips
        ScalerTimerPollingFlagProc_EXINT0 to its g_usTimerCounter branch while Timer2 cannot preempt -> endless poll"""
        if self._ip_back is None:
            return
        k = 0
        while self.t.m.p.nlvl and k < 20_000:
            self.t.m.run(20); k += 1
        self.t.sfr(0xB8, self._ip_back)
        self._ip_back = None

    def _timed(self, cmd, want, budget_ms=200.0):
        """send cmd, run until len(want) fires or budget; [(name, ms, fired id, dt)]"""
        self.fired.clear(); self.armed.clear()
        self.t.cmd(cmd)
        t0 = self.t.fw_ms()
        while len(self.fired) < len(want) and (self.t.fw_ms() - t0) % 65536 < budget_ms + CMD_MS:
            self.t.m.run(5_000)
        out = []
        for k, (name, ms) in enumerate(want):
            f = self.fired[k] if k < len(self.fired) else (None, None)
            dt = None if f[1] is None or not self.armed else (f[1] - self.armed[0]) % 65536
            out.append((name, ms, f[0], dt))
        return out

    def _judge(self, case, label, res):
        bad = 0
        for name, ms, fid, dt in res:
            ok = dt is not None and abs(dt - ms) <= 0.10 * ms and fid == EVENT_IDS[name]
            bad += not ok
            self.say(f"  {'ok ' if ok else 'BAD'} {label} {name} {ms} ms -> id {fid} after {dt if dt is None else round(dt, 2)} ms")
        return bad

    def c_t0_timing(self):
        if not self._sim("t0_timing"):
            return
        bad, txt = 0, []
        for cmd, label, want in ((0x2A, "M2PLL", [("RX1_DP_REBUILD_PHY", 30)]), (0x2B, "M2PLL", [("RX2_HDMI_RR_RETRY", 10)]),
                                 (0x2C, "M2PLL", [("RX3_HDMI_RR_RETRY", 10)]), (0x5A, "PS reload", [("RX1_DP_REBUILD_PHY", 30)]),
                                 (0x5B, "PS reload", [("RX2_HDMI_RR_RETRY", 10)])):
            r = self._timed(cmd, want)
            bad += self._judge("t0_timing", label, r)
            txt += [f"{label} {n} {d if d is None else round(d, 2)}" for n, _, _, d in r]
        self.row("t0_timing", "PASS" if not bad else "FAIL", "; ".join(txt) + " ms (sim)")

    def c_t0_clock_switch(self):
        if not self._sim("t0_clock_switch"):
            return
        bad, txt = 0, []
        for cmd, want in ((0x2E, [("RX1_DP_REBUILD_PHY", 30)]), (0x2F, [("RX2_HDMI_RR_RETRY", 10)])):
            r = self._timed(cmd, want)
            bad += self._judge("t0_clock_switch", "switch", r)
            txt += [f"{n} {d if d is None else round(d, 2)}" for n, _, _, d in r]
        self.row("t0_clock_switch", "PASS" if not bad else "FAIL", "; ".join(txt) + " ms (sim)")

    def c_t0_multi(self):
        if not self._sim("t0_multi"):
            return
        r1 = self._timed(0x2D, [("RX2_HDMI_RR_RETRY", 10), ("RX1_DP_REBUILD_PHY", 30)])
        bad = self._judge("t0_multi", "two", r1)
        r2 = self._timed(0x5C, [("RX2_HDMI_RR_RETRY", 5), ("RX1_DP_REBUILD_PHY", 30)])
        bad += self._judge("t0_multi", "3-cancel", r2)
        self.t.run_ms(30)                               # the cancelled RR D3 (10 ms) must stay silent
        extra = [f for f in self.fired if f[0] == EVENT_IDS["RX3_HDMI_RR_RETRY"]]
        bad += bool(extra)
        self.row("t0_multi", "PASS" if not bad else "FAIL",
                 f"two pending {[round(x[3] or -1, 2) for x in r1]} ms; out of order {[(x[0], round(x[3] or -1, 2)) for x in r2]} ms; "
                 f"cancelled RR D3 fired {len(extra)}x (sim)")

    def _arm_cmd(self, c: int):
        """test cmd that enters AwtoT0EvTest; returns once it ran (consumed by a main-loop pass, ~CMD_MS)"""
        self.armed.clear()
        self.t.cmd(c)
        t0 = self.t.fw_ms()
        while not self.armed and (self.t.fw_ms() - t0) % 65536 < 3 * CMD_MS:
            self.t.m.run(2_000)
        self.t.run_ms(2)

    def _mode(self, c: int, want: int):
        """EXINT0 test-hook mode by test cmd; returns once g_ucAwtoT0Test reads want"""
        a = self.t.m.addr("g_ucAwtoT0Test")
        self.t.cmd(c)
        t0 = self.t.fw_ms()
        while self.t.m.rd(a)[0] != want and (self.t.fw_ms() - t0) % 65536 < 3 * CMD_MS:
            self.t.m.run(2_000)

    def _exint0(self):
        """raise EXINT0 (TCON.IE0) as a scaler IRQ would"""
        self.t.sfr(0x88, self.t.sfr(0x88) | 0x02)

    def c_t0_arm_from_isr(self):
        if not self._sim("t0_arm_from_isr"):
            return
        t, bad, txt = self.t, 0, []
        ip0 = t.sfr(0xB8)

        only = os.environ.get("WDT_TEST_SUB")          # debug: run only the sub-cases whose label starts with these (comma list)

        def one(label, setup):
            nonlocal bad
            if only and not any(label.startswith(x) for x in only.split(",")):
                return
            self._mode(0x5D, 1)                         # the hook arms once per test cmd
            self.fired.clear(); self.isr_arm.clear()
            setup()
            t0 = t.fw_ms()
            while (t.fw_ms() - t0) % 65536 < 40:
                t.m.run(2_000)
            rr = [f for f in self.fired if f[0] == EVENT_IDS["RX2_HDMI_RR_RETRY"]]
            dts = [round((rr[k][1] - self.isr_arm[k]) % 65536, 2) for k in range(min(len(rr), len(self.isr_arm)))]
            lo = 9.0
            ok = len(rr) == len(self.isr_arm) == 1 and all(lo <= d <= 11.0 for d in dts)
            bad += not ok
            txt.append(f"{label}: arms {len(self.isr_arm)} fires {len(rr)} at {dts} ms")
            self.say(f"  {'ok ' if ok else 'BAD'} {txt[-1]}")
        one("EXINT0 alone", self._exint0)
        hit = []

        def during_t0():                                # IE0 raised at a Timer0 ISR entry, a 30 ms event keeps Timer0 ticking
            t.watch("AwtoT0EvIsr", lambda r: (not hit) and (hit.append(1) or self._exint0()))
            self._arm_cmd(0x2A)
        one("IE0 during the Timer0 ISR", during_t0)
        hit.append(1)                                   # stub stays; disarmed

        def both():                                     # IE0 just before Timer0 overflows: both pending, EX0 served first
            self._arm_cmd(0x2A)                         # Timer0 ticking (30 ms event)
            k = 0
            while (t.sfr(0x8C) << 8 | t.sfr(0x8A)) < 0xFFC0 and k < 50_000:     # within 64 counts of the overflow
                t.m.run(1); k += 1
            self._exint0()
        one("TF0 + IE0 together", both)
        # SDK power-saving swap (EXINT0 high, Timer2 low) from the Timer0 ISR entry to the hook's arm
        def ip81():
            hit.clear()
            t.unwatch("AwtoT0EvIsr")
            ta = t.m.addr("g_ucAwtoT0Test")

            def trig(r):
                if not hit:
                    hit.append(1)
                    t.m.wr(ta, b"\x01")                 # hook mode 1 right here (a natural EXINT0 may have used it)
                    self._ip_back = t.sfr(0xB8)
                    t.sfr(0xB8, 0x81)
                    self._exint0()
            t.watch("AwtoT0EvIsr", trig)
            self._arm_cmd(0x2A)
            self._ip_restore()
        one("IP 0x81: EXINT0 preempts Timer0", ip81)
        t.sfr(0xB8, ip0)
        self._mode(0x25, 0)
        self.row("t0_arm_from_isr", "PASS" if not bad else "FAIL", "; ".join(txt) + f" (sim; IP restored 0x{ip0:02X})")

    def c_prio_t0_vs_exint(self):
        if not self._sim("prio_t0_vs_exint"):
            return
        t = self.t
        ticks = []
        t.watch("SysTimerIntProc2", lambda r: ticks.append(t.m.ticks // 12))
        self.fired.clear(); self.armed.clear()
        self._mode(0x5E, 2)
        t.cmd(0x2B)
        t0 = t.fw_ms()
        while not self.armed and (t.fw_ms() - t0) % 65536 < CMD_MS * 2:
            t.m.run(2_000)
        t.run_ms(4)
        ticks.clear()
        self._exint0()                                  # 2..3 ms spin in EXINT0 (low) while RR D2 is pending
        t1 = t.fw_ms()
        while not self.fired and (t.fw_ms() - t1) % 65536 < 30:
            t.m.run(2_000)
        dt = (self.fired[0][1] - self.armed[0]) % 65536 if self.fired and self.armed else None
        t.unwatch("SysTimerIntProc2")
        per = 0x10000 - (t.sfr(0xCB) << 8 | t.sfr(0xCA))
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        mx = max(gaps) / per if gaps else None
        ok = dt is not None and 9.0 <= dt <= 13.0 * 1.1 and mx is not None and mx <= 1.1
        self.row("prio_t0_vs_exint", "PASS" if ok else "FAIL",
                 f"RR D2 10 ms fired after {dt if dt is None else round(dt, 2)} ms with a 2-3 ms EXINT0 spin (bound 10..14.3); "
                 f"Timer2 max interval {mx if mx is None else round(mx, 3)} x period over {len(gaps)} ticks (sim)")

    def c_prio_wdt_preempts(self):
        if not self.has("AwtoT0EvTestIsr"):
            return self.row("prio_wdt_preempts", "SKIP", "image without the interrupt test hooks")
        sim = self.t.name == "sim"
        txt, bad = [], 0
        runs = ([("stuck EXINT0", 0x5F, True, "AwtoT0EvTestIsr+", None)] if sim else []) + \
               [("stuck Timer0 handler", 0x24, False, "AwtoT0EvFire+", None)]
        if sim:
            runs.append(("stuck EXINT0, IP 0x81", 0x5F, True, None, 0x81))
        for label, cmd, trig, where, ip in runs:
            before = self.rec()
            if ip is not None:
                self.t.sfr(0xB8, ip)
            if trig:
                self._mode(cmd, 3)
                self._exint0()
            else:
                self.t.cmd(cmd)
            want = warn_ms() if where else reset_ms()
            kind, dt = self.t.wait_reset(1.25 * (want + CMD_MS))
            if kind != "reset":
                bad += 1; txt.append(f"{label}: {kind}" + (" POWER-CYCLE UNIT 2" if kind == "hang" else "")); continue
            d = self.rec()
            self.after_reset("prio" if where else "ea_off")
            sym = C.symbolize(self.syms, d["bank"], d["pc"])
            if where:
                ok = d["bites"] == before["bites"] + 1 and sym.startswith(where)
                txt.append(f"{label}: warning capture {dt:.0f} ms, PC {sym}")
            else:
                ok = d["bites"] == before["bites"] and d["warm"] == before["warm"] + 1
                txt.append(f"{label}: no capture, hardware reset {dt:.0f} ms, warm {before['warm']} -> {d['warm']}")
            bad += not ok
            self.say(f"  {'ok ' if ok else 'BAD'} {txt[-1]}")
        self.row("prio_wdt_preempts", "PASS" if not bad else "FAIL", "; ".join(txt) + (" (sim)" if sim else " (unit)"))

    def c_prio_inversion(self):
        for v, who, guard in SHARED:
            self.say(f"  {v}: {who} -> {guard}")
        self.row("prio_inversion", "INFO", f"{len(SHARED)} shared items, guards listed (inspection)")

    def _cycles(self, name: str, n: int, max_steps: int = 50_000) -> list[int]:
        """machine cycles of n calls / interrupts of _name: entry stub -> SP back below the stacked return address
        (RET / RETI, nested higher-priority interrupts included). Single-steps the fast core."""
        m = self.t.m
        v = m.sym["_" + name] & 0xFFFF
        out, cur = [], [None]
        m.stub(name, lambda m_, r: cur.__setitem__(0, (m_.p.cycles, m_.core.sfr[0x01])) or m_.request_stop() or None)
        while len(out) < n:
            cur[0] = None
            m.run(2_000_000)
            if cur[0] is None:
                break
            (c0, sp0), k = cur[0], 0
            while k < max_steps:
                m.run(1); k += 1                        # Machine.run: serves stubs / device events on the way
                if m.core.sfr[0x01] == (sp0 - 2) & 0xFF:
                    break
            out.append(m.p.cycles - c0)
        self.t.unwatch(name)
        return out

    def c_tick_load(self):
        if self.t.name != "sim":
            return self.row("tick_load", "SKIP", "sim only (cycle counts)")
        t2 = self._cycles("SysTimerIntProc2", 200)
        txt = f"Timer2 ISR {min(t2)}..{max(t2)} cycles, mean {sum(t2) / len(t2):.0f} (n {len(t2)})"
        mp = self._cycles("AwtoDiagMainPass", 50)
        txt += f"; AwtoDiagMainPass {min(mp)}..{max(mp)} (pass bookkeeping + poke)"
        if self.has("AwtoT0EvIsr"):
            self._arm_cmd(0x2A) if getattr(self, "_hooked", False) else self.t.cmd(0x2A)
            t0 = self._cycles("SysTimerIntProc0", 30)
            txt += f"; Timer0 ISR {min(t0)}..{max(t0)} over the {len(t0)} ticks of a 30 ms rebuild event (the last fires it)"
        self.row("tick_load", "INFO", txt + " (machine cycles, sim)")

    def run(self, names):
        late = [n for n in names if n in ("snapshot", "reason")]       # judged on what the other cases' resets left
        try:
            for n in [n for n in names if n not in late] + late:
                try:
                    if n not in late:
                        self.settle()
                    getattr(self, "c_" + n)()
                except (Exception, SystemExit) as e:        # one case's failure never ends the run
                    self.row(n, "FAIL", f"exception: {e!r}")
        except KeyboardInterrupt:
            self.row("run", "FAIL", "interrupted")
            self.summary()
            raise
        return self.summary()

    def summary(self) -> int:
        fails = [r for r in self.rows if r[1] in ("FAIL", "HANG")]
        self.say("---- wdt_test summary " + ("(" + self.t.name + ")"))
        for n, v, d in self.rows:
            self.say(f"  {v:4s} {n:14s} {d[:150]}")
        self.say(f"{'PASS' if not fails else 'FAIL'} wdt_test: {len(self.rows) - len(fails)}/{len(self.rows)} not failed")
        return 1 if fails else 0


def main() -> int:
    global N, THR
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", nargs=2, type=Path, metavar=("BIN", "MAP"))
    ap.add_argument("--unit")
    ap.add_argument("--map", type=Path)
    ap.add_argument("--header", type=Path, help="RL6449_Project.h of the image's tree: AWTO_WDT_N / THR (default 2 / 0xC00)")
    ap.add_argument("--cases", default=",".join(c[0] for c in CASES))
    ap.add_argument("--baseline-s", type=float, default=10.0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.header:
        t = a.header.read_text()
        N = int(re.search(r"#define AWTO_WDT_N\s+(\d+)", t).group(1))
        THR = int(re.search(r"#define AWTO_WDT_THR\s+(0x[0-9A-Fa-f]+|\d+)", t).group(1), 0)
    if a.list:
        for n, cmd, exp, worst, chk in CASES:
            w = worst() if worst else None
            dl = f"1.25 x {w:.1f} = {1.25 * w:.0f} ms" if w else "-"
            print(f"{n:9s} cmd {'-' if cmd is None else f'0x{cmd:02X}':4s} expected: {exp}; deadline {dl}; checks: {chk}")
        return 0
    a.map_path = a.sim[1] if a.sim else a.map
    names = [n for n in a.cases.split(",") if n]
    order = [c[0] for c in CASES]
    names.sort(key=order.index)                  # ea_off last (can need a power cycle)
    say = Log()
    if a.sim:
        t = SimTarget(a.sim[0], a.sim[1], say)
        say(f"wdt_test --sim {a.sim[0].name}: N {N}, THR 0x{THR:03X}: warning {warn_ms():.1f} ms, reset {reset_ms():.1f} ms")
    elif a.unit and a.map:
        t = UnitTarget(a.unit, a.map, say)
        say(f"wdt_test --unit {a.unit} bus {t.bus_n} {t.serial} map {a.map.name}: warning {warn_ms():.1f} ms, reset {reset_ms():.1f} ms")
    else:
        ap.error("--sim BIN MAP or --unit N --map MAP")
    try:
        return Runner(t, say, a).run(names)
    finally:
        t.close()


if __name__ == "__main__":
    sys.exit(main())
