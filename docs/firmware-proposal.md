# Proposed firmware / settings changes — JXC/Dahua 4K (RTD2795-class)

Status: DRAFT. Tags [fw]=read in code, [measured], [oss], [guess], [?].
Tracking: awto-ddc#1. Nothing here is flashed yet. Rule: dump twice, patch one 4 KB sector with
expected-content check, read back, keep backups (see rtdflash). Backups: ~/vendors/realtek/analysis/dumps/.

## Confirmed issues (what we'd fix)
1. **DDC/CI capabilities string is a stub** `(... vcp(02) ...)` [fw] — lists one feature, so OS tools hide
   brightness/contrast/input/power even though the firmware answers them [measured]. Fix: rewrite the caps
   string (plain text in flash at 0x52D72 / 0x52DD9) to advertise the VCPs the firmware really handles.
2. **EDID is the Realtek demo default** — vendor JXC, name "4K MONITOR", serial demoset-1 [fw/measured].
   Fix: proper vendor/model/serial, correct ranges. EDID lives in flash (3 copies ~0x138D8).
3. **Input source VCP 0x60 returns bad values** (reads VGA-2 on a DP unit; "invalid" in one scan) [measured].
4. **Power-save / no-signal shows colour test pattern instead of sleeping** [user]. Needs the no-signal
   handler (pattern-generator enable) — see RE. [?] data vs code.
5. **Host power control flag off** (VCP 0xCA sh=0): power button cannot be host-controlled [measured].

## Two delivery options
- **A. Settings/data patch (low risk):** caps string, EDID, OSD defaults, feature toggles are flash DATA
  (per Realtek extension region + Dizi0 notes). Patchable without a code rebuild. Covers issues 1,2 and
  possibly 5. Reflash via our ISP path (I2C 0x4A) or RTDCustomerTool.
- **B. Code patch / rebuilt firmware (higher risk):** needed for behaviour — issue 4 (no-signal), issue 3
  if it's a handler bug, and the new technical OSD. No source; would be binary patches to the 8051 image
  guided by the Ghidra RE. Keep behind a verified sector-patch + readback flow.

## Better technical OSD (the headline feature)
- Hardware can do it: scaler has OSD windows WIN0..WIN9, OSD font/char RAM, OSD_ADR_PORT 0x90/0x91 +
  OSD_DATA_PORT 0x92 [oss RTD2660 + regdb]. Current firmware only draws a tiny input box [measured].
- Content wanted (from Dan): every input with the active one marked; firmware version; current settings
  (brightness/contrast/colour/input/power); detected timing (res/refresh/H+V freq/pixel clock); link/lanes;
  HDR; signal-present; (temps if any sensor exists).
- Buttons: ADC key ladder on ADC_A0..A3 (regs 0xFF09-0xFF0C) [fw] — map the keys so a dedicated
  "tech info" page can be opened/paged. (button RE in progress → docs/reversing/realtek-rtd/buttons.md)
- Two build routes for the OSD: (host-driven) push glyphs into OSD RAM over ISP while firmware runs — no
  flash change, but only while our host drives it; (firmware) add an OSD page in the image, bound to a key.

## Technical OSD — design references (survey)
- **OSD RAM layout model:** KerJoe/ORTD2662 `osd/osd.h` + `osd/osd.c` [oss] — tile/character OSD (not bitmap):
  OSDRow (width/height/len), OSDCharacter1 (fg/bg/blink/visible), window (border/shadow/gradient, start pos);
  const `OSD_CHAR_OFFSET 0x13`, `OSD_FONT_OFFSET 0x300`; 0x90/0x91/0x92 access with 2-bit plane select in the
  top address bits (OSDWriteByte0/1/2). RTD2662 so bits may differ on RTD2795 — diff against our regdb (WIN0..9).
- **Non-modal corner HUD is feasible** (bitbuilt RTD2662 worklog) [oss]: scaler keeps drawing with MCU hooks;
  "Wiihud"-style persistent small window. Good model for an always-on tech strip.
- **Density/layout:** MangoHud [oss] — group by theme (Signal / Link / HDR / System), labels muted + values
  bright, units inline, fixed-width columns so numbers don't jitter, bar graphs via block glyphs in font RAM.
- **What to show (consumer status pages):** ASUS PG27AQDM "status" section, MSI/Dell factory menus (hours,
  version, timing) [oss, titles only — re-fetch for field lists].
- **Vendor-style menu structure:** danyaPostfactum/RTD2660, Mcsiv/OpenDisplayController (OSD + Factory dirs) [oss].
- **CAUTION — do NOT copy:** Kingdomwhisky/RTD-Scaler-TEST is leaked proprietary Realtek SDK. Reference for
  understanding the 0x90/0x91/0x92 `ScalerOsdAddrSet` + double-buffer only; no code reuse (licensing).

## Open / feeding this proposal
- [ ] button map + thresholds (agent)
- [ ] OSD UX references from modern/open projects (agent)
- [ ] no-signal pattern path (RE)
- [ ] caps-string + EDID exact byte layout and checksum recompute
