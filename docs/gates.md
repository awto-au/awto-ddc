# Firmware gates: normal and extensive tiers

Three separate numbers, never added together (Dan 2026-11-19):
- **BUILD** = compile + link of one image (`./dev.py build`). Warm (ccache hit) ~40 s; the same for 350 / 175 / 87 builds.
  - Of the 40 s: `pp_audit.py --check` 26 s, asm compile + bank assemble ~5 s, link 3 s, generators ~1 s.
  - A cold build (empty ccache) at load 15-25 takes 2-3 min.
- **GATE** = the gates against an already built image (below). Wall s with all gates of a tier in parallel; CPU s per gate in the table.
- **FLASH** = `./dev.py flash`, measured on its own.

## Tiers
- `scripts/fw_gates.py IMAGE` = **normal** (default). `./dev.py flash` accepts a complete normal record (`tmp/fw/<stem>.gates.json`, `tier: normal`).
- `scripts/fw_gates.py IMAGE --tier extensive` = normal + the EXTENSIVE gates (`fw_gates.EXTENSIVE`, one line of reason per gate). `./dev.py gate --extensive` runs it on the gate's own build after build + test.
- Extensive inputs: `--build-inputs` (also in `./dev.py gate --extensive`) builds the missing sibling images, then the base image again (the link / iram gates read the asm of the last build): `-t0ev` (`-D _AWTO_T0EV_TEST`, `wdt_full` Timer0 cases; without it they SKIP) and `-clk87` (`delays_full`). A fresh worktree needs only `./dev.py build` + this flag (#310).
- Record `tmp/fw/<stem>.gates.json`: `red` = FAIL gates, `new_red` = red and not red in the previous complete record of the tier (logged `NEW RED`).
- Merge to main: `./dev.py merge-check IMAGE.bin` passes only for a complete, FAIL-free record with `tier: extensive` for that exact .bin.
- `--only a,b` writes a partial record (flash refuses it).
- Normal gate wall time 22 s (24 gates in parallel, load ~15, 2026-11-19; longest bootsim / panel 12 s wall, ~6 s CPU). Budget (Dan): a normal gate ~1 s, a few s at most.
- Moved to extensive for cost (quick variants, 9-20 s CPU each, stay runnable with `--only`): keys, monitor, wake, crash, conwrap, conmode, sysm, sync. Normal `delays` = delay audit only (`delay_audit.py --check`); the panel-scenario sim is `delays_sim` (extensive).
- Extensive runs a `_full` twin instead of its quick variant.
- Next cut: a test-timing scale so the same logic runs with shorter OSD timeouts / holds / sample periods (not built yet); then these gates can return to normal.

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
| osdfit (static, also a `./dev.py build` step) / infocard | normal | osdfitsim: every OSD shot at 1080p60 + 2160p60, firmware fit guard (ED 7E) |

Opt-in switches (each is easy to undo, Dan decides): inputrate `--info` (two informational sweeps), the minimal variants above.

## Clock matrix (extensive)
`scripts/gate_matrix.py BASE_STEM [--build]`: delays, wdt, wake, inputrate, monitor, deadport, panel, sysm, htime, keys on the 350 / 175 / 87 MHz image of one source state (siblings `<stem>-clk175-be`, `-clk87-be`; `--build` builds a missing one). Writes no gates.json.

## Fault injection
`tests/test_gate_mutations.py --slow` (set `AWTO_TEST_IMAGE`): every normal variant and the sped-up extensive gates must FAIL with a function RET'd in the image or a sim input changed, and pass clean. `tests/test_gate_tiers.py`: tier table + merge-check.

## Test image (tests/conftest.py, scripts/test_image.py, #339)
- Image tests take the fixture `fw_image` (`.stem .bin .map .build_json .settings_table`); variants: `fw_variant("clk87" | "t0ev" | "nofrc" | "<-D entry>")`; `fw_build_tree` = this tree with the asm of the base build (static delay analysis).
- Resolution: `$AWTO_TEST_IMAGE` (stem), else newest build of this tree at HEAD (`commit` / `dirty` in `<stem>.build.json`, no defines, gated first), else one `./dev.py build --tag testimg` (build_guard serialises; cached by commit). A variant is found by (commit, defines) or built as `<base tag>-<slug>`.
- `AWTO_TEST_NO_BUILD=1`: never build from a test (the fixture skips, reason names `fixture fw_image`).
- `./dev.py test` exports `AWTO_TEST_IMAGE` (resolve or build once). `./dev.py gate` = build, then tests with `--slow`, `AWTO_TEST_IMAGE` = its own build, `AWTO_TEST_STRICT=1`: an absent image FAILS the test; the summary prints the count of image tests skipped / failed for lack of an image.
- Tiers: plain `pytest` / `./dev.py test` skip `slow` tests (`--slow` runs them; the gate does).
- Marks: `hw` = real hardware, skipped unless `pytest --hw` or `AWTO_TEST_HW=1`; the unit comes from `AWTO_TEST_UNIT`. No test opens a bus, serial or unit by default and none names one.
