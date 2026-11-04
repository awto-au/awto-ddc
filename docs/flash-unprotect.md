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
7. Restore original SR (`WRSR sr0 & 0x9C`, same WREN path) in `finally`, then reset scaler (`EE<-02`; WP# GPIO returns to default on reset)

## Flash-parameter reconciliation (P25Q80H vs Macronix)
- RTDTool `IspDebugLog.txt` "Get Flash Type: P25Q80H" is from third-party boards (JEDEC 85 60 14 per rtdflash); our unit is C2 20 14 [fw]
- RTDTool keys `FlashSet.dat` by JEDEC; the ID decides opcode set, not the scaler. Both are 1 MiB, 4K sector (0x20), 256 B page (0x02), WREN 06, RDSR 05, WRSR 01 [spec / oss]
- Decompiled ISP plugin has no flash-chip-specific WRSR path; the protection control is the ISP_WP GPIO. FlashSet.dat per-chip fields now decoded: `docs/reversing/realtek-rtd/db-bin-format.md` (record `c2 20 14`: SR count 1, disable-WP SR1 = 0x00, no SWREN script; erase/program opcodes are plugin constants) [fw]
- Which WP GPIO pair applies to this exact scaler (0x1036/0xFE26 vs 0x1029/0xFE19 also present in the plugin) is [guess] 1036/FE26: it is the RTD2795T profile in rtdflash. If SR stays 0x9C after the fix, try the other pair (FUN_1001bd10)

## Test status
- `rtd_flash_sector.py --selftest`: simulated chip; unprotect succeeds only with WP# released; without it fails loudly. Prints the exact reg writes
- Dry run on bus 20 (2026-11-04): JEDEC c22014, SR 0x9c, backup written. Not run with --write.
