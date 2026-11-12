# Front keys

Code: `fw/sdcc/awto_keys.inc` (`AwtoKeyPoll` debounce / combo / repeat, `AwtoKeyRoute` the one dispatcher), reader `fw/sdcc/awto_gpio.inc`.
Decisions: awto-ddc#132 (Dan, 2026-11-12). Key names are the printed ones (POWER, AUTO, UP, DOWN, MENU, SOURCE).

## Reader

- Source: ADC ladders A0 (MENU, AUTO, UP) and A1 (SOURCE, DOWN) + P3.0 (POWER); bands in `fw/awto/inputs.tsv`.
- Debounce: two equal samples 10 ms apart (`AWTO_KEY_SAMPLE_MS`).
- Repeat: first at 500 ms, then every 100 ms (`AWTO_KEY_REPEAT_MS`, `AWTO_KEY_RATE_MS`).
- Combo wait: UP and DOWN hold their press 80 ms for the other one (`AWTO_KEY_COMBO_MS`); a lone UP / DOWN then acts. Every other key acts at once (MENU included).
- With POWER held nothing else counts. Several keys that are not UP+DOWN: the first key to go down acted, the rest is ignored until all are up.
- No HOLD event, no MENU+DOWN combo, no key at power-on.

## Combos

| combo | action |
|---|---|
| UP+DOWN | diagnostic console on / off (toggle) |

No other combo exists. Removed (awto-ddc#132): MENU+DOWN (debug link toggle), MENU+DOWN held at power-on (reset to defaults + debug link), HOLD at 3 s.

## Per screen

| screen | POWER | AUTO | UP | DOWN | MENU | SOURCE |
|---|---|---|---|---|---|---|
| off | on | - | - | - | - | - |
| power saving | wakes only (the press is used up) | wakes only | wakes only | wakes only | wakes only | wakes only |
| blank (no signal / no support, nothing open) | off | opens the awto menu | - | - | - | opens the selector |
| picture (ACTIVE, nothing open) | off | opens the awto menu | - | input info pop-up | - | opens the selector |
| awto menu | off | forwarded to the menu (enter) | forwarded (repeats) | forwarded (repeats) | forwarded (exit / back) | - |
| source selector | off | takes the choice | step to the next item, no repeat | step to the previous item, no repeat | cancels, the choice goes back | - |
| diagnostics, main page | closes the console, then off | - | - | - | closes the console | - |
| diagnostics, GPIO page (test cmd 0x43) | closes the console, then off | - | scrolls (repeats) | scrolls (repeats) | - | - |

- `-` = nothing happens. UP+DOWN toggles the console from every row except power saving (where it wakes only).
- Blank vs picture: AUTO opens the awto menu in ACTIVE, NO SIGNAL and NO SUPPORT; the DOWN pop-up needs ACTIVE.
- Only SOURCE opens the selector (UP on a blank screen no longer does).
- Selector: no OSD timeout; closes on a choice, a cancel or POWER. A choice that is a port without a cable is refused and the selector stays up (awto-ddc#84).
- Input info pop-up (DOWN): closes 6 s after it opened (`AWTO_INFO_POPUP_MS`), whatever keys are pressed meanwhile; DOWN while it is up does not reopen it. Opening another screen (SOURCE, AUTO) replaces it.
- Other OSD screens: the OSD timeout from the settings (`osd_timeout`) restarts on every key; a value of 10 s or less means no timeout.
- POWER always works: an open console closes first, then the monitor goes off / on.

## Injected keys

- Test cmd 0x01..0x05 (AUTO, UP, DOWN, MENU, SOURCE) and `key_inject` (settings library, `menu.h`) take the same route as a front key: the rows above apply unchanged (power saving: wake only; console pages as listed).
- `key_hold(mask, ms)` ORs a key mask into the reader samples: debounce, combo wait and repeat apply.
- Injected keys are logged in the key press log (`g_stAwtoKey`, `scripts/rtd_keywatch.py --log`) with the injected flag.

## Not on the keys (DDC/CI only)

- Debug link on / off: `scripts/dbg_link.py` (VCP 0xE3), test cmds 0x3B / 0x3C.
- Reset to defaults (factory reset): VCP 0x04.
