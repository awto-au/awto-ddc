# RTD2795T board-family and generic-board match

Status: evidence review, 2026-11-10. This report distinguishes a product/platform
match from an exact PCB match. No board photograph, PCB silkscreen, schematic, BOM,
or independent firmware image is presently available for a copper-level comparison.

## Conclusion

The JXC/AWTO board is **very likely from the Dahua LM27-F410 product platform, or a
close OEM/rebrand of that platform**. This is substantially stronger than a match
based only on using an RTD2795T:

- the factory flash contains a complete Dahua logo glyph atlas and Dahua-specific
  OSD/user code;
- the monitor is a measured 27-inch 4K IPS/PLS-class display;
- its external video topology is exactly one DisplayPort plus two HDMI inputs;
- the firmware drives a speaker-amplifier enable and reads a headphone-jack switch;
- Dahua's LM27-F410 is a 27-inch 3840x2160 monitor with exactly one DP, two HDMI,
  one audio output and two 2 W speakers, introduced in 2019.

This is **not yet proof that the PCB itself is identical**. The three AWTO units have
no fitted speakers according to the physical inspection, their EDID uses a generic
`JXC / 4K MONITOR / demoset-1` identity, and no LM27-F410 main-board photo or firmware
dump has been found for a pad-by-pad or binary comparison.

The public `MH08D` board is the closest explicitly generic controller by advertised
I/O (RTD2775QT/RTD2795, 2 HDMI, 1 DP, eDP/V-by-One), but there is no evidence yet that
it shares the JXC board layout or GPIO assignments. The Realtek `QA_B` source profile
is only an SDK ancestor, not the physical board.

## Local hardware fingerprint

| Property | Evidence | Result |
|---|---|---|
| Scaler/package | datasheet pin table, live register map, firmware/SDK function match | RTD2795T-CG / RL6449 family, LQFP216 |
| Video inputs | working ports and live DDC/cable-detect/HPD assignments | D1 DP, D2 HDMI, D3 HDMI; no D0 and no VGA |
| Panel output | live transmitter registers and working AWTO build | four-lane eDP HBR2; fixed DPTX lanes, AUX/HPD |
| Panel/display | glass measurement and visual check | 597 x 336 mm active area, 27-inch 16:9, IPS/PLS-class, 3840x2160@60 |
| Audio hardware indicated by factory code | P7.4 and P4.5 trace | speaker-amplifier enable plus headphone-jack selection; speakers not fitted/observed on the AWTO units |
| Controls | live ADC readings plus factory dispatch | SOURCE, MENU, DOWN, UP, AUTO, POWER; two ADC ladders plus digital power key |
| IR | factory code and pin mux | NEC receiver on package pin 194/P9.0; physical receiver not confirmed |
| Power/status | firmware writes and live GPIO | two-colour LED on P3.5/P3.6; separate panel, backlight PWM/enable and normal-power control group |
| Storage | live flash ID | Macronix MX25L8006E-compatible `C2 20 14`, 1 MiB |
| Factory identity | original EDID and decoded OSD assets | generic `JXC / 4K MONITOR / demoset-1`; Dahua boot-logo atlas |

Primary local evidence:

- [`gpio-roles.md`](gpio-roles.md)
- [`../reversing/dahua-fw/gpio-ir.md`](../reversing/dahua-fw/gpio-ir.md)
- [`../boot-logo.md`](../boot-logo.md)
- [`pinshare-live-AWT26110003.tsv`](pinshare-live-AWT26110003.tsv)
- [`../edid-fix.md`](../edid-fix.md)
- [`../../fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h`](../../fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h)

## Candidate comparison

| Candidate | Classification | Positive evidence | Negative or missing evidence | Confidence |
|---|---|---|---|---|
| **Dahua LM27-F410** | likely same monitor/OEM platform | Dahua assets in the factory flash; 27-inch 4K; exactly 1 DP + 2 HDMI; audio out + two-speaker design agrees with the firmware's jack input and amp-enable output; 2019 product fits the factory EDID's week 51/2020 date | no PCB photo/silkscreen, schematic or firmware hash; AWTO units reportedly have no fitted speakers; Dahua documentation does not identify the scaler | **High for product family; medium for exact board** |
| **VTL/MH08D** | plausible generic board family, not established as the same PCB | explicitly uses RTD2775QT/RTD2795; exactly 2 HDMI + 1 DP; eDP/V-by-One output; 4K60 | no dimensions, board drawing, pin mux, power GPIO, key circuit, firmware or PCB revision published on the product page; no Dahua link | **Medium for functional equivalence; low for PCB identity** |
| **UNI Display HDMI-RTD2795T-001A V1.1** | same scaler/application class | RTD2795T; HDMI + DP; four-lane eDP/eight-lane V-by-One; 4K60 | public summary does not state input counts or expose pin/GPIO assignment; industrial board may use 12/24 V and a different layout | **Medium-low** |
| **3AScreen AD-0095** | same scaler family, clearly different board | RTD2795T, LQFP216-class features, eDP/V-by-One, audio, IR and keypad support | has VGA, **two** DP, two HDMI, line-in, 10 W amplifier, 175 x 110 mm board and five-key interface; JXC disables VGA and D0 DP | **Not an exact match** |
| **Dahua LM28-F400** | later Dahua product with similar external ports | Dahua; 4K; 1 DP + 2 HDMI; speaker outputs | 28-inch active area rather than measured 27-inch; includes USB charging; 2023-era product; no scaler/board evidence | **Same product concept only** |
| **Realtek RL6449 QA_B reference profile** | SDK source ancestor | same RL6449/LQFP216 software family and broad 1A/2MHL/DP/mDP/eDP capability; AWTO header was initially derived from it | only 35 of 77 live mux values match; reference enables VGA DDC, panel HPD/AUX, line-in and many demo-board GPIO outputs that differ on JXC; names such as `LED1`, `MHL_5V_EN` and `DDR_PW_EN` are demonstrably wrong for this board | **Not the physical board** |
| **Other RL6449 SDK DEMO/QA profiles** | same SDK family | compile-compatible scaler family | best non-AWTO result is 34/77 matching mux selections; port populations and power/control GPIOs differ | **Not exact matches** |

## Why LM27-F410 is the leading candidate

Dahua's official specification identifies the LM27-F410 as a 27-inch UHD display,
3840x2160 at 60 Hz, 300 cd/m2, 10-bit colour, 178-degree viewing angles, with one DP,
two HDMI, an audio output and two 2 W speakers. Its published chassis width is
622.9 mm and it uses an external 12 V supply. The [official LM27-F410 datasheet]
(https://www.dahuasecurity.com/asset/upload/uploads/soft/20190919/LM27-F410_Datasheet_2019.9.12.pdf)
is dated 2019.

The factory image is not merely a generic Realtek SDK build carrying a Dahua string.
The decoded glyph set at flash `0x23B41` contains the complete Dahua swoosh and
`TECHNOLOGY` wordmark, while the user layer contains custom Dahua GPIO sequencing,
two-colour power-LED control, speaker/headphone handling and NEC IR key handling.
The register-level function library, by contrast, matches the Realtek RL6449 SDK.
This is the expected split for an OEM monitor: Realtek scaler library underneath,
Dahua product/user layer on top.

The strongest inconsistency is speakers: the LM27-F410 specifies two 2 W speakers,
whereas the AWTO units were inspected as having none. The board firmware nevertheless
contains a speaker-amplifier enable and headphone-jack selector. Plausible explanations
are an unpopulated/reduced-cost rebrand, a common Dahua main board used in multiple
SKUs, or an incorrect physical observation. Until the PCB and enclosure connectors
are photographed, this remains unresolved.

## SDK profile comparison

All 216-pin RL6449 profiles shipped with the recovered SDK were compared against the
77 JXC live pin-share selections. This comparison intentionally uses the numeric mux
mode, not the misleading signal labels inherited from Realtek demo boards.

| SDK profile | Matching live selections | Reading |
|---|---:|---|
| `RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP` | **35/77** | closest single SDK profile, but still 42 differences |
| `RL6449_QA_A_1A2MHL1DP1mDP_DPTX_eDP` | 34/77 | not a match |
| `RL6449_QA_A_LOCAL_DIMMING...` | 34/77 | not a match |
| `RL6449_DEMO_D...` | 34/77 | not a match |
| `RL6449_DEMO_B...` | 34/77 | not a match |
| remaining 216-pin profiles | 14–32/77 (or 16/47 for DEMO_E) | not matches |

Examples of meaningful QA_B differences are VGA DDC enabled versus GPIO inputs;
panel DPTX HPD/AUX enabled versus GPIO on three pads; analogue line-in enabled versus
GPIO; reference GPIO outputs versus many JXC inputs; IR on JXC pin 194; PWM4 on JXC
pin 195; and different power-state outputs. Therefore the comment that the AWTO header
was "from QA_B" records a software starting point, not board ancestry.

The six apparent mismatches between the generated AWTO pin-share header and the live
table are DDC/VGA priority-override presentation details (pins 65, 66 and 212–215),
not six unknown physical routes. The original firmware static analysis and working
ports independently confirm HDMI DDC2/DDC3, while VGA DDC is unused.

## Public generic boards

- [MH08D product page](https://www.vtlcd.com/product/MH08D-4K-LCD-Controller-Board-V-By-One-EDP-with-HDMI-DP-input.html):
  advertises RTD2775QT/RTD2795, two HDMI, one DP and eDP/V-by-One up to 4096x2160.
- [3AScreen AD-0095](https://3ascreen.com/product_display-kits/ad-0095-4k2k/):
  publishes its clearly different VGA + 2 DP + 2 HDMI topology and board dimensions.
- [UNI Display board list](https://unidisplay.jp/display-touch-products-2/):
  lists HDMI-RTD2795T-001A V1.1 with HDMI/DP input and eDP/V-by-One output.
- [Dahua LM28-F400 specification](https://cctv.net/sites/default/files/product/files/Datasheet_DHI-LM28-F400_Final.pdf):
  useful as a later similar Dahua topology, not evidence of the same PCB.

`JXC` and `demoset-1` are weak identifiers. Public EDID collections contain unrelated
JXC displays, and `demoset-1` also appears on unrelated Realtek-based portable
monitors. They look like generic scaler-firmware defaults rather than a traceable PCB
manufacturer/model. They should not be used to claim a match.

## What would settle an exact match

1. Photograph both sides of the AWTO main board at readable resolution, including
   every silkscreen code, connector label and PCB revision.
2. Photograph the rear I/O and keypad board, and record the enclosure/model label.
3. Obtain an LM27-F410 teardown/main-board photograph. Compare board outline,
   mounting holes, connector order, scaler/flash/EEPROM positions and regulator BOM.
4. Obtain an LM27-F410 flash dump. Compare SHA-256 first, then bank-level similarity,
   EDID slots, OSD assets, pin-share table and GPIO write sites.
5. Trace the currently unknown JXC power-control loads (P8.4, P8.5, P9.7 and PA.0)
   and compare them with any candidate schematic.

Until one of steps 1–4 is completed, the defensible statement is:

> The AWTO/JXC hardware is probably a Dahua LM27-F410-family/OEM monitor platform
> using a custom RTD2795T board. No public generic board has yet been proven to be
> the identical PCB; MH08D is only the closest advertised functional equivalent.
