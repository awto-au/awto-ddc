#!/usr/bin/env python3
"""Verify the fast 8051 core (fastmachine.py / mcs51_core.c) against ucsim. Offline; no hardware.

usage: fastcore_check.py diff BIN MAP [--fine 5000000 --fine-step 100000 --coarse 30000000 --coarse-step 1000000 --irq-window 300]
       fastcore_check.py diffbus BIN MAP --coarse 150000000   SimBus(video) + OsdModel lockstep to ACTIVE, debug cmd 0x43
       fastcore_check.py fuzz BIN MAP [--seeds 30]   random code images, lockstep (opcodes the firmware never runs)
       fastcore_check.py gates BIN MAP         fw_sim --boot-check / --video-check, ucsim vs --fast: verdict + key lines
       fastcore_check.py gpio BIN MAP           gpio_shot.py --cmds 0x43 on both cores, PIL pixel compare
       fastcore_check.py speed BIN MAP          instr/s + boot-to-ACTIVE wall time (video devs, 1080p60), both cores
       fastcore_check.py timing                 dw8051 timing model (scripts/dw8051_model.json): per-opcode cycles, MOVX stretch, timer
         clk/12 and clk/4, dual DPTR, dual-clock model f_cpu per register state. No image, no ucsim.
  --cpu: diff / diffbus / fuzz / gates compare against ucsim = classic 8052 cycle counts: they run in --cpu 8052 (the default there;
  dw8051 is refused). timing runs in dw8051. The selected mode is logged on the first line (AWTO_SIM_CPU).
  diff: both cores from reset with the flash-port model (FlashPort on ucsim, FlashDev on the core; same IRAM seed);
  compares PC ACC B PSW DPTR SP R0-R7, code bank, instruction + clock counts, IRAM and SFR (hash + first differing byte)
  every --fine-step to --fine, then every --coarse-step to --coarse (XDATA hash there too); around the first
  interrupt every instruction for --irq-window instructions each side. On a mismatch: rerun to the last good
  checkpoint and single-step both to the first differing instruction (printed with the opcode bytes).
Log: tmp/logs/fastcore_check.log (all modes, appended).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw_sim as S  # noqa: E402
import fastmachine as F  # noqa: E402

ROOT = S.ROOT
LOG = ROOT / "tmp/logs/fastcore_check.log"
TOOL_LIMIT_S = 460              # one fw_sim tool run: 3x the slowest cold run (ucsim video-check, tmp/logs/fastcore_check.log)
UCSIM_ANSWER_S = 120            # one ucsim command: a 1 M-instruction step is ~1.5 s; 120 s matches fw_sim's own limit


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(s, flush=True)


# ---- ucsim side: exact instruction counts from `state` (Inst=) ----
class UcState:
    """CPU state from a ucsim session (needs self.cmd)."""

    @staticmethod
    def rows(out: str, width: int | None) -> dict[int, int]:
        """addr -> byte from dump rows; a row holds `width` bytes (None: up to the next row's address; the ASCII column
        after the hex can look like hex)."""
        rows = [(int(m.group(1), 16), m.group(2).split())
                for m in re.finditer(r"^0x([0-9a-f]{2,6})\s{2,}((?:[0-9a-f]{2} )+)", out, re.M)]
        named = sorted(int(m.group(1), 16) for m in re.finditer(r"^0x([0-9a-f]{2})\s+\w+:\s+0b", out, re.M))
        got = {}
        for base, toks in rows:
            nxt = min([b for b, _ in rows if b > base] + [b for b in named if b > base] + [base + 256])
            for i, h in enumerate(toks[:width if width else nxt - base]):
                got[base + i] = int(h, 16)
        return got

    def state(self) -> dict:
        out = self.cmd("state\ninfo registers")
        iram = self.rows(self.cmd("dump iram 0 0xff 8"), 8)
        so = self.cmd("dump sfr 0x80 0xff")
        sfr = self.rows(so, None)
        for m in re.finditer(r"^0x([0-9a-f]{2})\s+\w+:\s+0b[01]{8} 0x([0-9a-f]{2})", so, re.M):
            sfr[int(m.group(1), 16)] = int(m.group(2), 16)
        xf = self.rows(self.cmd("dump xram 0xffff 0xffff"), 1).get(0xFFFF, -1)
        st = {"instr": int(re.search(r"Inst= (\d+)", out).group(1)),
              "clks": int(re.search(r"\((\d+) clks\)", out).group(1)),
              "pc": int(re.search(r"PC= 0x([0-9a-f]+)", out).group(1), 16)}
        r = re.search(r"R0 R1 R2 R3 R4 R5 R6 R7\s*\n\s*((?:[0-9a-f]{2} ){7}[0-9a-f]{2})", out).group(1)
        st["r"] = [int(x, 16) for x in r.split()]
        st["acc"] = int(re.search(r"ACC= 0x([0-9a-f]{2})", out).group(1), 16)
        st["b"] = int(re.search(r"B= 0x([0-9a-f]{2})", out).group(1), 16)
        st["psw"] = int(re.search(r"PSW= 0x([0-9a-f]{2})", out).group(1), 16)
        st["sp"] = int(re.search(r"SP 0x([0-9a-f]{2})", out).group(1), 16)
        st["dptr"] = int(re.search(r"DPTR= 0x([0-9a-f]{4})", out).group(1), 16)
        if len(iram) != 256 or len(sfr) != 128:
            raise S.SimError(f"ucsim dump parse: iram {len(iram)} sfr {len(sfr)} bytes")
        st["iram"] = bytes(iram[a] for a in range(256))
        st["sfr"] = bytes(sfr[a] for a in range(0x80, 0x100))
        st["bank"] = xf & 15 if xf >= 0 else -1
        return st

    def xram_hash(self) -> str:
        got = self.rows(self.cmd("dump xram 0 0xffff 16"), 16)
        if len(got) != 0x10000:
            raise S.SimError(f"ucsim xram dump parse: {len(got)} bytes")
        return hashlib.sha1(bytes(got[a] for a in range(0x10000))).hexdigest()[:12]


class Uc(UcState):
    """Raw ucsim + FlashPort (fw_sim.open_native)."""

    def __init__(self, img: bytes, tag: str):
        self.flash = S.FlashPort(img)
        self.dir = ROOT / "tmp/fastcore" / f"{tag}.{os.getpid()}"
        self.s = S.open_native(img, self.dir, S._Null(), self.flash, [])
        self.n = 0
        self.cmd("fill xram 0x0 0xfffe 0x0")
        self.flash_events = 0

    def cmd(self, text: str) -> str:
        self.n += 1
        tag = f"@@{self.n}"
        self.s.send(f"{text}\necho {tag}")
        out = self.s.read_until(rb"(?:^|\n)" + tag.encode() + rb"\n", UCSIM_ANSWER_S)
        if out is None:
            raise S.SimError(f"ucsim did not answer `{text[:60]}`")
        return out

    def step_to(self, target: int, cur: int) -> int:
        """Step until Inst == target, serving flash-port events; returns Inst."""
        while cur < target:
            out = self.cmd(f"step {target - cur}")              # short steps print no "Simulated" line: sync on the echo
            if self.flash.handle(self.s, out):
                self.flash_events += 1
            cur = int(re.search(r"Inst= (\d+)", self.cmd("state")).group(1))
        return cur

    def close(self):
        self.s.send("quit")
        try:
            self.s.p.wait(10)
        except subprocess.TimeoutExpired:
            self.s.p.kill()
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def fast_state(m) -> dict:
    c, p = m.core, m.p
    g = c.regs()
    return {"instr": p.instr, "clks": p.cycles * 12, "pc": p.pc, "r": g["r"], "acc": g["acc"], "b": g["b"], "psw": g["psw"],
            "sp": g["sp"], "dptr": g["dptr"], "iram": bytes(c.iram), "sfr": bytes(c.sfr), "bank": c.xram[0xFFFF] & 15}


KEYS = ("instr", "clks", "pc", "acc", "b", "psw", "dptr", "sp", "r", "bank", "iram", "sfr")


def compare(u: dict, f: dict) -> list[str]:
    bad = []
    for k in KEYS:
        if u[k] != f[k]:
            if k in ("iram", "sfr"):
                base = 0 if k == "iram" else 0x80
                i = next(i for i in range(len(u[k])) if u[k][i] != f[k][i])
                bad.append(f"{k}[0x{base + i:02x}] ucsim 0x{u[k][i]:02x} fast 0x{f[k][i]:02x}")
            else:
                bad.append(f"{k} ucsim {u[k]} fast {f[k]}")
    return bad


def fast_run(m, n: int):
    """Exactly n instructions on the core (FlashDev events served by FastMachine.run)."""
    goal = m.p.instr + n
    while m.p.instr < goal:
        m.run(goal - m.p.instr)


def new_pair(img: bytes, mapp: Path, tag: str):
    u = Uc(img, tag)
    fd = S.FlashDev(img)
    m = F.bind(S, exact=True)(img, mapp, tag, None, [fd])
    seed = u.state()["iram"]
    if seed != bytes(m.core.iram):
        say("NOTE ucsim power-on IRAM differs from fastmachine.ucsim_iram(); seeding from ucsim")
    m.core.iram[:] = seed
    return u, m, fd


def first_divergence(img, mapp, good: int, bad: int) -> str:
    u, m, _ = new_pair(img, mapp, "fc-bisect")
    try:
        cur = u.step_to(good, 0)
        fast_run(m, good)
        prev = None
        while cur < bad:
            us, fs = u.state(), fast_state(m)
            d = compare(us, fs)
            if d:
                pc = prev["pc"] if prev else us["pc"]
                bank = prev["bank"] if prev else us["bank"]
                ops = m.rd(pc, 3, "rom").hex() if prev else "?"
                return (f"first divergence after instruction {cur}: previous PC 0x{pc:04x} bank {bank} "
                        f"({m.where(bank, pc)}) bytes {ops}: " + "; ".join(d[:6]))
            prev = us
            cur = u.step_to(cur + 1, cur)
            fast_run(m, 1)
        return "no divergence found in single-step range"
    finally:
        u.close(); m.close()


def find_first_irq(img: bytes, mapp: Path) -> tuple[int, int]:
    """(instructions before the first interrupt entry, vector) on the core alone."""
    fd = S.FlashDev(img)
    m = F.bind(S, exact=True)(img, mapp, "fc-irq", None, [fd])
    try:
        while m.p.nirq == 0 and m.p.instr < 50_000_000:
            fast_run(m, 1)
        return m.p.instr, m.p.pc
    finally:
        m.close()


def cmd_diff(a) -> int:
    img, mapp = a.bin.read_bytes(), a.map
    first_irq, vec = find_first_irq(img, mapp)
    win = set(range(max(0, first_irq - a.irq_window), first_irq + a.irq_window + 1))
    pts = sorted(set(range(0, a.fine + 1, a.fine_step)) | set(range(a.fine, a.coarse + 1, a.coarse_step)) | win)
    say(f"diff {a.bin.name}: {len(pts)} checkpoints to {pts[-1]} instr (every {a.fine_step} to {a.fine}, every "
        f"{a.coarse_step} to {a.coarse}, every instruction {min(win)}..{max(win)} around the first interrupt: core enters "
        f"vector 0x{vec:02x} after instruction {first_irq})")
    u, m, fd = new_pair(img, mapp, "fc-diff")
    t0, ok, last_good, cur, p = time.monotonic(), True, 0, 0, 0
    try:
        for p in pts:
            cur = u.step_to(p, cur)
            fast_run(m, p - m.p.instr)
            us, fs = u.state(), fast_state(m)
            d = compare(us, fs)
            xh = ""
            if p > a.fine and p % a.coarse_step == 0 and not d:
                hu, hf = u.xram_hash(), F_xram_hash(m)
                xh = f" xdata {hu}"
                if hu != hf:
                    d = [f"xdata hash ucsim {hu} fast {hf}"]
            if d:
                say(f"FAIL checkpoint {p}: " + "; ".join(d[:8]))
                ok = False
                break
            last_good = p
            if p % 1_000_000 == 0 or p == max(win):
                say(f"ok {p:>9} instr: pc 0x{fs['pc']:04x} bank {fs['bank']} clks {fs['clks']} irqs {m.p.nirq} "
                    f"flash reads {fd.fp.reads}{xh} ({time.monotonic() - t0:.0f} s)")
    finally:
        cnt = list(m.core.opcount)
        u.close(); m.close()
    if not ok:
        say(first_divergence(img, mapp, last_good, p))
        return 1
    say(f"PASS diff: {len(pts)} checkpoints identical to {pts[-1]} instr ({time.monotonic() - t0:.0f} s)")
    say(f"opcode coverage: {sum(1 for c in cnt if c)}/255 opcodes executed; never: " +
        " ".join(f"{i:02x}" for i in range(256) if i != 0xA5 and not cnt[i]))
    return 0


def F_xram_hash(m) -> str:
    return hashlib.sha1(bytes(m.core.xram)).hexdigest()[:12]


# ---- random-code fuzz: opcodes the firmware never executes ----
class FuzzUc(Uc):
    """Plain ucsim -t 52 on one 64 KiB code image (no banker, no flash port)."""

    def __init__(self, ihx: Path):
        self.flash = None
        self.dir = None
        self.s = S.Sim(ihx, S._Null())
        self.n = 0
        self.cmd("fill xram 0x0 0xffff 0x0")
        want = Path(ihx).read_text().split("\n")[0][9:11].lower()             # code byte 0 from the ihx record
        if not re.search(rf"0x0000\s+{want}\b", self.cmd("dump rom 0 0")):
            raise S.SimError(f"ucsim did not load {ihx}")
        self.flash_events = 0

    def step_to(self, target: int, cur: int) -> int:
        while cur < target:
            self.cmd(f"step {target - cur}")
            cur = int(re.search(r"Inst= (\d+)", self.cmd("state")).group(1))
        return cur

    def close(self):
        self.s.send("quit")
        try:
            self.s.p.wait(10)
        except subprocess.TimeoutExpired:
            self.s.p.kill()


def core_state(c) -> dict:
    g = c.regs()
    return {"instr": c.p.instr, "clks": c.p.cycles * 12, "pc": g["pc"], "r": g["r"], "acc": g["acc"], "b": g["b"],
            "psw": g["psw"], "sp": g["sp"], "dptr": g["dptr"], "iram": bytes(c.iram), "sfr": bytes(c.sfr),
            "bank": c.xram[0xFFFF] & 15}


def cmd_fuzz(a) -> int:
    """Random 64 KiB code (bytes 0xA5 -> NOP, 0x98/0x99 -> 0x9A: serial port not modelled), both cores
    from reset, state compared every --fuzz-step instructions for --fuzz-instr per seed; first divergence single-stepped."""
    import random
    total, ok = [0] * 256, True
    d = ROOT / "tmp/fastcore"
    d.mkdir(parents=True, exist_ok=True)
    for seed in range(a.seeds):
        code = bytearray(random.Random(seed).randbytes(BANK_SIZE))
        code = bytes(0x00 if b == 0xA5 else 0x9A if b in (0x98, 0x99) else b for b in code)   # no SCON/SBUF (not modelled)
        ihx = d / f"fuzz{seed}.{os.getpid()}.ihx"
        S.write_ihx(code, ihx)
        u = FuzzUc(ihx)
        c = F.Core(code)
        c.reset()
        c.iram[:] = u.state()["iram"]
        cur, bad = 0, None
        for p in range(a.fuzz_step, a.fuzz_instr + 1, a.fuzz_step):
            cur = u.step_to(p, cur)
            while c.p.instr < p:
                c.run(p - c.p.instr)
            dd = compare(u.state(), core_state(c))
            if dd:
                bad = (p - a.fuzz_step, p, dd)
                break
        cnt = list(c.opcount)
        u.close(); c.free()
        if bad:                                              # single-step from the last good checkpoint
            u, c = FuzzUc(ihx), F.Core(code)
            c.reset(); c.iram[:] = u.state()["iram"]
            cur = u.step_to(bad[0], 0)
            while c.p.instr < bad[0]:
                c.run(bad[0] - c.p.instr)
            prev = None
            while cur < bad[1]:
                dd = compare(u.state(), core_state(c))
                if dd:
                    break
                prev = (c.p.pc, bytes(c.code[c.p.pc:c.p.pc + 3]).hex())
                cur = u.step_to(cur + 1, cur)
                c.run(1)
            say(f"FAIL fuzz seed {seed}: after instr {cur}, previous PC/bytes {prev}: " + "; ".join(dd[:6]))
            u.close(); c.free()
            ok = False
        else:
            say(f"ok fuzz seed {seed}: {a.fuzz_instr} instr identical ({sum(1 for x in cnt if x)} opcodes)")
        total = [t + x for t, x in zip(total, cnt)]
        ihx.unlink(missing_ok=True)
    say(f"{'PASS' if ok else 'FAIL'} fuzz: {a.seeds} seeds, opcodes executed {sum(1 for x in total if x)}/255; never: " +
        " ".join(f"{i:02x}" for i in range(256) if i != 0xA5 and not total[i]))
    return 0 if ok else 1


BANK_SIZE = 0x10000


# ---- Machine-level lockstep: SimBus + video devs + OSD model + stubs on both cores ----
class ExactUc(UcState, S.UcsimMachine):
    """fw_sim.Machine (ucsim) with exact instruction accounting (`state` Inst= after every stop instead of ticks / 21), so
    run(n) executes the same instructions as FastMachine.run(n). Otherwise Machine.run unchanged."""

    def _counts(self) -> tuple[int, int]:
        out = self.cmd("state")
        return int(re.search(r"Inst= (\d+)", out).group(1)), int(re.search(r"\((\d+) clks\)", out).group(1))

    def run(self, n: int) -> str:
        rem, self._stop = n, False
        if self.t2_scale > 1 and self.instr - self._t2_at >= 100_000:
            self._t2_at = self.instr
            self._scale_t2()
        while True:
            out = self.cmd(f"step {max(rem, 1)}")
            if "Breakpoint" in out:                     # ucsim counts a breakpoint stop in Inst= (and as a step)
                self._bp = getattr(self, "_bp", 0) + 1
            i, self.ticks = self._counts()
            i -= getattr(self, "_bp", 0)
            used, self.instr = i - self.instr, i
            ev = [(("s" if sp == "sfr" else "") + k, a) for k, sp, a in re.findall(r"Event `(\w+)' at (xram|sfr)\[0x([0-9a-f]+)\]", out)]
            self.last_out = out
            if not ev:
                stop = re.search(r"Stop at 0x([0-9a-f]+)", out)
                if stop and int(stop.group(1), 16) in self.stubs and "Breakpoint" in out:
                    self._do_stub(int(stop.group(1), 16), out)
                    rem -= used
                    if rem <= 0 or self._stop:
                        return out
                    continue
                return out
            rem -= used
            for kind, a in ev:
                getattr(self.hook[(kind, int(a, 16))], "on_" + kind)(self, int(a, 16))
            self.flush()
            if rem <= 0 or self._stop:
                return out


def make_bus(cls, binp: Path, mapp: Path, tag: str):
    import osd_model as M
    model = M.OsdModel()
    model.img = binp.read_bytes()
    old = S.Machine
    S.Machine = cls
    try:
        b = S.SimBus(binp, mapp, tag, None, boot=False, devs=[model], video="1080p60")
    finally:
        S.Machine = old
    b.model = model
    return b


def bus_compare(bu, bf, where: str) -> list[str]:
    us, fs = bu.m.state(), fast_state(bf.m)
    us["instr"] -= getattr(bu.m, "_bp", 0)
    d = compare(us, fs)
    if not d and bu.m.xram_hash() != F_xram_hash(bf.m):
        d.append(f"xdata hash ucsim {bu.m.xram_hash()} fast {F_xram_hash(bf.m)}")
    if bu.m.stub_hits != bf.m.stub_hits:
        d.append(f"stub hits ucsim {bu.m.stub_hits} fast {bf.m.stub_hits}")
    su, sf = bu.model.st, bf.model.st
    if (su.win, su.font, su.pal, su.nwr) != (sf.win, sf.font, sf.pal, sf.nwr):
        d.append(f"OSD model state differs (writes ucsim {su.nwr} fast {sf.nwr})")
    if bytes(bu.iic.tx) != bytes(bf.iic.tx) or bu.iic.released != bf.iic.released:
        d.append("debug slave state differs")
    if d:
        say(f"FAIL {where}: " + "; ".join(d[:8]))
    return d


def cmd_diffbus(a) -> int:
    """SimBus(video=1080p60) + OsdModel on ExactUc and FastMachine in lockstep: boot to ACTIVE in 1 M chunks, debug link on,
    gpio_shot's test command 0x43 (3 debug-slave writes + waits); state, XDATA, stub hits, OSD model, debug slave compared."""
    t0 = time.monotonic()
    bu = make_bus(ExactUc, a.bin, a.map, "fc-bus-u")
    bf = make_bus(F.bind(S, exact=True), a.bin, a.map, "fc-bus-f")
    bf.m.core.iram[:] = bu.m.state()["iram"]
    n, bad, steps = 0, [], 0
    try:
        bad = bus_compare(bu, bf, "reset")
        while not bad and n < a.coarse:
            bu.m.run(1_000_000); bf.m.run(1_000_000); n += 1_000_000; steps += 1
            bad = bus_compare(bu, bf, f"chunk {n}")
            mu, mf = bu.mode_state(), bf.mode_state()
            if n % 5_000_000 == 0 or mu == 3:
                say(f"ok {n:>9}: mode {mu}/{mf} instr {bu.m.instr}/{bf.m.instr} stub hits {sum(bf.m.stub_hits.values())} "
                    f"OSD writes {bf.model.st.nwr} ({time.monotonic() - t0:.0f} s)")
            if mu == 3 and mf == 3:
                break
        if not bad:
            bu.dbg_link_on(); bf.dbg_link_on()
            bad = bus_compare(bu, bf, "dbg_link_on")
        import osd_test as OT
        addr = bf.diag_base + OT.TESTCMD_OFF
        for i, (sub, val) in enumerate(((0x01, addr >> 8), (0x03, 0x43), (0x3B, addr & 0xFF))):
            if bad:
                break
            ru, rf = bu.write(0x6A, sub, bytes([val])), bf.write(0x6A, sub, bytes([val]))
            if ru != rf:
                bad = [f"write {i} ack ucsim {ru} fast {rf}"]
                say("FAIL " + bad[0])
                break
            bad = bus_compare(bu, bf, f"debug write {i} (sub 0x{sub:02x} = 0x{val:02x}, ack {ru})")
            steps += 1
        for k in range(3):
            if bad:
                break
            bu.wait(0.5); bf.wait(0.5)
            bad = bus_compare(bu, bf, f"wait {k}")
            steps += 1
        if not bad:
            import osd_model as M
            iu = M.render(bu.model.snapshot(bu.m), 1920, 1080)
            i_f = M.render(bf.model.snapshot(bf.m), 1920, 1080)
            same = bool((iu == i_f).all())
            say(f"{'PASS' if same else 'FAIL'} diffbus: {steps} compares identical to {bf.m.instr} instr, OSD writes "
                f"{bf.model.st.nwr}, stub hits {bf.m.stub_hits}, render identical {same} ({time.monotonic() - t0:.0f} s)")
            return 0 if same else 1
        return 1
    finally:
        bu.close(); bf.close()


# ---- gates / gpio / speed: subprocesses on both cores ----
def run_proc(args: list[str], fast: bool, tag: str) -> tuple[int, str, float]:
    """Run a fw_sim tool; output -> tmp/logs/fastcore_<tag>_<core>.log. The tools print nothing while they boot (ucsim:
    minutes), so the guard is an overall TOOL_LIMIT_S, not a stall timeout; on expiry: kill, log limit + loadavg."""
    env = {**os.environ, "AWTO_SIM_CORE": "fast" if fast else "ucsim"}
    logf = ROOT / "tmp/logs" / f"fastcore_{tag}_{'fast' if fast else 'ucsim'}.log"
    t0 = time.monotonic()
    try:
        r = subprocess.run([sys.executable, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=ROOT,
                           text=True, timeout=TOOL_LIMIT_S)
        rc, out = r.returncode, r.stdout
    except subprocess.TimeoutExpired as e:
        rc, out = -9, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        out += f"\nTIMEOUT: {' '.join(args[:2])} still running after {TOOL_LIMIT_S} s; loadavg {os.getloadavg()}"
    dt = time.monotonic() - t0
    logf.write_text(out)
    return rc, out, dt


def cmd_timing(a) -> int:
    """dw8051 timing model vs the databook tables in dw8051_model.json (instruction cycles, MOVX stretch, timer rates, DPS)."""
    import json
    mdl = json.loads(F.MODEL_JSON.read_text())
    fails = []

    def core(code: bytes):
        c = F.Core(code + bytes(64))
        c.set_dw(mdl)
        c.reset()
        return c
    n = 0
    for op in range(256):
        if op == 0xA5:
            continue
        for md in (range(8) if op in (0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3) else (1,)):
            c = core(bytes([op, 0, 0]))
            c.sfr[0x0E] = md                                  # CKCON (0x8E): MD2..0
            c.sfr[0x20] = 1                                   # IE: nothing
            c.run(1)
            if op in (0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3):
                want = mdl["movx"]["base_cycles"] + md
            else:
                want = mdl["cycles"][op]
            n += 1
            if c.p.cycles != want or c.p.clk != want * mdl["clk_per_cycle"]:
                fails.append(f"op {op:02X} md {md}: {c.p.cycles} cycles / {c.p.clk} clk, want {want}")
    say(f"timing: {n} opcode / stretch cases checked")
    # timers: NOPs only; Timer2 free-running reload mode; CKCON.T2M 0: clk/12, 1: clk/4
    for t2m, div in ((0, mdl["timer_clk_div"]["slow"]), (1, mdl["timer_clk_div"]["fast"])):
        c = core(bytes(1000))
        c.sfr[0x0E] = t2m << 5
        c.sfr[0x48] = 0x04                                    # T2CON (0xC8): TR2, reload mode
        c.sfr[0x4A] = c.sfr[0x4C] = 0                         # RCAP2 / TL2 = 0 (counts up from 0)
        c.sfr[0x4B] = c.sfr[0x4D] = 0
        c.run(300)
        got = c.sfr[0x4D] << 8 | c.sfr[0x4C]
        want = c.p.clk // div
        if got != want:
            fails.append(f"Timer2 T2M={t2m}: count {got}, want clk {c.p.clk} / {div} = {want}")
        say(f"timing: Timer2 T2M={t2m}: {c.p.clk} clk -> {got} counts (clk/{div})")
    # dual DPTR: DPS.0 = 1 -> MOV DPTR,#0x1234 loads DPTR1 and leaves DPTR0
    c = core(bytes([0x90, 0x12, 0x34, 0x90, 0xAB, 0xCD]))
    c.sfr[0x02], c.sfr[0x03] = 0x11, 0x22                     # DPL0 / DPH0
    c.sfr[0x06] = 1                                           # DPS (0x86)
    c.run(1)
    if (c.sfr[0x04], c.sfr[0x05], c.sfr[0x02], c.sfr[0x03]) != (0x34, 0x12, 0x11, 0x22):
        fails.append(f"dual DPTR: DPL1/DPH1/DPL0/DPH0 = {[hex(x) for x in (c.sfr[0x04], c.sfr[0x05], c.sfr[0x02], c.sfr[0x03])]}")
    c.sfr[0x06] = 0
    c.run(1)
    if (c.sfr[0x02], c.sfr[0x03], c.sfr[0x04], c.sfr[0x05]) != (0xCD, 0xAB, 0x34, 0x12):
        fails.append("dual DPTR: DPS = 0 does not select DPTR0")
    say("timing: dual DPTR checked")
    # clock model: f_cpu from register cells (reset, crystal IN_DIV 1, M2PLL 351 MHz / 4, IOSC 28 MHz / 1)
    from sim_clock import ClockModel, XTAL_HZ, IOSC_HZ

    class Cells:
        def __init__(self, v):
            self.v = v

        def rd(self, a):
            return bytes([self.v.get(a, 0)])
    cm = ClockModel()
    cases = [({0xFFED: 0xC8, 0xFFEE: 0x04}, XTAL_HZ / 2, "reset: crystal / 2"),
             ({0xFFED: 0x04, 0xFFEE: 0x04}, XTAL_HZ, "ScalerMcuFlashClockGroupSetting(_EXT_XTAL_CLK)"),
             ({0xFFED: (4 << 2) | 0x02, 0xFFEE: 0x04, 0x01E0: 47, 0x01E1: 0}, XTAL_HZ * 49 / 2 / 4, "M2PLL 351 MHz, flash div 4"),
             ({0xFFED: 0x04, 0xFFEE: 0x04, 0x0009: 0x08}, IOSC_HZ, "power saving: IOSC, div 1")]
    for regs, want, name in cases:
        cm.update(Cells(regs))
        ok = abs(cm.f_cpu - want) < 1
        say(f"timing: f_cpu {name}: {cm.f_cpu / 1e6:.3f} MHz ({cm.src})")
        if not ok:
            fails.append(f"f_cpu {name}: {cm.f_cpu}, want {want}")
    for f_ in fails:
        say(f"FAIL {f_}")
    say(f"{'PASS' if not fails else 'FAIL'} fastcore_check timing: {len(fails)} failed")
    return 1 if fails else 0


def cmd_gates(a) -> int:
    ok = True
    for mode in ("--boot-check", "--video-check"):
        res = {}
        for fast in (False, True):
            rc, out, dt = run_proc([str(HERE / "fw_sim.py"), mode, str(a.bin), str(a.map)], fast, mode.strip("-"))
            res[fast] = (rc, out)
            say(f"{mode} {'fast ' if fast else 'ucsim'}: rc {rc} in {dt:.1f} s")
            for ln in out.splitlines():
                if re.match(r"(PASS|FAIL|RESTART|video-check|timeline|g_stMDomainInputData|stub hits|decision|state at)", ln):
                    say("    " + ln)
        if res[False][0] != res[True][0]:
            say(f"FAIL {mode}: exit code ucsim {res[False][0]} fast {res[True][0]}")
            ok = False
    return 0 if ok else 1


def cmd_gpio(a) -> int:
    from PIL import Image, ImageChops
    outs = {}
    for fast in (False, True):
        out = ROOT / f"tmp/{'fast' if fast else 'ucsim'}_gpio.png"
        rc, txt, dt = run_proc([str(HERE / "gpio_shot.py"), str(a.bin), str(a.map), "--cmds", "0x43", "--out", str(out)],
                               fast, "gpio")
        say(f"gpio_shot {'fast ' if fast else 'ucsim'}: rc {rc} in {dt:.1f} s -> {out.relative_to(ROOT)}")
        for ln in txt.splitlines():
            if "ACTIVE at" in ln or "test cmd" in ln or ln.startswith("png"):
                say("    " + ln)
        outs[fast] = out
    ia, ib = Image.open(outs[False]).convert("RGB"), Image.open(outs[True]).convert("RGB")
    if ia.size != ib.size:
        say(f"FAIL gpio: size {ia.size} vs {ib.size}"); return 1
    bbox = ImageChops.difference(ia, ib).getbbox()
    if bbox is None:
        say(f"PASS gpio: {ia.size[0]}x{ia.size[1]} pixel-identical")
        return 0
    diff = sum(1 for p in ImageChops.difference(ia, ib).getdata() if p != (0, 0, 0))
    say(f"DIFF gpio: {diff} pixels differ, bbox {bbox}")
    return 1


def cmd_speed(a) -> int:
    img = a.bin.read_bytes()
    for fast in (False, True):
        cls = F.bind(S) if fast else S.UcsimMachine
        devs, hdmi = S.video_devs(img, "1080p60")
        t0 = time.monotonic()
        m = cls(img, a.map, "fc-speed", None, devs)
        S.video_stubs(m, hdmi)
        m.t2_scale = S.T2_SCALE
        ma, t1, ms, n = m.addr("isr_g_stModeInfo"), time.monotonic(), 0, 0
        while n < 150_000_000:
            m.run(1_000_000); n += 1_000_000
            ms = m.rd(ma)[0] & 0x1F
            if ms == 3:
                break
        t2 = time.monotonic()
        name = "fast " if fast else "ucsim"
        say(f"speed {name}: ACTIVE={ms == 3} after {m.instr} instr (Machine.instr), {m.ticks} ticks, run {t2 - t1:.2f} s "
            f"(+ setup {t1 - t0:.2f} s): {m.instr / (t2 - t1) / 1e6:.2f} M instr/s, {m.ticks / (t2 - t1) / 1e6:.1f} M ticks/s")
        m.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("diff", "diffbus", "fuzz", "gates", "gpio", "speed", "timing"))
    ap.add_argument("bin", type=Path, nargs="?")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--cpu", choices=F.CPU_MODES, help="sim CPU model (default: 8052 for the ucsim lockstep modes, dw8051 for timing)")
    ap.add_argument("--fine", type=int, default=5_000_000)
    ap.add_argument("--fine-step", type=int, default=100_000)
    ap.add_argument("--coarse", type=int, default=30_000_000)
    ap.add_argument("--coarse-step", type=int, default=1_000_000)
    ap.add_argument("--irq-window", type=int, default=300)
    ap.add_argument("--seeds", type=int, default=8, help="fuzz: random code images")
    ap.add_argument("--fuzz-instr", type=int, default=20000, help="fuzz: instructions per seed")
    ap.add_argument("--fuzz-step", type=int, default=50, help="fuzz: compare every N instructions")
    a = ap.parse_args()
    cpu = a.cpu or ("dw8051" if a.what == "timing" else "8052")
    if a.what not in ("timing", "speed", "gpio") and cpu != "8052":
        ap.error(f"{a.what} compares against ucsim (classic 8052 cycle counts): --cpu 8052 only")
    if a.what != "timing" and not (a.bin and a.map):
        ap.error("BIN MAP required")
    os.environ["AWTO_SIM_CPU"] = cpu
    say(f"=== fastcore_check {a.what} {a.bin}; sim CPU model {cpu}")
    return {"diff": cmd_diff, "diffbus": cmd_diffbus, "fuzz": cmd_fuzz, "gates": cmd_gates, "gpio": cmd_gpio, "speed": cmd_speed,
            "timing": cmd_timing}[a.what](a)


if __name__ == "__main__":
    sys.exit(main())
