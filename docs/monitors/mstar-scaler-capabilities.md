# MStar monitor scalers: Philips 288E2 and the family vs our RTD2795T

Research 2026-11-19. Read-only: no hardware access this pass (probe data from the Philips probe branch), no GitHub writes.
Tags: `[measured]` probe on the 288E2 (2026-11-19), `[web]` public page (URL given), `[vendor-doc]` repo/vendor-store source file, `[guess]` our reading.

## Summary
- The 288E2 reports MStar (VCP 0xC8 sl=0x05), controller 0xFF16, firmware 1.0, MCCS 2.2 `[measured]`; exact part number is unknown (TSUM / MST9U / MSD / MT9xxx all fit).
- MStar 4K60 monitor parts (MST9U11/13/25 class) are public only through reseller blurbs: DP 1.2a, HDMI 2.0, eDP / V-by-One / LVDS out, 32-bit MCU `[web]`; no public datasheet read.
- Versus our RTD2795T: same job (scaler + OSD + DDC/CI + SPI-flash ISP over the DDC bus); different CPU (8051 vs 32-bit), different ISP address (0x49 + "MSTAR" magic vs 0x4A), no public register DB for MStar.
- A debug route exists on paper: ISP at I2C 0x49 via `flashrom -p mstarddc_spi`, flash read by the dumper project; unverified whether it answers through DP AUX on this unit.
- Reads need no OK; any ISP write, hidden-VCP write or opening the case needs Dan. It is Dan's own display (issue #136).

## 1. What we know about the 288E2 scaler

### Identity evidence
| claim | tag | source |
|---|---|---|
| EDID `PHL 288E2`, product 0xC231 (49713), serial UK52307000611, week 7/2023, DP, 10 bpc, EDID 1.4 | measured | `tmp/philips/20261119-edid-decode.txt` (probe branch) |
| Native 3840x2160 (DTD 533.25 MHz), also 2560x1440 and 1920x2160 DTDs in CTA block; range 40-60 Hz | measured | same |
| No HDR static metadata block, no DisplayID, no VRR range in EDID | measured | same |
| VCP 0xC8 = Mstar (sl 0x05); controller mh 0xFF, ml 0x16 | measured | `20261119-vcp-scan.txt` |
| VCP 0xC9 firmware 1.0; 0xDF MCCS 2.2 | measured | same |
| Caps string: `model(288E2)`, `asset_eep(40)`, `mswhql(1)` | measured | `20261119-caps.txt` |
| Same 0xFF16 controller id on another MStar monitor | web | https://github.com/memues/mstar-monitor-firmware-dumper |
| Panel Innolux M280DCA-E3B, 28" | web | https://pcmonitors.info/reviews/philips-288e2uae-288e2e/ (no scaler named there) |
| Scaler vendor of the 288E2 named by any web source | unknown | none found |

- "MStar" claim rests on the 0xC8 VCP value only; no teardown or board photo found `[web]`.
- Panel: 4K60 IPS-class, native 533.25 MHz pixel clock (same family of timing as our unit's 533.12 MHz DTD, `docs/history.md`).

### VCP table highlights (full scan 0x00..0xFF, 1 transaction per code, 0 errors) `[measured]`
- Standard readable: 0B 0C 10 12 14 16 18 1A 1E 20 30 52 54 60 62 6C 6E 70 72 86 8D 95-98 A5 AA AC AE B6 C0 C6 C8 C9 CA CC D6 DA DC DF.
- Capabilities advertise a full window set (95-98, A5), gamma presets 1.8/2.0/2.2/2.4/2.6 (0x72), display scaling modes (0x86: no scaling, max image, linear), colour presets sRGB / 5000 / 6500 / 7500 / 8200 / 9300 / 11500 K / user 1 (0x14).
- Input values in caps include VGA-1 (0x01), HDMI-1/2 (0x11/0x12), DP-1 (0x0F) plus 0x21/0x22/0x2F/0x31; current = 0x0F `[measured]`. VGA/0x2x/0x3x entries are probably a generic scaler table, not physical ports `[guess]`.
- 0xAC = 2228 Hz, 0xAE = 59.99 Hz, 0xC0 = 13769 h (usage time; 0x006F in C6 `[measured]`).
- Write-only (not readable): 01 04 05 06 08 0A 76 8B A2 B0 CF. 04/05/08 are factory/colour resets: deliberate only, with Dan's word (section 5).
- 0xDC display mode values: 00 standard, 01 productivity, 02 mixed, 03 movie, 05 games, 08 intermediate-power, 1F `[measured]` (caps).
- 0xCA OSD/button control: 01 OSD disabled + button events, 02 OSD enabled `[measured]` (caps); lets a host take the keys.

### Manufacturer codes (mh ml sh sl) `[measured]`
| code | value | caps values | note |
|---|---|---|---|
| E0 | 00 04 00 03 | 00-03 | |
| E6 | 00 01 00 01 | not in caps | readable anyway |
| E7 | 00 64 00 32 | | 0x64 max, 0x32 cur |
| E9 | 00 02 00 02 | 00 02 | |
| EB | 00 03 00 00 | 00-03 | |
| EC | 04 03 00 00 | 00-03 | |
| EF | 00 FF 00 FF | 00-04, FF | |
| F0 | 00 01 00 00 | 00 01 | |
| F7 | 00 42 00 42 | 42 FF | |
| FA | FF FF 00 00 | 00 01 02 | |
| FB / FC / FD | 00 FF 00 05 / 02 / 02 | | |
| FE | FF FF 00 00 | 00 01 02 04 | |
| F6, FF | in caps, not readable | F6: 01 | |
- Meaning of every manufacturer code is unknown `[guess]` only: E7 (max 0x64) looks like a 0-100 level; E0/EB/EC/EF/FA/FE look like small mode enums.
- Also readable but not in caps: 0x68 (00 05 00 00), 0xA8 (00 03 00 00) `[measured]`.

### Hidden-code leads
- TPV/MMD do not document VCP codes (ddcutil discussion #642, Philips Evnia) `[web]`, via probe README.
- Method that works elsewhere: sniff DDC/CI from the vendor app (SmartControl, V6.8.0.00 history in `/vendors/mstar/docs/philips-288E2-Smart_control_FHI.pdf`) `[web]`.
- LG DualUp (MST9W00V4) had a hidden factory command that copies bytes into scaler memory `[web]` https://forums.blurbusters.com/viewtopic.php?f=7&p=91093 ; same on Philips: unknown.
- AOC (TPV brand) service menu: unplug, hold MENU, plug in `[web]` (reddit, unverified for this model).
- Candidates for a first diff: E-range codes read before/after OSD changes (reads only) `[guess]`.

## 2. MStar family capabilities

Public detail is thin: reseller blurbs and board-vendor pages, no datasheet read. Datasheets found online are watermarked non-public copies (not downloaded; `/vendors/mstar/README.md`).

| claim | value | tag | source |
|---|---|---|---|
| MST9U13Q1 resolution | up to 4096x2160 panel | web | https://www.globalsources.com/knowledge/mstar-ic-for-uhd-lcd-controller-boards/ (2023-12-01) |
| MST9U13Q1 inputs | DVI / HDMI 2.0 / MHL 3.0 / DP 1.2a (5.4 Gb/s per lane), integrated ADC/PLL | web | same |
| MST9U13Q1 panel out | eDP (2.7 Gb/s), V-by-One, LVDS | web | same |
| MST9U13Q1 engine | 10-bit display processing, RTE response-time engine, two-window PIP/PBP | web | same |
| MST9U13Q1 CPU | 32-bit microcontroller | web | same |
| MST9U13Q1 misc | power management, spread spectrum | web | same |
| MST9U25Q1 | UHD HDR, scaling engine to 3840x2160 eDP panel, V-by-One | web | https://www.globalsources.com/product/controller-ic_1173266056f.htm (truncated read) |
| MST9U03V2 board | 4K2K 60: DVI, HDMI x2, DP x2, VGA; out VX1/eDP; PIP/POP | web | https://en.panvision.com.tw/program/4 |
| MST9U11 / MST9U13 board | 4K2K 60: VGA, DP, HDMI x2; out VX1/eDP/LVDS; 10 W x2 audio; PIP/POP, RS232 option | web | same |
| MSD91H1BNX board | 4K2K 60: DVI, HDMI x3, VGA; out VX1 (TV-class SoC) | web | same |
| TSUMU88CMT9-1 board | 1080p60, HDMI, LVDS, 2 W x2 audio (QFP128) | web | same |
| MSD8220LBP board | 1080p60, VGA/HDMI/CVBS, LVDS, 5 W x2, USB play | web | same |
| MST9W00V4 CPU | AEON R2 (custom 32-bit, OpenRISC-based) | web | https://forums.blurbusters.com/viewtopic.php?f=7&p=91093 ; `/vendors/mstar/sources/linux-chenxing-docs/cpu/aeon-r2.md` |
| Older TSUM parts CPU | embedded 8051 | web | https://github.com/csurf/mstar (README, via history branch `docs/monitors/mstar-vs-realtek.md`) |
| MStar TV SoC CPUs | MIPS / ARM / AEON | vendor-doc | `/vendors/mstar/sources/linux-chenxing-docs/cpu/index.md` |
| Firmware toolchain (TSUM class) | Keil uVision project | web | csurf README |
| ISP address | I2C 0x49 (0x51 on MSB123xC), "MSTAR" (4D 53 54 41 52) sync string, command set write 0x10 / read 0x11 / end 0x12 / reset 0x24 | vendor-doc | `linux-chenxing-docs/isp/index.md`, `flashrom-upstream/programmers/mstarddc_spi.c` |
| ISP bus speed | "very slow" over DDC | vendor-doc | `isp/index.md` |
| SPI flash (0xFF16 monitor) | Macronix MX25L8005 (1 MB) per dumper project | web | https://github.com/memues/mstar-monitor-firmware-dumper |
| Distributor price | MST9U13Q1 $28 (MOQ 100), MST9U25Q1 $35 (MOQ 288) | web | Global Sources pages above (supplier claim) |

Not found in any public source read: DSC, FreeSync / VRR support per part, local dimming, USB-C DP alt, KVM / USB hub, HDR tone mapping details, 6-axis colour, PWM backlight, OSD engine capabilities, DP 1.4 / HBR3, HDMI 2.1 parts, power figures. Marked "not found", not "absent".

## 3. Comparison: MStar (288E2 class) vs our RTD2795T

| feature | MStar (288E2 class) | RTD2795T (our RL6449 build) | note |
|---|---|---|---|
| Identity over DDC | VCP C8 = Mstar, ctrl 0xFF16 [measured] | C8 = 0x09 Realtek (our `vcp.c`), `docs/ddcci.md` | we answer our own C8 |
| MCU | 8051 (older), 32-bit AEON R2 (MST9x) [web]; 288E2 unknown | DW8051, bank-switched, SDCC build `docs/keil-vs-sdcc.md` | DW8051 is Synopsys IP |
| Max video | 4K60 native on 288E2 [measured]; MST9U13 up to 4096x2160 [web] | 4K59.94 working, 4K60.000 / 594 MHz not pursued `docs/history.md` | |
| Inputs | caps: DP, HDMI x2 (VGA entry) [measured]; HDMI 2.0, DP 1.2a [web] | DP D1, HDMI D2/D3 (`docs/ddcci.md` code 60) | |
| Panel interface | eDP / V-by-One / LVDS [web] | eDP (panel EDID read over eDP AUX, `docs/history.md`) | 288E2 interface unknown |
| ADC / VGA | integrated ADC/PLL on MST9U13 [web] | not used on our board | |
| OSD | MStar OSD engine, details unknown | glyph cells + windows, no framebuffer; `docs/osd.md`, `docs/osd/README.md` | |
| DDC/CI | MCCS 2.2, 0x37, full standard VCP set [measured] | MCCS 2.2 on IIC_1 at 0x37, registry-driven `docs/ddcci.md` | |
| ISP / flash access | I2C 0x49 + "MSTAR" magic, flashrom driver [vendor-doc] | ISP slave 0x4A (clean at 1 MHz), debug slave 0x35 `docs/flash-burst.md` | Realtek ISP is faster; MStar via DDC "very slow" |
| Flash | MX25L8005 1 MB on a sibling unit [web] | see `docs/flash-layout.md` | |
| Frame memory / FRC | unknown (RTE engine named) [web] | DDR frame buffer works, FRC on `docs/history.md` | |
| Rotation / mirror | unknown | mirror H/V, 180 verified on unit 3 `docs/history.md` | |
| Scaling | caps: no scaling / max image / linear (0x86) [measured] | scale-up windows `docs/osd/limits.md` | |
| Colour | sRGB + K presets, gamma 1.8-2.6, window codes 95-98 [measured] | colour + six-axis pages `docs/ddcci.md` | MStar 6-axis not confirmed |
| Audio | 2 ch LPCM in EDID [measured]; 288E2 has speakers? unknown | embedded DAC to PAM8006A, DVC volume `docs/audio.md` | |
| Keys | unknown | ADC ladders A0/A1 + P3.0 `docs/keys.md` | |
| HDR / VRR | none in EDID [measured]; MST9U25 names HDR [web] | not implemented | |
| Public register docs | none (chenxing wiki covers other MStar SoCs) [vendor-doc] | `re/regdb` | biggest gap for us |
| Firmware ownership | Philips firmware only | our own SDK build | |

## 4. A diag / debug / ISP route (nothing done)

- ISP over DDC: I2C 0x49 on the DDC channel; send "MSTAR" as one transfer; commands 0x10/0x11/0x12; `flashrom -p mstarddc_spi:dev=/dev/i2c-N:0x49` `[vendor-doc]` (`isp/index.md`, `mstarddc_spi.c`).
  - Flashrom driver does a chip reset at the end unless told not to (`mstarddc_spi.c` shutdown path): a read can reboot the scaler `[vendor-doc]`.
- Dumper project: reads an 0xFF16 monitor's MX25L8005 over ISP, tested on HDMI `[web]`.
- Open on this unit:
  - DP I2C-over-AUX acked every address (2026-11-05), so a 0x49 ACK says nothing `[measured]`.
  - Whether 0x49 is reachable through DP AUX at all: unknown. HDMI DDC is the tested path (`[web]`); the 288E2 has HDMI ports (caps).
  - UART / ISP header on the board: unknown, no teardown found.
  - Flash chip, DPCD identity (host is NVIDIA proprietary for DP-2, no DPCD node): unknown.
- A second route: sniff SmartControl DDC traffic for undocumented codes `[web]` method; the plan, in progress: `docs/monitors/smartcontrol-wine.md`.

## 5. Risks of touching it

- Any VCP write to 04 / 05 / 08 (factory / colour reset) or an unknown E/F code can change stored settings or enter a service state `[guess]`.
- ISP: the "MSTAR" sync puts the scaler in a mode where flash is exposed; interrupted sessions may leave it in reset or with the OSD/DDC dead `[guess]`; recovery needs an external programmer on the flash (not found for this board).
- flashrom resets the chip at the end by default `[vendor-doc]`.
- The LG DualUp updater bricked a monitor during a sniff attempt `[web]` (blurbusters thread).
- Our rules: monitor flash writes only on Dan's word and only on the `test` unit; this 288E2 is excluded from every flash/DDC test script by EDID serial (#136).

## 6. Ranked next steps

Reads, no OK needed
1. Re-read 0xE0..0xFF before/after OSD or SmartControl setting changes to map E/F codes. Reads only.
2. Read the three 288E2 docs in the vendor store and the SmartControl history for feature names (`/vendors/mstar/docs/`).
3. Search for a 288E2 teardown / service manual (documents.philips.com), FCC photos, for the scaler marking.
4. Read DPCD from a second GPU or an AUX sniffer to get the branch/sink identity string.
5. Ask the chenxing project whether a monitor-scaler (MST9U / TSUM) page exists; ours covers SoCs.

Need Dan
6. Opening the case: photograph scaler marking, SPI flash, UART header.
7. 0x49 ISP probe over HDMI DDC (a flashrom read; check the driver for a no-reset option first).
8. Flash dump twice and compare (vendor original, same rule as our units).
9. Writing anything (VCP resets, hidden codes, flash): deliberate only, with Dan's word; codes to try come from the SmartControl-under-Wine capture (`docs/monitors/smartcontrol-wine.md`).

## 7. What we could not find

- No public MStar datasheet for TSUMU88, MST9U11/13/25, MSD, MT96xx: only watermarked copies online, not downloaded (`/vendors/mstar/README.md`, "Found, not downloaded"). Everything in section 2 comes from reseller and board-vendor summaries.
- No 288E2 teardown, service manual, board photo or firmware dump.
- No source naming the exact scaler part in the 288E2.
- No MStar register database equivalent to `re/regdb`.
- Not covered: MT96xx / MStar TV SoC monitor variants, USB-C DP alt parts, DSC, local dimming, KVM; no source read states them for any part.
- The history-branch notes (`docs/monitors/mstar-vs-realtek.md`) cover company history only and are not repeated here.
