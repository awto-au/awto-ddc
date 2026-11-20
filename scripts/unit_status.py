"""Status line of the GUI (awto-ddc#277): decode + format of the cheap reads of one unit. Read-only: DDC/CI Get VCP frames (the
info rows go through the paged read: its only Set is the RAM-only row selector 0xE0, no setting changes), and reads over the debug
slave 0x35 when it already answers (never the DDC <-> debug swap, which is a Set of a unit mode).
The device ops live in unit_ops.status(); docs/monitor-gui.md "Status line"."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings_table as T

DDC_ROWS = ("volume", "mute", "brightness", "contrast", "power_mode", "input")      # registry rows read by their own VCP code
INFO_ROWS = ("info_hres", "info_vres", "info_vfreq", "info_loop")                   # no VCP code: paged read; vfreq in 0.1 Hz
DIAG_BASE, DIAG_LEN = 0xF6D0, 48                                                    # docs/diag-block.md
DIAG_LOOP_OFS, DIAG_STAGE_OFS = 0x2A, 0x03                                          # main-loop passes in the last ~1 s (u16), stage
XTAL_KHZ = 14318                                                                    # _EXT_XTAL (_XTAL14318K), fw/osd/console.c title clocks
# regdb RTD2795T-CG names: M2PLL M / N / MSB, MCU clock dividers (fw/osd/console.c AwtoPutClocks, docs/clock-sweep.md)
PLL_E0, PLL_E1, PLL_E7 = 0x01E0, 0x01E1, 0x01E7
MCU_FFE9, MCU_FFED, MCU_FFEE = 0xFFE9, 0xFFED, 0xFFEE
FF_PWM4H_DUT = 0xFF50                                                               # PWM4 duty high byte (_PWM_8BIT); backlight is PWM4
PWM_FULL = 255
PWM_INVERSE = True                                                                  # _BACKLIGHT_PWM_INVERSE: higher duty = dimmer
CLK_SEL_PLL = 0x02                                                                  # FFED[1] MCU_CLK_SEL: 1 = M2PLL, 0 = crystal
DIV_MASK, DIV_SHIFT = 0x0F, 2                                                       # FFED / FFEE [5:2]; FFE9 [3:0]
PLL_O_SHIFT, PLL_O_MASK = 4, 0x03                                                   # 0x01E1[5:4] = O / 2
MSB_M, MSB_N, CODE = 0x30, 0x0F, 2                                                  # 0x01E7[5:4] = M[9:8], [3:0] = N[7:4]; codes = value - 2


def _div(v: int) -> int:
    v &= DIV_MASK
    return v or 1


def clocks(e0: int, e1: int, e7: int, ffe9: int, ffed: int, ffee: int) -> dict:
    """MHz of CPU / PLL / SPI as the diag console title computes them; crystal clock: cpu = xtal, no PLL"""
    if not ffed & CLK_SEL_PLL:
        return {"cpu": XTAL_KHZ / 1000, "pll": None, "spi": None}
    m = e0 | (e7 & MSB_M) << 4
    n = (e7 & MSB_N) << 4 | e1 & MSB_N
    o = ((e1 >> PLL_O_SHIFT) & PLL_O_MASK) * 2 or 1
    pll = XTAL_KHZ * (m + CODE) / ((n + CODE) * o)
    f = _div(ffed >> DIV_SHIFT)
    return {"cpu": pll / f / _div(ffee >> DIV_SHIFT) / 1000, "pll": pll / 1000, "spi": pll / f / _div(ffe9) / 1000}


def backlight_pct(duty: int) -> int:
    """lit percent of a PWM4 duty byte"""
    return round(((PWM_FULL - duty) if PWM_INVERSE else duty) * 100 / PWM_FULL)


def label(name: str, raw: int) -> str:
    """row value -> text: enum option label, else the number"""
    r = T.BY_NAME[name]
    opts = r.get("options") or []
    return opts[raw] if r["type"] == "enum" and 0 <= raw < len(opts) else str(raw)


def row_value(name: str, cur: int) -> int | None:
    """raw VCP value of a Get -> registry row value (enum: the option behind the VCP value); None = not one of the options"""
    r = T.BY_NAME[name]
    if r.get("option_vcp"):
        return r["min"] + r["option_vcp"].index(cur) if cur in r["option_vcp"] else None
    return cur


def decode_diag(b: bytes, be: bool) -> dict:
    e = ">" if be else "<"
    return {"stage": b[DIAG_STAGE_OFS], "loop": struct.unpack_from(e + "H", b, DIAG_LOOP_OFS)[0]}


def fmt_mhz(x) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def format_line(st: dict) -> str:
    """one status line: 'CPU 350.8 PLL 350.8 SPI 116.9  1920x1080 60.000Hz  ...'; a missing source shows n/a, never a stale value"""
    d, g = st.get("ddc", {}), st.get("dbg") or {}
    clk = g.get("clk")
    parts = [f"CPU {fmt_mhz(clk['cpu'])} PLL {fmt_mhz(clk['pll'])} SPI {fmt_mhz(clk['spi'])}" if clk else "CPU n/a PLL n/a SPI n/a"]
    t, i = g.get("timing"), st.get("info", {})
    parts.append(f"{t['w']}x{t['h']} {t['hz']:.3f}Hz" if t else
                 (f"{i['info_hres']}x{i['info_vres']} {i['info_vfreq'] / 10:.1f}Hz" if i.get("info_hres") else "NO INPUT")
                 if "info_hres" in i else "timing n/a")
    if "power_mode" in d:
        parts.append(f"power {label('power_mode', d['power_mode'])}")
    if "input" in d:
        parts.append(f"input {label('input', d['input'])}")
    parts.append(f"sound {'muted' if d['mute'] else 'on'} vol {d['volume']}" if "mute" in d and "volume" in d else "sound n/a")
    parts.append(f"bright {d['brightness']}" if "brightness" in d else "bright n/a")
    parts.append(f"contrast {d['contrast']}" if "contrast" in d else "contrast n/a")
    pwm = g.get("pwm")
    parts.append(f"PWM {pwm} ({backlight_pct(pwm)} %)" if pwm is not None else "PWM n/a")
    loop = g.get("loop", i.get("info_loop"))
    parts.append(f"loop {loop}/s" if loop is not None else "loop n/a")
    parts.append(f"fw {st['tag']}" if st.get("tag") else "fw n/a")
    return "  ".join(parts)
