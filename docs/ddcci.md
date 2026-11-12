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
| E6..FF | direct manufacturer codes of our rows (fast switch, panel T3, ...); free: E8, F5 (retired rows) | rows |
| E9 | host time (#157): table write (0xE7) = set; get: max = syncs since boot, cur = drift ms (int16) | awto_ddcci.inc |

## Tests
- Offline: `scripts/ddc_sim.py BIN` (IIC_1 engine model in fw_sim; also the `ddc` gate of `scripts/fw_gates.py`).
- Unit (firmware agent): `ddcutil --bus N detect`, `capabilities`, `getvcp 10 12 14 60 D6 DF C8 C9`, `setvcp 10 60`,
  `setvcp 14 0B`, `setvcp 60 0x11`; expected: model `awto-mon`, mccs_ver 2.2, every listed code answers.
- Desktop brightness: not verified yet. Fedora 45 here: no `ddcci` kernel module packaged (ddcci-driver-linux would be
  an out-of-tree DKMS build); GNOME Shell / mutter 51.1. Open question in #67.

## Host time (#157)
- Purpose: monitor logs (sync ring, console) in host time. Sender `scripts/host_time.py` (unit 2 only), every 60 s via
  `systemd/host-time.service` (not enabled by default; same install steps as ddc-idle in [ddc-control.md](ddc-control.md)).
- Request: MCCS table write to VCP 0xE9, offset 0000, 7 data bytes; no reply.
  - `51 8B E7 E9 00 00 t3 t2 t1 t0 mH mL ofs chk`: unix s BE, ms within the second BE (0..999), UTC offset in 15 min (signed).
  - 14 bytes: fits only images with the 17-byte request buffer (`_AWTO_NET` on, the default); otherwise dropped.
  - E9 = the retired logo_ms code (#144): no row reads it; a table write cannot hit a row by accident.
- Firmware (`awto_sync.inc` AwtoHtSync): stores unix s, ms, offset and the fw ms at receipt (`g_stAwtoHt`, RAM only).
  - No flash, no dirty flag (not a setting). The NVRAM flush gate counts it as DDC/CI (busy 500 ms): one per 60 s.
  - fw ms = `AwtoUpMs()`: usT2Isr (1 ms) + a wrap count, 32 bit (49.7 days).
  - Ring: `host time <ISO>` + `(fw +N ms, first host sync since boot)` at the first sync of a boot; on |drift| > 1 s also
    `(fw +N ms, host sync after a drift)` + `drift +D ms`. Drift = host time - local tick from the previous sync.
  - Console title: `HOST hh:mm:ss` ticks from the last sync; `STALE` after 3 min without one; `--:--:--` before the first.
- Host side: `scripts/sync_log.py` / `rtd_diag.py --sync` print each ring line with its host time from the latest sync.
  - Ring ms are 16 bit: unwrapped from anchors (episode start C0: value bits 23..8 = fw ms bits 31..16; D8: full fw ms).
  - `~` after a time: forward unwrap and back-from-now disagree (a gap of 65.5 s or more between lines hid a wrap).
- Tests: `scripts/host_time_sim.py BIN` (fw_sim; gate `htime` of `fw_gates.py`). Unit 2: `host_time.py --once`.
- Debug link on (0x35 on the port) = DDC/CI off: the send fails and is logged; the next round retries.
