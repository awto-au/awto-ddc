# --nogenconstprop switch

- Build default: `--nogenconstprop` stays (scripts/fw_compile.py). SDK delay loops poll ISR-set flags (awto-ddc#23, ScalerTimerDelayXms endless loop).
- Switch: `AWTO_GENCONSTPROP=on ./dev.py build ...` drops the flag for that build. Any other value or unset keeps it.
- Precondition for `on`: interrupt-shared globals are volatile (commit "volatile on interrupt-shared ...") and the compiler has awto-sdcc#156 (genconstprop scoped to non-local objects, commit 93c996cd77).

## Offline A/B 2026-11-20 (build 977817123a dirty vs awto-sdcc-161 = bd2fc97250 incl. 93c996cd77; not a b839ff7198 stamp)
- Same tree (bedee736), compiler 161, flag on vs off: code bytes (non-0xFF in .bin) 749292 -> 736072 (-13220, includes layout shifts); DDOVLS 0x6d -> 0x69 (-4 B IRAM after overlay); free XDATA 183 -> 181 B; sim cycles/pass 163231 -> 163232, work 76844 -> 76776.
- `on` needs 46 new warn_policy rows first: "conditional flow changed by optimizer" in ScalerCommonNVRam (16), RTD2014NVRamOsd (6), ScalerPLL (4), DPRx1 (3), ScalerIDomain (3), UserCommonInterface (3), our testcmd (3 + 1 unreachable), ddcci (2), console (2), cec_msg, Osd, ScalerColor, DP_SeptPhy (1 each). Each is a folded condition: review for ISR-polled flags (the #23 class) before adding rows. Measurement builds used a wildcard row, not committed.
- Sim gates on the `on` image: boot_sim FAIL ("bite: line times never step back": console times 113 then 111 ms after the watchdog bite); the same compiler with the flag passes boot_sim. Not root-caused. The other gates were not meaningful (layout files restored after the A/B); rerun on a clean `on` build.
- Not run: delay_cal_check, unit boot test.

## After the compiler refresh (/usr/local)
1. Re-pin `SDCC_COMMIT` in scripts/fwimage.py (and the docstring line 4) to the new install stamp.
2. Build default image and an `on` image with the same compiler; compare code bytes, IRAM after overlay, free XDATA (build log), `scripts/speed_bench.py IMAGE --no-record`.
3. Sim: `scripts/fw_gates.py IMAGE_STEM` ALL PASS on the `on` image; `python scripts/delay_cal_check.py BIN MAP`; `python scripts/delay_audit.py --write` then `--check`.
4. Unit boot test (test unit only, units in `scripts/devices.json`): flash the `on` image, `./dev.py health` (delay-cal row, 4 ms paced loop rate). Rest the unit per its rest-mode rule afterwards.
5. All pass: delete `GENCONSTPROP` and the flag line in fw_compile.py in one commit; the default build then runs without `--nogenconstprop`.
6. Any failure: leave the default; file the failing site in awto-ddc#23.

## Not linked in the current image
- ISR_SHARED_NONVOLATILE rows of re/keil_sdcc_scan.tsv for DpRx0, MHL, MST, HDCP2, IR, LCTank, timer axis counters and logo timer are not compiled for RL6449 here (no asm in tmp/sdcc-port/asm). Mark them volatile when a build links them.
- Rows name the SDK originals (`g_x`); our tree renames ISR-shared ones `isr_g_x` / `d_isr_g_x`. TMDSRx2/3 LE tables, DpRx1 lane count and g_pucDdcciTxBuf keep SDK names.
