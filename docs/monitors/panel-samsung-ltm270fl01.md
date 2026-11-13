# Ruled out: Samsung LTM270FL01

- **Not the panel (2026-11-13):** Dan photographed the panel label: Innolux M280DCA-E3B rev C1, see [panel-innolux-m280dca-e3b.md](panel-innolux-m280dca-e3b.md). Kept for the history of the guess.

Panel's own EDID (597 x 336 mm) supports the 27" size: [panel-edid.md](panel-edid.md). Service menu names Innolux M280DCA-E3B (28"): [panel-innolux-m280dca-e3b.md](panel-innolux-m280dca-e3b.md). Model still unresolved.

Status: candidate only, not confirmed (size + measured active area match; many 27" 16:9 panels do). Best candidate is BOE MV270QUM-N20 (#3, panel-edid.md).
**Datasheet NOT obtained.** Only reseller/database listings read. Panelook is behind a slider CAPTCHA
(playwrong fetch fails; alt host `huasun.panelook.com` has a bad cert). alldatasheet.com has a "LTM270FL01"
PDF entry but it is a Samsung "PRODUCT SELECTION GUIDE" (28 pp, 3.3 MB), not the panel spec; PDF not fetched.
Real spec = Samsung Display "Product Specification" PDF, only via NDA/vendors (LCDPanels.com offers it by email).

## Listed specs (reseller/DB, not datasheet)
| Item | Value | Source |
|---|---|---|
| Resolution | 3840(RGB) x 2160, 163 PPI | [3] |
| Active area | 596.16 x 335.34 mm; bezel opening 602.0 x 340.4 | [1][3] |
| Mode | PLS, normally black, transmissive, a-Si TFT | [1][3][4] |
| Pixel format | RGB vertical stripe | [1][3] |
| Colours | 1.07B (10-bit, 8-bit + FRC or native 10 not stated) | [1][2][3][4] |
| "sRGB" tag | "1.07b [srgb]" | [1] |
| Frame rate | **60 Hz** (single value listed everywhere) | [1][3][4] |
| Interface | eDP, 4 lanes | [1][3] |
| Backlight | WLED | [1][3] |
| Luminance / CR | 350 cd/m2 typ / 1000:1 typ | [1][2][3] |
| Viewing angle | 89/89/89/89 typ (CR>=10) | [1][3] |
| Surface | matte, hard coat 3H | [1] |
| Temp | op 0~50 C, storage -20~60 C | [1][3] |

## Not found (state plainly)
- Max refresh other than 60 Hz: **no source lists >60 Hz.** 60 Hz is the only datasheet-level number seen.
- eDP link rate (RBR/HBR/HBR2), bpc mode, pixel clock typ/max, blanking limits (H/V total min/max).
- Primaries / white point / gamut %: not on any page read. "sRGB" tag is a DB label only.
- Whether any 120 Hz / VRR timing is in the panel's timing table.

## Derived (arithmetic, not from datasheet)
- eDP 4-lane payload (8b/10b): HBR 10.8 Gbps raw -> 8.64; HBR2 21.6 -> 17.28; HBR3 32.4 -> 25.92.
- 4K60 CVT-RB ~533 MHz: 24 bpp = 12.8 Gbps, 30 bpp = 16.0 Gbps -> needs HBR2 (HBR too slow). Link rate unconfirmed.
- 4K120 ~1.07 GHz: 24 bpp = 25.7 Gbps -> only just fits HBR3 8-bit; 30 bpp does not. A 60 Hz-rated 4K panel
  will not have HBR3/120 Hz timing; link maths is not the limit, the panel's rated timing is.
- Conclusion: no evidence of any > 60 Hz mode; treat 60 Hz as the panel ceiling.

## Mode recommendations for EDID (panel-feasible vs scaler-proven)
Ceiling = panel (60 Hz native). Real limit = RTD2795T scaler (Dan: observed max ~30-60 Hz at 4K).
| Mode | Pixel clk | Class | Note |
|---|---|---|---|
| 3840x2160@60 CVT-RB / CTA VIC 97 | ~533-594 MHz | panel-native; **scaler-unproven at 60** (observed 30-60) | keep as preferred/native only if scaler holds it |
| 3840x2160@30 (VIC 95) | 297 MHz | safe | fallback, DP+HDMI |
| 2560x1440@60 (CVT-RB) | 241.5 MHz | safe (scaler upscale) | not panel-native, scaler scales 1.5x |
| 1920x1080@60 (VIC 16) | 148.5 MHz | safe (integer 2x scale) | already present |
| 1080p120 / 1440p120 / 4K>60 | 297 / ~530 / >594 MHz | **panel-unsupported** (panel listed 60 Hz only) | scaler would decimate frames = fake refresh; do not advertise |
- Rule: advertise only modes the panel can show at their stated rate. >60 Hz at any res = scaler would have to
  decimate; not a real mode. Test any added high-refresh mode on hardware before shipping.
- Native/preferred DTD: 3840x2160@60 if hardware-verified at 60, else make 4K30 the DTD and 4K60 an extension block mode.

## Colour primaries
- Not in any source read. Keep sRGB/BT.709 default (R 0.640,0.330 G 0.300,0.600 B 0.150,0.060 W 0.3127,0.3290).
- Real values need the Samsung spec (CIE1931 R/G/B/W table) or a colorimeter measurement. [open]
- "1.07B [srgb]" in [1] is a DB class label, not measured primaries; do not treat as spec.

## Sources (fetched 2026-11-04, via playwrong)
1. https://www.twscreen.com/en/lcdpanel/14544  (Taiwan Screen spec table)
2. https://panelcd.com/product/ltm270fl01/  (panelcd.com; lists "Refresh rate: not specified")
3. https://www.lcddisplay-panel.com/cases/ltm270fl01-samsung-lcd-screen-introduction-to-the-functions-and-parameters-48649.html  (page dated 2026-03-11; full parameter list, bezel opening, 163 PPI)
4. https://agdisplays.com/ltm270fl01.html  (PLS, 60 Hz, 1.07B, eDP, AG surface)
5. https://lcdpanels.com/ltm270fl01/  (price/stock; datasheet by email to support@LCDPanels.com)
- Blocked: https://www.panelook.com/LTM270FL01_Samsung_27.0_LCM_overview_24453.html (CAPTCHA)
- Unfetched lead: https://www.alldatasheet.com/datasheet-pdf/pdf/1975836/SAMSUNG/LTM270FL01.html (selection guide only)

## Next steps
- Ask LCDPanels.com / Samsung rep for the Product Specification PDF; store in `~/vendors/samsung-display/`.
- Pass panelook CAPTCHA via playwrong `solve` (user) to read its parameter page (may list refresh/clock/eDP).
- Decode scaler firmware panel-config table (timing, lanes, link rate) to confirm the part + pixel clock limit.
