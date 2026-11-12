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
  - e151 1 (UP): e4dc(*e06c) [fw]: opens the value page of the OSD item whose id is stored in e06c, default 0x47 = volume (section 4).
  - e151 2 (DOWN): e4dc(*e06b) [fw]: same with e06b, default 0x2B = brightness (section 4).
  - e151 3 (AUTO): no case, no action [fw].
  - e151 4 (SOURCE): fcfe(); osd_page_build_dd7c 0xDD7C [fw]. Page = 3-row input list, state 0x52, handler e7b1: `source-select.md`.
  - e151 6: no case [fw].

## 1c. OSD open (usOsdState != 0): handler from table, by state
- States 1..6 = main menu items, handlers fd66, fd87, fda8, fdc9, fdea, fe0b [fw table]. Each handler: UP and DOWN move the cursor by osd_main_menu_select_item(n), MENU -> c3ea(), AUTO -> fcfe(), SOURCE: no case, and the gate in 1a drops it [fw].
  - fd66 (state 1): UP -> item 6, DOWN -> item 2 [fw 16054-16070].
  - fd87 (state 2): UP -> 1, DOWN -> 3 [fw].
  - fda8 (state 3): UP -> 2, DOWN -> 4 [fw, header].
  - fdc9 (state 4): UP -> 3, DOWN -> 5 [fw, header].
  - fdea (state 5): UP -> 4, DOWN -> 6 [fw, header].
  - fe0b (state 6): UP -> 5, DOWN -> 1 [fw, header].
  - osd_main_menu_select_item (ee33, arg N = 1..6): sets `dbae` = N, `usOsdState` = N, `e13e` = N-1 (highlighted row), redraws the 6 rows (loop `dbaf` < 6; row item id from table, 0x4F = empty row) [fw, section 4].
  - c3ea (MENU on a main-menu row): first 0xA0 bytes read; stores current item `e14b` in `dbad`, steps a 6-row counter `dbae` (event 2 advances with wrap at 5, event 1 goes back), for states 7..0x2A with e151 = 0 calls the getter `d9f8(item)` and `a62d`; remaining body (c4a0..c579 and tail) not read [?].
  - Decompile headers of fd66..fe0b say "6 -> c3ea". The code tests 0 for c3ea, not 6. The header is stale [fw].
- States 0x51 f184, 0x52 e7b1, 0x53 eee4 = value pages [fw table]:
  - e7b1 = SOURCE list page (state 0x52): fully read, `source-select.md`.
  - eee4 = single-item value page (state 0x53) opened by `e4dc`: fully read, section 4.
  - f184 (state 0x51): UP/DOWN -> `f62c` with wrap (bit3 set), range 0..5, result stored in `e068` bits 2:0, then the row text for value 0..4 is picked from a 5-way chain (text pointers 0x9E DF, 9F 15, 9F 4B, 9F 81, 9F B7; value 5 and 0 fall to the first); MENU (0) and AUTO (3) -> `fcfe()` (close); SOURCE and 6: ignored [fw]. What `e068[2:0]` is: [?].
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
- Still unread: c3ea tail (section 1c), what `e068[2:0]` (f184) is, the state-43..80 handlers fd23 / faf6 / f53c, event arg at e1d5 callers. Read since the first pass: eee4, f184, e7b1, fcfe, e4dc, ee33 (sections 1c, 4).

## 4. UP / DOWN hot keys and the value page (#41 step 2, 2026-11-12)
Evidence: bank 0 disassembly of `f97a`, `e4dc`, `eee4`, `b0a0`, `f62c`, `d9f8`, `f21e`, `fcfe` (`scripts/dis51.py` on `banks/bank0.bin`), default block bank 3 `a76c` (copied to XDATA e050 by bank 3 `d149`, length 0x1E), apply calls in bank 1 / bank 5. Names: `re/jxc-4k/names_re1.tsv`.

### 4a. Slots e06b / e06c
- e06b / e06c are persistent bytes of the user block XDATA e050..e06d. The block is initialised by copying 30 bytes from bank 3 code `a76c` (`d149`: dest e050, src a76c, R7 = 0x1E). Bytes at that offset: e06b = 0x2B, e06c = 0x47, e06d = 0x02. [fw]
- Content = an OSD item id, not a function code: `f97a` passes `*e06c` (UP) or `*e06b` (DOWN) as the id to `e4dc`. [fw]
- Writers by constant address: only `f21e` (save both to `dbb9`/`dbba`, run a reload `1029(0)`, restore both: survive the reload) and the reads at `f9ac` / `f9b7`. No menu setter: `b0a0` (value setter) has no case for ids 0x4D / 0x4E, `d9f8` getters exist (0x4D -> e06b, 0x4E -> e06c). So the assignment is not user-editable in code found; indirect writes (block load from NVRAM) are not excluded. [fw]
- Defaults therefore: UP = id 0x47, DOWN = id 0x2B.

### 4b. Item ids (those named by evidence)
Getter table `d9f8` (keil switch at 0:d9fc, 36 cases, id 0x2B..0x4E) and setter table `b0a0` (0:b12a, 13 cases: 0x2B 0x2C 0x2D 0x2E 0x39 0x3A 0x3B 0x3D 0x3E 0x3F 0x40 0x45 0x47).

| id | XDATA | default | what | evidence |
|---|---|---|---|---|
| 0x2B | e050 | 0x50 (80) | brightness, 0..100 | `b0a0` case writes e050 then calls `0de9` = bank 5 `d04a` = `backlight_pwm4_set_level`; same chain applies e050 at boot and after splash (`0:d99c` passes 0x64) [fw] |
| 0x47 | e05e | 0x32 (50) | volume, 0..100; 0 sets e05d bit3 (mute), non-zero clears it | `b0a0` case at 0:b31a: e05e then `0e6d` -> bank 5 `f6cc` -> bank 3 `fcdb` = `ScalerAudioDigitalAdjustVolume` (name [re-agent] high); mute bit then `0e73` [fw]; "volume" [fw+x] by the chain and the default 50 |
| 0x3D / 0x3E | e051 / e052 | 0x32 / 0x32 | [guess] OSD H / V position | defaults 50 / 50 equal the SDK `ucOsdHPos` / `ucOsdVPos` defaults. Settle: draw the menu and change e051 |
| 0x3F | e053 | 0x0A | OSD timeout in seconds | `a636`: R6:R7 = e053, x 1000 (`0x03E8`), timer id 8 (R5 = 8) [fw] |
| 0x40 | e054 | 0x00 | [guess] OSD transparency | applied through `0e13` in the apply-all routine (1:9b20); SDK default 0 |
| 0x44 | e060 | 0 | SOURCE page cursor row, 0..2 | `source-select.md` [fw] |
| 0x4D / 0x4E | e06b / e06c | 0x2B / 0x47 | the hot-key slots themselves | section 4a [fw] |
| 0x2C, 0x2D, 0x2E, 0x39..0x3B, 0x45, 0x46 | e07b, e07a, e056 hi, ... | | not named | setters exist (`b0a0`), apply calls `0e25` (bank 5 b3cf), `0e1f`. [?] Settle: render the pages with the sim or read the item name strings (text table not decoded) |

- IR direct keys (gpio-ir.md 6.3): B7 / B2 -> `e4dc(0x2B)` = brightness page, B6 / B1 -> `e4dc(0x47)` = volume page. Same two ids as the front-key defaults. [fw]

### 4c. What `e4dc(id)` does (0xE4DC)
- `dbad` = id. id < 0x50: draws the page (`f862(id + 0xB0)` title, `f924`, `e6cb`), type from `f2b3(id)` (3-byte LJMP table at 0:f2cc indexed by id - 0x2B: type 1 = bar, 2 = option list, 3 = special (id 0x3C only), 0 = none (0x41-0x43); bars are 0x2B-0x2E, 0x33-0x36, 0x39-0x3B, 0x3D-0x40, 0x45, 0x47; option lists 0x2F-0x32, 0x37, 0x38, 0x44, 0x46, 0x48-0x4E), current value from `d9f8(id)`, `e14b` = id (0xFF for some types), sets `usOsdState` (e14e) = 0x53 = `eee4`, then arms the OSD timeout: `a636` (e053 x 1000 ms, timer id 8) and `0597` = `ScalerTimerReactiveTimerEvent`. [fw]
- id >= 0x50: `usOsdState` = id directly (jumps to the state table), no value page. [fw]

### 4d. Value page `eee4` (state 0x53), keys [fw]
- UP (e151 = 1): item value +1. DOWN (2): -1. Both go to the same code at `ef05`; `f2b3(e14b)` selects the type. Type 1 (plain bar): getter `d9f8`, then `b0a0(R7 = 4, R3 = value, R5 = id)`, whose per-id case computes the new value with `f62c`: `e151` = 1 -> +1, `e151` = 2 -> -1, range min 0 / max 0x64, wrap flag `bit03` cleared = clamp at both ends, step 1 per event. Then the setter stores to the item byte and calls the apply routine at once (brightness: PWM, volume: audio DVC). No separate commit key. [fw]
- Type 2 (option list, `ef32`: caption from e055 low nibble) and type 3 (`ef4a`): different draw routines, not read further [?]. Brightness (0x2B) and volume (0x47) are type 1.
- MENU (0) and AUTO (3): `ea4d` (per-id exit work, ids 0x3C and a few others have extra save steps), `fcfe()` (close OSD: `usOsdState` = 0, e14c bit1 cleared, `0855(0x20)`, `0fed`, `0ff3(0x1A)`, e1ea = e1e5 = 0), `0dc5` (bank 3 `f2b3`, call not read), `e150` = 0x10. [fw]
- SOURCE (4): dropped by the key gate while the OSD is open (section 1a) and `eee4` has no case. [fw]
- Auto-repeat: none (section 3), so each press is one +1 / -1 step; 0..100 takes 100 presses. [fw]
- OSD timeout: timer id 8 is armed here with e053 seconds; the expiry consumer is not found (same gap as timers 1 and 0xD, section 3). Whether the value page closes by itself: [?]. Settle: unit 2, open the volume page and wait e053 s (default 10 s) with `rtd_keywatch.py` logging.

### 4e. For our firmware
- UP with OSD closed = volume page, DOWN = brightness page, both ids user-fixed. Pressing UP/DOWN inside the page changes the value by 1 immediately, clamped 0..100. MENU / AUTO close. SOURCE ignored. No repeat.
- Mute: volume 0 sets the mute bit, any non-zero volume clears it.
- Not yet done (no unit access in this pass): confirm on unit 1 that UP opens the volume bar and DOWN the brightness bar (expected from sections 4a-4c; [fw] only). Settle: press UP, DOWN on the original firmware, photo.

### 4f. Reset behaviour
- `f21e` (reached from a reset-all style action, caller not traced [?]) saves e06b / e06c, runs `1029(0)`, `0f9f(3)`, `fcfe`, ..., restores both, clears e067 bits 0-1. [fw] Meaning "factory reset keeps hot keys": [guess], settle by reading `1029`.
