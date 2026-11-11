# RTD2795T / RL6449 216-pin board audit

This audit is deliberately pin-number complete: the companion TSV has one row for every package pin, 1 through 216.
It combines the RTD2795T-CG LQFP216 package table with what the reversed firmware proves about the JXC board.

## Coverage

- 77 multiplexed pads are exposed by the scaler's page-`0x10` pin-share registers and have a scaler GPIO/function name.
- Original-firmware read/write analysis assigns board roles to the power key, both key ADCs, the two-colour LED,
  input HPD/cable sensing, panel/backlight controls, flash WP, IR, audio mute, and the NORMAL-power output group.
- All 216 package pins are now named from Table 1 of the RTD2795T-CG datasheet copy. This includes the fixed HDMI/DP
  input lanes, analogue VGA pins, panel eDP/V-by-One transmitter lanes, audio pins, crystal, power, ground, DDR rails,
  and pins 78 through 88 identified as NC.
- The remaining uncertainty is board routing, not package identity. Fixed pins that have not been physically traced are
  marked `package-function-only`; this does not imply that the package pin itself is unknown.

Generated ledgers:

- `docs/monitors/rtd2795t-216-pin-ledger.html` for interactive filtering by power/ground, fixed function, GPIO/mux,
  and NC pins.
- `docs/monitors/rtd2795t-bus-view.html` for selecting one interface/bus and seeing only its pins, with descriptions
  and electrical notes.
- `docs/monitors/rtd2795t-216-pin-ledger.md` for readable review in VS Code.
- `docs/monitors/rtd2795t-216-pin-ledger.tsv` for spreadsheet/manual review.
- `docs/monitors/rtd2795t-216-pin-ledger.json` for reverse-engineering tools and scripted queries. Its top-level
  metadata records the datasheet URL and explicitly labels it as a third-party mirror.

## Important corrections

| Package pins | Scaler pads | Proven board role |
|---|---|---|
| 91 / 92 | P3.5 / P3.6, push-pull | two-colour front power indicator: `(1,0)` normal, `(0,1)` standby, `(0,0)` off |
| 184 / 185 | P8.4 / P8.5, push-pull | NORMAL-power-state output group; sequenced high on wake and low entering standby/off; loads unresolved |
| 201 / 202 | P9.7 / PA.0, open-drain | same NORMAL-power-state group; released on and pulled low in standby/off; loads unresolved |
| 159 | P7.2, push-pull | panel or switched-peripheral power enable |
| 195 / 196 | P9.1 / P9.2 | backlight PWM4 / active-low backlight enable |

P8.4 was inherited under the SDK demo-board name `bLED1`, but that name is wrong for this board. The original JXC
firmware treats it as a power-state output and sequences it with P8.5, P9.7, and PA.0. Reusing it as an LED can alter
power sequencing.

## Evidence and confidence

- `confirmed`: original firmware reads/writes the pad in a function whose SDK-equivalent role is known, or the live
  hardware behaviour was tested.
- `confirmed-role` / `confirmed-behaviour`: the role or state transitions are proven, but the PCB load or physical LED
  colour has not yet been traced.
- `configured`: the live pin-share selects a dedicated peripheral function; physical routing is not independently traced.
- `unknown-load`: GPIO direction/function is known, PCB destination is not.
- `package-function-only`: the datasheet identifies the fixed package function, but the JXC PCB net has not been traced.

Primary local evidence:

- `docs/monitors/pinshare-live-AWT26110003.tsv`
- `docs/monitors/gpio-roles.md`
- `docs/reversing/dahua-fw/gpio-ir.md`
- `re/jxc-4k/gpio_audit.tsv`
- `fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K_PINSHARE.h`

External package-table evidence:

- [RTD2795T-CG datasheet copy, Table 1: Signals Pin Assignment](https://rtddisplay.com/upload/20231007170054.pdf)
- `docs/monitors/rtd2795t-datasheet-facts.md` and `.json` contain the extracted device, interface, OSD, electrical,
  mechanical, and package facts plus separately labelled RE inferences.

The host is a third-party datasheet mirror rather than Realtek's official site, so board-role claims remain tied to the
local firmware and live-hardware evidence. The package table is internally consistent with the 77 live pin-share pads.

Regenerate the ledger with `python3 scripts/rtd_pin_ledger.py`.
