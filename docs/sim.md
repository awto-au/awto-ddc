# Firmware simulator (how to run it)

Status 2026-11-17. The only simulator is ours; no ucsim in any flow except the cross-check below.

## Cores

- **Default = fast core** (`FastMachine`, `scripts/fastmachine.py` + `scripts/mcs51_core.c` via ctypes, built on first use into `tmp/mcs51_core.so`). In-process, no subprocess. `fw_sim.Machine` is `FastMachine` when `AWTO_SIM_CORE` is unset or `fast`.
- CPU timing model: `dw8051` (default; `docs/sim-cpu-model.md`), switch `AWTO_SIM_CPU` / `--cpu`.
- ucsim: only `fw_sim.py --xcheck-ucsim` or `AWTO_SIM_CORE=ucsim` (cross-check, `scripts/fastcore_check.py`). Not used for tests of our code.
- Test 8051 code through the firmware image in the sim (or a host gcc build), never a standalone ucsim program.

## Layers

| layer | file | gives |
|---|---|---|
| machine | `scripts/fw_sim.py`, `fastmachine.py` | CPU + XDATA/SFR + register models (`Dev`), function stubs, banking |
| bus | `fw_sim.SimBus` | debug slave 0x35 (diag block, test cmd byte), `bus.wait(s)` advances firmware time, `bus.now()` |
| session | `scripts/osd_render.py` `Session(bin, map, mode, devs=[...])` | `boot()`, `snap()` (OSD state), `render_snap(st, bg, scale)` -> PIL image |
| devices | `devs=[...]` | extra `Dev` models: `ddc_sim.DdcEngine` (DDC/CI), `audio_sim.AudioTap` (audio generator + amp pins) |

## Recipes

- **Test cmd** (`fw/test/testcmd.c`, one per main pass): `splash_sim.py` / `key_sim_test.py` (`k.cmd(byte)`) writes it over 0x35 without waiting; leave a gap before the next one.
- **DDC/CI set / get**: `ddc_sim.Mccs(sess.bus, engine).set(vcp, value)` with `Session(..., devs=[engine])` (`scripts/splash_sim.py`).
- **Picture of the OSD**: `osd_render.render_snap(sess.snap(), "black", 2)` (1920 x 1080 for the 3840 x 2160 panel).
- **Sound**: `audio_sim.AudioTap` records generator / amp writes -> WAV (`docs/audio.md`).

## Ready scripts

| script | checks |
|---|---|
| `scripts/boot_sim.py`, `wake_sim.py`, `sync_sim.py`, `wdt_sim.py`, `key_sim_test.py` | boot, wake, sync log, watchdog, keys |
| `scripts/card_shot.py`, `qc_frames_shot.py` | menu cards, Realtek QC OSD frames |
| `scripts/nv_policy_sim.py` | flash halts per scenario (#151): equal VCP sets, menu close, input switch, backlight minutes, changed set, POWER off |
| `scripts/fw_gates.py <stem>` | the gate set (boot, isr, link, h1080, h2160, ...) run before a flash |

## Gotchas

- Firmware time is not wall time: a scope frame (64 passes of tile uploads) takes ~1 fw second; wait for the draw before a snapshot.
- Watchdog bites after 586 ms fw time without a CLR_WDT kick; long loops must kick.
- The sim has no audio stream: the SDK never unmutes the amp (P7.4 stays 0); `audio_sim` assumes it enabled (`assume_amp_en`).

## Timing checks count instructions, not ticks

- `bus.now()` / Timer2 stamps are 1 ms ticks; a check that compares two stamps flips with the tick phase (a ~0.5 ms path crosses a tick boundary or not).
- Gate `pump` (`scripts/pump_sim.py`): reply must start inside the delay by instruction count, not stamps.
  - Measure: `bus.m.instr` at request injection -> at the first DOUT write of the reply (~3.5 k instr).
  - Limit: `(1 - REPLY_MARGIN) x N_ms x instr_per_ms` = 0.75 x N x measured rate (~7.5 k instr/ms in the sim, measured over a 100 ms window after the check, +-1 %). N = the delay's argument (2).
  - Fail message: `<actual> instr from request to first reply byte, limit <L> (0.75 x N ms x R instr/ms)`.
  - `pump_sim.py --phase F` sets Timer2 to F of a tick left at injection. `tests/test_pump_budget.py` was deleted (ecce3f6c, #244).
