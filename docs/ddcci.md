# DDC/CI (MCCS 2.2) on our firmware

- Transport: DDC/CI 0x37 on the spare IIC engine IIC_1, polled from the main loop (`fw/sdcc/awto_ddcci.inc`, #60);
  the debug slave 0x35 stays on the main engine. kvm2e config: `-D _AWTO_DDCCI_FIXCH=2 -D _AWTO_DBG_FOLLOW=_OFF`.
- Content: the settings registry (#67). `AwtoDdcRegistry` hands get / set / save / capabilities to awto-rtdfw `vcp.c`.
  Codes, values and the capabilities string: [settings.md](settings.md) (generated, column VCP).
- Requests answered in the main-loop pass that sees them; set has no reply (MCCS). Save (0x0C) writes the NVRAM record.

| Code | Meaning | Source |
|---|---|---|
| 02 | new control value: always 1 | vcp.c |
| 04 / 08 | factory reset / colour reset (Colour + Six-axis pages) | rows factory_reset, colour_reset |
| 10, 12, 16, 18, 1A, 62, 87 | backlight, contrast, user R/G/B gain, volume (inert), sharpness (inert) | rows |
| 14 | colour preset: 08 9300K, 06 7500K, 05 6500K, 04 5800K (as 5000K), 01 sRGB, 0B user | row colour_temp |
| 60 | input: 0F D1 DP, 11 D2 HDMI, 12 D3 HDMI; set = #60 fast path | row input -> AwtoInputSelect |
| C8 / C9 / DF | controller 0x09 (Realtek) / firmware level 1.0 / VCP version 2.2 | vcp.c |
| D6 | power mode: get = firmware power state (01 on, 04 off); set 01 on, 02..05 power saving | row power_mode |
| E0 / E1 | registry id select / value of the selected row (every row) | vcp.c |
| E2 / E3 | schema (read) / 1 confirm risky, 2 save, 3 all defaults | vcp.c |
| E4 / E5 | menu command (op << 8 \| arg, awto-rtdfw menu.h) / cursor item (read) | vcp.c |
| E6..FF | direct manufacturer codes of our rows (fast switch, logo, panel T3, ...) | rows |

## Tests
- Offline: `scripts/ddc_sim.py BIN` (IIC_1 engine model in fw_sim; also the `ddc` gate of `scripts/fw_gates.py`).
- Unit (firmware agent): `ddcutil --bus N detect`, `capabilities`, `getvcp 10 12 14 60 D6 DF C8 C9`, `setvcp 10 60`,
  `setvcp 14 0B`, `setvcp 60 0x11`; expected: model `awto-mon`, mccs_ver 2.2, every listed code answers.
- Desktop brightness: not verified yet. Fedora 45 here: no `ddcci` kernel module packaged (ddcci-driver-linux would be
  an out-of-tree DKMS build); GNOME Shell / mutter 51.1. Open question in #67.
