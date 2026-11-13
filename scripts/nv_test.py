#!/usr/bin/env python3
"""NVRAM store + flush gate test (awto-ddc#151): the same cases in fw_sim and on unit 2.

usage: AWTO_SIM_CORE=fast nv_test.py --sim BIN [--map MAP] [--cases a,b]
       nv_test.py --unit 2 --map MAP [--cases a,b] [--reboot mains|isp]
- Store: the Realtek SDK EEPROM emulation only; SDK item saves are deferred and written by the gate (glue_nv.inc).
- Counters: g_stAwtoNv (RL6449_Project.h StAwtoNv, big-endian words): mask, why, in-DDC flash ops, deferred, flushes,
  items programmed, flash halt ops, gate inputs (stable ms, DDC/CI idle ms), erases, bytes programmed (images before
  the flush line: 16 B, erases / bytes absent).
- Cases: unchanged (no write), vcp (no write in the handler or while DDC/CI is busy; written after the gate opens),
  forced (DDC/CI busy 30 s: written anyway), switch (KVM / search switches: no write), menu (close: card + write),
  selector (cancel: nothing; a choice: stored at the gate with the card),
  power (POWER off: written at once), halt (6 x test cmd 0x3D: max poke gap), persist (unit: mains cycle, values back),
  flushlog (sync ring D4 flush lines: menu close with a change -> "wrote N B ..." matching the counter deltas; close without
  a change -> "nothing changed, no flash write"; POWER off -> a power-off flush line).
- Sim DDC/CI: ddc_sim.DdcEngine (spare IIC engine). Unit: ddcutil on the unit's bus with the debug link off, then the
  link back on to read the counters; values through the VCP mailbox (settings_cli.Box) otherwise.
- Deadlines: gate = debounce 2 s + stable 3 s, x1.25 -> 6.5 s; forced 30 s x1.25 -> 37.5 s; power flush < 1 main pass x2 -> 1 s.
Log: tmp/logs/nv_test.log (one line per step), unit I2C bytes in tmp/logs/nv_test.raw.log
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/nv_test.log"
GATE_S = 6.5            # AWTO_NV_SAVE_MS 2 s + AWTO_NV_STABLE_MS 3 s (overlap: worst = sum) x 1.25
FORCE_S = 37.5          # AWTO_NV_FORCE_MS 30 s x 1.25
POWER_S = 1.0           # flush inside UserInterfacePowerSwitch: same main pass; one pass <= 0.5 s x 2
DDC_POLL_S = 0.2        # a host polling DDC/CI (ddcutil getvcp loop) well under the 500 ms idle window
WHY = {0: "-", 1: "gate", 2: "forced", 3: "power", 4: "close", 5: "test", 6: "second BriCon/CT item"}
MASK = ((0x01, "SYS"), (0x02, "OSD"), (0x04, "BRI"), (0x08, "CT"), (0x10, "SIX"), (0x20, "PANEL"), (0x40, "AUX"))


class Log:
    def __init__(self):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.f = LOG.open("a")

    def __call__(self, s: str):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True)
        self.f.write(line + "\n"); self.f.flush()


def sym(map_text: str, name: str) -> int | None:
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{name}\b", map_text, re.M)
    return int(m.group(1), 16) & 0xFFFF if m else None


NV_SIZE = 20


def decode(b: bytes) -> dict:
    w = lambda o: b[o] << 8 | b[o + 1]
    return dict(magic=chr(b[0]), mask=b[1], why=b[2], in_ddc=b[3], defer=w(4), flush=w(6), item_wr=w(8), ops=w(10),
                stable=w(12), ddc_idle=w(14), erase=w(16), bytes=w(18))


def show(d: dict) -> str:
    m = "|".join(n for bit, n in MASK if d["mask"] & bit) or "-"
    return (f"mask {m}, last flush {WHY.get(d['why'], d['why'])}, flushes {d['flush']}, items written {d['item_wr']}, "
            f"flash ops {d['ops']}, deferred {d['defer']}, in-DDC ops {d['in_ddc']}, stable {d['stable']} ms, DDC idle {d['ddc_idle']} ms")


class Sim:
    name = "sim"

    def __init__(self, binp: Path, mapp: Path):
        import fw_sim as S
        import ddc_sim as D
        import settings_cli as SC
        self.eng = D.DdcEngine()
        self.bus = S.SimBus(binp, mapp, devs=[self.eng], video="1080p60")
        self.d = D.Mccs(self.bus, self.eng)
        self.map_text = mapp.read_text(errors="replace")
        if not self.bus.run_until_mode(3):
            raise SystemExit("sim: no ACTIVE after boot")
        self.bus.dbg_link_on()
        self.box = SC.Box(self.bus, self.map_text, sim=True)
        self.nv_a = sym(self.map_text, "g_stAwtoNv")
        self.ring_a = sym(self.map_text, "g_stAwtoSync")
        self.mapp = mapp
        import osd_test as T
        self.diag = T.diag_addr(mapp)

    def wait(self, s: float):
        self.bus.wait(s)

    def nv(self) -> dict:
        return decode(bytes(self.bus.m.rd(self.nv_a, NV_SIZE)))

    def ring(self) -> bytes:
        import sync_log as S
        return bytes(S.read_ring(self.bus.m.rd, self.ring_a))

    def cmd(self, c: int):
        a = self.diag + 0x28
        self.bus.write(0x6A, 0x01, bytes([a >> 8])); self.bus.write(0x6A, 0x03, bytes([c])); self.bus.write(0x6A, 0x3B, bytes([a & 0xFF]))

    def vcp_set(self, code: int, v: int):
        self.d.set(code, v)

    def vcp_get(self, code: int) -> int | None:
        g = self.d.get(code)
        return None if g is None else g["cur"]

    def close(self):
        self.bus.close()


class Unit:
    name = "unit"

    def __init__(self, unit: str, mapp: Path, say):
        import wdt_test as W
        import settings_cli as SC
        self.say, self.mapp = say, mapp
        self.u = W.UnitTarget(unit, mapp, say)
        self.map_text = self.u.map_text
        self.box = SC.Box(self.u.io, self.map_text)
        self.nv_a = sym(self.map_text, "g_stAwtoNv")
        self.ring_a = sym(self.map_text, "g_stAwtoSync")

    def wait(self, s: float):
        time.sleep(s)

    def nv(self) -> dict:
        import dbg_xdata as X
        for _ in range(5):                                  # silent while the MCU halts on a flash op: retry
            b = X.read_bytes(self.u.io, self.nv_a, NV_SIZE)
            if b:
                return decode(bytes(b))
            time.sleep(0.36)                                # wdt_test FLASH_OP_MS: one save's ops at datasheet max x1.25
        raise SystemExit("g_stAwtoNv: no answer")

    def cmd(self, c: int):
        self.u.cmd(c)

    def ring(self) -> bytes:
        import dbg_xdata as X
        import sync_log as S
        for _ in range(5):                                  # silent while the MCU halts on a flash op: retry
            r = S.read_ring(lambda ad, n: X.read_blocks(self.u.io, ad, n), self.ring_a)
            if r:
                return bytes(r)
            time.sleep(0.36)
        raise SystemExit("g_stAwtoSync: no answer")

    def ddcutil(self, *args) -> str:
        r = subprocess.run(["ddcutil", "--bus", str(self.u.bus_n), "--noverify", *args], capture_output=True, text=True,
                           timeout=10)                       # one ddcutil call ~0.2 s; 10 s = a stuck bus, case FAILs
        return r.stdout + r.stderr

    def vcp_set(self, code: int, v: int):
        """real DDC/CI (0x37 on the spare engine): debug link off for the call, back on after"""
        self.u.dbg_link.off(self.u.bus_n)
        try:
            self.ddcutil("setvcp", f"0x{code:02X}", str(v))
        finally:
            self.u.link()

    def vcp_get(self, code: int) -> int | None:
        r = {0x10: "brightness", 0x12: "contrast"}
        import settings_table as T
        row = next((x for x in T.ROWS if x["vcp"] == code), None)
        return self.box.get_row(row) if row else None

    def close(self):
        pass


class Run:
    def __init__(self, t, say):
        self.t, self.say, self.rows = t, say, []

    def row(self, name, res, txt):
        self.rows.append((name, res, txt))
        self.say(f"{res} {name}: {txt}")

    def settle(self, s=FORCE_S) -> dict:
        """until nothing gate-relevant is dirty (a boot migration or an earlier case may still wait)"""
        end = time.monotonic() + s if self.t.name == "unit" else None
        n, prev = 0, None
        while True:
            d = self.t.nv()
            if d["mask"] & ~0x20 == 0 and prev == (d["flush"], d["item_wr"], d["ops"]):
                return d                                 # clean and no flash op for 0.5 s (the mask clears at a flush's start)
            prev = (d["flush"], d["item_wr"], d["ops"])
            if (end and time.monotonic() > end) or (not end and n * 0.5 > s):
                return d
            self.t.wait(0.5); n += 1

    def wait_write(self, d0: dict, s: float, poll=None) -> tuple[dict, float | None]:
        """poll (DDC/CI traffic) every DDC_POLL_S while waiting; returns (counters, s until items_written moved)"""
        t, h0 = 0.0, time.monotonic()
        while t < s:
            if poll:
                poll()
            self.t.wait(DDC_POLL_S if poll else 0.25)
            t = (time.monotonic() - h0) if self.t.name == "unit" else t + (DDC_POLL_S if poll else 0.25)
            d = self.t.nv()
            if d["item_wr"] != d0["item_wr"] or d["flush"] != d0["flush"]:
                return d, t
        return self.t.nv(), None

    def c_unchanged(self):
        d0 = self.settle()
        cur = self.t.vcp_get(0x10)
        self.t.vcp_set(0x10, cur)
        d, dt = self.wait_write(d0, GATE_S)
        ok = dt is None and d["defer"] == d0["defer"] and d["mask"] & ~0x20 == 0
        self.row("unchanged", "PASS" if ok else "FAIL", f"VCP 0x10 = {cur} again: {show(d)}")

    def c_vcp(self):
        d0 = self.settle()
        cur = self.t.vcp_get(0x10)
        new = 40 if cur != 40 else 41
        self.t.vcp_set(0x10, new)
        d1 = self.t.nv()
        deferred = d1["mask"] & 0x02 and d1["item_wr"] == d0["item_wr"] and d1["in_ddc"] == 0
        busy, dt_busy = self.wait_write(d0, 2.5, poll=lambda: self.t.vcp_get(0x10))
        d, dt = self.wait_write(d0, GATE_S)
        ok = bool(deferred) and dt_busy is None and dt is not None and d["why"] == 1 and d["in_ddc"] == 0 and d["item_wr"] > d0["item_wr"]
        self.row("vcp", "PASS" if ok else "FAIL",
                 f"0x10 {cur} -> {new}: right after the set {'deferred (OSD dirty, nothing written)' if deferred else 'NOT deferred'}; "
                 f"2.5 s of DDC/CI polls: {'no write' if dt_busy is None else f'WRITE after {dt_busy:.1f} s'}; "
                 f"written {dt if dt is None else f'{dt:.2f} s'} after the polls stopped; {show(d)}")
        self.t.vcp_set(0x10, cur)

    def c_forced(self):
        d0 = self.settle()
        cur = self.t.vcp_get(0x12)
        self.t.vcp_set(0x12, 33 if cur != 33 else 34)
        d, dt = self.wait_write(d0, FORCE_S, poll=lambda: self.t.vcp_get(0x12))
        ok = dt is not None and d["why"] == 2 and dt > 0.75 * 30     # host-side count: the sim's poll replies add fw time
        self.row("forced", "PASS" if ok else "FAIL", f"DDC/CI polled every {DDC_POLL_S} s: written after "
                 f"{dt if dt is None else f'{dt:.1f} s'} ({WHY.get(d['why'])}); {show(d)}")
        self.t.vcp_set(0x12, cur)

    def c_switch(self):
        d0 = self.settle()
        steps = [(0x33, 6.0), (0x31, 6.0), (0x32, 8.0), (0x30, 8.0)]       # D3 no cable, D1, D2, auto search
        for c, s in steps:
            self.t.cmd(c)
            self.t.wait(s)
        d, dt = self.wait_write(d0, FORCE_S if self.t.name == "unit" else GATE_S)
        ok = d["item_wr"] == d0["item_wr"] and d["flush"] == d0["flush"] and d["ops"] == d0["ops"]
        self.row("switch", "PASS" if ok else "FAIL", f"KVM D3 / D1 / D2 + auto search: items written "
                 f"{d0['item_wr']} -> {d['item_wr']}, flushes {d0['flush']} -> {d['flush']}, flash ops {d0['ops']} -> {d['ops']}; {show(d)}")

    def c_menu(self):
        import settings_table as T
        d0 = self.settle()
        r = T.BY_NAME["osd_timeout"]
        cur = self.t.box.get_row(r)
        self.t.box.call(3, 2, 0)                         # MO_OPEN page 0
        self.t.box.set_row(r, 45 if cur != 45 else 50)
        self.t.box.call(3, 6, 0)                         # MO_CLOSE
        d, dt = self.wait_write(d0, GATE_S)
        ok = dt is not None and d["why"] == 4
        self.row("menu", "PASS" if ok else "FAIL", f"menu close with osd_timeout changed: written after "
                 f"{dt if dt is None else f'{dt:.2f} s'} ({WHY.get(d['why'])}); {show(d)}")
        self.t.box.set_row(r, cur)

    def c_power(self):
        d0 = self.settle()
        cur = self.t.vcp_get(0x10)
        self.t.vcp_set(0x10, 42 if cur != 42 else 43)
        self.t.cmd(0x3E)                                 # POWER key: off
        d, dt = self.wait_write(d0, POWER_S + 1.0)
        ok = dt is not None and d["why"] == 3
        self.row("power", "PASS" if ok else "FAIL", f"set then POWER off: written {dt if dt is None else f'{dt:.2f} s'} "
                 f"after ({WHY.get(d['why'])}); {show(d)}")
        self.t.cmd(0x3E)                                 # on again
        self.t.wait(8.0 if self.t.name == "unit" else 3.0)
        self.t.vcp_set(0x10, cur)

    def c_selector(self):
        """SOURCE + UP + MENU (cancel): nothing stored; SOURCE + UP + AUTO (take): the input stored with the card at the
        gate; then back (SOURCE + DOWN + AUTO). Test cmds: 0x05 SOURCE, 0x02 UP, 0x03 DOWN, 0x01 AUTO, 0x04 MENU."""
        d0 = self.settle()
        self.t.cmd(0x27); self.t.wait(0.5)               # the console (opens by itself at power-on) closed: keys reach the selector
        for c in (0x05, 0x02, 0x04):
            self.t.cmd(c); self.t.wait(0.5)
        d1, dt = self.wait_write(d0, GATE_S)
        cancel_ok = dt is None and d1["mask"] & ~0x20 == 0
        res = []
        for step in (0x02, 0x03):
            a = self.t.nv()
            self.t.cmd(0x27); self.t.wait(0.5)
            for c in (0x05, step, 0x01):
                self.t.cmd(c); self.t.wait(0.5)
            d, dt = self.wait_write(a, FORCE_S)
            res.append((dt, d["why"], d["item_wr"] - a["item_wr"]))
            self.t.wait(3.0)
        ok = cancel_ok and all(x[0] is not None and x[1] in (2, 4) for x in res)    # forced: the chosen input has no picture
        self.row("selector", "PASS" if ok else "FAIL", f"cancel: {'nothing stored' if cancel_ok else 'STORED'}; take / back: "
                 + ", ".join(f"written after {x[0] if x[0] is None else round(x[0], 1)} s ({WHY.get(x[1])}, {x[2]} items)" for x in res)
                 + f"; {show(self.t.nv())}")

    def c_halt(self):
        if self.t.name != "unit":
            return self.row("halt", "SKIP", "unit only (real flash halts)")
        import rtd_crash as C
        d0 = self.settle()
        for _ in range(6):                               # even: the inert row kvm_prefill toggles back
            self.t.cmd(0x3D)
            self.t.wait(1.0)
        d = self.t.nv()
        rec = C.read_record(self.t.u.io, self.t.map_text) if hasattr(C, "read_record") else None
        self.row("halt", "PASS" if d["flush"] - d0["flush"] == 6 else "FAIL",
                 f"6 x 0x3D: items written {d0['item_wr']} -> {d['item_wr']}, flash ops {d0['ops']} -> {d['ops']}; {show(d)}"
                 + (f"; record {rec}" if rec else ""))

    def c_persist(self, how: str | None):
        if self.t.name != "unit" or not how:
            return self.row("persist", "SKIP", "unit with --reboot mains|isp only")
        import settings_table as T
        rows = {"osd_timeout": None, "kvm_prefill": None, "brightness": None}
        for n in rows:
            rows[n] = self.t.box.get_row(T.BY_NAME[n])
        want = {"osd_timeout": 55 if rows["osd_timeout"] != 55 else 60, "kvm_prefill": 1 - rows["kvm_prefill"],
                "brightness": 47 if rows["brightness"] != 47 else 48}
        for n, v in want.items():
            self.t.box.set_row(T.BY_NAME[n], v)
        d0 = self.t.nv()
        self.t.cmd(0x3E)                                 # soft off: the flush
        d, dt = self.wait_write(d0, POWER_S + 1.0)
        self.say(f"  soft off: written {dt}; {show(d)}")
        if how == "mains":                               # relay off 8 s + on; 60 s = relay API stuck, case FAILs
            cmd = [sys.executable, str(ROOT / "dev.py"), "power-cycle", "--unit", "2"]
        else:                                            # ISP 0xEE reboot: RAM rebuilt, the SDK store read back from flash
            cmd = [sys.executable, str(ROOT / "dev.py"), "reset", "--unit", "2"]
        rc = subprocess.run(cmd, capture_output=True, text=True, timeout=60).returncode
        self.say(f"  {how} reboot rc={rc}")
        self.t.wait(5.0)                                 # monitor back: 5 s max (memory rule)
        self.t = Unit("2", self.t.mapp, self.say)        # bus number may change after a cycle
        nv = self.t.nv()
        got = {n: self.t.box.get_row(T.BY_NAME[n]) for n in want}
        pw = self.t.box.get_row(T.BY_NAME["power_on"])
        ok = rc == 0 and got == want and pw == 0 and nv["flush"] == 0     # flushes 0: really a new boot
        self.row("persist", "PASS" if ok else "FAIL", f"after soft off + {how} reboot:{got} (want {want}), power_on {pw} "
                 f"(off before the cycle: stays off); {show(self.t.nv())}")
        self.t.cmd(0x3E)                                 # on
        self.t.wait(8.0)
        for n, v in rows.items():
            self.t.box.set_row(T.BY_NAME[n], v)


    def flush_lines(self) -> list[tuple[int, int, str, int, int]]:
        """(why arg, result value, "why | result" lines, ring ms, seq) of every D4 flush pair in the ring (all episodes), oldest first"""
        import sync_log as S
        rows = S.load_rows(S.tsv_for(self.t.mapp))
        h, _ = S.decode(self.t.ring(), rows, whole=True)
        out, evs = [], h.get("events", [])
        for k, ev in enumerate(evs):                     # why line (11..17), then its result line (20, fmt nvw)
            if ev[0] == 0xD4 and 0x11 <= ev[1] <= 0x17 and k + 1 < len(evs) and evs[k + 1][:2] == (0xD4, 0x20):
                txt = " | ".join(S.line(rows, e, h["t0"]).split(" ms ", 1)[1] for e in (ev, evs[k + 1]))
                out.append((ev[1], evs[k + 1][3], txt, ev[2], k))
        return out

    def new_flush(self, before: list, s: float):
        """the first flush line not in `before` (by arg, value, ring ms), polled for s"""
        seen = {x[:4] for x in before}
        t = 0.0
        while t <= s:
            fresh = [x for x in self.flush_lines() if x[:4] not in seen]
            if fresh:
                return fresh[0]
            self.t.wait(0.25)
            t += 0.25
        return None

    def c_flushlog(self):
        """menu close with a change: a 'wrote' line whose bytes / programs / erases match the counter deltas; menu close
        without a change: 'nothing changed'; POWER off: a power-off flush line (nothing dirty: panel time only, or nothing)"""
        import settings_table as T
        res = []
        r = T.BY_NAME["osd_timeout"]
        d0 = self.settle()
        cur = self.t.box.get_row(r)
        b0 = self.flush_lines()
        self.t.box.call(3, 2, 0)                         # MO_OPEN page 0
        self.t.box.set_row(r, 45 if cur != 45 else 50)
        self.t.box.call(3, 6, 0)                         # MO_CLOSE
        ln = self.new_flush(b0, GATE_S)
        d = self.t.nv()
        if ln:
            v = ln[1]
            want = (d["bytes"] - d0["bytes"], d["ops"] - d0["ops"] - (d["erase"] - d0["erase"]), d["erase"] - d0["erase"])
            got = ((v >> 9) & 0x3FF, (v >> 19) & 0x3F, (v >> 25) & 3)
            ok = ln[0] == 0x14 and "wrote" in ln[2] and "OSD data" in ln[2] and got == want
            res.append(("change", ok, f"{ln[2]} [counters: {want[0]} B, {want[1]} programs, {want[2]} erases]"))
        else:
            res.append(("change", False, f"no flush line within {GATE_S} s"))
        b1 = self.flush_lines()
        self.t.box.call(3, 2, 0)
        self.t.box.call(3, 6, 0)                         # close, nothing changed
        ln = self.new_flush(b1, 1.0)                     # logged by the next settings service (20 ms) x margin
        ok = bool(ln) and ln[0] == 0x14 and "| NVRAM nothing changed, no flash write" in ln[2]
        res.append(("no change", ok, ln[2] if ln else "no flush line within 1 s"))
        b2 = self.flush_lines()
        e0 = self.t.nv()
        self.t.cmd(0x3E)                                 # POWER key: off
        ln = self.new_flush(b2, POWER_S + 1.0)
        e = self.t.nv()
        ok = bool(ln) and ln[0] == 0x13 and (("nothing changed" in ln[2]) == (e["item_wr"] == e0["item_wr"]))
        res.append(("power off", ok, ln[2] if ln else f"no flush line within {POWER_S + 1.0} s"))
        self.t.cmd(0x3E)                                 # on again
        self.t.wait(8.0 if self.t.name == "unit" else 3.0)
        self.t.box.set_row(r, cur)                       # restored; written by the gate
        self.t.wait(GATE_S)
        ok = all(x[1] for x in res)
        self.row("flushlog", "PASS" if ok else "FAIL", "; ".join(f"{n}: {'ok' if k else 'BAD'} '{s}'" for n, k, s in res))


CASES = ["unchanged", "vcp", "forced", "switch", "menu", "selector", "power", "halt", "persist", "flushlog"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", type=Path)
    ap.add_argument("--unit")
    ap.add_argument("--map", type=Path)
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--reboot", choices=("mains", "isp"), help="persist: soft off, then the relay (mains) or ISP 0xEE reboot")
    a = ap.parse_args()
    say = Log()
    if a.sim:
        mapp = a.map or a.sim.with_suffix(".map")
        t = Sim(a.sim, mapp)
        say(f"nv_test --sim {a.sim.name}")
    elif a.unit:
        if a.unit != "2":
            raise SystemExit("tests on unit 2 only")
        t = Unit(a.unit, a.map, say)
        say(f"nv_test --unit 2 bus {t.u.bus_n} map {a.map.name}")
    else:
        raise SystemExit("--sim BIN or --unit 2 --map MAP")
    if t.nv_a is None:
        raise SystemExit("image without _g_stAwtoNv (#151)")
    r = Run(t, say)
    say(f"  start: {show(t.nv())}")
    try:
        for c in a.cases.split(","):
            if c == "persist":
                r.c_persist(a.reboot)
            else:
                getattr(r, f"c_{c}")()
    finally:
        r.t.close()
    say(f"---- nv_test summary ({t.name})")
    for n, res, txt in r.rows:
        say(f"  {res:4} {n:10} {txt[:400]}")
    bad = [x for x in r.rows if x[1] == "FAIL"]
    say(f"{'PASS' if not bad else 'FAIL'} nv_test: {len(r.rows) - len(bad)}/{len(r.rows)} not failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
