rows = """
e204|ScalerAudioD1DPAudioInitial|high|PB9 AUD_FREQUENY_TH 00 00 28 4C 5C 70, RS dec, I/P code; callee e813=D1SetAudioPLL, e958=D1DPSetDVCVolumeAdjustType; SDK ScalerAudio_SeptPhy.c ScalerAudioD1DPAudioInitial
e813|ScalerAudioD1SetAudioPLL|high|PB9_D1..D7 MN_SCLKG PLL power-down/M/WD/INSEL/power-up sequence; only caller e204; SDK RL6449_Series_Audio.c D1SetAudioPLL
e958|ScalerAudioD1DPSetDVCVolumeAdjustType|high|PB9_76 DVC_CTRL/PB9_77 DVC_VA + window size (PB9_78/79) inlined; SDK ScalerAudioD1DPSetDVCVolumeAdjustType
c7a7|ScalerAudioD2HDMIAudioInitial|high|P71 HDMI_AP data-port sequence (AFCR/WDCR0/PSCR/AAPNR..., I/P code 0/2, 7F/FF), first call e101=D2SetAudioPLL; SDK RL6449_Series_Audio.c
e101|ScalerAudioD2SetAudioPLL|high|P71 DPCR0 power down, M code, K code, VCO band, DPCR2/3, power up, CMP/latch/calibration; SDK D2SetAudioPLL
ded1|ScalerAudioD3SetAudioPLL|high|same as e101 on P72 page; first call in D3 initial; SDK D3SetAudioPLL (SeptPhy)
fec2|ScalerAudioDigitalAudioInitial|high|calls e204 (D1), c7a7 (D2), ded1 then falls into D3HDMIAudioInitial body (P72 page, Keil fall-through); SDK ScalerAudioDigitalAudioInitial
feec|ScalerAudioInitial|med|calls fec2 then DVC_EN/ZC_WIN/volume-type/gain regs = ScalerAudioDVCInitial fall-through; SDK ScalerAudioInitial
f00a|ScalerAudioADCInitial|high|AD_CTRL 0x48, REG_ADC_POWER C0, ADC_CTRL 0x39, AFE_GAIN 0x44/0x77 by IDCode, AD_GAIN 0x17, SPDIF_CS; SDK ScalerAudioADCInitial
f39f|ScalerAudioDACInitial|high|REG_DAC_POWER0, DA_CLK_CTRL=0x12, DAC_POWER1=0xF1, DA_GAIN L/R 0x57, MUX_ANA_OUT; SDK ScalerAudioDACInitial
f710|ScalerAudioDACSetOutputGain|high|REG_OUT_GAIN: type1 speaker <<4, type2 HP, type3 both; SDK ScalerAudioDACSetOutputGain
fe59|ScalerAudioDACSetVcmReady|high|REG_ANA_CTRL bit0 = bReady; SDK ScalerAudioDACSetVcmReady
f8ba|ScalerAudioDACNormalToDepop|high|VcmReady off, AOUT/HPOUT ctrl bit3 clear + bits7:6 set, VcmReady on, state=DEPOP; SDK ScalerAudioDACNormalToDepop
fbe2|ScalerAudioDACDepopToNormal|high|AOUT/HPOUT ctrl bit3 set, VcmReady off, state READY; SDK ScalerAudioDACDepopToNormal
f88e|ScalerAudioDACOutputEnable|high|VcmReady off, enable AOUT/HPOUT if REG_DAC_POWER0 bit5/bit4, VcmReady on; SDK ScalerAudioDACOutputEnable
fa25|ScalerAudioDACOutputSwitch|high|REG_DAC_POWER0 bits5:4 from output type (1 spk, 2 hp, 3 both, else none); SDK ScalerAudioDACOutputSwitch
fad6|ScalerAudioDACGetOutput|high|compares REG_DAC_POWER0 & 0x30 against 30/20/10; SDK ScalerAudioDACGetOutput
fe2b|ScalerAudioDACSetState|high|state byte e245 low 3 bits = state, bit3 = state-change flag; SDK ScalerAudioDACSetState
fedc|ScalerAudioDACGetState|high|returns e245 & 7; SDK GET_AUDIO_DAC_STATE
fee4|ScalerAudioDACClrStateChange|high|e245 &= ~0x08; SDK ScalerAudioDACClrStateChange
f3e9|ScalerAudioDisable|high|cancel 3 timer events, NormalToDepop, VcmReady off, DAC/ADC power down, DVC counter off, fa6d=DisableAudioPLL; SDK ScalerAudioDisable
fa6d|ScalerAudioDisableAudioPLL|high|power down ADC PLL (PBF_BD), D1 (PB9_D3), D2/D3 DPCR0 bit7 (P71/P72); SDK ScalerAudioDisableAudioPLL
ebb3|ScalerAudioSetADCAudioPLL|high|PBF_A0..C1 MN_SCLKG ADC PLL: DIVM 0x33, DIVS 8, OFFS, PWR sequence; SDK ScalerAudioSetADCAudioPLL
eb20|ScalerAudioSourceInputSwitch|high|source 1 digital: input port mux (fbac) else ADC path (ebb3), DA_MUTE, DVC_EN, REG_OUT_GAIN; SDK ScalerAudioSourceInputSwitch
fbac|ScalerAudioInputPortSwitch|high|MUX_DA_DVC_IN[2:0] and MUX_DIG_OUT = input port; SDK ScalerAudioInputPortSwitch
f7d5|ScalerAudioGetDigitalAudioPort|high|output type 0 MUX_DA_DVC_IN&7, 1 (MUX_DIG_OUT&0x70)>>4, 2 MUX_DIG_OUT&7; SDK ScalerAudioGetDigitalAudioPort
f833|ScalerAudioGetDigitalAudioPortMapping|high|switch on f7d5(DAC out) -> input port; SDK ScalerAudioGetDigitalAudioPortMapping
ecc2|ScalerAudioSamplingFreqDetect|high|port 5->f5f6 (D2), 6->f352 (D3), 4->f4c0 (D1) then type->packet switch; SDK ScalerAudioSamplingFreqDetect
f4c0|ScalerAudioD1SamplingFreqDetect|high|PB9_61 AUD_SAMPLE_CNT_0>>4, DA_CLK_CTRL[7:6] by freq class, store low nibble e213; SDK D1SamplingFreqDetect
f5f6|ScalerAudioD2SamplingFreqDetect|high|P71 data port 0x8B & 0x0F, DA_CLK_CTRL by freq class, store low nibble e215; SDK D2SamplingFreqDetect
f352|ScalerAudioD3SamplingFreqDetect|high|same on P72 page, store low nibble e217; SDK D3SamplingFreqDetect
f47b|ScalerAudioLPCMCheckData|high|port 5/6 HDMI_SR bit4 (P71/P72), port 4 DP_AUD_CTRL bits5:4 XOR test; SDK ScalerAudioLPCMCheckData
f742|ScalerAudioLPCMCheckInfo|high|P71/P72 data port 0x15 & 0xF0 in {0x00,0x10}; SDK ScalerAudioLPCMCheckInfo
f774|ScalerAudioDigitalOutputMute|med|port 5/6 AVMCR bit5 on P71/P72, port 4 DP_CHANNEL_EN (fe4a) = ~mute; SDK ScalerAudioDigitalOutputMute
f804|ScalerAudioWatchDogProc|high|per-port dispatch to D1 (f9b3) / D2 (fb37) / D3 (faf7) watchdog; SDK ScalerAudioWatchDogProc
f9b3|ScalerAudioD1WatchDogProc|high|DP_AWD_CTRL (PB9_39) 0xC0 on/off, AUD_BUFFER_CTRL (PB9_70) clear, FSM reset; SDK D1WatchDogProc
fb37|ScalerAudioD2WatchDogProc|med|P71 data port 0x31 WDCR0 mask F9 / 6, HDMI_SR 0x71CB; SDK D2WatchDogProc
faf7|ScalerAudioD3WatchDogProc|med|same as fb37 on P72; SDK D3WatchDogProc
fc30|ScalerAudioGetAudioDetected|med|port 4: PB9 FSM/BUFFER/AWD checks, 5/6: HDMI_SR 0x71CB/0x72CB bits; SDK ScalerAudioGetAudioDetected
e6c1|ScalerAudioD1DigitalDetectProc|med|f4c0 freq detect + PB9_50 AUD_FREQUENY_DET_0 bit5 handling + e958; vendor variant of SDK D1DigitalDetectProc
f53f|ScalerAudioD2DigitalDetectProc|med|f5f6 freq detect + 0x33 timer event + fd99 (P71 FIFO tracking); vendor variant of SDK D2DigitalDetectProc
e8b6|ScalerAudioDVCSetVolumeZCDTimeout|high|VOLUME_STEP_SIZE type, |DVC_GAIN - vol|/step+1, freq from ecc2, writes DVC_ZC_WIN_CTRL (f27d); SDK ScalerAudioDVCSetVolumeZCDTimeout
e9f7|ScalerAudioDVCSetMuteZCDTimeout|high|DB-gain step from DVC_EN[3:0], freq from ecc2, writes DVC_ZC_WIN_CTRL; SDK ScalerAudioDVCSetMuteZCDTimeout
eeb4|ScalerAudioDVCVolumeMute|high|AdjustType, ZCD timeout, read gain, mute: gain 0 and wait DVC_GAIN_DONE bit7 with timeout; SDK ScalerAudioDVCVolumeMute
fa00|ScalerAudioDVCVolumeAdjustType|high|DVC_EN[4:0]/DVC_VA_MSB/LSB per type (dB step 0x0F/1 or volume step 0x10/0x40); SDK ScalerAudioDVCVolumeAdjustType
fc4a|ScalerAudioDVCAdjustVolume|high|DVC_GAIN_MSB[5:0]/LSB then DVC_GAIN_READ_MSB bit6 double buffer; SDK ScalerAudioDVCAdjustVolume
fcdb|ScalerAudioDigitalAdjustVolume|high|e8b6 (ZCD timeout) then DVC AdjustVolume inline; SDK ScalerAudioDigitalAdjustVolume
fcf1|ScalerAudioDigitalVolumeMute|med|stores mute/volume args then calls eeb4; SDK ScalerAudioDigitalVolumeMute
f8e5|SysAudioMuteProc|high|amp mute (0555/055b interface) + volume mute via fcf1, ordering by bMute; SDK SysAudioMuteProc
f1a9|SysAudioPowerProc|high|switch on power action: ->normal fb90, ->off/ps mute+watchdog off+f3e9 ScalerAudioDisable+state; SDK SysAudioPowerProc
fb90|SysAudioInitial|high|feec (ScalerAudioInitial), eb20 (SourceInputSwitch), VcmReady on, DAC state initial(e245|9); SDK SysAudioInitial
f98b|SysAudioDpAudioSecDataResetProc|high|mute, watchdog off, f8ba NormalToDepop, state preparing, then ScalerDpSecDataReset (2040); SDK SysAudioDpAudioSecDataResetProc
ed44|SysAudioHandler|high|ddb2 (analog handler), fe8f (digital handler), audio state machine on e244 bits5:4 (1 preparing, 2 playback); SDK SysAudioHandler
ddb2|SysAudioAnalogAudioHandler|med|DAC state machine (fedc/fe2b/f8ba/f88e/fa25/fad6) + mute/state change; SDK SysAudioAnalogAudioHandler
fe8f|SysAudioDigitalAudioHandler|med|f774 output mute, e6c1/f53f/f352 per-port detect (D3 detect falls through); SDK SysAudioDigitalAudioHandler + ScalerAudioDigitalDetect
fd73|SysAudioChangeAudioState|high|e244 = (e244&0xCF)|(state<<4)|0x40 (state + state-change flag); SDK SysAudioChangeAudioState
feb9|SysAudioGetAudioState|high|returns (e244>>4)&3; SDK SysAudioGetAudioState
fe9a|ScalerAudioDVCGetVolumeMuteStatus|low|returns bit field of e245 (e245>>4); likely mute flag; hint only
d5db|ScalerFlashDetectFlashType|high|loops 0x4A flash table entries, ID check 1/2 via e617, result in e248 (g_ucFlashType, 0xFE=_FLASH_UNDETECT); SDK ScalerCommonNVRam.c
e617|ScalerFlashReadFlashIDCode|high|COMMON_INST_EN 0x46/0x47 op 0x9F, 0x5E/0x5F op 0x90/0xAB, reads READ_PORT0..2; SDK ScalerFlashReadFlashIDCode
f076|ScalerFlashErasePage|high|bank>=XDATA_BANK_START check, detect type if 0xFE, WREN (a7f8), INST_EN 0xB8/0xB9 erase op, WRDis (d966); SDK ScalerFlashErasePage
a7f8|ScalerFlashWREN|med|jump-table dispatch on g_ucFlashType; called with (page, bank) from f076 and d3bd; SDK ScalerFlashWREN (flash-type switch)
d966|ScalerFlashWRDis|med|jump-table dispatch on g_ucFlashType (<0x4A) default dae2; called after write/erase; SDK ScalerFlashWRDis
fd5e|ScalerFlashSetWRSR|high|INST_EN 0x68/0x88 (SST), op 0x01, ISP0=value, start; PORT86 WP pin around it; SDK ScalerFlashSetWRSR
fa49|ScalerFlashSet2ByteWRSR|high|INST_EN 0x70/0x90, op 0x01, ISP0/ISP1; SDK ScalerFlashSet2ByteWRSR
f861|ScalerFlashSet2ByteWRSRonebyone|high|INST_EN 0x68/0x88 op 0x01 then op 0x31; SDK ScalerFlashSet2ByteWRSRonebyone
fcad|ScalerFlashSet2ndWRSR|high|INST_EN 0x68/0x88, op 0x31, ISP0; SDK ScalerFlashSet2ndWRSR
fbfc|ScalerFlashSet3rdWRSR|high|INST_EN 0x68/0x88, op 0x11, ISP0; SDK ScalerFlashSet3rdWRSR
fc16|ScalerFlashSet4thWRSR|high|INST_EN 0x68/0x88, op 0x41, ISP0; SDK ScalerFlashSet4thWRSR
fcc4|ScalerFlashReadSR|high|COMMON_OP_CODE=op, INST_EN=0x43, returns READ_PORT0; SDK ScalerFlashReadSR
fde5|ScalerFlashSetWREN|med|COMMON_OP_CODE=op then INST_EN=0x21 (0x20 set by caller); SDK ScalerFlashSetWREN
da12|ScalerFlashWRProtect|med|SetWRSR (fd5e) with table value then SetWREN(WRDis op) from tFlashInformation, op codes disabled at end; SDK ScalerFlashWRProtect
aa12|ScalerFlashWREN_at25sf321_page|med|ucWRSR 0xE4/E8/EC/F8/A4 by page, ucWRSR1 0x40 = AT25SF321 case 0 of SDK ScalerFlashWREN
d43e|flash_wp_pin_release|med|PORT86_PIN_REG=1 (PCB_FLASH_WRITE_PROTECT disable) before WRSR sequences
d402|flash_cmd_end_wp_pin_assert|med|COMMON_OP_CODE=0xFF, PORT86_PIN_REG=0 (WP asserted) after WRSR sequences
d7a4|UserCommonFlashCalculateCheckSumData|high|bitwise CRC-8 network identical to SDK equations (bTempCRC0..7), result packed by d915; SDK UserCommonNVRamSystem.c
c177|UserCommonFlashSaveItem|high|scan items top-down by id, compare checksum (d7a4) and data, write 16-byte item, verify, move page when full; SDK UserCommonFlashSaveItem
dfef|UserCommonFlashLoadItem|high|scan items top-down by id, checksum check (d7a4), copy data; SDK UserCommonFlashLoadItem
fe09|UserCommonFlashSaveSystemData|med|c177 with item id 2 (SYSTEM_DATA), 13 bytes (StructSystemDataType size) at e1d8
fc63|UserCommonFlashWrite|med|copies bank/addr/len/ptr from dc6c.. into ScalerFlashWrite call; SDK UserCommonFlashWrite
fc7c|UserCommonFlashRead|med|same wrapper for ScalerFlashRead; SDK UserCommonFlashRead
c4df|RTDFlashMoveData|high|erase free page, copy newest valid items (checksum+id dedup), write page info with move count, checksum/version page; SDK RTD2014NVRamOsd.c RTDFlashMoveData
f0e1|RTDFlashGetFreePage|high|start page 0x0B end 0x0C, skips pages in use, uses last page and move count; SDK RTDFlashGetFreePage
edc1|RTDFlashInitialDataPage|high|get free page, erase, move count++, write page info (id, 3-byte count, crc); SDK RTDFlashInitialDataPage
daf9|RTDFlashInitialAddr|high|clear move count/last page, scan pages 0x0B..0x0C (f14b valid check), pick max move count, init missing pages (edc1, e2fa); SDK RTDFlashInitialAddr
f14b|RTDFlashIsPageInfoValid|med|reads 5-byte page info, checksum of 4 bytes via d7a4 vs byte 0; SDK RTDFlashIsPageInfoValid
f205|RTDFlashSearchPageAddr|high|scans items from page end down for first byte != 0xFF, returns item index; SDK RTDFlashSearchPageAddr
e2fa|RTDFlashSaveChecksumVersionCode|high|reads stored version/checksum, 5-way compare (0xFF = erased), writes missing or moves page (c4df); SDK RTDFlashSaveChecksumVersionCode
f90f|RTDFlashLoadChecksumVersioncode|med|two ScalerFlashRead calls at page offsets for checksum and version code; SDK RTDFlashLoadChecksumVersioncode
e76a|RTDFlashStartup|high|daf9 InitialAddr, load checksum/version, compare, restore defaults or load items (dfef); SDK RTDFlashStartup
""".strip().splitlines()
g = """
e248|g_ucFlashType|u8|high|compared with 0xFE (_FLASH_UNDETECT) in ScalerFlashWrite/ErasePage; written by d5db DetectFlashType
e048|g_ucFlashLastPage|u8|high|init 0x0B (_SYSTEM_EEPROM_EMULATION_START_PAGE) in daf9; used by f0e1 GetFreePage
e049|g_pucFlashPageArr|u8|med|page index of page id 0; <<4 is page address high byte in c177/dfef/e2fa
e06e|g_pusFlashAddrArr|u16|med|item count of page id 0 (c177/dfef/f205 index (id*2)+0xE06E)
e070|g_ulFlashMoveCount|u32|high|4-byte clear in daf9, 3-byte count written to page info (edc1, c4df)
e244|g_stAudioInfo|u8|med|audio state bits5:4, state-change bit6, search index low nibble (field order differs from sdk_types StructAudioInfoType); SysAudioHandler ed44
e245|g_stAudioDACInfo|u8|med|DAC state low 3 bits, state-change bit3 (fe2b/fedc/fee4)
e213|g_stAudioD1DigtalInfo|u8|med|low nibble = D1 sampling freq (f4c0)
e215|g_stAudioD2DigtalInfo|u8|med|low nibble = D2 sampling freq (f5f6)
e217|g_stAudioD3DigtalInfo|u8|med|low nibble = D3 sampling freq (f352)
e1d8|g_stSystemData|var:StructSystemDataType|med|fe09 saves 13 bytes from here as flash item 2 = SYSTEM_DATA; StructSystemDataType size 13
""".strip().splitlines()
out=[]
for r in rows:
    a,n,c,e=r.split('|',3)
    out.append('\t'.join(['CODE:'+a,n,'func',e,'[re-agent]',c]))
for r in g:
    a,n,t,c,e=r.split('|',4)
    if not t.startswith('var:'): t='var:'+t
    out.append('\t'.join(['EXTMEM:'+a,n,t,e,'[re-agent]',c]))
# uniqueness
names=[o.split('\t')[1] for o in out]
addrs=[o.split('\t')[0] for o in out]
assert len(set(names))==len(names), [n for n in names if names.count(n)>1]
assert len(set(addrs))==len(addrs)
open('tmp/b3/rows.tsv','w').write('\n'.join(out)+'\n')
import collections
print(collections.Counter(o.split('\t')[5] for o in out), len(out))
