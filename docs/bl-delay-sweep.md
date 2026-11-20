# Backlight on-delay sweep (filmed video test)

Goal: find how long the backlight must stay off after the panel video is ready to avoid a start-up flash. Product default is unchanged: backlight on right after power-up on the M2PLL clock (Dan, 2026-11-13; `docs/design-162.md`). The knob below is a TEST knob only.

## Power-up order today (default image)

Code: `fw/sdk/Kernel/User Common Function/Code/UserCommonInterface.c` (panel machine), `SysMain.c`, `SysPower.c`, `SysJudge.c`. Sync rows: `fw/awto/sync.tsv` 11 xx / 12 xx / 13 xx.

| step | event | sync row |
|---|---|---|
| 1 | MCU reset; GPIO init leaves the backlight pin off (P9.2 high) | boot:GPIO set up |
| 2 | M2PLL on, Timer2 tick | boot:MCU set up |
| 3 | `UserCommonInterfacePanelBoot`: VDD on, backlight pin on, PWM 100 % (`SysMain.c` stage 4/5; no wait for link or video) | 11 01, 11 C2 |
| 4 | settings loaded: PWM = user brightness | 11 CA |
| 5 | T1 (VDD to PHY), PHY on | 11 12 |
| 6 | HPD, link training, stream on (eDP VIDEO state) | 11 23, 11 34 |
| 7 | display setting, DISPLAY SETTING -> ACTIVE = **panel video ready** | 13 xx `ACTIVE:display set, panel video ready` (why 0x25) |

- Wake from power saving (DDC/CI or other): `SysPower.c` PS_TO_NORMAL requests the backlight when VDD is up (11 C1 / D1); link and video follow as above, ACTIVE last.
- Backlight is on from step 3, before the link trains and ~1 s before ACTIVE: the panel shows whatever its timing controller holds (no video yet).
- Existing registry row 118 `bl_on_delay` delays the pin from "wanted" (step 3), not from video ready. Default 0.
- Datasheet T8 (video valid -> LED on, >= 200 ms): not followed (Dan); `docs/delays.md`, `docs/monitors/panel-innolux-m280dca-e3b.md`.

Measured 2026-11-20, unit 3, warm reset (ISP 0xEE), image 50fd217, sync log ms from the reset (knob 150 ms run): boot reason 113, GPIO 129, M2PLL 133, VDD kept on / backlight on by boot 133 (default image), PHY on 209, HPD 300, link trained + stream on 375, ACTIVE 1423 (DISPLAY SETTING 519 ms), backlight on with knob 150: 1575 (= 152 ms after ACTIVE). Default: backlight on at 133, 1.3 s before video is ready. Details in the issue.

## Test knob

- 4 B no-init XDATA at `AWTO_BLK_ADDR` (`RL6449_Project.h` `AWTO_BLK_*`, 0xF698): magic, ms lo, ms hi, check byte. Outside the linker XDATA range like the watchdog record, so it survives an ISP warm reset. RAM only, no NVRAM, no registry row.
- Valid = magic + check + ms <= 2000. Anything else (cold RAM, cleared) = off = default behaviour.
- Read at each panel-up (boot, wake). On: the backlight pin stays off until ACTIVE + knob ms (`UserCommonInterfacePanelVideoReady`, called at the ACTIVE transition; the machine's Timer2 `AwtoMs` deadline, no blocking). Cap: no ACTIVE within 5000 ms of "wanted" = pin on anyway, row 11 E3.
- Rows (class timing): 11 E2 knob in effect (value ms), 11 E1 pin on (ms after MCU boot, ms after video ready), 11 E3 cap expired (warning).
- Written by `scripts/bl_sweep.py` through `./dev.py dbg-write`, read back with `dbg-read`, cleared at the end of the sweep.
- Cost vs `origin/main` (1e32c76): XDATA free 209 -> 197 B, code +584 B, sim cycles per pass 163222 -> 163230.

## Sweep

`./dev.py bl-sweep --unit 3 [--values 0,50,100,150,200,300,400] [--runs 3] [--gap-s 8]`

- Bus access: direct, not through the GUI app's control port (#276): the run is its own reset + sync-log timing loop, and `reset` / `dbg-write` / `dbg-read` are not ported. It takes the unit lock, refuses to start while the app is running, and calls `synclog` / `note` with `--direct` (no headless app starts during the sweep).
- Order: values sorted, taken with a stride coprime to n (7 values: 0 200 50 300 100 400 150), the round repeated `--runs` times.
- Per run: knob write + read back, ISP reset, no bus traffic for 2.1 s, sync log read until ACTIVE + E1/E2 rows are in (5 s from the reset), verdict, host note `run k/n delay D ms` on the unit's console, gap.
- Verdict OK = E2 knob equals the planned value and E1 is present; KNOB-MISMATCH / NO-KNOB-ROW / NO-BL-ROW otherwise. 3 broken runs in a row abort the sweep.
- 21 runs at gap 8 s: about 5 min (14.5 s per run, dry run 2026-11-20).
- `--camera`: hook for `scripts/cam_frames.py` (branch cam-lcd-frames); TODO stub until it is on main. Match a recording by `reset_at` + `planned_ms` in the TSV.
- Output: START banner (host clock), RUN lines (reset time with ms, ACTIVE ms, backlight ms after boot / after video ready, estimated host time of the pin edge), summary table, DONE banner; `./tmp/logs/bl_sweep.tsv`, `./tmp/logs/bl_sweep.log`.
- Offline proof: `scripts/bl_knob_sim.py BIN MAP` (cold boot in fw_sim with the knob pre-seeded).
