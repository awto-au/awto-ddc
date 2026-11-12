# Board GPIO roles (JXC 4K, RTD2795T, original firmware)

- Method 1, hardware: `scripts/rtd_gpio_live.py` reads every regdb GPIO pin + pin-share mode over ISP, unit AWT26110001 (original fw), 2026-11-05, monitor ON vs DPMS standby (`ddcutil setvcp d6 4`). Raw: `tmp/regs/AWT26110001-gpio-{on,standby}-*.json`. Issue #7.
- Method 2, code: three read-only agents traced writes in `~/vendors/realtek/analysis/jxc-4k/bank*/decompiled_named.c` (confidence per row). Corrected and extended 2026-11-08 from the disassembly and the SDK user layer (#93): `docs/reversing/dahua-fw/gpio-ir.md`, table `re/jxc-4k/gpio_audit.tsv`.
- Read caveat: in standby the always-off domain reads 0 for pulled-up inputs (P4-P8 inputs), so only pins whose mode is output/OD and that code writes are used as evidence.

| Pin | Port | Mode | ON | Standby | Code evidence | Role |
|---|---|---|---|---|---|---|
| 159 | P7.2 | PP out | 1 | 0 | set in power-up (during splash), cleared first in power-down; never read; OD pins P7.4, P9.7, PA.0 fall 1 -> 0 with it | **panel power (or switched peripheral rail) enable**, active high. The scaler itself stays alive in standby, so it is not the scaler's own supply; which rail is not proven |
| 184 | P8.4 | PP out | 1 | 0 | written with P8.5, P9.7, PA.0 as one group: `ScalerPinshareConfig` (1 in NORMAL power, 0 in saving / off), `ScalerPowerIsolation` (10 ms / 10 ms up, 200 ms down), 1:f188, init `D2A0` (#93, `docs/reversing/dahua-fw/gpio-ir.md` s.3) | **NORMAL-power-state enable, not the LED**: the SDK demo name `bLED1` does not apply; the power LED is P3.5 / P3.6. Load unknown [?] |
| 185 | P8.5 | PP out | 1 | 0 | same group as P8.4 | **not the backlight enable** (that is P9.2); high for the whole NORMAL state. Load unknown [?] |
| 195 | P9.1 | mode 3 = PWM4 push-pull | pwm | - | bank6 `3902` selects PWM4 PP (mode 3); no caller found | **backlight PWM** (pin function set live; duty regs not read) |
| 196 | P9.2 | PP out | 0 | 1 | cleared at splash end; set by power-down and standby paths | **backlight enable, active low**: 0 = on, 1 = off. Proven live 2026-11-06 with `scripts/rtd_reg_poke.py` on unit 3 (#7); health check `backlight en`, board header `bBACKLIGHT_EN_N`. |
| 91, 92 | P3.5, P3.6 | PP out (SFR bits) | not readable | not readable (`0xFFE3` reads 0 for all P3 pins) | `d6b2` = `UserInterfaceKeyPadLedControl`: (1,0) power on / signal states, (0,1) power saving, (0,0) off; init (1,0) (#93, `gpio-ir.md` s.2) | **two-colour power LED** [fw+x]; colours / physical LED not observed. The `DPTX AUX` regdb label is the reference-board function |
| 97 | P4.2 | PP out | 1 | - | D1 HPD: 0 at init, set / clear in 1:e1c0, 1:818e, 4:d319; read in 1:c275, dab8, 4:fbb1 | D1 hot-plug (`bD1_HPD`) |
| 113 | P4.5 | input | 0 | 0 | read only, `1:f69b` = `UserInterfaceGetAudioDACOutput` | **headphone-jack select input**: low -> speaker, high -> headphone [fw+x]; polarity / switch type [?] |
| 201, 202 | P9.7, PA.0 | OD out | 1, 1 | 0, 0 | same group as P8.4 / P8.5 (`ScalerPinshareConfig`, `f188`, `e222`); released in NORMAL, pulled low in saving / off | NORMAL-power-state outputs; load unknown [?]. SDK MHL names do not apply |
| 190 | P8.6 | PP out | 0 | - | high during a command sequence (`f861` from `bc9f`) | undetermined; not part of power sequence |
| 160, 161 | P7.3, P7.4 | OD out | 0, 1 | 0, 0 | both driven low once at boot init (`D2A0`: P7.4 low, delay, P7.3 low); P7.4 then follows `ea99` = `UserInterfaceAdjustAudioAmpMuteProc` (mute proc 3:f8e5): high when unmuted and the speaker is selected | P7.3: static low, role [?] (our firmware leaves it released: unit 3 reads 1). P7.4: **speaker amp enable** [fw+x] |
| 179 | P8.1 | OD out | 1 | - | SDK: `bVCCKOFFPOWER`, `_VCCK_OFF_POWER_ON 1`. Old firmware never writes it | VCCK_OFF per SDK name; no firmware write, so unverified (probably left at its reset level) |

## Not found
- Flash write-protect and DDR/VCCK pins: no write seen for the pins traced; WP# is 0x1036/0xFE26 in the SDK board header (= P8.6 here), but P8.6 pulses during a command sequence, which fits a WP#/CS line. Check before using.
- Remaining unknown loads: P7.3, P8.4, P8.5, P9.7, PA.0 (written, purpose unproven); see `docs/reversing/dahua-fw/gpio-ir.md`.

## Power sequence from code (old firmware)
1. AC on (`D2A0`): P8.6 low, P8.5 high, 10 ms, P8.4 high, P7.2 low, P9.2 high, P3.5 / P3.6 = (1,0), P7.4 low, 200 ms, P7.3 low, then P9.7, PA.0, P8.5, P8.4 = 1. Boot splash path: P7.2 high; splash end clears P9.2 (backlight on).
2. To saving / off: panel down (`917c(1)`: P9.2 high, P7.2 low), LED (0,1) / (0,0), `ScalerPinshareConfig(3 / 1)` = P8.4, P8.5, P9.7, PA.0 low, `ScalerPowerIsolation`: P8.5 low, P8.4 low, then 200 ms.
3. To normal: `ScalerPowerIsolation`: P8.4 high, 10 ms, P8.5 high, 10 ms (when the VCCK_OFF / group power-cut bits are set); 1:f188 and `ScalerPinshareConfig(2)`: P9.7, PA.0, P8.5, P8.4 high; LED (1,0).
- Delays from the `FB15` millisecond helper (`ScalerTimerDelayXms`); unit assumed ms [guess].
