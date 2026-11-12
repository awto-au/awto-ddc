# fw/sdk-parked: SDK sources that link 0 B (awto-ddc#165)

- Same relative paths as `fw/sdk/`. The build does not see them: `fw_compile.py` counts a project file found here as parked (a file in neither tree fails the build); `msg_tokenise.py port` copies `fw/sdk` only.
- Parked 2026-11-12 by `scripts/sdk_park.py move` from the last build's 0-byte modules + other-scaler board headers. Image after the move: code and map byte-identical; only the DebugMessage table (0xDA000) lost the parked sources' message texts.
- Bring one back: `git mv fw/sdk-parked/<path> fw/sdk/<path>`, set its option `_ON` in `RL6449_Project.h`, build (`fw_build.py`), warn-policy / pp_audit rows for its sites, gates.
- `pp_audit.py` counts `#define`s here as defined (header guards like `__USER_ADJUST_3D_GAMMA__` live in parked `.c` files).
- Not parked: other-scaler `Kernel/Common/*_Default.h`, `*_Gen_Option.h`, `Project/Header/RL6xxx_Project.h`. They are included unconditionally and their `#ifndef` defaults define 404 macros the RL6449 build reads (e.g. `_D4_INPUT_PORT_TYPE`).
- Comparing a new SDK drop (`scripts/sdk_import.py --out tmp/sdk-new`): diff against `fw/sdk` plus this tree.

| group | files | what | why parked |
|---|---|---|---|
| chip | 50 | `Pcb/RL6369`, `RL6410`, `RL6432`, `RL6463`, `RL6492` board headers | other scalers; each is all `#if(_PCB_TYPE == ...)` |
| mhl | 10 | MHL Rx / MHL3 / SysMHL | no MHL hardware (Dan: drop, #21) |
| od | 3 | overdrive (ScalerOD, RL6449_Series_OD, QC_OD_FRC) | `_OD_SUPPORT` off (Dan: drop) |
| uniformity | 3 | uniformity + OCC / OGC calibration | `_UNIFORMITY_SUPPORT`, `_OCC_SUPPORT` off (Dan: drop) |
| dimming | 5 | local / global dimming | off (Dan: drop) |
| dptx | 12 | DP Tx, DP Tx HDCP2, MST Rx / Tx | `_DP_TX_SUPPORT`, `_DP_MST_SUPPORT` off (Dan: drop); eDP panel output (ScalerDisplayDPTx) stays in fw/sdk |
| hdcp2 | 11 | HDCP 2.2 Rx (common, DP Rx0 / Rx1, TMDS Rx1..5) | HDCP 2.2 parked (#44); bring back D1 / D2 / D3 files with `_TMDS_/_DP_HDCP_2_2_SUPPORT` |
| freesync | 1 | ScalerCommonFreeSync | FreeSync planned (#21), off today |
| typec | 22 | Type-C, PMIC drivers, port controllers, USB hub / retimer, seamless charge | no Type-C port |
| cec | 4 | HDMI CEC | `_HDMI_CEC_SUPPORT` off |
| hdr | 2 | HDR10 user / common | `_HDR10_SUPPORT` off |
| vga | 11 | VGA / ADC / auto adjust / mode search / sync processor / LC tank / autotest | no VGA port (`_A0_NO_PORT`) |
| dvi | 10 | DP Rx0 (D0), TMDS Rx1 / Rx4 / Rx5, dual-link DVI | ports this board does not have (D1 DP, D2 / D3 HDMI only) |
| qc | 11 | Realtek QC self-tests (BIST, colour, OSD, DSPC) | factory QC, not built |
| memory | 7 | DDR1 / DDR3 / SDRAM, FRC, rotation, MBR | DDR2 board; FRC / rotation off (rotation planned, #165 list) |
| misc | 18 | IR (planned), SPI, TCON, power, PLL common, two-chip data exchange, digital signature, LED drivers, 3D / RGB gamma, user boot | options off; each compiled to 0 B |
