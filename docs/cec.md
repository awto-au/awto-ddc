# HDMI CEC (awto-ddc#101)

Dan asked 2026-11-19: "Turn on CEC please, and at some stage we will test with an RPi5". State: code on, nothing tested on a unit (Phase B), the CEC pad is not proven to exist.
Tags: [hw] measured on a unit, [spec] regdb / datasheet text, [sdk-hypothesis] SDK header or source only (SDK is not evidence), [?] untested, test in `re/regmap/tests.tsv` (`C-CEC*`).

## What is on
- Build: `_D2_HDMI_CEC_PIN` and `_D3_HDMI_CEC_PIN` = `_HDMI_CEC_0` in `RL6449_AWTO_JXC4K.h` -> `_HDMI_CEC_SUPPORT` on; one code path, no build flag.
- SDK files brought back from `fw/sdk-parked`: `ScalerCec.c` (register layer, EXINT0 receive), `SysCec.c`, `UserCommonCec.c`; `RTD2014UserInterfaceCec.c` rewritten (glue). Our message layer: `fw/cec/cec_msg.c` (pure logic, host-tested).
- Removed from the SDK: LA polling / topology scan (a TV needs none), the demo triggers on XDATA 0x000D, `ScalerCecInitial` in `SysPower.c`.
- Init: `SysCecHandler` runs `ScalerCecInitial` once power is NORMAL and the mode is ACTIVE / NO SIGNAL / NO SUPPORT (display path up), again after a power-off. No wait, no poll loop in it: a CEC fault cannot block boot.
- Role: TV, logical address 0 (`CEC_LA_TV`), physical address 0.0.0.0 (root). CEC version 1.4 (0x05).
- `SysMain` calls `SysCecHandler` only when due (frame / reply / analysis pending, else every 32nd pass: `AWTO_CEC_DUE`).

## Pin evidence (step 1)
| source | finding | tag |
|---|---|---|
| pin ledger `docs/monitors/rtd2795t-216-pin-ledger.tsv` (datasheet Table 1) | no CEC-named lead on the LQFP216; pins 78..88 NC | [spec] |
| RTD2795T regdb pin-share table (`~/vendors/realtek/analysis/regdb/RTD2795T-CG.gpio.tsv`, 175 pads) | no pad has a CEC option (0 matches for `cec`) | [spec] |
| same tables of sibling chips | RTD2776B: PE.7 option 011 = `Cec1_line_pio_in`, PF.0 option 011 = `Cec0_line_pio_in`; RTD2785TM: P9.0 (pin 208) = `cec0_line_pio_in`. The chips that bring CEC out list it as a pin-share option | [regdb-other] |
| RTD2795T regdb pages 18 / 19 | no rows; SDK header names the block (`P18_A0_CEC1_CR0_1` ... `P19_F5_CEC_PSM`); live scans read non-zero reset-like values (18A0 = 0F, 18A1 = 40, 18A3 = 14, 18A4 = 12, 18B0 = 0F) | [spec] + [sdk-hypothesis] |
| SDK `_D[0-5]_HDMI_CEC_PIN` | only a per-port boolean (`_HDMI_CEC_0` = this port uses CEC block 0); RL6449 defines it for D2 and D3 (the two HDMI ports); no pad name, no pin-share write anywhere | [sdk-hypothesis] |
| Dahua firmware | never touches pages 18 / 19 (`docs/reversing/dahua-fw/register-audit.md`) | [fw] |
| `scripts/port_watch_excluded.tsv` | "no CEC pin on the LQFP216 table" | [spec] |

- Ports on this board: D1 DP, D2 HDMI, D3 HDMI (D0 none). CEC slots exist for D2 and D3 only.
- Conclusion: the die has a CEC block, the RTD2795T-CG has no pin-share option that routes a pad to it. Confidence the HDMI CEC line (connector pin 13) cannot reach the block through pin-share: high. It can still reach a GPIO pad on the PCB (not traced) or the block through a path the databook does not list [?].
- Why CEC is on anyway: Dan's request; an idle block costs nothing and answers nothing; the RPi5 test settles it.
- Test `C-CECPIN` (Phase B / Pi, read-only):
  - Pi: send polls continuously (`cec-ctl -d0 --to 0 --poll` in a loop) with the cable on D2, then D3.
  - Host: `./dev.py gpio watch` (every unused GPIO input) and `./dev.py dump` pages 18 / 19; a pad that toggles at the poll rate carries the CEC line; 18B0..18B2 changing = the block sees it.
  - Continuity check connector pin 13 -> scaler / GPIO if neither moves (board trace, issue #101 item 1).
- If a GPIO carries it: a software CEC (bit time 2.4 ms) would be the route; not written.

## EDID physical address
- The Pi / any source reads its physical address from the CEA VSDB of the EDID.
- `scripts/make_edid.py`: HDMI D2 = 1.0.0.0 (`10 00`, unchanged), HDMI D3 = **2.0.0.0** (`20 00`, was 1.0.0.0). A TV with two inputs is the root 0.0.0.0, its inputs are 1.0.0.0 and 2.0.0.0. DP EDID has no VSDB.
- The monitor reports 0.0.0.0 itself (`<Report Physical Address>`, device type TV).
- EDID is per-unit flash data: the new D3 bytes reach a unit with `./dev.py edid` / `deploy` (Phase B; not flashed from this tree). `docs/edid-fix.md` updated.

## Registry (`fw/rtdfw/settings/registry.tsv`, menu page Signal)
| id | name | default | meaning |
|---|---|---|---|
| 125 | `cec_en` | on (Dan 2026-11-19) | CEC block + replies; off clears the block enable bits (`18A0[7:6]`) within ~32 passes |
| 126 | `cec_ctl` | off | CEC may act on Standby / Image View On / Text View On / Active Source / Set Stream Path / Routing / User Control. Today: no action; on = an extra log row per hook |

## Messages (HDMI 1.4b CEC; names as `cec-ctl`)
| received | reply | notes |
|---|---|---|
| polling (header only) | none | the block acks by logical address [?] (`C-CECACK`) |
| `<Give Physical Address>` 83 | broadcast `<Report Physical Address>` 84: 00 00 00 (0.0.0.0, TV) | |
| `<Give Device Vendor ID>` 8C | broadcast `<Device Vendor ID>` 87: A7 70 D0 | awto OUI as in the EDID port tag (`AWTO_OUI`), unregistered. Linux answers Feature Abort for "no vendor ID"; we answer with an unregistered ID (Dan's brief) |
| `<Get CEC Version>` 9F | `<CEC Version>` 9E: 05 | 1.4 |
| `<Give OSD Name>` 46 | `<Set OSD Name>` 47: `awto-mon` | = EDID monitor name |
| `<Give Device Power Status>` 8F | `<Report Power Status>` 90: 00 on (power NORMAL) / 01 standby (saving, off) | "to on / to standby" (02 / 03) not reported |
| `<Abort>` FF | `<Feature Abort>` 00: FF 04 (refused) | spec |
| any other opcode | `<Feature Abort>` 00: opcode 00 (unrecognized) | not for broadcast-only opcodes (32, 80..82, 84..87, 89, 8A, 8B, A0): the block does not tell broadcast from directed [?] |
| `<Feature Abort>`, `<Report PA>`, `<Device Vendor ID>`, `<Set OSD Name>`, `<Report Power Status>`, `<CEC Version>`, `<Request Active Source>`, `<Inactive Source>` | none | answers / announcements of others, logged |
| `<Standby>` 36, `<Image View On>` 04, `<Text View On>` 0D | none | hook, logged, **no action** |
| `<Active Source>` 82, `<Set Stream Path>` 86, `<Routing Information>` 81, `<Routing Change>` 80 | none | hook, logged, **no action** (no input switching) |
| `<User Control Pressed / Released>` 44 / 45 | none | hook, logged, **no action** |
- Logic and tests: `fw/cec/cec_msg.c`, `tests/test_cec_msg.py` (compiled on the host, every row above).
- Not implemented: Get Menu Language, Set Menu Language, System Audio, ARC, Deck / Tuner, Vendor Command (answered with Feature Abort), Standby from the monitor's own power key, CEC wake from power saving.

## Log (sync ring row `EB`, fmt `cec`; `./dev.py synclog`, the on-screen console and the host print the same text)
- Row: `fw/awto/sync.tsv` `EB * cec CEC %`. arg = flags | length << 3 | kind; value = header << 24 | opcode << 16 | operand 1 << 8 | operand 2. Decoder: `scripts/sync_log.py cec_line` (host), `AwtoPutCec` in `fw/osd/console.c` (screen); opcode names `fw/cec/opcodes.tsv` (a test keeps the firmware table in step).
- Every frame and every reply is a row, repeats included (never dropped):
  - `CEC rx 4>? Give Physical Address`: `4` initiator, `?` destination unknown (gen type 0 has no register for it)
  - `CEC tx 0>F Report Physical Address 00 00+`: first two operands, `+` = more
  - `CEC tx result:acked | line error | no ack (header) | no ack (data)` (gen type 0: only acked / no ack)
  - `CEC hook:Standby (no action)` (cec_ctl on), `CEC rx reply dropped, the last reply is not sent`, `CEC block on / off`
- Raw frame bytes: `cec_pi_test.raw.log` on the Pi; the ring keeps no raw trace (decoded rows only).

## Register layer (all [sdk-hypothesis], rows in `re/regmap/regs.tsv`, tests `C-CECINIT / RX / TX / DEST / ACK`)
- Gen type 0 (`_HW_CEC_GEN_TYPE_0`): no received-header register (18E3) and no TX result (18B7). Consequences in code:
  - destination of a received frame is unknown: logged `?`, broadcast-only opcodes never get a Feature Abort;
  - TX result is `acked` when 18B5 bit2 (tx EOM) is set, else `no ack (header)`; a lost or collided frame is not distinguished [?].
- Clock: IOSC 28 MHz (18A1 bit7 = 0), dividers 18A3 / 18A4 = 0x19 / 0x1C, bit timings 18E5.., 18EF..: the SDK values.
- Receive: EXINT0 -> `ScalerCecIntHandler_EXINT0` -> frame into `isr_g_stCecRxReceivedInfo` (or the 20-byte backup FIFO while one is analysed) -> main loop -> `UserInterfaceCecReceivedNotify` (log + `CecMsgRx` + queue reply). Changes to the SDK code: no `memset` in the ISR path (library helper not ISR-safe), byte count clamped to 16 (5-bit field), backup FIFO 30 -> 20 bytes (XDATA floor).
- Transmit: the reply is composed straight into `g_stCecTxTransmitInfo` (no second copy) and `SET_CEC_TX_START`; one reply at a time: a second request while a reply is in flight is not answered (logged `dropped`), the initiator asks again. 3 retransmissions (SDK value).
- RX handoff: the analysing flag is set before the frame is handled (the ISR then fills the backup FIFO, not the RX struct); the SDK's backup-FIFO shift in the main loop still runs while the ISR can append (frames come >= 24 ms apart; a flash write can block the loop longer) [?].
- `UserCommonCecTransmitInfoPrepare` and the LA-polling glue are gone.
- No delays added (`docs/delay-audit.tsv` unchanged): nothing waits, every step is a register access in the main loop or the ISR.

## Cost (sim, image tag af46ad6+, 2026-11-19; baseline = af46ad6 without CEC)
- XDATA free: 901 B -> 734 B (after merging the health monitor of #245 the same tree without the copy removals would have left 697 B). Copies removed: local RX / TX structs in `UserCommonCec.c`, the reply slot, backup FIFO 30 -> 20 B.
- Code + constants in banked space: ~4.9 KB (SDK CEC 2.0 KB, `cec_msg` 1.1 KB, glue 0.9 KB, console names + printer 0.5 KB, sync row). Gate `link` / bank layout pass.
- Main loop (sim bench: main-loop heartbeat passes in 2 fw seconds after ACTIVE + 1 s settle, `AWTO_SIM_CORE=fast`; not a committed script): 1201 passes -> 1191 passes (8428 -> 8501 instr/pass, +0.9 %; measured before the #245 merge, which adds its own monitor work). Running the CEC work every pass was +10 % (9275 instr/pass): the due-gate removed it.
- ISR: `ScalerCecIntHandler_EXINT0` adds one register read + compare per EXINT0 while idle (6 instructions, `18B0` bit4 clear before init); a frame costs ~300 instructions once per >= 24 ms. `fw_stack`: worst ISR path is still the DP training path through `SysEXINT0` (32 B); the CEC path is shallower. Gates `isr`, `canary` pass.
- On a unit the same numbers need `./dev.py health` loop rate before / after (Phase B).

## Tests
- `python -m pytest tests/test_cec_msg.py` (host C build of `cec_msg.c`, name tables, decoder, registry rows, EDID PA, then the sim test if an image exists).
- `scripts/cec_sim.py BIN MAP`: boots the image to ACTIVE in the firmware sim, a CEC block + bus model ([sdk-hypothesis] register behaviour: RX frame registers + EXINT0, TX completes at once with EOM set) sends 14 frames from a playback device and checks the reply frames and the decoded sync rows; also cec_ctl hook rows and cec_en off / on. In `fw_gates`-style runs: `AWTO_SIM_CORE=fast python scripts/cec_sim.py tmp/fw/<stem>-be.bin tmp/fw/<stem>-be.map`.
- The sim model is not the hardware: it proves the firmware logic and logging, not the pad, the bit timing, the ack or the TX result.

## RPi5 test (Dan, later)
Pi 5 micro-HDMI ports have native CEC (`/dev/cec0` for HDMI0, `/dev/cec1` for HDMI1, vc4 driver); `sudo apt install v4l-utils` gives `cec-ctl`, `cec-compliance`.
1. Cable: Pi micro-HDMI -> monitor HDMI input (D2 or D3) with a cable that carries CEC (pin 13). Monitor on, EDID of this tree flashed (`./dev.py edid`) so the Pi gets 1.0.0.0 (D2) / 2.0.0.0 (D3).
2. On the Pi, from this repo: `python3 scripts/cec_pi_test.py --dev /dev/cec0` (table of PASS / FAIL, raw output in `tmp/logs/cec_pi_test.raw.log`); `--compliance` adds the cec-compliance remote test of logical address 0. Not yet run on a Pi: the first run may need output-token fixes in `ROWS`.
3. By hand:
   - `cec-ctl -d0 --playback --osd-name pi5-test` then `cec-ctl -d0 -S` (topology: the Pi is logical address 4, physical address 1.0.0.0 / 2.0.0.0; the monitor shows as TV, 0.0.0.0, once it answered).
   - `cec-ctl -d0 --to 0 --poll` (ack = the monitor's block sees the line; NACK on every retry = no CEC path: run `C-CECPIN`).
   - `cec-ctl -d0 --to 0 --give-physical-addr` -> `phys-addr: 0.0.0.0`, `prim-devtype: tv`
   - `--give-device-vendor-id` -> `0x00a770d0`; `--give-osd-name` -> `awto-mon`; `--give-device-power-status` -> `pwr-state: on`; `--get-cec-version` -> `version-1-4`
   - `--give-deck-status status-req=once` -> `FEATURE_ABORT` (unrecognized)
   - `--active-source phys-addr=1.0.0.0`, `--to 0 --image-view-on`, `--to 0 --standby`, `--to 0 --user-control-pressed ui-cmd=select`: acked, logged, the monitor does nothing.
   - `cec-compliance -d0 --help` shows the option that tests a remote logical address (`-r 0` in recent v4l-utils); run it against logical address 0 and keep the report (expect failures on features not implemented: menu language, system audio, ARC).
4. On the PC: `./dev.py synclog --unit 3` (Debug link on) shows `CEC rx / tx / tx result` rows for each step; `./dev.py dump` pages 18 / 19 for the register view.
5. Results go to the `C-CEC*` rows (`re/regmap/tests.tsv`, `regmap_build.py --set 18B0 result=...`) and #101.

## Phase B plan (unit 3, on Dan's go; not done)
- Flash the default image (`./dev.py flash`), health 11/11, boot loop 10x, DDC check, loop rate before / after.
- Read pages 18 / 19 after boot: `18A0` bit6 = 1, `19F0` bit7, `18A3` / `18A4` = 0x19 / 0x1C (block initialised, `C-CECINIT`).
- No CEC source on the bench yet: the RX path is untested until the Pi is connected.
- Leave unit 3 on the new default, rest state (4K59.940, saver off, Rotate 180).
