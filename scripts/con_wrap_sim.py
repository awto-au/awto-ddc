#!/usr/bin/env python3
"""Console line wrap in fw_sim (Dan 2026-11-12: no log line clipped): the drawn console rows against the sync ring.

usage: AWTO_SIM_CORE=fast con_wrap_sim.py BIN [--map MAP] [--out tmp/len/con_wrap]
Scenario: cold boot 1080p60 (console auto-open), POWER off / on (test cmd 0x3E), power saving (VCP D6 = 4), SOURCE key (the\nwake poll may wake first: power NORMAL is the check).
After each phase, with the main page open, the shown rows are read from the OSD model and grouped into lines (a row starting
' +' and its continuation: AWTO_LOG_TXT0 spaces, then text). FAIL:
- a group of more than two rows, or a group whose text (time column dropped, continuation joined) is not a ring line: a clipped
  row is a prefix only, so it fails;
- a ring line of the phase that should be in view (the newest lines that fit the view) missing from the console.
Then the widest lines (LONG) are pushed into the ring: each must take two rows; 30 more run the map past its end (redraw).
Port names differ by design (console HDMI-1 / DP-1, host D2 / D1): both sides are compared with port names as <P>.
Text + PNG of each phase: --out. Log: tmp/logs/con_wrap_sim.log
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D  # noqa: E402
import fw_sim as S  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402
import sync_log as SL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/con_wrap_sim.log"
LOG_COL = 1            # fw/osd/console.c AWTO_LOG_COL (main page)
TXT0 = 11              # text column (fw/osd/console.c AWTO_LOG_TXT0): continuation rows start here; checked against the tree below
POWER_KEY, K_SOURCE = 0x3E, 0x05
PWR_OFF, PWR_NORMAL, PWR_SAVING = 1, 2, 3
MODE_ACTIVE = 3
# Phase bounds (firmware s; expiry = FAIL), sysm_sim's: off 1.5 s + T6 1.3 s, on 3 s, saving 3 s, wake 5.5 s; console draw 1 s
OFF_S, T6_S, ON_S, PS_S, WAKE_S, DRAW_S = 1.5, 1.3, 3.0, 3.0, 5.5, 1.0
# Widest lines (gen_awto_sync.py worst case), pushed into the ring: sys DISPLAY SETTING -> POWER SAVING, why 0E + mode text,
# 24-bit ms; sysreq 13 by 0E, outcome 04; backlight off deferred, requester 07
LONG = ((0x13, 0x4A, (0x8E << 24) | 0xFFFFFF), (0x14, 0x13, (0x0E << 8) | 0x04), (0x10, 0x0F, 0x07))
PORT = re.compile(r"\b(DP-1|HDMI-\d+|Input D\d+|D\d)\b")


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def norm(s: str) -> str:
    return PORT.sub("<P>", s.rstrip())


class Sim:
    def __init__(self, binp: Path, mapp: Path):
        self.model = M.OsdModel()
        self.model.img = binp.read_bytes()
        self.eng = D.DdcEngine()
        self.bus = S.SimBus(binp, mapp, "conwrap-" + binp.stem, None, boot=False, devs=[self.model, self.eng], video="1080p60")
        self.m = self.bus.m
        self.mccs = D.Mccs(self.bus, self.eng)
        self.rows = SL.load_rows(SL.tsv_for(mapp))
        self.a_sync, self.a_pwr = self.m.addr("g_stAwtoSync"), self.m.addr("isr_g_stPowerInfo")
        self.fails = 0
        self.base = None

    def check(self, ok: bool, what: str, detail: str = ""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}" + (f": {detail}" if detail else ""))
        self.fails += not ok

    def text(self) -> list[str]:                         # host_time_sim.Sim.text: glyph ids -> ASCII from the drawn title
        st = self.model.snapshot(self.m, 0)
        rows = M.layout_rows(st, M.frame_geometry(st))
        cs = rows[0]["chars"] if rows else []
        for k in range(1, 4) if self.base is None else ():         # title " AWTO..." at column 1 or 2 (a leading space)
            if len(cs) > k + 3 and all(c["kind"] == "1bit" for c in cs[k:k + 4]):
                b = cs[k]["id"] - (ord("A") - 0x20)
                if [c["id"] - b + 0x20 for c in cs[k + 1:k + 4]] == [ord(x) for x in "WTO"]:
                    self.base = b
        b = self.base or 0
        return ["".join(chr(c["id"] - b + 0x20) if c["kind"] == "1bit" and 0 <= c["id"] - b < 95 else " " for c in r["chars"])
                for r in rows]

    def cmd(self, c: int):
        self.m.wr(self.m.addr("isr_g_stAwtoDiag") + T.TESTCMD_OFF, bytes([c]))

    def power(self) -> int:
        return self.m.rd(self.a_pwr)[0] >> 4

    def until(self, cond, sec: float) -> bool:
        t_end = self.bus.now() + sec
        while not cond() and self.bus.now() < t_end:
            self.bus.wait(0.05)
        return cond()

    def ring(self) -> list[str]:
        _, lines = SL.decode(bytes(SL.read_ring(self.m.rd, self.a_sync)), self.rows, whole=True)
        return lines

    def inject(self, evs):
        """ring entries as AwtoSyncPush writes them (StAwtoSync: seq at 3, N at 12, wrap at 13, 8 B entries after 14 B)"""
        h = bytes(self.m.rd(self.a_sync, SL.HDR))
        seq, n, wrap = h[3], h[12], h[13]
        ms = self.m.rd(0xF6D0 + SL.DIAG_T2, 2)             # ring ms = usT2Isr (diag block)
        for i, a, v in evs:
            self.m.wr(self.a_sync + SL.HDR + SL.EV * (seq % n), bytes([i, a, *ms]) + v.to_bytes(4, "big"))
            seq = (seq + 1) % wrap
        self.m.wr(self.a_sync + 3, bytes([seq]))
        say(f"  injected {len(evs)} widest lines: " + " | ".join(SL.line(self.rows, (i, a, 0, v), 0) for i, a, v in evs))

    def phase(self, name: str, out: Path, want_wraps: int = 0):
        t = self.text()
        if not t or "AWTO DIAGNOSTICS" not in t[0]:
            say(f"  {name}: console not open (title {t[0].strip()[:40] if t else '-'!r}), nothing to compare")
            if want_wraps:                               # the wrap phases must see the console (they passed silently before)
                self.check(False, f"{name}: console open for the wrap check", t[0].strip()[:40] if t else "-")
            return
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.txt").write_text("\n".join(r.rstrip() for r in t) + "\n")
        R.render_snap(self.model.snapshot(self.m, 0), "black", 1).save(out / f"{name}.png")
        groups, cur = [], None
        for r in t[1:]:
            r = r[LOG_COL:]                                   # the log pane starts at map column AWTO_LOG_COL
            if re.match(r" *\d+:", r):
                cur = [r]
                groups.append(cur)
            elif cur is not None and r.startswith(" " * TXT0) and r.strip():
                cur.append(r)
            else:
                cur = None
        ring = [norm(x.split(":", 1)[1]) for x in self.ring()]   # host line: "nnnnn:" then the text
        bad, wraps = [], 0
        for g in groups:
            if len(g) > 2:
                bad.append(f"{len(g)} rows: {g[0].strip()[:60]}")
                continue
            body = g[0].split(":", 1)[1].rstrip()                 # after the "nnnnn:" time column
            if len(g) == 2:
                wraps += 1
                cont = g[1][TXT0:].rstrip()
                cands = (body + " " + cont, body + cont)     # break at a space (dropped) / at the edge (no space)
            else:
                cands = (body,)
            if not any(norm(c) in ring for c in cands):
                bad.append(f"not a ring line (clipped?): {' | '.join(x.rstrip() for x in g)}")
        say(f"  {name}: {len(groups)} console lines ({wraps} on two rows), {len(t) - 1} rows shown")
        for g in groups:
            say("    " + " / ".join(x.rstrip() for x in g))
        self.check(not bad, f"{name}: every console line whole (one or two rows, the ring's text)", "; ".join(bad[:3]))
        head = lambda g: g[0].split(":", 1)[1].rstrip()              # first row after its "nnnnn:" time column
        shown = {norm(head(g) + (" " + g[1][TXT0:].rstrip() if len(g) == 2 else "")) for g in groups}
        shown |= {norm(head(g) + g[1][TXT0:].rstrip()) for g in groups if len(g) == 2}
        newest = ring[-min(len(groups), 20):] if groups else []
        miss = [x for x in newest if x not in shown and not x.startswith("(fw +")]   # D8 sits on the host time row
        self.check(groups and not miss, f"{name}: the newest {len(newest)} ring lines are on the console", "; ".join(miss[:3]))
        if want_wraps:
            self.check(wraps >= want_wraps, f"{name}: the widest lines on two rows", f"{wraps} of {want_wraps}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--tree", type=Path, help="worktree: AWTO_LOG_TXT0 from fw/osd/console.c")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/len/con_wrap")
    a = ap.parse_args()
    global TXT0
    if a.tree:
        sys.path.insert(0, str(a.tree / "scripts"))
        import gen_awto_sync as G                       # noqa: E402
        TXT0 = G.c_int("AWTO_LOG_TXT0", a.tree / "fw/osd/console.c")
    mapp = a.map or a.bin.with_suffix(".map")
    say(f"=== con_wrap_sim {a.bin.name} (text column {TXT0}) ===")
    s = Sim(a.bin, mapp)
    out = a.out / a.bin.stem
    s.check(s.bus.run_until_mode(MODE_ACTIVE, 160_000_000), "cold boot:ACTIVE")
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], 4.0)
    s.bus.wait(DRAW_S)
    s.phase("1-cold-boot", out)
    s.cmd(POWER_KEY)
    s.check(s.until(lambda: s.power() == PWR_OFF, OFF_S), "POWER key: OFF")
    s.bus.wait(T6_S)
    s.phase("2-power-off", out)
    s.cmd(POWER_KEY)
    s.check(s.until(lambda: s.bus.mode_state() == MODE_ACTIVE, ON_S), "POWER key: ACTIVE again")
    s.bus.wait(DRAW_S)
    s.phase("3-power-on", out)
    s.mccs.set(0xD6, 4)
    s.check(s.until(lambda: s.power() == PWR_SAVING, PS_S), "VCP D6 = 4: power saving")
    s.bus.wait(0.3)
    s.phase("4-power-saving", out)
    s.cmd(K_SOURCE)
    s.check(s.until(lambda: s.power() == PWR_NORMAL, WAKE_S), "SOURCE key: woke (power NORMAL)", f"mode {s.bus.mode_state()}")
    s.bus.wait(DRAW_S)
    s.phase("5-wake", out)
    s.cmd(0x26)                                         # console (the wake leaves the input selector up)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], 4.0)
    s.inject(LONG)
    s.bus.wait(DRAW_S)
    s.phase("6-long-lines", out, want_wraps=len(LONG))
    for _ in range(10):                                 # 30 lines of two rows: past the map end (62 rows), redraw from the ring
        s.inject(LONG)
        s.bus.wait(0.1)
    s.bus.wait(2 * DRAW_S)                              # the redraw is a console open (map clear, font load) + the backfill
    s.phase("7-map-end", out, want_wraps=len(LONG))
    s.cmd(0x3A)                                         # demo log: 100 lines 5ms apart (test cmd 0x3A), a burst with wraps
    s.bus.wait(2.5)                                     # 100 lines x ~13 ms on unit 3 = 1.3 s, x1.25, + the draw backlog
    s.phase("8-demo-log", out, want_wraps=2)           # burst; every third demo line wraps
    bites = [x for x in s.ring() if "watchdog bite" in x]
    s.check(not bites, "no watchdog bite while the console drew the bursts (one wrapped line per AwtoConLogSync call)", str(bites[:1]))
    say(f"{'PASS' if s.fails == 0 else 'FAIL'} con_wrap_sim {a.bin.name}: {s.fails} failed (pages: {out})")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
