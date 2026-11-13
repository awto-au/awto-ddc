# Panel: Innolux M280DCA-E3B rev C1 (JXC/Dahua 4K, RTD2795T)

- **Confirmed 2026-11-13 by Dan from a photo of the panel label: Innolux M280DCA-E3B, revision C1.** The Samsung LTM270FL01 (`panel-samsung-ltm270fl01.md`) is NOT the panel; the 27" EDID size was wrong.
- Name source before: service menu reads `M280DCA-E3B` (Dan, 2026-11-05).
- Datasheet: `~/vendors/innolux/M280DCA-E3B/M280DCA-E3B_spec_v0.0_20190311.pdf` (Innolux tentative spec Ver0.0, 2019-03-11).
- The 597 x 336 mm (27") in our input EDIDs was ours and wrong (copied from the TCON template EDID, [panel-edid.md](panel-edid.md)); fixed to 621 x 341 mm + datasheet primaries (`docs/edid-fix.md` "Current").

## Spec (datasheet)
| Item | Value |
|---|---|
| Size / active | 28.0", 620.928 x 341.28 mm; module 631.928 x 359.78 x 15.5 mm |
| Resolution | 3840x2160, 1.073G colours (8-bit+FRC), 10-bit input mapping |
| Interface | 4-lane eDP, HBR2 5.4 Gbps, JAE FI-RXE51S-HF 51-pin, 12 V (10.8-13.2) |
| Pixel clock | 480 / 533.28 / 560 MHz (min/typ/max) |
| Htotal | 3980 / 4000 / 4020 |
| Vtotal | 2200 / 2222 / 3520 |
| Frame rate | 40 / 60 / 62.5 Hz; FreeSync functional only (#21) |
| Optics | 300 cd/m2 typ, CR 1000 typ, 178/178 deg, DCI-P3 90% typ, AG25 3H |
| Backlight | WLED, 30k h, external driver (4 pins x 65 mA) |
| Primaries (CIE1931) | Rx 0.678, Ry 0.312, Gx 0.267, Gy 0.617, Bx 0.146, By 0.061 (tentative, in parentheses in the spec; +-0.03), W 0.313/0.329 |

## Match against live registers (#7, unit 1 rip)
- HBR2 x4 on TX1, 10 bpc, Htotal 4000 (= typ), Vtotal 2251 (in range), ~540 MHz (in range): consistent.
- The 2026-11-04 glass measurement (~336 mm height) does not match 341.28 mm active; the label + datasheet win (re-measure if it matters).

## FreeSync / adaptive sync (#21)
- Datasheet frame rate 40 / 60 / 62.5 Hz (min/typ/max); Vtotal up to 3520 lines = 40 Hz at 533 MHz / 4000. "FreeSync: functional only" (no optical/cosmetic guarantee).
- So a re-added FreeSync range is at most 40-62.5 Hz. Today: EDID range 48-60 Hz, panel header 59.0-61.0 Hz; no change made.

## Firmware
- Panel header limits = datasheet (2026-11-13): Htotal 3980 / 4000 / 4020 (was 4000 / 7040), pixel clock 480 / 533 / 560 MHz (was 160 / 600).
  - Consequence (sim, fw_sim_vfreq, 2026-11-13): line-buffer frame sync keeps Vtotal 2250 and scales the DCLK with the input rate, so only ~53-62.5 Hz inputs fit; 1080p50, 2160p50, 1080p30, 1080p24 now NO SUPPORT (before: shown at DCLK 450 / 270 / 216 MHz, below the panel's 480 MHz min). 1080p60, 2160p60, 2160p59.94 unchanged.
- Panel header `fw/sdk/Panel/AWTO_M280DCA_E3B.h` (`_AWTO_M280DCA_E3B`; renamed from AWTO_LTM270FL01.h 2026-11-13, image byte-identical).
- Input EDIDs: size + primaries from this datasheet (`scripts/make_edid.py`).

## Power sequence: datasheet 4.8 vs the firmware panel machine (checked 2026-11-13, no value changed)
Datasheet (source = monitor, sink = panel). Firmware: `UserCommonInterfacePanelStep` (UserCommonInterface.c), defaults in the panel header = registry `PANEL_T*`.

| datasheet | what | min / max ms | firmware | value ms | measured | verdict |
|---|---|---|---|---|---|---|
| T1 | VDD 10 % -> 90 % rise | 0.5 / 10 | T1: VDD on -> PHY / HPD read | 10 | rise not measured (board) | ok: wait >= max rise |
| T2 | VDD -> panel black video | 10 / 200 | (sink) | - | - | panel side |
| T3 | VDD -> HPD high | 15 / 200 | T2: HPD wait bound | 250 | VDD -> HPD 115 ms unit 3 (#78); unit 2 cold boot HPD seen 78 ms after PHY (PHY gated by power NORMAL) (#162 s2-7) | ok: bound = 1.25 x 200 |
| T4 | HPD -> link training | - / - | LINK step | - | - | no limit |
| T5 | link training | - / - | `ScalerDisplayDPTxLinkSequence` | - | ~32 ms (#162) | no limit |
| T6 | training end -> valid video | - / 100 | stream start after training + Mvid measure | - | link 380 -> stream 434 = 54 ms (unit 2, s2-7) | ok |
| T7 | valid video -> panel shows it | 0 / 50 | (sink) | - | - | panel side |
| T8 | valid video -> LED on | 200 / - | none: backlight on with VDD (registry `bl_on_delay`, default 0) | 0 | - | **not followed (Dan)** |
| T9 | LED off -> video idle | 200 / - | T4 | 250 | - | ok |
| T10 | video end -> VDD off | 0 / 500 | T5 (+ SSC / PHY off) | 20 | - | ok |
| T11 | VDD off (10 %) -> VDD on | 1000 / - | T6 (from the VDD-off edge) | 1100 | VDD decay not measured | ok if decay to 10 % < 100 ms |

- T8 is deliberately NOT followed (Dan, 2026-11-13, repeated decision): backlight on immediately after power-up once the MCU is on the M2PLL clock, not gated by video. Accepted risk per datasheet note 2: a momentarily abnormal screen. Firmware: design-162.md "Backlight at once"; registry T3 rows retired.
- T6 vs T11: datasheet counts from VDD at 10 %; firmware from the switch edge. Margin 100 ms; the VDD decay time is not measured.
- Not in the datasheet: `_PANEL_POWER_ON_BL_TO_PWM` 50, `_PANEL_POWER_OFF_PWM_TO_BL` 50 (SDK defaults, Panel_Default.h; external LED driver).
