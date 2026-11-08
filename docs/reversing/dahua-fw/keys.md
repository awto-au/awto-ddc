# Dahua firmware: front-panel keys (static RE)

Original Dahua firmware, not our build. Tags: [fw] read in decompile or disassembly; [guess] inference (settle-test given); [?] unknown.

## Sources
- Decompile + disassembly: `/mnt/2tb/vendors/realtek/analysis/jxc-4k/bank{0,6}/`. Bank 1 and bank 5 decompiles read for the timer code.
- Raw bank bytes (read-only): `/mnt/2tb/vendors/realtek/analysis/banks/bank0.bin`.
- Key masks and band mapping: `docs/reversing/realtek-rtd/buttons.md` section 2, issue awto-au/awto-ddc#85.

## Names
- XDATA e151 = `g_stOsdInfo.ucOsdKeyMessage` (event idx written by key_post_event). Name in bank0 TSV: `osd_key_event_idx`.
- XDATA e152 = `ucOsdKeyControl` (key flags): bit1 scan start, bit2 repeat start, bit3 repeat enable, bit4 long-press armed.
- XDATA e14e:e14f = `usOsdState`: e14e low byte = state index into the table at 0xA047, e14f = page. OSD closed = whole 16-bit value 0 [fw, disasm 5298-52A4].
- XDATA e208 = key_cur, e209 = key_prev.
- Timers: `bcall_ScalerTimerActiveTimerEvent(id, hi, lo)`, value = hi<<8|lo, bank 5 0xD930.

## 1a. Key event table (key_event_dispatch 0x5255 -> key_post_event 0x5B45)

| key (mask, idx) | press (key-down) | held | release |
|---|---|---|---|
| MENU (0x02, 0) | posts e151=0 [fw 0x527A]; calls 0x666E (clears e152 bit3) | no post (bit3 clear) [fw] | clear e152 bits 2,3; cancel timer 1 [fw 0x52B6] |
| UP (0x04, 1) | posts e151=1 [fw 0x5283] | if bit3 set and bit2 clear: arm timer 1 = 500 every pass [fw 0x5B7D]; bit2 path re-posts (dead, see 3) | as MENU |
| DOWN (0x08, 2) | posts e151=2 [fw 0x5289] | as UP | as MENU |
| AUTO (0x10, 3) | arms timer 0xD = 3000, sets e152 bit4, returns with CY=1: NO post [fw 0x641E, 0x6430] | nothing (see 2) | if bit4 still set: e151=3 [fw 0x5D67], then key_cancel_timers 0x6567 |
| AUTO+DOWN (0x18, 3) | same as AUTO press: arm, no post [fw] | nothing | prev 0x18 not matched in 0x5D4B: no post [fw] |
| SOURCE (0x20, 4) | posts e151=4 only if usOsdState == 0; otherwise dropped, no other effect [fw 0x5298-0x52A4] | nothing | nothing (no clear of bits 2,3) [fw] |
| POWER (0x01) | no e151 event; handled in key_power_edge (see 1d) [fw] | | |
| 0x00 or unmatched mask | falls to 0x52B6: clear bits 2,3, cancel timer 1 [fw] | | |

- e151 is also written by bank0 `osd_keycode_to_event_idx` 0xC6B1 (16-bit keycode -> 0..3; 0xF1/0x0E -> 0, 0xA7/0x58 -> dd7c page). Source of those keycodes not traced [?]. So an e151 value alone does not prove the front panel.

## 1b. OSD closed (usOsdState == 0): state handler f97a 0xF97A
- Table 0xA047, 3 bytes per state: `FF hi lo`, handler = bytes 1..2 big-endian. State 0 = 0xF97A [fw raw bytes].
- Dispatcher bank0 e1d5 (0xE1D5, ICALL in decompile 13275). Handler runs only when the event arg is 3 [fw 13227]. Event arg at callers d9da/d9df (bank0 12282, 12303; disasm d9ed) not traced [?].
- f97a acts only when event == 3 [fw 15473-15507]:
  - e151 0 (MENU): if e067 bit0 -> bcall_b1_4b00(); else osd_page_build_main_menu 0xD439 [fw].
  - e151 1 (UP): e4dc(*e06c) [fw]. e06c as hotkey slot: [guess], settle by reading e4dc.
  - e151 2 (DOWN): e4dc(*e06b) [fw]. Same as UP, other slot [guess].
  - e151 3 (AUTO): no case, no action [fw].
  - e151 4 (SOURCE): fcfe(); osd_page_build_dd7c 0xDD7C [fw]. Page = 3-row input list: [guess] from builder name, 3 rows, and dd7c's handler 0xE7B1 writing ucOsdEventMsg 0x0B on confirm (decompile of 0xE7B1 partial).
  - e151 6: no case [fw].

## 1c. OSD open (usOsdState != 0): handler from table, by state
- States 1..6 = main menu items, handlers fd66, fd87, fda8, fdc9, fdea, fe0b [fw table]. Each handler: UP and DOWN move the cursor by osd_main_menu_select_item(n), MENU -> c3ea(), AUTO -> fcfe(), SOURCE: no case, and the gate in 1a drops it [fw].
  - fd66 (state 1): UP -> item 6, DOWN -> item 2 [fw 16054-16070].
  - fd87 (state 2): UP -> 1, DOWN -> 3 [fw].
  - fda8 (state 3): UP -> 2, DOWN -> 4 [fw, header].
  - fdc9 (state 4): UP -> 3, DOWN -> 5 [fw, header].
  - fdea (state 5): UP -> 4, DOWN -> 6 [fw, header].
  - fe0b (state 6): UP -> 5, DOWN -> 1 [fw, header].
  - Meaning of osd_main_menu_select_item and c3ea (MENU = select/enter): [guess] from name and wiring. Settle: read both.
  - Decompile headers of fd66..fe0b say "6 -> c3ea". The code tests 0 for c3ea, not 6. The header is stale [fw].
- States 0x51 f184, 0x52 e7b1, 0x53 eee4 = value pages [fw table]:
  - e7b1: UP/DOWN: _0_2=1, value e060 scaled and clamped by f4c3, then bcall_b6_561e(0,10) [fw]. MENU and AUTO branches: partly read [?].
  - eee4: UP/DOWN: branch on bf_b1OsdLogo (1, 2, 3) [fw]. AUTO (3): ef8a(), ef5e(0xD) [fw], e150 = 0x10 per old header [?] (not read in code).
  - f184: UP/DOWN value change and AUTO -> fcfe per header. Body not read [?].
- Other states: 7..42 (0x07-0x2A) -> c3ea; 43..64 and 68..78 -> fd23; 65..67 and 79 -> fa f6; 80 -> f53c. Not read [?].

## 1d. POWER (P3.0, mask 0x01): key_power_edge 0x5942 (decompile 8061)
- Press edge only (bit0 set and changed) [fw].
- Calls key_power_combo (cur 0x03, 0x18, 0x14: e067 |= 3, bcall_b3_f2b3) [fw].
- cur == 0x01: clear usOsdState, clear bf_b3OsdsixColor bit1, FUN_0F39(2) [fw]. Other cur with bit0: FUN_0F39(1) [fw]. Meaning of 0F39 (power on/off) [?].

## 2. Long press (AUTO, timer id 0xD)
- Arm: 0x641E calls bcall_ScalerTimerActiveTimerEvent(0xD, 0x0B, 0xB8) = 0x0BB8 = 3000 [fw].
- Expiry consumer: none found [fw search]. Id 0xD appears only in bank6 at 0x641E (arm) and 0x6567 (cancel). Not in banks 0-5 (arm/cancel/wait forms).
- Expiry does not clear bit4. Only key_cancel_timers (0x6567) clears it, called from release (RTDKeyHoldKeyCheck 0x5D4B) and other-key posts. So release posts e151=3 after any hold length [fw].
- Net effect of holding AUTO in code found: none beyond the release message 3 [fw]. With OSD closed, 3 has no case in f97a. With OSD open, 3 -> fcfe() (back) in the main-menu handlers [fw].
- Event 6: no writer in banks 0-6. Writes of e151 are idx 0..4 (key path), 0..3 (keycode path), 8 (key_poll idle marker), 7 read as marker [fw]. Readers of 6 in f97a and fd66 family: none [fw].
- Timer tick: SysTimerIntProc2 (Timer2 overflow ISR, present in every bank) increments DAT_INTMEM_47:48 16-bit counter [fw]. It also calls bank1 0xE1C0 (PORT42 bit-bang, not a timer dispatcher) [fw].
- Timer table: 18 entries at g_pucDdcciData+0x12, Active 0xD930 / Check 0xC79C in bank 5. Expiry is lazy: no per-id callback found [fw].
- Tick period: [guess] 1 ms, from ScalerTimerDelayXms note in `re/jxc-4k/ghidra_names_bank5.tsv` (re-agent name, not checked). Settle: decode the Timer2 reload (bank5 decompile lines 18211-18214 load TL2/TH2/RCAP2 from DAT_dbb1..4; source of those values not traced) and the clock divider, or count DAT_INTMEM_47:48 over 1 s on unit 2.

## 3. Repeat (timer id 1 = 500)
- Arm: key_post_event 0x5B7D: held key, e152 bit3 set, bit2 clear -> bcall_ScalerTimerActiveTimerEvent(1, 1, 0xF4) = 500 [fw].
- bit3 set: only in bank0 e1d5 LAB_E24A (decompile 13239-13240) when e151 is 1 or 2 (UP/DOWN) [fw]. Condition to reach it: [?].
- bit3 clear: 0x666E (MENU, AUTO, AUTO+DOWN press) and release (0x52B6) [fw].
- bit2: never set in banks 0-6 (direct-address grep of e152 in all bank disasm: only clears, 0x52B6, 0x7169/7189 `&0xF3`). Indirect @Rn writes not searched [?]. So the re-post branch (0x5B74) is not reached by any path found [fw].
- Timer 1 expiry consumer: none in banks 0 or 6 (only arm and cancel). WaitForEvent(1) calls in banks 1, 2, 5 are a different API (hardware event flags, bank5 0xD20D) [fw]. So the code found does not auto-repeat [fw]; whether any other code consumes timer 1 [?].
- Keys that can repeat: UP (0x04) and DOWN (0x08) only, and only when bit3 is set [fw]. MENU, AUTO, SOURCE, POWER never post on hold. SOURCE and POWER do not clear bit3 on press, so a leftover bit3 can arm timer 1 for them too. No effect found because bit2 is never set [fw].

## Not settled
- Timer 0xD expiry: no consumer found. Settle: find the table scan that compares DAT_47:48 against stored deadlines (bank5, 0xD930 area), or hold AUTO 5 s on unit 2 with `rtd_keywatch.py` and see if a second message appears.
- Tick period (1 ms guess above).
- Repeat re-post: bit2 never set, timer 1 has no consumer. Settle: same scan as above, or a held UP on unit 2 in a value-adjust page.
- Unread handler bodies: eee4, f184, e7b1 (MENU/AUTO), fcfe, c3ea, osd_main_menu_select_item, e4dc. Event arg at e1d5 callers.
