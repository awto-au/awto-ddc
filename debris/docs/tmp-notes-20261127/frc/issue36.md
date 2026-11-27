🤖 #26 / #36 DDR read errors: no longer seen. The frame buffer runs clean at 4K60 on unit 3 (2026-11-13). Dan checked the picture by eye.

**Set-up**
- Branch `wb-p14ui-frc` (not pushed):
  - FRC is back as a build option, `-D _AWTO_FRC=_ON` (default off). `ScalerFRC.c` is unparked.
  - Test cmds 0x0C / 0x0D force the frame buffer / return to the SDK memory choice at the current timing.
  - Sync log E3: one line per request and one per memory-select change.
- Tools on `tools-frc`: `scripts/mem_mode.py` (unit) and `scripts/mem_mode_sim.py` (sim).
- Unit 3 (AWT26110003, Intel HDMI-A-2, bus 11), host 3840x2160@60.000, no host mode change.

**Result**
| time (+11:00) | image | memory | P0_02 | 8F/CF 04..0B SLIC | EF / F1..F7 INT_STATUS | 03 VALID_WIN_DET_0 | picture |
|---|---|---|---|---|---|---|---|
| 11:41:41-11:42:47 | wb-p14ui-frc1 | frame buffer (forced) | 00 | 00 | 00 | 22 / 22 | - |
| 11:44:41-11:44:55 | wb-p14ui-ddrinit1 (+DELAY_XUS(500) x2 in DDR init) | frame buffer (forced) | 00 | 00 | 00 | 22 / 22 | - |
| 11:56:02-11:56:35 | wb-p14ui-rot1 | Mirror H | 00 | 00 | 00 | 22 / 22 | Dan: flipped left-right, clean |
| 11:56:35-11:59:32 | wb-p14ui-rot1 | Mirror V | 00 | 00 | 00 | 22 / 22 | Dan: flipped top-bottom, clean |
| 11:59:37- | wb-p14ui-rot1 | Rotate 180 | 00 | 00 | 00 | 22 / 22 | Dan: rotated, clean |
| line buffer, any image | - | - | 00 | 00 | 00 | 00 | - |

- The VALID_WIN_DET_0 = 22 reading also appears in the Dahua firmware's own frame-buffer dumps: `tmp/regs/AWT26110003-20261107-103549.json` (4K30) 8F03 = 22 / CF03 = 32; `-103721` (1080p50) 32 / 32. It is normal frame-buffer traffic, not the read error.
- Failing signature 2026-11-07 (`-103441`, ours, pre-`~bit` fix): 03 = 33, SLIC0/1 = ff, INT_STATUS1 = ff. That signature is gone.
- Cause: the Keil `~bit` fix in the compiler (92e4233, 323b342) is the only change since 11-07 on this path. The modes that read errors then were never re-run in the frame buffer before today.
- `wb-ddrinit` (DDR init delays) changes nothing (same flags): not needed. It stays on branch `wb-p14ui-ddrinit` (8a34f69), not for merge.
- FRC cost, FRC on vs off: +27 635 B code, +168 B stubs, +104 B XDATA. XDATA free: 2081 B FRC, 2052 B FRC + rotation, 2181 B default (floor 700).
- Main loop on unit 3, 4K60 line buffer: 298/s (wb-p14ui-rec3), 307/s (frc1, ddrinit1), 303/s (rot1).

Next: 4K30 through the FRC within the datasheet panel limits (#165 follow-up). The 50 Hz / 24 Hz modes are not wanted.
