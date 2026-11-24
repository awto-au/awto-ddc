# docs index (partial: sessions of 2026-11-18/19)

- Clock and delays: `clock-sweep.md`, `delay-audit.md` (owner of the delay decisions), `delays.md` (SDK constants, sources).
- Hardware investigations: `monitoring.md` (health monitor, ADC), `temperature.md`, `register-audit.md`, `monitors/README.md` (I2C roles), `reversing/dahua-fw/register-audit.md`.
- Extra apps (`--extra-fw`, app hooks): `extra-apps.md`.
- OSD: `osd/` (manual), `osd-write-sweep.md`, `saver-fps-hw.md` (OSD hardware levers; its saver numbers are of the removed games, `games.md`).
- Interfaces: `cec.md` (HDMI CEC sink, RPi5 test plan).
- Registers: `../re/regmap/README.md` (one row per register; docs link by key `PPAA`).
- Reports (research, no hardware):
  - `clock-scaling-review.md` (2026-11-19): what depends on the MCU / flash / timer clock at 350.8 / 116.9 MHz.
  - `read-behind-research.md` (2026-11-19): read-behind latch, internet + SDK + local research.
  - `monitors/mstar-vs-realtek.md` (2026-11-19): MStar vs Realtek monitor scalers.
  - `monitors/mstar-scaler-capabilities.md`: MStar scaler capabilities.
  - `monitors/smartcontrol-wine.md`: Philips SmartControl emulation under Wine (dxva2/nvapi shims, `../tools/smartcontrol_dxva2/`).
  - Philips probe: `../scripts/philips_probe.py`, `philips_raw_ddc.py`, `smartcontrol_probe.py` (section in `monitors/README.md`).
  - Read-behind cause tooling: `../scripts/reg_behind_cause.py`, `reg_behind_fix.py`, `reg_behind_indirect.py` (notes in `../re/regmap/README.md`, `live-register-scan.md`).
- Open items: `open-decisions.md`. Superseded one-liners: `history.md`.
