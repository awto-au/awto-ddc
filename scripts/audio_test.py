#!/usr/bin/env python3
"""Speaker test of a unit (awto-ddc#94, docs/audio.md): host HDMI / DP audio to the monitor, tones, live audio register readback.

usage: audio_test.py host                       ELD + IEC958 switch of the pcm that carries the unit (--connector, ELD name + type)
       audio_test.py regs --map MAP             one decoded line per audio register / SDK state (debug slave 0x35, MCU runs)
       audio_test.py tones --map MAP [--secs 3] host unmute, then left / right / both sine (3 s each), regs read during 'both'
       audio_test.py poke --map MAP ADDR=VAL..  XDATA write over the debug slave (cmd 0x3B, MCU runs), read back
       audio_test.py rd --map MAP ADDR[+N]..    XDATA reads (registers are XDATA-mapped)
       audio_test.py dpoke --map MAP IDX=VAL..  HDMI D2 audio data port write (71C9 index, 71CA data), read back
       audio_test.py tone --chan left|right|both [--hz N] [--secs 4]   one tone, start / end logged
       audio_test.py gen --map MAP [--secs 4] MUX..   audio-test image only: chip sine generator (VCP 0x63) for --secs per REG_MUX_ANA_OUT
                                                value (hex), 3 s off between; 06E0 restored to its value before; times logged
       audio_test.py outs --map MAP [--secs 4]  ear matrix: one both-channel 440 Hz tone per amp set-up (OUTS), 3 s gaps;
                                                hpout (amp feed) by its mute bits + P7.4 (SDK leaves those alone)
       audio_test.py steps --map MAP [--secs 3] [--only 1,3] [--freqs 200,1000,4000]   (dev.py sound-test)
                                                diagnostics console held open, then firmware ear-test steps 1..6: VCP 0x63 =
                                                0x10 + n (console "audio test n/6: ..."), per tone 0x8000 | Hz (console "audio
                                                test n: <Hz> Hz") + the tone, 0x30 + n (done line); VCP 0x62 volume checked after
       audio_test.py dport --map MAP IDX..      HDMI D2 audio data port page 71: index -> 71C9, read 71CA (restores the index)
- Plays straight to ALSA plughw:<card>,<dev>: the card of the unit's GPU (--connector, default devices.json for --serial), the pcm
  whose ELD names our monitor with the connector's type (HDMI / DP); never the PipeWire default sink (HDMI pcms are free there).
- Caller holds unit_lock for --serial. The EDID serial on --bus must match (i2cbus.require_unit) before any debug-slave access.
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
BUS, SERIAL = 11, "AWT26110003"                 # test unit (scripts/devices.json "test"), Intel HDMI-A-2; --bus / --serial
CONNECTOR = None                                # DRM connector (card1-HDMI-A-2); None = devices.json entry of SERIAL
MON_NAME = "awto-mon"                           # EDID product name in the ELD
RATE = 48000                                    # Hz; LPCM in our SAD (32 / 44.1 / 48 kHz)
TONES = (("left", 440, (1, 0)), ("right", 660, (0, 1)), ("both", 880, (1, 1)))
AMP = 0.5                                       # -6 dBFS: loud through the 100 % DVC gain, no clipping
APLAY_LIMIT_S = 1.25                            # x tone length: aplay runs the tone + ~0.2 s open/drain
REGDB = ROOT / "re/regdb/RTD2795T-CG.tsv.gz"
REGS = (0x06C0, 0x06C1, 0x06C5, 0x06C6, 0x06C7, 0x06C8, 0x06D0, 0x06D1, 0x06D2, 0x06D3, 0x06D4, 0x06E0,
        0x08A0, 0x08A1, 0x08A2, 0x08A5, 0x08A6, 0x08A7, 0x6F00, 0x6F01)
PORTS = {"P7.3 (amp aux, pin 160)": 0xFE1B, "P7.4 (amp enable, pin 161)": 0xFE1C, "P4.5 (jack input, pin 113)": 0xFE05}
DPORT_IDX, DPORT_DATA = 0x71C9, 0x71CA           # P71_C9_HDMI_AP / P71_CA_HDMI_DP (D2 HDMI audio data port)
DPORT_NAMES = {0x03: "HDMI_AFCR", 0x05: "HDMI_MAGCR1", 0x06: "HDMI_MAGCR2", 0x07: "HDMI_MAG_M_FINAL", 0x08: "HDMI_MAG_L_FINAL",
               0x09: "HDMI_MAG_R_FINAL", 0x30: "HDMI_AVMCR", 0x31: "HDMI_WDCR0"}
MUX_ANA_OUT = 0x06E0                            # REG_MUX_ANA_OUT
GEN_VCP = 0x63                                  # ear-test steps; -D _AWTO_AUDIO_TEST image: chip sine generator (fw/sdcc/awto_ddcci.inc)
VCP_VOLUME = 0x62
HZ_FLAG = 0x8000                                # VCP 0x63 value: tone frequency announce (RL6449_Project.h AWTO_AUDIO_TEST_HZ_FLAG)
MCCS_GAP_S = 0.05                               # MCCS: host waits >= 50 ms between DDC/CI messages
VCP_TRIES = 3                                   # one NAK (MCU busy in a DVC ramp, <= 400 ms) is retried after the gap
GEN_GAP_S = 3.0                                 # silence between generator runs: Dan tells them apart
REGS_READ_S = 1.0                               # one regs() pass over the debug slave (~0.6 s measured 2026-11-13)
DDC_LIMIT_S = 10                                # ddcutil setvcp ~1 s with retries; 10 s = stall


STEPS, STEP_START, STEP_DONE = 6, 0x10, 0x30     # firmware ear-test steps (RL6449_Project.h AWTO_AUDIO_TEST_*)
STEP_WHAT = ("hpout only, P7.3 low", "hpout only, P7.3 HIGH", "aout only, P7.3 low", "aout only, P7.3 HIGH",
             "hpout + aout, P7.3 low", "hpout + aout, P7.3 HIGH")          # all: amp P7.4 on, DVC -6 dB (awto_audio.inc)
STEP_SETTLE_S = 0.25                            # step set-up -> first tone: fw writes output / P7.3 / gain at once (one main-loop
                                                # pass ~3.4 ms + DVC zero-cross ramp); 0.25 s so the console line shows first
DVC_GAIN = (0x08A5, 0x08A6)                     # DVC_GAIN_MSB / LSB: double-buffered, applied by DVC_GAIN_READ_MSB bit 6
DVC_LATCH, DVC_LATCH_BIT = 0x08A7, 0x40         # (ScalerAudioDVCAdjustVolume); read back = the applied gain, 0 while muted
AOUT_CTRL, HPOUT_CTRL = 0x06C6, 0x06C7           # REG_AOUT_CTRL / REG_HPOUT_CTRL: bits 7:6 mute L/R, bit 3 normal mode
OUT_ON, OUT_MUTED = 0x08, 0xC8
OUTS = (("hpout, amp P7.4 = 1 (as flashed: hpout feeds the amp)", OUT_MUTED, OUT_ON, 1),    # aout unused in the fw (#94)
        ("hpout, amp P7.4 = 0", OUT_MUTED, OUT_ON, 0))
AMP_WAIT_S = 1.5                                # unmute: SDK pass + DVC ramp (<= 400 ms, _DVC_VOLUME_MUTE_TIMER) + amp; x1.25 + ddc


def amp_wait(u, rio):
    """Seconds until P7.4 reads 1 (amp on), None on expiry."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < AMP_WAIT_S:
        v = u.rd(rio, PORTS["P7.4 (amp enable, pin 161)"])
        if v and v[0] & 1:
            return time.monotonic() - t0
    return None


def ddc_vcp(code: int, val: int, what: str = "") -> bool:
    """DDC/CI set VCP (16-bit value) straight on the bus (dbg_link._setvcp); MCCS gap after, NAK retried."""
    import dbg_link
    for k in range(VCP_TRIES):
        try:
            dbg_link._setvcp(BUS, code, val >> 8, val & 0xFF)
            time.sleep(MCCS_GAP_S)
            say(f"setvcp {code:02X} = 0x{val:04X} on bus {BUS}" + (f" ({what})" if what else "") + (f", try {k + 1}" if k else ""))
            return True
        except OSError as e:
            time.sleep(MCCS_GAP_S)
            err = e
    say(f"setvcp {code:02X} = 0x{val:04X} on bus {BUS} FAILED after {VCP_TRIES} tries: {err}")
    return False


def ddc_get(code: int) -> int | None:
    r = subprocess.run(["ddcutil", "--bus", str(BUS), "getvcp", f"{code:02X}", "--terse"], capture_output=True, text=True,
                       timeout=DDC_LIMIT_S)
    m = re.search(r"VCP \S+ C (\d+) \d+", r.stdout)                     # continuous: current, max
    v = int(m.group(1)) if m else None
    if m is None and (m := re.search(r"VCP \S+ CNC x\S+ x\S+ x([0-9a-fA-F]+) x([0-9a-fA-F]+)", r.stdout)):
        v = int(m.group(1), 16) << 8 | int(m.group(2), 16)              # non-continuous: mh ml sh sl, current = sh:sl
    say(f"getvcp {code:02X} on bus {BUS}: " + (str(v) if v is not None else f"failed rc {r.returncode} {(r.stdout + r.stderr).strip()[:120]}"))
    return v


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
def unit_connector() -> str:
    if CONNECTOR:
        return CONNECTOR
    import json
    for u in json.loads((ROOT / "scripts/devices.json").read_text())["units"].values():
        if u["serial"] == SERIAL:
            return u["connector"]
    raise SystemExit(f"{SERIAL} not in scripts/devices.json: give --connector")


def hdmi_pcm() -> tuple[str, int, int]:
    """(card id, card number, device) of the unit's pcm: ALSA card on the connector's GPU vendor, ELD = MON_NAME + connector type."""
    conn = unit_connector()
    vendor = Path(f"/sys/class/drm/{conn.split('-')[0]}/device/vendor").read_text().strip()
    want = 1 if "-DP-" in conn else 0           # ELD byte 5 bits 3:2 conn_type: 0 = HDMI, 1 = DP
    lst = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
    for cdir in sorted(Path("/proc/asound").glob("card[0-9]*")):
        card = int(cdir.name[4:])
        vf = Path(f"/sys/class/sound/card{card}/device/vendor")
        if not vf.exists() or vf.read_text().strip() != vendor:
            continue
        cid = (cdir / "id").read_text().strip()
        for m in re.finditer(rf"card {card}: \S+ \[[^]]*\], device (\d+): HDMI \d+ \[{MON_NAME}\]", lst):
            dev = int(m.group(1))
            out = subprocess.run(["amixer", "-c", cid, "cget", f"iface=PCM,name=ELD,device={dev}"], capture_output=True, text=True).stdout
            v = re.search(r": values=(\S+)", out)
            eld = [int(x, 16) for x in v.group(1).split(",")] if v else []
            if len(eld) > 5 and (eld[5] >> 2) & 3 == want:
                say(f"host: {conn} (GPU vendor {vendor}) -> ALSA card {card} ({cid}) device {dev}, ELD {MON_NAME} "
                    f"{'DP' if want else 'HDMI'}")
                return cid, card, dev
    raise SystemExit(f"no ALSA pcm for {conn}: ELD {MON_NAME} {'DP' if want else 'HDMI'} on GPU vendor {vendor} not found "
                     f"(EDID / hotplug)")


def host(unmute: bool) -> str:
    cid, card, dev = hdmi_pcm()
    say(f"host: {SERIAL} audio = ALSA card {card} ({cid}) device {dev} (ELD names {MON_NAME})")
    ctype = "DisplayPort" if "-DP-" in unit_connector() else "HDMI"
    eld = [e for e in Path(f"/proc/asound/card{card}").glob("eld#*")
           if MON_NAME in (t := e.read_text(errors="replace")) and re.search(rf"connection_type\s+{ctype}\b", t)]
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
        import i2cbus
        i2cbus.require_unit(BUS, SERIAL, None)  # SystemExit on another monitor

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
    global BUS, SERIAL, CONNECTOR
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("host", "regs", "tones", "poke", "rd", "dport", "dpoke", "tone", "gen", "outs", "steps"))
    ap.add_argument("--map", type=Path)
    ap.add_argument("--bus", type=int, default=BUS)
    ap.add_argument("--serial", default=SERIAL)
    ap.add_argument("--connector", help="DRM connector of the unit's link (card1-HDMI-A-2); default devices.json for --serial")
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--chan", choices=("left", "right", "both", "silence"), default="both")
    ap.add_argument("--hz", type=int, default=440)
    ap.add_argument("--freqs", help="steps: comma list of tone Hz played in turn per step, e.g. 200,1000,4000")
    ap.add_argument("--only", help="steps: comma list of step numbers to run (default all)")
    ap.add_argument("pokes", nargs="*")
    a = ap.parse_args()
    BUS, SERIAL, CONNECTOR = a.bus, a.serial, a.connector
    say(f"audio_test {a.cmd} {' '.join(a.pokes)} (map {a.map})")
    if a.cmd == "host":
        host(False)
        return 0
    if a.cmd == "tone":
        dev = host(True)
        ch = {"left": (1, 0), "right": (0, 1), "both": (1, 1), "silence": (0, 0)}[a.chan]
        p = tone_wav(a.chan, a.hz, ch, a.secs)
        say(f"TONE {a.chan.upper()} {a.hz} Hz START {time.strftime('%H:%M:%S')} ({a.secs:.0f} s) -> {dev}")
        r = subprocess.run(["aplay", "-q", "-D", dev, str(p)], capture_output=True, text=True, timeout=a.secs * APLAY_LIMIT_S + 2)
        say(f"TONE {a.chan.upper()} {a.hz} Hz END {time.strftime('%H:%M:%S')} rc {r.returncode} {r.stderr.strip()[:160]}")
        return r.returncode
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
            if any(int(pk.split("=")[0], 16) in DVC_GAIN for pk in a.pokes):    # DVC gain is double-buffered: latch it
                l0 = u.rd(rio, DVC_LATCH)
                ok = l0 is not None and u.wr(rio, DVC_LATCH, l0[0] | DVC_LATCH_BIT)
                g = u.rd(rio, DVC_GAIN[0], 2)
                say(f"DVC gain latched (08A7 bit 6: {'ok' if ok else 'FAILED'}); applied gain 08A5/08A6 = {g.hex(' ') if g else '?'} "
                    f"(stays 00 00 while the SDK holds the DVC muted: no stream / P7.4 = 0)")
        u.session(go)
        return 0
    if a.cmd == "rd":
        def go(rio):
            for x in a.pokes:
                ad, n = (x.split("+") + ["1"])[:2]
                v = u.rd(rio, int(ad, 16), int(n))
                say(f"rd {ad.upper()} {u.names.get(int(ad, 16), '')}: {v.hex(' ') if v else 'read failed'}")
        u.session(go)
        return 0
    if a.cmd == "dport":
        def go(rio):
            old = u.rd(rio, DPORT_IDX)
            for x in a.pokes:
                i = int(x, 16)
                ok = u.wr(rio, DPORT_IDX, i)
                v = u.rd(rio, DPORT_DATA)
                say(f"dport 71C9 idx {i:02X} {DPORT_NAMES.get(i, '')}: {v.hex() if v and ok else 'failed'}")
            if old:
                u.wr(rio, DPORT_IDX, old[0])
        u.session(go)
        return 0
    if a.cmd == "steps":
        dev = host(True)
        freqs = [int(f) for f in a.freqs.split(",")] if a.freqs else [a.hz]
        if any(not 20 <= hz < HZ_FLAG for hz in freqs):
            raise SystemExit(f"--freqs: each 20..{HZ_FLAG - 1} Hz, got {freqs}")
        waves = [(hz, tone_wav("both", hz, (1, 1), a.secs)) for hz in freqs]
        only = [int(x) for x in a.only.split(",")] if a.only else list(range(1, STEPS + 1))
        if any(not 1 <= n <= STEPS for n in only):
            raise SystemExit(f"--only: steps 1..{STEPS}, got {only}")
        vol0 = ddc_get(VCP_VOLUME)
        osd = [sys.executable, str(ROOT / "scripts/osd_test.py"), str(BUS), "--serial", SERIAL, "--map", str(a.map), "--cmd"]
        import dbg_link
        with dbg_link.linked(BUS, 2):
            r = subprocess.run(osd + ["debug"], capture_output=True, text=True, timeout=DDC_LIMIT_S)
        say(f"console open (test cmd 0x26, held): rc {r.returncode} {r.stderr.strip()[:120]}")
        say(f"STEPS START {time.strftime('%H:%M:%S')}: steps {','.join(map(str, only))} of {STEPS}, tones {freqs} Hz, "
            f"{a.secs:g} s each, {GEN_GAP_S:.0f} s gap between steps")
        bad, held = 0, None
        try:
            for i, n in enumerate(only):
                if i:
                    time.sleep(GEN_GAP_S)
                held = n
                ddc_vcp(GEN_VCP, STEP_START + n, f"step {n} set up")
                say(f"STEP {n}/{STEPS} START {time.strftime('%H:%M:%S')}: {STEP_WHAT[n - 1]} (console 'audio test {n}/{STEPS}: ...'); "
                    f"{STEP_SETTLE_S} s settle")
                time.sleep(STEP_SETTLE_S)
                for hz, p in waves:
                    ddc_vcp(GEN_VCP, HZ_FLAG | hz, f"announce {hz} Hz")
                    say(f"  STEP {n} TONE {hz} Hz START {time.strftime('%H:%M:%S')} (console 'audio test {n}: {hz} Hz')")
                    r = subprocess.run(["aplay", "-q", "-D", dev, str(p)], capture_output=True, text=True,
                                       timeout=a.secs * APLAY_LIMIT_S + 2)
                    bad += r.returncode != 0
                    say(f"  STEP {n} TONE {hz} Hz END {time.strftime('%H:%M:%S')} aplay rc {r.returncode} {r.stderr.strip()[:120]}")
                ddc_vcp(GEN_VCP, STEP_DONE + n, f"step {n} done")
                held = None
                say(f"STEP {n}/{STEPS} END {time.strftime('%H:%M:%S')}")
        finally:
            if held is not None:                # stopped inside a step: release it (amp, user volume)
                ddc_vcp(GEN_VCP, STEP_DONE + held, f"step {held} done (run stopped inside it)")
            vol1 = ddc_get(VCP_VOLUME)
            if vol0 is not None and vol1 != vol0:
                ddc_vcp(VCP_VOLUME, vol0, f"volume back to {vol0} % (read {vol1})")
            else:
                say(f"volume {vol1} % unchanged (before {vol0} %)")
        say(f"STEPS END {time.strftime('%H:%M:%S')}: {bad} aplay failure(s); console stays open (clear: osd_test.py ... --cmd clear)")
        return 1 if bad else 0
    if a.cmd == "outs":
        dev = host(True)
        p = tone_wav("both", a.hz, (1, 1), a.secs)
        amp = PORTS["P7.4 (amp enable, pin 161)"]
        try:
            for k, (what, ao, hp, en) in enumerate(OUTS):
                if k:
                    time.sleep(GEN_GAP_S)
                u.session(lambda rio: (u.wr(rio, AOUT_CTRL, ao), u.wr(rio, HPOUT_CTRL, hp), u.wr(rio, amp, en)))
                rb = u.session(lambda rio: [u.rd(rio, x) for x in (AOUT_CTRL, HPOUT_CTRL, amp)])
                say(f"OUT {k + 1} START {time.strftime('%H:%M:%S')} ({a.secs:.0f} s, {a.hz} Hz both channels): {what}; "
                    f"read back 06C6 {rb[0].hex() if rb[0] else '?'} 06C7 {rb[1].hex() if rb[1] else '?'} P7.4 {rb[2][0] & 1 if rb[2] else '?'}")
                r = subprocess.run(["aplay", "-q", "-D", dev, str(p)], capture_output=True, text=True, timeout=a.secs * APLAY_LIMIT_S + 2)
                say(f"OUT {k + 1} END {time.strftime('%H:%M:%S')} rc {r.returncode}")
        finally:
            u.session(lambda rio: (u.wr(rio, AOUT_CTRL, OUT_ON), u.wr(rio, HPOUT_CTRL, OUT_ON), u.wr(rio, amp, 1)))
            say("outputs restored: 06C6 = 08, 06C7 = 08, P7.4 = 1")
        return 0
    if a.cmd == "gen":
        mux0 = u.session(lambda rio: u.rd(rio, MUX_ANA_OUT))
        try:
            for k, x in enumerate(a.pokes):
                if k:
                    time.sleep(GEN_GAP_S)
                u.session(lambda rio: u.wr(rio, MUX_ANA_OUT, int(x, 16)))
                ddc_vcp(GEN_VCP, 1)
                t_amp = u.session(lambda rio: amp_wait(u, rio))
                note = f"amp on {t_amp * 1000:.0f} ms after the VCP" if t_amp is not None else ""
                if t_amp is None:               # generator path leaves the amp off (#94): force it for the ear test
                    ok = u.session(lambda rio: u.wr(rio, PORTS["P7.4 (amp enable, pin 161)"], 1) and
                                   (u.rd(rio, PORTS["P7.4 (amp enable, pin 161)"]) or b"\0")[0] & 1)
                    note = f"amp NOT on within {AMP_WAIT_S} s: P7.4 forced 1 by debug poke ({'ok' if ok else 'FAILED'})"
                say(f"GEN sine (chip generator) START {time.strftime('%H:%M:%S')}, 06E0 = {x.upper()} ({a.secs:.0f} s), {note}")
                time.sleep(min(1.0, a.secs / 3))
                u.session(lambda rio: u.regs(rio, f"generator on, 06E0 = {x}"))
                time.sleep(max(0.0, a.secs - min(1.0, a.secs / 3) - REGS_READ_S))
                ddc_vcp(GEN_VCP, 0)
                say(f"GEN sine END {time.strftime('%H:%M:%S')}")
        finally:
            ddc_vcp(GEN_VCP, 0)
            if mux0:
                u.session(lambda rio: u.wr(rio, MUX_ANA_OUT, mux0[0]))
                say(f"06E0 restored to {mux0[0]:02X}")
        return 0
    if a.cmd == "dpoke":
        def go(rio):
            old = u.rd(rio, DPORT_IDX)
            for x in a.pokes:
                i, v = (int(y, 16) for y in x.split("="))
                ok = u.wr(rio, DPORT_IDX, i)
                b = u.rd(rio, DPORT_DATA)
                ok = ok and u.wr(rio, DPORT_IDX, i) and u.wr(rio, DPORT_DATA, v)
                u.wr(rio, DPORT_IDX, i)
                r = u.rd(rio, DPORT_DATA)
                say(f"dpoke 71CA idx {i:02X} {DPORT_NAMES.get(i, '')}: {b.hex() if b else '?'} -> {v:02X} "
                    f"(write {'ok' if ok else 'NAK'}), read back {r.hex() if r else '?'}")
            if old:
                u.wr(rio, DPORT_IDX, old[0])
        u.session(go)
        return 0
    return tones(a, u)


if __name__ == "__main__":
    sys.exit(main())
