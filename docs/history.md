# History: superseded, refuted or wrong (one line each)

- Format: date | what was believed or tried | why superseded | link.
- Live docs and open issues hold current state only. Newest first, sections per area.

## 4K60 / display path (#26, #55)
- 2026-11-07 | DDR read-error bug parked; frame-buffer (FRC) path unusable | DDR frame buffer works: 4K60 frame memory clean, mirror H/V and rotate 180 verified by Dan on unit 3 (2026-11-13, images wb-p14ui-ddrinit, wb-p14ui-rot1) | #26, #165
- 2026-11-07 | P0_37, DPLL offset (+-10 %), static M-domain/FRC/DPLL config, DDR for the line buffer, memory select (frame-sync line buffer) as cause of 4K60 NOSUPPORT | all equal the vendor in the failing state; M1 FIFO flag returns within a frame with firmware frozen | #26
- 2026-11-07 | IVS2DVS phase and fine-tune passes as cause | ruled out on hardware | #26
- 2026-11-07 | HDMI 2.0 RX link errors at 594 MHz (lanes 1/2) as cause | refuted: offline config diff, live SCDC and 6 PHY trials; SCDC errors equal on the vendor firmware | #55
- 2026-11-07 | EDID DTD1 = 3840x2160@60.000, 594 MHz (VIC 97), `make_edid.py` ab8c4c9 | vendor EDID never preferred it; vendor DTD1 is 3840x2160@59.982, 533.12 MHz (panel-native 4000x2222); 594 MHz not pursued, 4K59.94 works | #26
- 2026-11-07 | FRC/frame-buffer modes (4K24/25/30/50, 1080p50) to be made to work | DDR read-error bug parked (p3); modes dropped from the EDID | #26, #36
- 2026-11-04..05 | `_FRC_SUPPORT` cut for bring-up | without FRC 4K60 cannot set the display (equal line times 7.40 us); turned back ON | #8, #26

## GPIO / board (#7)
- 2026-11-06 | P8.5 = backlight enable (high = on), SDK name `bBACKLIGHTPOWER` | backlight enable is P9.2 (FE2A) active low, proven live with `rtd_reg_poke.py`; P8.5 only follows it | #7, `docs/monitors/gpio-roles.md`
- 2026-11-05 | P9.2 = standby LED (probable) | it is the backlight enable | #7

## Toolchain / speed measurements (#11, #23)
- 2026-11-06 | main-loop rate 278/s vs 172/s between images | artefact of `rtd_diag`'s single-read figure (u16 counters wrap at 65 s, boot time in the denominator); not comparable between images | #11
- 2026-11-06 | "register calls are faster" | the 6-byte stubs cost -6.5 % loop rate, ABI 1 a further ~-2.5 %; register calls bought size, not speed | #11, `docs/speed-bench.tsv`
- 2026-11-06 | wb-step2/stepA/stepB contain the fixed compiler | built with the stale `rc-be-install-sc1` (pre-41a2b76); 345->406/s gains were stub + layout only; `fw_build` now refuses stale stamped installs | #11
- 2026-11-06 | Keil PK51 (~A$284/month) vs SDCC, "needs-dan" | decided: SDCC fork with register calling convention (awto-sdcc), not Keil | #11
- 2026-11-05 | trunk SDCC `genconstprop` folds `ScalerTimerDelayXms` into an endless loop | fixed with `--nogenconstprop` | #23
- 2026-11-06 | "stall at stage 4" in the simulator | harness artefact (`fw_sim --serial` stopped after 300 samples, read stale `fw.bin`) | #11

## Timing / delays (#40, #54)
- 2026-11-06 | TMDS pre-detect treated as ~1 ms | 6 ms blind per call (D081/D086) | #40, `docs/delays.md`
- 2026-11-06 | `0x830B6229` ulDclk in the simulator read as a firmware fault | sim artefact (unmodelled P30_41..49 counts) | #38

## Debug / recovery (#35, #48, #52)
- 2026-11-06 | self-recovery hooks (power-key reset, DDC bus watchdog, main-loop canary) on by default | no image booted with them on; behind `_AWTO_SELF_RECOVERY _OFF`, re-introduce one at a time | #35
- 2026-11-06 | safe-window / `dev.py recover --hold` available on every image | the safe block (0xF6B0) exists only on the main line; on working-base 0xF6B0.. is live firmware XDATA, so the hold corrupts globals; recover must hold only when the map has `_g_stAwtoSafe` | #52, #48
- 2026-11-05 | debug slave 0x35 usable at 1 MHz | NAKs intermittently (2 of 4 diag reads failed); 100 kHz only. ISP slave 0x4A is clean at 1 MHz | `docs/flash-burst.md`, #12

## Docs retired
- 2026-11-13 | panel = 27" (597 x 336 mm, BOE MV270QUM-N20 / Samsung LTM270FL01); input EDID size 597 x 336 mm + sRGB primaries | panel label (Dan's photo): Innolux M280DCA-E3B rev C1, 28"; the 597 x 336 mm was ours (copied from the TCON template EDID); EDID now 621 x 341 mm + datasheet primaries | #3
- 2026-11-04 | panel = Samsung LTM270FL01 (closest by size) | panel EDID read over eDP AUX (MST/AGERA, 2018); best candidate BOE MV270QUM-N20, unconfirmed | #3
- 2026-11-07 | `docs/handover.md` (2026-11-05 snapshot: unit table, "verify the flash lights the panel", Keil-vs-SDCC pending, P8.5 backlight) | all items done or superseded; state lives in issues #7, #26, #38 | git history
- 2026-11-07 | `docs/firmware-proposal.md` patch routes A/B and EDID-fail list | firmware is our own build on the SDK (#7); EDID failures fixed (`docs/edid-fix.md`) | #7
- 2026-11-04 | persistent boot-splash patch of the vendor image | our firmware draws the logo (confirmed on unit 3, `dev.py osd logo`) | #5, #46

## Front keys, naming, test units (#85, #91)
- 2026-11-04 | key labels in `buttons.md`: MENU "almost certainly 0x10 (sole long-press key)", DOWN/UP "the symmetric pair", SOURCE/AUTO "order unconfirmed" | wrong for 5 of 6 keys; settled 2026-11-08 by Dan's presses on unit 2 (ADC readings) + the Dahua dispatch trace: MENU 0x02, UP 0x04, DOWN 0x08, AUTO 0x10 (the long-press key), SOURCE 0x20 | #85, #91
- 2026-11-04 | board header kept the SDK reference keypad (LEFT/RIGHT/EXIT, `QA_B`) for the JXC board | replaced by the JXC ladder decode (keys4+); earlier combos (#34, #60, #67, #79) used keys this monitor does not have | #85, #91
- 2026-11-05 | 'AUTO long press = auto-adjust / lock / factory entry' (guess in chat) | timer 0xD has no consumer in banks 0-6; a held AUTO does nothing extra [fw, medium] | `docs/reversing/dahua-fw/keys.md`
- 2026-11-05 | 'IR/key_alt_source_poll role unknown', '8 bytes at 0xFF:3067 are a code table' | it is the IR path (NEC); the 8 bytes are the zero initialiser | #93, `dahua-fw/gpio-ir.md`
- 2026-11-05 | 'no audio-mute GPIO' (gpio-roles.md), 'P9.7/PA.0 never written' | P7.4 is the speaker-amp enable, P4.5 the jack select; P9.7/PA.0 follow the power state | #93, #95
- 2026-11-07 | all three units free for tests (units 1/2 after an image booted on unit 3) | from 2026-11-08 only unit 2 (lower left, HDMI-A-2 + DP-1, so-th-1 relay); units 1 and 3 are Dan's working screens | `scripts/devices.json`, #85
- 2026-11-08 | `docs/osd-vendor-menu.md`, 'vendor menu' | said "vendor" for the Realtek SDK demo menu; renamed `osd-realtek-sdk-menu.md`; terms: Dahua firmware / Realtek SDK menu / awto menu | `docs/osd.md` naming, #87
- 2026-11-08 | menu keys MENU = open, AUTO = back (keys4/5) | Dan: AUTO = open, MENU = back (keys6, unverified) | #85
