# Board GPIO roles (JXC 4K, RTD2795T, original firmware)

- Method 1, hardware: `scripts/rtd_gpio_live.py` reads every regdb GPIO pin + pin-share mode over ISP, unit AWT26110001 (original fw), 2026-11-05, monitor ON vs DPMS standby (`ddcutil setvcp d6 4`). Raw: `tmp/regs/AWT26110001-gpio-{on,standby}-*.json`. Issue #7.
- Method 2, code: three read-only agents traced writes in `~/vendors/realtek/analysis/jxc-4k/bank*/decompiled_named.c` (confidence per row).
- Read caveat: in standby the always-off domain reads 0 for pulled-up inputs (P4-P8 inputs), so only pins whose mode is output/OD and that code writes are used as evidence.

| Pin | Port | Mode | ON | Standby | Code evidence | Role |
|---|---|---|---|---|---|---|
| 159 | P7.2 | PP out | 1 | 0 | set in power-up (during splash), cleared first in power-down; never read; OD pins P7.4, P9.7, PA.0 fall 1 -> 0 with it | **panel power (or switched peripheral rail) enable**, active high. The scaler itself stays alive in standby, so it is not the scaler's own supply; which rail is not proven |
| 184 | P8.4 | PP out | 1 | 0 | written together with P8.5 at every site (`de69`, init `D2A0`); SDK DEMO boards name P8.4 `bLED1`, `_LED_ON 1` | **power LED (LED1)**, active high: high ON, low in standby matches the SDK demo board; not proven by an LED observation |
| 185 | P8.5 | PP out | 1 | 0 | written together with P8.4 at every site (`de69`, init `D2A0`); follows P9.2 in the vendor sequence | **not the backlight enable** (that is P9.2). Role undetermined; SDK name `bBACKLIGHTPOWER` does not match this board (#7) |
| 195 | P9.1 | mode 3 = PWM4 push-pull | pwm | - | bank6 `3902` selects PWM4 PP (mode 3); no caller found | **backlight PWM** (pin function set live; duty regs not read) |
| 196 | P9.2 | PP out | 0 | 1 | cleared at splash end; set by power-down and standby paths | **backlight enable, active low**: 0 = on, 1 = off. Proven live 2026-11-06 with `scripts/rtd_reg_poke.py` on unit 3 (#7). |
| 91, 92 | P3.5, P3.6 | PP out | 0, 0 | mode regs read 0 | 2-bit state pair from `d6b2` (mode dispatcher) | undetermined; labelled DPTX AUX in regdb |
| 97 | P4.2 | PP out | 1 | - | only read, gates a routine | undetermined (labelled DP hot-plug 1 in pin-share) |
| 190 | P8.6 | PP out | 0 | - | high during a command sequence (`f861` from `bc9f`) | undetermined; not part of power sequence |
| 160, 161 | P7.3, P7.4 | OD out | 0, 1 | 0, 0 | both driven low once at boot init (`D2A0`: P7.4 low, delay, P7.3 low); P7.4 also follows a bank3 state bit | undetermined; SDK RL6432 boards use them as D3 MHL VBUS / D2 TMDS switch (not this board) |
| 179 | P8.1 | OD out | 1 | - | SDK: `bVCCKOFFPOWER`, `_VCCK_OFF_POWER_ON 1`. Old firmware never writes it | VCCK_OFF per SDK name; no firmware write, so unverified (probably left at its reset level) |

## Not found
- Flash write-protect and DDR/VCCK pins: no write seen for the pins traced; WP# is 0x1036/0xFE26 in the SDK board header (= P8.6 here), but P8.6 pulses during a command sequence, which fits a WP#/CS line. Check before using.
- Power key / LED key mapping and the P9.7, PA.0 roles: never written by the firmware.

## Power sequence from code (old firmware)
1. Boot splash path: P7.2 high, then P8.4 high, 10 ticks, P8.5 high, 10 ticks; splash end clears P9.2 (backlight on).
2. Power-down: P8.5 low, P8.4 low, delay (200 ticks); P7.2 low in the 917c power-down step. Tick units unverified.
