#!/usr/bin/env python3
"""Unit 2 speaker test (awto-ddc#94, docs/audio.md): host HDMI audio to the monitor, tones, live audio register readback.

usage: audio_test.py host                       ELD + IEC958 switch of the Intel HDMI pcm that carries unit 2 (EDID name)
       audio_test.py regs --map MAP             one decoded line per audio register / SDK state (debug slave 0x35, MCU runs)
       audio_test.py tones --map MAP [--secs 3] host unmute, then left / right / both sine (3 s each), regs read during 'both'
       audio_test.py poke --map MAP ADDR=VAL..  XDATA write over the debug slave (cmd 0x3B, MCU runs), read back
- Plays straight to ALSA plughw:<card>,<dev> of the HDMI pcm whose ELD names our monitor: never the PipeWire default sink
  (the Intel card's PipeWire profile is analog only; that HDMI pcm is free).
- Caller holds unit_lock (AWT26110002). Units 1 / 3 hands off: bus and serial are fixed to unit 2.
Log: ./tmp/logs/audio_test.log (every step, ISO time).
"""
from __future__ import annotations

import argparse, gzip, math, os, re, struct, subprocess, sys, time, wave
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "tmp/logs/audio_test.log"
OUT = ROOT / "tmp/audio"
BUS, SERIAL = 11, "AWT26110002"                 # unit 2, Intel HDMI-A-2 (scripts/devices.json)
MON_NAME = "awto-mon"                           # EDID product name in the ELD
RATE = 48000                                    # Hz; LPCM in our SAD (32 / 44.1 / 48 kHz)
TONES = (("left", 440, (1, 0)), ("right", 660, (0, 1)), ("both", 880, (1, 1)))
AMP = 0.5                                       # -6 dBFS: loud through the 100 % DVC gain, no clipping
APLAY_LIMIT_S = 1.25                            # x tone length: aplay runs the tone + ~0.2 s open/drain
REGDB = ROOT / "re/regdb/RTD2795T-CG.tsv.gz"
REGS = (0x06C0, 0x06C1, 0x06C5, 0x06C6, 0x06C7, 0x06C8, 0x06D0, 0x06D1, 0x06D2, 0x06D3, 0x06D4, 0x06E0,
        0x08A0, 0x08A1, 0x08A2, 0x08A5, 0x08A6, 0x08A7, 0x6F00, 0x6F01)
PORTS = {"P7.3 (amp aux, pin 160)": 0xFE1B, "P7.4 (amp enable, pin 161)": 0xFE1C, "P4.5 (jack input, pin 113)": 0xFE05}
AUDIO_STATE = ("POWER_OFF", "PREPARING", "PLAYBACK", "?")         # Global.h EnumAudioState
DAC_STATE = ("OFF", "INITIAL", "CHARGE", "DEPOP", "READY", "?", "?", "?")   # EnumAudioDACState
FREQ = {0: "none", 1: "32k", 2: "44.1k", 3: "48k", 4: "64k", 5: "88.2k", 6: "96k", 7: "128k", 8: "176.4k", 9: "192k"}


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def reg_names() -> dict[int, str]:
    names = {}
    with gzip.open(REGDB, "rt") as f:
        for ln in f:
            c = ln.rstrip("\n").split("\t")
            if len(c) > 5 and c[4] == "REG" and c[1].startswith("0x"):
                names.setdefault(int(c[1], 16), c[5])
    return names


def xsym(mp: Path, name: str) -> int:
    m = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", mp.read_text(errors="replace"))
    if not m:
        raise SystemExit(f"{name} not in {mp}")
    return int(m.group(1), 16) & 0xFFFF


# ---- host side ----
def hdmi_pcm() -> tuple[str, int, int]:
    """(card id, card number, device) of the HDMI pcm whose ELD carries MON_NAME on the Intel card."""
    for eld in sorted(Path("/proc/asound").glob("card*/eld#*")):
        t = eld.read_text(errors="replace")
        if "monitor_present\t\t1" in t and MON_NAME in t:
            card = int(eld.parent.name[4:])
            cid = (eld.parent / "id").read_text().strip()
            if cid != "PCH":
                continue                         # NVIDIA card = units 1 / 3
            codec, nid = eld.name[4:].split(".")
            for pcm in sorted(eld.parent.glob("pcm*p")):
                info = (pcm / "info").read_text(errors="replace") if (pcm / "info").exists() else ""
                if MON_NAME in info:
                    return cid, card, int(pcm.name[3:-1])
            out = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
            m = re.search(rf"card {card}: \S+ \[[^]]*\], device (\d+): HDMI \d+ \[{MON_NAME}\]", out)
            if m:
                return cid, card, int(m.group(1))
    raise SystemExit(f"no Intel HDMI ELD names {MON_NAME}: host sees no audio sink on unit 2 (EDID / hotplug)")


def host(unmute: bool) -> str:
    cid, card, dev = hdmi_pcm()
    say(f"host: unit 2 audio = ALSA card {card} ({cid}) device {dev} (ELD names {MON_NAME})")
    eld = [e for e in Path(f"/proc/asound/card{card}").glob("eld#*") if MON_NAME in e.read_text(errors="replace")]
    for e in eld:
        for ln in e.read_text().splitlines():
            if ln.split("\t")[0] in ("monitor_name", "connection_type", "sad_count", "sad0_coding_type", "sad0_channels",
                                     "sad0_rates", "sad0_bits", "speakers"):
                say(f"host: ELD {e.name} {' '.join(ln.split())}")
    # IEC958 Playback Switch index n belongs to the n-th HDMI pcm of the card (HDMI 0 -> index 0)
    hdmi_n = [int(m.group(2)) for m in re.finditer(rf"card {card}: \S+ \[[^]]*\], device (\d+): HDMI (\d+)",
                                                   subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout)
              if int(m.group(1)) == dev][0]
    ctl = f"IEC958 Playback Switch',index={hdmi_n}"
    cur = subprocess.run(["amixer", "-c", cid, "cget", f"iface=MIXER,name='{ctl}"], capture_output=True, text=True).stdout
    state = "on" if "values=on" in cur else "off"
    say(f"host: IEC958 Playback Switch index {hdmi_n} (HDMI {hdmi_n} = device {dev}) is {state}")
    if unmute and state != "on":
        r = subprocess.run(["amixer", "-c", cid, "cset", f"iface=MIXER,name='{ctl}", "on"], capture_output=True, text=True)
        say(f"host: IEC958 index {hdmi_n} -> on: rc {r.returncode}")
    elif unmute:
        say(f"host: IEC958 index {hdmi_n} already on")
    return f"plughw:CARD={cid},DEV={dev}"


def tone_wav(name: str, hz: int, chans: tuple[int, int], secs: float) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"tone-{name}-{hz}.wav"
    n = int(RATE * secs)
    fade = RATE // 100                           # 10 ms ramp: no click at start / end
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        buf = bytearray()
        for i in range(n):
            g = min(1.0, i / fade, (n - 1 - i) / fade)
            v = int(32767 * AMP * g * math.sin(2 * math.pi * hz * i / RATE))
            buf += struct.pack("<hh", v * chans[0], v * chans[1])
        w.writeframes(bytes(buf))
    return p


# ---- monitor side (debug slave 0x35) ----
class Unit:
    def __init__(self, mp: Path):
        import dbg_xdata as X
        import rtd_i2c_bridge as B
        self.X, self.B, self.mp = X, B, mp
        self.sym = {n: xsym(mp, n) for n in ("g_stAudioInfo", "g_stAudioDACInfo", "g_stAudioD2DigtalInfo",
                                              "g_stPowerInfo", "g_stModeInfo")}
        for n in ("g_ulAwtoAudioT0", "g_ucAwtoAudioAux"):
            try:
                self.sym[n] = xsym(mp, n)
            except SystemExit:
                pass
        self.names = reg_names()

    def session(self, fn):
        import dbg_link
        with dbg_link.linked(BUS, 2):
            rio = self.B.Real(BUS, allow_write=True)
            try:
                return fn(rio)
            finally:
                rio.close()

    def rd(self, rio, a: int, n: int = 1):
        return self.X.read_bytes(rio, a, n)

    def wr(self, rio, a: int, v: int) -> bool:
        X = self.X                              # debug slave: stage hi (0x01), value (0x03), write at lo (0x3B)
        return bool(rio.write(X.DEV8, 0x01, bytes([a >> 8])) and rio.write(X.DEV8, 0x03, bytes([v])) and
                    rio.write(X.DEV8, 0x3B, bytes([a & 0xFF])))

    def regs(self, rio, why: str) -> dict:
        say(f"regs ({why}):")
        got = {}
        for a in REGS:
            v = self.rd(rio, a)
            got[a] = None if v is None else v[0]
            say(f"  {a:04X} {self.names.get(a, '?'):<20} = " + ("read failed" if v is None else f"0x{v[0]:02X}"))
        for n, a in PORTS.items():
            v = self.rd(rio, a)
            got[a] = None if v is None else v[0]
            say(f"  {a:04X} {n:<28} = " + ("read failed" if v is None else f"{v[0] & 1}"))
        if got.get(0x06C0) is not None:
            v = got[0x06C0]
            say(f"  DAC power: aout (bit 5) {'on' if v & 0x20 else 'off'}, hpout (bit 4) {'on' if v & 0x10 else 'off'}")
        if got.get(0x08A5) is not None and got.get(0x08A6) is not None:
            g = (got[0x08A5] << 8 | got[0x08A6]) & 0x3FFF
            db = 20 * math.log10(g / 0x3FFF) if g else float("-inf")
            say(f"  DVC gain set 0x{g:04X} = {db:.1f} dB (0x3FFF = 0 dB, 0 = silent)")
        for n in ("g_stAudioInfo", "g_stAudioDACInfo", "g_stAudioD2DigtalInfo", "g_stPowerInfo", "g_stModeInfo"):
            v = self.rd(rio, self.sym[n])
            got[n] = None if v is None else v[0]
        if got["g_stAudioInfo"] is not None:
            say(f"  SDK audio state {AUDIO_STATE[(got['g_stAudioInfo'] >> 4) & 3]}")
        if got["g_stAudioDACInfo"] is not None:
            say(f"  SDK DAC state {DAC_STATE[got['g_stAudioDACInfo'] & 7]}")
        if got["g_stAudioD2DigtalInfo"] is not None:
            d = got["g_stAudioD2DigtalInfo"]
            say(f"  D2 HDMI audio: detected {d >> 4 & 1}, sampling {FREQ.get(d & 0xF, d & 0xF)}")
        if got["g_stModeInfo"] is not None:
            say(f"  power {got['g_stPowerInfo'] >> 4 if got['g_stPowerInfo'] is not None else '?'} (2 = NORMAL), "
                f"mode {got['g_stModeInfo'] & 0x1F} (3 = ACTIVE)")
        if "g_ucAwtoAudioAux" in self.sym:
            v = self.rd(rio, self.sym["g_ucAwtoAudioAux"])
            say(f"  awto amp owner: P7.3 driven low = {None if v is None else v[0]}")
        return got


def tones(a, u: Unit) -> int:
    dev = host(True)
    files = [(nm, hz, tone_wav(nm, hz, ch, a.secs)) for nm, hz, ch in TONES]
    u.session(lambda rio: u.regs(rio, "before tones"))
    for nm, hz, p in files:
        t0 = time.strftime("%H:%M:%S")
        say(f"TONE {nm.upper()} {hz} Hz START {t0} ({a.secs:.0f} s) -> {dev}")
        pr = subprocess.Popen(["aplay", "-q", "-D", dev, str(p)], stderr=subprocess.PIPE, text=True)
        if nm == "both":
            time.sleep(min(1.0, a.secs / 3))   # stream running and DVC unmuted before the readback
            u.session(lambda rio: u.regs(rio, f"during {nm} tone"))
        try:
            _, err = pr.communicate(timeout=a.secs * APLAY_LIMIT_S + 2)
        except subprocess.TimeoutExpired:
            pr.kill()
            say(f"TONE {nm}: aplay still running after {a.secs * APLAY_LIMIT_S + 2:.1f} s: killed")
            return 1
        say(f"TONE {nm.upper()} {hz} Hz END {time.strftime('%H:%M:%S')} rc {pr.returncode} {err.strip()[:160]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("host", "regs", "tones", "poke"))
    ap.add_argument("--map", type=Path)
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("pokes", nargs="*")
    a = ap.parse_args()
    say(f"audio_test {a.cmd} {' '.join(a.pokes)} (map {a.map})")
    if a.cmd == "host":
        host(False)
        return 0
    if not a.map:
        raise SystemExit("--map required")
    u = Unit(a.map)
    if a.cmd == "regs":
        u.session(lambda rio: u.regs(rio, "now"))
        return 0
    if a.cmd == "poke":
        def go(rio):
            for pk in a.pokes:
                ad, v = (int(x, 16) for x in pk.split("="))
                b = u.rd(rio, ad)
                ok = u.wr(rio, ad, v)
                r = u.rd(rio, ad)
                say(f"poke {ad:04X} {u.names.get(ad, '')}: {b.hex() if b else '?'} -> {v:02X} (write {'ok' if ok else 'NAK'}), "
                    f"read back {r.hex() if r else '?'}")
        u.session(go)
        return 0
    return tones(a, u)


if __name__ == "__main__":
    sys.exit(main())
