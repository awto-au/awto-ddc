#!/usr/bin/env python3
"""Pac-Man sound sequencer: note tables -> firmware data (fw/test/pacman_sound_data.inc) + WAV preview. Docs: docs/pacman-sound.md

usage: pacman_sound.py [--k-hz HZ] [--inc PATH] [--wav-dir DIR] [--wave square|sine] [--no-inc] [--no-wav]
  - Tracks: intro jingle, waka (loops), death glissando.
  - Chip tone = HDMI audio test generator (AFCR audio_test_enable); pitch = audio PLL S code (SCAPR sc, 7 bit): f = K / sc,
    octave flag = AFCR tst_i2s_sw = 0 (f / 2). K = --k-hz, default AWTO_PS_K_DEFAULT_HZ (derived, calibrate with test cmd 0xBD).
  - Firmware data: byte pairs {sc | AWTO_PS_OCT_FLAG, duration in AWTO_PS_TICK_MS ticks}; sc 0 = rest; duration 0 = end of track.
Log: ./tmp/logs/pacman_sound.log
"""
import argparse
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402

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

TRACKS = [("intro", False), ("waka", True), ("death", False), ("alert", False)]


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
    return {"waka": WAKA, "death": DEATH, "alert": ALERT}[track]


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
    lines.append("#pragma place bank(11)                      // data and its reader (PsByte) share the bank")
    per_line = 20
    wrapped = [", ".join(f"0x{b:02X}" for b in blob[i:i + per_line]) + "," for i in range(0, len(blob), per_line)]
    lines.append("static const __code BYTE g_aucPsData[AWTO_PS_BYTES] = {")
    lines += ["    " + w for w in wrapped]
    lines.append("};")
    return "\n".join(lines) + "\n"


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path(__file__).resolve().parents[1]


def main():
    root = repo_root()
    ap = argparse.ArgumentParser()
    ap.add_argument("--k-hz", type=float, default=PS_K_DEFAULT_HZ)
    ap.add_argument("--inc", type=Path, default=root / "fw/test/pacman_sound_data.inc")
    ap.add_argument("--wav-dir", type=Path, default=root / "tmp/pacman_sound")
    ap.add_argument("--wave", choices=("square", "sine"), default="square", help="WAV timbre (the chip plays a sine)")
    ap.add_argument("--no-inc", action="store_true")
    ap.add_argument("--no-wav", action="store_true")
    a = ap.parse_args()
    log = root / "tmp/logs/pacman_sound.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as lf:
        def say(s):
            print(s)
            lf.write(f"{isostamp.now()} {s}\n")
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
