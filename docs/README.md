# docs index

- State lives in open issues + typed files (`scripts/devices.json`, `fw/rtdfw/settings/registry.tsv`, `fw/bank_map.tsv`); `history.md` = superseded one-liners, last section = the former handover (frozen 2026-11-16). Open items: `open-decisions.md`.
- Units: tests on unit 3 only (`scripts/devices.json` `test`, Dan 2026-11-27); units 1 / 2 are working screens, written only when Dan asks.
- Commands: `./dev.py --help` (one entry point; `./dev.py doctor` first when stuck).

## Build, rules, gates
- `dw8051-rules.md` (repo side of the awto-dan DW8051 / SDCC rules, compiler pin + refresh, `./dev.py rules-report`), `keil2sdcc-rules.md` (SDK edits), `keil-vs-sdcc.md`, `genconstprop-switch.md`.
- `gates.md` (normal / extensive tiers), `gates-report.md`, `build-guard.md`, `size-log.md` (per-build size log, `./dev.py size-graph`).
- `flash-layout.md`, `flash-sector-churn.md`, `duplicate-code.md`, `realtek-libs.md`, `sdk-model-inventory.md`, `design-162.md`, `script-triage.md`, `extra-apps.md` (`--extra-fw`, app hooks).
- Simulator: `sim.md`, `sim-cpu-model.md`, `sanitizer.md`, `speed-bench.tsv`.

## Flashing and deployment
- `deployment.md` (one image + per-monitor EDID), `flash-record.md` (which image each unit runs, flash preflight), `flash-registry.md` (on-device manifest), `flash-crc.md`, `flash-burst.md`, `flash-dp-aux.md`, `flash-unprotect.md`, `flash-screen.md`, `self-flash.md`, `edid-fix.md`.

## Logging, console, host time
- `sync-log-design.md` (lines, console time columns, start rows, line rules), `dram-log-design.md` (log ring in DDR), `note-store.md`, `diag-block.md`, `input-status.md`, `input-sync-timeline.md`, `display-on-timeline.md`.
- `ddcci.md` (MCCS, host time), [DDC compatibility review](ddcci-compatibility-review.md) (MCCS, vendor-code collisions, stock/OEM comparisons, approved follow-up and simulator cases; #388), `ddc-control.md`, `ip-over-ddc.md`, `data-channels.md`, `monitoring.md` (health monitor), `watchdog.md`.

## OSD
- `osd.md` (overview: console, info card, menu, fonts), `osd/README.md` (manual), `osd-hw-tests.md`, `osd-write-sweep.md`, `osd-port-loss.md`, `saver-fps-hw.md`, `qc-osd-suite.md`, `osd-realtek-sdk-menu.md`, `osd-screens-as-data.md`, `osd-editor-spec.md`, `firmware-proposal.md`, `boot-logo.md`, `logo/`, `osd-prototypes/README.md`, `games.md` (removed).
- Settings: `settings.md` (generated from the registry), `nvram-settings.md` (generated snapshot), `keys.md`.
- GUI: `monitor-gui.md` (monitor tab, control port, log view).

## Power, panel, timing
- `power-levels.md`, `delays.md`, `delay-audit.md` (+ `delay-audit.tsv`, `delay-audit-hwtest.tsv`, `delay-budget.tsv`), `irq-masks.md` (+ `irq-masks.tsv`, `irq-masks-parallel.tsv`), `main-loop-pacing.md`, `parallel-bringup-budget.md`, `tmds-isr-diet-plan.md`, `input-scan-rates.md`.
- Backlight / panel: `camera-lcd-timing.md`, `bl-delay-sweep.md`, `monitors/panel-innolux-m280dca-e3b.md`.
- Clocks: `clock-sweep.md`, `clock-scaling-review.md`, `temperature.md`.

## DDR
- `ddr-map.md` (2 chips, clients, free ranges, events, tools; #348), `ddr-draw.md`, `note-store.md`, `dram-log-design.md`, `data-channels.md` (frame capture).

## Audio, CEC, GPIO
- `audio.md`, `audio-registers.md` (generated), `cec.md`, `gpio-diagnostics.md`, `dp-rx-port-state.tsv`.

## Hardware, registers, reversing
- `monitors/README.md` (units, I2C roles, Philips probe), `monitors/boards.md`, `monitors/gpio-roles.md`, `monitors/panel-edid.md`, `monitors/panel-samsung-ltm270fl01.md` (ruled out), `monitors/rtd2795t-*` (pin ledger, datasheet facts, board match, pin audit), `monitors/mstar-*.md`, `monitors/smartcontrol-wine.md`, `monitors/ddcui.md`.
- Registers: `../re/regmap/README.md` (one row per register), `register-audit.md`, `live-register-scan.md`, `read-behind-research.md`, `realtek-debug.md`.
- Reversing: `reversing/` (Dahua firmware, Realtek RTD, 8051 playbook), `re-full-reversal.md`, `rtd2795t-sdk-hunt.md`, `rtdtool-*.md`, `cleanroom.md` (ended 2026-11-16).

