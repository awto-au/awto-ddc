# Script triage (#304)

Scan 2026-11-22 on 2949ca69: module-name word match over tracked text files (excl. `fw/sdk`, `fw/sdk-parked`, `regdb`, `debris/`, the file itself).
- `none` = referenced nowhere; `docs` = only from docs/*.md; `code` = from dev.py, tests, scripts, tools, fw or systemd (not listed, all kept).
- Last commit = last non-refactor commit date; author = first commit.
- Re-run: `./dev.py orphans` (table in tmp/tmp_audit/orphans.tsv).

## Scan 2026-11-27: 20 new orphans (scripts added 2026-11-23 .. 11-25) + 4 orphaned by the deletes

| script | purpose | issues | decision |
|---|---|---|---|
| dfe_check_equiv | host proof: DpRx1 DFECheck lane-helper merge == originals | #300 (closed) | deleted (last 7ef8410b) |
| dptx_lane_equiv | host proof: merged eDP lane Adjust == 8 per-lane originals | #295 (closed) | deleted (last 60272f9f) |
| pdata_exint_equiv | proof: pData_EXINT -> locals rewrite changed nothing else | #328 (closed) | deleted (last 1ca13b6d) |
| freeze_trials | freeze a failed 4K60 pass, try SDK-value register candidates | #26 (closed) | deleted (last 85672132) |
| branch_status | branches with commits outside wb-p14ui (retired line) and main | - | deleted (last 49b518e1) |
| tp_check_equiv | host proof: Tp1/Tp2Check_EXINT0 lane-loop merge == originals (orphaned by dfe_check_equiv) | #299 (closed) | deleted (last 261cb255) |
| dpll_hold | DPLL fine-offset sweep on a frozen 4K60 pass (orphaned by freeze_trials) | #26 (closed) | deleted (last 7f550a14) |
| freeze_dump | dump every scaler page of a frozen failed pass over 0x35 (orphaned by freeze_trials) | #26 | keep (generic) |
| regs_diff4k | diff two tmp/regs dumps register by register with regdb names | #26 | keep (generic) |
| aux_traffic | read-only DP AUX EDID reads for the TMDS PHY event-loss test | #256* | keep |
| aux_window_sim | DPTx AuxRead / AuxWrite poll window per image in the sim | #295 | keep |
| ctemp_regs | colour-temperature presets -> CTS coefficients read back from a unit | #278* | keep |
| ctemp_sim | colour-temperature presets in fw_sim | #278* | keep |
| dptx_lt_sim | eDP link training in the sim with a DPCD sink model | #295 | keep |
| drm_conn_prop | read-only DRM connector properties (Broadcast RGB, max bpc) | - | keep |
| gen_flash_wren | ScalerFlashWREN per-chip table generator + host proof | #296 | keep (generator) |
| hot_data | rank small XSEG objects by `mov dptr` loads: `__data` candidates | #335* | keep |
| kc_asmdiff | per-function diff of two compiler asm trees (tmp/runs/<tag>) | awto-sdcc#25 | keep |
| mem_map | flash memory map of an image as one HTML page | - | keep |
| port_status | per-port status word of a running unit over the debug link | #323* | keep |
| review_list | one page of issues waiting for Dan (needs-dan / needs-test / ready-to-close) | - | keep |
| sdcc_mem_report | RAM allocation report of an SDCC -S tree | #8 | keep |
| sdk_park_funcs | park whole-feature `#if` function blocks to fw/sdk-parked | #305 | keep |
| sim_pcprofile | PC sampling over a sim time window | #216 | keep |
| warn_shift | re-key fw/warn_policy.tsv rows after SDK lines moved | - | keep |

## Referenced nowhere (70)

| script | last | by | purpose | issues | decision |
|---|---|---|---|---|---|
| audio_levels | 2026-11-20 | bot | Ear test of loudness/clipping per user volume (#94): for each VCP 0x62 | #94 | delete |
| audit_chat | 2026-11-20 | bot | Extract genuine human messages, pop-up answers, assistant text and com | - | keep |
| boot_prof_sim | 2026-11-20 | bot | Boot profile in the sim (#144 / #162): the probe times of boot_prof.py | #144*,#162* | keep |
| build_edid_sector | 2026-11-20 | bot | Build a per-unit 4 KiB EDID sector (0x13000) from the IPS/sRGB templat | - | keep |
| dead_code_maps | 2026-11-20 | bot | Build the default image + opt-in variants, then run dead_code.py over  | #209* | keep |
| diag_build | 2026-11-20 | bot | Build a wb-p14ui-diag image (awto-ddc#157): dev.py build with the nv l | #157 | delete |
| fw_boot_reg | 2026-11-20 | bot | Boot an image in the simulator (native banking, as fw_sim --boot-check | - | delete |
| fw_link_check_test | 2026-11-20 | bot | Offline tests for fw_link_check.py on synthetic 2-bank images (no firm | - | keep |
| fw_lmu_manifest | 2026-11-20 | bot | Resolve LG OnScreen Control firmware endpoints into a fw_pkg_fetch sou | - | keep |
| fw_sim_abi_test | 2026-11-20 | bot | Offline tests for fw_sim's ABI handling (SDCC levels 0-2 vs --sdcccall | - | keep |
| fw_sim_mdomain | 2026-11-20 | bot | M-domain memory-select decision trace + wide register diff vs the vend | #26 | debris/code |
| fw_xdata_map | 2026-11-20 | bot | Histogram of XDATA addresses an 8051 firmware image references via `MO | - | delete |
| fw_xfr_writes | 2026-11-20 | bot | Static: list every `MOV DPTR,#addr` + following read/modify/write for  | - | delete |
| hdcp_key_scan | 2026-11-20 | bot | Locate HDCP 1.4 / 2.2 key records in flash dumps; prints offsets, leng | #44* | keep |
| hdmi_phy_trials | 2026-11-20 | bot | awto-ddc#55: freeze a failed 4K60 pass, read SCDC char-error rates + R | #55 | delete |
| hold_sim | 2026-11-20 | bot | Held test visual in the fw_sim model (#28): does a held pop-up (consol | #144*,#28 | keep |
| host_note_sim | 2026-11-20 | Dan | #273 in fw_sim: host notes (text slot + test cmd AWTO_TC_HOST_NOTE) -> | #273* | keep |
| i2c_rate_test | 2026-11-20 | bot | Failure rate of the firmware debug slave 0x35 per DDC bus rate (#12).  | #12 | debris/code |
| i2c_shapes | 2026-11-20 | bot | READ-ONLY 0x35 diag-magic read in every transaction shape; shows which | #28 | delete |
| i2c_trace | 2026-11-20 | bot | Who talks on the host's i2c adapters (incl. DisplayPort I2C-over-AUX = | - | delete |
| icon_raster | 2026-11-20 | bot | Rasterise Material Symbols SVGs to 1-bpp OSD cell sizes + contact shee | - | keep |
| idle_passes | 2026-11-20 | Dan | How many main-loop passes do nothing? (exact fast-forward potential of | - | delete |
| isp_read_check | 2026-11-20 | bot | Read-path check: flash read with 64 B vs N B FIFO reads must give the  | #61,#71 | delete |
| kc_asm_classify | 2026-11-20 | bot | Classify per-function asm differences of two runs: rename-only (helper | #36 | delete |
| layout_diff | 2026-11-20 | bot | Diff two bank_layout.tsv files: symbols whose region (C = common / ban | - | keep |
| lazytimer_check | 2026-11-20 | bot | Differential fuzz of mcs51_core.c timers: an old core revision vs the  | #183 | debris/code |
| mem_mode_sim | 2026-11-20 | Dan | #165 step 2 in fw_sim: test cmds 0x0C (frame buffer forced) / 0x0D (SD | #165*,#26 | keep |
| menu_open_time | 2026-11-20 | bot | Sim time of the awto menu open and of its font load (before / after th | #87* | keep |
| menu_walk_timing | 2026-11-20 | bot | menu_cli walk in fw_sim with a wide mailbox budget, timing every mailb | - | delete |
| msg_nohost_sim | 2026-11-20 | Dan | Sim check (#56): debug messages firing with no host / a silent host mu | #56* | keep |
| msg_table_test | 2026-11-20 | Dan | Offline tests for scripts/msg_table.py (#56): encode/decode, stability | #56* | keep |
| nv_boot_sim | 2026-11-20 | bot | Boot the sim with real NVRAM pages (dumps of bank 15 pages 11-12) and  | - | delete |
| nv_items | 2026-11-20 | bot | List the SDK EEPROM-emulation items in dumped NVRAM pages (bank 15 pag | - | delete |
| osd_cleanup_report | 2026-11-20 | bot | OSD cleanup ledger: flash bytes (from the build map) and source lines  | - | delete |
| osd_icon_render | 2026-11-20 | bot | Render a 6x4-tile 1-bit main-menu icon (tFONT1_ICON_<NAME>) from the p | #46* | keep |
| param_cost | 2026-11-20 | bot | Byte cost of arg 2+ passing (_X_PARM_n) in the built firmware, and wha | - | debris/code |
| pe_exports_scan | 2026-11-20 | bot | Static PE scan of an unpacked RTDCustomerTool tree: exports, CodeView  | - | delete |
| phy_probe_runs | 2026-11-21 | Dan | Repeated HDMI re-locks of unit 3 with the AWTO_TMDS_PHY_PROBE image: p | #256* | keep |
| pip_try | 2026-11-20 | bot | #164 PIP hands-on: read / poke scaler registers over debug slave 0x35  | #164 | delete |
| popup_frames | 2026-11-20 | Dan | Every small pop-up card on the full panel frame (sim), one PNG each +  | - | delete |
| prefill_hw | 2026-11-21 | bot | #83 pre-fill on hardware: wait for the idle-D1 cache pre-fill after a  | #83* | keep |
| prefill_sim | 2026-11-20 | bot | #83 idle-port cache pre-fill in the fw_sim model: HDMI on D2 on screen | #83* | keep |
| premain_sim | 2026-11-20 | bot | Instructions and machine cycles from reset to main() in the sim, and w | #63 | delete |
| regcall_build | 2026-11-20 | bot | Build the firmware once per --sdcccall level and keep the artefacts (a | - | delete |
| rtd_pinshare_decode | 2026-11-20 | bot | Decode a live RL6449 pin-share dump (page 0x10) against an SDK *_PINSH | - | delete |
| rtd_reg_decode | 2026-11-20 | bot | Name a rtd_reg_dump.py capture with the regdb: list registers whose va | - | delete |
| rtd_settings_diff | 2026-11-20 | bot | Show byte offsets in the settings area (default 0xFB000-0xFD000) that  | - | delete |
| rtd_xfr_diff | 2026-11-20 | bot | Read-only: dump MCU XFR ranges (DDC / DDC-CI / bank control) from seve | - | delete |
| rtd_xram_probe | 2026-11-20 | bot | Find the RTD2795T's real XRAM extent over ISP (MCU halted): dump and/o | - | delete |
| screens_diff | 2026-11-20 | Dan | Compare two osd_catalog.py output directories pixel for pixel: prints  | #122,#137* | keep |
| sdcc_bank_stackargs_test | 2026-11-20 | bot | A function that reads stack-passed args via SP/_bp must be common (stu | #11 | delete |
| sdcc_link_test | 2026-11-20 | bot | Offline test for sdcc_link.dseg_runs: DSEG split around the bit bytes  | - | keep |
| sdk_park | 2026-11-20 | bot | Park SDK sources that link 0 B: move them from fw/sdk to fw/sdk-parked | #165* | keep |
| sector_diff | 2026-11-20 | Dan | usage: sector_diff.py A.bin B.bin  -> number of differing 4 KiB sector | #56* | keep |
| sim_core_compare | 2026-11-20 | bot | Run every regression image on two awto-ddc cores (dw8051 mode) and req | #183 | delete |
| sim_loop_speed | 2026-11-20 | bot | Main-loop host speed of the fast sim core on one image (awto-ddc#183): | #183 | delete |
| sim_profile | 2026-11-20 | bot | Where the fw_sim wall time goes (boot to ACTIVE + N s of firmware time | - | delete |
| sim_regs | 2026-11-20 | bot | Boot an image in fw_sim to ACTIVE and print scaler registers: compare  | #137* | keep |
| strip_funcs | 2026-11-20 | bot | Delete C function definitions + their one-line prototypes by name (#20 | #209* | keep |
| sw_table | 2026-11-20 | bot | #60 timing table: alternate D2 -> D1 and D1 -> D2 switches N times eac | #60 | delete |
| sweep_diff | 2026-11-20 | bot | Before/after table of two mode_sweep TSVs (first row per mode; the res | - | delete |
| sweep_ppm | 2026-11-07 | bot | Measured-vs-host refresh offset per mode from a mode_sweep TSV (measur | - | delete |
| timebase_probe | 2026-11-20 | bot | Check the firmware ring clock against the host clock across a cold pow | #144* | keep |
| tmds_ab | 2026-11-20 | Dan | A/B of the TMDS ISR diet on a unit (#256): per run reset, sample the T | #256* | keep |
| trace_diff | 2026-11-20 | bot | Diff two fw_sim_trace.py TSVs (vendor vs ours) over DISPLAY_SETTING -> | #26 | delete |
| unifdef_opt | 2026-11-20 | bot | Make build options unconditional: resolve `#if` on fixed option values | #165* | keep |
| warn_policy_renum | 2026-11-20 | bot | Renumber fw/warn_policy.tsv rows whose file:line moved after code was  | - | delete |
| worktree_review | 2026-11-20 | Dan | Review every git worktree of a repo (read only): merged into main? ahe | - | deleted 2026-11-27 (superseded by `./dev.py worktree-sweep`; last 49b518e1) |

`*` = issue still open. keep = open issue, reusable tool, or offline test of a kept tool (a kept test script nobody runs is a follow-up: wire into `tests/`).

## Referenced from docs only (68): all kept

| script | referenced from |
|---|---|
| bl_knob_sim | docs/bl-delay-sweep.md |
| boot_profile | docs/delay-audit.md |
| boot_variance | docs/delays.md |
| branch_prune | docs/history.md |
| cec_pi_test | docs/cec.md |
| clone_scan | docs/duplicate-code.md |
| con_blank_probe | docs/delays.md |
| con_colours_sim | docs/osd.md |
| dahua_gpio_audit | docs/reversing/dahua-fw/gpio-ir.md, docs/reversing/dahua-fw/register-audit.md |
| ddc_probe | docs/history.md |
| delay_sites | docs/delays.md |
| doc_photos | docs/monitors/boards.md |
| dp_aux_probe | docs/data-channels.md |
| dp_isp_bench | docs/flash-dp-aux.md |
| flash_layout_measure | docs/delays.md, docs/flash-layout.md, docs/self-flash.md |
| flash_screen_pic | docs/flash-screen.md |
| flash_soak | docs/clock-sweep.md |
| fw_stage | docs/delays.md |
| fw_variants | docs/delays.md |
| ghidra_match_sdk | docs/re-full-reversal.md, docs/reversing/8051-reuse-playbook.md |
| ghidra_merge_lib_names | docs/re-full-reversal.md |
| ghidra_re_stats | docs/re-full-reversal.md, docs/reversing/8051-reuse-playbook.md |
| host_output_drop | docs/power-levels.md |
| irq_masks_hw | docs/irq-masks.md |
| keil_probe | docs/reversing/8051-reuse-playbook.md |
| keil_sdcc_scan | docs/genconstprop-switch.md, docs/keil-vs-sdcc.md |
| keil_uv_flags | docs/reversing/8051-reuse-playbook.md |
| kvm_demo | docs/delays.md, docs/history.md |
| led_unit | docs/delays.md |
| lib_review | re/lib-review/README.head.md, re/lib-review/README.md |
| logo_decode | README.md, docs/osd.md |
| map_size_diff | docs/watchdog.md |
| menu_shot | docs/reversing/dahua-fw/gpio-ir.md |
| nv_burst | docs/nvram-settings.md |
| nvram_list | docs/nvram-settings.md |
| osd_font_scan | docs/qc-osd-suite.md |
| osd_logo_big | docs/osd-editor-spec.md |
| osd_screens_md5 | docs/osd/path-cost.md |
| osdt_unit | docs/delays.md |
| philips_probe | docs/README.md, docs/monitors/README.md |
| philips_raw_ddc | docs/README.md, docs/monitors/smartcontrol-wine.md |
| qc_suite_unit | docs/osd/api.md, docs/qc-osd-suite.md |
| reg_behind_indirect | docs/README.md, re/regmap/README.md |
| reg_live_diff | docs/live-register-scan.md |
| regdb_pack | README.md |
| rtd_dump_info | README.md, docs/monitors/README.md |
| rtd_extract_all | docs/delays.md, docs/reversing/realtek-rtd/extraction.md |
| rtd_panel_aux | docs/monitors/panel-edid.md |
| rtd_pin_ledger | docs/monitors/rtd2795t-pin-audit.md |
| san_bench | docs/sanitizer.md |
| sdcc_size_probe | docs/delays.md |
| sdk_option_audit | docs/delays.md |
| smartcontrol_probe | docs/README.md, docs/monitors/smartcontrol-wine.md |
| stack_high | docs/history.md |
| startup_clear_cost | docs/flash-sector-churn.md |
| vlc_probe | README.md, docs/osd.md |
| worktree_prune | docs/history.md (deleted 2026-11-27, superseded by `./dev.py worktree-sweep`; last 49b518e1) |
| xdata_churn_probe | docs/flash-sector-churn.md |
