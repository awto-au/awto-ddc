"""Power LED gate (awto-ddc#95) shared by sysm_sim / panel_sim: P3.5 (on colour) / P3.6 (standby colour) per system state.

- LedWatch: fw_sim Dev on the P3 SFR (0xB0): every P3.5 / P3.6 level change, with sim time and phase.
- Rule (Dan 2026-11-12): on colour (1, 0) in AC ON .. NO SIGNAL / WAKE SEARCH; standby colour breathing in POWER SAVING
  (P3.5 = 0, P3.6 toggling); both off in OFF. POWER DOWN shows its target (the next state) at once, as the Dahua power switch.
- judge_lines: after every 'system: A -> B' line the 'LED: ...' lines up to the next transition leave B's colour; each LED
  line names the state it was set for. sample: pins + g_ucAwtoLedMode at a checkpoint against the current state.
"""
import re

P3 = 0xB0
ON, BREATHE, OFF = "on colour", "standby colour breathing", "off"
STATE_LED = {"AC ON": ON, "INITIAL": ON, "SEARCH": ON, "DISPLAY SETTING": ON, "ACTIVE": ON, "FAST SWITCH": ON, "HOLD L1": ON,
             "NO SUPPORT": ON, "NO SIGNAL": ON, "WAKE SEARCH": ON, "POWER SAVING": BREATHE, "OFF": OFF}
MODE_LED = {0: OFF, 1: ON, 2: BREATHE}            # RL6449_Project.h AWTO_LED_OFF / ON / BREATHE
BREATHE_MIN_EDGES = 4                             # P3.6 edges in a breathing phase: the PWM runs (one ramp step = 16 ms)


class LedWatch:
    """P3 SFR writes: (t, phase, p35, p36) on a change of either pin; P3.6 edges counted per phase"""
    reads, writes, swrites = (), (), (P3,)

    def __init__(self, run):
        self.run, self.rec, self.last, self.edges = run, [], None, {}

    def init(self, m):
        self.last = None

    def on_read(self, m, a):
        pass

    def on_write(self, m, a):
        pass

    def on_swrite(self, m, a):
        v = m.rd(P3, 1, "sfr")[0]
        pins = (v >> 5 & 1, v >> 6 & 1)
        if pins != self.last:
            if self.last is not None and pins[1] != self.last[1]:
                self.edges[self.run.phase] = self.edges.get(self.run.phase, 0) + 1
            self.rec.append((self.run.t(), self.run.phase, *pins))
            self.last = pins


def pins_colour(p35, p36, edges):
    if p35 and not p36:
        return ON
    if not p35 and (p36 or edges >= BREATHE_MIN_EDGES):
        return BREATHE if edges >= BREATHE_MIN_EDGES else "standby colour steady"
    return OFF if not p35 and not p36 else "both on"


def judge_lines(lines, check):
    """transition / LED line order (ring lines of all phases, in order)"""
    trans = [(i, m.group(1), m.group(2)) for i, x in enumerate(lines) if (m := re.search(r"system: in (.+?) for \d+ ms -> (.+?):", x))]
    leds = {i: (m.group(1), m.group(2)) for i, x in enumerate(lines) if (m := re.search(r"LED: (.+?) \((.+?)\)$", x))}
    check(bool(leds), f"LED lines logged ({len(leds)})")
    led, bad, named = None, [], []
    for i in sorted(k for k in leds if not trans or k < trans[0][0]):
        led = leds[i][0]                                               # boot: before the first transition line
    for k, (i, a, b) in enumerate(trans):
        end = trans[k + 1][0] if k + 1 < len(trans) else len(lines)
        tgt = b
        if b == "POWER DOWN":                                         # shows its target at once
            tgt = trans[k + 1][2] if k + 1 < len(trans) else None
        for j in range(i + 1, end):
            if j in leds:
                led = leds[j][0]
                if leds[j][1] != b:
                    named.append(f"{lines[j]} (after -> {b})")
        want = STATE_LED.get(tgt)
        if want is not None and led != want:
            bad.append(f"{a} -> {b}: LED {led!r}, want {want!r}")
    check(trans and not bad, f"LED colour matches the state after every transition ({len(trans)})", "; ".join(bad[:4]))
    check(not named, "every LED line names the state it was set for", "; ".join(named[:3]))
    return len(trans)


def sample(m, watch, state, phase, mode_addr, check, table):
    """pins and g_ucAwtoLedMode now vs the current system state (state name from the last transition line)"""
    v = m.rd(P3, 1, "sfr")[0]
    p35, p36 = v >> 5 & 1, v >> 6 & 1
    edges = watch.edges.get(phase, 0)
    got = pins_colour(p35, p36, edges)
    mode = MODE_LED.get(m.rd(mode_addr)[0], "?") if mode_addr is not None else None
    want = STATE_LED.get(state)
    table.append((phase, state, want, p35, p36, edges, mode))
    check(got == want and (mode is None or mode == want),
          f"LED pins in {phase} ({state}): want {want}", f"P3.5 {p35} P3.6 {p36}, {edges} P3.6 edges, g_ucAwtoLedMode {mode}")


def print_table(say, table):
    say("  LED per state (phase, state, want, P3.5, P3.6, P3.6 edges in phase, g_ucAwtoLedMode):")
    for ph, st, w, a, b, e, mo in table:
        say(f"    {ph:16s} {st:16s} {w!s:26s} {a} {b} {e:5d} {mo}")


PIN_FILES = ("fw/sdcc/awto_led.inc", "fw/sdk/Project/Header/RL6449_Project.h")     # AwtoLedSet, AWTO_LED_T2ISR
SET_FILES = ("fw/sdk/Kernel/System/Code/SysJudge.c",)
SDK_BOARDS = "fw/sdk/Pcb/"                                                        # other boards' headers: not built


def lint(tree):
    """one LED owner in the tree: [file:line] of a pin write / AwtoLedSet call / SDK LED call outside it"""
    bad = []
    files = [p for p in (tree / "fw/sdk").rglob("*") if p.suffix in (".c", ".h")] + list((tree / "fw/sdcc").glob("*.inc"))
    for p in files:
        rel = str(p.relative_to(tree))
        if rel.startswith(SDK_BOARDS) and "AWTO" not in p.name:
            continue
        for n, ln in enumerate(p.read_text(errors="replace").splitlines(), 1):
            code = ln.split("//")[0]
            if re.search(r"\b(P3_5|P3_6|bLED_ON|bLED_STANDBY)\s*=[^=]", code) and rel not in PIN_FILES:
                bad.append(f"{rel}:{n}")
            if re.search(r"\bAwtoLedSet\s*\(", code) and not re.search(r"\b(extern|void)\b", code) and rel not in SET_FILES:
                bad.append(f"{rel}:{n}")
            if re.search(r"\bUserInterfaceKeyPadLedControl\s*\(|\bPCB_LED_(?!AC_ON_INITIAL)\w+\s*\(\s*\)\s*;", code) and "Pcb_Default" not in rel \
                    and "ScalerSync.c" not in rel:                                 # DDR burn-in test: compiled out
                bad.append(f"{rel}:{n}")
    return bad
