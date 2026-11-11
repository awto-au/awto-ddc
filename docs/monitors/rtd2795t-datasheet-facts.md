# RTD2795T-CG datasheet facts

Source: [RTD2795T-CG Datasheet, 21 pages](https://rtddisplay.com/upload/20231007170054.pdf), hosted by
`rtddisplay.com`. This is a third-party mirror with an `rtddisplay.com` watermark, not an official Realtek download.
No copy was found on Realtek's public site. Search indexing exposed no second RTD2795T technical document on the
mirror, so the facts below come from this PDF rather than distributor-generated descriptions.

## Device identity

- Realtek multi-function display/monitor controller with an embedded industrial-standard 8051 MCU.
- Package: LQFP216, 24 × 24 mm body, 26 × 26 mm lead span, 0.40 mm pitch, maximum 1.60 mm height.
- Maximum documented input format: 4096 × 2160 at 60 Hz.
- Intended applications include monitors, all-in-one PCs, and embedded display systems.
- The ordering table lists one VGA input, two DisplayPort 1.2 inputs, two HDMI 2.0/DVI inputs, an eight-lane
  V-by-One/eDP HBR output, a four-lane eDP HBR2 output, frame-rate conversion, and overdrive.

## Inputs

### HDMI / DVI

- Two HDMI 2.0/DVI receiver ports; the package signals use receiver suffixes `_2` and `_3`.
- HDMI signalling up to 6 GHz.
- 6-, 8-, 10-, and 12-bit colour-depth transport.
- HDMI HDCP 1.4 and HDCP 2.2; DVI HDCP 1.4.
- HDMI audio can be routed to I2S or SPDIF.
- Data-enable-only mode is supported.
- Each receiver has fixed TMDS clock/data differential inputs, HPD/GPIO, DDC clock/data, receiver supplies,
  grounds, and a shared external TMDS impedance-reference pin.

### DisplayPort

- Two DisplayPort 1.2 receiver ports; package lane suffixes are `_0` and `_1`.
- Four lanes per receiver plus AUX and HPD/cable-sense-capable GPIOs.
- RBR 1.62 GHz, HBR 2.7 GHz, and HBR2 5.4 GHz link rates.
- 6-, 8-, 10-, and 12-bit colour-depth transport.
- HDCP 1.4 and HDCP 2.2.
- DisplayPort audio can be routed to I2S or SPDIF.

### Analogue VGA / component

- One analogue RGB input with an integrated triple-channel 8-bit 210 MHz ADC/PLL.
- YPbPr component input up to 1080p.
- Separate positive/negative R/Pr, G/Y, and B/Pb inputs, HSYNC, VSYNC, and sync-on-green.
- Programmable HSYNC Schmitt trigger, composite-sync modes, and ADC noise reduction.
- VGA DDC clock/data pins are multiplexed with GPIO.

## Panel output

- Eight-lane V-by-One or eight-lane eDP HBR output supports formats up to 4096 × 2160 at 60 Hz.
- Four-lane eDP HBR2 output also supports up to 4096 × 2160 at 60 Hz.
- Output colour depth is 8 or 10 bits.
- The LQFP216 exposes eight differential transmitter lanes plus two panel AUX/HPD groups.
- Data-pair swapping is programmable to simplify PCB routing.

## MCU and board-control resources

- Industrial-standard 8051 core with external SPI firmware flash.
- Four five-bit low-speed ADC inputs intended for keys or sensors.
- I2C master or slave hardware.
- Six programmable PWM channels with selectable frequency.
- One 14.318 MHz crystal supplies the device timing.
- Programmable low-voltage reset.
- Dedicated external-flash SPI clock, input, output, chip-enable, and write-protect pins.
- Separate `USB_SPI_*` multiplexed pins provide an SPI control link for an external USB device/hub. They are not
  USB D+/D− PHY pins.

## Audio

- Embedded audio DAC and headphone amplifier.
- Analogue headphone and speaker/line outputs with separate analogue supplies and grounds.
- Multiplexed I2S word-select, serial-clock, master-clock, and four serial-data pins.
- Four multiplexed SPDIF outputs.

## Image processing and frame buffer

- Independent horizontal and vertical scaling with programmable and non-linear zoom ratios.
- 12-bit internal colour-processing path, 14-bit gamma, and programmable 12-bit 3D gamma.
- Input/output gamma, sRGB/Adobe RGB-related processing, xvYCC, independent colour management, dynamic contrast,
  brightness/contrast, sharpness, and dithering.
- Panel brightness/colour uniformity correction.
- Embedded frame buffer with frame-rate conversion and response-time/overdrive processing.
- Automatic input-format detection and VGA phase/position/colour calibration.

## OSD hardware

- Two independent font-based OSD engines.
- 36 KiB SRAM dynamically shared by OSD commands and font data.
- One-, two-, and four-bit-per-pixel multicolour RAM fonts with a 64-colour palette.
- Proportional fonts from 12×18 down to 4×18, hardware font decompression, scrolling, and per-character blinking.
- Up to 26 windows with alpha blending, gradients, borders, shadows, and fade effects.
- 90°, 180°, and 270° rotation plus an OSD pattern generator for factory use.

## Supplies and environmental limits

| Rail/parameter | Datasheet range |
|---|---:|
| Pad/analogue supply `PVCC` | 3.14–3.47 V, 3.30 V typical |
| DDR2 I/O supply | 1.7–1.9 V, 1.8 V typical |
| Core supplies `VCCK_ON` / `VCCK_OFF` | 1.05–1.15 V, 1.1 V typical |
| Ambient operating temperature | 0–70 °C |
| Storage temperature, recommended table | −55–110 °C |
| Junction maximum | 125 °C |
| ESD figure | ±2.5 kV |
| Latch-up figure | ±100 mA |
| Junction-to-air thermal resistance | 21.5 °C/W typical |
| Junction-to-case thermal resistance | 8.8 °C/W typical |
| Minimum reset pulse | 1120 ns |
| Power-on reset interval | 145–148 ms, 146.5 ms typical |

The absolute-maximum table separately gives 3.6 V maximum `PVCC` and 150 °C maximum plastic-package storage
temperature; these are stress limits, not normal operating targets.

## Pinout-derived RE conclusions

These are inferences from the complete package table plus local live/firmware evidence, not claims printed as feature
bullets in the datasheet:

- The LQFP216 table has no dedicated CEC-labelled lead. The generic SDK contains CEC code/register definitions, but
  the JXC firmware does not touch that block and no CEC board connection is proven.
- The package table has no USB D+ or D− leads and the feature list does not claim a native USB PHY. Any USB hub/KVM
  data path must therefore be external to this scaler.
- Pins 153–157 are `USB_SPI_*`, but the live JXC pin-share config selects ordinary GPIO inputs on all five; the
  USB-SPI function is currently disabled and their PCB loads remain untraced.
- Pins 78–88 are explicitly NC in the package table.
- The pinout is consistent with the ordering table's two HDMI/DVI receivers, two DP receivers, and eight-lane panel
  transmitter.

Related local views:

- [Interactive package-pin ledger](rtd2795t-216-pin-ledger.html)
- [Interface/bus explorer](rtd2795t-bus-view.html)
- [Machine-readable facts](rtd2795t-datasheet-facts.json)
- [Machine-readable pin ledger](rtd2795t-216-pin-ledger.json)
