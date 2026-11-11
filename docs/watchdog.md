# Watchdog and crash canary (#131)

- Firmware: `awto-ddc-wdt` branch `wb-p14ui-wdt` a559295 (`fw/sdcc/awto_wdt.inc`, `awto_wdtpop.inc`, `fw/awto/wdt/rules.py`, `RL6449_Project.h` `StAwtoWdt`).
- Host: `scripts/rtd_crash.py` (read / decode / clear), `scripts/crash_sim_test.py` (fw_sim), `scripts/fw_sim.py` `ChipReset`.
- Related: #29 (reset cause on screen), #35 (self-recovery hooks), #26 (power-key reset; not on this branch, see Open items).

## Registers (regdb `re/regdb/RTD2795T-CG.tsv.gz`)

| reg | bits | fact |
|---|---|---|
| FFEA WATCHDOG_TIMER | 7 wdt_en, 6 clr_wdt (W: clear all counters, latch them into FFAA-FFAD), 5/4 halt on SPI-flash / burst write, 2:0 cnt1 = N 1..8 | `ScalerMcuInitial` sets N = 8 and enables it |
| FFE9 MCU_CLK_CONTROL_1 | 7 wdt_en_3 | any of FFEA[7], FF3A[6], FFE9[7] enables the WDT |
| FFEB WDT_TEST | 7 wdt_overflow_flag (W1C, set at threshold), 4 timer mode, 3 latch counters, 2 IRQ at threshold, 1/0 bypass CNT2 / CNT3 | SDK: timer mode + IRQ on (`ScalerTimerWDInitial`) |
| FFAA-FFAD | CNT2 11 bit, CNT3 12 bit, CNT1 3 bit (latched values) | |
| FFAE-FFB0 | threshold 12 bit + mask | compared with CNT3 (bypass bits 0) |
| FFEE MCU_CLOCK_CONTROL | 1 sof_rst: "Reset Scaler IC chip" | = host ISP `0xEE <- 0x02` (`rtd_reset.py`), reboots the unit |
| P0_01 HOST_CTRL | 6 reset_chk: write 1, an LVR clears it | 0 at boot = power-on / brown-out |

- No reset-cause latch for the WDT: FFEB[7] is the threshold flag of the SDK's timer use and resets to 0 [regdb reset value]; #26 found the same.
- CNT3 counts once per 2048 XTAL clocks: SDK converts ms with `ms * XTAL_kHz >> 11` (`ScalerCommonTimerFunction.c:631`). XTAL 14.318 MHz (`RL6449_AWTO_JXC4K.h`).
  - CNT3 wrap: 4096 x 2048 / 14.318 MHz = 585.9 ms. SDK comment: event times "10 ~ 500 ms (for 14.318M)".
  - Reset after N CNT3 wraps [likely: chain inferred, not measured]: N = 8 -> 4.69 s.
- DW8051 core has no watchdog of its own (datasheet: timers 0-2, serial, interrupt unit); the WDT is Realtek's XFR block, IRQ on EXINT2 = interrupt 8, vector 0x43, flag EXIF[4].

## Why the old WDT never caught a hung main loop

- SDK runs the WDT in timer mode as a one-shot event timer (`_WD_TIMER_INT_SUPPORT` on for DP / HDMI 2.0).
- `ScalerTimerWDEventProc_WDINT` clears all counters at every threshold IRQ; idle threshold 0xFFF -> cleared every 586 ms.
- Timer2 ISR (1 ms) clears it too when CNT1 > 4 ("Prevent INT Lock Reset", `SysTimer.c`).
- So the hardware reset only fires when both ISRs are dead (EA off, or a hang in a high-priority ISR): the backstop, 4.69 s, no capture.

## Design

- Check in the Timer2 ISR (`AWTO_DIAG_T2ISR` -> `AWTO_WDT_T2ISR`), every `AWTO_WDT_CHECK_MS` = 200 ms (Dan).
- Two ages, in checks, both bytes (atomic for the main loop):
  - `ucFeed`: zeroed by every main-loop pass (`AwtoDiagMainPass`) and every ms of a bounded wait: `ScalerTimerDelayXms`, `ScalerTimerPollingFlagProc`, `ScalerTimerWaitForEvent`, `AwtoMsgWait`.
  - `ucPass`: zeroed by main-loop passes only.
- Bite when `ucFeed >= AWTO_WDT_FEED_CHECKS` (STALL: compute loop, no wait) or `ucPass >= AWTO_WDT_PASS_CHECKS` (PASS: a wait called in an endless loop).
- A limit of N checks bites after (N-1)..N checks of silence (phase of the 200 ms check).
- Bite (`AwtoWdtBite`, Timer2 ISR context): EA off, capture from the ISR frame, seal the record, then:
  - WDT to normal mode, IRQ off, N = 1 (fallback reset after one CNT3 wrap, 586 ms, if sof_rst does nothing);
  - FFEE[1] sof_rst; spin.
- Feed sites are same-line keil2sdcc SUBS: no SDK line moves (`fw/warn_policy.tsv`).
- WD timer events (DP rebuild PHY, HDMI RR retry) untouched; the watchdog no longer depends on the WD ISR.

### Timeouts (expected worst case, source, multiplier, expiry)

| limit | waits for | expected worst | source | x | value | expiry |
|---|---|---|---|---|---|---|
| FEED 5 checks | any feed | < 600 ms compute without a wait | sim: max `ucFeed` 2 over boot, 10 s ACTIVE, console / menu / selector / D3-D2 switch (2026-11-11, wdt3) | 1.25 -> 750 ms <= (5-1) x 200 | 800-1000 ms | capture + reset |
| PASS 27 checks | main-loop pass | 4056 ms | `docs/delays.md` static worst context (search: 2186 ms blind + 1870 ms poll bounds); sim max `ucPass` 3 (< 800 ms) | 1.25 -> 5070 ms <= (27-1) x 200 | 5.2-5.4 s | capture + reset |
| SHOW 1000 ms | screen settled after a bite | SDK mode pop-up drawn within one pass (sim < 800 ms) | sim | 1.25 | 1000 ms | console opens |
| hardware backstop | CNT1 = 8 CNT3 wraps | ISRs dead | regdb + SDK formula [likely] | - | 4.69 s | reset, no capture |

- FEED is set from a sim measurement: hardware-only paths (flash erase, HDMI PHY, DP training) are not in it. Read `max feed` / `max pass` on unit 2 with `rtd_crash.py` and raise the limit with the number if needed.

## Record `g_stAwtoWdt`, 32 B at XDATA 0xF6B0

- Outside the linker XDATA range (`fw_build.py XRAM = (0xD700, 0xF6B0)`): neither the crt (XSEG clear, `crt_xinit.asm`) nor `AwtoDiagInit` touches it.
- Bytes only: same layout in LE and BE images.

| off | field | |
|---|---|---|
| 0-2 | 'W' 'D' version 1 | host clear = write 0 to byte 0 |
| 3 | cause | 1 STALL, 2 PASS; bit 7 = test hang (cmd 0x4C-0x4E) |
| 4 | bites | watchdog resets since clear (stops at 255) |
| 5 | warm | other warm resets: no LVR and no bite (hardware WDT, ISP 0xEE) |
| 6-7 | PC hi lo | return address stacked by the Timer2 interrupt |
| 8 | bank | `__bs_cur` (bank.asm shadow) at the interrupt; PC >= 0x5000 is in this bank |
| 9 | SP | SP before the interrupt |
| 10-14 | PSW ACC B DPH DPL | from the ISR frame |
| 15-16 | stack top hi lo | word at SP / SP-1 (often a return address or a bank-return entry) |
| 17-18 | stage, mode | `g_stAwtoDiag.ucStage`, `GET_MODE_STATE()` |
| 19-22 | heartbeat, uptime ms | big-endian pairs |
| 23-24 | feed age, pass age | at the bite, in checks |
| 25 | check | 0xA5 ^ bytes 0..24 |
| 26 | boot (live) | 0x01 LVR, 0x02 bite pending, 0x04 test armed, 0x08 not yet shown, 0x10 warm without capture |
| 27-31 | live | tick ms, feed age, pass age, max feed, max pass (this boot) |

- ISR frame: SDCC prologue of `SysTimerIntProc2` pushes acc, psw, r7..r0, bits, dpl, dph, b: PC at SP-15/-14 when `AWTO_WDT_T2ISR` reads SP (`AWTO_WDT_FRAME` 16). A prologue change moves it: `crash_sim_test.py` fails (PC not in `AwtoWdtHang`).
- `AwtoWdtInit` (before EA, once per reset): bad magic / check -> fresh record; bite pending -> not-yet-shown; no LVR and no bite -> warm++.

## Reading it

- Console: opens by itself once stage 8 + ACTIVE / no signal / no support has held 1 s after a bite; panel `WATCHDOG` (col 62, row 19): bites / warm, cause, ages, PC as bank:addr, stack top, SP, A, B, PSW, DPTR, heartbeat, uptime, stage, mode, this boot's class and max ages. Title red until shown.
  - Chosen over a one-line notice: no new OSD code, the PC is on screen at once, the console is the place Dan already reads.
  - Not via the info pop-up (`ucDbgPopup`): the SDK pop-up repositions the OSD after the console opened (sim render: vertical delay off screen).
- Any time: console (test cmd 0x20 / UP+DOWN) shows the panel; `NO BITE RECORDED` when empty.
- I2C: `python scripts/rtd_crash.py BUS --map MAP --serial SERIAL [--clear]` -> one line, PC as symbol+offset from the map, stack top decoded (bank-return entries named). Log `tmp/logs/rtd_crash.log`.
- Test cmds (diag `ucTestCmd`): 0x4C spin (STALL), 0x4D spin in `ScalerTimerDelayXms(10)` (PASS), 0x4E spin with EA off (hardware backstop only, no capture).

## Timer split (DP rebuild PHY, HDMI RR retry)

- Users of the WD timer in this build: `_SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY` (30 ms after TP end, armed from EXINT0, `RL6449_Series_DP_INT.c:822`), `RXn_HDMI_RR_RETRY` (10 ms, `ScalerTMDSRx2/3_SeptPhy.c:562`). DP HDCP2 SKE (4 ms) and Type-C PD events are compiled out.
- Granularity: events of 10 and 30 ms; a 1 ms timer would meet them.
- Not moved:
  - Timer2 ISR is high priority (PT2): the rebuild handler blocks ~1 ms (845 us PHY + 150 us delays, `docs/delays.md`) and would delay EXINT0/1 and the 1 ms tick. In the WD ISR (EIP never written = low priority) Timer2 still preempts it.
  - Timer1 (free: `_INSTANT_TIMER_EVENT_1` off, no UART) counts the MCU clock, which the SDK switches (XTAL / M2PLL / power-saving dividers); its reload would need recalculation at every switch. The WD counter runs on the crystal (SDK only rescales on XTAL <-> IOSC).
  - Gain is nil now: the watchdog check is in the Timer2 ISR and never reads or clears the WD counter.
- Separation done instead: the WD ISR keeps its counter clears (timer function); feeding, checks and the bite live in the main loop, wait helpers and Timer2 ISR.

## Verified in fw_sim (2026-11-11, image `AWT26110002-wb-p14ui-wdt3-be`, fast core)

- `crash_sim_test.py`: no reset over boot + 10 s ACTIVE + workload; 0x4C -> reset 805 ms after the command (limit window 800-1000 ms), PC `AwtoWdtHang+0xc` bank 0B, stack top = bank-return to bank 8 (caller `AwtoDiagTestCmd`); reboot to ACTIVE, console opens by itself, panel drawn; 0x4D -> PASS reset 5363 ms after (window 5200-5400 ms), PC `ScalerTimerDelayXms+0xd`; host clear -> invalid. PNG `tmp/wdt/crash_panel.png`.
- `key_sim_test.py` at f8e1afd (the #129 version; main's version expects later UI cards, fails identically on the baseline image): 28/28 PASS.
- `fw_sim.py --fast --boot-check`: PASS.
- Sim model: `ChipReset` = FFEE[1] -> CPU reset, bank 0, register cells to regdb reset values, RAM and P0_01 kept. The hardware WDT counter is not modelled.

## Needs hardware (unit 2)

- sof_rst from firmware resets the chip like the host's ISP write, and XDATA 0xF6B0 survives it.
- P0_01[6] after sof_rst / ISP 0xEE (kept = WARM count works) and after power-on (0).
- Reading P0_01 before `SysMainSystemInitial` returns the real value.
- 0x4E: the hardware backstop resets in ~4.7 s (CNT1 = 8) and the next boot counts it as warm.
- Real `max feed` / `max pass` over boot, 4K60 HDMI, DP, source switches, menu saves: confirm FEED 5 / PASS 27.

## Prior art

- Synopsys DW8051 datasheet (core has timers 0-2, serial, interrupt unit; no WDT): https://www.keil.com/dd/docs/datashts/synopsys/dw8051_ds.pdf (copy: `tmp/wdt/prior/dw8051_ds.pdf`)
- Dallas DS80C320 high-speed micro watchdog: interrupt first, reset 512 clocks later (pre-reset interrupt pattern): https://www.analog.com/en/resources/design-notes/using-the-highspeed-micros-watchdog-timer.html
- DS89C420 user guide, WDCON WTRF (latched watchdog reset flag, cleared by software; our chip lacks one): https://crlab.ece.ucr.edu/usbgps/doc/ds89c420_ug.pdf
- Keil forum, C51 crash handler (save the stacked return address in the handler): https://community.arm.com/support-forums/f/keil-forum/38486/c51-8051-crash-handler
- Embedded core dumps: PC + registers into no-init RAM, then a software reboot: https://www.codeproject.com/Articles/5376928/Designers-Guide-to-Embedded-Core-Dumps
- SDCC bug 2335: WDT during startup, handle it in `__sdcc_external_startup`: https://sourceforge.net/p/sdcc/bugs/2335/
