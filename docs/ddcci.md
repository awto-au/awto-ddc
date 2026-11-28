# DDC/CI (MCCS 2.2) on our firmware

- Transport: DDC/CI 0x37 on the spare IIC engine IIC_1, polled from the main loop (`fw/ddcci/ddcci.c`, #60);
  the debug slave 0x35 stays on the main engine. kvm2e config: `-D _AWTO_DDCCI_FIXCH=2 -D _AWTO_DBG_FOLLOW=_OFF`.
- DDC/CI and the debug slave sit on the DDC channel of the selected port (D1 = DDC1 = DP AUX I2C, D2 = DDC2, D3 = DDC3); the channel moves at the input select (VCP 0x60, test cmds, selector), and again at ACTIVE. DP AUX I2C reaches 0x37 / 0x35 the same as an HDMI DDC bus (unit 2, Intel DP-1).
- Content: the settings registry (#67). `AwtoDdcRegistry` hands get / set / save / capabilities to `fw/rtdfw/awto/settings/vcp.c`.
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
| E4 / E5 | menu command (op << 8 \| arg, `fw/rtdfw/awto/include/menu.h`) / cursor item (read) | vcp.c |
| E6..FF | direct manufacturer codes of our rows (fast switch, panel T3, ...); free: E8, F5 (retired rows) | rows |
| E9 | host time (#157): table write (0xE7) = set; get: max = syncs since boot, cur = drift ms (int16) | fw/ddcci/ddcci.c |
| FE E1 | firmware-version string (#385): `01 FE E1 E6 06 00` -> `6E 80\|n E1 00 <ASCII build tag>` (SmartControl GetDisplayFWVersion) | fw/ddcci/ddcci.c |

## Philips/TPV compatibility (#388, #385)

Dan 2026-11-28: adopt these so SmartControl / ddcutil-style tools read our units cleanly. Documented first (RE + SDK) then matched.

| code / behaviour | Dahua original | Realtek SDK default | ours now | proposed / done |
|---|---|---|---|---|
| 0x60 encoding | single low byte, no PIP (`re/jxc-4k/ghidra_names_bank5.tsv:20`) | single low byte, no PIP (`fw/sdk` caps `RL6449_Project.h:2208`) | single byte (high byte 0) | keep single byte; high byte = `AWTO_DDCCI_INPUT_SUB` (0) made explicit |
| 0x60 PIP high byte | none | none | none (no PIP block) | none — the high/low split is Philips/TPV-specific; the simpler single-byte form is what Dahua + SDK use and ddcutil/SmartControl read either way |
| set-VCP write pacing | none (only ~300 us bus debounce) | none (50 ms RX timeout, debug path only) | none | drop set-VCP < `AWTO_DDCCI_WR_PACE_MS` (110 ms) apart. Compat pace, NOT a hw limit; TPV tools already pace 110-120 ms (`docs/monitors/smartcontrol-wine.md:162`) |
| 0x14 colour preset | yes (values 0..13) | yes (`14(01 02 04 05 06 08 0B)`) | yes (row colour_temp) | already have it |
| 0x72 gamma | no RE evidence | not in caps / not answered | no (gamma not a DDC/CI row) | report-only: no gamma-preset feature to expose |
| 0xDC SmartImage | no RE evidence | not in caps / not answered | no SmartImage feature | report-only: no SmartImage equivalent |
| vendor 0xEF | no RE evidence | n/a | E0..FF are our registry rows (not 0xEF) | report-only |
| FE E1 fw string | no RE evidence (vendor frame) | n/a | not answered | answer with the build tag (#385) |

- 0x60 high byte: the get reply value is `(sub << 8) \| main`; `AWTO_DDCCI_INPUT_SUB` is 0 (no PIP window), so the value stays a plain input code.
- Pacing applies to MCCS set-VCP (opcode 0x03) only; the audio-test tone and debug-link control writes stay unpaced.
- Named constants: `AWTO_DDCCI_INPUT_SUB`, `AWTO_DDCCI_WR_PACE_MS`, `AWTO_DDCCI_FW_STR_OP` (`fw/sdk/Project/Header/RL6449_Project.h`).
- The build tag in the FE E1 reply is `AWTO_FW_TAG` (the `@FW_TAG@` commit tokenised into fw/sdk; also the console title). Capped to the 16-byte engine buffer, so a long tag is truncated on the wire.

## Tests
- Offline: `scripts/ddc_sim.py BIN` (IIC_1 engine model in fw_sim; also the `ddc` gate of `scripts/fw_gates.py`).
- Unit (firmware agent): `ddcutil --bus N detect`, `capabilities`, `getvcp 10 12 14 60 D6 DF C8 C9`, `setvcp 10 60`,
  `setvcp 14 0B`, `setvcp 60 0x11`; expected: model `awto-mon`, mccs_ver 2.2, every listed code answers.
- Desktop brightness: not verified yet. Fedora 45 here: no `ddcci` kernel module packaged (ddcci-driver-linux would be
  an out-of-tree DKMS build); GNOME Shell / mutter 51.1. Open question in #67.

## Host time (#157)
- Purpose: monitor logs (sync ring, console) in host time. Sender `scripts/host_time.py`; refuses non-test units.
  - Service `systemd/host-time.service`: `--unit 3 --loop 300` (every 300 s, Dan 2026-11-27; unit 3 only for now). Not enabled by
    default; same install steps as ddc-idle in [ddc-control.md](ddc-control.md).
  - Several units: `--units 1,2,3` or `--units test` (every devices.json test unit), one send per unit per period; explicit only.
    An unreachable unit: one decoded line, skipped until the next period (no retry).
  - One `--unit N --once --wait 5` send after every dev.py path that restarts the fw clock: flash (ok or failed, not when held in ISP),
    deploy / edid (sector write ends with an ISP reset), power-cycle on, reset (#358). A failed send is a WARN line, never a failed flash.
  - `--loop`: also a get VCP E9 every 30 s (`BOOT_CHECK_S`); 0 syncs since boot (watchdog, mains, an unseen reset) = send at once;
    skipped while a flash holds the unit lock. The 0x35 fallback takes the running image's map from the shared flash record.
  - `./dev.py doctor`: host-time.service must be active and its installed ExecStart = `systemd/host-time.service`; notes when it runs another tree's script (#358).
- Request: MCCS table write to VCP 0xE9, offset 0000, 7 data bytes; no reply.
  - `51 8B E7 E9 00 00 t3 t2 t1 t0 mH mL ofs chk`: unix s BE, ms within the second BE (0..999), UTC offset in 15 min (signed).
  - 14 bytes: fits only images with the 17-byte request buffer (`_AWTO_NET` on, the default); otherwise dropped.
  - E9 = the retired logo_ms code (#144): no row reads it; a table write cannot hit a row by accident.
- Firmware (`fw/log/sync.c` AwtoHtSync): stores unix s, ms, offset and the fw ms at receipt (`g_stAwtoHt`, RAM only).
  - No flash, no dirty flag (not a setting). The NVRAM flush gate counts it as DDC/CI (busy 500 ms): one per period.
  - fw ms = `AwtoUpMs()`: usT2Isr (1 ms) + a wrap count, 32 bit (49.7 days).
  - Ring: `host time <ISO>` + `(fw +N ms, first host sync since boot)` at the first sync of a boot; on |drift| > 1 s also
    `(fw +N ms, host sync after a drift)` + `drift +D ms`. Drift = host time - local tick from the previous sync.
  - Console title: `HOST hh:mm:ss` ticks from the last sync; `--:--:--` before the first; `STALE` after 375 s without one
    (`AWTO_HT_STALE_MS` = 1.25 x the 300 s period; was Dan's 3 min for the 60 s period).
- Host side: `scripts/sync_log.py` / `rtd_diag.py --sync` print each ring line with its host time from the latest sync; columns: [sync-log-design.md](sync-log-design.md) "Console time columns".
  - DRAM log images (default): 32-bit fw ms per line, exact over any gap.
  - 16-bit ring (`_AWTO_DRAM_LOG` off): unwrapped from anchors (C0 / D8 full times); between anchors that do not land exactly: a `counter wrap` row.
- Tests: `scripts/host_time_sim.py BIN` (fw_sim; gate `htime` of `fw_gates.py`). Hardware: `host_time.py --unit 3 --once`.
- Debug link on (0x35 on the port) = DDC/CI off: DDC/CI send fails, the debug-link path (0x35) is tried; failure logged, next period retries.
