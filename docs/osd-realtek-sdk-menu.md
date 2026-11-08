# Realtek SDK menu (RTD2014 demo OSD), as built for our board

- **Not** Dahua's original menu: this is Realtek's demo UI from the SDK, compiled into our own images. Naming: [osd.md](osd.md#naming).
- In our menu it is "Vendor menu" (System page) until #87 relabels it.

Walked for awto-ddc#67 (2026-11-08): sim renders of image wb-p14sw (`scripts/osd_render.py`, key actions) plus the
compiled source tree (tmp/sdcc-port/src of the p14sc3 line). Every row here is a `[sdk-ui]` row of
`awto-rtdfw/settings/registry.tsv` (tag = Realtek SDK menu fact; rename pending, #87); our list: [settings.md](settings.md).

- Renders: `tmp/osd67/sdk/sdk_icon_*.png` (main icon row, one per icon), `tmp/osd67/sdk_main.png`.
- Main menu: 9 icons, wrapping: Picture, Display, Color, Advance, Input, Audio, Other, Information, Factory.
- Keys: OSD off: Menu = open (ACTIVE only), Right = source hot menu, Left = input info / hold 3 s DP version, Exit = DDC/CI
  hot menu (no signal). Icon: Menu = enter, Right / Left = next / previous (wrap), Exit = close. Item: Menu = adjust,
  Exit = back. Adjust: Right / Left = +1 / -1 (repeat after 0.5 s), Menu = keep + save, Exit = revert.
- Sliders show 0-100 %, mapped piecewise-linear around the centre to the real value (UserCommonAdjustPercentToRealValue).

| Page | Item | Range (shown) | Real range | Default | Effect on this build |
|---|---|---|---|---|---|
| Picture | Backlight | 0-100 % | 30-255 PWM | 128 | PWM4 duty |
| Picture | Brightness | 0-100 % | 312-712 | 512 | colour offset |
| Picture | Contrast | 0-100 % | 1248-2848 | 2048 | contrast x colour-temp gain |
| Picture | Sharpness | 0-4 | | 2 | greyed, compiled out |
| Display | Auto, H/V pos, clock, phase, rotate, latency, freeze | | | | VGA-only or compiled out: page unreachable |
| Color | Panel uniformity | on/off | | on | none; blocks Gamma/PCM while on |
| Color | Gamma | off/1.8/2.0/2.2/2.4 | | off | output gamma LUT |
| Color | Color temp | 9300/7500/6500/5800/sRGB/User | | 6500 | presets all 0x800 = equal gains |
| Color | User R/G/B | 0-255 | x16 in 12 bit | 128 | gains (User only) |
| Color | Color effect (+ six-axis hue 0-100 / sat 0-200 per R Y G C B M) | 6 options | | Standard | stored only |
| Color | Color demo | off/type 1-5 | | off | stored only |
| Color | PCM | User/Native | | Native | stored only |
| Color | Hue / Saturation | 0-100 % | 30-230 / 0-200 | 130 / 100 | stored only |
| Advance | Aspect ratio | Full/16:9/4:3/5:4/Original/User | | Full | display re-set |
| Advance | Over scan | on/off | | on | video timings only |
| Advance | DDC/CI | on/off | | on | forced off: DDC runs debug slave 0x35 |
| Advance | DP option D1 | 1.1/1.2/1.3 | | 1.2 | DP capability switch |
| Advance | DP resolution (EDID) D1 | 1080P/1440P/4K2K60 | | 1080P | DP EDID switch |
| Advance | Clone | on/off | | off | no DP TX |
| Input | Auto / D1 DP / D2 HDMI / D3 HDMI | | | Auto, port D2 | scan type + fixed port |
| Audio | Volume 0-100, mute, stand-alone, source analog/digital | | | 50, off, off, analog | stored only (no audio) |
| Other | Reset | action | | | all vendor records to defaults |
| Other | Menu time | 10-60 s | | 10 (= never) | OSD timeout |
| Other | OSD H / V pos | 0-100 | | 50 / 50 | position |
| Other | Language | English / Chinese-T | | English | strings |
| Other | Transparency | 0-100 % | 0-255 | 0 | blending |
| Other | OSD rotate | 0/90/270/180 | | 0 | stored only |
| Information | port, resolution, H freq / pixel clock, HDCP | read only | | | |
| Factory | factory menu | action | | | RTDFactoryMainMenu (Menu on the 9th icon) |

Compiled out (no row needed until the feature is built): OverDrive, Ultra Vivid, DCR, MST, HDMI version, FreeSync,
HDR, local dimming, SDR to HDR, pixel shift, MBR, Type-C, 3D OSD, audio self-test.
