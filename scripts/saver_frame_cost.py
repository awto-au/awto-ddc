#!/usr/bin/env python3
"""Cost of one saver frame by stage, in the firmware sim (docs/saver-fps-budget.md).

usage: saver_frame_cost.py BIN [--case scope|scope2|asteroids|pacman ...] [--window S] [--rotate] [--every N] [--top K] [--count FN ...]
  Starts the saver by DDC/CI VCP 0xEB (as saver_loop_cost.py), lets the first (hidden) frame finish, then over --window
  fw seconds:
  - frames: Scope 2 g_usAwtoS2Frame, Asteroids g_ucAwtoAstCol wraps, Scope 1 ScPass calls / 64, Pac-Man sub-steps
  - CPU clk per function: the PC every --every instr, weighted by the clk since the last sample (fetch stalls, MOVX
    included); grouped into stages (STAGES); samples split by main-loop slot: inside AwtoSaverPoll = saver, else main loop
  - OSD port traffic: data-port bytes per address-set burst; burst of 3 B = map word, longer = glyph
  Per frame: fw ms, instr, saver ms vs main-loop ms, port bytes (glyph / map), address sets; stage table (ms and %).
Log: ./tmp/logs/saver_frame_cost.log
"""
import argparse
import bisect
import collections
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402

LOG = R.ROOT / "tmp/logs/saver_frame_cost.log"
VCP_SAVER = 0xEB
VCP = {"scope": 3, "scope2": 4, "asteroids": 8, "pacman": 2}
SETTLE_S = {"scope": 2.5, "scope2": 2.5, "asteroids": 8.0, "pacman": 2.5}   # first frame hidden (asteroids_speed SETTLE_S 8)
ROW_DISP_ROTATE = 32
ROTATE_SETTLE_S = 6.0                                     # as scope2_sim.py
SC1_PASSES_PER_FRAME = 64                                 # Scope 1: 32 columns x 2 bands (scope_saver.c)
ADR_LSB, DATA = 0x91, 0x92                                # osd_model taps
MAP_BURST = 3                                             # one char command
# stage = first matching pattern (function names from the map; `__bs_*` = banked-call trampoline)
STAGES = [
    ("bank trampoline", r"^_bs_|^d_isr_bs"),
    ("OSD port (SDK call + store)", r"^ScalerOsd(DataPort|AddrSet|AddrMsb|AddrLsb)$|^ScalerSetByte$|^ScalerSetBit$|^ScalerGetByte$"),
    ("upload (glyph / map / rot)", r"^AwtoOsd(Glyph|Tile|Word|RevByte|RotCell|Turn|Map1)$|^S2(Glyph|MapWord)$|^Pc(Step|CellSet|Glyph|Cell)$"),
    ("draw (lines / runs / text / clear)", r"^osd_|^cursor_|^S2(Run|Trace|Char|Text|Base|BaseCopy)$|^Ast(Shape|TileInk|Draw\w*|Digits)$|^ScPass$|^ScY$"),
    ("compiler helpers (mul / div / gptr)", r"^_(mul|div|mod|gptr|sdcc|mcs51|memcpy|memset)"),
    ("time (AwtoMs)", r"^AwtoMs$"),
    ("saver frame logic", r"^S2|^Ast|^Pc|^AwtoScopeSaver|^AwtoAsteroids|^AwtoPacman|^AwtoSaver|^Saver"),
    ("ISR", r"_EXINT|_TIMER|Isr|_isr|IntProc"),
]


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def wherer(m):
    """bank, pc -> function name, the banked-call trampoline (__bs_*) included (fw_sim.parse_map leaves it out)."""
    funcs = sorted((v, k) for k, v in m.sym.items() if k.startswith("_"))
    keys = [v for v, _ in funcs]
    cend = m.where.cend
    return lambda bank, pc: next((k[1:] for v, k in reversed(funcs[:bisect.bisect_right(keys, pc if pc < cend or bank == 0 else bank * 0x10000 + pc)])), "?")


def stage(fn: str) -> str:
    for name, rx in STAGES:
        if re.search(rx, fn):
            return name
    return "SDK / main loop other"


def measure(a, case: str) -> None:
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    m, bus = sess.bus.m, sess.bus
    ddc = D.Mccs(bus, eng)
    ddc.set(0xE0, ROW_DISP_ROTATE)
    ddc.set(0xE1, 1 if a.rotate else 0)
    bus.wait(ROTATE_SETTLE_S)
    ddc.set(VCP_SAVER, VCP[case])
    bus.wait(SETTLE_S[case])
    where = wherer(m)
    on, in_saver = [False], [False]
    port = {"bytes": 0, "sets": 0, "glyph_b": 0, "map_b": 0, "glyphs": 0, "maps": 0, "cur": 0}

    def close_burst():
        n = port["cur"]
        if n:
            k = "map" if n == MAP_BURST else "glyph"
            port[k + "_b"] += n
            port[k + "s"] += 1
        port["cur"] = 0
    orig = sess.model.on_write

    def tap(mm, adr):
        if on[0]:
            if adr == ADR_LSB:
                close_burst()
                port["sets"] += 1
            elif adr == DATA:
                port["bytes"] += 1
                port["cur"] += 1
        orig(mm, adr)
    sess.model.on_write = tap
    m.stub("AwtoSaverPoll", lambda mm, r: in_saver.__setitem__(0, True) and None)
    m.stub("SysMachineHandler", lambda mm, r: in_saver.__setitem__(0, False) and None)
    calls = collections.Counter()
    for fn in ("ScPass", "AwtoPacmanClassic", "AwtoStackCheck", *a.count):
        if "_" + fn in m.sym:
            m.stub(fn, lambda mm, r, fn=fn: on[0] and calls.update([fn]) and None)
    rd16 = lambda n: int.from_bytes(m.rd(m.addr(n), 2), "big")
    rd8 = lambda n: m.rd(m.addr(n), 1)[0]
    frames = 0
    last = rd16("g_usAwtoS2Frame") if case == "scope2" else rd8("g_ucAwtoAstCol") if case == "asteroids" else 0
    clk, stall = collections.Counter(), collections.Counter()
    saver_clk = [0, 0]                                    # in AwtoSaverPoll slot, outside
    i0, k0, w0, s0 = m.p.instr, m.p.clk, m.wall_ms, m.p.fm_stall
    on[0] = True
    t_end = bus.now() + a.window
    kp, sp = m.p.clk, m.p.fm_stall
    while bus.now() < t_end:
        m.run(a.every)
        k = m.p.clk
        fn = where(m.p.bank, m.p.pc)
        clk[(fn, in_saver[0])] += k - kp
        stall[(fn, in_saver[0])] += m.p.fm_stall - sp
        sp = m.p.fm_stall
        saver_clk[0 if in_saver[0] else 1] += k - kp
        kp = k
        if case == "scope2":
            v = rd16("g_usAwtoS2Frame")
            frames += (v - last) & 0xFFFF
            last = v
        elif case == "asteroids":
            v = rd8("g_ucAwtoAstCol")
            frames += v == 0 and last != 0
            last = v
    on[0] = False
    close_burst()
    if case == "scope":
        frames = calls["ScPass"] / SC1_PASSES_PER_FRAME
    elif case == "pacman":
        frames = calls["AwtoPacmanClassic"]
    instr, kclk, wall = m.p.instr - i0, m.p.clk - k0, m.wall_ms - w0
    f = max(frames, 1e-9)
    ms_clk = wall / max(kclk, 1)
    passes = calls["AwtoStackCheck"]
    say(f"{a.bin.name} {case}{' rot180' if a.rotate else ''}: window {a.window:.1f} s fw, f_cpu {m.clock.f_cpu / 1e6:.1f} MHz, PC every {a.every} instr; "
        f"{frames:.1f} {'sub-steps' if case == 'pacman' else 'frames'} -> {frames / (wall / 1000):.2f} /s, {wall / f:.1f} ms each; "
        f"{instr / f:.0f} instr, {kclk / 4 / f:.0f} cycles ({instr / wall:.0f} instr/ms), {passes / f:.1f} passes each")
    say(f"    per frame: saver slot {saver_clk[0] * ms_clk / f:.1f} ms, rest of the main loop {saver_clk[1] * ms_clk / f:.1f} ms "
        f"({saver_clk[1] * ms_clk / max(passes, 1):.2f} ms per pass); port {port['bytes'] / f:.0f} B "
        f"(glyph {port['glyph_b'] / f:.0f} B in {port['glyphs'] / f:.1f} uploads, map {port['map_b'] / f:.0f} B = {port['maps'] / f:.1f} words), "
        f"{port['sets'] / f:.0f} address sets; flash fetch stall {(m.p.fm_stall - s0) * ms_clk / f:.2f} ms")
    if a.count:
        say("    calls per frame: " + ", ".join(f"{fn} {calls[fn] / f:.0f}" for fn in a.count))
    tot = sum(clk.values())
    for slot, nm in ((True, "saver slot"), (False, "main loop")):
        st, sst = collections.Counter(), collections.Counter()
        for (fn, s_), c in clk.items():
            if s_ == slot:
                st[stage(fn)] += c
                sst[stage(fn)] += stall[(fn, s_)]
        for s, c in st.most_common():
            say(f"    {nm}: {100 * c / tot:5.1f} %  {c * ms_clk / f:7.2f} ms/frame (fetch stall {sst[s] * ms_clk / f:6.2f})  {s}")
    for (fn, s_), c in clk.most_common(a.top):
        say(f"      fn {100 * c / tot:5.1f} %  {c * ms_clk / f:7.2f} ms/frame (stall {stall[(fn, s_)] * ms_clk / f:6.2f})  {'saver' if s_ else 'main '}  {fn}  [{stage(fn)}]")
    bus.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--case", nargs="*", default=["scope", "scope2", "asteroids", "pacman"])
    ap.add_argument("--window", type=float, default=10.0, help="fw seconds measured")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--every", type=int, default=200, help="instructions between PC samples")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--count", nargs="*", default=[], help="functions whose calls per frame are counted (entry hooks)")
    a = ap.parse_args()
    for c in a.case:
        measure(a, c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
