#!/usr/bin/env python3
"""#144 power-on in fw_sim: no boot logo, the console with the live power-on log from mode INITIAL; PNGs along the way.

usage: AWTO_SIM_CORE=fast boot_sim.py BIN MAP [--mode 1080p60] [--out tmp/boot] [--at MS ...]
- Runs from reset (console default on) to ACTIVE + AFTER_MS. Records OSD grid size, console flag and mode per step.
- PNGs: <out>/boot_<ms>ms.png at each --at (fw ms since power-on, default 300 1000), boot_console_first.png (first OSD on),
  boot_active.png (mode ACTIVE), boot_after_ds.png (ACTIVE + AFTER_MS: after display setting).
- Checks: no logo symbols in the map; console open before display setting with the 120 x 63 map; the same console still
  open at ACTIVE (one "console opened" line: it survived display setting); power-on log lines; no chip reset.
- Prints power-on -> ACTIVE (sync ring) and first-console / backlight-on times; the backlight lines' chain (11 C0..DF) is timed
  like the panel and system lines.
- #29 (images with AwtoBootReason): first line = boot reason, stage lines, times since reset; cold boot and, with --bite
  (default), after a 0x4C watchdog bite. PNGs boot_reason_cold.png / boot_reason_bite.png.
Log: tmp/logs/boot_sim.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import rtd_crash as C  # noqa: E402
import sync_log as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/boot_sim.log"
CON_COLS, CON_MAP_ROWS = 120, 63      # awto_dbgpop.inc AWTO_CON_COLS, AWTO_CON_ROWS + pad row
AFTER_MS = 300                        # after ACTIVE: the console has had display setting + active proc behind it
BUDGET_INSTR = 160_000_000            # sim boot to ACTIVE takes ~75 M instructions (boot1); x2 margin; expiry = FAIL
STEP = 100_000                        # instructions per sample (~1-2 ms of fw time)
BITE_INSTR = 40_000_000               # 0x4C -> reset: cmd ~0.1 s + warning 1.03 s at ~12.6 k instr / fw ms = 14 M; x2.5
TIME_SLACK_MS = 3                     # line time vs the next line's '(N ms)' (time in its old state): action after the time stamp (pin, DPTx call) ~1 ms x3
LOGO_SYMS = ("_OsdDispShowLogo", "_AwtoLogoDraw", "_tICON_REALTEK_1BIT_LOGO0", "_tAWTO_LOGO_RUNS", "_AwtoTestHoldLogoOff")


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.s = R.Session(a.bin, a.map, a.mode)
        self.bus, self.m = self.s.bus, self.s.bus.m
        self.rows = S.load_rows(S.tsv_for(a.map))
        self.ring = S.sym(a.map, "g_stAwtoSync")
        self.gpio = self.m.addr("g_stAwtoGpio")
        self.w, self.h = self.m.addr("g_ucOsdWidth"), self.m.addr("g_ucOsdHeight")
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        mt = a.map.read_text(errors="replace")
        self.caddr, self.mt = C.map_addr(mt), mt

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def ms(self):
        """fw ms since power-on: Timer2 ms (diag usT2Isr) minus the power-on episode's t0 (the ring's own time base)."""
        raw = self.m.rd(self.ring, 9)
        if raw[:2] != b"SY":
            return 0.0
        return float((self.bus.diag_t2() - (raw[7] << 8 | raw[8])) & 0xFFFF)

    def state(self):
        return (self.bus.mode_state(), self.m.rd(self.w)[0], self.m.rd(self.h)[0], self.m.rd(self.gpio + 3)[0],
                M.summary(self.s.model.snapshot(self.m, 0.0))["en"])

    def shot(self, name):
        st = self.s.model.snapshot(self.m, self.ms())
        out = self.a.out / f"{name}.png"
        img = np.array(R.render_snap(st, "black", 1))
        Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(out)
        sm = M.summary(st)
        say(f"  png {out} at {self.ms():.0f} ms (OSD {'on' if sm['en'] else 'OFF'}, grid {sm['cols']}x{sm['rows']})")

    def reason(self, tag, want, lines, sym=""):
        """#29: first line = the reason; boot milestone lines (>= 6) present, times (ms since reset) never step back; PNG."""
        for ln in lines[:16]:
            say(f"    {ln}")
        first = lines[0].split(" ms ", 1)[1] if lines else ""
        self.check(first.startswith(want) and sym in first, f"{tag}: first line is the boot reason", first)
        st = [ln for ln in lines[1:] if " boot: " in ln]       # milestone lines (sync.tsv D1 rows), after the reason
        want = sum(1 for r in self.rows if r["id"] == 0xD1)     # s3b: panel stages 5 / 7 / 8 have no row (the panel machine's lines)
        self.check(len(st) >= want, f"{tag}: boot stage lines", f"{len(st)} of {want}")
        ms = [int(ln[1:].split("ms")[0]) for ln in lines]
        # 1 ms slack: the WDT-counter time (before Timer2) and the Timer2 time meet with integer-ms truncation
        self.check(all(b >= a - 1 for a, b in zip(ms, ms[1:])), f"{tag}: line times never step back (> 1 ms)", str(ms[:12]))
        self.shot(f"boot_reason_{tag}")

    def machine_times(self, evs):
        """#162 s3b: a machine line's ring time is its transition: line B -> C ('B -> C (N ms)') comes N ms after line A -> B
        (console open: a live draw between an action and its line shows here). Panel (11) and system (13) lines."""
        for eid, name in ((0x11, "panel"), (0x11, "backlight"), (0x13, "system")):
            tr = [(ms, a, v) for i, a, ms, v in evs if i == eid and (eid != 0x11 or (a >= 0xC0) == (name == "backlight"))]
            if name == "backlight":              # backlight sub-state lines (11 C0..DF): arg = C0 | old << 2 | new (+ 10 delayed)
                tr = [(ms, ((a >> 2 & 3) << 4) | (a & 3), v) for ms, a, v in tr]
            bad = []
            for (t1, a1, _), (t2, a2, v2) in zip(tr, tr[1:]):
                if (a1 & 0x0F) != (a2 >> 4) or (a1 >> 4) == (a1 & 0x0F) or (eid == 0x11 and a1 == 0x49):
                    continue                     # chain gap / A -> A (entry kept) / VIDEO -> T4 (T4 counts from the backlight-off)
                inn = (v2 & 0xFFFF) if eid == 0x11 else (v2 & 0xFFFFFF)
                if abs(((t2 - t1) & 0xFFFF) - inn) > TIME_SLACK_MS:
                    bad.append(f"{a1:02X}@{t1} -> {a2:02X}@{t2}: {inn} ms in, lines {(t2 - t1) & 0xFFFF} ms apart")
            self.check(len(tr) > 1 and not bad, f"{name} lines carry their transition time (+-{TIME_SLACK_MS} ms)", "; ".join(bad[:4]))

    def episode(self):
        return S.decode(S.read_ring(self.m.rd, self.ring), self.rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/boot")
    ap.add_argument("--at", type=float, nargs="*", default=[300.0, 1000.0])
    ap.add_argument("--bite", action=argparse.BooleanOptionalAction, default=True, help="#29: 0x4C bite, reboot, reason line")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"boot_sim {a.bin.name}")
    r = Run(a)
    try:
        left = [s for s in LOGO_SYMS if s in r.mt]
        r.check(not left, "no boot logo symbols in the map", ", ".join(left))
        ats, used, last, first_con, active_ms = sorted(a.at), 0, None, None, None
        con_at_ds = None
        while used < BUDGET_INSTR:
            r.m.run(STEP); used += STEP
            t, st = r.ms(), r.state()
            if st != last:
                say(f"  {t:7.0f} ms mode {st[0]} grid {st[1]}x{st[2]} console {st[3]} osd {'on' if st[4] else 'off'}")
                if first_con is None and st[3] and st[4]:
                    first_con = t
                    r.shot("boot_console_first")
                if st[0] == 2 and con_at_ds is None:
                    con_at_ds = (st[1], st[2], st[3])
                last = st
            while ats and t >= ats[0]:
                r.shot(f"boot_{int(ats.pop(0))}ms")
            if st[0] == 3:
                active_ms = t
                r.shot("boot_active")
                break
        r.check(active_ms is not None, "reached ACTIVE", f"{used} instr")
        if active_ms is None:
            return 1
        r.bus.wait(AFTER_MS / 1000.0)
        st = r.state()
        r.shot("boot_after_ds")
        h, lines = r.episode()
        say(f"  power-on: episode {S.KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines, lost {h.get('lost', 0)}")
        for ln in lines:
            say(f"    {ln}")
        txt = "\n".join(lines)
        r.check(h.get("lost", 0) == 0, "ring holds every power-on line (none overwritten)", f"{len(lines)} lines in {h['n']} slots, lost {h.get('lost', 0)}")
        r.check(first_con is not None, "console shown during power-on", f"first at {first_con:.0f} ms" if first_con else "never")
        r.check(con_at_ds is not None and con_at_ds[:2] == (CON_COLS, CON_MAP_ROWS) and con_at_ds[2] != 0,
                f"console ({CON_COLS} x {CON_MAP_ROWS} map) open when display setting starts", str(con_at_ds))
        r.check(st[1:4] == (CON_COLS, CON_MAP_ROWS, st[3]) and st[3] != 0 and st[4], "console open after display setting", str(st))
        r.check(txt.count("console opened") == 1, "one 'console opened' line (survived display setting, no reopen)",
                f"{txt.count('console opened')}")
        r.check("0.0 MHz" not in txt and "TMDS predetect on (clock not measured yet)" in txt, "HDMI scan: predetect line without a clock value, no 0.0 MHz line")
        for want in ("power on", "backlight on at once", "timing ", "-> DISPLAY SETTING:", "-> ACTIVE:"):
            r.check(want in txt, f"power-on log has '{want}'")
        r.machine_times(h["events"])
        r.bus.dbg_link_on()                         # #79 images: 0x35 parked off the host port until this
        d = C.decode(C.read(r.bus, r.caddr))
        say(f"  measured, watchdog: {C.ages(d)}")
        r.check(r.cr.resets == 0, "no chip reset (watchdog)", f"resets {r.cr.resets}")
        if "_AwtoBootReason" in r.mt:               # #29: reason line first, boot stages with ms since reset
            S.set_map(a.map)
            r.reason("cold", "boot: cold power-up", lines)
            if a.bite:
                T = __import__("osd_test")
                ad = T.diag_addr(a.map) + T.TESTCMD_OFF
                r.bus.write(0x6A, 0x01, bytes([ad >> 8])); r.bus.write(0x6A, 0x03, b"\x4c"); r.bus.write(0x6A, 0x3B, bytes([ad & 0xFF]))
                used = 0
                while r.cr.resets == 0 and used < BITE_INSTR:
                    r.m.run(STEP); used += STEP
                r.check(r.cr.resets == 1, "test cmd 0x4C: watchdog reset", f"{used} instr")
                while r.bus.mode_state() == 3 and used < 2 * BITE_INSTR:     # ACTIVE in RAM until init rewrites it
                    r.m.run(STEP); used += STEP
                r.check(r.bus.run_until_mode(3), "ACTIVE again after the bite")
                r.bus.wait(AFTER_MS / 1000.0)
                r.reason("bite", "boot: watchdog bite, STALL TEST, PC ", r.episode()[1], "AwtoWdtHang+")
    finally:
        r.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} boot_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
