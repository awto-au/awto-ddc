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

Physical buttons, left-to-right per Dan (2026-11-04): **SOURCE, MENU, DOWN, UP, AUTO, POWER** (6 keys) [user].
POWER = the digital P3.0 key [fw+user]. The other 5 are the A0/A1 ADC bands below. The exact band->label
pairing is still to be confirmed by pressing each key and reading 0xFF09/0xFF0A (see confirm note); the
`[user-pending]` tags are my best mapping from dispatch order, not yet hardware-verified.

| mask | source | raw band | 5-bit code (R>>3) | label |
|---|---|---|---|---|
| 0x01 | P3.0 low | n/a | n/a | POWER [fw+user] |
| 0x02 | ADC_A0 | 0xC0..0xDF | 24..27 | [user-pending] — top of A0 ladder; likely SOURCE or AUTO |
| 0x04 | ADC_A0 | 0x28..0x47 | 5..8 | [user-pending] DOWN (adjust-) |
| 0x08 | ADC_A1 | 0x28..0x47 | 5..8 | [user-pending] UP (adjust+) |
| 0x10 | ADC_A0 | 0x70..0x8F | 14..17 | [user-pending] MENU (only key with long-press timer) |
| 0x20 | ADC_A1 | 0x68..0x87 | 13..16 | [user-pending] SOURCE or AUTO |

- 6 distinct single keys: 1 digital (POWER) + 3 on A0 + 2 on A1 [fw]
- Dan's order is SOURCE,MENU,DOWN,UP,AUTO,POWER. 5 analog keys for {SOURCE,MENU,DOWN,UP,AUTO}: MENU is almost
  certainly 0x10 (sole long-press key); DOWN/UP are the symmetric adjust pair 0x04/0x08; that leaves SOURCE
  and AUTO as 0x02 and 0x20 (order unconfirmed). Confirm by press-test. [guess+user]
- Idle (no key) = no band hit = R near 0xF8 (pull-up) [guess]
- Bands are 32 raw counts wide (4 codes) around nominal centres; centre voltage fraction of full-scale = R/256 [guess]; absolute volts depend on ADC ref, not checked [?]
- Combos: masks OR together (e.g. 0x18 = 0x10 + 0x08). Only 0x18 and 0x03 have special handling; others fall through to "no key" [fw]
- Labels are inferred from behaviour only (long press, gating, OSD handler cases). Nothing in flash carries label text for keys [?]. Confirm on hardware by pressing each key and reading `0xFF09/0xFF0A` + P3.0.
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

- `key_post_event` CODE:5b45: new key -> `641e`; for 0x10/0x18 arms 3000-unit timer id 0xd (long press, 0x0BB8) and returns without posting [fw]. Otherwise `e151 = idx`, then `6567` cancels timers 0xb/0xd/0xe [fw]
- Held key (no change): if e152 bit3 set, repeats e151 or arms timer id 1 with 0x01F4 (500 units, auto-repeat delay) [fw]. Timer time unit not determined [?]
- Consumer: `e151` (XDATA 0xE151, named `osd_key_event_idx`) is read in ~30 places in bank0 OSD code (0xA6ED-0xFE0B) as `switch(e151)` DEC chains with cases 1, 2, 3, 6 [fw]:
  - 1, 2 = value adjust (two direction keys): `fd66`, `fd87` (+ siblings fda8/fdc9/fdea/fe0b) call `ee33(n)`, `eee4`/`f184` change a value [guess]
  - 3 = select/enter or back: `fcfe` [guess]
  - 6 = other event (`c3ea`); not produced by the scan path, so it comes from the long-press timer (id 0xd) or OSD logic [?]
  - idx 0 and 4 are consumed by different code (bank0 ~0xC3EA-0xC5xx: `e151 == 0` test) [?]
- Entry into OSD/menu state machine: not isolated. Candidates: idx 3 (MENU/ENTER key, 0x10) via `fcfe`/`c3ea` in bank0; `0dc5` banked call (called from `63fe`, `eee4`) [?]. Needs a proper bank0 decompile: the OSD region 0xA000-0xFFFF in bank0 is only partially disassembled (seeded from e151 xrefs, function starts are heuristic).
- `key_alt_source_poll` CODE:5154 runs when no ADC/P3.0 key is down: copies 8 bytes from code `0xFF:3067` into dbb4, calls 57f3, returns dbbe; result can set a key mask via `68a7`. Possibly the VCP 0xCA "OSD button control" injection path (bank5 case_vcp_ca_osd_button_ctrl -> bank0 0x0db9) [?]

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
