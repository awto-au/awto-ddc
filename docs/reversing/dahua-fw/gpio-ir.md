# Dahua firmware: GPIO groups, power LED, IR path

Original Dahua firmware of the JXC 27" 4K monitor (RTD2795T / RL6449, DW8051, Keil C51, 7 banks). Not our build. Tracking: #93, #41, #91 (labels in `ghidra_names_*.tsv` are not facts).
Tags: [fw] read in code; [fw+x] code structure matches SDK source (named below), so the function role is known; [hw] live read; [spec] SDK / register DB; [guess] says what settles it; [?] unknown.
Evidence: `/mnt/2tb/vendors/realtek/analysis/jxc-4k/bank*/{disassembly.asm,decompiled_named.c}`, raw banks `.../analysis/banks/bank{0..6}.bin`, SDK `/mnt/2tb/git/awto-ddc-keys/tmp/sdcc-port/src`. Names: `re/jxc-4k/names_gpio_ir.tsv`. Pin table: `re/jxc-4k/gpio_audit.tsv` (`scripts/dahua_gpio_audit.py`).

## 1. Method: the power / LED / audio layer is the SDK user layer
- Power action numbers passed to `8aa1` (1:8aa1, 14-case jump table at 1:8ab5) = SDK `EnumPowerAction` 0..13 in SDK order (`Kernel/Common/Global.h:3045`): 0 OFF_TO_NORMAL, 1 OFF_TO_FAKE_OFF, 2 AC_ON_TO_NORMAL, 3 AC_ON_TO_OFF, 4 AC_ON_INITIAL, 5 PS_TO_NORMAL, 6 PS_TO_OFF, 7 NORMAL_TO_PS, 8 NORMAL_TO_OFF, 9 NORMAL_TO_FAKE_OFF, 10 SWITCH_INTERFACE_TO_OFF, 11 NORMAL_TO_FAKE_PS, 12 FAKE_PS_TO_NORMAL, 13 FAKE_OFF_TO_NORMAL. `8aa1` = `SysPowerSwitch`. The caller `SysPowerHandler` (1:a587) picks the number from e23a (target / current power status, SDK `EnumPowerStatus`). [fw+x]
- `d3ac` (1:d3ac) = SDK `UserInterfacePowerSwitch` (`User/None Series/NoneFunction/Code/NoneUserInterface.c:1331`): per action it sets the LED (`d6b2`), calls the panel-down routine `917c(1)` and stores `_MONITOR_POWER_STATUS` (`cd09` + `fe09` = NVRAM set + save). Case-by-case match of all six handled actions. [fw+x]
- `d6b2` (1:d6b2) = SDK `UserInterfaceKeyPadLedControl`: 14-case switch on `EnumLedIndication` 0..13 (`Global.h:1229`). [fw+x]
- `ea99` (1:ea99) = SDK `UserInterfaceAdjustAudioAmpMuteProc(bit)`, `f69b` (1:f69b) = `UserInterfaceGetAudioDACOutput`. [fw+x]
- `5d88` (6:5d88) = SDK `ScalerPinshareConfig(power status)`, which runs the board macros `PCB_GPIO_SETTING_POWER_NORMAL / _SAVING / _DOWN`. [fw+x]
- Bank 0 `d8c4` = the OSD system flow (SDK `NoneOsdSystemFlow`: `switch(SysModeGetModeState())`, LED calls on mode-state change). [fw+x]

## 2. P3.5 / P3.6 (pins 91 / 92): two-output power indicator
- Pin-share mode 1 = GPIO push-pull on the live unit [hw: `docs/monitors/pinshare-live-AWT26110003.tsv`]; the regdb label `DPTX_AUX_P/N` is the reference-board function and is not used here. [spec]
- Accessed as SFR bits `T1` (0xB5 = P3.5) and `WR` (0xB6 = P3.6). Writers: only `d6b2` (1:d6f1-d703) and the AC-on init (5:d311 `SETB P3.5`, 5:d313 `CLR P3.6`). No read of either bit. Raw byte scan of all banks for 0xB5/0xB6 bit ops and `P3` byte ops: no other real site. [fw]
- LED index (argument of `d6b2`, SDK `EnumLedIndication`) -> pins:

| index | SDK name | (P3.5, P3.6) |
|---|---|---|
| 0 ON, 1 SEARCH, 2 ACTIVE, 4 NOSUPPORT | power on / search / active / no support | (1, 0) |
| 3 SAVING, 5 NOSUPPORT_SAVING | power saving | (0, 1) |
| 6 OFF, 13 end/all-off | off | (0, 0) |
| 7 TYPE_1 | P3.5 = 1, P3.6 unchanged | - |
| 8 TYPE_2 | P3.6 = 1, P3.5 unchanged | - |
| 9-12 | no code | unchanged |

- Callers of `d6b2` (2 call paths, all callers found by raw scan of `LCALL/LJMP 0x0FA5`/`d6b2`): [fw]

| caller | condition | index -> pins |
|---|---|---|
| 5:d2a0 init (ScalerMcuGpioInitial) | AC on, after P8.4=1, P7.2=0, P9.2=1 | (1, 0) direct SFR writes |
| `d3ac` from `8aa1`, action 0 OFF_TO_NORMAL, 2 AC_ON_TO_NORMAL, 13 FAKE_OFF_TO_NORMAL | power on | 0 -> (1, 0) |
| `d3ac`, action 7 NORMAL_TO_PS, 11 NORMAL_TO_FAKE_PS | to power saving; also panel down `917c(1)` | 3 -> (0, 1) |
| `d3ac`, action 3 AC_ON_TO_OFF, 6 PS_TO_OFF, 8 NORMAL_TO_OFF, 9 NORMAL_TO_FAKE_OFF | to off (3, 8, 9 also panel down) | 6 -> (0, 0) |
| `d3ac`, action 1, 5, 12 | no LED code | unchanged (action 5 PS_TO_NORMAL keeps (0, 1) until the mode machine sets ACTIVE/SEARCH) |
| bank 0 `d8c4` mode flow, mode SEARCH(1) at 0:d943-d973 | on mode-state change and power status NORMAL | 1 -> (1, 0) |
| same, mode ACTIVE(3) at 0:d957 | same | 2 -> (1, 0) |
| same, mode NOSUPPORT(4) at 0:d971 | same, after storing E150 = 3 | 4 -> (1, 0) |
| same, mode NOSIGNAL(5), POWER_SAVING(6), POWER_OFF(7) | no LED call | - |

- Reading: P3.5 = "on" colour, P3.6 = "standby" colour, both low = off; it is the front-panel power indicator. [fw+x] for the function (`UserInterfaceKeyPadLedControl` with the SDK enum), [guess] for the physical LED / colours. SDK precedent: board `RL6449_QA_A_156PIN_2H1DP_eDP.h` names `bLED2 = P3_5`, `bLED3 = P3_6`.
- Path from no signal to the (0, 1) state: see 2a. [fw]
- Live dump cannot show the levels: `0xFFE3` reads 0 for every P3 pin including the power key P3.0 (idle high) in both read-control modes (`tmp/regs/AWT26110001-gpio-{on,standby}-*.json`). [hw]
- Ours: pins are GPIO push-pull by our pin-share (`_PIN_91/_PIN_92` = 1) but nothing drives them; level = reset default [?]. Our `bLED1` is P8.4 (section 3), so the front LED, if it hangs on P3.5/P3.6, stays unlit or in an arbitrary colour. Header: `P3_5/P3_6` not mentioned.
- Settle: on unit 1 (original firmware) watch the front LED colour in on / DPMS standby and probe pins 91/92 with a meter (expect (high, low) on, (low, high) standby). Then add `bLED2 = P3_5`, `bLED3 = P3_6` with the table above to our header.

## 2a. LED rule per power / mode state (#95 step 1, 2026-11-12)
Evidence: bank 0 `d8c4` jump table at 0:d8d7 (raw bytes, index -> handler), bank 1 `98c0` / `e49f` / `d3ac` / `d6b2` disassembly (`scripts/dis51.py`). Names: `re/jxc-4k/names_re1.tsv`.

- `d6b2` decompile and disassembly agree with section 2: 14 cases, writes only P3.5 (`T1`) / P3.6 (`WR`), no timer, no delay, no loop. [fw]
- Mode-state flow (0:d8c4 jump table; index = `SysModeGetModeState`; handler bodies are undisassembled in the Ghidra export, read from raw bytes): [fw]

| mode state | handler | LED call |
|---|---|---|
| 0 INITIAL | 0:d904 | none (OSD / keycode work only) |
| 1 SEARCH | 0:d933 | on state change and power status == NORMAL: `d6b2(1)` -> (1, 0) |
| 2 DISPLAY_SETTING | 0:d9df | none |
| 3 ACTIVE | 0:d947 | same gate: `d6b2(2)` -> (1, 0) |
| 4 NOSUPPORT | 0:d95e | same gate, also `E150 = 3`: `d6b2(4)` -> (1, 0) |
| 5 NOSIGNAL | 0:d978 | none (OSD message only: no-signal text, 0x1388 = 5000 passed as message arg) |
| 6 POWER_SAVING | 0:d9c1 | none |
| 7 POWER_OFF | 0:d8ef | none |

- Gate = "mode state changed" (helper 0:0f99 = trampoline to bank 1 `fd21`; flag meaning [guess]: edge of mode state change, since the handlers run the LED call once per entry. Settle: read `1:fd21`) and `0:d9f1` (power status == 2 NORMAL). [fw]
- Consequence: with a cable but no signal (SEARCH, NOSIGNAL) the LED stays (1, 0). The LED does NOT change on NOSIGNAL. Only a POWER status change to SAVING changes it. [fw]
- Saving entry (resolves the open path in section 2): `1:98c0` (power-side handler, called via 0:0633 trampoline) [fw]
  - Reads mode state (`1:df24` = `e22e & 0x1F`). If it is 6 POWER_SAVING and `e0f4` bit3 is set and `1:faac` returns carry and current power status (`1:e49f`) != 3: sets target power status (`e23a` low nibble) = 3 SAVING and clears `e0f4` bit3 (1:993e-994d). [fw]
  - Then `SysPowerHandler` (1:a587) runs action 7 NORMAL_TO_PS -> `d3ac(7)` -> `d6b2(3)` = (0, 1) and `917c(1)` panel down. [fw]
  - Wake: `1:e339` true (source / signal wake test, body only partly read) and current status != 2 -> target NORMAL (2), `e22f` high nibble = 1 (1:995b-996d); action 5 PS_TO_NORMAL has no LED call, so (0, 1) stays until the mode flow reaches SEARCH / ACTIVE and calls `d6b2` (gate above). [fw]; `e339` semantics [?]
- Full LED rule of the Dahua firmware: [fw]
  - AC on: (1, 0) (direct SFR writes, 5:d311 / d313).
  - Power status NORMAL: (1, 0) in every mode state (SEARCH / ACTIVE / NOSUPPORT set it again, NOSIGNAL leaves it).
  - SAVING (also FAKE_PS): (0, 1). OFF (soft power off, FAKE_OFF): (0, 0). Back to NORMAL: (1, 0).
  - Never blinks, never breathes: no timer arm, no PWM on pins 91 / 92 (GPIO mode), `d6b2` called only from the sites above. Raw scan for `P3`-byte and bit 0xB5 / 0xB6 ops again finds `d6b2` and 5:d311 / d313 as the only code writes (other hits are operand bytes inside other instructions) [fw]. Coverage limit: indirect-addressed writes to SFR P3 are not possible on the 8051 for SFRs (direct addressing only), so this is complete for P3.
- For our firmware: LED = f(power status) only; do not tie it to the signal state. SEARCH / NOSIGNAL keep the "on" colour until the saving timer fires.

## 2b. P7.3 (pin 160), role search
- Only access: `MOV DPTR,#FE1B; CLR A; MOVX @DPTR,A` at 5:d320-d324, 200 ms (`fb15` delay with R7 = 0xC8) after `P7.4 = 0` (FE1C), then P9.7 / PA.0 group. Raw scan of all 7 banks for `MOV DPTR,#FE1B` (90 FE 1B): this one site only (the `FE1A`/`FE1C` hits in the common area are bank-call thunks whose DPTR is a code address, not the port). [fw]
- Neighbours in the same init: P7.4 (amp enable, muted = 0), P7.2 panel power (FE1A = 0), P9.2 backlight (FE2A = 1). P7.3 follows the amp line in sequence. [fw]
- Role: [guess] second audio-amp or audio-path control (a shutdown / standby pin released after the amp line is set low), from the 200 ms ordering after P7.4 and from the SDK RL6432 convention that P7.3 / P7.4 are a pair. Settle: probe pin 160 and trace to the first component on unit 1 (expect ~0 V), or poke 0xFE1B high on unit 2 only while playing audio. No consumer reads it. [?] for what it drives.

## 3. P8.4, P8.5, P9.7, PA.0 (pins 184, 185, 201, 202): switched-peripheral group
- Modes live: P8.4, P8.5 push-pull (mode 1), P9.7, PA.0 open-drain (mode 2). ON all read 1, standby all read 0 (unit 1). [hw]
- Writers (all of them; port regs 0xFE24 P8.4, 0xFE25 P8.5, 0xFE2F P9.7, 0xFE30 PA.0): [fw]

| site | writes | when |
|---|---|---|
| 5:d2a0 `ScalerMcuGpioInitial` | P8.5 = 1 (first), 10 ms later P8.4 = 1; at the end `5:e222(1)` twice = P9.7, PA.0, P8.5, P8.4 all 1 | AC on, after P7.4 = 0, 200 ms, P7.3 = 0 |
| 6:5d88 `ScalerPinshareConfig(a)` | a = 2 NORMAL: all four = 1; a = 3 SAVING, a = 1 OFF: all four = 0; a = 0 AC_ON: flash drive config only | see below |
| 1:adb1 `ScalerPowerIsolation(action)` -> 1:de69 | action 0, 2, 5 (to normal): P8.4 = 1, 10 ms, P8.5 = 1, 10 ms, only if `VCCKOFF_CONTROL0` bit4 or `GA_POWER_CTRL` bit1 is set; action 3, 4, 7, 8 (to off / saving): P8.5 = 0, P8.4 = 0, then 200 ms | inside the scaler's power-cut sequence (Dahua addition to the SDK function) |
| 1:d7ab -> 1:f188 | P9.7, PA.0, P8.5, P8.4 = 1 | on the way to normal, when isolation flag e23b bit0 is set |

- `8aa1` actions and the group (`5d88` argument in brackets): to normal 0, 1, 2, 5 -> all four 1 [2] (order: `ScalerPowerIsolation` rail sequence, `f188`, then `5d88(2)`); 7 NORMAL_TO_PS -> 0 [3]; 3, 8 -> 0 [1]; 6 PS_TO_OFF -> 0 [1]; 9, 11, 12, 13 (fake states) -> no change; 4, 10 -> nothing. [fw]
- So the four pins follow the POWER state (high in NORMAL, low in saving and off), not the signal state. Signal / no-signal changes do not touch them. [fw]
- This is the Dahua board's `PCB_GPIO_SETTING_POWER_NORMAL/SAVING/DOWN` macro set (SDK demo boards leave these macros empty) [fw+x]. P8.4 / P8.5 are additionally sequenced 10 ms / 10 ms up and 200 ms down around the scaler power-cut, which fits an enable of a switched rail (a discharge wait after turn-off); it does not fit an LED. [guess] Settles: probe pins 184 / 185 on a unit and see which regulator / load follows; scope P8.4 -> P8.5 timing on wake.
- What P9.7 / PA.0 drive: open-drain, released (1) in NORMAL, pulled low in saving / off; SDK names for these pins on other boards (`bD3_MHL_VBUS_SWITCH`, `bD2_MHL_CONNECT`) do not describe this board (no MHL). Load unknown. [?] Settles: continuity from pins 201 / 202 to the first component, voltage in on / standby.
- SDK board names for P8.4 / P8.5 (`bLED1`, `bBACKLIGHTPOWER`; `RL6449_DEMO_LOCAL_DIMMING_1USB1H1TC.h` pin comments `GPIO_184_CPU_LED_WHITE`, `GPIO_185_CPU_BLEN`) are a different board. Here the proven backlight enable is P9.2 (active low), and P8.5 stays high through the whole NORMAL state, so it is not the backlight switch. [fw]
- `docs/monitors/gpio-roles.md` said P9.7 / PA.0 are never written: wrong, corrected there.
- Ours: P8.4 = `bLED1` (low in SEARCH / idle / saving), P8.5 = backlight (follows backlight on/off), P9.7 / PA.0 = never driven. Unit 3 live reads with our firmware (`tmp/regs/AWT26110003-gpio-{after-4k60,u3dark}-*.json`): P8.4 / P8.5 read 0 in the 'after-4k60' capture where Dahua ON reads 1. Risk: if these are rail enables, our firmware drops them when it only wants the LED off. [?] Settles: drive P8.4, P8.5, P9.7, PA.0 = 1 for the whole NORMAL state (Dahua behaviour) and keep LED and backlight on other pins; check nothing else changes.

## 4. P7.3, P7.4, P4.5 (pins 160, 161, 113)
| pin | port | Dahua access | role |
|---|---|---|---|
| 160 | P7.3 (0xFE1B, open-drain, pin-share 2) | one write: 0 at init (5:d2a0, 200 ms after P7.4 = 0); never read, never written again | static low output after AC on. Role [?] |
| 161 | P7.4 (0xFE1C, open-drain) | 0 at init; `1:ea99` (value below) | speaker amplifier enable / mute line [fw+x] |
| 113 | P4.5 (0xFE05, input, mode 0) | read in `1:f69b` only | headphone-jack select input [fw+x]: low -> output SPEAKER (1), high -> HEADPHONE (2); polarity and switch type [?] |

- `ea99(bMute)` (SDK `UserInterfaceAdjustAudioAmpMuteProc`): P7.4 = `!bMute` when `f69b()` is 3 (BOTH) or 1 (SPEAKER), else 0. Caller: `3:f8e5 SysAudioMuteProc` via thunk 0x055b (mute at f8ea, unmute at f8ff). The SDK version writes `PCB_AMP_MUTE(bMute)` only for the same two outputs. [fw+x]
- This corrects `register-audit.md` ("no audio-mute GPIO exists"). Audio itself is out of scope (Dan).
- P7.3: SDK RL6432 boards use P7.3 / P7.4 as MHL VBUS / TMDS switch (not this board). P7.3 role [?]. Settles: poke 0xFE1B on unit 3 (`scripts/rtd_reg_poke.py`) and watch audio, USB, LEDs, picture; probe pin 160 (expect ~0 V on unit 1).
- Ours: neither driven. Unit 3 (our firmware) reads P7.3 = 1 (released) in the 'after-4k60' and 'u3dark' captures; Dahua unit 1 reads 0. A measured difference. [hw]

## 5. Output pins the Dahua firmware drives, compared with our header (`gpio_audit.tsv`)
| pin | port | Dahua | our header / behaviour | difference |
|---|---|---|---|---|
| 1, 14 | P1.0, P1.1 | D3 / D2 HPD (OD): 1 at init, set/clear in 5:f722/f917, 5:f774/fa36 | `bD3_HPD`, `bD2_HPD` driven | none |
| 97 | P4.2 | D1 HPD, 0 at init | `bD1_HPD` driven | none |
| 96 | P4.1 | not touched | `bD0_HPD` driven | ours only |
| 91, 92 | P3.5, P3.6 | LED pair (section 2) | not listed, not driven | missing |
| 159 | P7.2 | panel power | `bPANELPOWER` driven | none |
| 160 | P7.3 | static 0 | not listed | missing (measured, section 4) |
| 161 | P7.4 | amp enable | not listed | missing (audio) |
| 184, 185 | P8.4, P8.5 | NORMAL-state group | LED1 / backlight | semantics differ (section 3) |
| 190 | P8.6 | flash WP (3:d402 / d43e), 0 at init | `bFLASH_WRITE_PROTECT` driven | none |
| 196 | P9.2 | backlight enable, active low (`917c`) | `bBACKLIGHT_EN_N` driven | none |
| 195 | P9.1 | PWM4 backlight (pin-share 3) | PWM4 | none |
| 201, 202 | P9.7, PA.0 | group (section 3) | listed as `bD3_MHL_VBUS_SWITCH` / `bD2_MHL_CONNECT` (input name), macros empty | not driven |
| inputs | P3.0, P4.5, P9.4, PA.2-PA.5 | key, jack, cable detects | P3.0 in key code; `bD*_CONNECT` | P4.5 missing |
- Our header drives P8.3 (EDID WP) and P4.1 which Dahua never writes. [fw]
- Pins 194 (P9.0, `irda_in`) is listed in our header as `bLED2` (macro is a no-op): never drive it, it is the IR input. [fw][hw]
- Coverage: constant-address port writes (raw `MOV DPTR,#0xFE00-0xFE37` scan plus export) and the SFR bit sites above. Writes through a pointer that the resolver could not name (1,033 sites, `register-audit.md`) are not excluded; the 72-pin sim traces show no other port-register write.

## 6. IR receiver path
### 6.1 Hardware set-up [fw+x]
- Pin 194 = P9.0 = `irda_in` (pin-share mode 6, live). Block = IR registers 0x23A0-0x23DF.
- Init `ScalerIRHWModeInitial` (6:6315, thunk 0:0681, from `SysMainSystemInitial` 0:fb4d): `IR_SF2:SF3 = 0x00B1`, `IR_SR3 = 0x7F` (clear flags), `IR_CR2 |= 5` (bit0 enable, bit2 interrupt enable). Power-save clock switch `ScalerIRHWModeClockSel` (6:654C) sets `0x00B1` (XTAL) or `0x015D` (IOSC), called from the system-clock select (1:acd8) in the saving / off states.
- Sample clock: 14318 kHz / (0xB1 + 1) = 80.4 kHz and 28 MHz / (0x15D + 1) = 80 kHz; the SDK formula `_IR_SAMPLE_CLK 50` would give 0x011D. The Dahua build samples at 80 kHz. [fw+x]
- Protocol table: `ScalerIRHWModeDecoder` (6:573b) is called once, from 5:fe28 (`UserAdjusIR`, via thunk 0:0def from 1:e32b) with the table at **bank 5:0x2B0E** (32 bytes, 4 chunks), which is byte-identical to the SDK `IRRemote/NEC_DTV328.h`: [fw]
  - `A0-A9`: 6D 1A 1A 50 00 03 17 36 FF 7D; `AE-B3`: 13 9F 00 00 00 DF; `D0-D7`: 77 1E 1E 64 00 00 1F 3E; `DA-DB`: 00 00.
  - `IR_CR3 = 0xDF` = length mode, burst, 32 data bits; `IR_CR2 = 0` (default endian). Protocol = NEC, 32 bit frame (address, ~address, command, ~command), timings at the 80 kHz sample clock. [fw+x]
- Receive: `ScalerIRHWModeIntHandler_EXINT0` (6:4fc4) copies `IR_RP0-3`, `IR_RP2_0-3` to XDATA E1EE-E1F5 and sets the received flag; `ScalerIRHWModeGetData` (6:57f3) hands them to the key scan once per frame. [fw+x]
- Byte order assumption: SDK NEC key codes are `(buf[0] << 8) | buf[2]` with a constant low byte (0xFB) over five keys, so `buf[0]` (RP0) is the varying NEC command byte and `buf[2]` the constant address byte. The Dahua code below matches `buf[0]:buf[1]` = (command, ~command). [guess] Settles: log E1EE-E1F5 while pressing an NEC remote (ISP read), or a frame with a known address / command.

### 6.2 Key scan `key_alt_source_poll` = SDK `RTDIRKeyScan` (6:5154) [fw+x]
- Runs from `key_scan_adc` (6:3944, call at 6:3a71) when no ADC key and no P3.0 key is down; returns the key mask in R7 (0 or 1), which becomes the same mask as the front keys (`key_scan_adc` then calls 6:68a7 when it is non-zero).
- The "table" copied from `0xFF:3067` into XDATA DBB4 is the zero initialiser of the SDK local `BYTE pucIRCodeBuffer[8] = {0}`: bank 6 bytes at 0x3067-0x306E are all 0x00. The earlier note ("bank-0 bytes 30 00 CC...") read the wrong bank. [fw]
- Flow: `ScalerIRHWModeGetData(&DBB4)`; frame accepted only when `DBB6 == ~DBB7` (buf[2] == ~buf[3], command check); `key = (DBB4 << 8) | DBB5` = (buf[0], buf[1]); `16-bit switch` (Keil helper 0x163D, case table inline at 6:51AA): the one case **0xB946** returns 1; anything else stores the 16-bit value in XDATA E20A:E20B and returns 0; no frame clears E20A:E20B. The address pair (buf[2], buf[3]) is only checked for complement, never compared: any remote address is accepted. [fw]
- Key 0xB946 (command 0xB9, complement 0x46) -> mask 0x01 = the POWER key (same bit as P3.0 low; the power-key edge handler `key_power_edge` 6:5942 then runs, power toggle per `buttons.md` section 3). [fw]

### 6.3 Everything else: `osd_keycode_to_event_idx` (0:c6b1) [fw]
- Runs at the end of the bank 0 OSD flow in every mode state (0:d90f, d9dc, d9e1). Reads the code word from E20A:E20B (helper 0:f9cc) and the OSD state e14e:e14f (helper 0:f9d5). Zero word = nothing.
- OSD closed (`usOsdState == 0`):

| code (cmd, ~cmd) | action |
|---|---|
| F1 0E | `e151 = 0` = MENU message: opens the main menu (`f97a` index 0) |
| A7 58 | `osd_page_build_dd7c` = input-source list page (same as the SOURCE key) |
| B6 49 or B1 4E | `e4dc(0x47)` |
| B7 48 or B2 4D | `e4dc(0x2B)` |
| A3 5C | `e4dc(0x46)` |
| A0 5F | `e4dc(0x37)` |
| A1 5E | `e4dc(0x2F)` |
| A2 5D | `e4dc(0x49)` |
| ED 12 | `e4dc(0x45)` |

  `e4dc(id)` (0:e4dc) opens the value-adjust page of OSD item `id` (ids < 0x4F; the front-key UP / DOWN hot-key slots call it with `*e06c` / `*e06b`). Which setting each id is: [?]. Settles: render with the sim (`scripts/menu_shot.py`) or read the item table for ids 0x2B, 0x2F, 0x37, 0x45-0x47, 0x49.
- OSD open: result is `e151` (key message 0 = MENU / select, 1 = UP, 2 = DOWN, 3 = AUTO / back; same meaning as the front keys), by `usOsdState` range:

| state | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0x01-0x2A | B5 4A, B6 49 | B7 48 | B2 4D | F2 0D, B1 4E |
| 0x2B-0x4F except 0x3C | B5 4A | B6 49 | B1 4E | F2 0D |
| 0x3C | B5 4A | B7 48 | B2 4D | F2 0D |
| 0x50-0x54 | B5 4A | B6 49, B7 48 | B1 4E, B2 4D | F2 0D |
| 0x55-0x72 | B5 4A, F1 0E | B2 4D, B6 49 | B7 48, B1 4E | F2 0D |
| 0x73-0x8E | B5 4A, F1 0E | B6 49 | B1 4E | F2 0D |
| >= 0x8F | B5 4A, F1 0E | B7 48 | B2 4D | F2 0D |

- Command bytes in use: B9 (power), B5 F2 B7 B2 B6 B1 F1 A7 A3 A0 ED A1 A2. Key names for the navigation codes (B5 = enter / menu, F2 = back / exit, B6 / B7 / B1 / B2 = up / down / left / right) are [guess]; settles: log the code of each remote key (above) and press in a menu.
- What a remote can do [fw]: power toggle (B9); open the menu (F1 0E, when closed); open the input list (A7); navigate and confirm in menus; open seven direct-adjust pages. Whether IR wakes the monitor from standby: the IR sample clock is re-timed for the saving clock, the main key poll is not shown to run in standby here. [?] Settles: NEC command 0xB9 at standby.
- No remote has been available: nothing here is [hw].

### 6.4 Ours
- `_IR_SUPPORT _IR_OFF` (`RL6449_Project.h:1220`); no IR init (registers 0x23AA, 0x23AB, 0x23B2, 0x23BB are Dahua-only).
- To match: `_IR_SUPPORT = _IR_HW_SUPPORT`, NEC table above, sample clock 80 kHz, and the key mapping of 6.2 / 6.3 (the SDK `RTDIRKeyScan` has a different code scheme: use the Dahua one). Header pin: `irda_in` pin 194 is already mode 6 in our pin-share.

## 7. Missing features for our firmware
- Two-colour power LED on P3.5 / P3.6 (section 2): issue filed with this pass.
- P8.4 / P8.5 / P9.7 / PA.0 NORMAL-state group, P7.3 static low (sections 3, 4): same issue (power-state GPIO parity).
- IR receiver with NEC command 0xB9 = power and the menu codes (section 6): optional.
- Speaker amp enable P7.4 and jack input P4.5: audio, out of scope.
