# DDR map

- Source: DDR map review awto-ddc#348 (2026-11-25; measurements and open tests live there). Tags: [HW] measured, [regdb], [SDK] hypothesis only.
- SDK refs: `fw/sdk/...` on main (same lines as tag `pre-strip-209`).

## Chips and ports
- Two DDR2 chips, 32 MiB each (16M x 16 bit = 256 Mbit, 4 banks, 8192 rows, 512 columns), 64 MiB total: `RL6449_Project.h:2163` `_16M_16BIT_DDR2_2PCS`.
- Separate controllers: DC_SYS_A / DC_PHY_A (regdb 0xA0xx), DC_SYS_B / DC_PHY_B (0xA8xx); `RL6449_Series_DDR2Include.h:47-49` (B = A + 0x40 / 0x4000 / 0x800).
- MCU_DC port A (0x3700..) reaches chip A only; port B (0x3740..) chip B only: regdb `M_DOMAIN_CLIENT_MUX_CTRL0/1` (0x37B0/B1), set 0x22 for 2 chips (`RL6449_Series_DDR2.c:158-162`); [HW] #255 port B returns different data and lane order.
- Address unit 8 B (FRC and MCU_DC). Registers hold 28 bits; the address wraps at 2^22 units = 32 MiB per chip [HW, `ddr-draw.md`].
- Both chips init in `ScalerDDR2PowerControl` (`RL6449_Series_DDR2.c:77`) via `ScalerMemoryPowerControl` (`ScalerMemory.c:625`): ON `SysPower.c:559` (also wake), OFF `SysPower.c:260`, `:308`, `:394`.

## Capture layout (E/O mode)
- 4K path: M1 captures even rows into chip A, M2 odd rows into chip B, each V/2 = 1080 lines at base 0.
  - `RL6449_Series_FRC.c:468-469` (VHeight / 2 for E/O), `:653-663` (2-chip build: M2 base 0, not BLOCK_STEP as in the 1-chip branch `:639-651`).
  - [HW] 2026-11-25 `CAP_M2_DDR_CTRL1` 0x82, `LINE_NUM` 0x438, `MEM_ADDR` 0.
  - [HW] unit 3: port A line L = row 2L, port B line L = row 2L+1, 92/92 exact each; both ports halves-swapped (#348 test 1).
  - [HW] `CAP_M1/M2_LINE_STEP` reads back 0 live although the data follows a 0x5A0 pitch (open, #348).
- LINE_STEP = ceil(W x bpp / 64), rounded up to a multiple of 4; BLOCK_STEP = (V / 2) x LINE_STEP.
  - 3840 px, 24 bpp: LINE_STEP 0x5A0, BLOCK_STEP 0x17BB00 units = 12,441,600 B per chip.
  - 30 bpp: LINE_STEP 0x708.

## Clients
| client | start (units, per chip) | size | active when | in our build | evidence |
|---|---|---|---|---|---|
| M1 capture -> chip A | MEM_ADDR 0; BL2 = BLOCK_STEP; BL3 = last line (cw180) | BLOCK_STEP x 1/2/3 | frame-buffer mode, `cap_cap_en`, not frozen | yes | `RL6449_Series_FRC.c:457-556` |
| M2 capture -> chip B | same as M1 | same | same | yes | `RL6449_Series_FRC.c:562-672` |
| M1/M2 display read (read only) | same blocks | same | frame-buffer mode | yes | `RL6449_Series_FRC.c:681-961` |
| Rotation / mirror | BL3 = 0x17B560 | none in 1-buffer; 2/3 blocks at non-1:1 frame rate | rotate != off | yes | `RL6449_Series_FRC.c:512-533`, `RL6449_Series_DDR2.c:385-415` |
| 1/2/3 buffer choice | 2-buffer at MN / free-run / rotation at non-1:1 rate; 3-buffer at rotation with input faster | 3-buffer at 4K = 4,199,040 units > 2^22: wraps [SDK] | per mode set (sync event FBUF) | yes | `RL6449_Series_Scaling.c` (#348) |
| OD (overdrive) | top rows | - | `_OD_SUPPORT` | no (`_OFF`) | `RL6449_Project.h:2169` |
| DRAM log + note store (port A) | chip A 0x3EBFFE-0x3FFFFF | 655,376 B | every main pass with log lines | yes | `fw/log/hostnote.c:84-96`, `dram-log-design.md`, `note-store.md` |
| ddr_draw test ops (port A) | block 1; `--extend` up to the whole chip | - | freeze image | freeze build only | `ddr-draw.md` |
| Doom (games repo, port A) | byte addr / 8 | ~0x80010 .. flats end | game image | games repo | awto-games-dw8051 `cache_native.asm:979-1010` |
| OSD, DCC, LD, HDR, audio, 3D-LUT, PIP/PBP | - | - | - | no DDR client (only clients 0-6, 8, MCU) | `RL6449_Series_DDR2.c:122-149` |
| DDR BIST / QC fill | QC OD/FRC test only | - | `_FACTORY_RTD_QC_SUPPORT` | no | `QC_Option.h:22` |

## Unit 3, current mode (4K60, Rotate 180, 1 buffer, 24 bpp; [HW] dump 2026-11-19 + log 2026-11-25)
| chip / units | bytes | user |
|---|---|---|
| A 0x000000-0x17BAFF | 12,441,600 | M1 capture each frame (even rows); M2 display reads |
| A 0x17BB00-0x3EBFFD | 20,457,456 | free in this mode |
| A 0x3EBFFE-0x3FFFFF | 655,376 | DRAM log + note store |
| B 0x000000-0x17BAFF | 12,441,600 | M2 capture each frame (odd rows); M1 display reads |
| B 0x17BB00-0x3FFFFF | 21,112,832 | free in this mode |

## Free in every 1- or 2-buffer mode (above 0x3B5380)
- A 0x3B5380-0x3EBFFD: 1,795,056 B.
- B 0x3B5380-0x3FFFFF: 2,450,432 B.
- 3-buffer mode overruns the whole chip, log included [SDK arithmetic].
- `BOUNDARY_ADDR1/2` = 0 / 0x0FFFFFFF: no write limit set.

## Events that rewrite or clear
- Freeze (`cap_frz_en`, P5_27 / P45_27 bit 2) stops capture writes [HW]; `RL6449_Series_FRC.c:1382-1388`.
- Any mode set unfreezes: `ScalerFRCInitial` clears the bit (`RL6449_Series_FRC.c:101-102`; called from `ScalerMemory.c:147`).
  - Triggers: timing change, source switch, test cmd 0x0C / 0x0D, rotate / mirror change, wake.
- Buffering change: blocks 2 and 3 go live, up to 0x2F75FF (24 bpp) or 0x3B537F (30 bpp).
- DPMS / power-key off: DDR PLL stops, no explicit self-refresh in the SDK; wake re-inits the PHY.
  - [HW] content is lost: POWER key off 12 s flips single bits (450 / 475 bad bursts of 156,288 on A / B); power saving 524 s loses 99.7 % (#348 test 2). Data kept in DDR must be reloaded after either.
  - [HW] intact on both chips: test cmd 0x0C / 0x0D, input switch, source switch, rotate off / on, ISP reset, watchdog reset (#348 test 2). AC cycle: not measured.
- [HW] 4K60 rotate off = line-buffer mode: `cap_cap_en` stays 1 and blocks stay programmed, but neither chip is written (marker unchanged 2 s; rotate 180 control overwritten within 23 ms; #348). DDR is then free except the log; any switch to rotate 180 rewrites block 1.
- No clear / fill path in our build. Cold power-up: content undefined. Writes before the first main-loop pass are lost [HW].
- Hazard: `MCU_DC_LEN` != 2 on port A kills port A [HW #255].

## Open (#348, one run each on unit 3)
- E/O mapping at 1080p60 (blocked: no picture, #350); buffering at 24 / 30 / 50 Hz; 10 bpc LINE_STEP; freeze cleared by mode set; retention without DDR clock; picture impact of MCU traffic.
