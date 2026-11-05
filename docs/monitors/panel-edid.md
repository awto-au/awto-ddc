# Panel EDID and DPCD (read from the panel over eDP AUX)

- Read 2026-11-05 on unit AWT26110001 with `scripts/rtd_panel_aux.py` (scaler DPTX TX1 AUX, page 9D; MCU halted, reset after). Raw: `tmp/regs/AWT26110001-panel-aux-20261105-134943.*`. Issue #3.
- Separate from the monitor's input-side EDIDs (`jxc-4k-edid.bin`, flash 0x138d8..).

## EDID (128 B, no extension)
| Field | Value |
|---|---|
| ID | `MST`, product 30036 (0x7554), serial 1, week 51/2018, EDID 1.4 |
| Strings | name `AGERA`, serial `001` |
| Input | digital DisplayPort, 10 bpc, sRGB default, max image 60 x 34 cm |
| Primaries | R 0.6523/0.3339, G 0.3066/0.6367, B 0.1503/0.0595, W 0.3125/0.3291 |
| DTD 1 | 3840x2160 @59.9966 Hz, 533.25 MHz, image 597 x 336 mm |
| Horizontal | 3840 + HFP 48 + sync 32 + BP 80 = 4000 |
| Vertical | 2160 + VFP 3 + sync 5 + BP 54 = 2222 |
| Range limits | 40-60 Hz, 135 kHz, max 600 MHz |

## DPCD
- Rev 1.4, max link rate 0x14 (HBR2), 4 lanes, enhanced framing, TPS3, no-AUX-handshake LT.
- Sink OUI / device ID (0x400..0x40B): all zero.

## Reading
- 597 x 336 mm = 27" class; matches measured 336 mm and LTM270FL01 (596.16 x 335.34); not M280DCA-E3B (620.9 x 341.3).
- Timing equals the M280DCA-E3B datasheet typical (533.28 MHz, 4000 x 2222), so timing does not separate the candidates.
- `MST` / `AGERA` is not a panel-maker ID; no model string in the EDID.
- Use for firmware panel header: DTD above, 10 bpc, 4-lane HBR2.

## Candidate: Innolux M270DCA-E5B (panelook overview, pasted by Dan 2026-11-05)
- 27.0" LCM, a-Si TFT, AAS (IPS family), 3840x2160, active 596.736 x 335.664 mm (EDID: 597 x 336), 350 cd/m2, 1000:1, 10-bit (1.07B), 99% sRGB.
- eDP 4 lanes HBR2 (5.4G/lane), 51-pin 0.5 mm, 12 V, 60 Hz, WLED without driver, 21.63 W typ.
- Dates: customer sample 2022-Q3, mass production 2023-Q4 (EDID says week 51/2018: unexplained; template date or earlier revision).
- Family: M270DCA-D5B (cell, discontinued), D7B (cell, 16.7M colours), E5B (LCM). No E3B in the 27" family.
- Datasheet: panelook `M270DCA-E5B.pdf` Ver3.0, 2022-09-23, 42 pages, 6.1 MB. NOT fetched (panelook CAPTCHA / bad cert on the huasun mirror). Store in `~/vendors/innolux/M270DCA-E5B/`.
- To confirm: its timing table (Fc / Htotal / Vtotal) against the EDID DTD (533.25 MHz, 4000 x 2222).

## Datasheet in hand: BOE MV270QUM-N50 (same 27" 4K family, not Innolux)
- `~/vendors/boe/MV270QUM-N50/MV270QUM-N50_spec_ver0_20210111.pdf` (Ver 0, 2021-01-11).
- 27", 3840x2160, active 596.736 x 335.664 mm (identical to Innolux M270DCA-E5B), 4-lane eDP 5.4 Gbps, 10-bit, sRGB 100% typ.
- Timing (min/typ/max): DCLK 444/533/551 MHz; tHP 3950/4000/4088; tHB 110/160/248; tVP 2213/2222/2290; tVB 53/62/130; fV 50/60/62 Hz (adaptive 40-60).
- EDID DTD (533.25 MHz, 4000 x 2222, hblank 160, vblank 62) equals the typical column exactly.
- So the 597 x 336 mm / 4000 x 2222 timing is the generic 27" 4K eDP panel standard, shared by BOE and Innolux. Neither the timing nor the size names the maker.
- BOE MV270QUM-N20 (earlier sibling, 350 nits) fits the EDID date (week 51/2018) better than N50 (2021) or Innolux E5B (2023).
- Power sequence (section 8.0): T1 0.5-10 ms, T2 0-200 ms, T3 link training, T4 >=500 ms, T5 >=100 ms, T6 0-50 ms (recommend 0), T7 0-10 ms, T8 >=1000 ms. Use for the firmware panel header.
