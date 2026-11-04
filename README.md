# awto-ddc

Tools and notes for controlling monitors over DDC/CI and for reverse-engineering + reflashing
Realtek RTD scaler monitors (the JXC/Dahua 28" 4K units, RTD2795-class). Private repo.

## Controlling monitors over DDC/CI
- `scripts/ddc_ctl.py` — list / sleep / wake / brightness / get, over `ddcutil`; bus resolved per-run from the
  DRM connector. `scripts/ddc_idle.py` + `systemd/ddc-idle.service` — sleep/wake on GNOME idle. See `docs/ddc-control.md`.

## Scaler ISP over DDC (I2C slave 0x4A; halts the MCU, monitor reboots on reset)
- `scripts/rtd_isp_probe.py` — enter ISP, read JEDEC, read-only flash dump, `--resume` (reset MCU), `--scaler-regs`.
- `scripts/rtd_scaler.py` — one ISP session: read/write scaler regs (F4/F5 window), OSD RAM access; `--keep` leaves halted.
- `scripts/rtd_dump_info.py` — fingerprint + diff flash dumps (bank usage, 8051 vectors, EDID copies, caps string).
- `scripts/i2c_bench.py` — `/dev/i2c-N` read throughput per bus and read size.
- `scripts/rtd_keywatch.py` — poll the ADC key registers to see which front-panel button is pressed.

## Flashing (FIRST write anything — dump twice, patch one 4 KB sector, read back, keep backups)
- `scripts/rtd_flash_sector.py <bus> <addr> <file4k>` — DRY-RUN by default (JEDEC + status + backup + compare);
  `--write` does backup → unprotect → erase → program → read-back verify → re-protect → reset;
  `--expect-current <file>` aborts unless the live sector matches. Backups land in `tmp/flash-backups/`.
- `scripts/make_edid.py` — build the clean/conformant awto EDID(s) (identity AWT/awto-mon, measured 597x336 mm).

## Reverse-engineering
- Firmware (8051, one program per 64 KB bank): `scripts/ghidra_re.py import|regen <bank|all>` drives Ghidra headless,
  applies register labels (`scripts/regdb_ghidra_labels.py`) + hand names from `re/jxc-4k/ghidra_names_bank<N>.tsv`,
  seeds from `scripts/ghidra_seeds.py`. Needs awto-2000's shared Ghidra scripts (`$AWTO_2000`). `scripts/dis51.py` is a standalone 8051 disassembler.
- Realtek tool data → JSON (reproducible, and a diff-check for future tool versions):
  - `scripts/rtd_db_parse.py <DB.bin> <out.tsv>` — scaler register database (names, bit-fields, addresses, descriptions).
  - `scripts/rtd_gpio_parse.py <GPIO.bin> <out.tsv>` — GPIO/pin map (pin → register refs).
  - `scripts/rtd_flashdb_parse.py <FlashSet.dat|Flash.dat> <out.json>` — the JEDEC→flash-parameters table
    (erase/program/unprotect opcodes per chip); `--diff a.json b.json` compares two tool versions. Output in `re/flashdb/`.
  - `scripts/pe_resources.py <root> <out.tsv>` — GUI dialog/menu/control-ID map from the tool's PE resources.
  - `scripts/regdb_query.py <chip> regs|fields|port ...` — query the decoded register tables in `re/regdb/`.
  - `scripts/regdb_pack.py` — pack `~/vendors/.../regdb/*.tsv` into `re/regdb/*.tsv.gz`.
- `scripts/rtd_identify.py <bus>|--all [--json] [--no-isp]` — read-only full ID report (EDID, DDC VCP C8/C9/DF + caps, scaler product code, SPI flash JEDEC/status + FlashSet programming params); one ISP session, monitor reboots.
- Decoders: `scripts/logo_decode.py` (OSD tile sheet), `scripts/vlc_probe.py` (VLC font data).
- OSD (clean-room, from hardware facts): `scripts/rtd_osd.py` — draw text via OSD windows/font over ISP.
- Headless tool host: `scripts/rtd_headless/` — C host for the ISP plugin's version reads (see `docs/rtdtool-headless-feasibility.md`).

## Docs
- `docs/firmware-proposal.md` — issues + fix routes (settings-patch vs firmware-patch), priority order, OSD design.
- `docs/edid-fix.md` — the EDID rebuild (identity/size/conformance), patch plan, flash procedure + revert.
- `docs/logo/` — awto monitor mark (red, house style) + boot-splash replacement (640x360): `-colour` (primary), plain = black/white fallback.
- `docs/boot-logo.md`, `docs/reversing/realtek-rtd/{buttons,osd,db-bin-format}.md`, `docs/rtdtool-*.md`, `docs/monitors/`.

## Not in this repo
- Vendor binaries, flash dumps, extracted TSVs, Ghidra projects: `~/vendors/realtek/analysis/` (helpers in its `scripts/`).
- Exception (private repo only): decoded register/flash JSON under `re/regdb/` and `re/flashdb/` (see `CLAUDE.md`).
- Origin: moved from awto-dan (issue #86 → awto-ddc#1).
