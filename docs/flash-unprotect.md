# SPI flash unprotect (Macronix MX25L8006E-class, RTD2795-class scaler)

Script: `scripts/rtd_flash_sector.py`. Datasheet: `~/vendors/macronix/MX25L8006E_v1.6.pdf`.

## Root cause
- Live status reg = 0x9C = SRWD (b7) + BP2..BP0 (b4..b2) all set [spec: Table 5, Table 2 level 7 = all protected]
- SRWD=1 and WP# low = Hardware Protected Mode: WRSR is rejected, SRWD/BP read-only [spec: Table 6, WRSR text]
- WP# is a scaler GPIO, held asserted in normal operation. Reads work, WRSR is silently ignored [fw]
  - Realtek RTDTool `PlugIn_ISP.dll` `FUN_1001bd80`: `WriteRegBitEx(0x1036,0xF8,0x01)` then `WriteRegBitEx(0xFE26,0xFE,ISP_WP bValueHigh)`; `bValueHigh` default 1 (`GetPrivateProfileInt ISP_WP`)
  - Same pair in naorunaoru/rtdflash `flash_prepare_write_rtd2795`; comment there: FE26.0 reads 0 in normal operation, leaving it keeps flash WP asserted [oss: rtdflash]
- Old script never touched WP#; WRSR(0x00) was sent while HPM was active -> no effect (WREN handling was not the problem)

## Corrected sequence (--write)
1. Release WP#: sys regs via scaler page select (`F4<-9F, F5<-page, F4<-reg, F5<-val`)
   - `sys[0x1036] = (v & 0xF8) | 0x01`; `sys[0xFE26] = (v & 0xFE) | 0x01`; read back each, abort on mismatch [fw]
2. Engine opcodes: `0x62=06 (WREN) 0x63=50 (EWSR) 0x6A=03 0x6B=0B 0x6D=02 0x6E=05` [oss: ghent360 SetupChipCommands, rtdflash common_setup]
   - 0x63=0x50 is unused on Macronix (EWSR is a Winbond/SST thing); harmless, matches both open-source tools
3. WRSR: `60<-68 (type3 WRITE_AFTER_WREN, nw=1), 61<-01, 64<-00, 60<-69`, poll 0x60 bit0
   - Engine emits `06` then `01 00` itself [oss: ghent360 `SPICommonCommand(E_CC_WRITE_AFTER_WREN,1,0,1,..)`]
   - WREN must precede every WRSR; WEL clears after WRSR [spec: WRSR, Data Protection]
4. Poll RDSR WIP clear (limit 50 ms = 1.25 x tW max 40 ms [spec: Table 13]); then require `SR & 0x9C == 0`, retry up to 3x, else abort naming the WP# cause
5. Erase 4K (`60<-B8, 61<-20, 64..66<-addr, 60<-B9` (type 5, nw=3; matches rtdflash); engine adds WREN), limit 250 ms = 1.25 x tSE max 200 ms [spec]
6. Blank check, page program (`6F<-A0`, per-page WREN done by engine [oss: rtdflash comment]), limit tPP 3 ms x1.25 (checked between I2C polls), read-back compare
7. Re-protect, only after `VERIFY OK` (also when the sector already equals the new data), regardless of the starting SR:
   - `--reprotect VALUE` (default `0x9C` = factory SRWD|BP2..0; `--reprotect none` skips)
   - order: release WP# (if not already) -> engine opcodes -> WREN+WRSR(VALUE) (same path as unprotect) -> RDSR must match VALUE & 0x9C -> restore sys 0x1036/0xFE26 to their pre-release values (WP# asserted, as factory) -> RDSR again
   - WRSR is done while WP# is released: SRWD=1 + WP# low locks the SR; re-assert only after
   - any failure before VERIFY OK (erase, blank check, program, verify): no re-protect attempted, SR left as is, rc != 0
   - re-protect failure: rc 8
   - then reset scaler (`EE<-02`; WP# GPIO also returns to default on reset)

## Flash-parameter reconciliation (P25Q80H vs Macronix)
- RTDTool `IspDebugLog.txt` "Get Flash Type: P25Q80H" is from third-party boards (JEDEC 85 60 14 per rtdflash); our unit is C2 20 14 [fw]
- RTDTool keys `FlashSet.dat` by JEDEC; the ID decides opcode set, not the scaler. Both are 1 MiB, 4K sector (0x20), 256 B page (0x02), WREN 06, RDSR 05, WRSR 01 [spec / oss]
- Decompiled ISP plugin has no flash-chip-specific WRSR path; the protection control is the ISP_WP GPIO. FlashSet.dat per-chip fields now decoded: `docs/reversing/realtek-rtd/db-bin-format.md` (record `c2 20 14`: SR count 1, disable-WP SR1 = 0x00, no SWREN script; erase/program opcodes are plugin constants) [fw]
- Which WP GPIO pair applies to this exact scaler (0x1036/0xFE26 vs 0x1029/0xFE19 also present in the plugin) is [guess] 1036/FE26: it is the RTD2795T profile in rtdflash. If SR stays 0x9C after the fix, try the other pair (FUN_1001bd10)

## Test status
- `rtd_flash_sector.py --selftest`: simulated chip; unprotect succeeds only with WP# released; without it fails loudly. Also: write from SR 0x00 -> ends 0x9C; from 0x9C -> ends 0x9C; forced verify failure -> rc 7, SR untouched; `--reprotect none` leaves SR
- Dry run on bus 20 (2026-11-04): JEDEC c22014, SR 0x9c, backup written. Not run with --write.

## State after the awto EDID flash (2026-11-04) — DEVIATION recorded, Dan's call
- bus /dev/i2c-20 (card1-DP-4) flash is left UNPROTECTED: status reg = 0x00 (factory was 0x9C = SRWD|BP2..0).
- Reason: the first write aborted mid-erase before the finally-block re-protect took; the recovery write was
  guarded with an all-FF --expect-current (sector already blank) and entered unprotected, so it skipped re-protect.
- Superseded by the always-re-protect change: the next successful `--write` on this unit (a no-op re-run with the same file also re-protects) leaves it at 0x9C. Earlier decision (Dan): LEAVE IT UNPROTECTED. Block-protect only guards against stray SPI writes; nothing on the board
  writes the flash except our deliberate ISP sessions. Re-protecting would mean another WRSR on the working unit.
- While it is 0x00, a write skips release_wp()/unprotect(); re-protect still releases WP# for the final WRSR.
  The OTHER two units are still factory-protected (0x9C) and will need the WP# release path.

## Known script fix still to apply
- The ORIGINAL abort was a too-tight engine-busy poll (POLL_MAX=20) on the 4K erase (tSE up to 200ms). The committed
  rtd_flash_sector.py already moved to TIME-BASED waits (1.25x MX25L8006E maxima), which fixes this. Confirmed: erase
  engine wait and WIP wait both use `T_ERASE_LIMIT = 0.25 s` (time-based, 1.25 x tSE max).
