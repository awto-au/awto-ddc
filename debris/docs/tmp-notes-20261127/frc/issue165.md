🤖 #165 rotation, steps 1-4 done on unit 3 (2026-11-13). Picture checked by Dan's eye: H, V and 180 all clean.

**Branches (local, not pushed)**
- `wb-p14ui-frc` (awto-ddc, main merged in at 77f9309).
- `tools-frc` (awto-ddc host tools).
- `rotate` (awto-rtdfw on ui aa74554, pin 7211ab4).
- `wb-p14ui-ddrinit` (8a34f69): DDR init delays. Measured no effect; not for merge.

**Build options** (`fw/sdk/Project/Header/RL6449_Project.h`; all default `_OFF`)
- `-D _AWTO_FRC=_ON`: frame buffer. `ScalerFRC.c` is unparked.
- `-D _AWTO_ROTATION=_ON`: 180 plus H / V mirror. Needs FRC. `ScalerRotation.c` and `RL6449_Series_Rotation.c` are unparked.
- `-D _AWTO_FREEZE=_ON`: freeze instead of rotation. The two are exclusive (`#error`).
- The rotation image is built with `-D _AWTO_FRC=_ON -D _AWTO_ROTATION=_ON`.

**Settings**
- Row 32 `disp_rotate`: `0 | 180`. It is no longer inert, and the registry now stores it itself (no `sdk` flag).
- New row 117 `mirror`: `Off | Horizontal | Vertical`.
- Both rows have one owner, `set_ap_rotate` (glue.inc): effective flip = (Rotate 180 ? H+V : none) XOR mirror. The owner writes `b3OsdDispRotate`. In ACTIVE it requests a display re-set from the system machine.
- One sync line per change: E4 `picture <normal | mirrored left-right | mirrored top-bottom | rotated 180>: <display re-set | stored | already in effect | not built>`.

**OSD**
- One owner, `AwtoOsdOrient`, runs at every `osd_tc_open`. At Rotate 180 it sets the chip's OSD auto rotation to 180 (`ScalerOsdMapRotation`: map plus font library). VLC glyph downloads are rotated by the decoder (FRAME_CTRL_0B). The sync log has E4 20 / 21.
- No rotated font copy is needed: no extra OSD SRAM or flash.
- Limits:
  - Mirror modes keep the OSD upright: FRAME_CTRL_41 only rotates (CW / CCW / 180).
  - Roll-up (console viewport scroll) is off while rotated.
  - The Realtek SDK message cards are not rotated yet.

**Measured, unit 3 (AWT26110003, HDMI-A-2, 4K60.000; host mode untouched)**
| time (+11:00) | state | image | Dan |
|---|---|---|---|
| 11:41:41-11:42:47 | frame buffer forced (test cmd 0x0C) | wb-p14ui-frc1 | - |
| 11:56:02-11:56:35 | Mirror H | wb-p14ui-rot1 | flipped left-right, clean |
| 11:56:35-11:59:32 | Mirror V | wb-p14ui-rot1 | flipped top-bottom, clean |
| 11:59:37- | Rotate 180 | wb-p14ui-rot1 | rotated, clean |
| 12:14:51- | Rotate 180 + console (OSD rotated) | wb-p14ui-rot3 | (asked) |
- Registers while rotated: P20_F0 = 81 (line reverse, width 3840), P5_49 / P45_49 = 03 (cw180 capture), P37_B0 = 12, P0_02 = 00.
- DDR PHY flags: SLIC / INT_STATUS 00. VALID_WIN_DET_0 = 22, the same as in the Dahua firmware's own frame-buffer dumps. Details in #36.

**Cost / speed**
| image | XDATA free (floor 700) | main loop, unit 3, 4K60 |
|---|---|---|
| default (rot0) | 2181 B | - |
| FRC (frc1) | 2081 B | 307/s |
| FRC + rotation (rot1 / rot3) | 2052 / 2050 B | 303/s |
| before: wb-p14ui-rec3 | - | 298/s |
- FRC on adds +27.6 KB code.
- 28 gates PASS on frc1, ddrinit1, rot1, rot0 and rot3.

**Open**
- Mirrored OSD text in the mirror modes: needs mirrored font copies plus mirrored layout. Dan to decide.
- Rotate the Realtek SDK message cards too (the SDK hardware-rotate path, `_OSD_ROTATE_FUNCTION`).
- Console scroll while rotated.
- Test cmd 0x0C collides with `wb-p14ui-cmds`; that branch renumbers (coordinator).
- `settings_cli.py set disp_rotate 180` takes "180" as a raw number and refuses it ("outside 0..1"). The option label needs `1`. Host tool fix: prefer the label match for enum rows.
