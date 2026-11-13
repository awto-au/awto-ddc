# Panel: Innolux M280DCA-E3B rev C1 (JXC/Dahua 4K, RTD2795T)

- **Confirmed 2026-11-13 by Dan from a photo of the panel label: Innolux M280DCA-E3B, revision C1.** The Samsung LTM270FL01 (`panel-samsung-ltm270fl01.md`) is NOT the panel; the 27" EDID size was wrong.
- Name source before: service menu reads `M280DCA-E3B` (Dan, 2026-11-05).
- Datasheet: `~/vendors/innolux/M280DCA-E3B/M280DCA-E3B_spec_v0.0_20190311.pdf` (Innolux tentative spec Ver0.0, 2019-03-11).
- Status (superseded 2026-11-13, see above): name from the service menu only. Panel EDID (read 2026-11-05, #3) says 597 x 336 mm (27"), which does not match this 28" part; see [panel-edid.md](panel-edid.md). Samsung LTM270FL01 is the size match.

## Spec (datasheet)
| Item | Value |
|---|---|
| Size / active | 28.0", 620.928 x 341.28 mm; module 631.928 x 359.78 x 15.5 mm |
| Resolution | 3840x2160, 1.073G colours (8-bit+FRC), 10-bit input mapping |
| Interface | 4-lane eDP, HBR2 5.4 Gbps, JAE FI-RXE51S-HF 51-pin, 12 V (10.8-13.2) |
| Pixel clock | 480 / 533.28 / 560 MHz (min/typ/max) |
| Htotal | 3980 / 4000 / 4020 |
| Vtotal | 2200 / 2222 / 3520 |
| Frame rate | 40 / 60 / 62.5 Hz; FreeSync functional only |
| Optics | 300 cd/m2 typ, CR 1000 typ, 178/178 deg, DCI-P3 90% typ, AG25 3H |
| Backlight | WLED, 30k h, external driver (4 pins x 65 mA) |
| Primaries (CIE1931) | Gx 0.267, Gy 0.617, Bx 0.146, By 0.061, W 0.313/0.329 (values in parentheses in the spec) |

## Match against live registers (#7, unit 1 rip)
- HBR2 x4 on TX1, 10 bpc, Htotal 4000 (= typ), Vtotal 2251 (in range), ~540 MHz (in range): consistent.
- Not consistent: measured picture height ~336 mm vs 341.28 mm active (docs/edid-fix.md); re-measure the lit area.

## Follow-ups
- EDID: use the datasheet primaries instead of the LTM270FL01 database label.
- `fw/sdk/Panel/AWTO_LTM270FL01.h` name is provisional; rename once confirmed.
- Power sequencing: datasheet section 4.8 (T1..T11) feeds the firmware panel power-on code.
