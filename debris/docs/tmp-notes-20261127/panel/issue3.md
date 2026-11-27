🤖 Panel = Innolux M280DCA-E3B rev C1 (label photo, Dan 2026-11-13). EDID size + primaries fixed; header renamed; power sequence checked (no value changed). Branch `wb-p14ui-panel` (705219a, b6a50c3), not merged.

**EDID** (`scripts/make_edid.py`, all ports D1 DP / D2 / D3 HDMI, all serials)
- The 597 x 336 mm (27") size was ours: copied from the panel TCON's template EDID (`MST` / `AGERA`, 2018) and a glass measurement. Datasheet: active 620.928 x 341.28 mm (28.0").
- Now: DTD image size 621 x 341 mm, base max image 62 x 34 cm.
- Primaries from datasheet 5.2 (typical, tentative): R 0.678/0.312, G 0.267/0.617, B 0.146/0.061, W 0.313/0.329. sRGB-default feature bit cleared (primaries are not sRGB).
- 20 bytes differ per EDID: size, feature byte, chroma, 4 DTD sizes, 2 checksums. Serials, modes, audio, port tag unchanged. `edid-decode -c` PASS, same warnings as before.

| | before | after |
|---|---|---|
| Max image size | 59 x 33 cm | 62 x 34 cm |
| DTD 1..4 size | 597 x 336 mm | 621 x 341 mm |
| Red | 0.6396, 0.3300 | 0.6777, 0.3115 |
| Green | 0.2998, 0.5996 | 0.2666, 0.6171 |
| Blue | 0.1503, 0.0595 | 0.1464, 0.0605 |
| White | 0.3125, 0.3291 | 0.3134, 0.3291 |
| Default sRGB colour space | yes | no |

**Header:** `fw/sdk/Panel/AWTO_LTM270FL01.h` -> `AWTO_M280DCA_E3B.h`, `_PANEL_TYPE _AWTO_M280DCA_E3B`, manufacturer `_PANEL_INNOLUX` (unused by code). Image vs main: 14 bytes differ, all the build-tag digit.

**Unit 3** (test unit, Intel HDMI-A-2 bus 11): image wb-p14ui-pnl2 (gates 27/27 PASS), flashed 2026-11-13T11:26+11:00 (224 sectors, verify OK). Live EDID at 0x50 = generator output, byte for byte; host re-read after a connector detect: 62 x 34 cm, DTD 621 x 341 mm, conformity PASS. Layout unchanged. Health 10/11 (delay cal tick 9.947 ms: known), ACTIVE 3840x2160@59.991, 298.7 loops/s.
Units 1 and 2: images built and gated (27/27 PASS each), not flashed.

**Power sequence: datasheet 4.8 vs the panel machine** (no value changed; Dan decides)

| datasheet | what | min / max ms | firmware | ms | measured | verdict |
|---|---|---|---|---|---|---|
| T1 | VDD 10 -> 90 % rise | 0.5 / 10 | T1 VDD on -> PHY / HPD | 10 | - | ok |
| T3 | VDD -> HPD | 15 / 200 | T2 HPD wait bound | 250 | 115 (unit 3, #78) | ok (1.25 x 200) |
| T6 | training end -> valid video | - / 100 | LINK -> stream | - | 54 (unit 2, #162 s2-7) | ok |
| T8 | valid video -> LED on | 200 / - | T3 | 550 | - | ok |
| T8 | same, own black frame | 200 / - | T3_OWN | 20 | 37 (unit 2, #162 s2-7) | **below min** |
| T9 | LED off -> video idle | 200 / - | T4 | 250 | - | ok |
| T10 | video end -> VDD off | 0 / 500 | T5 | 20 | - | ok |
| T11 | VDD off -> on | 1000 / - | T6 | 1100 | VDD decay not measured | ok if decay < 100 ms |

- T2, T7: panel-side. T4, T5: no limit.
- Proposal (not applied): T3_OWN >= 200 ms; costs ~165 ms to backlight on at boot / wake. Datasheet note 2: backlight before LCD operation may show a momentarily abnormal screen.
- Full table: `docs/monitors/panel-innolux-m280dca-e3b.md`.

**FreeSync (#21):** datasheet 40 / 60 / 62.5 Hz, Vtotal max 3520; "functional only". Any re-added range: at most 40-62.5 Hz.
