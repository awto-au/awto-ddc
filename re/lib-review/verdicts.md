### ScalerGetDataPortSingleByte
**Verdict: different function, matcher artefact (not a build difference).**
- The matcher placement 6:5991 is the EXACT placement of `ScalerGetDataPortWord` (vendor bytes = lib bytes modulo fixups).
- Shared skeleton: `memset(array)`, `ScalerGetDataPortByte(...)`, then return from the array. 77.6% is that skeleton.
- Real differences vs the SingleByte lib body: array/count 2 instead of 1 (`R7` 02 vs 01), `bAutoInc` taken from the bit parameter (`MOV C,20h.6 / MOV 20h.7,C`) instead of the constant (`SETB`), return built from two bytes (`ADD/ADDC` tail) instead of one.
- The vendor image has no placement for the SingleByte body at all (ABSENT even under fuzzy matching with fixups masked): the module is not linked.
- Hot? No. No `.c` in the compiled tree (tmp/sdcc-port/src, RL6449 + common trees) calls `ScalerGetDataPortSingleByte`; only its own file and one header declaration mention it. `ScalerGetDataPortWord` (which the vendor links) has no caller either; the vendor's use comes from its own user code.

### ScalerColorRGBOutputGammaAdjust
**Verdict: same function, different source revision (real variant). The table-load bulk is identical; the entry logic differs.**
- Bulk identical: 3x (`ScalerColorOutputGammaChannelCtrl` + `ScalerBurstWrite` of one channel, port 0x66 GAMMA_PORT_SETA), channel offsets 0x0400/0x0800 via `ADD/ADDC`, DEN-stop waits (R7=0x20). This is the 72.5% fixed-byte match.
- Difference 1 (the gamma-on test): lib reads `RGB_GAMMA_CTRL_M1` (0x09D0) bit0 `rgb_gamma_en`; vendor reads `GAMMA_CTRL_SETA` (0x0067) bit6 `gamma_enable`.
- Difference 2: lib sets/clears `RGB_GAMMA_CTRL_M1` bit1 `rgb_gamma_port_enable` around the table write (0x09D0 `ANL #FD / ORL #02` and the clear); the vendor body has no 0x09D0 access, it only clears `GAMMA_CTRL_SETA` bit7 `gamma_access_port` (`ANL #7F`).
- Difference 3: control-flow layout (lib: if/else each calling the local channel-load routine, ends `RET`; vendor: the else path falls into the load routine and ends `RET`; branch offsets differ accordingly).
- All three shifts are consistent with the vendor using an older/other revision of this source (single gamma engine controlled through P0_67) while the SDK .LIB has the M1 write-enable. None of the RL6410/6432/6492 sources in the SDK has the vendor's form (all use P9_D0 bit0 like RL6449), so the vendor's revision is not in this SDK.
- For our firmware: this function matters (gamma load). Build from the SDK source; the SDK variant is the documented one for the RL6449 register set. Confirm on hardware (unit 3) that gamma loads with the SDK variant before relying on it.

### ScalerColorDCRLocalDimmingReadTHDResult
**Verdict (matcher placement 5:8044): different function, matcher artefact.**
- 5:8044 is the EXACT placement of `ScalerColorDCRReadResult`. Both begin with the same prologue (store arg byte, `?C?LSTKXDATA` zero of a DWORD, NOP pad for the library routine, `JNB DCR_ready`, `GetDataPortBit(CTS_BRI_PORT_ADD, 0x27, BIT0)`), which is the 63.8%.
- The real counterpart is the next table.

### ScalerColorDCRLocalDimmingReadTHDResult @0:c119
**Verdict: same function, different source revision (real variant), vendor function at 0:C119.**
- Same prologue, same `GetDataPortBit(CTS_BRI_PORT_ADD, idx 0x27, BIT0)` call (this is what `ScalerColorDCRGetLocalDimmingHistoEnable` was matched against).
- Difference 1: vendor tests `== 1` first and then the DCR-ready bit (`JB 25h.7`); lib tests ready first (`JNB`) and then `== 0`. Logically equal, different source order.
- Difference 2: lib returns `g_stDCRStoreInfo.ulDCR_LD_ABOVE_TH1_NUM / TH2_NUM` (a stored copy in XDATA); the vendor body appears to compute its result from live register reads (calls into shared register-read helpers with A=0x17 / 0x33, shifts by 3/6 and 1/2, `ANL #E0/#C0/#0E/#0C`) followed by a further helper call (1565h); this reading is from the disassembly only, the helpers were not decoded.
- So the vendor's function is a different algorithm behind the same name and prototype, not a patched copy. Not in the SDK sources (RL6410 has the same body as RL6449 bar comments).
- Matters only if local dimming is used; our panel path does not call it unless DCR local dimming is enabled.

### ScalerColorDCRGetLocalDimmingHistoEnable
**Verdict: different function, matcher artefact.**
- The 15-byte .LIB function is `return GetDataPortBit(CTS_BRI_PORT_ADD, 0x27, BIT0)`. Its first 11 bytes (4 argument loads and the call) equal the inside of vendor 0:C119 above, and the vendor has the same sequence also in the `ScalerColorDCRReadResult` sibling (5:8054).
- No standalone copy exists in the vendor banks (exhaustive search for the 11-byte prefix: only those two places). 76.9% is 10 of 13 fixed bytes of a prefix inside a different function.
- Callers in SDK sources: SysColor.c, UserCommonAdjust.c (DCR local dimming only).

### ScalerColorHLWOutputGammaAdjust
**Verdict: different function (sibling), matcher artefact; fixed in rtk_libsig.py (class SIBLING).**
- 6:6359 is the EXACT placement of `ScalerColorHLWDCRAdjust` (lib bytes equal except the one index constant).
- The three lib functions are the same 34-byte wrapper `ScalerSetDataPortBit(HLW_ADDR_PORT (0x0060), index, mask 0xCF, value)` and differ only in index: HLWDCRAdjust 0x0D, HLWOutputGammaAdjust 0x0E, HLWIAPSGainAdjust 0x0F. Vendor has index 0x0D, i.e. the DCR one.
- The vendor image has no placement for the 0x0E / 0x0F variants (not linked). Score 95.8% = 23 of 24 fixed bytes (one constant).
- The vendor bytes after the `LJMP` (rows marked vendor-only) belong to the next function.

### ScalerColorHLWIAPSGainAdjust
**Verdict: different function (sibling), matcher artefact. Same as above, index 0x0F vs vendor 0x0D. Both NEARs hit 6:6359 because their bytes differ from `ScalerColorHLWDCRAdjust` in one constant only, so they tie on the same best placement; the matcher did not check that another lib function already owned the address.**

### ScalerTcon0Enable
**Verdict: different function (look-alike), matcher artefact. Vendor has no TCON enable wrappers.**
- Lib `ScalerTconNEnable(bEnable)` = `ScalerSetDataPortBit(TCON_ADDR (0x15A3), index 0x18+0x10*N, 0x7F, bEnable<<7)` then `LJMP`.
- Vendor 2:FCE7 is `ScalerSetDataPortBit(DISPLAY_FORMAT_ADDR_PORT (0x002A), index 0x25, 0x7F, bit<<7)` with a different tail (a function in the next block follows). Same wrapper shape, other port/index: 85% = the shape.
- All 14 TCON wrappers tie at 85% on the same vendor address (table below this section). A direct search of every vendor bank for `MOV R7,#A3 / MOV R6,#15` (the TCON_ADDR port) finds nothing: the vendor never calls the TCON data port through these wrappers, they are unlinked.
- The source is only in other series' trees (RL6432/6410/6492 `*_Tcon0.c`, identical shape); the RL6449 tree has the lib only.
