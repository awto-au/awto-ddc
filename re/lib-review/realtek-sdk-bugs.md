# Bugs found in Realtek's own SDK source (RL6449 line)

Found 2026-11-05 by an audit agent + review (awto-ddc#20 area; filed as awto-ddc#100). Source tree: `tmp/sdcc-port/src` of the p14 line (Realtek confidential, repo stays PRIVATE; this doc describes, it does not quote).
Tags: [fw] read in the source; [guess]; [?]. Keil C51 and our SDCC store multi-byte values the same way and use 16-bit `int`, so the Dahua binary has the same faults wherever it takes the same path [guess: not checked in the Dahua decompile].

## 1. One-byte write lands on a 4-byte value (FRC)
- Where: `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_FRC.c:1040`, `ScalerFRCCompareIHFandDHF`; consumer `ScalerFRCOneFrameCtrl` (:1088 call, :1192 body) [fw].
- What: `pData[8]` is the top byte of `PDATA_DWORD(2)` (DHF = panel line rate; IHF = input line rate). The code sets `pData[8]` to `_BIT3` when IHF > DHF, i.e. adds 0x08000000 to DHF [fw].
- Effect: input faster than panel -> DHF becomes huge (1333 -> 134,219,061), so IHF <= DHF and the input-slower branch runs; it computes `usVHeight * ulDHF / ulIHF` into 16 bits (truncates) and programs the one-frame FRC margins from that. The input-faster branch can never run through this call [fw]. Input slower: `pData[8]` = 0, nothing corrupted [fw].
- Reached only with free-run memory and a 1-frame buffer; `_ONE_FRAME_FRC_SUPPORT` is ON in our config [fw].
- Fix (not applied): a separate scratch byte for the flag.

## 2. 16-bit multiply overflow (DPLL fine tune)
- Where: `Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c:2388` and `:2392`, `ScalerDPLLFineTuneFrameSyncFrameBuffer` [fw].
- What: `(DWORD)(usHTotal * (PDATA_WORD(0) - PDATA_WORD(1)))`: the cast to DWORD comes after the multiply, so the product is 16-bit [fw].
- Effect: with our panel's HTotal 4000, any DV-total gap above 16 lines overflows (4000 x 17 = 68000 -> 2464). The wrong limits feed `ScalerPLLSetDPLLOffset` (panel clock offset registers P1_C4..C6): wrong offset, cannot hang the chip [fw]. Reached only in `_MN_FRAME_SYNC_MEMORY` mode [fw].
- Fix (not applied): cast before the multiply.

## Status
- Fixes were held until the Dahua firmware's memory mode at 4K60 was known (fixing a bug the working original also has would make us differ from it). 4K60.000 now runs in line-buffer mode on our images (the `~bit` fix, awto-sdcc `--keil-compat`), so neither path is exercised at 4K60 [guess]. Check `_MN_FRAME_SYNC_MEMORY` / one-frame FRC use per mode before patching.
- Related Keil-vs-SDCC differences (not SDK bugs): awto-sdcc `docs/keil-vs-sdcc.md`.
