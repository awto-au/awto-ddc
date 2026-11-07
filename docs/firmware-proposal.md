# Technical OSD: design notes (feeds #2, #34, #39)

- Firmware is our own build on the RL6449 SDK (#7); the old patch routes, EDID-fail list and priority order are retired (`docs/history.md`).
- Current OSD work: debug pop-up in the Realtek input-info style (#34, done), button test (#39), boot log (#29).

## Better technical OSD (the headline feature)
- Hardware can do it: scaler has OSD windows WIN0..WIN9, OSD font/char RAM, OSD_ADR_PORT 0x90/0x91 +
  OSD_DATA_PORT 0x92 [oss RTD2660 + regdb]. Current firmware only draws a tiny input box [measured].
- Content wanted (from Dan): every input with the active one marked; firmware version; current settings
  (brightness/contrast/colour/input/power); detected timing (res/refresh/H+V freq/pixel clock); link/lanes;
  HDR; signal-present; (temps if any sensor exists).
- **Panel identity on the tech-info page:** size 597x336 mm / 27.0"; native 3840x2160@60, eDP 4-lane HBR2. Panel maker/model unconfirmed: best candidate BOE MV270QUM-N20 (#3, `docs/monitors/panel-edid.md`); the earlier Samsung LTM270FL01 guess is retired (`docs/history.md`).
  - Panel model is NOT in the EDID; the OSD string stays generic until #3 is settled.
- Buttons: ADC key ladder on ADC_A0..A1 (AD_KEY1 FF09, AD_KEY2 FF0A), thresholds in `RL6449_AWTO_JXC4K.h` PCB_KEY_STATE; see `docs/reversing/realtek-rtd/buttons.md`.
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
- **Realtek RL64xx SDK:** Kingdomwhisky/RTD-Scaler-TEST = Realtek RL64xx Keil-C51 SDK (RL6449 = our RTD2795T family).
  At `/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST/`. Use freely (build, name funcs, reference the
  `ScalerOsd*` OSD + font-download path). Carries a Realtek confidential header → fine in this private repo;
  revisit only if awto-ddc is ever made public. See `docs/rtd2795t-sdk-hunt.md`.
