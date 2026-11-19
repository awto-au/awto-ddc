# Firmware gates: normal and extensive tiers

Three separate numbers, never added together (Dan 2026-11-19):
- **BUILD** = compile + link of one image (`./dev.py build`). Warm (ccache hit) ~40 s; the same for 350 / 175 / 87 builds.
  - Of the 40 s: `pp_audit.py --check` 26 s, asm compile + bank assemble ~5 s, link 3 s, generators ~1 s.
  - A cold build (empty ccache) at load 15-25 takes 2-3 min.
- **GATE** = the gates against an already built image (below). Wall s with all gates of a tier in parallel; CPU s per gate in the table.
- **FLASH** = `./dev.py flash`, measured on its own.

## Tiers
- `scripts/fw_gates.py IMAGE` = **normal** (default). `./dev.py flash` accepts a complete normal record (`tmp/fw/<stem>.gates.json`, `tier: normal`).
- `scripts/fw_gates.py IMAGE --tier extensive` = normal + the EXTENSIVE gates (`fw_gates.EXTENSIVE`, one line of reason per gate). `./dev.py gate --extensive` runs it on the newest image after test + build.
- Merge to main: `./dev.py merge-check IMAGE.bin` passes only for a complete, FAIL-free record with `tier: extensive` for that exact .bin.
- `--only a,b` writes a partial record (flash refuses it).
- Normal gate wall time 30 s (23 gates in parallel, load ~15); extensive adds keys, monitor heartbeat, wdt, wake, crash, canary, menu, deadport, inputrate, conwrap phases 1-5, delays at two clocks.

| gate | normal | extensive twin |
|---|---|---|
| keys | selector section (`--only switch`) | `keys_full`: every screen, 80 checks |
| monitor | all but the 30-sample heartbeat (`--no-beat`) | `monitor_full`: heartbeat, 300 simulated s |
| wdt | stall, pass, reason, t0_timing | `wdt_full`: 21 cases |
| wake | `--quick`: cable, EDID, AUX, SOURCE-key wakes | `wake_full`: + UP+DOWN, DPCD, poll period, TMDS clock, burst |
| crash | `--tests stall` | `crash_full`: workload, stall, hw, probe |
| conwrap | `--scope inject`: boot, injected widest lines, map end, demo burst | `conwrap_full`: + real power off / on / saving / wake |
| delays | own clock + delay audit | `delays_full`: + the sibling `-clk87` image |
| menu, deadport, inputrate, canary, bootsim_always | - | extensive only |

Opt-in switches (each is easy to undo, Dan decides): inputrate `--info` (two informational sweeps), the minimal variants above.

## Clock matrix (extensive)
`scripts/gate_matrix.py BASE_STEM [--build]`: delays, wdt, wake, inputrate, monitor, deadport, panel, sysm, htime, keys on the 350 / 175 / 87 MHz image of one source state (siblings `<stem>-clk175-be`, `-clk87-be`; `--build` builds a missing one). Writes no gates.json.

## Fault injection
`tests/test_gate_mutations.py --slow` (set `AWTO_TEST_IMAGE`): every normal variant and the sped-up extensive gates must FAIL with a function RET'd in the image or a sim input changed, and pass clean. `tests/test_gate_tiers.py`: tier table + merge-check.
