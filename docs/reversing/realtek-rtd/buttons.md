# JXC 4K monitor: front-panel button handling (static RE)

Tags: [fw] seen in firmware, [spec] datasheet/DB, [guess] inferred, [?] unknown.
Source: bank6 (flash 0x60000), decompile `~/vendors/realtek/analysis/jxc-4k/bank6/`. Names in `re/jxc-4k/ghidra_names_bank{6,0}.tsv`.
Bank 6 needed new seeds (0x3902-0x392c, 0x3944, 0x5f70, 0x6217, 0x5942, 0x5255); the earlier export had none of this code.

## 1. ADC reads
- Only one routine touches the ADC result regs: `key_scan_adc` CODE:3944 (bank6). Raw search of all 7 banks for `MOV DPTR,#0xff09..0xff0c`: hits only there, A0 + A1 only [fw]
- ADC_A2/A3 (0xFF0B/0xFF0C): never read by any bank [fw]. P4.1/P4.2 unused for keys (other analog use not found) [?]
- Result regs are 8-bit with data in bits 7:3 (5-bit ADC, low 3 bits 0) [spec: regdb `ADC_Ax_CONVERT_RESULT` reset 0xF8]
- Plus one digital key: SFR bit 0xB0 = P3.0 (RXD pin), pressed = low [fw]
- Settle: each channel is sampled, short delay (`0x07e3`, args 0,3), re-sampled; accepted when the two differ by < 5 counts (3ab6/3acc). Retry counter XDATA dbb2, reloaded to 3 (6666 dec / 6676 reload) [fw]

## 2. ADC to key decode (hard-coded immediates, no table)
Compares at CODE:39e9-3a60. Raw value R = register byte; band is `lo <= R < hi`. Mask bits accumulate in XDATA dbad.

Physical buttons, left to right: **SOURCE, MENU, DOWN, UP, AUTO, POWER** (6 keys) [user, 2026-11-04].
Settled 2026-11-08 [fw+hw]: hardware presses by Dan on unit 2, plus the Dahua firmware trace in #85.
Dahua code detail: `docs/reversing/dahua-fw/keys.md`.

| mask | source | raw band | 5-bit code (R>>3) | label |
|---|---|---|---|---|
| 0x01 | P3.0 low | n/a | n/a | POWER [fw+hw] |
| 0x02 | ADC_A0 | 0xC0..0xDF | 24..27 | MENU [fw+hw] |
| 0x04 | ADC_A0 | 0x28..0x47 | 5..8 | UP [fw+hw] |
| 0x08 | ADC_A1 | 0x28..0x47 | 5..8 | DOWN [fw+hw] |
| 0x10 | ADC_A0 | 0x70..0x8F | 14..17 | AUTO [fw+hw] (only key with a long-press timer, id 0xd) |
| 0x20 | ADC_A1 | 0x68..0x87 | 13..16 | SOURCE [fw+hw] |

- 6 distinct single keys: 1 digital (POWER) + 3 on A0 + 2 on A1 [fw]
- Idle (no key) = no band hit = R near 0xF8 (pull-up) [guess]
- Bands are 32 raw counts wide (4 codes) around nominal centres; centre voltage fraction of full-scale = R/256 [guess]; absolute volts depend on ADC ref, not checked [?]
- Combos: masks OR together (e.g. 0x18 = 0x10 + 0x08). Only 0x18 and 0x03 have special handling; others fall through to "no key" [fw]
- Labels settled above. Nothing in flash carries label text for keys [?].
- Debounce: new mask is accepted only when seen on 2 consecutive scans (`e205` compare); first sighting returns 0 [fw]. `e205` is not cleared on release, so re-pressing the same key is accepted on first scan [?]

## 3. Dispatch
- `key_poll` CODE:5f70: tick (skips if XDATA e207 != 0; forces e151 = 8 unless it is 7). Shifts e208 to e209 (prev), `key_scan_adc` returns mask into e208 [fw]
- `key_power_edge` CODE:5942: mask bit0 set in both cur/prev-xor (press edge) -> banked call `0x0f39` (arg 1 or 2 depending on `0x07a7` result) = power toggle; CY=1 stops further dispatch [guess on the toggle meaning]
- `key_event_dispatch` CODE:5255: switch on e208 [fw]:

| e208 | key event idx (R5) | extra |
|---|---|---|
| 0x02 | 0 | clears e152 bit3 |
| 0x04 | 1 | |
| 0x08 | 2 | |
| 0x10 | 3 | clears e152 bit3 |
| 0x18 | 3 | clears e152 bit3 |
| 0x20 | 4 | only if e14e/e14f (16-bit) == 0 |

- `key_post_event` CODE:5b45: new key -> `641e`; for 0x10/0x18 (AUTO) arms 3000-unit timer id 0xd (0x0BB8) and returns without posting [fw]. Nothing in banks 0-6 reads timer 0xd or acts on its expiry, so a held AUTO does nothing extra [fw, medium: a table-driven consumer is not excluded; see dahua-fw/keys.md]. Otherwise `e151 = idx`, then `6567` cancels timers 0xb/0xd/0xe [fw]
- Held key (no change): if e152 bit3 set, repeats e151 or arms timer id 1 with 0x01F4 (500 units, auto-repeat delay) [fw]. Timer time unit not determined [?]
- Consumer: `e151` (XDATA 0xE151, named `osd_key_event_idx`) is read in ~30 places in bank0 OSD code (0xA6ED-0xFE0B) as `switch(e151)` DEC chains with cases 1, 2, 3, 6 [fw]:
  - 1, 2 = value adjust (two direction keys): `fd66`, `fd87` (+ siblings fda8/fdc9/fdea/fe0b) call `ee33(n)`, `eee4`/`f184` change a value [guess]
  - 3 = AUTO: back (`fcfe`) with a menu open; no case with the OSD closed (handler `f97a`) [fw]
  - 6 = never produced by the scan path; the handler header comments say "6 -> c3ea" but the code tests 0 [fw, dahua-fw/keys.md]
  - idx 0 (MENU) with the OSD closed opens the main menu (`d439`); inside menus it is select/OK (`c3ea`) [fw, awto-ddc#85 trace]
  - idx 4 (SOURCE, only with the OSD closed: e14e/e14f is the 16-bit OSD state) builds the 3-row page at `dd7c` via `bcall_osd_builder_menu_source(2)`; its handler `e7b1` moves the cursor on 1/2 and confirms on 0 [fw]. That the page is the input list is [guess] (builder name, 3 rows, port set); a press of the original's SOURCE key would settle it
- Entry into the OSD state machine: OSD state table at bank0 `a047` sends state 0 to handler `f97a`; with the OSD closed e151==0 opens the main menu, e151==4 the source page, e151==1/2 are hotkeys (`e4dc`) [fw]. Unread bodies: `eee4`, `f184`, `e7b1` (MENU/AUTO branches), `fcfe`, `c3ea`, `e4dc` [?].
- `key_alt_source_poll` CODE:5154 is the IR key path (NEC, `ScalerIRHWModeInitial` at boot, pin 194 `irda_in`): the 8 bytes copied from code `0xFF:3067` are all zero (the SDK `pucIRCodeBuffer[8] = {0}` initialiser), not a code table; command 0xB9 = POWER, F1 opens the menu, A7 the input list [fw]; byte order of the received frame unverified, needs a remote: `dahua-fw/gpio-ir.md`, awto-ddc#93

## 4. Data-driven or hard-coded
- Thresholds: 5 pairs of immediates in code (`MOV A,#0x68/0xC0/0x28/0x70..`, `SUBB A,#0x88/0xE0/0x48/0x90`) at CODE:39e9-3a60 [fw]. Not a flash table.
- Key id to event idx: compare chain in `key_event_dispatch` [fw]. Not a table.
- Event to action: DEC-chain switches in bank0 [fw].
- Conclusion: hard-coded. The only config-data input found is DB.bin pin mux (ADC pins P3.7/P4.0 enabled as `a_adc0/a_adc1`, see db-bin-format.md section 8). To change key behaviour: patch code bytes (immediates at 39e9-3a60 for bands; operands in 5255 for idx mapping), or change pin/ADC config in DB.bin.
- Caveat: other banks may hold alternative scan code for other panel types; none found (no other ff09-ff0c refs) [fw].

## 5. Names added
- bank6: `key_scan_adc`, `adc_a0_settled_cmp`, `adc_a1_settled_cmp`, `key_poll`, `key_event_dispatch`, `key_post_event`, `key_power_edge`, `key_longpress_arm`, `key_cancel_timers`, `key_power_combo`, `key_alt_source_poll`, `key_scan_gate`; vars `osd_key_event_idx` (e151), `key_flags` (e152), `key_last_debounced` (e205), `key_cur` (e208), `key_prev` (e209)
- bank0: `osd_key_event_idx`, `osd_keyevt_handler_*` (fd66, fd87, eee4, f184, f97a)
- Scratch XDATA dbad-dbb3 deliberately unnamed: shared scratch (dbae is `ddcci_cmd_byte` in bank5)
- Seeds appended: `seeds_bank6.txt` (6 entries), `seeds_bank0.txt` (26 heuristic function starts from e151 xrefs)
