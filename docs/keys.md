# Front keys

Code: `fw/keys/keys.c` (`AwtoKeyPoll` debounce / combo / repeat, `AwtoKeyRoute` the one dispatcher), reader `fw/input/inputs.c`,
selector + backlight bar `fw/osd/console.c`, menu `awto-rtdfw awto/settings/menu.c`.
Decisions: awto-ddc#132 (Dan, 2026-11-12). Key names are the printed ones, left to right: SOURCE, MENU, DOWN, UP, AUTO, POWER.

## Reader

- Source: ADC ladders A0 (MENU, UP, AUTO) and A1 (SOURCE, DOWN) + P3.0 (POWER); bands in `fw/awto/inputs.tsv` (also read by `scripts/rtd_keywatch.py`).
- Debounce: two equal samples 10 ms apart (`AWTO_KEY_SAMPLE_MS`).
- Repeat: first at 500 ms, then every 100 ms (`AWTO_KEY_REPEAT_MS`, `AWTO_KEY_RATE_MS`).
- Combo wait: UP and DOWN hold their press 80 ms for the other one (`AWTO_KEY_COMBO_MS`); a lone UP / DOWN then acts. Every other key acts at once.
- With POWER held nothing else counts. Several keys that are not UP+DOWN: the first key down acts, the rest is ignored until all are up.
- No HOLD event, no MENU+DOWN combo, no key at power-on.

## Combos

| combo | action |
|---|---|
| UP+DOWN | diagnostic console on / off (toggle); in power saving: wake, then the console opens |

No other combo. Removed (#132): MENU+DOWN (debug link toggle), MENU+DOWN held at power-on (defaults + debug link), HOLD at 3 s.

## Per screen

| screen | POWER | AUTO | UP | DOWN | MENU | SOURCE |
|---|---|---|---|---|---|---|
| off | on | - | - | - | - | - |
| power saving | wakes only | wakes only | wakes only | wakes only | wakes only | wakes only |
| nothing open, no signal / no support | off | auto source select | - | - | opens the awto menu | opens the selector |
| nothing open, picture (ACTIVE) | off | auto source select | backlight bar, +1 % (repeats) | backlight bar, -1 % (repeats) | opens the awto menu | opens the selector |
| backlight bar | off | bar closes, auto source select | +1 % (repeats) | -1 % (repeats) | bar closes, menu opens | bar closes, selector opens |
| awto menu | off | enter / edit / confirm | move / more (repeats) | move / less (repeats) | back / revert, closes at the top | closes the menu (any page) |
| source selector | off | takes the highlighted input now | next item | previous item | cancel (input unchanged) | next item (wraps) |
| diagnostics, main page | closes the console, then off | - | - | - | closes the console | - |
| diagnostics, GPIO page (test cmd 0x43) | closes the console, then off | - | scrolls (repeats) | scrolls (repeats) | - | - |

- `-` = nothing happens. UP+DOWN toggles the console from every row; in power saving it wakes and opens it (whatever `sync_console` says).
- Other modes (INITIAL, SEARCH, DISPLAY SETTING): AUTO / MENU / UP / DOWN do nothing; SOURCE opens the selector.
- Auto source select (AUTO): the selector's Auto row (`AwtoSourceAuto`): scan type auto, search again through `SysMachineRequest` (request line "requested by AUTO key: auto source select"); the SDK auto search takes the first input with a signal and the mode lines name it. The scan type is stored at the NVRAM gate with "Saving to memory".
- Backlight bar: registry row `brightness` (Backlight, 0..100 %), step `AWTO_BL_KEY_STEP` per press / repeat, applied live. Closes on the OSD timeout (`osd_timeout`; 10 s or less = never) or on another key. Stored by the NVRAM gate like a menu change: written `AWTO_NV_SAVE_MS` after the last change; still dirty at the close = "Saving to memory".
- Input info pop-up on DOWN: removed (#132). Input details: menu Information page.
- awto menu: inert rows (registry flag `inert`) are dimmed with `*` after the label and cannot be changed from the menu (AUTO does nothing; status line "* not active: stored only"); DDC/CI still stores them. SOURCE closes with the save rule of `menu_close` ("Saving to memory" if something changed).
- Selector:
  - The highlighted input is taken after `AWTO_SRC_IDLE_COMMIT_MS` (2 s) with no key; every step (SOURCE / UP / DOWN) restarts the wait. AUTO takes it at once. Request line: "requested by input selector" (AUTO) or "input selector: no key for 2 s (idle commit)".
  - Opening it arms no idle commit: it stays until a step, AUTO, MENU or POWER (no OSD timeout, #139). No picture: the 60 s sleep rule (`AWTO_SRC_SLEEP_SEC`).
  - Highlight on a port without a cable: the commit (idle or AUTO) is refused (#84, dead-port line in the sync log); the selector stays open with the highlight on that row (state column "no cable").
  - Highlight on the current input: the commit only closes it.
- Other OSD screens: the OSD timeout restarts on every key.
- POWER always works: an open console closes first, then the monitor goes off / on.

## Stock behaviour (for comparison)

| key | Realtek SDK demo (RTD2014, this board's band to mask mapping) | Dahua firmware (`docs/reversing/dahua-fw/keys.md`) |
|---|---|---|
| MENU | Menu role: opens the menu (ACTIVE only), enter / adjust / keep | opens the main menu; in it: select / enter (c3ea) |
| AUTO | Exit role: nothing with the OSD off (after the #85 exit-role patch); back / revert / close | nothing with the OSD off; in it: back (fcfe); 3 s long-press timer without a consumer |
| UP | Right: source hot menu; next / +1 (repeat 0.5 s) | hotkey slot e06c (function not read); in it: move |
| DOWN | Left: input info, held 3 s DP version; previous / -1 (repeat) | hotkey slot e06b (function not read); in it: move |
| SOURCE | not used | input list page (OSD closed only; dropped with the OSD open) |
| POWER | on / off | on / off |

## Injected keys

- Test cmd 0x01..0x05 (AUTO, UP, DOWN, MENU, SOURCE) and `key_inject` (settings library, `menu.h`) take the same route as a front key: the rows above apply.
- `key_hold(mask, ms)` ORs a key mask into the reader samples: debounce, combo wait and repeat apply.
- Injected keys are logged in the key press log (`g_stAwtoKey`, `scripts/rtd_keywatch.py --log`) with the injected flag.

## Not on the keys (DDC/CI only)

- Debug link on / off: `scripts/dbg_link.py` (VCP 0xE3), test cmds 0x3B / 0x3C.
- Reset to defaults: VCP 0x04.
