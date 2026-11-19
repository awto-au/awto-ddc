#!/usr/bin/env python3
"""Screensaver exits in the firmware sim (docs/saver-mode.md): what ends a saver, and what the SDK OSD does to it.

usage: saver_mode_sim.py BIN [MAP] [--out DIR]
  - idle_loss: screensaver Pac-Man, idle 10 s (rows 119 / 120 over DDC/CI), saver starts over the picture (why = idle);
    then the input goes to D3 with no source (test cmd 0x33, a signal-loss proxy): trace run / why / mode / OSD on, PNG.
  - nosig_lock: D3 no source until the no-signal saver starts (why = nosig); back to D2 (test cmd 0x32): the saver must stop.
  - Report lines only; PASS / FAIL where the expected behaviour is written down (nosig_lock). Exit 1 on a FAIL.
Log: ./tmp/logs/saver_mode_sim.log
"""
import argparse
import os
import sys
from pathlib import Path

import isostamp

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import osd_model as M
import osd_render as R
import pacman_sim as P

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_mode_sim.log"
ROW_SAVER, ROW_SAVER_S, ROW_DISP_ROTATE, ROW_PWR_L3_EN, ROW_PWR_L3_S = 119, 120, 32, 79, 80    # fw/rtdfw/settings/registry.tsv
SAVER_PACMAN, IDLE_S = 1, 10                                     # registry: screensaver Pac-Man, screensaver_s step 10
IDLE_WAIT_S = IDLE_S + 2.0                                       # idle start + one Pac-Man draw
NOSIG_SEARCH_S = 6.0                                             # D3 switch -> NOSIGNAL (sim: measured in the trace)
NOSIG_START_MAX_S = 2.5                                          # saver within this of NOSIGNAL: AWTO_SAVER_NOSIG_MS 1.8 s + a pass, before the SDK card at 2 s
NOSIG_RUN_S, NOSIG_RUN_TOL_S = 30, 1.0                           # pwr_l3_s step 30; trace step 0.5 s
NOSIG_PS_S = 10.0                                                # SDK chain after N: card 2 s + power-saving card 3 s + 2 s
IDLE_TOL_S = 1.0                                                 # idle restart must come no earlier than the idle time minus this (trace step + pass)
NOSIG_AFTER_S = 6.0                                              # watch after the saver end
MODE_NOSIGNAL, MODE_PS = "5", "6"                                # _MODE_STATUS_NOSIGNAL / _POWER_SAVING: checked against the trace
TRACE_S, TRACE_STEP_S = 6.0, 0.25                                # after the input switch: SDK search + no-signal pop-up timers
LOCK_S = 5.0                                                     # D2 search + display setting to ACTIVE (boot ~0.75 s, x6)
TC_D2, TC_D3 = 0x32, 0x33
D3_PIN = 0xFE2C                                                  # wake_sim D3_PIN: D3 cabled, no source
RUN_NAMES = {0: "off", 1: "pacman", 3: "scope2", 5: "flash", 6: "splash"}


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


class Probe:
    def __init__(self, a):
        self.a = a
        self.eng = D.DdcEngine()
        self.sess = R.Session(a.bin, a.map, "1080p60", devs=[self.eng])
        self.sess.boot()
        self.m = self.sess.bus.m
        self.ddc = D.Mccs(self.sess.bus, self.eng)
        self.run_a, self.why_a = self.m.addr("g_ucAwtoSaverRun"), self.m.addr("g_ucAwtoSaverWhy")

    def row(self, rid: int, v: int):
        self.ddc.set(0xE0, rid)
        self.ddc.set(0xE1, v)

    def state(self) -> str:
        run, why = self.m.rd(self.run_a)[0], self.m.rd(self.why_a)[0]
        sm = M.summary(self.sess.snap())
        return (f"run {RUN_NAMES.get(run, run)} why {why:#04x} mode {self.sess.bus.mode_state()} "
                f"OSD {'on' if sm['en'] else 'off'} grid {sm['cols']}x{sm['rows']}")

    def png(self, name: str):
        R.render_snap(self.sess.snap(), "black", 2).save(self.a.out / name)

    def trace(self, secs: float, tag: str) -> list:
        last, out, t = None, [], 0.0
        while t < secs:
            s = self.state()
            if s != last:
                say(f"  {tag} +{t:.2f} s: {s}")
                last = s
            out.append(s)
            self.sess.bus.wait(TRACE_STEP_S)
            t += TRACE_STEP_S
        return out


def idle_loss(a) -> int:
    p = Probe(a)
    p.row(ROW_DISP_ROTATE, 0)
    p.row(ROW_SAVER, SAVER_PACMAN)
    p.row(ROW_SAVER_S, IDLE_S)
    p.sess.bus.wait(IDLE_WAIT_S)
    s0 = p.state()
    started = "run pacman why 0x02" in s0
    say(f"{'PASS' if started else 'FAIL'} idle_loss: idle saver started after {IDLE_WAIT_S} s: {s0}")
    p.png("idle_loss_before.png")
    p.m.wr(D3_PIN, b"\x00")
    P.send(p.sess, TC_D3)
    st = p.trace(TRACE_S, "idle_loss")
    first = next((i for i, s in enumerate(st) if " mode 3 " not in s), None)        # first sample with the picture gone
    ok = first is not None and st[first].startswith("run off") and not any("why 0x02" in s for s in st[first:])
    say(f"{'PASS' if ok else 'FAIL'} idle_loss: idle saver off from the first sample without ACTIVE, never restarts; a later saver is the no-signal one (why 0x01): "
        f"{st[first] if first is not None else 'mode never left ACTIVE'}")
    p.png("idle_loss_after.png")
    say(f"idle_loss: PNGs {a.out}/idle_loss_before.png, idle_loss_after.png")
    p.sess.bus.close()
    return 0 if (started and ok) else 1


def nosig_start(p, l3_en: int, run_s: int, idle: bool = False):
    """Rows set, D3 without a source: returns the trace start state. l3_en = pwr_l3_en, run_s = pwr_l3_s (the no-signal saver run time)."""
    p.row(ROW_DISP_ROTATE, 0)
    p.row(ROW_SAVER, SAVER_PACMAN)
    p.row(ROW_PWR_L3_EN, l3_en)
    p.row(ROW_PWR_L3_S, run_s)
    if idle:
        p.row(ROW_SAVER_S, IDLE_S)                              # idle start on too: the picture that ends the saver must not start it again
    p.m.wr(D3_PIN, b"\x00")
    P.send(p.sess, TC_D3)


def trace_t(p, secs: float, tag: str, step: float = TRACE_STEP_S) -> list:
    """(t, state) samples every step s, state changes logged."""
    last, out, t = None, [], 0.0
    while t < secs:
        s = p.state()
        if s != last:
            say(f"  {tag} +{t:.2f} s: {s}")
            last = s
        out.append((t, s))
        p.sess.bus.wait(step)
        t += step
    return out


def mode_of(s: str) -> str:
    return s.split(" mode ")[1].split(" ")[0]


def nosig_default(a) -> int:
    """Defaults (pwr_l3_en 1), run time N = 30 s: saver at the card time, no card over it, N expiry -> SDK chain -> power saving."""
    p = Probe(a)
    nosig_start(p, 1, NOSIG_RUN_S)
    st = trace_t(p, NOSIG_RUN_S + NOSIG_PS_S + NOSIG_SEARCH_S, "nosig_default", 0.5)
    t_nosig = next((t for t, s in st if mode_of(s) == MODE_NOSIGNAL), None)
    t_run = next((t for t, s in st if "run pacman why 0x01" in s), None)
    t_end = next((t for t, s in st if t_run is not None and t > t_run and "run off" in s), None)
    t_ps = next((t for t, s in st if mode_of(s) == MODE_PS), None)
    card = [s for t, s in st if t_run is not None and t_end is not None and t_run < t < t_end and ("run pacman" not in s or "grid 28x36" not in s)]
    ok_start = t_nosig is not None and t_run is not None and (t_run - t_nosig) <= NOSIG_START_MAX_S
    say(f"{'PASS' if ok_start else 'FAIL'} nosig_default: NOSIGNAL at +{t_nosig} s, saver at +{t_run} s (<= {NOSIG_START_MAX_S} s after NOSIGNAL: the card time)")
    ok_len = t_end is not None and abs((t_end - t_run) - NOSIG_RUN_S) <= NOSIG_RUN_TOL_S
    say(f"{'PASS' if ok_len else 'FAIL'} nosig_default: saver ran {None if t_end is None else t_end - t_run} s (N = {NOSIG_RUN_S} s +- {NOSIG_RUN_TOL_S})")
    say(f"{'PASS' if not card else 'FAIL'} nosig_default: no card / other OSD while it ran ({len(card)} samples off)")
    ok_ps = t_ps is not None and t_end is not None and t_ps > t_end
    say(f"{'PASS' if ok_ps else 'FAIL'} nosig_default: power saving at +{t_ps} s, after the saver end +{t_end} s: {st[-1][1]}")
    again = [t for t, s in st if t_end is not None and t > t_end and "run pacman" in s]
    say(f"{'PASS' if not again else 'FAIL'} nosig_default: no saver restart after its end ({len(again)} samples)")
    p.sess.bus.close()
    return 0 if (ok_start and ok_len and not card and ok_ps and not again) else 1


def nosig_l3off(a) -> int:
    """pwr_l3_en 0, N = 30 s: saver at the card time, survives to N, then the card comes back and stays (power saving ignored), no restart."""
    p = Probe(a)
    nosig_start(p, 0, NOSIG_RUN_S, idle=True)
    st = trace_t(p, NOSIG_RUN_S + NOSIG_SEARCH_S + NOSIG_AFTER_S, "nosig_l3off", 0.5)
    t_run = next((t for t, s in st if "run pacman why 0x01" in s), None)
    t_end = next((t for t, s in st if t_run is not None and t > t_run and "run off" in s), None)
    during = [s for t, s in st if t_run is not None and t_end is not None and t_run < t < t_end]
    wiped = [s for s in during if "run pacman" not in s or "grid 28x36" not in s]
    ok = t_run is not None and t_end is not None and not wiped and abs((t_end - t_run) - NOSIG_RUN_S) <= NOSIG_RUN_TOL_S
    say(f"{'PASS' if ok else 'FAIL'} nosig_l3off: saver +{t_run} .. +{t_end} s (N = {NOSIG_RUN_S} s), {len(wiped)} wiped samples")
    after = [s for t, s in st if t_end is not None and t > t_end]
    card_back = any("run off" in s and "OSD on" in s for s in after)
    again = any("run pacman" in s for s in after)
    still_nosig = all(mode_of(s) == MODE_NOSIGNAL for s in after)
    say(f"{'PASS' if (card_back and not again and still_nosig) else 'FAIL'} nosig_l3off: after N the card is back ({card_back}), no restart ({not again}), still NOSIGNAL ({still_nosig}): {st[-1][1]}")
    p.png("nosig_l3off_end.png")
    p.sess.bus.close()
    return 0 if (ok and card_back and not again and still_nosig) else 1


def nosig_key(a) -> int:
    """A key (test-cmd stand-in: DDC/CI command) ends the no-signal saver; the card returns and the saver does not loop back."""
    p = Probe(a)
    nosig_start(p, 0, NOSIG_RUN_S)
    st = trace_t(p, NOSIG_SEARCH_S + NOSIG_START_MAX_S + 2.0, "nosig_key", 0.5)
    started = "run pacman why 0x01" in st[-1][1]
    say(f"{'PASS' if started else 'FAIL'} nosig_key: saver running: {st[-1][1]}")
    p.ddc.get(0x10)                                             # a DDC/CI command (not VCP 0xEB) ends a no-signal saver
    st2 = trace_t(p, NOSIG_SEARCH_S + NOSIG_AFTER_S, "nosig_key_after", 0.5)
    stopped = st2[1][1].startswith("run off") or st2[0][1].startswith("run off")
    again = any("run pacman" in s for t, s in st2)
    card = any("run off" in s and "OSD on" in s for t, s in st2)
    say(f"{'PASS' if (stopped and not again and card) else 'FAIL'} nosig_key: stopped ({stopped}), card shown ({card}), no restart in {NOSIG_AFTER_S + NOSIG_SEARCH_S} s ({not again}): {st2[-1][1]}")
    p.sess.bus.close()
    return 0 if (started and stopped and not again and card) else 1


def nosig_lock(a) -> int:
    p = Probe(a)
    nosig_start(p, 0, NOSIG_RUN_S, idle=True)                   # power saving ignored: no signal stays NOSIGNAL
    p.trace(NOSIG_SEARCH_S + NOSIG_START_MAX_S + 2.0, "nosig_wait")
    s0 = p.state()
    started = "run pacman why 0x01" in s0
    say(f"{'PASS' if started else 'FAIL'} nosig_lock: no-signal saver started (pwr_l3_en 0): {s0}")
    run = p.trace(TRACE_S, "nosig_run")
    wiped = any("run pacman" in s and "grid 28x36" not in s for s in run)
    say(f"{'FAIL' if wiped else 'PASS'} nosig_lock: {'the SDK no-signal card took the OSD while the saver runs' if wiped else 'saver kept the OSD'}: {run[-1]}")
    p.png("nosig_saver.png")
    P.send(p.sess, TC_D2)
    st = trace_t(p, LOCK_S + IDLE_S, "nosig_lock")
    t_act = next((t for t, s in st if " mode 3 " in s), None)                          # first sample with the picture back
    early = [s for t, s in st if t_act is not None and t_act < t < t_act + IDLE_S - IDLE_TOL_S and not s.startswith("run off")]
    t_idle = next((t for t, s in st if t_act is not None and t > t_act and "why 0x02" in s), None)
    stopped = t_act is not None and not early and t_idle is not None and t_idle - t_act >= IDLE_S - IDLE_TOL_S
    say(f"{'PASS' if stopped else 'FAIL'} nosig_lock: D2 locked at +{t_act} s, saver off and no idle restart over the new picture before the idle time "
        f"({IDLE_S} s); idle saver at +{t_idle} s")
    p.sess.bus.close()
    return 0 if (started and not wiped and stopped) else 1


def now_ddc(a) -> int:
    """D4: a DDC/CI command does not end a 'now' saver, plain (VCP 0xEB = 2) or Alternate (0xEB = 1 with the screensaver row Off)."""
    p = Probe(a)
    ok = True
    for tag, _unused, val in (("plain", 0, 2), ("alternate", 0, 1)):
        p.row(ROW_SAVER, 0)
        p.ddc.set(0xEB, 0)
        p.ddc.set(0xEB, val)
        p.sess.bus.wait(1.0)
        before = p.state()
        p.ddc.get(0x10)
        p.sess.bus.wait(0.5)
        after = p.state()
        good = "run pacman" in before and "why 0x03" in before.replace("0x83", "0x03") and "run pacman" in after
        say(f"{'PASS' if good else 'FAIL'} now_ddc {tag}: before {before} | after a Get VCP 0x10: {after}")
        ok &= good
        p.ddc.set(0xEB, 0)
    p.sess.bus.close()
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/saver_mode_sim")
    ap.add_argument("--case", nargs="*", default=["idle_loss", "nosig_default", "nosig_l3off", "nosig_key", "nosig_lock", "now_ddc"])
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"saver_mode_sim {a.bin.name}")
    fails = 0
    for c in a.case:
        fails += {"idle_loss": idle_loss, "nosig_default": nosig_default, "nosig_l3off": nosig_l3off, "nosig_key": nosig_key, "nosig_lock": nosig_lock, "now_ddc": now_ddc}[c](a)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
