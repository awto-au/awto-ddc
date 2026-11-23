#!/usr/bin/env python3
"""Audio tap for the firmware simulator (fw_sim): time-stamped writes to the HDMI audio test generator and the amp pins -> mono WAV.

usage (library): tap = AudioTap(clock); pass it in the Machine devs; tap.wav(path, t0, t1) after the run. Docs: docs/pacman-sound.md
  - Recorded: indirect data port writes of the D2 / D3 HDMI audio block (AFCR, CMCR, SCAPR) and the amp pins P7.4 / P7.3.
  - Model (everything in MODEL below is [guess]): tone f = K / sc (AFCR.tst_i2s_sw = 1), K / 2 / sc (= 0), sine (phase continuous over pitch changes), silent unless
    generator on AND amp enabled AND not muted. Same K as scripts/pacman_sound.py (PS_K_DEFAULT_HZ).
  - Register addresses are numeric (regdb re/regdb/RTD2795T-CG.tsv.gz): AWTO_R_ names exist only in firmware builds (gen_regnames.py).
"""
from __future__ import annotations

import wave
from pathlib import Path

import fw_sim as S
import numpy as np

# --- regdb (RTD2795T-CG.tsv.gz): D2 block = page 71, D3 = page 72; address port 0x7xC9, data port 0x7xCA, idx = port_idx column
AP_D2, AP_D3 = 0x71C9, 0x72C9
IDX_AFCR, IDX_CMCR, IDX_SCAPR = 3, 16, 18                      # PORT_PAGEnn_HDMI_AFCR / CMCR / SCAPR
AFCR_TST_I2S_SW, AFCR_AUDIO_TEST_ENABLE = 0x80, 0x10            # AFCR bits 7, 4
CMCR_DBDCB = 0x10                                               # CMCR bit 4: latch S / D codes into the audio PLL (self-clearing)
SCAPR_SC_MASK = 0x7F                                            # SCAPR bits 6:0 (bit 7 = slc, S1 div 2)
RESET = {IDX_AFCR: 0x58, IDX_CMCR: 0x40, IDX_SCAPR: 0x05}       # regdb reset values (read back by the firmware's read-modify-write)
DVC_GAIN_MSB, DVC_GAIN_LSB = 0x08A5, 0x08A6                    # DVC_GAIN_MSB / LSB (regdb): the volume ramp target, written by the SDK mute / unmute
PIN_AMP_EN, PIN_AMP_MUTE = 0xFE1C, 0xFE1B                       # PORT74_PIN_REG (bAMP_EN, P7.4) / PORT73_PIN_REG (bAMP_MUTE, P7.3), bit 0

# --- model assumptions: [guess], the single place (docs/pacman-sound.md "Unverified")
MODEL = {
    "k_hz": 48000.0,        # tone f = k_hz / sc; = pacman_sound.PS_K_DEFAULT_HZ (sc 32 = 48 kHz sample rate, 32 samples per period)
    "latch_s": 0.0,         # delay from the CMCR.dbdcb write to the new pitch (hardware: after the current audio PLL cycle)
    "amp_en_reset": 0,      # pin values before the first firmware write (audio.c: EN 0, MUTE 1 at start)
    "amp_mute_reset": 1,
    "assume_amp_en": True,  # P7.4 treated as 1: on the unit the SDK's first playback unmute sets it; the sim has no audio stream, so it stays 0
    "level": 0.3,           # sine amplitude, fraction of full scale (DVC gain / amp response not modelled)
}
WAV_RATE = 44100


class AudioTap(S.Dev):
    """fw_sim device: records the register / pin writes with clock() time stamps (firmware seconds)."""
    writes = (AP_D2 + 1, AP_D3 + 1, AP_D2, AP_D3, PIN_AMP_EN, PIN_AMP_MUTE, DVC_GAIN_LSB)

    def __init__(self, clock):
        self.clock = clock                               # () -> firmware time, s
        self.events: list[tuple] = []                    # (t, "reg", idx, value) / (t, "pin", name, value)
        self.shadow = {AP_D2: dict(RESET), AP_D3: dict(RESET)}

    def on_write(self, m, a):
        if a in (AP_D2, AP_D3):                          # index write: preload the data cell, the SDK read-modify-writes AFCR / CMCR
            idx = m.rd(a)[0] & 0x3F
            m.put(f"set memory xram 0x{a + 1:x} 0x{self.shadow[a].get(idx, 0):x}")
        elif a - 1 in (AP_D2, AP_D3):
            base, idx, val = a - 1, m.rd(a - 1)[0] & 0x3F, m.rd(a)[0]
            if idx in RESET:
                self.shadow[base][idx] = val & ~CMCR_DBDCB if idx == IDX_CMCR else val
                self.events.append((self.clock(), "reg", idx, val))
        elif a == DVC_GAIN_LSB:                          # MSB is written first (ScalerAudioDVCAdjustVolume), the LSB write completes the gain
            self.events.append((self.clock(), "dvc", "gain", (m.rd(DVC_GAIN_MSB)[0] << 8) | m.rd(a)[0]))
        elif a == PIN_AMP_EN:
            self.events.append((self.clock(), "pin", "amp_en", m.rd(a)[0] & 1))
        elif a == PIN_AMP_MUTE:
            self.events.append((self.clock(), "pin", "amp_mute", m.rd(a)[0] & 1))

    def wav(self, path: Path, t0: float, t1: float, **kw) -> dict:
        return write_wav(path, self.events, t0, t1, **kw)


def segments(events, t_end: float, model: dict | None = None):
    """Events -> [(t_start, hz)] piecewise-constant tone (0 = silent), time-sorted, covering up to t_end."""
    md = {**MODEL, **(model or {})}
    afcr, sc, applied = RESET[IDX_AFCR] & ~AFCR_AUDIO_TEST_ENABLE, 0, 0        # generator off until the firmware turns it on
    en, mute = md["amp_en_reset"], md["amp_mute_reset"]
    if md["assume_amp_en"]:
        en = 1
    out, timeline = [], []
    for t, kind, a, v in sorted(events, key=lambda e: e[0]):
        if kind == "pin":
            en, mute = (v if a == "amp_en" and not md["assume_amp_en"] else en, v if a == "amp_mute" else mute)
        elif a == IDX_AFCR:
            afcr = v
        elif a == IDX_SCAPR:
            sc = v & SCAPR_SC_MASK
        elif a == IDX_CMCR and v & CMCR_DBDCB:
            applied, t = sc, t + md["latch_s"]
        else:
            continue
        timeline.append((t, afcr, applied, en, mute))
    last = None
    for t, afcr, applied, en, mute in timeline:
        on = bool(afcr & AFCR_AUDIO_TEST_ENABLE) and applied > 0 and en == 1 and mute == 0
        hz = md["k_hz"] / (1 if afcr & AFCR_TST_I2S_SW else 2) / applied if on else 0.0
        if hz != last:
            out.append((t, hz))
            last = hz
    return out


def synth(events, t0: float, t1: float, rate: int = WAV_RATE, model: dict | None = None) -> np.ndarray:
    """int16 mono samples for firmware time [t0, t1)."""
    md = {**MODEL, **(model or {})}
    n = max(0, round((t1 - t0) * rate))
    seg = segments(events, t1, md)
    ts = np.arange(n) / rate + t0
    freq = np.zeros(n)
    for t, hz in seg:                                    # later segments overwrite from their start on
        freq[ts >= t] = hz
    phase = np.cumsum(freq) / rate                       # phase continues across a pitch change
    return (np.sin(2 * np.pi * phase) * (freq > 0) * md["level"] * 32767).astype(np.int16)


def write_wav(path: Path, events, t0: float, t1: float, rate: int = WAV_RATE, model: dict | None = None) -> dict:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pcm = synth(events, t0, t1, rate, model)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return {"path": str(path), "samples": len(pcm), "rate": rate, "tone_s": float(np.count_nonzero(pcm)) / rate,
            "events": len(events)}


# --- pop-free ordering (#249 / #250): the order and spacing of amp enable, amp mute, generator and DVC gain events
# Delays = firmware constants in fw/audio/audio.c (tests/test_audio_order.py checks they match). By ear: the PAM8006A datasheet (/vendors/diodes/PAM8006A.pdf) gives no MUTE / SD timing.
ORDER = {
    "amp_mute_s": 0.002,    # AWTO_AMP_MUTE_MS: P7.3 high must have held this long before P7.4 low / a generator change
    "amp_wake_s": 0.020,    # AWTO_AMP_WAKE_MS: P7.4 high must have held this long before P7.3 low
    "dvc_ramp_s": 0.001,    # AWTO_DVC_RAMP_POLL_MS: a gain write of 0 holds at least one DONE poll before P7.3 high (the sim reads DONE set; real wait <= 2 polls)
}


def order_violations(events, order: dict | None = None) -> list[str]:
    """Invariants over a time-sorted event list (AudioTap.events); returns one text per violation, [] = pop-free.
      1. P7.4 (amp enable) rises only while the signal is zero: generator off, DVC gain 0, or P7.3 muted.
      2. P7.3 (unmute) falls only with the amp enabled for at least amp_wake_s.
      3. P7.4 falls only while muted (P7.3 high for at least amp_mute_s) or the signal is zero (generator off / gain 0).
      4. The generator is switched or its pitch changed only with the amp disabled, or muted for at least amp_mute_s.
      5. P7.3 (MUTE) changes only with the DVC at zero while the generator runs: high after a gain-0 write held dvc_ramp_s, low before the ramp up."""
    o = {**ORDER, **(order or {})}
    afcr, gain, en, mute = RESET[IDX_AFCR] & ~AFCR_AUDIO_TEST_ENABLE, 0, 0, 1
    t_en, t_mute, t_gain0 = None, float("-inf"), float("-inf")                # the reset state (amp off, muted) has settled
    out = []
    eps = 1e-9

    def silent():
        return not (afcr & AFCR_AUDIO_TEST_ENABLE) or gain == 0

    def muted_for(t):
        return mute == 1 and t_mute is not None and t - t_mute >= o["amp_mute_s"] - eps

    for t, kind, a, v in sorted(events, key=lambda e: e[0]):
        if kind == "dvc":
            if v == 0 and gain != 0:
                t_gain0 = t
            gain = v
        elif kind == "pin" and a == "amp_en" and v != en:
            if v == 1 and not (silent() or mute == 1):
                out.append(f"{t:.4f} s amp enabled while unmuted signal is non-zero (generator on, gain {gain}, P7.3 low)")
            if v == 0 and not (silent() or muted_for(t)):
                out.append(f"{t:.4f} s amp disabled before the mute settled ({o['amp_mute_s'] * 1e3:g} ms) with signal non-zero")
            en, t_en = v, t
        elif kind == "pin" and a == "amp_mute" and v != mute:
            if (afcr & AFCR_AUDIO_TEST_ENABLE) and (gain != 0 or (v == 1 and t - t_gain0 < o["dvc_ramp_s"] - eps)):
                out.append(f"{t:.4f} s MUTE pin {'high' if v else 'low'} with the DVC not at zero (gain {gain}, ramp {o['dvc_ramp_s'] * 1e3:g} ms)")
            if v == 0 and not (en == 1 and t_en is not None and t - t_en >= o["amp_wake_s"] - eps):
                out.append(f"{t:.4f} s unmuted {'with the amp disabled' if en == 0 else 'less than ' + format(o['amp_wake_s'] * 1e3, 'g') + ' ms after the amp enable'}")
            mute = v
            t_mute = t if v == 1 else None
        elif kind == "reg" and ((a == IDX_AFCR and (v ^ afcr) & AFCR_AUDIO_TEST_ENABLE) or (a == IDX_CMCR and v & CMCR_DBDCB)):
            if en == 1 and not muted_for(t):
                out.append(f"{t:.4f} s generator {'on / off' if a == IDX_AFCR else 'pitch change'} with the amp enabled and not muted for {o['amp_mute_s'] * 1e3:g} ms")
        if kind == "reg" and a == IDX_AFCR:
            afcr = v
    return out
