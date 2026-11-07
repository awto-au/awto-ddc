/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2012>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : RL6449_Project.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#if(_PROJECT == _RL6449_PROJECT)

//--------------------------------------------------
// awto switches for SDK code compiled out by scripts/keil2sdcc.py WRAPS (#8)
//--------------------------------------------------
#define _AWTO_DEMO_LOGO                                         _ON     // awto: back on (#46)
#define _AWTO_LOGO_SDK                                          _OFF    // _ON = Realtek logo consts; _OFF = awto mark (fw/sdcc/awto_logo_*.inc, scripts/osd_logo_encode.py)
#define _AWTO_POPUP_ICON                                        _ON     // _ON = icon at the left of the input-info/debug pop-ups, _OFF = blank (#46)
#define _AWTO_POPUP_ICON_AWTO                                   _ON     // _ON = awto mark (fw/sdcc/awto_icon_info.inc, scripts/osd_icon_encode.py), _OFF = SDK info bubble
// Boot-stage + timing diag block (#23): 48 B at 0xF6D0, outside the linker's XDATA range (fw_build.py XRAM end).
// Layout (SDCC little-endian: low byte first): docs/diag-block.md, scripts/rtd_diag.py. Read over debug slave 0x35.
#define _AWTO_DIAG                                              _ON
#define _AWTO_DIAG_SELFTEST                                     _OFF    // _ON = delay self-test before panel power (usDelayXms10/usBusy1ms), costs boot time (#53.6)
#if(_AWTO_DIAG == _ON)
typedef struct
{
    unsigned char ucMagic0;                     // 'A'
    unsigned char ucMagic1;                     // 'D'
    unsigned char ucVersion;                    // 1; 2 = debug slave block read 0x3C (#38)
    unsigned char ucStage;                      // last stage reached (1..8, monotonic)
    unsigned int usStageMs[8];                  // g_usTimerCounter (1 ms) at first entry of stage n
    unsigned int usHeartbeat;                   // main-loop passes
    unsigned int usT2Isr;                       // Timer2 ISR entries
    unsigned int usEx1Isr;                      // EXINT1 (DDC-CI/debug) ISR entries
    unsigned char ucDelay5usN;                  // g_ucDelay5usN_Base seen by the self-test
    unsigned int usDelayXms10;                  // ScalerTimerDelayXms(10), Timer2 counts / 4
    unsigned int usBusy1ms;                     // 200 x ScalerDelay5us(), Timer2 counts / 4
    unsigned char ucRcap2h;                     // RCAP2H at self-test: tells XTAL from M2PLL reload
    unsigned int usReserved[4];                 // was the micro-bench (removed, #53.6); stays 0
    unsigned char ucTestCmd;                    // OSD test command, written over I2C, applied + cleared in main loop (#33)
    unsigned char ucDbgPopup;                   // 1 = next input-info pop-up shows the debug lines (#34), cleared when drawn
    unsigned int usLoopRate;                    // main-loop passes in the last ~1 s (#34)
    unsigned char ucOsdOfsState;                // offsetof(StructOsdInfo, usOsdState): g_stOsdInfo layout moves with _DP_DEBUG_MSG (#37)
    unsigned char ucOsdOfsEvent;                // offsetof(StructOsdInfo, ucOsdEventMsg)
    unsigned char ucOsdOfsKey;                  // offsetof(StructOsdInfo, ucOsdKeyMessage)
    unsigned char ucHold;                       // #28 held test visuals: bit0 logo (cmd 0x24), bit1 debug pop-up (0x26); 0x27 clears
} StAwtoDiag;
typedef char AwtoDiagSizeCheck[(sizeof(StAwtoDiag) == 48) ? 1 : -1];
#ifdef _AWTO_DIAG_DEFINER
volatile __xdata __at(0xF6D0) StAwtoDiag g_stAwtoDiag;
#else
extern volatile __xdata __at(0xF6D0) StAwtoDiag g_stAwtoDiag;
#endif
extern void AwtoDiagInit(void);
extern void AwtoDiagStage(unsigned char ucStage);
extern void AwtoDiagMainPass(void);
extern void AwtoDiagTestCmd(void);
extern void AwtoTestHoldLogoOff(void);
extern void AwtoOsdDebugLines(void);
extern void AwtoOsdOfsInit(void);
#if(_AWTO_DIAG_SELFTEST == _ON)
extern void AwtoDiagSelfTest(void);
#else
#define AwtoDiagSelfTest()
#endif
#define AWTO_DIAG_T2ISR()                                       (g_stAwtoDiag.usT2Isr++)
#define AWTO_DIAG_EX1ISR()                                      (g_stAwtoDiag.usEx1Isr++)
#else
#define AwtoDiagInit()
#define AwtoOsdOfsInit()
#define AwtoDiagStage(n)
#define AwtoDiagMainPass()
#define AwtoDiagTestCmd()
#define AwtoDiagSelfTest()
#define AWTO_DIAG_T2ISR()
#define AWTO_DIAG_EX1ISR()
#endif
// Debug slave 0x35 answers 0x3A / 0x3C in the EXINT1 ISR (#38, docs/diag-block.md); diag version 2 = this is on.
#define _AWTO_DBGISR                                            _ON
#define _AWTO_DBGISR_BLK_MAX                                    24      // max bytes per 0x3C read: IIC data FIFO fill, as the SDK 0xBB reply
// Debug slave 0x35 on the DDC of the active port, not fixed _PCB_DEBUG_DDC (#28): D1 -> DDC1 (DP AUX), D2 -> DDC2, D3 -> DDC3.
// SCL hold/release of the debug protocol follow FF22 (fw/sdcc/awto_dbgport.inc, keil2sdcc SUBS).
#define _AWTO_DBG_FOLLOW                                        _ON
#if(_AWTO_DBG_FOLLOW == _ON)
#define AWTO_DBG_SCL(op)                                        do { BYTE ucAwtoCh = MCU_FF22_IIC_CH_SEL & 0x07; \
    if(ucAwtoCh == 0x03) { MCU_FE66_DDC2_DDC_CONTROL_2 op; } else if(ucAwtoCh == 0x04) { MCU_FE6F_DDC3_DDC_CONTROL_2 op; } \
    else if(ucAwtoCh == 0x02) { MCU_FF2E_DDC1_DDC_CONTROL_2 op; } else if(ucAwtoCh == 0x01) { MCU_FF20_DDC0_DDC_CONTROL_2 op; } } while(0)
#endif
// 4K60 measurement ring (awto-ddc#26): Timer2 ISR samples scaler regs every 20 ms from the first M-domain setup; layout in scripts/meas4k_dump.py.
// Re-arm: write state byte (g_stAwtoMeas+3) = 0 over the debug slave, then change mode.
#define _AWTO_MEAS4K                                            _ON
#if(_AWTO_MEAS4K == _ON)
#define AWTO_MEAS_PERIOD_MS                                     20
#define AWTO_MEAS_WINDOW_MS                                     1000
#define AWTO_MEAS_SAMPLES                                       52      // 1000 / 20 + 1 + 1 spare
#define AWTO_MEAS_EVENTS                                        40
typedef struct
{
    unsigned int usMs;
    unsigned char ucMode;
    unsigned char ucP0_02, ucP0_0C, ucP5_B0, ucP45_B0, ucP5_2B, ucP45_2B;
    unsigned char ucP0_3D, ucP0_3E, ucP0_40, ucP0_41, ucP0_45, ucP1_C4, ucP1_C5, ucP0_28;
} StAwtoMeasRec;                                // 17 B
typedef struct
{
    unsigned int usMs;
    unsigned char ucId;
    unsigned char ucArg;
    unsigned int usVal;
} StAwtoMeasEv;                                 // 6 B
typedef struct
{
    unsigned char ucMagic0;                     // 'M'
    unsigned char ucMagic1;                     // 'K'
    unsigned char ucVersion;                    // 1
    unsigned char ucState;                      // 0 idle (armable), 1 sampling, 2 done
    unsigned char ucArms;
    unsigned char ucNSamp;
    unsigned char ucNEv;
    unsigned char ucSpare;
    unsigned int usStartMs;
    unsigned int usNextMs;
    unsigned int usEndMs;
    __xdata StAwtoMeasRec *pSampWr;
    StAwtoMeasRec stSamp[AWTO_MEAS_SAMPLES];
    StAwtoMeasEv stEv[AWTO_MEAS_EVENTS];
} StAwtoMeas;
extern __xdata StAwtoMeas g_stAwtoMeas;
extern void AwtoMeasInit(void);
extern void AwtoMeasEvent(unsigned char ucId, unsigned char ucArg, unsigned int usVal);
extern void AwtoMeasT2Sample(void);
#define AWTO_MEAS_RD(a)                                         (*((volatile __xdata unsigned char *)(a)))
#define AWTO_MEAS_T2ISR()                                       do { if(g_stAwtoMeas.ucState == 1) { AwtoMeasT2Sample(); } } while(0)
#define AWTO_MEAS_P0_02_0C()                                    (((unsigned int)AWTO_MEAS_RD(0x000C) << 8) | AWTO_MEAS_RD(0x0002))
#else
#define AwtoMeasInit()
#define AwtoMeasEvent(a, b, c)
#define AWTO_MEAS_T2ISR()
#define AWTO_MEAS_P0_02_0C()                                    0
#endif
// Exact input frequencies (#34, #26) from the input active-region count the M-domain set-up took (fw/sdcc/awto_freq.inc);
// pop-ups show 3 decimals from these. The SDK's own 0.1 Hz / 0.1 kHz values and decisions are untouched.
#define _AWTO_FREQ                                              _ON
#if(_AWTO_FREQ == _ON)
#define AWTO_XTAL_HZ                                            14318180UL      // board crystal, 4x NTSC colour burst; SDK _XTAL14318K = 14318 kHz
typedef struct
{
    unsigned long ulCount;                      // g_ulInputActiveRegionBackUp: measure clocks, first to last active pixel
    unsigned long ulMeasHz;                     // measure clock: crystal or M2PLL / P40_07 divider
    unsigned long ulPclkHz;                     // ulMeasHz * (IHtotal * (IVheight - 1 + extra) + IHwidth) / ulCount
    unsigned long ulHFreqHz;                    // ulPclkHz / IHtotal
    unsigned long ulVFreqmHz;                   // ulPclkHz * 1000 / (IHtotal * IVtotal)
    unsigned int usIHTotal;
    unsigned int usIVTotal;
    unsigned int usIHWidth;
    unsigned int usIVHeight;
    unsigned char ucExtraLines;                 // count spans extra lines with V scale-down (SDK fine-tune: 1, F-to-P 2)
    unsigned char ucValid;                      // 1 = fields above are from the current count
} StAwtoFreq;                                   // 30 B, big-endian in -be images
extern __xdata StAwtoFreq g_stAwtoFreq;
extern void AwtoFreqUpdate(void);
#define AwtoFreqInvalidate()                                    (g_stAwtoFreq.ucValid = 0)
#else
#define AwtoFreqUpdate()
#define AwtoFreqInvalidate()
#endif
// Debug port: DDC on the active port speaks the Realtek debug protocol (slave 0x35) instead of DDC/CI (0x37),
// so RTDCustomerTool / our CLI get live register access (#13). DDC/CI (ddcutil) is off while this is _ON.
#define _AWTO_DEBUG_PORT                                        _ON
#if(_AWTO_DEBUG_PORT == _ON)
#define GET_OSD_DDCCI_STATUS()                                  (_OFF)
#endif
#define _AWTO_INFO_POPUP_SEC                                    6       // input-info pop-up on-screen time (SDK: 3)
#define _CHECKSUM                                               0xA2    // awto NVRAM layout id; change = defaults reload (SDK 0x1A)


/////////////
// General //
/////////////

//--------------------------------------------------
// Pcb Option
//--------------------------------------------------
// awto: board = 1 DP + 2 HDMI + eDP panel (Dan, awto-ddc#7). Placeholder until our own PCB header.
#define _PCB_TYPE                                               _RL6449_AWTO_JXC4K  // 216-pin; live pinshare (#7)

//--------------------------------------------------
// Panel Option
//--------------------------------------------------
// awto: Samsung LTM270FL01, eDP HBR2 x4 on TX1 (fw/overlay/Panel/AWTO_LTM270FL01.h, #7)
#define _PANEL_TYPE                                             _AWTO_LTM270FL01
#define _PANEL_POW_SEQ_FAST_MODE                                _ON

//--------------------------------------------------
// Osd Option
//--------------------------------------------------
#define _OSD_TYPE                                               _REALTEK_2014_OSD

#define _OSD_INCLUDE                                            "RTD2014Include.h"
#define _USER_FUNCTION_INCLUDE                                  "RTD2014UserInclude.h"
#define _USER_TIMER_INCLUDE                                     "RTD2014TimerInclude.h"
#define _FACTORY_INCLUDE                                        "RTDFactoryInclude.h"
#define _USER_HWIIC_INCLUDE                                     "RTD2014HWIICInclude.h"

//--------------------------------------------------
// OSD Window & Font Align to DEN Option
//--------------------------------------------------
#define _OSD_POSITION_OFFSET_CORRECTION                         _ON

//--------------------------------------------------
// OSD Position Align Option
//--------------------------------------------------
#define _OSD_POSITION_SELF_ALIGNMENT                            _ON


///////////
// DDCCI //
///////////

//-------------------------------------------------
// DDCCI Option
//-------------------------------------------------
#define _DDCCI_RXBUF_LENGTH                                     16
#define _DDCCI_TXBUF_LENGTH                                     16
#define _DDCCI_TIMEOUT_LIMIT                                    50 // 0~65535ms

#define _CAPABILITIES_STRING_VGA                                "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 0E 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 1E 1F 20 30 3E 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_DVI                                "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_HDMI                               "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_DP                                 "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"


/////////////////////
// Display Setting //
/////////////////////

//-------------------------------------------------
// Embedded Memory Size Option
//-------------------------------------------------
#define _EMBEDDED_MEMORY_SIZE_CONFIG                            _16M_16BIT_DDR2_2PCS
#define _DDR2_MEMORY_CLK_1200M_SUPPORT                          _ON     // vendor fw: DDR PLL 1200000 kHz (bank2 F9B7) + 1200M PHY timings (#26)

//-------------------------------------------------
// OD Option
//-------------------------------------------------
#define _OD_SUPPORT                                             _OFF    // awto: cut (Dan 2026-11-04, #8)

//-------------------------------------------------
// FRC Option
//-------------------------------------------------
// FRC: off by default (#8); K2S_SDCC_EXTRA=-D_AWTO_FRC turns it on (4K60 work, #26)
#ifdef _AWTO_FRC
#define _FRC_SUPPORT                                            _ON
#else
#define _FRC_SUPPORT                                            _OFF
#endif

//-------------------------------------------------
// Display Rotation Option
//-------------------------------------------------
#define _DISPLAY_ROTATION_SUPPORT                               _OFF    // awto: unused on this board (#7)

//--------------------------------------------------
// Aspect Ratio Option
//--------------------------------------------------
#define _ASPECT_RATIO_SUPPORT                                   _ON
#define _ASPECT_ORIGINAL_MODE_SUPPORT                           _ON

//--------------------------------------------------
// Overscan Option
//--------------------------------------------------
#define _OVERSCAN_VGA_SUPPORT                                   _OFF    // awto: unused on this board (#7)
#define _OVERSCAN_DVI_SUPPORT                                   _ON
#define _OVERSCAN_HDMI_SUPPORT                                  _ON
#define _OVERSCAN_DP_SUPPORT                                    _ON

#define _OVERSCAN_H_RATIO                                       30
#define _OVERSCAN_V_RATIO                                       30

//-------------------------------------------------
// Adjust H & V Position Max Range Option
//-------------------------------------------------
#define _MAX_H_POSITION_RANGE                                   100 // Pixel
#define _MAX_V_POSITION_RANGE                                   100 // Line


////////////////////
// Color Function //
////////////////////

//--------------------------------------------------
// Digital Functional Option
//--------------------------------------------------
#define _I_DITHER_SUPPORT                                       _ON
#define _D_DITHER_SUPPORT                                       _ON
#define _GAMMA_FUNCTION                                         _ON
#define _COLOR_FORMAT_CONVERT                                   _ON
#define _RGB_QUANTIZATION_RANGE_SUPPORT                         _ON
#define _YCC_QUANTIZATION_RANGE_SUPPORT                         _ON
#define _ULTRA_VIVID_SUPPORT                                    _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _DCR_SUPPORT                                            _OFF
#define _DCC_FUNCTION                                           _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _DCC_HISTOGRM_INFO                                      _OFF
#define _ICM_SUPPORT                                            _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _ICM_BRI_SUPPORT                                        _OFF
#define _SCM_SUPPORT                                            _OFF
#define _SIX_COLOR_SUPPORT                                      _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _HIGHLIGHT_WINDOW_SUPPORT                               _OFF    // awto: unused on this board (#7)
#define _RINGING_FILTER_SUPPORT                                 _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _SHARPNESS_SUPPORT                                      _OFF    // awto: cut (Dan 2026-11-04, #8)
#define _CONTRAST_SUPPORT                                       _ON
#define _BRIGHTNESS_SUPPORT                                     _ON

//-------------------------------------------------
// Hue and Saturation Option
//-------------------------------------------------
#define _GLOBAL_HUE_SATURATION                                  _OFF    // awto: cut (Dan 2026-11-04, #8)

#define _HUE_MAX                                                230
#define _HUE_MIN                                                30
#define _SATURATION_MAX                                         200
#define _SATURATION_MIN                                         0

//-------------------------------------------------
// IAPS Option
//-------------------------------------------------
#define _IAPS_SUPPORT                                           _OFF


////////////////////////////////////////
// Off-Line Display Color Calibration //
////////////////////////////////////////

//-------------------------------------------------
// PCM (Load Code Table) Option
//-------------------------------------------------
#define _PCM_FUNCTION                                           _OFF

//-------------------------------------------------
// 3D Gamma (Load Code Table) Option
//-------------------------------------------------
#define _RGB_3D_GAMMA                                           _OFF

////////////////////////////////////////
// On-Line Display Color Calibration //
////////////////////////////////////////

//-------------------------------------------------
// OGC and OCC (On-Line Calibration) Option
//-------------------------------------------------
#define _OCC_SUPPORT                                            _OFF
#define _OGC_SUPPORT                                            _OFF
#define _OGC_DICOM_SUPPORT                                      _OFF
#define _TWO_BRI_CALIBRATION_TYPE                               _TWO_BRI_CALIBRATION_NONE

#define _OGC_TOTAL_GAMMA                                        5 // 1/2/3/4/5/6
#define _OGC_TOTAL_CT                                           6
#define _OGC_FLASH_BANK                                         14 // awto: old fw gamma data at bank 14 pages 0-2 (1 MiB flash)

//-------------------------------------------------
// FreesyncII Option
//-------------------------------------------------
#define _FREESYNC_II_FLASH_BANK                                 13 // awto: unused (FreeSync II off); kept inside 1 MiB
#define _FREESYNC_II_FLASH_PAGE                                 0

//-------------------------------------------------
// Uniformity (On-Line Calibration) Option
//-------------------------------------------------
#define _UNIFORMITY_SUPPORT                                     _OFF

#define _UNIFORMITY_FLASH_BANK0                                 29

#define _UNIFORMITY_1ST_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_2ND_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_3RD_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_4TH_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_5TH_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_6TH_TABLE_LEVEL                             _UNIFORMITY_NONE

//-------------------------------------------------
// Dimming Option
//-------------------------------------------------
#define _LOCAL_DIMMING_SUPPORT                                  _OFF
#define _GLOBAL_DIMMING_SUPPORT                                 _OFF

#define _DISPLAY_HDR_VERSION                                    _DISPLAY_HDR_VERSION_1_0

////////////
// Eeprom //
////////////

//-------------------------------------------------
// Eeprom Access Function Option
//-------------------------------------------------
#define _EEPROM_ACCESS_FUNCTION_SUPPORT                         _ON

//-------------------------------------------------
// System Eeprom Start Address for Kernel Data Option
//-------------------------------------------------
#define _EEPROM_KERNEL_START_ADDRESS                            (_EEPROM_PAGE0_BANK0)


///////////
// Flash //
///////////

//-------------------------------------------------
// Flash Clock Option
//-------------------------------------------------
#define _FLASH_CLK_SPEED                                        _FLASH_FAST_SPEED

//-------------------------------------------------
// Flash Access Function Option
//-------------------------------------------------
#define _FLASH_WRITE_FUNCTION_SUPPORT                           _ON  // awto: needed by EEPROM emulation
#define _FLASH_READ_FUNCTION_SUPPORT                            _ON  // awto: needed by EEPROM emulation

#define _FLASH_TYPE_W25X20A_OR_W25X21CL                         _FLASH_W25X20A
#define _FLASH_TYPE_W25X40CL_OR_W25X41CL                        _FLASH_W25X40CL
#define _FLASH_TYPE_GD25Q16C_OR_GD25Q16                         _FLASH_GD25Q16C
#define _FLASH_TYPE_MX25L3206E_OR_MX25L3233F_OR_KH25L3236F      _FLASH_MX25L3233F
#define _FLASH_TYPE_GD25Q40B_OR_GD25Q41B                        _FLASH_GD25Q41B
#define _FLASH_TYPE_W25Q16DV_OR_W25Q16JVSIQ                     _FLASH_W25Q16JVSIQ
#define _FLASH_TYPE_FM25Q08_OR_FM25Q08A                         _FLASH_FM25Q08A
#define _FLASH_TYPE_BY25D40C_OR_BY25D40ASTIG                    _FLASH_BY25D40C
#define _FLASH_TYPE_W25Q32F_OR_W25Q32JVSSIQ                     _FLASH_W25Q32F
#define _FLASH_TYPE_BY25D80ASTIG_OR_BY25Q80BSTIG                _FLASH_BY25D80ASTIG

#define _FLASH_EWSR_FUNCTION_SUPPORT                            _OFF

//-------------------------------------------------
// EEPROM Emulation Option
//-------------------------------------------------
#define _SYSTEM_EEPROM_EMULATION_SUPPORT                        _ON  // awto: no EEPROM (EEIIC pins GPIO); old fw records at bank 15 p11-12

#define _SYSTEM_EEPROM_EMULATION_FLASH_BANK                     15
#define _SYSTEM_EEPROM_EMULATION_START_PAGE                     11
#define _SYSTEM_EEPROM_EMULATION_END_PAGE                       12
#define _START_OF_PAGEID                                        _PAGEID_0
#define _END_OF_PAGEID                                          _PAGEID_0
#define _CHECKSUM_VERSIONCODE_ID                                _PAGEID_0


//////////
// EDID //
//////////

//-------------------------------------------------
// EDID Location Option
//-------------------------------------------------
#define _EDID_ADDRESS_EEPROM                                    (_EEPROM_PAGE7_BANK0)
#define _EDID_ADDRESS_FLASH                                     0
#define _EDID_FLASH_BANK                                        9
#define _EDID_HDR10_AUTO_SWITCH                                 _OFF    // awto: unused on this board (#7)


//////////////
// HDCP Key //
//////////////

//-------------------------------------------------
// HDCP Key Location Option
//-------------------------------------------------
#define _HDCP_1_4_KEY_LOCATION                                  _TABLE_LOCATION_CODE
#define _HDCP_2_2_KEY_LOCATION                                  _TABLE_LOCATION_CODE

//-------------------------------------------------
// For HDCP 1.4 Rx Key (FW Size : 325 Bytes ; Tool Size : 376 Bytes)
//-------------------------------------------------
#define _RX_HDCP_1_4_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE2_BANK1)
#define _RX_HDCP_1_4_KEY_ADDRESS_FLASH                          0
#define _RX_HDCP_1_4_KEY_FLASH_BANK                             8

//-------------------------------------------------
// For HDCP 2.2 Rx Key (FW Size : 1118 Bytes ; Tool Size : 1120 Bytes)
//-------------------------------------------------
#define _RX_HDCP_2_2_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE6_BANK0)
#define _RX_HDCP_2_2_KEY_ADDRESS_FLASH                          0
#define _RX_HDCP_2_2_KEY_FLASH_BANK                             15

//-------------------------------------------------
// For HDCP 1.4 Tx Key (FW Size : 325 Bytes ; Tool Size : 376 Bytes)
//-------------------------------------------------
#define _TX_HDCP_1_4_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE4_BANK0)
#define _TX_HDCP_1_4_KEY_ADDRESS_FLASH                          0x180
#define _TX_HDCP_1_4_KEY_FLASH_BANK                             8

//-------------------------------------------------
// For HDCP 2.2 Tx Key (FW Size : 900 Bytes ; Tool Size : 935 Bytes)
//-------------------------------------------------
#define _TX_HDCP_2_2_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE8_BANK0)
#define _TX_HDCP_2_2_KEY_ADDRESS_FLASH                          0x180
#define _TX_HDCP_2_2_KEY_FLASH_BANK                             15


///////////////////
// System Source //
///////////////////

//-------------------------------------------------
// System Auto Search Style Option
//-------------------------------------------------
#define _SOURCE_AUTO_SEARCH_STYLE                               _SOURCE_POLLING_IN_SEARCH_STATE

//-------------------------------------------------
// System Source Search Time Option
//-------------------------------------------------
#define _SOURCE_DEFAULT_SEARCH_TIME_VGA                         SEC(0.5)
#define _SOURCE_DEFAULT_SEARCH_TIME_HDMI                        SEC(2)
#define _SOURCE_DEFAULT_SEARCH_TIME_DVI                         SEC(2)
#define _SOURCE_DEFAULT_SEARCH_TIME_DP                          SEC(3)
#define _SOURCE_DEFAULT_SEARCH_TIME_TYPE_C                      SEC(4.5)


//////////////////
// System Judge //
//////////////////

//-------------------------------------------------
// System Display Setting Check Time Option
//-------------------------------------------------
#define _WAIT_TIME_TO_ACTIVE_VGA                                SEC(0.05)
#define _WAIT_TIME_TO_ACTIVE_DVI                                SEC(0.1)
#define _WAIT_TIME_TO_ACTIVE_HDMI                               SEC(0.1)
#define _WAIT_TIME_TO_ACTIVE_DP                                 SEC(0.1)

//--------------------------------------------------
// System Support Timing Option
//--------------------------------------------------
#define _OOR_H_FREQ_UPPER_BOUND                                 2200 // Unit in 0.1 kHZ
#define _OOR_H_FREQ_LOWER_BOUND                                 100  // Unit in 0.1 kHZ
#define _OOR_V_FREQ_UPPER_BOUND                                 1500 // Unit in 0.1 HZ
#define _OOR_V_FREQ_LOWER_BOUND                                 230  // Unit in 0.1 HZ
#define _OOR_H_WIDTH_UPPER_BOUND                                4096 // Unit in pixel
#define _OOR_V_HEIGHT_LOWER_BOUND                               240  // Unit in line

#define _FAIL_SAVE_H_FREQ_UPPER_BOUND                           2200 // Unit in 0.1 kHZ
#define _FAIL_SAVE_H_FREQ_LOWER_BOUND                           110  // Unit in 0.1 kHZ
#define _FAIL_SAVE_V_FREQ_UPPER_BOUND                           1500 // Unit in 0.1 HZ
#define _FAIL_SAVE_V_FREQ_LOWER_BOUND                           230  // Unit in 0.1 HZ

#define _INPUTCLOCK_RANG_VGA                                    2100 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_DVI                                    6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_HDMI                                   6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_DP                                     6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_USBC                                   6000 // Unit in 0.1 MHz


/////////
// VGA //
/////////

//--------------------------------------------------
// VGA YPBPR Option
//--------------------------------------------------
#define _YPBPR_SUPPORT                                          _OFF    // awto: unused on this board (#7)
#define _SOG_SUPPORT                                            _OFF    // awto: unused on this board (#7)
#define _VGA_COMPOSITE_SUPPORT                                  _OFF    // awto: no VGA port (A0 none); demo default was _ON

//--------------------------------------------------
// VGA Mode Search condition reference by picture width Option
//--------------------------------------------------
#define _MODE_SEARCH_BY_ACTIVE_MEASURE_SUPPORT                  _OFF

//--------------------------------------------------
// VGA Auto Adjust Clock Setup Option
//--------------------------------------------------
#define _AUTO_CLOCK_STEP                                        2  // 1 or 2
#define _AUTO_CLOCK_RANGE                                       95 // Set Clock Non-adjusting Range (%) by the active region
#define _AUTO_TOLERANCE_PIXEL                                   2  // Definitions Of tolerance pixel for Auto Clock
#define _AUTO_CLOCK_SAVE_VALUE_OPTION                           _CLOCK_SAVE_PERCENT_VALUE

//--------------------------------------------------
// VGA Gain & Offset Defualt Option
//--------------------------------------------------
#define _ADC_RGB_DEFAULT_RED_GAIN                               128
#define _ADC_RGB_DEFAULT_GREEN_GAIN                             128
#define _ADC_RGB_DEFAULT_BLUE_GAIN                              128
#define _ADC_RGB_DEFAULT_RED_OFFSET                             128
#define _ADC_RGB_DEFAULT_GREEN_OFFSET                           128
#define _ADC_RGB_DEFAULT_BLUE_OFFSET                            128

#define _ADC_YPBPR_DEFAULT_Y_GAIN                               159
#define _ADC_YPBPR_DEFAULT_PB_GAIN                              154
#define _ADC_YPBPR_DEFAULT_PR_GAIN                              154
#define _ADC_YPBPR_DEFAULT_Y_OFFSET                             112
#define _ADC_YPBPR_DEFAULT_PB_OFFSET                            128
#define _ADC_YPBPR_DEFAULT_PR_OFFSET                            128

//--------------------------------------------------
// VGA Self-Calibration Option
//--------------------------------------------------
#define _ADC_SELF_CALIBRATION                                   _OFF    // awto: unused on this board (#7)

#define _CALIBRATION_R_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_G_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_B_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_R_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source
#define _CALIBRATION_G_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source
#define _CALIBRATION_B_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source

//--------------------------------------------------
// VGA YPBPR Auto Color Method Option
//--------------------------------------------------
#define _YPBPR_AUTO_METHOD                                      _YPBPR_AUTO_BY_SOURCE

#define _AUTO_PB_GAIN_BIAS                                      (5)
#define _AUTO_PR_GAIN_BIAS                                      (5)
#define _AUTO_Y_GAIN_BIAS                                       (0)
#define _AUTO_PB_OFFSET_BIAS                                    (-8)
#define _AUTO_PR_OFFSET_BIAS                                    (-8)
#define _AUTO_Y_OFFSET_BIAS                                     (-16)

//--------------------------------------------------
// VGA Digital Filter Option
//--------------------------------------------------
#define _DIG_FILTER_NSMEAR_ENABLE                               _ENABLE
#define _DIG_FILTER_PSMEAR_ENABLE                               _ENABLE
#define _DIG_FILTER_NRING_ENABLE                                _ENABLE
#define _DIG_FILTER_PRING_ENABLE                                _ENABLE
#define _DIG_FILTER_EXTENSION_ENABLE                            _ENABLE
#define _DIG_FILTER_ENHANCE_PHASE_ENABLE                        _ENABLE


////////////////
// DVI & HDMI //
////////////////

//--------------------------------------------------
// DVI & HDMI Option
//--------------------------------------------------
#define _DVI_DE_ONLY_SUPPORT                                    _OFF    // awto: unused on this board (#7)
#define _HDMI_FROM_DVI_CONNECT                                  _ON
#define _HDMI_FREESYNC_SUPPORT                                  _OFF
#define _HDMI_HDR10_SUPPORT                                     _OFF
#define _HDMI_FREESYNC_II_SUPPORT                               _OFF
#define _TMDS_HDCP_2_2_SUPPORT                                  _OFF    // awto: unused on this board (#7)

//--------------------------------------------------
// HDMI CTS Option
//--------------------------------------------------
#define _TMDS_HDCP_FEATURE                                      _HDCP_FEATURE_BY_INPUT
#define _TMDS_Z0_POWER_SAVING_OPTION                            _ALL_CHANNEL_CONNECTED_FOR_CTS


////////
// DP //
////////

//-------------------------------------------------
// DP Capability Option
//-------------------------------------------------
#define _DP_MST_SUPPORT                                         _OFF    // awto: no DP-out/daisy chain (demo _ON; ~0.9 KB XDATA)
#define _DP_TX_SUPPORT                                          _OFF    // awto: DP-out port only; eDP panel uses ScalerDisplayDPTx (independent)
#define _DP_FREESYNC_SUPPORT                                    _OFF
#define _DP_FREESYNC_II_SUPPORT                                 _OFF
#define _DP_HDR10_SUPPORT                                       _OFF
#define _DP_HDCP_2_2_SUPPORT                                    _OFF    // awto: unused on this board (#7)


/////////
// MHL //
/////////

//--------------------------------------------------
// MHL2.x Option
//--------------------------------------------------
#define _MHL_CBUS_CTS_MODE                                      _OFF
#define _MHL2_UCP_SUPPORT                                       _OFF
#define _MHL2_AUD_CHANNEL                                       _MHL_AUD_2CH
#define _MHL2_ADOPTER_ID                                        0x0000
#define _MHL2_DEVICE_ID                                         0x0000
#define _MHL2_PP_MODE_SUPPORT                                   _OFF    // awto: unused on this board (#7)


///////////
// Audio //
///////////

//-------------------------------------------------
// Audio Option
//-------------------------------------------------
#define _AUDIO_SUPPORT                                          _OFF // awto: no audio jacks (Dan, 2026-11-04)

//-------------------------------------------------
// Audio DAC Option
//-------------------------------------------------
#define _EMBEDDED_DAC_SUPPORT                                   _OFF

//-------------------------------------------------
// Audio Line In Option
//-------------------------------------------------
#define _LINE_IN_SUPPORT                                        _OFF

#define _LINE_IN_DAC_AOUT_GAIN_DB                               _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _LINE_IN_DAC_HPOUT_GAIN_DB                              _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _LINE_IN_BOOST_GAIN_DB                                  0x17                        // 0dB, 1.5dB for each step, Max Gain: 0x3F(30dB)
#define _LINE_IN_VOLUME_MAX                                     0x3FFF                      // MAX: 0x3FFF
#define _LINE_IN_VOLUME_MIN                                     0x0000

//-------------------------------------------------
// Audio Digital Option
//-------------------------------------------------
#define _DIGITAL_DAC_AOUT_GAIN_DB                               _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _DIGITAL_DAC_HPOUT_GAIN_DB                              _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _DIGITAL_VOLUME_MAX                                     0x3FFF                      // MAX: 0x3FFF
#define _DIGITAL_VOLUME_MIN                                     0x0000

//-------------------------------------------------
// Audio PS Option
//-------------------------------------------------
#define _SLEEP_AUDIO_SUPPORT                                    _OFF

#define _PS_AUDIO_INPUT                                         _PS_AUDIO_LINE_IN


///////////////////
// Misc Function //
///////////////////

//-------------------------------------------------
// Instant Timer Events Option
//-------------------------------------------------
#define _INSTANT_TIMER_EVENT_0                                  _ON
#define _INSTANT_TIMER_EVENT_1                                  _OFF

//--------------------------------------------------
// IRDA Option
//--------------------------------------------------
#define _IR_SUPPORT                                             _IR_OFF

#endif // End of #if(_PROJECT == _RL6410_PROJECT)

