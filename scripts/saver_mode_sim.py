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
import isostamp  # noqa: E402
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import osd_model as M  # noqa: E402
import ddc_sim as D  # noqa: E402
import pacman_sim as P  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_mode_sim.log"
ROW_SAVER, ROW_SAVER_S, ROW_DISP_ROTATE, ROW_PWR_L3_EN = 119, 120, 32, 79    # fw/rtdfw/settings/registry.tsv
SAVER_PACMAN, IDLE_S = 1, 10                                     # registry: screensaver Pac-Man, screensaver_s step 10
IDLE_WAIT_S = IDLE_S + 2.0                                       # idle start + one Pac-Man draw
NOSIG_START_S = 10.0 + 4.0                                       # AWTO_SAVER_NOSIG_MS after NO SIGNAL (+ search ~4 s)
TRACE_S, TRACE_STEP_S = 6.0, 0.25                                # after the input switch: SDK search + no-signal pop-up timers
LOCK_S = 5.0                                                     # D2 search + display setting to ACTIVE (boot ~0.75 s, x6)
TC_D2, TC_D3 = 0x32, 0x33
D3_PIN = 0xFE2C                                                  # wake_sim D3_PIN: D3 cabled, no source
RUN_NAMES = {0: "off", 1: "pacman", 2: "scope", 3: "scope2", 5: "flash", 6: "splash"}


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
    ok = first is not None and st[first].startswith("run off") and all(s.startswith("run off") for s in st[first:])
    say(f"{'PASS' if ok else 'FAIL'} idle_loss: saver off from the first sample without ACTIVE (before the SDK no-signal card): "
        f"{st[first] if first is not None else 'mode never left ACTIVE'}")
    p.png("idle_loss_after.png")
    say(f"idle_loss: PNGs {a.out}/idle_loss_before.png, idle_loss_after.png")
    p.sess.bus.close()
    return 0 if (started and ok) else 1


def nosig_l3on(a) -> int:
    """Defaults (pwr_l3_en = 1): does the no-signal saver start before the SDK's power saving? Report only."""
    p = Probe(a)
    p.row(ROW_SAVER, SAVER_PACMAN)
    p.m.wr(D3_PIN, b"\x00")
    P.send(p.sess, TC_D3)
    st = p.trace(NOSIG_START_S, "nosig_l3on")
    ran = any("run pacman" in s for s in st)
    say(f"REPORT nosig_l3on: no-signal saver {'ran' if ran else 'never started'} before power saving; last: {st[-1]}")
    p.sess.bus.close()
    return 0


def nosig_lock(a) -> int:
    p = Probe(a)
    p.row(ROW_SAVER, SAVER_PACMAN)
    p.row(ROW_SAVER_S, IDLE_S)                                  # idle start on too: the picture that ends the saver must not start it again
    p.row(ROW_PWR_L3_EN, 0)                                     # power saving ignored: no signal stays NOSIGNAL
    p.m.wr(D3_PIN, b"\x00")
    P.send(p.sess, TC_D3)
    p.trace(NOSIG_START_S, "nosig_wait")
    s0 = p.state()
    started = "run pacman why 0x01" in s0
    say(f"{'PASS' if started else 'FAIL'} nosig_lock: no-signal saver started (pwr_l3_en 0): {s0}")
    run = p.trace(TRACE_S, "nosig_run")
    wiped = any("run pacman" in s and "grid 28x36" not in s for s in run)
    say(f"REPORT nosig_lock: {'the SDK no-signal card took the OSD while the saver runs (open decision, docs/saver-mode.md)' if wiped else 'saver kept the OSD'}: {run[-1]}")
    p.png("nosig_saver.png")
    P.send(p.sess, TC_D2)
    st = p.trace(LOCK_S, "nosig_lock")
    first = next((i for i, s in enumerate(st) if " mode 3 " in s), None)               # first sample with the picture back
    stopped = first is not None and all(s.startswith("run off") for s in st[first:])
    say(f"{'PASS' if stopped else 'FAIL'} nosig_lock: D2 locked, saver off and no idle restart over the new picture for "
        f"{LOCK_S} s: {st[-1]}")
    p.sess.bus.close()
    return 0 if (started and stopped) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/saver_mode_sim")
    ap.add_argument("--case", nargs="*", default=["idle_loss", "nosig_l3on", "nosig_lock"])
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"saver_mode_sim {a.bin.name}")
    fails = 0
    for c in a.case:
        fails += {"idle_loss": idle_loss, "nosig_l3on": nosig_l3on, "nosig_lock": nosig_lock}[c](a)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
