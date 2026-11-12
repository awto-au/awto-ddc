#!/usr/bin/env python3
"""System machine gate (awto-ddc#162 step 3): one owner of the power status + mode state, every change requested and logged.

usage: AWTO_SIM_CORE=fast sysm_sim.py BIN MAP [--tree DIR] [--mode 1080p60] [--report]
Scenario (dw8051 core): cold boot -> ACTIVE; POWER off / on (test cmd 0x3E); POWER off during display setting; switch to D3
(test cmd 0x33, no source) and back to D2 (0x32); signal lost (L1 hold) and back; power saving by DDC/CI VCP D6 = 4; SOURCE-key wake;
unsupported timing (UserCommonInterfaceCheckNoSupport forced true, D3 -> D2): NO SUPPORT kept, then the OSD's power saving (SDK path).
FAIL (gate):
- a firmware write that changes the power status / power target (g_stPowerInfo) or the mode state / mode reset target
  (g_stModeInfo) without g_ucAwtoSysOwn = 1 (after the machine's init);
- a 'system: A -> B' line whose A is not the B of the line before (chain broken), or a state name missing (hex in the line);
- a transition line whose SDK mode text ('; <text>', sync.tsv 1A, #162 s3b) is missing although the mode changed, present
  although it did not, or not the new state's text; the first line not 'RESET -> AC ON' with the POWER OFF text;
- a mode text with no row (hex), or a request line of the panel machine without its requester ('requested by <who>');
- a phase that does not reach its state (bounds below), or a 'target written without a request' line from the firmware's own phases;
- --tree: SET_MODE_STATE / SET_POWER_STATUS / SET_TARGET_POWER_STATUS / SET_MODE_RESET_TARGET outside SysJudge.c, SysPowerSwitch /
  SysModeResetState called outside the machine's files, the old handlers (SysPowerHandler / SysJudgeHandler / SysModeHandler) anywhere.
--report: timeline only (old images have no g_ucAwtoSysOwn). Log: tmp/logs/sysm_sim.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import osd_test as T  # noqa: E402
import sync_log as L  # noqa: E402
from ddc_sim import DdcEngine, Mccs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/sysm_sim.log"
POWER_KEY, K_SOURCE, SEL_D2, SEL_D3 = 0x3E, 0x05, 0x32, 0x33     # test cmds (awto_testcmd.inc)
PWR_OFF, PWR_NORMAL, PWR_SAVING = 1, 2, 3                        # Global.h EnumPowerStatus (g_stPowerInfo high nibble)
MODE_DS, MODE_ACTIVE, MODE_NOSUPPORT, MODE_NOSIGNAL, MODE_PS = 2, 3, 4, 5, 6
STATE_MODE = {"AC ON": 7, "OFF": 7, "INITIAL": 0, "SEARCH": 1, "DISPLAY SETTING": 2, "ACTIVE": 3, "FAST SWITCH": 3, "HOLD L1": 3,
              "NO SUPPORT": 4, "NO SIGNAL": 5, "POWER SAVING": 6, "WAKE SEARCH": 6}       # POWER DOWN keeps the mode before it
BOOT_INSTR = 160_000_000
# Phase bounds (firmware ms; expiry = FAIL): panel_sim's (power off incl. T4 + T5 + flush 1.5 s; on 3 s; hold 1.5 s; PS 3 s);
# no signal after a switch to an empty port: fixed-port HDMI search time 2 s (SDK) + 1 s judge timer, x1.25 -> 4 s;
# wake: SDK auto search after PS_TO_NORMAL, sim 4.2 s seen (s2-2) x1.25 -> 5.5 s
OFF_MS, ON_MS, SETTLE_MS, HOLD_MS, PS_MS, NOSIG_MS, WAKE_MS, T6_MS = 1500, 3000, 1000, 1500, 3000, 4000, 5500, 1300
# no support: hold check 2.5 s (< the OSD's 3 s message); PS = message 3 s + power-saving message 2 s + PS_MS, x1.25 -> 10 s
NOSUP_HOLD_MS, NOSUP_PS_MS = 2500, 10000
STEP = 20_000
OWNED = ("SET_MODE_STATE(", "SET_POWER_STATUS(", "SET_TARGET_POWER_STATUS(", "SET_MODE_RESET_TARGET(")
OLD = ("SysPowerHandler", "SysJudgeHandler", "SysModeHandler")
MACHINE_FILES = ("Kernel/System/Code/SysJudge.c",)
ACTION_FILES = ("Kernel/System/Code/SysJudge.c", "Kernel/System/Code/SysPower.c", "Kernel/System/Code/SysMode.c")


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class StateWatch(S.Dev):
    """Firmware writes to the SDK power / mode views: a change of the watched bits is recorded with the owner flag."""
    MASK = {0: 0xFF, 1: 0x1F, 2: 0xF0}          # g_stPowerInfo byte 0 (target | status); g_stModeInfo byte 0 bits 4..0, byte 1 bits 7..4

    def __init__(self, run, pwr, mode):
        self.run, self.cell = run, {pwr: ("power", 0), mode: ("mode", 1), mode + 1: ("reset", 2)}
        self.writes, self.last = tuple(self.cell), {}

    def init(self, m):
        self.last = {a: m.rd(a)[0] for a in self.cell}

    def on_write(self, m, a):
        v = m.rd(a)[0]
        what, k = self.cell[a]
        mask = self.MASK[k]
        if (v ^ self.last.get(a, v)) & mask:
            self.run.rec(what, self.last.get(a, v) & mask, v & mask)
        self.last[a] = v


class Run:
    def __init__(self, a):
        self.a, self.fails, self.events, self.phase = a, 0, [], "boot"
        self.eng = DdcEngine()
        mp = Path(a.map).read_text(errors="replace")
        self.has_own = re.search(r"\s_g_ucAwtoSysOwn\b", mp) is not None
        m0 = S.SimBus(a.bin, a.map, "sysm-probe", None, boot=False, video=a.mode).m        # addresses before the watch device exists
        pwr, mode = m0.addr("g_stPowerInfo"), m0.addr("g_stModeInfo")
        self.own = m0.addr("g_ucAwtoSysOwn") if self.has_own else None
        m0.close() if hasattr(m0, "close") else None
        w1c = S.W1C({0xFE69: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, 0xBADC: 0x01})    # wake latches as wake_sim.py: no stale latch
        self.bus = S.SimBus(a.bin, a.map, "sysm-" + a.bin.stem, None, boot=False, video=a.mode,
                            devs=[StateWatch(self, pwr, mode), self.eng, w1c])
        self.m = self.bus.m
        self.pwr = pwr
        self.mccs = Mccs(self.bus, self.eng)
        self.diag = T.diag_addr(a.map)
        self.ring = L.sym(a.map, "g_stAwtoSync")
        self.rows = L.load_rows(L.tsv_for(a.map))
        pre = self.m.sym.get("_ScalerTMDSNormalPreDetect", 0) & 0xFFFF
        self.signal = True
        if pre in self.m.stubs:                      # video_stubs' pre-detect: answer by the signal switch (as panel_sim)
            b, n, f = self.m.stubs[pre][0]
            self.m.stubs[pre][0] = (b, n, lambda m_, r, f=f: f(m_, r) if self.signal else {"carry": 0})
        self.lines_seen = []
        self.seq = None

    def t(self):
        return self.bus._t2()

    def rec(self, what, old, new):
        own = self.m.rd(self.own)[0] if self.own is not None else None
        self.events.append((self.t(), self.phase, what, old, new, own))

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def cmd(self, c):
        addr = self.diag + T.TESTCMD_OFF
        b = self.bus
        return b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))

    def power(self):
        return self.m.rd(self.pwr)[0] >> 4

    def until(self, cond, ms):
        t0 = self.t()
        while self.t() - t0 < ms:
            if cond():
                return True, self.t() - t0
            self.m.run(STEP)
        return cond(), self.t() - t0

    def stable_detect(self, ok: bool):
        if "_ScalerTMDSStableDetect" in self.m.sym and getattr(self.m, "hle", True):
            self.m.patch_const("ScalerTMDSStableDetect", 1 if ok else 0)

    def ring_lines(self, title):
        """ring entries pushed since the last read (by ring seq, all episodes), times = firmware ms (mod 65536)"""
        raw = L.read_ring(self.m.rd, self.ring)
        seq, n, wrap = raw[3], raw[12], raw[13]
        last = self.seq if self.seq is not None else (seq - n) % wrap
        k = (seq - last) % wrap
        if k > n:
            self.check(False, f"ring read in time ({title})", f"{k - n} entries overwritten")
            last, k = (seq - n) % wrap, n
        new = []
        for j in range(k):
            s = (last + j) % wrap
            e = raw[L.HDR + L.EV * (s % n):L.HDR + L.EV * (s % n) + L.EV]
            new.append(L.line(self.rows, (e[0], e[1], e[2] << 8 | e[3], int.from_bytes(e[4:8], "big")), 0))
        self.seq = seq
        self.lines_seen += new
        say(f"  ring ({title}): {len(new)} new lines")
        for x in new:
            say(f"    {x}")
        self.phase_lines.setdefault(title, []).extend(new)
        return new

    def step(self, title, action, cond, ms, what):
        self.phase = title
        if action:
            action()
        ok, took = self.until(cond, ms)
        self.check(ok, what, f"{took} ms")
        return ok

    def scenario(self):
        self.phase_lines = {}
        ok = self.bus.run_until_mode(MODE_ACTIVE, BOOT_INSTR)
        self.check(ok, "cold boot: ACTIVE")
        self.bus.dbg_link_on()
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("cold boot")
        self.step("power off", lambda: self.cmd(POWER_KEY), lambda: self.power() == PWR_OFF, OFF_MS, "POWER key: power OFF")
        self.bus.wait(T6_MS / 1000)
        self.ring_lines("power off")
        self.step("power on", lambda: self.cmd(POWER_KEY), lambda: self.bus.mode_state() == MODE_ACTIVE, ON_MS, "POWER key: ACTIVE again")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("power on")
        self.phase = "off in DS"
        self.cmd(POWER_KEY)
        self.bus.wait(T6_MS / 1000)
        self.ring_lines("off before display setting")             # the ring holds 52 lines: read between the steps
        self.step("off in DS", lambda: self.cmd(POWER_KEY), lambda: self.bus.mode_state() == MODE_DS, ON_MS, "POWER on again: DISPLAY SETTING")
        self.ring_lines("on up to display setting")
        self.step("off in DS", lambda: self.cmd(POWER_KEY), lambda: self.power() == PWR_OFF, OFF_MS, "POWER key during DISPLAY SETTING: OFF")
        self.bus.wait(T6_MS / 1000)
        self.ring_lines("off in display setting")
        self.step("power on 2", lambda: self.cmd(POWER_KEY), lambda: self.bus.mode_state() == MODE_ACTIVE, ON_MS, "POWER key: ACTIVE again")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("power on 2")
        self.step("switch D3", lambda: self.cmd(SEL_D3), lambda: self.bus.mode_state() == MODE_NOSIGNAL, NOSIG_MS,
                  "switch to D3 (no source): NO SIGNAL")
        self.ring_lines("switch to D3")
        self.step("switch D2", lambda: self.cmd(SEL_D2), lambda: self.bus.mode_state() == MODE_ACTIVE, ON_MS, "switch back to D2: ACTIVE")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("switch back to D2")
        self.phase = "signal lost"
        self.signal = False
        self.stable_detect(False)
        self.bus.wait(HOLD_MS / 1000)
        lost = self.ring_lines("signal lost")
        self.check(any("-> HOLD L1" in x for x in lost), "signal lost: system ACTIVE -> HOLD L1 (mode stays ACTIVE)")
        self.phase = "signal back"
        self.signal = True
        self.stable_detect(True)
        self.step("signal back", None, lambda: self.bus.mode_state() == MODE_ACTIVE, HOLD_MS, "signal back: ACTIVE")
        self.bus.wait(SETTLE_MS / 1000)
        back = self.ring_lines("signal back")
        self.check(any("HOLD L1 -> FAST SWITCH" in x for x in back) and any("FAST SWITCH -> ACTIVE" in x for x in back),
                   "signal back: HOLD L1 -> FAST SWITCH -> ACTIVE")
        self.step("power saving", lambda: self.mccs.set(0xD6, 4), lambda: self.power() == PWR_SAVING, PS_MS, "VCP D6 = 4: power saving")
        self.bus.wait(0.3)
        ps = self.ring_lines("power saving")
        self.check(any("power saving requested by DDC/CI VCP D6 power mode" in x for x in ps), "power saving requested by VCP D6 (logged)")
        self.step("wake", lambda: self.cmd(K_SOURCE), lambda: self.bus.mode_state() == MODE_ACTIVE, WAKE_MS, "SOURCE key wake: ACTIVE")
        self.bus.wait(SETTLE_MS / 1000)
        wk = self.ring_lines("wake")
        self.check(any("power on requested by front key in power saving" in x for x in wk), "wake requested by the front key (logged)")
        self.no_support()

    def no_support(self):
        """SDK no-support path (hidden customer branches issue): no-support timer -> NO SUPPORT, no search loop, then the OSD's
        NO SUPPORT message (3 s) -> power-saving message (2 s) -> power-saving request. Last phase: the patch is not undone."""
        if "_UserCommonInterfaceCheckNoSupport" not in self.m.sym:
            self.check(False, "no support: UserCommonInterfaceCheckNoSupport in the map")
            return
        self.m.patch_const("UserCommonInterfaceCheckNoSupport", 1)
        self.step("no support", lambda: self.cmd(SEL_D3), lambda: self.bus.mode_state() == MODE_NOSIGNAL, NOSIG_MS,
                  "no support: switch to D3 first (NO SIGNAL)")
        self.ring_lines("no support: D3")
        self.step("no support", lambda: self.cmd(SEL_D2), lambda: self.bus.mode_state() == MODE_NOSUPPORT, ON_MS,
                  "unsupported timing on D2: NO SUPPORT")
        held, _ = self.until(lambda: self.bus.mode_state() != MODE_NOSUPPORT, NOSUP_HOLD_MS)
        self.check(not held, f"NO SUPPORT kept {NOSUP_HOLD_MS} ms (no search loop)")
        # signal still on the port: the SDK takes fake power saving (mode POWER SAVING, power status kept NORMAL)
        self.step("no support PS", None, lambda: self.bus.mode_state() == MODE_PS, NOSUP_PS_MS, "NO SUPPORT -> OSD power saving (mode)")
        ns = self.ring_lines("no support")
        self.check(any("-> NO SUPPORT" in x for x in ns), "no support: system transition into NO SUPPORT logged")
        self.check(not any("NO SUPPORT -> SEARCH" in x for x in ns), "no support: no NO SUPPORT -> SEARCH loop")

    def judge(self):
        ev = self.events
        say("  view changes (fw ms, phase, view, old, new, owner flag):")
        for t, ph, w, o, n, own in ev:
            say(f"    {t:7d} {ph:13s} {w:6s} {o:02X} -> {n:02X} {'-' if own is None else own}")
        lines = [x for ph in self.phase_lines.values() for x in ph]
        if self.a.report or not self.has_own:
            say("  report only" + ("" if self.has_own else " (no g_ucAwtoSysOwn in this image)"))
            return
        first = next((i for i, e in enumerate(ev) if e[5] == 1), None)
        outside = [e for e in ev[first or 0:] if e[5] != 1]
        self.check(first is not None and not outside, "every power / mode view change after the machine's init is the machine's",
                   "; ".join(f"{t} {ph} {w} {o:02X}->{n:02X}" for t, ph, w, o, n, _ in outside[:6]))
        trans = [(i, m.group(1), m.group(2)) for i, x in enumerate(lines)
                 if (m := re.search(r"system: (.+?) -> (.+?): ", x))]
        broken = [(a, b) for (_, _, a2), (_, b, _) in zip(trans, trans[1:]) for a, b in [(a2, b)] if a != b]
        self.check(trans and not broken, f"transition chain unbroken ({len(trans)} transitions)", str(broken[:4]))
        unnamed = [x for x in lines if re.search(r"system: .*\b[0-9A-F]{2}\b -> |-> [0-9A-F]{2}: |requested by [0-9A-F]{2} ", x)]
        self.check(not unnamed, "every state / who / request has a name (no hex code in a system line)", str(unnamed[:3]))
        texts = {r["arg"]: r["text"] for r in self.rows if r["id"] == L.SYS_MODE}     # mode text per state index
        names = {r["text"]: r["arg"] for r in self.rows if r["id"] == L.SYS_STATE}
        bad, mode = [], None
        for i, a, b in trans:
            x = lines[i]
            tail = x.split(" ms in ", 1)[1].split(")", 1)[1]               # after '(N ms in OLD)'
            new = STATE_MODE.get(b, mode)                                    # POWER DOWN keeps the mode before it
            want = f"; {texts.get(names.get(b), '?')}" if new != mode else ""
            if tail != want:
                bad.append(f"{x} (want tail {want!r})")
            mode = new
        self.check(trans and trans[0][1:] == ("RESET", "AC ON") and not bad,
                   "mode text on exactly the transitions that change the SDK mode (first: RESET -> AC ON, POWER OFF)", str(bad[:3]))
        req = [x for x in lines if re.search(r"(panel|backlight) (on|off) requested", x) and " requested by " not in x]
        self.check(not req, "every panel request line names its requester", str(req[:3]))
        direct = [x for x in lines if "target written without a request" in x]
        self.check(not direct, "no power target without a request", str(direct[:3]))


def lint(tree: Path, r: Run):
    sdk = tree / "fw/sdk"
    src = [p for p in sdk.rglob("*") if p.suffix in (".c", ".h")] + list((tree / "fw/sdcc").glob("*.inc"))
    owned, calls, old = [], [], []
    for p in src:
        rel = str(p.relative_to(sdk)) if sdk in p.parents else str(p.relative_to(tree))
        for n, ln in enumerate(p.read_text(errors="replace").splitlines(), 1):
            code = ln.split("//")[0]
            if re.match(r"\s*#\s*define\b", code):
                continue
            if rel not in MACHINE_FILES and any(o in code for o in OWNED):
                owned.append(f"{rel}:{n}")
            if rel not in ACTION_FILES and re.search(r"\b(SysPowerSwitch|SysModeResetState)\s*\(", code) and not re.search(r"\bextern\b", code):
                calls.append(f"{rel}:{n}")
            if any(re.search(rf"\b{o}\s*\(", code) for o in OLD):
                old.append(f"{rel}:{n}")
    r.check(not owned, "static: SDK power / mode views written only in SysJudge.c", ", ".join(owned[:6]))
    r.check(not calls, "static: SysPowerSwitch / SysModeResetState called only by the machine (SysJudge.c, SysPower.c, SysMode.c)", ", ".join(calls[:6]))
    r.check(not old, "static: SysPowerHandler / SysJudgeHandler / SysModeHandler gone", ", ".join(old[:6]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--tree", type=Path, help="worktree: static checks of its fw/sdk + fw/sdcc")
    ap.add_argument("--report", action="store_true", help="timeline only, no verdict (old images)")
    ap.add_argument("--out", type=Path, help="unused (sim_timelines passes it to every sim)")
    a = ap.parse_args()
    say(f"sysm_sim {a.bin.name}")
    r = Run(a)
    try:
        r.scenario()
        r.judge()
    finally:
        r.bus.close()
    if a.tree and not a.report:
        lint(a.tree, r)
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} sysm_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
