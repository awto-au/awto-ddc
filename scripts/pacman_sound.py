#!/usr/bin/env python3
"""Pac-Man sound sequencer: note tables -> firmware data (fw/audio/snd_data.inc) + WAV preview. Docs: docs/pacman-sound.md

usage: pacman_sound.py [--k-hz HZ] [--inc PATH] [--wav-dir DIR] [--wave square|sine] [--no-inc] [--no-wav]
  - Tracks: intro jingle, waka (loops), death glissando, alert, ghost-eat sweep, fruit, siren x 3 speeds (loop), frightened (loop).
  - Chip tone = HDMI audio test generator (AFCR audio_test_enable); pitch = audio PLL S code (SCAPR sc, 7 bit): f = K / sc,
    octave flag = AFCR tst_i2s_sw = 0 (f / 2). K = --k-hz, default AWTO_PS_K_DEFAULT_HZ (derived, calibrate with test cmd 0xBD).
  - Firmware data: byte pairs {sc | AWTO_PS_OCT_FLAG, duration in AWTO_PS_TICK_MS ticks}; sc 0 = rest; duration 0 = end of track.
Log: ./tmp/logs/pacman_sound.log
"""
import argparse
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PS_K_DEFAULT_HZ = 48000.0       # sc 32 = 48 kHz sample rate (SDK S code 0xA0), 32 samples per sine period: derived, not measured
PS_SC_MIN = 24                  # sample rate <= 64 kHz: the DAC clock divider (06D4 bits 7:6) stays at its 48 kHz setting
PS_SC_MAX = 127                 # 7 bit field
PS_OCT_FLAG = 0x80
PS_TICK_MS = 10                 # duration unit; AwtoMs() is 1 ms, the main loop pass is the real resolution
PS_DUR_MAX = 255
PS_GAP_TICKS = 1                # rest between two notes of a melody (re-articulation)
PS_WAV_RATE = 22050
PS_WAV_LEVEL = 0.3              # of full scale

NOTE_BASE = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
A4_HZ = 440.0

# Pac-Man start jingle (arcade, B major / C major phrases); (note, 16ths). 16th = 80 ms.
SIXTEENTH_MS = 80
INTRO = [
    ("B4", 1), ("B5", 1), ("F#5", 1), ("D#5", 1), ("B5", 1), ("F#5", 2), ("D#5", 3),
    ("C5", 1), ("C6", 1), ("G5", 1), ("E5", 1), ("C6", 1), ("G5", 2), ("E5", 3),
    ("B4", 1), ("B5", 1), ("F#5", 1), ("D#5", 1), ("B5", 1), ("F#5", 2), ("D#5", 3),
    ("D#5", 1), ("E5", 1), ("F5", 1), ("F5", 1), ("F#5", 1), ("G5", 1), ("G5", 1), ("G#5", 1), ("A5", 1), ("B5", 4),
]
# Waka-waka: two sweeps, one per mouth movement, alternating; loops while eating. (Hz, ms) steps
WAKA = [(f, 28) for f in (392, 523, 659, 784)] + [(f, 28) for f in (784, 659, 523, 392)]
# Death: falling glissando, three sweeps, each lower and slower, then two low pops. (Hz, ms) steps
DEATH = ([(1000 - 30 * i, 20) for i in range(18)]
         + [(780 - 22 * i, 26) for i in range(16)]
         + [(560 - 16 * i, 34) for i in range(14)]
         + [(0, 60), (420, 50), (0, 50), (380, 80)])

# Alert (flash warning / "I need you"): rising bip - bip - long beep, 1000 ms. (Hz, ms) steps
ALERT = [(880, 150), (0, 50), (1175, 150), (0, 50), (1568, 600)]

# Ghost eaten: rising sweep 300 -> 1800 Hz, 18 ms per step. Fruit eaten: falling sweep then a rising blip. (Hz, ms) steps
GHOST = [(round(300 * 6 ** (i / 15)), 18) for i in range(16)]
FRUIT = [(round(1600 - 90 * i), 16) for i in range(12)] + [(0, 20), (660, 40), (880, 40), (1320, 60)]
# Siren: two-tone wail, up 520 -> 780 Hz then down, 8 steps each way; step ms per speed (faster as pellets run out).
SIREN_LO_HZ, SIREN_HI_HZ, SIREN_STEPS = 520, 780, 8
SIREN_STEP_MS = (40, 30, 20)
# Frightened (power pellet): fast rising saw 400 -> 1000 Hz, 6 steps of 20 ms, repeated.
FRIGHT = [(400 + 120 * i, 20) for i in range(6)]

# Asteroids screensaver (docs/asteroids.md): fire = falling zap; explosions = falling, jittering tones (alternate x0.8 / x1.3 per step, floor 200 Hz:
# the octave flag reaches 189 Hz); thrust and saucer = low loops (background states 5 / 6 of AwtoPmSoundBg).
def boom(n: int, ms: int, f0: int, f1: int):
    return [(max(200, round((f0 + (f1 - f0) * i / (n - 1)) * (1.3 if i % 2 else 0.8))), ms) for i in range(n)]


AST_FIRE = [(1900 - 150 * i, 8) for i in range(8)]
AST_BOOM_S = boom(6, 18, 600, 260)
AST_BOOM_M = boom(10, 20, 640, 220)
AST_BOOM_L = boom(14, 22, 700, 200)
AST_BOOM_SHIP = boom(28, 25, 800, 200)
AST_THRUST = [(200, 30), (260, 30), (220, 30), (280, 30)]
AST_SAUCER = [(660, 60), (880, 60)]


def siren(step_ms: int):
    up = [(round(SIREN_LO_HZ + (SIREN_HI_HZ - SIREN_LO_HZ) * i / (SIREN_STEPS - 1)), step_ms) for i in range(SIREN_STEPS)]
    return up + up[::-1]


# (track, loops). One tone generator: a new sound plays only when its priority >= the playing one's; a looping low
# priority sound is resumed by the player when the higher one ends. intro / alert / calibration are above everything.
TRACKS = [("intro", False), ("waka", True), ("death", False), ("alert", False), ("ghost", False), ("fruit", False),
          ("siren1", True), ("siren2", True), ("siren3", True), ("fright", True),
          ("thrust", True), ("saucer", True), ("fire", False), ("boom_s", False), ("boom_m", False), ("boom_l", False), ("boom_ship", False)]
PRIORITY = {"intro": 7, "alert": 7, "ghost": 6, "death": 5, "fruit": 4, "waka": 3, "fright": 2, "siren1": 1, "siren2": 1, "siren3": 1,
            "boom_ship": 6, "boom_l": 5, "boom_m": 4, "boom_s": 4, "fire": 3, "thrust": 2, "saucer": 1}


TRK_BYTES = 4
# Per cmd of AwtoPmSound: (track, sync event, 1 = event value is the cmd). No track = the player handles it (calibration, stop, waka off).
CMDS = ([("intro", "AWTO_PS_EV_START", 0), ("waka", "AWTO_PS_EV_START + 1", 0), ("death", "AWTO_PS_EV_START + 2", 0), (None, 0, 0), (None, 0, 0),
         ("alert", "AWTO_PS_EV_ALERT", 0), ("ghost", "AWTO_PS_EV_GHOST", 0), ("fruit", "AWTO_PS_EV_FRUIT", 0), (None, 0, 0)]
        + [(t, "AWTO_PS_EV_AST", 1) for t in ("fire", "boom_s", "boom_m", "boom_l", "boom_ship")])


def note_hz(name: str) -> float:
    n, rest = name[0], name[1:]
    sharp = rest.startswith("#")
    octave = int(rest[1:] if sharp else rest)
    semis = NOTE_BASE[n] + (1 if sharp else 0) + 12 * (octave - 4)
    return A4_HZ * 2 ** (semis / 12)


def to_sc(hz: float, k_hz: float):
    """(sc, oct) for the generator tone nearest hz (finest step first), or None when out of range."""
    if hz <= 0:
        return 0, 0
    for oct_ in (0, 1):
        sc = round((k_hz / (2 if oct_ else 1)) / hz)
        if PS_SC_MIN <= sc <= PS_SC_MAX:
            return sc, oct_
    raise ValueError(f"{hz:.1f} Hz out of range for K = {k_hz}")


def chip_hz(sc: int, oct_: int, k_hz: float) -> float:
    return 0.0 if sc == 0 else k_hz / (2 if oct_ else 1) / sc


def steps(track: str):
    """[(Hz, ms)] for a track; melody notes get a PS_GAP_TICKS rest after them."""
    if track == "intro":
        out = []
        for name, n16 in INTRO:
            ms = n16 * SIXTEENTH_MS
            out += [(note_hz(name), ms - PS_GAP_TICKS * PS_TICK_MS), (0, PS_GAP_TICKS * PS_TICK_MS)]
        return out
    if track.startswith("siren"):
        return siren(SIREN_STEP_MS[int(track[5:]) - 1])
    return {"waka": WAKA, "death": DEATH, "alert": ALERT, "ghost": GHOST, "fruit": FRUIT, "fright": FRIGHT, "thrust": AST_THRUST,
            "saucer": AST_SAUCER, "fire": AST_FIRE, "boom_s": AST_BOOM_S, "boom_m": AST_BOOM_M, "boom_l": AST_BOOM_L, "boom_ship": AST_BOOM_SHIP}[track]


def encode(track: str, k_hz: float):
    """-> (bytes, [(hz_wanted, hz_chip, ms)]); long steps split into PS_DUR_MAX ticks."""
    data = bytearray()
    plan = []
    for hz, ms in steps(track):
        sc, oct_ = to_sc(hz, k_hz)
        ticks = max(1, round(ms / PS_TICK_MS))
        plan.append((hz, chip_hz(sc, oct_, k_hz), ticks * PS_TICK_MS))
        while ticks > 0:
            t = min(ticks, PS_DUR_MAX)
            data += bytes([sc | (PS_OCT_FLAG if oct_ else 0), t])
            ticks -= t
    data += bytes([0, 0])
    return bytes(data), plan


def decode(data: bytes, k_hz: float):
    """Firmware bytes -> [(chip Hz, ms)]; what the unit plays."""
    out = []
    for i in range(0, len(data) - 2, 2):
        sc, t = data[i] & ~PS_OCT_FLAG & 0xFF, data[i + 1]
        out.append((chip_hz(sc, 1 if data[i] & PS_OCT_FLAG else 0, k_hz), t * PS_TICK_MS))
    return out


def render(notes, wave_kind: str = "square"):
    """[(Hz, ms)] -> 16 bit mono samples (bytes)."""
    buf = bytearray()
    phase = 0.0
    for hz, ms in notes:
        n = int(PS_WAV_RATE * ms / 1000)
        for _ in range(n):
            if hz <= 0:
                v = 0.0
            else:
                phase = (phase + hz / PS_WAV_RATE) % 1.0
                v = math.sin(2 * math.pi * phase) if wave_kind == "sine" else (1.0 if phase < 0.5 else -1.0)
            buf += struct.pack("<h", int(v * PS_WAV_LEVEL * 32767))
    return bytes(buf)


def write_wav(path: Path, notes, wave_kind: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(PS_WAV_RATE)
        w.writeframes(render(notes, wave_kind))


def inc_text(k_hz: float) -> str:
    blob = bytearray()
    offs = []
    for name, _ in TRACKS:
        offs.append(len(blob))
        blob += encode(name, k_hz)[0]
    lines = [f"// Generated by scripts/pacman_sound.py (K = {k_hz:g} Hz): do not edit. Pairs {{sc | AWTO_PS_OCT_FLAG, ticks}}, 0 ticks = end.",
             f"#define AWTO_PS_K_HZ {k_hz:g}"]
    for (name, loop), off in zip(TRACKS, offs):
        lines.append(f"#define AWTO_PS_OFF_{name.upper()} {off}")
        lines.append(f"#define AWTO_PS_LOOP_{name.upper()} {1 if loop else 0}")
    lines.append(f"#define AWTO_PS_BYTES {len(blob)}")
    lines.append("#pragma place group(audio_11)                      // data, tables and their reader (PsByte) share the bank")
    per_line = 20
    wrapped = [", ".join(f"0x{b:02X}" for b in blob[i:i + per_line]) + "," for i in range(0, len(blob), per_line)]
    lines.append(f"#define AWTO_PS_TRK {len(blob)}                       // track table after the note data: {{offset lo, offset hi, priority, loops}} per track")
    lines.append(f"#define AWTO_PS_CMD {len(blob) + TRK_BYTES * len(TRACKS)}                       // cmd table after it: {{track, sync event, 1 = event value is the cmd}} per cmd")
    lines.append(f"#define AWTO_PS_TRACKS {len(TRACKS)}")
    lines.append(f"#define AWTO_PS_CMDS {len(CMDS)}")
    lines.append("static const __code BYTE g_aucPsData[AWTO_PS_BYTES + AWTO_PS_TRACKS * 4 + AWTO_PS_CMDS * 3] = {")
    lines += ["    " + w for w in wrapped]
    for (name, loop), off in zip(TRACKS, offs):
        lines.append(f"    0x{off & 0xFF:02X}, 0x{off >> 8:02X}, {PRIORITY[name]}, {1 if loop else 0},   // {name}")
    names = [n for n, _ in TRACKS]
    for i, (tr, ev, arg) in enumerate(CMDS):
        lines.append(f"    {names.index(tr) if tr else 'AWTO_PS_TRACK_NONE'}, {ev}, {arg},   // cmd {i}" + ("" if tr else " (handled by the player)"))
    lines.append("};")
    return "\n".join(lines) + "\n"


from _log import Logger
from _repo import repo_root


def main():
    root = repo_root()
    ap = argparse.ArgumentParser()
    ap.add_argument("--k-hz", type=float, default=PS_K_DEFAULT_HZ)
    ap.add_argument("--inc", type=Path, default=root / "fw/audio/snd_data.inc")
    ap.add_argument("--wav-dir", type=Path, default=root / "tmp/pacman_sound")
    ap.add_argument("--wave", choices=("square", "sine"), default="square", help="WAV timbre (the chip plays a sine)")
    ap.add_argument("--no-inc", action="store_true")
    ap.add_argument("--no-wav", action="store_true")
    a = ap.parse_args()
    log = root / "tmp/logs/pacman_sound.log"
    with Logger(log, stamp_echo=False) as lf:
        say = lf.say
        for name, loop in TRACKS:
            data, plan = encode(name, a.k_hz)
            worst = max((abs(1200 * math.log2(c / w)) for w, c, _ in plan if w > 0), default=0.0)
            say(f"{name}: {len(data)} B, {sum(m for _, _, m in plan)} ms{' (loops)' if loop else ''}, worst pitch error {worst:.1f} cents")
            if not a.no_wav:
                p = a.wav_dir / f"{name}.wav"
                write_wav(p, decode(data, a.k_hz), a.wave)
                say(f"  wav {p}")
        if not a.no_inc:
            a.inc.write_text(inc_text(a.k_hz))
            say(f"inc {a.inc}")


if __name__ == "__main__":
    main()
