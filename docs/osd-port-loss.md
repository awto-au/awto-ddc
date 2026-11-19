# OSD data port spacing: FFF1 write interval + 24 nops

Decision (Dan, 2026-11-19): `FFF1[3:0]` (`mcu_wr_sca_intrvl_sel`) = 12 is the default at every build clock; `AWTO_OSD_PORT(v)` is one store + 24 nops.
- Both needed: sel 12 alone corrupted the savers on unit 3 (2026-11-19); sel 12 fixes the DPCD corruption, the nops fix the OSD port. Sel 12 + 24 nops image looked at on unit 3: clean.

- Set first in `ScalerMcuInitial` (`ScalerMcu.c`), before any scaler register / table write. `AWTO_SCA_WR_INTRVL_SEL` stays a `-D` override.
- Only other FFF1 writer in production: `ScalerOsdHardwareCompression` (sel 2 for its window, restores). Test ops (`fw/test/testcmd.c`, `scripts/osd_port_loss.py`) restore too.
- Sel is a hardware pace between continued scaler writes (4 + 4 x sel MCU cycles); the nops stay on top of it.
- 175 / 87 builds use the same sel 12 (52 cycles = 297 / 593 ns, above the 350.8 need). Per-clock tuning is open: `docs/clock-scaling-review.md` (S1, FFF1 rows).
- Build guard: `AWTO_CLOCK_MHZ` must be 350 / 175 / 87 (`Project_Option.h`, `#error`).

## Evidence (unit 3, 2026-11-19, branch worktree-agent-a4fa00f04d21de1c1, `./dev.py osd-port-loss`)
- Raw triple stores, 30 passes x 612 words: sel 10..15 0 bad bytes; sel <= 9 fail.
- Cost per byte at sel 12: raw 0.411 us, 24-nop macro 0.674 us, SDK call 1.34 us.
- Same sel fixes the DPCD read corruption at 350.8 (`docs/clock-sweep.md` "DP input at 350.8 MHz on unit 2").
- Earlier nop bisect (16 pass, 12 fail): `docs/scope-corruption.md`.
- Sel 12 + 24 nops (n12): checked by eye on unit 3, no corruption.
