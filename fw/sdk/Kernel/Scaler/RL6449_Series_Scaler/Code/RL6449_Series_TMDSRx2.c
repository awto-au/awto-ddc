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
// ID Code      : RL6449_Series_TMDSRx2.c No.0000 (shared Rx2/Rx3 body, port = d_isr_g_ucTMDSRxPort; Rx3 wrappers: RL6449_Series_TMDSRx3.c)
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RL6449_SERIES_TMDSRX2__
#define RX_SHARE_BODY

#include "ScalerFunctionInclude.h"
#include "RL6449_Series_TMDSRxCheck.h"

#if(_D2_TMDS_SUPPORT == _ON)

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************
//--------------------------------------------------
// Definitions of Measure Clk Source
//--------------------------------------------------
#define _CLK_SOURCE_RED                         0
#define _CLK_SOURCE_BLUE                        1
#define _CLK_SOURCE_GREEN                       2
#define _CLK_SOURCE_TMDS                        3

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// CODE TABLES
//****************************************************************************


//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
volatile BYTE __data d_isr_g_ucTMDSRxPort;
StructTMDSCtrlInfo __data d_g_stTMDSRx2CtrlInfo;  // awto: IRAM direct, hot variable (#335)
volatile bit d_g_bTMDSRx2HDMI2RREnable = _FALSE;
volatile bit d_isr_g_bTMDSRx2HDMI2HighSpeedMode = _FALSE;
volatile bit d_isr_g_bTMDSRx2TMDSPhySet = _FALSE;
volatile bit d_isr_g_bTMDSRx2TMDSDdcDetected = _FALSE;
volatile WORD isr_g_usTMDSRxClkCount[2];
volatile WORD isr_g_usTMDSRxPhyCount[2];
volatile WORD isr_g_usTMDSRxPhyClk[2];
volatile BYTE isr_g_ucTMDSRxPhyPend[2];

volatile BYTE g_pucTMDSRxLEMax[2][3];
volatile BYTE g_pucTMDSRxLEMin[2][3];
BYTE g_pucTMDSRxTap0Min[2][3];
BYTE g_pucTMDSRxTap0Max[2][3];
BYTE g_ucTMDSRxTap0Init[2];
BYTE g_pucTMDSRxTap1Max[2][3];
volatile BYTE isr_g_ucTMDSRxClkIRQ[2];
BYTE g_ucTMDSRxZ0Status[2];
BYTE g_ucTMDSRxSlaveAddr[2];

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
BYTE g_ucTMDSRx2ClkMode = _TMDS_24BIT_PHY_SETTING;
#endif

#if((_TMDS_HDCP_2_2_SUPPORT == _ON) && ((_D2_INPUT_PORT_TYPE == _D2_HDMI_PORT) || (_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)))
BYTE g_pucTmdsRx2Caps[3];
#endif

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void ScalerTMDSRxInitial(void);
void ScalerTMDSRxInterruptInitial(void);
void ScalerTMDSRxSetDFEInitial_EXINT0(void);
void ScalerTMDSRxFLDBandFineTune_EXINT0(void);
void ScalerTMDSRxSetPhy_EXINT0(void);
void ScalerTMDSRxPhySetDeferred(void);
void ScalerTMDSRxIntHandler_EXINT0(void);
bit ScalerTMDSRxCheckCDRStable(WORD usClkCount);
BYTE ScalerTMDSRxCheckCDRStable_EXINT0(WORD usClkCount);
WORD ScalerTMDSRxMeasureClk(BYTE ucMeasureClk);
WORD ScalerTMDSRxMeasureClk_EXINT0(BYTE ucMeasureClk);
void ScalerTMDSRxSetPorchColor(EnumColorSpace enumColorFormat);

#if(_D2_HDMI_SUPPORT == _ON)

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
bit ScalerTMDSRxHdmiSetDeepColorPll(WORD usTMDSClkCount, BYTE ucColorDepth);
#endif // End of #if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)

void ScalerTMDSRxHdmiPacketDetect(bit bWait);
void ScalerTMDSRxHdmiAVMuteProc(void);
void ScalerTMDSRxHdmiWatchDog(BYTE ucWDType, bit bEnable);

#endif

void ScalerTMDSRxPowerSavingProc(void);
void ScalerTMDSRxFreqDetectDisable(void);

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
BYTE ScalerTMDSRxTMDSScanInputPort(BYTE ucInputType);
BYTE ScalerTMDSRxFormatDetect(void);
bit ScalerTMDSRxHdcpEnabled(void);
#endif // End of #if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
bit ScalerTMDSRxCheckDataDFE(void);

bit ScalerTMDSRxTMDSStableDetect(BYTE ucSourceType);
void ScalerTMDSRxHotPlugEvent(void);
void ScalerTMDSRxSwitchSlaveAddr(void);
void ScalerTMDSRxBeforeHotPlugEventProc(void);
void ScalerTMDSRxAfterHotPlugEventProc(void);
void ScalerTMDSRxHdcp1p4AksvClear(void);

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : Register access of the port pages (P71/P7B/P76/P2D, +0x100 for D3: RX_CHK_REG); pinned to common (register-only, ISR-safe)
// Input Value  : usAddr = D2 address
// Output Value : value
//--------------------------------------------------
BYTE RxRegGetByte(WORD usAddr)
{
    return *((volatile BYTE xdata *)RXA(usAddr));
}

BYTE RxRegGetBit(WORD usAddr, BYTE ucAnd)
{
    return (*((volatile BYTE xdata *)RXA(usAddr)) & ucAnd);
}

void RxRegSetByte(WORD usAddr, BYTE ucValue)
{
    *((volatile BYTE xdata *)RXA(usAddr)) = ucValue;
}

void RxRegSetBit(WORD usAddr, BYTE ucAnd, BYTE ucOr)
{
    volatile BYTE xdata *pucReg = (volatile BYTE xdata *)RXA(usAddr);

    *pucReg = (*pucReg & ucAnd) | ucOr;
}

//****************************************************************************
//--------------------------------------------------
// Description  : Initialize TMDS setting for search
// Input Value  : Current Search Port
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxInitial(void)
{
    // Disable TMDS output
    RxSetBit(P71_A6_TMDS_OUTCTL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

    // Set HS Width(DE only) and HDCP Reference VS
    RxSetBit(P71_AB_TMDS_ACC2, ~(_BIT7 | _BIT6), 0x00);

    // Set TMDS Hsync/Vsync Polarity as Input Raw Polarity
    RxSetBit(P71_AF_TMDS_WDC, ~(_BIT3 | _BIT2), 0x00);

    // Disable C9/CA Port Auto-Inc
    RxSetBit(P71_C8_HDMI_APC, ~_BIT0, 0x00);

#if(_D2_HDMI_SUPPORT == _ON)

    ScalerTMDSRxHdmiWatchDog((_HDMI_AVI_INFO_VARIATION_WD | _HDMI_AV_MUTE_WD), _DISABLE);

    // Deep Color Mode clock and detection auto
    RxSetBit(P71_B8_TMDS_DPC1, ~(_BIT3 | _BIT2), _BIT2);

    // Enable BCH Detection
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_02_PORT_PAGE71_HDMI_BCHCR, ~(_BIT6 | _BIT3 | _BIT2 | _BIT1), (_BIT6 | _BIT3 | _BIT2 | _BIT1));

    // DVI mode don't disable Audio Clk
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT5), _BIT5);

    // Set Video Watch Dog New Mode
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_32_PORT_PAGE71_HDMI_WDCR1, ~_BIT5, _BIT5);

    // Specify Packet Detect Type
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_43_PORT_PAGE71_HDMI_PTRSV0, _HDMI_AVI_INFO_TYPE);
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_44_PORT_PAGE71_HDMI_PTRSV1, _HDMI_GENERAL_CONTROL_TYPE);

#if((_HDMI_FREESYNC_SUPPORT == _ON) || (_HDMI_FREESYNC_II_SUPPORT == _ON))
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_A4_PORT_PAGE71_HDMI_PTRSV_2, _SPD_INFO_TYPE);
#endif

#if(_HDMI_HDR10_SUPPORT == _ON)
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_A5_PORT_PAGE71_HDMI_PTRSV_3, _HDR_INFO_TYPE);
#endif

    // Packet Variation Detect Disable
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_45_PORT_PAGE71_HDMI_PVGCR0, 0x00);
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_46_PORT_PAGE71_HDMI_PVGCR1, 0x00);
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_47_PORT_PAGE71_HDMI_PVGCR2, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_A9_PORT_PAGE71_HDMI_PVSR_4, ~(_BIT7 | _BIT6 | _BIT5), 0x00);
    ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_AA_PORT_PAGE71_HDMI_PVGCR3, 0x00);
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_AB_PORT_PAGE71_HDMI_PVGCR4, ~(_BIT7 | _BIT6 | _BIT5), 0x00);

#if(_D2_HDMI_2_0_SUPPORT == _ON)

    if(RxGetBit(P71_E6_HDMI_FREQDET_CTRL, _BIT1) == 0x00)
    {
        // Disable HDMI 2.0 SCDC Function
#if(_AWTO_SCDC_KEEP == _OFF)
        RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, 0x00);
#endif

        RXSEL((CLR_TMDS_RX2_HIGH_SPEED_MODE()), (CLR_TMDS_RX3_HIGH_SPEED_MODE()));
    }

    // Disable SCDC Scrambling Status
    ScalerSetDataPortBit(RXA(P71_39_HDMI_CTRL_39), _P71_3A_PT_21_PORT_PAGE71_HDMI_SCDC_21, ~_BIT0, 0x00);

    // Set Scrambling detection SSCP Number = 8, Enable HW Auto Detect Scrambling Control Symbol
    RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT5 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT2 | _BIT1 | _BIT0));

    // Set SCDC Port not auto increase
    RxSetBit(P71_38_HDMI_CTRL_38, ~(_BIT4 | _BIT0), _BIT4);

    // Disable Ignore Source Transimit Read Request Enable
    RxSetBit(P71_1C_HDMI_CTRL_1C, ~_BIT2, 0x00);

    // Set Read Request 1ms reference clock to XTAL
    RxSetBit(P71_1A_HDMI_CTRL_1A, ~_BIT3, 0x00);

    // Set time interval form bus free to Read Request(4.7us~500us)
    RxSetBit(P71_1B_HDMI_CTRL_1B, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT0));

    // Enable HDMI 2.0 Function
    RxSetBit(P71_00_HDMI_CTRL_00, ~_BIT0, _BIT0);

    // Enable HDMI 2.0 SCDC Module
    RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, _BIT7);

#else

    // Disable HDMI 2.0 Function
    RxSetBit(P71_00_HDMI_CTRL_00, ~_BIT0, 0x00);

    // Disable HDMI 2.0 SCDC Function
    RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, 0x00);

#endif

#endif // End of #if(_D2_HDMI_SUPPORT == _ON)

    // Set HDCP DDC Channel
    RxSetBit(P71_C2_HDCP_PCR, ~(_BIT2 | _BIT1), 0x00);

    // Set HDCP DDC Debounce, TMDS Function
    RxSetBit(P71_AC_TMDS_Z0CC2, ~(_BIT7 | _BIT6 | _BIT5), (_BIT7 | _BIT6 | _BIT5));

#if(_AWTO_HDCP == _ON)
    // Set D2 Port HDCP Address is 0x74
    ScalerSetDataPortBit(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C2_PORT_PAGE71_HDCP_SLAVE_ADD, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x3A);
#else
    // awto: HDCP off (#44): HDCP slave on the SDK's HPD-low parking address, DDC 0x74 unanswered = no HDCP receiver
    ScalerTMDSRxSwitchSlaveAddr();
#endif

    // Set HDCP Feature
#if(_D2_HDMI_SUPPORT == _ON)

#if(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_1_0)
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x81);
#elif(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_1_1)
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x83);
#else
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x81);
#endif

#else // Else of #if(_D2_HDMI_SUPPORT == _ON)

#if(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_1_0)
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x01);
#elif(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_1_1)
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x03);
#else
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, 0x01);
#endif

#endif // End of #if(_D2_HDMI_SUPPORT == _ON)

    // Enable New Advance Cipher Mode
    RxSetBit(P71_C0_HDCP_CR, ~_BIT7, _BIT7);

    // Disable HDMI MAC Global Power Down
    RxSetBit(P71_AD_TMDS_CPS, ~_BIT1, 0x00);

    // Enable MAC Input
    RxSetBit(P71_A7_TMDS_PWDCTL, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Set MAC Signal Swap
    RxSetBit(P71_A7_TMDS_PWDCTL, ~(_BIT6 | _BIT5), ((_D2_TMDS_BR_SWAP << 6) | (_D2_TMDS_PN_SWAP << 5)));

    // Auto switch to DVI when no signal
    RxSetBit(P71_AD_TMDS_CPS, ~_BIT2, _BIT2);

    // Detect TMDS Format by Data Island Packet Preamble & Guard Band
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT4 | _BIT1), _BIT1);

    // Enable TMDS MAC Error Correction
    RxSetBit(P71_B7_TMDS_UDC2, ~(_BIT7 | _BIT6 | _BIT5), (_BIT6 | _BIT5));

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        // Enable MHL Mac and Set MHL MAC Signal Swap
        RxSetBit(P76_A0_MHL_CTRL_00, ~(_BIT5 | _BIT0), ((_D2_TMDS_PN_SWAP << 5) | _BIT0));

        // Enable New Algorithm for Packed Pixel Mode
        RxSetBit(P76_A1_MHL_CTRL_01, ~_BIT7, _BIT7);

        // Guard Band reference enable for __data remapping
        RxSetBit(P76_B2_MHL_CTRL_12, ~_BIT7, _BIT7);

        // Set 24Bit Mode Threshold
        RxSetByte(P76_AA_MHL_CTRL_0A, 0x00);
        RxSetByte(P76_AB_MHL_CTRL_0B, 0x09);

        // Set PP Mode Threshold
        RxSetByte(P76_AC_MHL_CTRL_0C, 0x00);
        RxSetByte(P76_AD_MHL_CTRL_0D, 0x09);

        // Set Detection Period
        RxSetByte(P76_A8_MHL_CTRL_08, 0x69);
        RxSetByte(P76_A9_MHL_CTRL_09, 0x78);

        // Set Detection by Video Leading and Detection Period by Xtal
        RxSetBit(P76_A7_MHL_CTRL_07, ~(_BIT4 | _BIT3 | _BIT2 | _BIT0), _BIT2);
    }
    else
#endif
    {
        // Disable MHL Mac and Revert CDR Data Polarity
        RxSetBit(P76_A0_MHL_CTRL_00, ~(_BIT5 | _BIT0), 0x00);

        // Guard Band reference disable for __data remapping
        RxSetBit(P76_B2_MHL_CTRL_12, ~_BIT7, 0x00);
    }
}
void ScalerTMDSRx2Initial(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxInitial();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : Initialize TMDS Interrupt Required Settings
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxInterruptInitial(void)
{
    // Enable INT Clock Check
    isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

    if(RxGetBit(P71_E6_HDMI_FREQDET_CTRL, _BIT1) == 0x00)
    {
        RXSEL((CLR_TMDS_RX2_PHY_SET()), (CLR_TMDS_RX3_PHY_SET()));
    }

    // Enable Rx_En for Clk pair Z0
    RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);

    // Choose Measure Clk to TMDS Clk
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT7 | _BIT5 | _BIT4), 0x00);

    // Set Freq. Reference Counter = 2000
    RxSetBit(P71_F6_HDMI_FREQDET_BOUND_H, ~(_BIT1 | _BIT0), _BIT0);

    // Set Online Measure Input Clock Divider = /2 (No Matter if Input Clock >300Mhz or <=300Mhz)
    RxSetBit(P71_E7_HDMI_FREQDET_OFFSET, ~_BIT6, _BIT6);

    // Settings for IRQ set PHY
    // Consider using table to fill all required initial settings
    // Set pre-set threshold (225MHz * 0.01 / 26.8KHz = 0x54)

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        // Set TMDS Offset = 1/32
        RxSetBit(P71_E7_HDMI_FREQDET_OFFSET, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

        // Set Upper Bound
        RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));
        RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));
    }
    else
#endif
    {
        // Set TMDS Offset = 1/32
        RxSetBit(P71_E7_HDMI_FREQDET_OFFSET, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

        // Set Upper Bound
        RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
        RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
    }

    // Set Lower Bound
    RxSetByte(P71_EA_HDMI_FREQDET_LOWER_M, HIBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));
    RxSetByte(P71_EB_HDMI_FREQDET_LOWER_L, LOBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));

    // Set Stable Time (0x3F = about 5ms)
    RxSetByte(P71_EC_HDMI_FREQDET_STABLE, 0x3F);

    // Disable Freq. Unstable IRQ
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00);

    // Enable Freq. Stable IRQ
    RxSetBit(P71_EF_HDMI_ERROR_TH, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

    // Clear IRQ Pending Flag
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_60_PORT_PAGE71_HDMI_INTCR, ~_BIT7, _BIT7);

    // Internal IRQ Enable (Global)
    ScalerGlobalIRQControl(_ENABLE);

    EX0 = 1;

    // Start Freq. Detection
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, _BIT7);
}
void ScalerTMDSRx2InterruptInitial(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxInterruptInitial();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS DFE Initial Setting (EXINT0 Only)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxSetDFEInitial_EXINT0(void)
{
    WORD usPixClk = isr_g_usInputPixelClk;   // one read: EX0 is masked / we are in EXINT0, nothing else writes it here

    // [6] Enable Timer Control DFE Loop
    // [5:4] Reduce Gain to 1/4
    // [3] Disable Running Length Detection
    // [2] bypass Blank out Case-3 Symbol
    RxSetBit(P7B_A0_L0_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    RxSetBit(P7B_B0_L1_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    RxSetBit(P7B_C0_L2_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));

    if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
    {
        if(usPixClk <= 1000)
        {
            // [7:6] adapt_mode[1:0] = 2'b10 --> Amplitude-based Adaptation with Independent LE Loop
            RxSetBit(P7B_E0_MODE_TIMER, ~(_BIT7 | _BIT6), _BIT7);
        }
        else
        {
            // [7:6] adapt_mode[1:0] = 2'b11 --> Amplitude-based Adaptation without Independent LE Loop
            RxSetBit(P7B_E0_MODE_TIMER, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));
        }
    }
    else  // ACDR
    {
        // [7:6] adapt_mode[1:0] = 2'b11 --> Amplitude-based Adaptation without Independent LE Loop
        RxSetBit(P7B_E0_MODE_TIMER, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));
    }

    // [5] edge_det_mode = 1 --> Edge Lag Data
    // [4] transition_only = 1 --> Only Transition Bit is Effective
    // [3] le_auto_reload = 0 --> Disable Auto-reload LE Coefficient
    // [2:0] tap1_delay[2:0] = 3'b010 --> Tap1+LE Delay 2us after Tap0
    RxSetBit(P7B_E0_MODE_TIMER, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT1));

    // Set DFE Delay Time
    // Turn On LE/Tap1~6 Simultaneously
    RxSetByte(P7B_E1_TIMER, 0x01);

    // Tap0_Gain = 1/256, Tap1_Gain = 1/512
    RxSetBit(P7B_E2_GAIN_1, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT2));

    // Tap2_Gain = 1/512; Tap3_Gain = 1/512
    RxSetBit(P7B_E3_GAIN_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT2));

    // Tap4_Gain = 1/512; Servo_Gain = 1/256
    RxSetBit(P7B_E4_GAIN_3, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT3));

    // LE_Gain1 = 1/256, LE_Gain2 = 0
    RxSetBit(P7B_E5_GAIN_4, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT4 | _BIT3));
    RxSetBit(P7B_FA_GAIN_PREC, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1));

    // Tap0 = 0~21
    // Vth_Threshold = 1
    RxSetByte(P7B_E6_LIMIT_1, 0x35);

    if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
    {
        // LE = 0~24
        if(usPixClk <= 1000)
        {
            // Tap1 = 0~31 in Mode2
            RxSetBit(P7B_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
        }
        else
        {
            // Tap1 = 0~55 in Mode3
            RxSetBit(P7B_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT2 | _BIT1 | _BIT0));
        }
    }
    else   // ACDR
    {
        // Tap1 = 0~55 in Mode3
        RxSetBit(P7B_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT2 | _BIT1 | _BIT0));
    }

    // Tap2 Max is 10, Min is -6
    RxSetBit(P7B_E8_LIMIT_3, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT6 | _BIT4));
    RxSetBit(P7B_E8_LIMIT_3, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);
    RxSetBit(P7B_E9_LIMIT_4, ~(_BIT7 | _BIT6), _BIT7);

    // Tap3 Max is 0, Min is -3
    RxSetBit(P7B_E9_LIMIT_4, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_EA_LIMIT_5, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT4 | _BIT3));

    // Tap4 Max is 0, Min is -3
    RxSetBit(P7B_EA_LIMIT_5, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_EB_LIMIT_6, ~(_BIT7 | _BIT6), 0x00);
    RxSetBit(P7B_EB_LIMIT_6, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Tap0_Threshold = 10
    RxSetBit(P7B_EF_RESET_1, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT5));

    // Vth_max = 6
    // Vth_min = 0
    RxSetByte(P7B_F9_LIMIT_10, 0x60);

    // Set Vth/Tap Divider
    // Servo_Divider = 40
    // Vth_Divider = 15
    // Tap_Divider = 10
    RxSetByte(P7B_EC_LOOP_DIV_1, 0xA3);
    RxSetByte(P7B_ED_LOOP_DIV_2, 0xCA);

    // [5] servo_notrans = 1'b1 --> Transition Bits are not Effective in Servo
    // [4] tap0_notrans = 1'b1 --> Transition Bits are not Effective in Tap0
    RxSetBit(P7B_F8_GRAY_DEC_2, ~(_BIT5 | _BIT4), (_BIT5 | _BIT4));

    // [0] tap0_trans = 1'b0 --> Nontransition Bits are Effective in Tap0
    RxSetBit(P7B_E3_GAIN_2, ~_BIT0, 0x00);

    // over 3.4Gbps, __data has scramble, use Run length = 4
    if(usPixClk >= 3400)
    {
        // [1:0] trans_rlength = 2'b10 --> Tap0 Run Length = 4
        RxSetBit(P7B_E4_GAIN_3, ~(_BIT1 | _BIT0), _BIT1);
    }
    else
    {
        // [1:0] trans_rlength = 2'b00 --> Tap0 Run Length = 2
        RxSetBit(P7B_E4_GAIN_3, ~(_BIT1 | _BIT0), 0x00);
    }

    // [1] tap1_trans = 1'b1 --> Nontransition Bits are not Effective in LE/Tap1
    RxSetBit(P7B_E3_GAIN_2, ~_BIT1, _BIT1);

    // [1] De_inverse = 1'b0 --> Adapation Only for Blanking Area (Transition Maximum)
    // [0] De_brank_en = 1'b0 --> Disable Blank Function of gdi_de
    RxSetBit(P7B_AF_L0_GDI_DE, ~(_BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_BF_L1_GDI_DE, ~(_BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_CF_L2_GDI_DE, ~(_BIT1 | _BIT0), 0x00);


    /////////////////////////
    // DFE Code Initialize //
    /////////////////////////

    // Initial DFE Code
    if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
    {
        if(usPixClk <= 375)
        {
            // LE Max = 24, Initial = 4
            RxSetByte(P7B_A2_L0_LIMIT_INIT, 0x84);
            RxSetByte(P7B_B2_L1_LIMIT_INIT, 0x84);
            RxSetByte(P7B_C2_L2_LIMIT_INIT, 0x84);

            // Tap1 Initial Value = 0 for Mode1 DFE
            RxSetByte(P7B_A5_L0_INIT_3, 0x00);
            RxSetByte(P7B_B5_L1_INIT_3, 0x00);
            RxSetByte(P7B_C5_L2_INIT_3, 0x00);
        }
        else if(usPixClk <= 700)
        {
            // LE Max = 24, Initial = 6
            RxSetByte(P7B_A2_L0_LIMIT_INIT, 0x86);
            RxSetByte(P7B_B2_L1_LIMIT_INIT, 0x86);
            RxSetByte(P7B_C2_L2_LIMIT_INIT, 0x86);

            // Tap1 Initial Value = 0 for Mode1 DFE
            RxSetByte(P7B_A5_L0_INIT_3, 0x00);
            RxSetByte(P7B_B5_L1_INIT_3, 0x00);
            RxSetByte(P7B_C5_L2_INIT_3, 0x00);
        }
        else if(usPixClk <= 1000)
        {
            // LE Max = 24, Initial = 10
            RxSetByte(P7B_A2_L0_LIMIT_INIT, 0x8A);
            RxSetByte(P7B_B2_L1_LIMIT_INIT, 0x8A);
            RxSetByte(P7B_C2_L2_LIMIT_INIT, 0x8A);

            // Tap1 Initial Value = 0 for Mode1 DFE
            RxSetByte(P7B_A5_L0_INIT_3, 0x00);
            RxSetByte(P7B_B5_L1_INIT_3, 0x00);
            RxSetByte(P7B_C5_L2_INIT_3, 0x00);
        }
        else
        {
            // LE Max = 24, Initial = 12
            RxSetByte(P7B_A2_L0_LIMIT_INIT, 0x8C);
            RxSetByte(P7B_B2_L1_LIMIT_INIT, 0x8C);
            RxSetByte(P7B_C2_L2_LIMIT_INIT, 0x8C);

            // Tap1 Initial Value = 12 for Mode3 DFE
            RxSetByte(P7B_A5_L0_INIT_3, 0x0C);
            RxSetByte(P7B_B5_L1_INIT_3, 0x0C);
            RxSetByte(P7B_C5_L2_INIT_3, 0x0C);
        }
    }
    else    // ACDR
    {
        // LE Max = 21, Initial = 12
        RxSetByte(P7B_A2_L0_LIMIT_INIT, 0x5C);
        RxSetByte(P7B_B2_L1_LIMIT_INIT, 0x5C);
        RxSetByte(P7B_C2_L2_LIMIT_INIT, 0x5C);

        // Tap1 Initial Value = 15 for Mode3 DFE
        RxSetByte(P7B_A5_L0_INIT_3, 0x0F);
        RxSetByte(P7B_B5_L1_INIT_3, 0x0F);
        RxSetByte(P7B_C5_L2_INIT_3, 0x0F);
    }

    RxSetByte(P7B_A3_L0_INIT_1, 0x90);
    RxSetByte(P7B_B3_L1_INIT_1, 0x90);
    RxSetByte(P7B_C3_L2_INIT_1, 0x90);

    RxSetByte(P7B_A4_L0_INIT_2, 0x0F);
    RxSetByte(P7B_B4_L1_INIT_2, 0x0F);
    RxSetByte(P7B_C4_L2_INIT_2, 0x0F);
    g_ucTMDSRxTap0Init[RX_CUR] = RxGetByte(P7B_A4_L0_INIT_2);

    RxSetByte(P7B_A6_L0_INIT_4, 0x00);
    RxSetByte(P7B_B6_L1_INIT_4, 0x00);
    RxSetByte(P7B_C6_L2_INIT_4, 0x00);

    RxSetByte(P7B_A7_L0_INIT_5, 0x00);
    RxSetByte(P7B_B7_L1_INIT_5, 0x00);
    RxSetByte(P7B_C7_L2_INIT_5, 0x00);

    RxSetByte(P7B_A8_L0_INIT_6, 0x00);
    RxSetByte(P7B_B8_L1_INIT_6, 0x00);
    RxSetByte(P7B_C8_L2_INIT_6, 0x00);

    RxSetByte(P7B_A9_L0_INIT_7, 0x04);
    RxSetByte(P7B_B9_L1_INIT_7, 0x04);
    RxSetByte(P7B_C9_L2_INIT_7, 0x04);

    // Load Intial DFE Code
    RxSetByte(P7B_AA_L0_INIT_8, 0xFF);
    RxSetByte(P7B_BA_L1_INIT_8, 0xFF);
    RxSetByte(P7B_CA_L2_INIT_8, 0xFF);

    RxSetByte(P7B_AA_L0_INIT_8, 0x00);
    RxSetByte(P7B_BA_L1_INIT_8, 0x00);
    RxSetByte(P7B_CA_L2_INIT_8, 0x00);

    // DFE Loop Normal
    RxSetBit(P7B_EF_RESET_1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_EF_RESET_1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Disable All Adaptation Loop
    RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
    RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
    RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);
}

//--------------------------------------------------
// Description  : TMDS FLD Band Fine Tune  (EXINT0 Only)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxFLDBandFineTune_EXINT0(void)
{
    WORD pusLaneFreq[3];
    BYTE ucCount = 0;
    BYTE ucLaneCount = 0;
    BYTE pucBestVCOBand[3];
    BYTE pucAutoVCOBand[3];
    BYTE ucBacksetting2 = 0;

    pusLaneFreq[0] = 0;
    pusLaneFreq[1] = 0;
    pusLaneFreq[2] = 0;

    // Get 3 Lane Auto Result
    pucAutoVCOBand[0] = (RxGetByte(P7B_35_ANA_CDR_11) & 0x7F);
    pucAutoVCOBand[1] = (RxGetByte(P7B_36_ANA_CDR_12) & 0x7F);
    pucAutoVCOBand[2] = (RxGetByte(P7B_37_ANA_CDR_13) & 0x7F);

    // Scan Lane
    RxSetBit(P7B_32_ANA_CDR_08, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucAutoVCOBand[0]);
    RxSetBit(P7B_33_ANA_CDR_09, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucAutoVCOBand[1]);
    RxSetBit(P7B_34_ANA_CDR_10, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucAutoVCOBand[2]);

    ucBacksetting2 = RxGetByte(P71_EC_HDMI_FREQDET_STABLE);

    // Set Open Loop
    RxSetBit(P7B_2B_ANA_CDR_01, ~(_BIT7 | _BIT6 | _BIT5), _BIT6);

    // Change Measure Count  64=>3
    RxSetBit(P71_EC_HDMI_FREQDET_STABLE, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT1);

    for(ucLaneCount = 0; ucLaneCount < 3; ucLaneCount++)
    {
        // Read Lane0 Result
        RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, 0x00);
        RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT5 | _BIT4), ((ucLaneCount + 1) << 4));
        RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, _BIT7);

        // Waiting For Measure Done -> 300us
        for(ucCount = 0; ucCount <= 60; ucCount++)
        {
            DELAY_5US_EXINT();

            if(RxGetBit(P71_E6_HDMI_FREQDET_CTRL, _BIT6) == _BIT6)
            {
                // POP Result
                RxSetBit(P71_EC_HDMI_FREQDET_STABLE, ~_BIT7, _BIT7);

                pusLaneFreq[ucLaneCount] = ((DWORD)((WORD)(RxGetByte(P71_ED_HDMI_FREQDET_RESULT_M) << 8) | RxGetByte(P71_EE_HDMI_FREQDET_RESULT_L))*27 / 100);
                break;
            }
        }
        AWTO_PHY_FLD(ucLaneCount, ucCount);
    }

    // For 3 Lane Cal Best Band
    for(ucLaneCount = 0; ucLaneCount < 3; ucLaneCount++)
    {
        if(pusLaneFreq[ucLaneCount] < GET_INPUT_PIXEL_CLK())
        {
            pucBestVCOBand[ucLaneCount] = pucAutoVCOBand[ucLaneCount] + 1;
        }
        else
        {
            pucBestVCOBand[ucLaneCount] = pucAutoVCOBand[ucLaneCount];
        }
    }

    // Reload Best Band
    RxSetBit(P7B_32_ANA_CDR_08, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucBestVCOBand[0]);
    RxSetBit(P7B_33_ANA_CDR_09, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucBestVCOBand[1]);
    RxSetBit(P7B_34_ANA_CDR_10, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), pucBestVCOBand[2]);

    // Reload Measure TMDS Clock & Clear Unsatble IRQ Flag & Dummy POP Out
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT5 | _BIT4), 0x00);
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT7), 0x00);
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT7), _BIT7);
    for(ucCount = 0; ucCount <= 60; ucCount++)
    {
        DELAY_5US_EXINT();
        if(RxGetBit(P71_E6_HDMI_FREQDET_CTRL, _BIT6) == _BIT6)
        {
            // POP result
            RxSetBit(P71_EC_HDMI_FREQDET_STABLE, ~_BIT7, _BIT7);
            break;
        }
    }
    AWTO_PHY_FLD(3, ucCount);

    // Set Stable Count
    RxSetByte(P71_EC_HDMI_FREQDET_STABLE, ucBacksetting2);

    // Clear Unstable IRQ Flag
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT2, _BIT2);
}
//--------------------------------------------------
// Description  : TMDS Set PHY Function (EXINT0 Only)
// Input Value  : Measured Clk Count for PHY Setting
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxSetPhy_EXINT0(void)
{
    WORD usPixClk = isr_g_usInputPixelClk;   // one read: EX0 is masked / we are in EXINT0, nothing else writes it here

    BYTE ucIcp = 0;

    AWTO_PHY_START(RX_CUR + 2, (usPixClk <= 2000) ? 0 : ((usPixClk <= 3400) ? 1 : 2));

    //////////////
    // CDR Mode //
    //////////////

    if(usPixClk <= 2000)  // DCDR
    {
        // [3:0] reg_en_ana_cdr = 4'b0000 --> Disable Analog CDR
        RxSetBit(P7B_2A_ANA_CDR_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

        // [0] En_APLL_Lane2 = 1'b1 --> Enable Lane2 VCO as CMU
        RxSetBit(P7B_1B_CMU_01, ~_BIT0, _BIT0);

        if((usPixClk <= 1000) && (RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1))  // MHL mode
        {
            // [6:5] CMU_REFCK_SEL = 2'b10 --> Ref. TMDS Clock w/ Hysteresis OP
            RxSetBit(P7B_1B_CMU_01, ~(_BIT6 | _BIT5), _BIT6);
        }
        else
        {
            // [6:5] CMU_REFCK_SEL = 2'b00 --> Ref. TMDS Clock w/o Hysteresis OP
            RxSetBit(P7B_1B_CMU_01, ~(_BIT6 | _BIT5), 0x00);
        }
    }
    else  // ACDR
    {
        // [3:0] reg_en_ana_cdr = 4'b0111 --> Enable Lane0~2 Analog CDR
        RxSetBit(P7B_2A_ANA_CDR_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

        // [0] En_APLL_Lane2 = 1'b0 --> Disable Lane2 VCO as CMU
        RxSetBit(P7B_1B_CMU_01, ~_BIT0, 0x00);
    }

    ///////////////
    // RX CMU EN //
    ///////////////

    // [7] cmu_en = 0 --> Disable CMU PLL
    RxSetBit(P7B_1B_CMU_01, ~_BIT7, 0x00);

#if(_SOURCE_BACKGROUND_DETECT_SUPPORT == _ON)
    // [3:0] cdr_en = 4'b0000 --> Disable CDREN
    RxSetBit(P7B_1A_CMU_00, ~_BIT3, 0x00);
    DELAY_5US_EXINT();
    RxSetBit(P7B_1A_CMU_00, ~_BIT2, 0x00);
    DELAY_5US_EXINT();
    RxSetBit(P7B_1A_CMU_00, ~_BIT1, 0x00);
    DELAY_5US_EXINT();
    RxSetBit(P7B_1A_CMU_00, ~_BIT0, 0x00);

    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
    {
        if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
        {
            // [7:4] rx_en = 4'b1101 --> Enable RXEN for Lane0, 2, 3
            // [3:0] cdr_en = 4'b0101 --> Enable CDREX for Lane0, 2
            RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT6, _BIT6);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT5, 0x00);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT4, _BIT4);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT2, _BIT2);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT0, _BIT0);
        }
        else
        {
            // [7:4] rx_en = 4'b1001 --> Enable RXEN for Lane0, 3
            // [3:0] cdr_en = 4'b0001 --> Enable CDREX for Lane0
            RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT6, 0x00);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT5, 0x00);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT4, _BIT4);
            DELAY_5US_EXINT();
            RxSetBit(P7B_1A_CMU_00, ~_BIT0, _BIT0);
        }
    }
    else
    {
        // [7:4] rx_en = 4'b1111 --> Enable RXEN
        // [3:0] cdr_en = 4'b0001 ~ 4'b0011 ~ 4'b0111
        RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT6, _BIT6);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT5, _BIT5);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT4, _BIT4);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT2, _BIT2);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT1, _BIT1);
        DELAY_5US_EXINT();
        RxSetBit(P7B_1A_CMU_00, ~_BIT0, _BIT0);
    }
#else
    // [3:0] cdr_en = 4'b0000 --> Disable CDREN
    RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
    {
        if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
        {
            // [7:4] rx_en = 4'b1101 --> Enable RXEN for Lane0, 2, 3
            RxSetBit(P7B_1A_CMU_00, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT6 | _BIT4));

            // [3:0] cdr_en = 4'b0101 --> Enable CDREX for Lane0, 2
            RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT0));
        }
        else
        {
            // [7:4] rx_en = 4'b1001 --> Enable RXEN for Lane0, 3
            RxSetBit(P7B_1A_CMU_00, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT4));

            // [3:0] cdr_en = 4'b0001 --> Enable CDREX for Lane0
            RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT0);
        }
    }
    else
    {
        // [7:4] rx_en = 4'b1111 --> Enable RXEN
        RxSetBit(P7B_1A_CMU_00, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT6 | _BIT5 | _BIT4));

        // [3:0] cdr_en = 4'b0001 ~ 4'b0011 ~ 4'b0111
        RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT0);
        RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));
        RxSetBit(P7B_1A_CMU_00, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));
    }
#endif


    //////////////////////
    // A/DCDR  Setting  //
    //////////////////////

    // [1:0] reg_cdr_kvco = 2'b01 --> Analog CDR KVCO = 700M/v
    RxSetBit(P7B_2C_ANA_CDR_02, ~(_BIT1 | _BIT0), _BIT0);

    // [4] reg_sel_cont3 = 1'b1 --> BBPD UP/DN Pulse Div 3
    RxSetBit(P7B_2D_ANA_CDR_03, ~_BIT4, _BIT4);

    // [7] en_fld_ref_ecbuss = 0 --> FLD Reference Lane3 Clock
    RxSetBit(P7B_28_KOFFSET_04, ~_BIT7, 0x00);

    if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
    {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
        {
            // [5:4] reg_cmu_sel_cp = 2'b10 --> Analog CDR Cp = 2pF
            // [3] reg_en_largers_forcmu = 1'b1 --> Analog CDR Rs Increase 8K
            // [2:0] reg_cmu_sel_Rs = 3'b011 --> Analog CDR Rs = 12K + 8K
            RxSetBit(P7B_1E_CMU_04, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT3 | _BIT1 | _BIT0));

            // [3:0] reg_cdr_cp_in = 4'b1010 --> Analog CDR Icp = 31.5uA
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT1));
        }
        else   // HDMI Mode
#endif
        {
            // [5:4] reg_cmu_sel_cp = 2'b10 --> Analog CDR Cp = 2pF
            // [3] reg_en_largers_forcmu = 1'b1 --> Analog CDR Rs Increase 8K
            // [2:0] reg_cmu_sel_Rs = 3'b110 --> Analog CDR Rs = 16K + 8K
            RxSetBit(P7B_1E_CMU_04, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT3 | _BIT2 | _BIT1));

            // [3:0] reg_cdr_cp_in = 4'b1100 --> Analog CDR Icp = 37.5uA
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2));
        }
    }
    else
    {
        // [5:4] reg_cmu_sel_cp = 2'b00 --> Analog CDR Cp = 0pF
        // [3] reg_en_largers_forcmu = 1'b0 --> Analog CDR Rs Increase 0K
        RxSetBit(P7B_1E_CMU_04, ~(_BIT5 | _BIT4 | _BIT3), 0x00);

        if(usPixClk <= 3000)
        {
            // [6:4] reg_sel_cdr_res = 3'b101 --> Analog CDR Rs = 6K
            // [3:0] reg_cdr_cp_in = 4'b0101 --> Analog CDR Icp = 16.5uA
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT6 | _BIT4 | _BIT2 | _BIT0));
        }
        else
        {
            // [6:4] reg_sel_cdr_res = 3'b011 --> Analog CDR Rs = 2K
            // [3:0] reg_cdr_cp_in = 4'b0011 --> Analog CDR Icp = 10.5uA
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT1 | _BIT0));
        }
    }

    ucIcp = (RxGetByte(P7B_31_ANA_CDR_07) & 0x0F);

    // [7:5] KD = 3'b000 --> KD = 0
    RxSetBit(P7B_4F_KD, ~(_BIT7 | _BIT6 | _BIT5), 0x00);

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
    {
        // KI = 3'b001 --> KI = 1/16
        RxSetBit(P7B_50_KI_L0, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);

        if(usPixClk <= 1000)
        {
            // KP = 0x23 --> KP = 8.75
            RxSetByte(P7B_53_KP_L0, 0x23);
        }
        else
        {
            // KP = 0x2F --> KP = 11.75
            RxSetByte(P7B_53_KP_L0, 0x2F);
        }
    }
    else   // HDMI Mode
#endif
    {
        // KI = 3'b000 --> KI = 0
        RxSetBit(P7B_50_KI_L0, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
        RxSetBit(P7B_51_KI_L1, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
        RxSetBit(P7B_52_KI_L2, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

        if(usPixClk < 1500)
        {
            // KP = 0x20 --> KP = 8
            RxSetByte(P7B_53_KP_L0, 0x20);
            RxSetByte(P7B_54_KP_L1, 0x20);
            RxSetByte(P7B_55_KP_L2, 0x20);
        }
        else
        {
            // KP = 0x0F --> KP = 3.75
            RxSetByte(P7B_53_KP_L0, 0x0F);
            RxSetByte(P7B_54_KP_L1, 0x0F);
            RxSetByte(P7B_55_KP_L2, 0x0F);
        }
    }

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
    {
        // Check if Packed Pixel Mode
        if(RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())) == _TMDS_MHL_PPMODE_PHY_SETTING)
        {
            if(usPixClk <= 1500)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 30
                // cdr_counter = 480
                // 30/480 = 1/16 = 5*(1/80 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x1D);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0100 1100 --> 76 + 4 = 80
                RxSetByte(P7B_20_CMU_06, 0x4C);

                // [2:0] SEL_DIV = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

                // [6:4] rate_sel = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT5);
            }
            else
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 50
                // cdr_counter = 400
                // 50/400 = 1/8 = 5*(1/40 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x31);
                RxSetByte(P7B_2F_ANA_CDR_05, 0x8F);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0010 0100 --> 36 + 4 = 40
                RxSetByte(P7B_20_CMU_06, 0x24);

                // [2:0] rate_sel = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);

                // [6:4] SEL_DIV = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT4);
            }
        }
        else  // MHL 24bit Mode
        {
            if(usPixClk <= 750)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 20
                // cdr_counter = 480
                // 20/480 = 1/24 = 5*(1/120 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x13);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0111 0100 --> 116 + 4 = 120
                RxSetByte(P7B_20_CMU_06, 0x74);

                // [2:0] SEL_DIV = 3'b011 --> 375MHz ~ 750MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

                // [6:4] rate_sel = 3'b011 --> 375MHz ~ 750MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), (_BIT5 | _BIT4));
            }
            else if(usPixClk <= 1500)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 40
                // cdr_counter = 480
                // 40/480 = 1/12 = 5*(1/60 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x27);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0011 1000 --> 56 + 4 = 60
                RxSetByte(P7B_20_CMU_06, 0x38);

                // [2:0] SEL_DIV = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

                // [6:4] rate_sel = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT5);
            }
            else if(usPixClk <= 3000)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 80
                // cdr_counter = 480
                // 80/480 = 1/6 = 5*(1/30 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x4F);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0001 1010 --> 26 + 4 = 30
                RxSetByte(P7B_20_CMU_06, 0x1A);

                // [2:0] SEL_DIV = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);

                // [6:4] rate_sel = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT4);
            }
            else
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 160
                // cdr_counter = 480
                // 160/480 = 1/3 = 5*(1/15 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x9F);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0000 1101 --> 11 + 4 = 30
                RxSetByte(P7B_20_CMU_06, 0x0B);

                // [2:0] SEL_DIV = 3'b000 --> 3000MHz ~ 6000MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

                // [6:4] rate_sel = 3'b000 --> 3000MHz ~ 6000MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), 0x00);
            }
        }
    }
    else     // HDMI Mode
#endif
    {
#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _FALSE)  // 1:10
#endif
        {
            if(usPixClk <= 375)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 30
                // cdr_counter = 480
                // 30/480 = 1/16 = 5*(1/80 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x1D);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xDF);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0100 1100 --> 76 + 4 = 80
                RxSetByte(P7B_20_CMU_06, 0x4C);

                // [2:0] SEL_DIV = 3'b100 --> 187.5MHz ~ 375MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT2);

                // [6:4] rate_sel = 3'b100 --> 187.5MHz ~ 375MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT6);
            }
            else if(usPixClk <= 750)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 50
                // cdr_counter = 400
                // 50/400 = 1/8 = 5*(1/40 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x31);
                RxSetByte(P7B_2F_ANA_CDR_05, 0x8F);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0010 0100 --> 36 + 4 = 40
                RxSetByte(P7B_20_CMU_06, 0x24);

                // [2:0] SEL_DIV = 3'b011 --> 375MHz ~ 750MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

                // [6:4] rate_sel = 3'b011 --> 375MHz ~ 750MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), (_BIT5 | _BIT4));
            }
            else if(usPixClk <= 1500)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 125
                // cdr_counter = 500
                // 125/500 = 1/4 = 5*(1/20 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0x7C);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xF3);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /1
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), 0x00);

                // [7:0] N_CODE = 8'b0001 0000 --> 16 + 4 = 20
                RxSetByte(P7B_20_CMU_06, 0x10);

                // [2:0] SEL_DIV = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

                // [6:4] rate_sel = 3'b010 --> 750MHz ~ 1500MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT5);
            }
            else if(usPixClk <= 3000)
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 250
                // cdr_counter = 500
                // 250/500 = 1/2 = 5*(1/10 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
                RxSetByte(P7B_2E_ANA_CDR_04, 0xF9);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xF3);

                // [5:4] CMU_SELPREDIV = 2'b00 --> /2
                RxSetBit(P7B_1F_CMU_05, ~(_BIT5 | _BIT4), _BIT4);

                // [7:0] N_CODE = 8'b0001 0000 --> 16 + 4 = 20
                RxSetByte(P7B_20_CMU_06, 0x10);

                // [2:0] SEL_DIV = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);

                // [6:4] rate_sel = 3'b001 --> 1500MHz ~ 3000MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), _BIT4);
            }
            else     // ACDR 1:10
            {
                // Analog CDR Auto FLD Counter
                // ref_conuter = 500
                // cdr_counter = 500
                // 500/500 = 1/1 = 5*(1/5 clock rate)
                RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));
                RxSetByte(P7B_2E_ANA_CDR_04, 0xF3);
                RxSetByte(P7B_2F_ANA_CDR_05, 0xF3);

                // [2:0] rate_sel = 3'b000 --> 3000MHz ~ 6000MHz
                RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

                // [6:4] SEL_DIV = 3'b000 --> 3000MHz ~ 6000MHz
                RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), 0x00);
            }
        }
#if(_D2_HDMI_2_0_SUPPORT == _ON)
        else  // ACDR 1:40
        {
            // Analog CDR Auto FLD Counter
            // ref_conuter = 125
            // cdr_counter = 500
            // 100/400 = 1/4 = 5*(1/20 clock rate)
            RxSetBit(P7B_2D_ANA_CDR_03, ~(_BIT1 | _BIT0), _BIT0);
            RxSetByte(P7B_2E_ANA_CDR_04, 0x7C);
            RxSetByte(P7B_2F_ANA_CDR_05, 0xF3);

            // [2:0] rate_sel = 3'b000 --> 3000MHz ~ 6000MHz
            RxSetBit(P7B_21_CMU_07, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

            // [6:4] SEL_DIV = 3'b000 --> 3000MHz ~ 6000MHz
            RxSetBit(P7B_3E_EN_01, ~(_BIT6 | _BIT5 | _BIT4), 0x00);
        }
#endif
    }


    /////////////////////
    // Rx Misc Setting //
    /////////////////////

    // [0] en_clkout_manual = 0 --> Disable Clkout
    RxSetBit(P7B_0E_SDM_03, ~_BIT0, 0x00);

    // [0] en_eqen_manual = 0 --> Disable Clkout
    RxSetBit(P7B_10_EQEN_TIMER, ~_BIT0, 0x00);

    // [0] en_data_manual = 0 --> Disable Dataout
    RxSetBit(P7B_11_DATA_TIMER, ~_BIT0, 0x00);

    // [4] reg_acdr_l0_en = 1'b0 --> Disable Lane0 ACDR_DFE
    // [3] reg_en_data_manual_l0 = 1'b0
    // [2] reg_bypass_data_rdy_l0 = 1'b1
    // [1] reg_en_eqen_manual_l0 = 1'b0
    // [0] reg_bypass_eqen_rdy_l0 = 1'b1
    RxSetBit(P7B_12_ANA_CDR, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT0));

    // [6:4] RST_N = 3'b000 = 3'b111 -> Digital Circuit Reset Toggle
    // [2:0] Disable DCDR
    RxSetBit(P7B_38_TMDS_RESET, ~(_BIT6 | _BIT5 | _BIT4 | _BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P7B_38_TMDS_RESET, ~(_BIT6 | _BIT5 | _BIT4 | _BIT2 | _BIT1 | _BIT0), (_BIT6 | _BIT5 | _BIT4));


    /////////////////
    // DFE Setting //
    /////////////////

    // Load DFE Initial Code
    ScalerTMDSRxSetDFEInitial_EXINT0();

    // Enable Tap0~4
    RxSetBit(P7B_21_CMU_07, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3));

    if(usPixClk <= 2500)
    {
        // [3:1] LE_lowgain_highboost = 111 --> LE HighBoost Mode
        RxSetBit(P7B_22_CMU_08, ~(_BIT3 | _BIT2 | _BIT1), (_BIT3 | _BIT2 | _BIT1));
    }
    else
    {
        // [3:1] LE_lowgain_highboost = 100 --> LE HighBoost Mode
        RxSetBit(P7B_22_CMU_08, ~(_BIT3 | _BIT2 | _BIT1), _BIT3);
    }

    if(usPixClk <= 2000)
    {
        // [7] SEL_DFE_DELAY = 1'b1 --> Increase DFE Delay
        RxSetBit(P7B_22_CMU_08, ~_BIT7, _BIT7);
    }
    else
    {
        // [7] SEL_DFE_DELAY = 1'b0 --> Normal DFE Delay
        RxSetBit(P7B_22_CMU_08, ~_BIT7, 0x00);
    }

    if(usPixClk <= 2500)
    {
        // [7:5] LE_RLSEL = 3'b011
        // [4:2] LE_ISEL = 3'b000
        RxSetBit(P7B_23_CMU_09, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    }
    else if(usPixClk <= 3400)
    {
        // [7:5] LE_RLSEL = 3'b001
        // [4:2] LE_ISEL = 3'b010
        RxSetBit(P7B_23_CMU_09, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT3));
    }
    else
    {
        // [7:5] LE_RLSEL = 3'b000
        // [4:2] LE_ISEL = 3'b011
        RxSetBit(P7B_23_CMU_09, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT3 | _BIT2));
    }


    ////////////////////
    // First K Offset //
    ////////////////////

    // Disable Sumamp High Gain Mode
    RxSetBit(P7B_1D_CMU_03, ~_BIT4, 0x00);

    // [5] Enable Foreground Calibration Auto Mode
    RxSetBit(P7B_24_KOFFSET_00, ~_BIT5, _BIT5);

    // [6] Toggle Foreground Calibration
    RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);
    RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, 0x00);
    RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);

    // Waiting for K Offset
    DELAY_XUS_EXINT(50);


    ///////////////////////////////////
    // FLD Lock Band & DFE Adaptation//
    ///////////////////////////////////

    // [7] reg_auto_mode = 1'b1 --> FLD Select Auto Mode
    // [6] reg_adp_en_manual = 1'b0 --> Disable adp_en_manual
    // [5] reg_cp_en_manual = 1'b0 -->  Disable cp_en_manual
    // [4] reg_adp_eq_off = 1'b0 --> Enable Analog CDR DFE Adaptation
    // [3] xtal_en = 0 --> FLD Reference Input Clock
    // [0] reg_cp_adj_en = 1'b1 --> Enable Adjust Icp When Tracking
    RxSetBit(P7B_2B_ANA_CDR_01, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT0), (_BIT7 | _BIT0));

    // [5] en_wide_temp = 1'b1 --> Enable Wide Temp VCO Band
    RxSetBit(P7B_2D_ANA_CDR_03, ~_BIT5, _BIT5);

    // [3:2] en_vcm_tune = 2'b11 --> Vc = Vdd/2
    RxSetBit(P7B_2C_ANA_CDR_02, ~(_BIT3 | _BIT2), (_BIT3 | _BIT2));

    if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
    {
        // [7] reg_rstb_fsm --> Toggle for FLD reset
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, 0x00);
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, _BIT7);

        // Waiting for FLD Lock Band
        AWTO_PHY_FLD_WAIT(360);

        // [7] cmu_en = 1'b1 --> Enable CMU PLL
        RxSetBit(P7B_1B_CMU_01, ~_BIT7, _BIT7);

        // Enable Digital CDR
        RxSetByte(P7B_38_TMDS_RESET, 0xFF);

        // Waiting for CMU Stable
        AWTO_PHY_CMU_WAIT(150);

        // [0] en_clkout_manual = 1 --> Enable Clkout
        RxSetBit(P7B_0E_SDM_03, ~_BIT0, _BIT0);

        // [0] en_eqen_manual = 1 --> Enable Adaptation
        RxSetBit(P7B_10_EQEN_TIMER, ~_BIT0, _BIT0);

        if(usPixClk <= 375) // TMDS Clock < 375
        {
            // Disable Adaptation Loop  0x000
            RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
            RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
            RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);
        }
        else if(usPixClk <= 1000)// 375~1000
        {
            // Enable the Vth, Tap0~1 Adaptation Loop 0x043
            RxSetByte(P7B_A1_L0_DFE_EN_2, 0x43);
            RxSetByte(P7B_B1_L1_DFE_EN_2, 0x43);
            RxSetByte(P7B_C1_L2_DFE_EN_2, 0x43);
        }
        else
        {
            // Enable the LE, Vth, Tap0~1 Adaptation Loop 0x0C3
            RxSetByte(P7B_A1_L0_DFE_EN_2, 0xC3);
            RxSetByte(P7B_B1_L1_DFE_EN_2, 0xC3);
            RxSetByte(P7B_C1_L2_DFE_EN_2, 0xC3);
        }

        // Waiting for the Adaptation
        DELAY_XUS_EXINT(290);
    }
    else if(usPixClk <= 3400) // 2000~3400 Analog CDR
    {
        // [7] cmu_en = 1'b1 --> Enable CMU PLL
        RxSetBit(P7B_1B_CMU_01, ~_BIT7, _BIT7);

        // [4] reg_acdr_l0_en = 1'b1 --> Enable Lane0 ACDR
        // [1] reg_en_eqen_manual_l0 = 1'b1
        RxSetBit(P7B_12_ANA_CDR, ~(_BIT4 | _BIT1), (_BIT4 | _BIT1));

        // [7] reg_rstb_fsm --> Toggle for FLD reset
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, 0x00);
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, _BIT7);

        // Enable LE, Vth, Tap0~4 Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0xDF);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0xDF);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0xDF);

        // Waiting for VCO Stable & DFE Adaptation
        DELAY_XUS_EXINT(360);

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
        {
            if(usPixClk > 2500) // for 2500~3000 MHL PP Mode
            {
                // Start to Record LE Max/Min
                RxSetBit(P7B_F2_COEF_3, ~_BIT0, _BIT0);

                // Waiting for DFE Adaptation
                DELAY_XUS_EXINT(150);

                // Stop to Record LE Max/Min
                RxSetBit(P7B_F2_COEF_3, ~_BIT0, 0x00);

                // Disable All Adaptation Loop
                RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);

                // Read Back LE Max
                RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT3);

                // Read Back Lane0
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
                g_pucTMDSRxLEMax[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

                // Set Max Value of LE
                RxSetBit(P7B_A5_L0_INIT_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), g_pucTMDSRxLEMax[RX_CUR][0]);

                // Reload LE Max
                RxSetBit(P7B_AA_L0_INIT_8, ~_BIT1, _BIT1);
                RxSetBit(P7B_AA_L0_INIT_8, ~_BIT1, 0x00);
            }
        }
        else // HDMI Mode
#endif
        {
            if(usPixClk > 2900) // for 2900~3400 10M Cable Case
            {
                // Start to Record LE Max/Min
                RxSetBit(P7B_F2_COEF_3, ~_BIT0, _BIT0);

                // Waiting for DFE Adaptation
                DELAY_XUS_EXINT(150);

                // Stop to Record LE Max/Min
                RxSetBit(P7B_F2_COEF_3, ~_BIT0, 0x00);

                // Disable All Adaptation Loop
                RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
                RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
                RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);

                // Read Back LE Max
                RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT3);

                // Read Back Lane0
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
                g_pucTMDSRxLEMax[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

                // Read Back Lane1
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
                g_pucTMDSRxLEMax[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

                // Read Back Lane2
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
                g_pucTMDSRxLEMax[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

                // Read Back Tap1 Max
                RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT2);

                // Read Back Lane0
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
                g_pucTMDSRxTap1Max[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

                // Read Back Lane1
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
                g_pucTMDSRxTap1Max[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

                // Read Back Lane2
                RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
                g_pucTMDSRxTap1Max[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

                // Lane0 LEQ >= 20
                if(g_pucTMDSRxLEMax[RX_CUR][0] >= 16)
                {
                    // Set Tap2 = 6
                    RxSetByte(P7B_A6_L0_INIT_4, 0x06);

                    // Set Max Value of LE + Tap1
                    RxSetBit(P7B_A5_L0_INIT_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (g_pucTMDSRxLEMax[RX_CUR][0] + g_pucTMDSRxTap1Max[RX_CUR][0]));

                    // Reload LE/Tap1~2
                    RxSetBit(P7B_AA_L0_INIT_8, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
                    RxSetBit(P7B_AA_L0_INIT_8, ~(_BIT2 | _BIT1), 0x00);
                }

                // Lane1 LEQ >= 20
                if(g_pucTMDSRxLEMax[RX_CUR][1] >= 16)
                {
                    // Set Tap2 = 6
                    RxSetByte(P7B_B6_L1_INIT_4, 0x06);

                    // Set Max Value of LE + Tap1
                    RxSetBit(P7B_B5_L1_INIT_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (g_pucTMDSRxLEMax[RX_CUR][1] + g_pucTMDSRxTap1Max[RX_CUR][1]));

                    // Reload LE/Tap1~2
                    RxSetBit(P7B_BA_L1_INIT_8, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
                    RxSetBit(P7B_BA_L1_INIT_8, ~(_BIT2 | _BIT1), 0x00);
                }

                // Lane2 LEQ >= 20
                if(g_pucTMDSRxLEMax[RX_CUR][2] >= 16)
                {
                    // Set Tap2 = 6
                    RxSetByte(P7B_C6_L2_INIT_4, 0x06);

                    // Set Max Value of LE + Tap1
                    RxSetBit(P7B_C5_L2_INIT_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (g_pucTMDSRxLEMax[RX_CUR][2] + g_pucTMDSRxTap1Max[RX_CUR][2]));

                    // Reload LE/Tap1~2
                    RxSetBit(P7B_CA_L2_INIT_8, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
                    RxSetBit(P7B_CA_L2_INIT_8, ~(_BIT2 | _BIT1), 0x00);
                }
            }
        }

        // Disable Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);
    }
    else  // 3400~6000 Analog CDR
    {
        // [7] cmu_en = 1'b1 --> Enable CMU PLL
        RxSetBit(P7B_1B_CMU_01, ~_BIT7, _BIT7);

        // [4] reg_acdr_l0_en = 1'b1 --> Enable Lane0 ACDR
        // [1] reg_en_eqen_manual_l0 = 1'b1
        RxSetBit(P7B_12_ANA_CDR, ~(_BIT4 | _BIT1), (_BIT4 | _BIT1));

        // [7] reg_rstb_fsm --> Toggle for FLD reset
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, 0x00);
        RxSetBit(P7B_2A_ANA_CDR_00, ~_BIT7, _BIT7);

        // Enable LE, Vth, Tap0~4 Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0xDF);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0xDF);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0xDF);

        // Waiting for VCO Stable & DFE Adaptation
        AWTO_PHY_FLD_WAIT(360);
        AWTO_PHY_STAMP(0);

        // RLE0638 2.9 ms unscrambled-source delay dropped: requirement not confirmed (#331)
        AWTO_PHY_STAMP(1);

        // Start to Record Tap0/Tap1 Max/Min
        RxSetBit(P7B_F2_COEF_3, ~_BIT0, _BIT0);

        // Waiting for DFE Adaptation
        DELAY_XUS_EXINT(150);

        // Stop to Record Tap0 Max/Min
        RxSetBit(P7B_F2_COEF_3, ~_BIT0, 0x00);

        // Disable Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);

        // Read Back Tap0 Max
        RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), 0x00);

        // Read Back Lane0
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
        g_pucTMDSRxTap0Max[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane1
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
        g_pucTMDSRxTap0Max[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane2
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
        g_pucTMDSRxTap0Max[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Tap0 Min
        RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT1);

        // Read Back Lane0
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
        g_pucTMDSRxTap0Min[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane1
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
        g_pucTMDSRxTap0Min[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane2
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
        g_pucTMDSRxTap0Min[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

        // Reload Max Value of Tap0
        RxSetByte(P7B_A4_L0_INIT_2, g_pucTMDSRxTap0Min[RX_CUR][0]);
        RxSetByte(P7B_B4_L1_INIT_2, g_pucTMDSRxTap0Min[RX_CUR][1]);
        RxSetByte(P7B_C4_L2_INIT_2, g_pucTMDSRxTap0Min[RX_CUR][2]);

        // Reload Tap0
        RxSetByte(P7B_AA_L0_INIT_8, 0x01);
        RxSetByte(P7B_BA_L1_INIT_8, 0x01);
        RxSetByte(P7B_CA_L2_INIT_8, 0x01);
        RxSetByte(P7B_AA_L0_INIT_8, 0x00);
        RxSetByte(P7B_BA_L1_INIT_8, 0x00);
        RxSetByte(P7B_CA_L2_INIT_8, 0x00);

        // Enable LE/Tap1 Adapt
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0x82);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0x82);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0x82);

        // Waiting for DFE Adaptation
        DELAY_XUS_EXINT(290);

        // Start to Record LE Max/Min
        RxSetBit(P7B_F2_COEF_3, ~_BIT0, _BIT0);

        // Waiting for DFE Adaptation
        DELAY_XUS_EXINT(150);

        // Stop to Record LE Max/Min
        RxSetBit(P7B_F2_COEF_3, ~_BIT0, 0x00);

        // Disable Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);

        // Read Back LE Min
        RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), (_BIT3 | _BIT1));

        // Read Back Lane0
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
        g_pucTMDSRxLEMin[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane1
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
        g_pucTMDSRxLEMin[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane2
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
        g_pucTMDSRxLEMin[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

        // Read Back LE Max
        RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT3);

        // Read Back Lane0
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
        g_pucTMDSRxLEMax[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane1
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
        g_pucTMDSRxLEMax[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane2
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
        g_pucTMDSRxLEMax[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Tap1 Max
        RxSetBit(P7B_F2_COEF_3, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT2);

        // Read Back Lane0
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), 0x00);
        g_pucTMDSRxTap1Max[RX_CUR][0] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane1
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT6);
        g_pucTMDSRxTap1Max[RX_CUR][1] = RxGetByte(P7B_F3_COEF_4);

        // Read Back Lane2
        RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), _BIT7);
        g_pucTMDSRxTap1Max[RX_CUR][2] = RxGetByte(P7B_F3_COEF_4);

        // Reload LE/Tap1 to Max
        RxSetByte(P7B_A5_L0_INIT_3, g_pucTMDSRxLEMax[RX_CUR][0] + g_pucTMDSRxTap1Max[RX_CUR][0]);
        RxSetByte(P7B_B5_L1_INIT_3, g_pucTMDSRxLEMax[RX_CUR][1] + g_pucTMDSRxTap1Max[RX_CUR][1]);
        RxSetByte(P7B_C5_L2_INIT_3, g_pucTMDSRxLEMax[RX_CUR][2] + g_pucTMDSRxTap1Max[RX_CUR][2]);

        // Reload LE + Tap1
        RxSetByte(P7B_AA_L0_INIT_8, 0x02);
        RxSetByte(P7B_BA_L1_INIT_8, 0x02);
        RxSetByte(P7B_CA_L2_INIT_8, 0x02);
        RxSetByte(P7B_AA_L0_INIT_8, 0x00);
        RxSetByte(P7B_BA_L1_INIT_8, 0x00);
        RxSetByte(P7B_CA_L2_INIT_8, 0x00);
    }

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) == _BIT1)  // MHL Mode
    {
        // Disable Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);

        // [4] reg_adp_eq_off = 1'b1 --> Disable Adaptation for Analog CDR
        RxSetBit(P7B_2B_ANA_CDR_01, ~_BIT4, _BIT4);

        // [1] reg_en_eqen_manual_l0 = 1'b0
        RxSetBit(P7B_12_ANA_CDR, ~_BIT1, 0x00);

        // Reload Tap0 = 21
        RxSetByte(P7B_A4_L0_INIT_2, 0x15);
        RxSetByte(P7B_AA_L0_INIT_8, 0x01);
        RxSetByte(P7B_AA_L0_INIT_8, 0x00);

        // Enable Sumamp High Gain Mode
        RxSetBit(P7B_1D_CMU_03, ~_BIT4, _BIT4);

        /////////////////////
        // Second K Offset //
        /////////////////////

        // [5] Enable Foreground Calibration Auto Mode
        RxSetBit(P7B_24_KOFFSET_00, ~_BIT5, _BIT5);

        // [6] Toggle Foreground Calibration
        RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);
        RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, 0x00);
        RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);

        // Waiting for K Offset
        DELAY_XUS_EXINT(150);

        // Set Manual FLD Fine Tune OK
        ScalerTMDSRxFLDBandFineTune_EXINT0();

        // [3:0] reg_cdr_cp_in --> Double Icp to Enlarge Locking Range
        if(ucIcp > 7)
        {
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));
        }
        else
        {
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (ucIcp << 1));
        }

        // Waiting for VCO Stable
        DELAY_25US_EXINT();

        // [6] reg_adj_en_manual = 1'b1 -->  Enable adj_en_manual
        // [5] reg_cp_en_manual = 1'b1 -->  Enable cp_en_manual
        RxSetBit(P7B_2B_ANA_CDR_01, ~(_BIT6 | _BIT5), (_BIT6 | _BIT5));

        // Waiting for VCO Stable
        DELAY_XUS_EXINT(80);

        // [3:0] reg_cdr_cp_in --> Restore Icp to Original Setting
        RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), ucIcp);

        // Waiting for VCO Stable
        DELAY_XUS_EXINT(80);
    }
    else
#endif
    {
        if(RxGetBit(P7B_1B_CMU_01, _BIT0) == _BIT0) // DCDR
        {
            // Disable the Vth Adaptation Loop
            RxSetBit(P7B_A1_L0_DFE_EN_2, ~_BIT6, 0x00);
            RxSetBit(P7B_B1_L1_DFE_EN_2, ~_BIT6, 0x00);
            RxSetBit(P7B_C1_L2_DFE_EN_2, ~_BIT6, 0x00);
        }
        else // 2000~6000 ACDR
        {
            // [4] reg_adp_eq_off = 1'b1 --> Disable Adaptation for Analog CDR
            RxSetBit(P7B_2B_ANA_CDR_01, ~_BIT4, _BIT4);

            // [1] reg_en_eqen_manual_l0 = 1'b0
            RxSetBit(P7B_12_ANA_CDR, ~_BIT1, 0x00);

            // Enable Sumamp High Gain Mode
            RxSetBit(P7B_1D_CMU_03, ~_BIT4, _BIT4);

            /////////////////////
            // Second K Offset //
            /////////////////////

            // Read Back K offset Lane0
            if((RxGetByte(P7B_27_KOFFSET_03) & 0x1F) > 24)
            {
                // Set Servo = 24
                RxSetBit(P7B_A3_L0_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | _BIT3));
            }
            else if((RxGetByte(P7B_27_KOFFSET_03) & 0x1F) < 8)
            {
                // Set Servo = 8
                RxSetBit(P7B_A3_L0_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT3);
            }

            // Read Back K offset Lane1
            if((RxGetByte(P7B_28_KOFFSET_04) & 0x1F) > 24)
            {
                // Set Servo = 24
                RxSetBit(P7B_B3_L1_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | _BIT3));
            }
            else if((RxGetByte(P7B_28_KOFFSET_04) & 0x1F) < 8)
            {
                // Set Servo = 8
                RxSetBit(P7B_B3_L1_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT3);
            }

            // Read Back K offset Lane2
            if((RxGetByte(P7B_29_KOFFSET_05) & 0x1F) > 24)
            {
                // Set Servo = 24
                RxSetBit(P7B_C3_L2_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | _BIT3));
            }
            else if((RxGetByte(P7B_29_KOFFSET_05) & 0x1F) < 8)
            {
                // Set Servo = 8
                RxSetBit(P7B_C3_L2_INIT_1, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT3);
            }

            // Reload Servo
            RxSetByte(P7B_AA_L0_INIT_8, 0x20);
            RxSetByte(P7B_BA_L1_INIT_8, 0x20);
            RxSetByte(P7B_CA_L2_INIT_8, 0x20);
            RxSetByte(P7B_AA_L0_INIT_8, 0x00);
            RxSetByte(P7B_BA_L1_INIT_8, 0x00);
            RxSetByte(P7B_CA_L2_INIT_8, 0x00);

            // [5] Enable Foreground Calibration Auto Mode
            RxSetBit(P7B_24_KOFFSET_00, ~_BIT5, _BIT5);

            // [6] Toggle Foreground Calibration
            RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);
            RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, 0x00);
            RxSetBit(P7B_24_KOFFSET_00, ~_BIT6, _BIT6);

            AWTO_PHY_STAMP(2);
            // Waiting for K Offset
            DELAY_XUS_EXINT(150);
            AWTO_PHY_STAMP(3);

            // Set Manual FLD Fine Tune OK
            ScalerTMDSRxFLDBandFineTune_EXINT0();
            AWTO_PHY_STAMP(4);

            // [3:0] reg_cdr_cp_in --> Double Icp to Enlarge Locking Range
            if(ucIcp > 7)
            {
                RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));
            }
            else
            {
                RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (ucIcp << 1));
            }

            // Waiting for VCO Stable
            DELAY_25US_EXINT();

            // [6] reg_adj_en_manual = 1'b1 -->  Enable adj_en_manual
            // [5] reg_cp_en_manual = 1'b1 -->  Enable cp_en_manual
            RxSetBit(P7B_2B_ANA_CDR_01, ~(_BIT6 | _BIT5), (_BIT6 | _BIT5));

            // Waiting for VCO Stable
            DELAY_XUS_EXINT(80);

            // [3:0] reg_cdr_cp_in --> Restore Icp to Original Setting
            RxSetBit(P7B_31_ANA_CDR_07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), ucIcp);

            // Waiting for VCO Stable
            DELAY_XUS_EXINT(80);
        }
    }

    // solve philip DVD issue
    if((RxGetBit(P7B_E4_GAIN_3, _BIT1) == _BIT1) && (((g_pucTMDSRxTap0Max[RX_CUR][0] == g_ucTMDSRxTap0Init[RX_CUR]) && (g_pucTMDSRxTap0Min[RX_CUR][0] == g_ucTMDSRxTap0Init[RX_CUR])) ||
                                                               ((g_pucTMDSRxTap0Max[RX_CUR][1] == g_ucTMDSRxTap0Init[RX_CUR]) && (g_pucTMDSRxTap0Min[RX_CUR][1] == g_ucTMDSRxTap0Init[RX_CUR])) ||
                                                               ((g_pucTMDSRxTap0Max[RX_CUR][2] == g_ucTMDSRxTap0Init[RX_CUR]) && (g_pucTMDSRxTap0Min[RX_CUR][2] == g_ucTMDSRxTap0Init[RX_CUR]))))
    {
        // Disable Sumamp High Gain Mode
        RxSetBit(P7B_1D_CMU_03, ~_BIT4, 0x00);

        // [1] reg_en_eqen_manual_l0 = 1'b1
        RxSetBit(P7B_12_ANA_CDR, ~_BIT1, _BIT1);

        // Enable LE, Vth, Tap0~4 Adaptation
        RxSetByte(P7B_A1_L0_DFE_EN_2, 0xDF);
        RxSetByte(P7B_B1_L1_DFE_EN_2, 0xDF);
        RxSetByte(P7B_C1_L2_DFE_EN_2, 0xDF);
    }

    // [3] reg_en_data_manual_l0 = 1'b1
    RxSetBit(P7B_12_ANA_CDR, ~_BIT3, _BIT3);

    // [0] en_data_manual = 1'b1 --> Enable Dataout
    RxSetBit(P7B_11_DATA_TIMER, ~_BIT0, _BIT0);

    // Reset PHY -> MAC Interface
    RxSetBit(P71_A7_TMDS_PWDCTL, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P71_A7_TMDS_PWDCTL, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Reset HDMI 3 Channel FIFO
    RxSetBit(P71_B0_TMDS_CHANNEL_FIFO, ~_BIT6, _BIT6);

    // HDMI 3 Channel FIFO Global Enable
    RxSetBit(P71_B0_TMDS_CHANNEL_FIFO, ~(_BIT7 | _BIT6), _BIT7);

    // Clear RGB Data Detection Flags
    RxSetBit(P71_A4_TMDS_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT6 | _BIT5));
}

//--------------------------------------------------
// Description  : Freq. stable PHY set-up, run from the main loop with EX0 masked (was inside the EXINT0 handler)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxPhySetDeferred(void)
{
    BYTE ucEx0 = EX0;
    BYTE ucAp;
    BYTE ucApc;
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    bit bMHLFail = _FALSE;
#endif

    EX0 = 0;

    if(isr_g_ucTMDSRxPhyPend[RX_CUR] == _FALSE)
    {
        EX0 = ucEx0;
        return;
    }

    isr_g_ucTMDSRxPhyPend[RX_CUR] = _FALSE;
    ucAp = RxGetByte(P71_C9_HDMI_AP);
    ucApc = RxGetByte(P71_C8_HDMI_APC);
    RxSetBit(P71_C8_HDMI_APC, ~_BIT0, 0x00);

    // The other port's handler may have overwritten the shared pixel clock since
    SET_INPUT_PIXEL_CLK(isr_g_usTMDSRxPhyClk[RX_CUR]);

    // Enable Freq unstable IRQ
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));

    if((RXSEL((GET_TMDS_RX2_PHY_SET()), (GET_TMDS_RX3_PHY_SET())) == _FALSE) || ((bit)ScalerTMDSRxCheckCDRStable_EXINT0(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE))
    {
        isr_g_usTMDSRxClkCount[RX_CUR] = ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS);

        // If Measure Divider = /2 then CLK x 2
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
        if(RxGetBit(P71_CA_HDMI_DP, _BIT6) == _BIT6)
        {
            // TMDS_OFFLine Measure FREQ(MHz) = GDI_CLK(MHz) * 1024 * 2 / isr_g_usTMDSRx2ClkCount
            SET_TMDS_OFFLINE_MEASURE_CLK(((DWORD)(_GDI_CLK_KHZ * 1024) * 2 / 100) / isr_g_usTMDSRxClkCount[RX_CUR]);
        }
        else
        {
            // TMDS_OFFLine Measure FREQ(MHz) = GDI_CLK(MHz) * 1024 / isr_g_usTMDSRx2ClkCount
            SET_TMDS_OFFLINE_MEASURE_CLK(((DWORD)(_GDI_CLK_KHZ * 1024) / 100) / isr_g_usTMDSRxClkCount[RX_CUR]);
        }

#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _TRUE)
        {
            SET_TMDS_OFFLINE_MEASURE_CLK((GET_TMDS_OFFLINE_MEASURE_CLK() * 4));
        }
#endif

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
        {
            RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR);

#if(_MHL_DEBUG_WITHOUT_CBUS_MODE == _ON)
            // Set HDMI/DVI switch to Auto Mode
            RxSetBit(P71_CA_HDMI_DP, ~(_BIT7 | _BIT6 | _BIT3), 0x00);
#else
            // Set HDMI/DVI switch to Manual Mode and Forced to HDMI
            RxSetBit(P71_CA_HDMI_DP, ~(_BIT7 | _BIT6 | _BIT3 | _BIT2), (_BIT3 | _BIT2));
#endif

            if((GET_INPUT_PIXEL_CLK() >= 730) && (GET_INPUT_PIXEL_CLK() <= 770))
            {
                RXSEL((SET_TMDS_RX2_CLK_MODE(_TMDS_MHL_PPMODE_PHY_SETTING)), (SET_TMDS_RX3_CLK_MODE(_TMDS_MHL_PPMODE_PHY_SETTING)));

                SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() * 4);
                ScalerTMDSRxSetPhy_EXINT0();
                SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() / 4);

                // Enable Packed Pixel Mode
                RxSetBit(P76_A0_MHL_CTRL_00, ~_BIT1, _BIT1);

                // Check CDR Stable
                if((ScalerTMDSRxCheckCDRStable_EXINT0(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE) || (RXSEL((ScalerMHLRx2DetectClkMode_EXINT0()), (ScalerMHLRx3DetectClkMode_EXINT0())) == _FALSE))// MHL mode need modify
                {
                    RXSEL((SET_TMDS_RX2_CLK_MODE(_TMDS_24BIT_PHY_SETTING)), (SET_TMDS_RX3_CLK_MODE(_TMDS_24BIT_PHY_SETTING)));

                    // TMDS_FREQ(MHz) = GDI_CLK(MHz) * 1024 / CLK_COUNT = GDI_CLK(KHz) * 1024 / (CLK_COUNT * 1024)
                    SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() * 3);
                    ScalerTMDSRxSetPhy_EXINT0();
                    SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() / 3);

                    // Disable Packed Pixel Mode
                    RxSetBit(P76_A0_MHL_CTRL_00, ~_BIT1, 0x00);

                    if((ScalerTMDSRxCheckCDRStable_EXINT0(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE) || (RXSEL((ScalerMHLRx2DetectClkMode_EXINT0()), (ScalerMHLRx3DetectClkMode_EXINT0())) == _FALSE))// MHL Need modify
                    {
                        bMHLFail = _TRUE;
                    }
                }
            }
            else
            {
                RXSEL((SET_TMDS_RX2_CLK_MODE(_TMDS_24BIT_PHY_SETTING)), (SET_TMDS_RX3_CLK_MODE(_TMDS_24BIT_PHY_SETTING)));

                // TMDS_FREQ(MHz) = GDI_CLK(MHz) * 1024 / CLK_COUNT = GDI_CLK(KHz) * 1024 / (CLK_COUNT * 1024)
                SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() * 3);
                ScalerTMDSRxSetPhy_EXINT0();
                SET_INPUT_PIXEL_CLK(GET_INPUT_PIXEL_CLK() / 3);

                // Disable Packed Pixel Mode
                RxSetBit(P76_A0_MHL_CTRL_00, ~_BIT1, 0x00);

                if((ScalerTMDSRxCheckCDRStable_EXINT0(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE) || (RXSEL((ScalerMHLRx2DetectClkMode_EXINT0()), (ScalerMHLRx3DetectClkMode_EXINT0())) == _FALSE))// MHL Need modify
                {
                    bMHLFail = _TRUE;
                }
            }
        }
        else
        {
            RXSEL((SET_TMDS_RX2_CLK_MODE(_TMDS_24BIT_PHY_SETTING)), (SET_TMDS_RX3_CLK_MODE(_TMDS_24BIT_PHY_SETTING)));

            ScalerTMDSRxSetPhy_EXINT0();

            // Disable Packed Pixel Mode
            RxSetBit(P76_A0_MHL_CTRL_00, ~_BIT1, 0x00);

            // Set HDMI/DVI switch to Auto Mode
            RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR);
            RxSetBit(P71_CA_HDMI_DP, ~(_BIT7 | _BIT6 | _BIT3), 0x00);
        }
#else
        ScalerTMDSRxSetPhy_EXINT0();
        AWTO_PHY_MARK();
        {
            BYTE ucCdr = ScalerTMDSRxCheckCDRStable_EXINT0(isr_g_usTMDSRxClkCount[RX_CUR]);

            AWTO_PHY_END(ucCdr);
        }
#endif
    }

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(bMHLFail == _FALSE)
#endif
    {
        // Set Upper Bound (allow 1/64 freq shift)
        RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, (HIBYTE(isr_g_usTMDSRxPhyCount[RX_CUR] + (isr_g_usTMDSRxPhyCount[RX_CUR] >> 6)) & 0x7F));
        RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(isr_g_usTMDSRxPhyCount[RX_CUR] + (isr_g_usTMDSRxPhyCount[RX_CUR] >> 6)));

        // Set Lower bound
        RxSetByte(P71_EA_HDMI_FREQDET_LOWER_M, (HIBYTE(isr_g_usTMDSRxPhyCount[RX_CUR] - (isr_g_usTMDSRxPhyCount[RX_CUR] >> 6)) & 0x7F));
        RxSetByte(P71_EB_HDMI_FREQDET_LOWER_L, LOBYTE(isr_g_usTMDSRxPhyCount[RX_CUR] - (isr_g_usTMDSRxPhyCount[RX_CUR] >> 6)));

        // Reset Color Depth to 8 Bits
        SET_COLOR_DEPTH(_COLOR_DEPTH_8_BITS);

        RXSEL((SET_TMDS_RX2_PHY_SET()), (SET_TMDS_RX3_PHY_SET()));
    }

#if(_D2_HDMI_2_0_SUPPORT == _ON)
    // Clear CED Lock Transition Flag
    RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

    // Set HDMI 2.0 Character Error Detection Function Lock Transition Error Boundary
    RxSetBit(P71_14_HDMI_CTRL_14, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (GET_INPUT_PIXEL_CLK() / 10) >> 8);
    RxSetByte(P71_15_HDMI_CTRL_15, (GET_INPUT_PIXEL_CLK() / 10));

    // Enable Character Error Detection Function & Valid Flag
    RxSetBit(P71_0B_HDMI_CTRL_0B, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2));

    // Enable Character Error Detction Function Lock Transition IRQ
    RxSetBit(P71_18_HDMI_CTRL_18, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));
#endif


    RxSetByte(P71_C8_HDMI_APC, ucApc);
    RxSetByte(P71_C9_HDMI_AP, ucAp);
    EX0 = ucEx0;
}
void ScalerTMDSRx2PhySetDeferred(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxPhySetDeferred();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS Interrupt Process (EXINT0 Only)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxIntHandler_EXINT0(void)
{
#if(_D2_HDMI_2_0_SUPPORT == _ON)
    BYTE pucBackUp[4];
#else
    BYTE pucBackUp[2];
#endif

    WORD usPixClk;
    WORD usCount = 0;

    pucBackUp[0] = RxGetByte(P71_C9_HDMI_AP);
    pucBackUp[1] = RxGetByte(P71_C8_HDMI_APC);

    // Set CA Port non-auto increase
    RxSetBit(P71_C8_HDMI_APC, ~_BIT0, 0x00);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
    pucBackUp[2] = RxGetByte(P71_39_HDMI_CTRL_39);
    pucBackUp[3] = RxGetByte(P71_38_HDMI_CTRL_38);
#endif

    // Freq. Stable Into IRQ
    if(((RxGetByte(P71_EF_HDMI_ERROR_TH) & 0xC0) == 0xC0) && (isr_g_ucTMDSRxClkIRQ[RX_CUR] == _ENABLE))
    {
        // Disable Freq Stable IRQ
        RxSetBit(P71_EF_HDMI_ERROR_TH, ~(_BIT7 | _BIT6), _BIT6);
#if(_AWTO_PS_WAKE == _ON)
        isr_g_pucAwtoClkEv[RX_CUR]++;                   // #323 port status: clock stable event
#endif

#if(_D2_HDMI_2_0_SUPPORT == _ON)
        // Set SCDC Port Clock Detected
        RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
        RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, _BIT0);

        // Disable Reset HDMI/DVI Format
        RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), 0x00);

        // Set SCDC Port Status Update Flag
        RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_10_PORT_PAGE71_HDMI_SCDC_10);

        if(RxGetBit(P71_3A_HDMI_CTRL_3A, _BIT0) == 0x00)
        {
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, _BIT0);

            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // FW Manual Enable Read Request
                RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);

                // Enable Read Request Done IRQ
                RxSetBit(P71_1F_HDMI_CTRL_1F, ~_BIT3, _BIT3);
            }
        }
#endif

        // Pop up Counter Value
        RxSetBit(P71_EC_HDMI_FREQDET_STABLE, ~_BIT7, _BIT7);

        usCount = (WORD)(((RxGetByte(P71_ED_HDMI_FREQDET_RESULT_M) & 0x7F) << 8) | RxGetByte(P71_EE_HDMI_FREQDET_RESULT_L));

        // TMDS_FREQ(MHz) = GDI_CLK(MHz) * CLK_COUNT * _TMDS_MEASURE_CLOCK_DIVIDER / _TMDS_MEASURE_CLOCK_COUNTER
        usPixClk = (((DWORD)_GDI_CLK_KHZ * usCount + 50000) / 100000);   // snapshot: the handlers run one at a time
        SET_INPUT_PIXEL_CLK(usPixClk);

#if(_D2_HDMI_2_0_SUPPORT == _ON)

        // If SCDC tell 1:40 then set High speed flag
        if((usPixClk >= 850) && (usPixClk <= 1500))
        {
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_20_PORT_PAGE71_HDMI_SCDC_20);

            if((RxGetBit(P71_3A_HDMI_CTRL_3A, _BIT1) == _BIT1) || AWTO_TMDS_MEM_USE((AWTO_TMDS_MEM_D2 << RX_CUR)))
            {
                RXSEL((SET_TMDS_RX2_HIGH_SPEED_MODE()), (SET_TMDS_RX3_HIGH_SPEED_MODE()));
            }
        }

        if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _TRUE)
        {
            usPixClk *= 4;
            SET_INPUT_PIXEL_CLK(usPixClk);
        }
#endif

        if(usPixClk > 3000)
        {
            // Set Input Clock Measure Divider = /2
            RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
            RxSetBit(P71_CA_HDMI_DP, ~_BIT6, _BIT6);
        }
        else
        {
            // Set Input Clock Measure Divider = /1
            RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
            RxSetBit(P71_CA_HDMI_DP, ~_BIT6, 0x00);
        }

        // Deferred to ScalerTMDSRx2PhySetDeferred(): the 5.5 ms PHY set-up runs from the main loop
        isr_g_usTMDSRxPhyCount[RX_CUR] = usCount;
        isr_g_usTMDSRxPhyClk[RX_CUR] = usPixClk;
        isr_g_ucTMDSRxPhyPend[RX_CUR] = _TRUE;
    }

    // Freq. Unstable Into IRQ
    if(((RxGetByte(P71_E6_HDMI_FREQDET_CTRL) & 0x06) == 0x06) && (isr_g_ucTMDSRxClkIRQ[RX_CUR] == _ENABLE))
    {
        // Clear Unstable IRQ Flag
        RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT2, _BIT2);

        // Ensure Freq really unstable
        usPixClk = isr_g_usInputPixelClk;
        if((abs(isr_g_usTMDSRxClkCount[RX_CUR] - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS)) > (isr_g_usTMDSRxClkCount[RX_CUR] >> 6)) ||
           (abs(usPixClk - ((GET_TMDS_OFFLINE_MEASURE_CLK() << 3) / GET_COLOR_DEPTH())) > (usPixClk >> 6)))
        {
            // Set Display M1 output force to background color and free run mode
            ScalerSetBit_EXINT(P0_28_VIDEO_DISPLAY_CONTROL_REG, ~_BIT5, _BIT5);

            // Disable RGB/clock Output to avoid garbage
            RxSetBit(P71_A6_TMDS_OUTCTL, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

#if(_D2_HDMI_2_0_SUPPORT == _ON)

            // Clear Scrambling Detection Flag
            RxSetBit(P71_01_HDMI_CTRL_01, ~_BIT3, _BIT3);

            // Disable Scrambling Status
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_21_PORT_PAGE71_HDMI_SCDC_21);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, 0x00);

            // Disable CED Function
            RxSetBit(P71_0B_HDMI_CTRL_0B, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), 0x00);

            // Pop Up CED Error For Clear Error Counter
            RxSetBit(P71_0C_HDMI_CTRL_0C, ~_BIT7, _BIT7);

            // Disable CED Lock Transition IRQ & Flag
            RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));
            RxSetBit(P71_18_HDMI_CTRL_18, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

            // Clear SCDC Port Status Update Flag & CED Update Flag
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_10_PORT_PAGE71_HDMI_SCDC_10);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~(_BIT1 | _BIT0), 0x00);

            // Clear SCDC Port Status Lock Flag
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

            // Reset HDMI/DVI Format
            RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), _BIT7);
#endif

            // Disable Freq. Unstable IRQ
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00);

            // Set HDMI/DVI switch to Auto Mode
            RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR);
            RxSetBit(P71_CA_HDMI_DP, ~(_BIT7 | _BIT6 | _BIT3), 0x00);

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
            if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
            {
                // Set Upper Bound
                RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));
                RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));

                // Suspend Key Calculation before load key
                RxSetBit(P71_AE_TMDS_RPS, ~_BIT1, 0x00);
            }
            else
#endif
            {
                // Set Upper Bound
                RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
                RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
            }

            // Set Lower bound
            RxSetByte(P71_EA_HDMI_FREQDET_LOWER_M, HIBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));
            RxSetByte(P71_EB_HDMI_FREQDET_LOWER_L, LOBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));

            // Reset Freq. Detect Counter(Toggle)
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, 0x00);
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, _BIT7);

            // Enable Freq. Stable IRQ
            RxSetBit(P71_EF_HDMI_ERROR_TH, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

            RXSEL((CLR_TMDS_RX2_PHY_SET()), (CLR_TMDS_RX3_PHY_SET()));

#if(_D2_HDMI_2_0_SUPPORT == _ON)
            RXSEL((CLR_TMDS_RX2_HIGH_SPEED_MODE()), (CLR_TMDS_RX3_HIGH_SPEED_MODE()));
#endif

#if((_TMDS_HDCP_2_2_SUPPORT == _ON) && ((_D2_INPUT_PORT_TYPE == _D2_HDMI_PORT) || (_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)))
            // Reset Authenticated FSM
            RxSetByte(P2D_28_HDCP_I2C_CTRL_2, 0x01);
            RxSetBit(P2D_29_HDCP_I2C_CTRL_3, ~_BIT6, _BIT6);

            // Cancel HDCP 2.2 Re-Auth Timer Event
            ScalerTimerCancelTimerEvent_EXINT0(RXSEL((_SCALER_TIMER_EVENT_RX2_HDCP2_REAUTH), (_SCALER_TIMER_EVENT_RX3_HDCP2_REAUTH)));
#endif
        }
    }

#if(_D2_HDMI_2_0_SUPPORT == _ON)

    // Detect Source Write Read Request Enable Flag
    if((RxGetBit(P71_25_HDMI_CTRL_25, _BIT3) == _BIT3) && (RxGetBit(P71_26_HDMI_CTRL_26, _BIT3) == _BIT3))
    {
        // Clear Read Request Flag
        RxSetBit(P71_25_HDMI_CTRL_25, ~_BIT3, _BIT3);

        // Set Read Request Enable
        RXSEL((SET_HDMI_2_0_RX2_RR_ENABLE()), (SET_HDMI_2_0_RX3_RR_ENABLE()));

        // Enable Test Read Request HW Auto Mode
        RxSetBit(P71_1C_HDMI_CTRL_1C, ~_BIT1, _BIT1);

        // Enable CED Update Read Request Auto Mode
        RxSetBit(P71_24_HDMI_CTRL_24, ~_BIT0, _BIT0);

        // Enable Read Request Done IRQ
        RxSetBit(P71_1F_HDMI_CTRL_1F, ~_BIT3, _BIT3);
    }

    // Detect CED Channel 2 Lock Transition Flag into IRQ
    if((RxGetBit(P71_17_HDMI_CTRL_17, _BIT2) == _BIT2) && (RxGetBit(P71_18_HDMI_CTRL_18, _BIT2) == _BIT2))
    {
        // Clear Lock Transition Flag
        RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), _BIT2);

        // Detect CED Realtime Flag
        if(RxGetBit(P71_17_HDMI_CTRL_17, _BIT5) == _BIT5)
        {
            // Set CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT3, _BIT3);
        }
        else
        {
            // Clear CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT3, 0x00);
        }

        // Set SCDC Port Status Update Flag
        RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_10_PORT_PAGE71_HDMI_SCDC_10);

        if(RxGetBit(P71_3A_HDMI_CTRL_3A, _BIT0) == 0x00)
        {
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, _BIT0);

            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // FW Manual Enable Read Request
                RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);

                // Enable Read Request Done IRQ
                RxSetBit(P71_1F_HDMI_CTRL_1F, ~_BIT3, _BIT3);
            }
        }
    }

    // Detect CED Channel 1 Lock Transition Flag into IRQ
    if((RxGetBit(P71_17_HDMI_CTRL_17, _BIT1) == _BIT1) && (RxGetBit(P71_18_HDMI_CTRL_18, _BIT1) == _BIT1))
    {
        // Clear Lock Transition Flag
        RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);

        // Detect CED Realtime Flag
        if(RxGetBit(P71_17_HDMI_CTRL_17, _BIT4) == _BIT4)
        {
            // Set CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT2, _BIT2);
        }
        else
        {
            // Clear CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT2, 0x00);
        }

        // Set SCDC Port Status Update Flag
        RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_10_PORT_PAGE71_HDMI_SCDC_10);

        if(RxGetBit(P71_3A_HDMI_CTRL_3A, _BIT0) == 0x00)
        {
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, _BIT0);

            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // FW Manual Enable Read Request
                RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);

                // Enable Read Request Done IRQ
                RxSetBit(P71_1F_HDMI_CTRL_1F, ~_BIT3, _BIT3);
            }
        }
    }

    // Detect CED Channel 0 Lock Transition Flag into IRQ
    if((RxGetBit(P71_17_HDMI_CTRL_17, _BIT0) == _BIT0) && (RxGetBit(P71_18_HDMI_CTRL_18, _BIT0) == _BIT0))
    {
        // Clear Lock Transition Flag
        RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);

        // Detect CED Realtime Flag
        if(RxGetBit(P71_17_HDMI_CTRL_17, _BIT3) == _BIT3)
        {
            // Set CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT1, _BIT1);
        }
        else
        {
            // Clear CED Lock Flag in SCDC Port
            RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_40_PORT_PAGE71_HDMI_SCDC_40);
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT1, 0x00);
        }

        // Set SCDC Port Status Update Flag
        RxSetByte(P71_39_HDMI_CTRL_39, _P71_3A_PT_10_PORT_PAGE71_HDMI_SCDC_10);

        if(RxGetBit(P71_3A_HDMI_CTRL_3A, _BIT0) == 0x00)
        {
            RxSetBit(P71_3A_HDMI_CTRL_3A, ~_BIT0, _BIT0);

            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // FW Manual Enable Read Request
                RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);

                // Enable Read Request Done IRQ
                RxSetBit(P71_1F_HDMI_CTRL_1F, ~_BIT3, _BIT3);
            }
        }
    }

    // Read Request Done into IRQ
    if((RxGetBit(P71_1F_HDMI_CTRL_1F, _BIT3) == _BIT3) && (RxGetBit(P71_1C_HDMI_CTRL_1C, _BIT7) == _BIT7))
    {
        // Clear Read Request Done Flag
        RxSetBit(P71_1C_HDMI_CTRL_1C, ~_BIT7, _BIT7);

        // Read Request Outcome Processing
        ScalerTMDSRxReadRequestProc_EXINT0(RxGetByte(P71_1C_HDMI_CTRL_1C) & 0x70);
    }

    // Detect HDMI HPD Rising to Falling into IRQ
#if(_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON)
    if(RxGetBit(P71_23_HDMI_CTRL_23, (_BIT6 | _BIT1)) == (_BIT6 | _BIT1))
    {
        // Clear HPD IRQ Flag
        RxSetBit(P71_23_HDMI_CTRL_23, ~_BIT1, _BIT1);

        if(RxGetBit(P71_23_HDMI_CTRL_23, (_BIT2 | _BIT0)) == 0x00)
        {
            // Clear All Source Write SCDC Port Register
            RxSetBit(P71_38_HDMI_CTRL_38, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));

            // Clear HDMI 2.0 Read Request Enable
            RXSEL((CLR_HDMI_2_0_RX2_RR_ENABLE()), (CLR_HDMI_2_0_RX3_RR_ENABLE()));

            // Disable Rising to Falling IRQ, Set IRQ Status Falling to Rising edge IRQ
            RxSetBit(P71_23_HDMI_CTRL_23, ~(_BIT6 | _BIT2 | _BIT1), (_BIT2 | _BIT1));

            // Enable Falling to Rising edge IRQ
            RxSetBit(P71_23_HDMI_CTRL_23, ~_BIT6, _BIT6);

            /*
            // Disable Test Read Request HW Auto Mode
            ScalerSetBit_EXINT(P71_1C_HDMI_CTRL_1C, ~_BIT1, 0x00);

            // Disable CED Update Read Request Auto Mode
            ScalerSetBit_EXINT(P71_24_HDMI_CTRL_24, ~_BIT0, 0x00);

            // Disable Character Error Detection Function
            ScalerSetBit_EXINT(P71_0B_HDMI_CTRL_0B, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), 0x00);

            // Disable Lock Transition IRQ
            ScalerSetBit_EXINT(P71_18_HDMI_CTRL_18, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

            ScalerSetBit_EXINT(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

            // Detect 3 Channel CDR Stable
            if((bit)ScalerTMDSRx2CheckCDRStable_EXINT(isr_g_usTMDSRx2ClkCount) == _TRUE)
            {
                // Disable Rising to Falling IRQ, Set IRQ Status Falling to Rising edge IRQ
                ScalerSetBit_EXINT(P71_23_HDMI_CTRL_23, ~(_BIT6 | _BIT2 | _BIT1), (_BIT2 | _BIT1));

                // Enable Falling to Rising edge IRQ
                ScalerSetBit_EXINT(P71_23_HDMI_CTRL_23, ~_BIT6, _BIT6);
            }
            */
        }
        else
        {
            /*
            // Enable CED Function
            ScalerSetBit_EXINT(P71_0B_HDMI_CTRL_0B, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2));

            // Enable CED Lock Transition IRQ
            ScalerSetBit_EXINT(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

            ScalerSetBit_EXINT(P71_18_HDMI_CTRL_18, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

            // Enable SCDC Module
            ScalerSetBit_EXINT(P71_19_HDMI_CTRL_19, ~_BIT7, _BIT7);
            */

            // Disable Falling to Rising IRQ, Set IRQ Status Rising to Falling edge IRQ
            RxSetBit(P71_23_HDMI_CTRL_23, ~(_BIT6 | _BIT2 | _BIT1), _BIT1);

            // Enable Rising to edge IRQ
            RxSetBit(P71_23_HDMI_CTRL_23, ~_BIT6, _BIT6);
        }
    }
#endif // End of #if(_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON)

#endif // End of #if(_D2_HDMI_2_0_SUPPORT == _ON)

    // HDCP 1.4 Write Aksv IRQ have been Received
    if((RxGetBit(P71_A9_TMDS_ABC0, _BIT7) == _BIT7) && (RxGetBit(P71_AA_TMDS_ABC1, _BIT4) == _BIT4))
    {
        // clear AKSV flag
        RxSetBit(P71_A9_TMDS_ABC0, ~(_BIT7 | _BIT6 | _BIT5 | _BIT2), _BIT7);

        // SET KEY ready bit 1
        RxSetBit(P71_AE_TMDS_RPS, ~_BIT1, _BIT1);

#if(_TMDS_HDCP_2_2_SUPPORT == _ON)
        // Enable HDCP 1.4 Module
        RxSetBit(P71_C0_HDCP_CR, ~(_BIT7 | _BIT0), (_BIT7 | _BIT0));

        // Disable HDCP 2 Function
        RxSetBit(P2D_26_HDCP_I2C_CTRL_0, ~_BIT7, 0x00);
#endif
    }

#if(_AUDIO_SUPPORT == _ON)
    // Detect if Auido Sampling is Changed
    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET);
    if(RxGetBit(P71_CA_HDMI_DP, (_BIT3 | _BIT1)) == (_BIT3 | _BIT1))
    {
        // Clear Auido Sampling Change Flag
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET);
        RxSetBit(P71_CA_HDMI_DP, ~_BIT1, _BIT1);

        // Disable FIFO Boundary Tracking, Disable Trend Tracking
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR);
        RxSetBit(P71_CA_HDMI_DP, ~(_BIT3 | _BIT2), 0x00);

        // Set Double Buffer bit
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR);
        RxSetBit(P71_CA_HDMI_DP, ~_BIT4, _BIT4);

        // Reload D __code
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0);
        RxSetBit(P71_CA_HDMI_DP, ~_BIT6, _BIT6);
        RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0);
        RxSetBit(P71_CA_HDMI_DP, ~_BIT6, 0x00);
    }
#endif

    // Clear IRQ Pending Flag
    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_60_PORT_PAGE71_HDMI_INTCR);
    RxSetBit(P71_CA_HDMI_DP, ~_BIT7, _BIT7);

    RxSetByte(P71_C8_HDMI_APC, pucBackUp[1]);
    RxSetByte(P71_C9_HDMI_AP, pucBackUp[0]);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
    RxSetByte(P71_38_HDMI_CTRL_38, pucBackUp[3]);
    RxSetByte(P71_39_HDMI_CTRL_39, pucBackUp[2]);
#endif
}
void ScalerTMDSRx2IntHandler_EXINT0(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxIntHandler_EXINT0();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : Check CDR Locked
// Input Value  : Measured Clk Count to be compared
// Output Value : _TRUE => Stable
//--------------------------------------------------
bit ScalerTMDSRxCheckCDRStable(WORD usClkCount)
{
    // Disable INT Clock Check
    isr_g_ucTMDSRxClkIRQ[RX_CUR] = _DISABLE;

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        switch(RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())))
        {
            // Check if Packed Pixel Mode
            case _TMDS_MHL_PPMODE_PHY_SETTING:

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - (ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED) * 4)) > (usClkCount >> 6))
                {
                    DebugMessageRx2("R Channel CDR Unstable", ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED));

                    // Enable INT Clock Check
                    isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                    return _FALSE;
                }

                break;

            // Check if 24 Bit Mode
            case _TMDS_24BIT_PHY_SETTING:

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - (ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED) * 3)) > (usClkCount >> 6))
                {
                    DebugMessageRx2("R Channel CDR Unstable", ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED));

                    // Enable INT Clock Check
                    isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                    return _FALSE;
                }

                break;

            default:

                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
                break;
        }
    }
    else
#endif // End of #if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    {
#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _TRUE)
        {
            // Check Current Measured Freq. is the same as previously locked
            if(abs(usClkCount - (ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED) * 4)) > (usClkCount >> 6))
            {
                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }

            if(abs(usClkCount - (ScalerTMDSRxMeasureClk(_CLK_SOURCE_BLUE) * 4)) > (usClkCount >> 6))
            {
                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }

            if(abs(usClkCount - (ScalerTMDSRxMeasureClk(_CLK_SOURCE_GREEN) * 4)) > (usClkCount >> 6))
            {
                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }
        }
        else
#endif
        {
            // Check Current Measured Freq. is the same as previously locked
            if(abs(usClkCount - ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED)) > (usClkCount >> 6))
            {
                DebugMessageRx2("R Channel CDR Unstable", ScalerTMDSRxMeasureClk(_CLK_SOURCE_RED));

                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }

            if(abs(usClkCount - ScalerTMDSRxMeasureClk(_CLK_SOURCE_BLUE)) > (usClkCount >> 6))
            {
                DebugMessageRx2("B Channel CDR Unstable", ScalerTMDSRxMeasureClk(_CLK_SOURCE_BLUE));

                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }

            if(abs(usClkCount - ScalerTMDSRxMeasureClk(_CLK_SOURCE_GREEN)) > (usClkCount >> 6))
            {
                DebugMessageRx2("G Channel CDR Unstable", ScalerTMDSRxMeasureClk(_CLK_SOURCE_GREEN));

                // Enable INT Clock Check
                isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

                return _FALSE;
            }
        }
    }

    // Enable INT Clock Check
    isr_g_ucTMDSRxClkIRQ[RX_CUR] = _ENABLE;

    return _TRUE;
}
bit ScalerTMDSRx2CheckCDRStable(WORD usClkCount)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxCheckCDRStable(usClkCount);
    RX_CUR = ucOld;

    return xRet;
}

//--------------------------------------------------
// Description  : Check CDR Locked (EXINT0 Only)
// Input Value  : Measured Clk Count to be compared
// Output Value : _TRUE => Stable
//--------------------------------------------------
BYTE ScalerTMDSRxCheckCDRStable_EXINT0(WORD usClkCount)
{
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        switch(RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())))
        {
            // Check if Packed Pixel Mode
            case _TMDS_MHL_PPMODE_PHY_SETTING:

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS)) > (usClkCount >> 6))
                {
                    return _FALSE;
                }

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - (ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_RED) * 4)) > (usClkCount >> 6))
                {
                    return _FALSE;
                }

                break;

            // Check if 24 Bit Mode
            case _TMDS_24BIT_PHY_SETTING:

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS)) > (usClkCount >> 6))
                {
                    return _FALSE;
                }

                // Check Current Measured Freq. is the same as previously locked
                if(abs(usClkCount - (ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_RED) * 3)) > (usClkCount >> 6))
                {
                    return _FALSE;
                }

                break;

            default:

                return _FALSE;
                break;
        }
    }
    else
#endif // End of #if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    {
#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _TRUE)
        {
            // Check Current Measured Freq. is the same as previously locked
            if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - (ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_RED) * 4)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - (ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_BLUE) * 4)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - (ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_GREEN) * 4)) > (usClkCount >> 6))
            {
                return _FALSE;
            }
        }
        else
#endif
        {
            // Check Current Measured Freq. is the same as previously locked
            if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_TMDS)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_RED)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_BLUE)) > (usClkCount >> 6))
            {
                return _FALSE;
            }

            if(abs(usClkCount - ScalerTMDSRxMeasureClk_EXINT0(_CLK_SOURCE_GREEN)) > (usClkCount >> 6))
            {
                return _FALSE;
            }
        }
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : Measure Clk
// Input Value  : Clk Source to be measured
// Output Value : Measured Clk Count
//--------------------------------------------------
WORD ScalerTMDSRxMeasureClk(BYTE ucMeasureClk)
{
    BYTE ucDelayCount = 0;

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        // Enable Rx_EN (Lane0,3)
        RxSetBit(P7B_1A_CMU_00, ~(_BIT7 | _BIT4), (_BIT7 | _BIT4));
    }
    else
#endif
    {
        // Enable Rx_EN (Lane3)
        RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);
    }

    // Disable Measure for Reset Measure Window
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0, ~(_BIT5 | _BIT4 | _BIT3), 0x00);

    // Select reference clk to Xtal Clk and measure clk
    RxSetBit(P71_AD_TMDS_CPS, ~(_BIT6 | _BIT5 | _BIT4), ((ucMeasureClk << 5) | _BIT4));

    // Start Measure
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0, ~(_BIT5 | _BIT4 | _BIT3), _BIT3);

    // Delay at least 40us at Xtal = 27MHz
    for(ucDelayCount = 0; ucDelayCount <= 8; ucDelayCount++)
    {
        DELAY_5US();

        if((ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0, _BIT3)) == 0x00)
        {
            break;
        }
    }

    ScalerGetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0, 2, &pData[0], _AUTOINC);

    return ((WORD)(pData[0] & 0x07) << 8) | pData[1];
}

//--------------------------------------------------
// Description  : Measure Clk (EXINT0 Only)
// Input Value  : Clk Source to be measured
// Output Value : Measured Clk Count
//--------------------------------------------------
WORD ScalerTMDSRxMeasureClk_EXINT0(BYTE ucMeasureClk)
{
    BYTE ucDelayCount = 0;
    WORD usClkCount = 0;
    BYTE ucBackUp = 0;

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        // Enable Rx_EN (Lane0,3)
        RxSetBit(P7B_1A_CMU_00, ~(_BIT7 | _BIT4), (_BIT7 | _BIT4));
    }
    else
#endif
    {
        // Enable Rx_EN (Lane3)
        RxSetBit(P7B_1A_CMU_00, ~_BIT7, _BIT7);
    }

    // Disable Measure for Reset Measure Window
    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
    RxSetBit(P71_CA_HDMI_DP, ~(_BIT5 | _BIT4 | _BIT3), 0x00);

    // Select reference clk to Xtal Clk and measure clk
    RxSetBit(P71_AD_TMDS_CPS, ~(_BIT6 | _BIT5 | _BIT4), ((ucMeasureClk << 5) | _BIT4));

    ucBackUp = RxGetByte(P71_C8_HDMI_APC);

    // Set CA Port non-auto increase
    RxSetBit(P71_C8_HDMI_APC, ~_BIT0, 0x00);

    // Start Measure
    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
    RxSetBit(P71_CA_HDMI_DP, ~(_BIT5 | _BIT4 | _BIT3), _BIT3);

    // Delay at least 40us at Xtal = 27MHz
    for(ucDelayCount = 0; ucDelayCount <= 8; ucDelayCount++)
    {
        DELAY_5US_EXINT();

        if((RxGetBit(P71_CA_HDMI_DP, _BIT3)) == 0x00)
        {
            break;
        }
    }

    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0);
    usClkCount = ((WORD)(RxGetByte(P71_CA_HDMI_DP) & 0x07) << 8);

    RxSetByte(P71_C9_HDMI_AP, _P71_CA_PT_29_PORT_PAGE71_HDMI_NTX1024TR1);
    usClkCount = usClkCount | RxGetByte(P71_CA_HDMI_DP);

    RxSetByte(P71_C8_HDMI_APC, ucBackUp);

    return usClkCount;
}

//--------------------------------------------------
// Description  : Set Back Ground Color
// Input Value  : Current Color Space
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxSetPorchColor(EnumColorSpace enumColorFormat)
{
    // Manual Set Background Color Enable
    RxSetBit(P71_B9_TMDS_OUT_CTRL, ~_BIT7, 0x00);

    if((enumColorFormat == _COLOR_SPACE_YCBCR444) || (enumColorFormat == _COLOR_SPACE_YCBCR422))
    {
        RxSetByte(P71_BA_TMDS_ROUT_HIGH_BYTE, 0x80);
        RxSetByte(P71_BB_TMDS_ROUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BC_TMDS_GOUT_HIGH_BYTE, 0x10);
        RxSetByte(P71_BD_TMDS_GOUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BE_TMDS_BOUT_HIGH_BYTE, 0x80);
        RxSetByte(P71_BF_TMDS_BOUT_LOW_BYTE, 0x00);
    }
#if(_HDMI_2_0_YCBCR420_SUPPORT == _ON)
    else if(enumColorFormat == _COLOR_SPACE_YCBCR420)
    {
        RxSetByte(P71_BA_TMDS_ROUT_HIGH_BYTE, 0x10);
        RxSetByte(P71_BB_TMDS_ROUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BC_TMDS_GOUT_HIGH_BYTE, 0x10);
        RxSetByte(P71_BD_TMDS_GOUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BE_TMDS_BOUT_HIGH_BYTE, 0x80);
        RxSetByte(P71_BF_TMDS_BOUT_LOW_BYTE, 0x00);
    }
#endif
    else
    {
        RxSetByte(P71_BA_TMDS_ROUT_HIGH_BYTE, 0x00);
        RxSetByte(P71_BB_TMDS_ROUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BC_TMDS_GOUT_HIGH_BYTE, 0x00);
        RxSetByte(P71_BD_TMDS_GOUT_LOW_BYTE, 0x00);
        RxSetByte(P71_BE_TMDS_BOUT_HIGH_BYTE, 0x00);
        RxSetByte(P71_BF_TMDS_BOUT_LOW_BYTE, 0x00);
    }
}
void ScalerTMDSRx2SetPorchColor(EnumColorSpace enumColorFormat)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxSetPorchColor(enumColorFormat);
    RX_CUR = ucOld;
}

#if(_D2_HDMI_SUPPORT == _ON)
#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
//--------------------------------------------------
// Description  : Set Deep Color PLL
// Input Value  : usTMDSClkCount, ucColorDepth
// Output Value : None
//--------------------------------------------------
bit ScalerTMDSRxHdmiSetDeepColorPll(WORD usTMDSClkCount, BYTE ucColorDepth)
{
    DWORD ulTMDSClkValue = 0;
    WORD usM = 0;
    BYTE ucN = 0;
    BYTE ucDivS = 0;
    BYTE ucFactor = 0;

#if((_D2_HDMI_2_0_SUPPORT == _ON) && (_HDMI_2_0_YCBCR420_SUPPORT == _ON))
    BYTE ucRatio = 1;
#endif

    ////////////////////////////////////////////////////////////////////////////////////////////////
    // Fin = TMDS_clk
    // Fref = Fin / N
    // Fvco = Fin * M / N
    // Freq = Fvco / Divs
    //
    // Restriction
    // A. BW = Kvco * Icp * R / (M * 2pi) = 700k (Band10 Kvco = 1880), R = 13k)
    // B. 300MHz < Fvco < 600MHz
    // C. (Fin / N) >= 10 * BW --> (Fin / N) >= 7MHz
    // D. YCbCr 420, Ratio = 2, other case Ratio = 1
    //
    // note 1.   According A, Icp = 2.5 ~ 20 --> 14 <= M <= 111
    // note 2.   According B and note 1. --> 3 <= (Fin / N) <= 42
    // note 3.   According C and note 2. --> 7 <= (Fin / N) <= 42
    // note 4_a. 10bit : (M / N / Divs) = (4 / 5 * Ratio) --> M = N * Divs * (4 / 5 * Ratio), N or Divs: multiple of 5
    // note 4_b. 12bit : (M / N / Divs) = (2 / 3 * Ratio) --> M = N * Divs * (2 / 3 * Ratio), N or Divs: multiple of 3
    // note 4_b. 16bit : (M / N / Divs) = (1 / 2 * Ratio) --> M = N * Divs * (1 / 2 * Ratio), N or Divs: multiple of 2
    ////////////////////////////////////////////////////////////////////////////////////////////////

    // If Measure Divider = /2 then TMDS_CLK x 2, unit:kHz
    if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_28_PORT_PAGE71_HDMI_NTX1024TR0, _BIT6) == _BIT6)
    {
        ulTMDSClkValue = (DWORD)_GDI_CLK_KHZ * 1024 * 2 / usTMDSClkCount;
    }
    else
    {
        ulTMDSClkValue = (DWORD)_GDI_CLK_KHZ * 1024 / usTMDSClkCount;
    }

#if(_D2_HDMI_2_0_SUPPORT == _ON)

    if(RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _TRUE)
    {
        ulTMDSClkValue = (ulTMDSClkValue << 2);
    }

#if(_HDMI_2_0_YCBCR420_SUPPORT == _ON)
    if(GET_COLOR_SPACE() == _COLOR_SPACE_YCBCR420)
    {
        ucRatio = 2;
    }
#endif

#endif

    DebugMessageRx2("TMDS clk", ulTMDSClkValue);
    DebugMessageRx2("Color Depth", ucColorDepth);

    switch(ucColorDepth)
    {
        case _COLOR_DEPTH_10_BITS:

            ucFactor = 5;

            break;

        case _COLOR_DEPTH_12_BITS:

            ucFactor = 3;

            break;

        case _COLOR_DEPTH_16_BITS:

            ucFactor = 2;

            break;

        default:

            return _FALSE;
    }

    // N <= (Fin / 7)
    PDATA_WORD(0) = (ulTMDSClkValue / 7000);

    if(PDATA_WORD(0) < 2)
    {
        return _FALSE;
    }
    else if(PDATA_WORD(0) >= ucFactor)
    {
        // N: Multiple of factor
        PDATA_WORD(0) -= (PDATA_WORD(0) % ucFactor);
    }
    else if(PDATA_WORD(0) > 255)
    {
        // N: Multiple of factor
        PDATA_WORD(0) = 255 - (255 % ucFactor);
    }

    ucN = PDATA_WORD(0);

    // for differenct Divs, find suitable Divs and M
    for(pData[15] = 0; pData[15] <= 254; pData[15] += 2)
    {
        // N or Divs: Multiple of factor
        if(((ucN % ucFactor) == 0x00) || ((pData[15] % ucFactor) == 0x00))
        {
#if((_D2_HDMI_2_0_SUPPORT == _ON) && (_HDMI_2_0_YCBCR420_SUPPORT == _ON))
            usM = (WORD)ucN * ((pData[15] == 0) ? 1 : pData[15]) * (ucFactor - 1) / ucFactor * ucRatio;
#else
            usM = (WORD)ucN * ((pData[15] == 0) ? 1 : pData[15]) * (ucFactor - 1) / ucFactor;
#endif

            // Fvco = Fin * M / N
            PDATA_DWORD(0) = (ulTMDSClkValue * usM / ucN);

            if((PDATA_DWORD(0) >= 300000) && (PDATA_DWORD(0) <= 600000))
            {
                ucDivS = ((pData[15] == 0) ? 1 : pData[15]);
                break;
            }
        }

        if((pData[15] == 254) && (ucDivS == 0))
        {
            DebugMessageRx2("4. PLL Setting Error", 0);
            return _FALSE;
        }
    }

    //////////////////////////////////////////////////////////////////////////////////////////////////
    // Precise formula of Chrage Pump Current depends on DPM, resistor, and band.                   //
    // If VCO band = 'b00, Icp = (700 * M * 2 * pi) / (778 * 0x01C1[7:5]).                          //
    // If VCO band = 'b01, Icp = (700 * M * 2 * pi) / (1340 * 0x01C1[7:5]).                         //
    // If VCO band = 'b10, Icp = (700 * M * 2 * pi) / (1880 * 0x01C1[7:5]).                         //
    // If VCO band = 'b11, Icp = (700 * M * 2 * pi) / (2340 * 0x01C1[7:5]).                         //
    // 700: DPLL max frequency design target is 700MHz; 778: Frequency curve in band00 is 778MHz.   //
    // Assume DPLL_M=0x13, DPM=0x13+2=21; DPN=2; reg_dpll_vcomd='b01; reg_dpll_rs[2:0]='b011;       //
    // Icp = (700 * 21 * 2 * 3.14) / (1340 * 13)                                                    //
    //////////////////////////////////////////////////////////////////////////////////////////////////

    // Set VCO resister = 3b'011(13K), Capacitor = 2b'11(66pF) (Analog DIC suggust)
    RxSetBit(P2D_BE_MN_SCLKG_PLL_CHP, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT6 | _BIT5 | _BIT4 | _BIT3));

    // BW = Kvco * Icp * R / (M * 2pi) = 700k --> Icp = M * BW * 2pi / Kvco / R
    PDATA_WORD(1) = ((DWORD)usM * 700UL * 2 * 314UL * 20) / _PLL_VCO_BAND_10 / ((7 + (RxGetBit(P2D_BE_MN_SCLKG_PLL_CHP, (_BIT7 | _BIT6 | _BIT5)) >> 5) * 2) * 100);
    pData[5] = (PDATA_WORD(1) + 25) / 50;
    pData[5] -= ((pData[5] == 0) ? 0 : 1);

    if(pData[5] > 0x07)
    {
        pData[5] = 0x07;
    }

    DebugMessageRx2("Deep Color Charge Pump icp =", pData[5]);

    // DPPLL Power Down
    RxSetByte(P2D_BD_MN_SCLKG_PLL_PWR, 0x80);

    // Disable M/N Tracking
    RxSetBit(P2D_A7_MN_SCLKG_TRK_CTRL, ~(_BIT7 | _BIT6 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Set PLL Charge Pump Current
    RxSetBit(P2D_BE_MN_SCLKG_PLL_CHP, ~(_BIT2 | _BIT1 | _BIT0), (pData[5] & 0x07));

    // Set VCOMD, phase Swallow Circuit Clock Select, SCLKGSTOP
    RxSetBit(P2D_BF_MN_SCLKG_PLL_WD, ~(0x7F), 0x16);

    // Set DPPLL Div_2 & Div_s
    RxSetByte(P2D_A3_MN_SCLKG_DIVS, (ucDivS >> 1));

    // Set DPPLL Div_O.
    RxSetBit(P2D_BD_MN_SCLKG_PLL_PWR, ~(_BIT1 | _BIT0), (0 & (_BIT1 | _BIT0)));

    // Offset Value Setting
    RxSetByte(P2D_A6_MN_SCLKG_OFFS_L, 0);
    RxSetByte(P2D_A5_MN_SCLKG_OFFS_M, 0);
    RxSetBit(P2D_A4_MN_SCLKG_OFFS_H, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
    RxSetBit(P2D_A7_MN_SCLKG_TRK_CTRL, ~(_BIT1 | _BIT0), 0x00);

    // Enable phase swallow
    RxSetBit(P2D_B8_MN_SCLKG_SDM_CTRL, ~(_BIT5 | _BIT4), _BIT4);

    // Set DPPLL M Code
    RxSetBit(P2D_A0_MN_SCLKG_CTRL, ~(_BIT1 | _BIT0), (HIBYTE(usM - 2) & 0x03));
    RxSetByte(P2D_A1_MN_SCLKG_DIVM, LOBYTE(usM - 2));

    // Set DPPLL N Code
    RxSetByte(P2D_A2_MN_SCLKG_DIVN, (ucN - 2));

    // PLL Input Clock select to Link Clock, Output Clock Select to PLL Clock, Double Buffer.
    RxSetBit(P2D_A0_MN_SCLKG_CTRL, ~(_BIT6 | _BIT5 | _BIT4), (_BIT6 | _BIT4));

    // Load offset value
    RxSetBit(P2D_A4_MN_SCLKG_OFFS_H, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), _BIT7);

    // Double Buffer for M/N Tracking
    RxSetBit(P2D_A0_MN_SCLKG_CTRL, ~_BIT4, _BIT4);

    // DPLL VCORSTB Set to Normal
    RxSetBit(P2D_C0_MN_SCLKG_PLL_INSEL, ~_BIT0, _DPLL_VCORSTB_NORMAL_VALUE);

    // DPLL Power On
    RxSetBit(P2D_BD_MN_SCLKG_PLL_PWR, ~_BIT7, 0x00);

    ScalerTimerDelayXms(2);

    ////////////////////////////////
    // DPPLL VCO Band Calibration //
    ////////////////////////////////

    // Reg DPLL_CMPEN
    RxSetBit(P2D_BD_MN_SCLKG_PLL_PWR, ~_BIT2, _BIT2);

    ScalerTimerDelayXms(2);

    // Reg DPLL_CALLCH
    RxSetBit(P2D_BD_MN_SCLKG_PLL_PWR, ~_BIT3, _BIT3);

    ScalerTimerDelayXms(2);

    // Reg DPLL_CALSW
    RxSetBit(P2D_BD_MN_SCLKG_PLL_PWR, ~_BIT4, _BIT4);

    // Check VCO Band is '10
    if(RxGetBit(P2D_C0_MN_SCLKG_PLL_INSEL, (_BIT5 | _BIT4)) != _BIT5)
    {
        switch(RxGetBit(P2D_C0_MN_SCLKG_PLL_INSEL, (_BIT5 | _BIT4)) >> 4)
        {
            case 00:

                PDATA_WORD(0) = _PLL_VCO_BAND_00;
                break;

            case 01:

                PDATA_WORD(0) = _PLL_VCO_BAND_01;
                break;

            case 10:

                PDATA_WORD(0) = _PLL_VCO_BAND_10;
                break;

            case 11:

                PDATA_WORD(0) = _PLL_VCO_BAND_11;
                break;

            default:
                PDATA_WORD(0) = _PLL_VCO_BAND_10;
                break;
        }

        PDATA_WORD(1) = ((DWORD)usM * 700UL * 2 * 314UL * 20) / PDATA_WORD(0) / ((7 + (RxGetBit(P2D_BE_MN_SCLKG_PLL_CHP, (_BIT7 | _BIT6 | _BIT5)) >> 5) * 2) * 100);

        DebugMessageRx2("4. reset Icp", PDATA_WORD(1));

        pData[5] = (PDATA_WORD(1) + 25) / 50;
        pData[5] -= ((pData[5] == 0) ? 0 : 1);

        if(pData[5] > 0x07)
        {
            pData[5] = 0x07;
        }

        // Set PLL Charge Pump Current
        RxSetBit(P2D_BE_MN_SCLKG_PLL_CHP, ~(_BIT2 | _BIT1 | _BIT0), (pData[5] & 0x07));

        DebugMessageRx2("4. VCO is not band10, reset Icp", pData[5]);
    }

    return _TRUE;
}
bit ScalerTMDSRx2HdmiSetDeepColorPll(WORD usTMDSClkCount, BYTE ucColorDepth)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdmiSetDeepColorPll(usTMDSClkCount, ucColorDepth);
    RX_CUR = ucOld;

    return xRet;
}
#endif // End of #if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)

//--------------------------------------------------
// Description  : Detect HDMI Info Frame
// Input Value  : bWait => Whether to wait then read
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdmiPacketDetect(bit bWait)
{
    if(bWait == _WAIT)
    {
        // Polling 3 frame for detect Packet signals
        if(ScalerTimerPollingFlagProc(130, RXA(P71_CC_HDMI_GPVS), (_BIT6 | _BIT5), _TRUE) == _TRUE)
        {
            // Both GCP & AVI infoframe packet have been received
            if(RxGetBit(P71_CC_HDMI_GPVS, (_BIT6 | _BIT5)) == (_BIT6 | _BIT5))
            {
                RXSEL((SET_HDMI_RX2_GCP_RECEIVED()), (SET_HDMI_RX3_GCP_RECEIVED()));

                RXSEL((SET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));
            }
            // Only AVI infoframe packet have been received
            else if(RxGetBit(P71_CC_HDMI_GPVS, (_BIT6 | _BIT5)) == _BIT5)
            {
                RXSEL((SET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));

                // Polling more time to wait GCP when AVI IF has been received.
                if(ScalerTimerPollingFlagProc(180, RXA(P71_CC_HDMI_GPVS), _BIT6, _TRUE) == _TRUE)
                {
                    RXSEL((SET_HDMI_RX2_GCP_RECEIVED()), (SET_HDMI_RX3_GCP_RECEIVED()));
                }
                else
                {
                    RXSEL((CLR_HDMI_RX2_GCP_RECEIVED()), (CLR_HDMI_RX3_GCP_RECEIVED()));
                }
            }
            // Only GCP Packet have been received
            else if(RxGetBit(P71_CC_HDMI_GPVS, (_BIT6 | _BIT5)) == _BIT6)
            {
                RXSEL((SET_HDMI_RX2_GCP_RECEIVED()), (SET_HDMI_RX3_GCP_RECEIVED()));

                // Polling more time to wait AVI IF when GCP has been received.
                if(ScalerTimerPollingFlagProc(180, RXA(P71_CC_HDMI_GPVS), _BIT5, _TRUE) == _TRUE)
                {
                    RXSEL((SET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));
                }
                else
                {
                    RXSEL((CLR_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));
                }
            }
        }
        // Neither AVI infoframe nor GCP packet received
        else
        {
            RXSEL((CLR_HDMI_RX2_GCP_RECEIVED()), (CLR_HDMI_RX3_GCP_RECEIVED()));

            RXSEL((CLR_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));
        }

#if((_HDMI_FREESYNC_SUPPORT == _ON) || (_HDMI_FREESYNC_II_SUPPORT == _ON))
#if((_HDMI_FREESYNC_SUPPORT == _ON) && (_HDMI_FREESYNC_II_SUPPORT == _OFF) && (_HDMI_FREESYNC_CAPABILITY_SWITCH_METHOD == _MCCS_SWITCH_MODE))
        // Polling 3 frame for detect Packet signals
        if((GET_HDMI_FREESYNC_VCP() == 0x01) && (ScalerTimerPollingDataBitFlagProc(130, RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT7, _TRUE) == _TRUE))
#else
        // Polling 3 frame for detect Packet signals
        if(ScalerTimerPollingDataBitFlagProc(130, RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT7, _TRUE) == _TRUE)
#endif
        {
            RXSEL((SET_TMDS_RX2_SPD_INFO_FRAME_RECEIVED()), (SET_TMDS_RX3_SPD_INFO_FRAME_RECEIVED()));
        }
        else
        {
            RXSEL((CLR_TMDS_RX2_SPD_INFO_FRAME_RECEIVED()), (CLR_TMDS_RX3_SPD_INFO_FRAME_RECEIVED()));
        }
#endif

#if(_HDMI_HDR10_SUPPORT == _ON)
        // Polling 3 frame for detect Packet signals
        if(ScalerTimerPollingDataBitFlagProc(130, RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT6, _TRUE) == _TRUE)
        {
            RXSEL((SET_HDMI_RX2_HDR10_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_HDR10_INFO_FRAME_RECEIVED()));
        }
        else
        {
            RXSEL((CLR_HDMI_RX2_HDR10_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_HDR10_INFO_FRAME_RECEIVED()));
        }
#endif

        // No extra frame wait (was 130 ms): the GCP poll above has seen the packet, the depth is read once and re-checked in TMDSStableDetect; #216

        RXSEL((CLR_HDMI_RX2_PACKET_DETECTING()), (CLR_HDMI_RX3_PACKET_DETECTING()));
    }
    else
    {
        if(RxGetBit(P71_CC_HDMI_GPVS, _BIT6) == _BIT6)
        {
            ScalerTMDSRxHdmiWatchDog(_HDMI_AV_MUTE_WD, _ENABLE);

            RXSEL((SET_HDMI_RX2_GCP_RECEIVED()), (SET_HDMI_RX3_GCP_RECEIVED()));

            // Clear Detection Flag
            RxSetBit(P71_CC_HDMI_GPVS, ~(_BIT6 | _BIT5), _BIT6);
        }
        else
        {
            ScalerTMDSRxHdmiWatchDog(_HDMI_AV_MUTE_WD, _DISABLE);

            RXSEL((CLR_HDMI_RX2_GCP_RECEIVED()), (CLR_HDMI_RX3_GCP_RECEIVED()));
        }

        if(RxGetBit(P71_CC_HDMI_GPVS, _BIT5) == _BIT5)
        {
            // Color Space Auto/ Pixel Repetition auto mode
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_51_PORT_PAGE71_HDMI_ACRCR, ~(_BIT6 | _BIT2), (_BIT6 | _BIT2));

            ScalerTMDSRxHdmiWatchDog(_HDMI_AVI_INFO_VARIATION_WD, _ENABLE);

            RXSEL((SET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));

            // Clear Detection Flag
            RxSetBit(P71_CC_HDMI_GPVS, ~(_BIT6 | _BIT5), _BIT5);
        }
        else
        {
            // Mannal Set Color Space and disable pixel  repetition
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_51_PORT_PAGE71_HDMI_ACRCR, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), 0x00);

            // Disable down sampling
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_50_PORT_PAGE71_HDMI_VCR, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

            // Waiting for Down Sampling Effect
            ScalerTimerDelayXms(20);

            ScalerTMDSRxHdmiWatchDog(_HDMI_AVI_INFO_VARIATION_WD, _DISABLE);

            RXSEL((CLR_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));
        }

#if((_HDMI_FREESYNC_SUPPORT == _ON) || (_HDMI_FREESYNC_II_SUPPORT == _ON))
#if((_HDMI_FREESYNC_SUPPORT == _ON) && (_HDMI_FREESYNC_II_SUPPORT == _OFF) && (_HDMI_FREESYNC_CAPABILITY_SWITCH_METHOD == _MCCS_SWITCH_MODE))
        if((GET_HDMI_FREESYNC_VCP() == 0x01) && (ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT7) == _BIT7))
#else
        if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT7) == _BIT7)
#endif
        {
            RXSEL((SET_TMDS_RX2_SPD_INFO_FRAME_RECEIVED()), (SET_TMDS_RX3_SPD_INFO_FRAME_RECEIVED()));

            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6), _BIT7);
        }
        else
        {
            RXSEL((CLR_TMDS_RX2_SPD_INFO_FRAME_RECEIVED()), (CLR_TMDS_RX3_SPD_INFO_FRAME_RECEIVED()));
        }
#endif

#if(_HDMI_HDR10_SUPPORT == _ON)
        if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT6) == _BIT6)
        {
            RXSEL((SET_HDMI_RX2_HDR10_INFO_FRAME_RECEIVED()), (SET_HDMI_RX3_HDR10_INFO_FRAME_RECEIVED()));

            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6), _BIT6);
        }
        else
        {
            RXSEL((CLR_HDMI_RX2_HDR10_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_HDR10_INFO_FRAME_RECEIVED()));
        }
#endif

        RXSEL((SET_HDMI_RX2_PACKET_DETECTING()), (SET_HDMI_RX3_PACKET_DETECTING()));

        // Activate Packet Detection Event
        ScalerTimerActiveTimerEvent(130, RXSEL((_SCALER_TIMER_EVENT_RX2_TMDS_HDMI_PACKET_DETECT), (_SCALER_TIMER_EVENT_RX3_TMDS_HDMI_PACKET_DETECT)));
    }
}
void ScalerTMDSRx2HdmiPacketDetect(bit bWait)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdmiPacketDetect(bWait);
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : Hdmi Handle AVMute Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdmiAVMuteProc(void)
{
    // if AVMute Has been triggered
    if((RxGetBit(P71_CB_HDMI_SR, _BIT6) == 0x00) && (RxGetBit(P71_A6_TMDS_OUTCTL, (_BIT6 | _BIT5 | _BIT4)) == 0x00))
    {
        // Clear AVMute Flag
        RxSetBit(P71_CB_HDMI_SR, ~_BIT7, _BIT7);

        // Disable AVMute Watch Dog
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT7, 0x00);

        // Enable Video/Audio Output
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_30_PORT_PAGE71_HDMI_AVMCR, ~(_BIT5 | _BIT3), (_BIT5 | _BIT3));

        // Enable RGB Output
        RxSetBit(P71_A6_TMDS_OUTCTL, ~(_BIT6 | _BIT5 | _BIT4), (_BIT6 | _BIT5 | _BIT4));

        // Enable AVMute Watch Dog
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT7, _BIT7);
    }
}
void ScalerTMDSRx2HdmiAVMuteProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdmiAVMuteProc();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : Hdmi Enable Watch Dog
// Input Value  : ucWDType => Watch Dog type, bEnable => Enable watch dog flag
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdmiWatchDog(BYTE ucWDType, bit bEnable)
{
    if(bEnable == _ENABLE)
    {
        if(((ucWDType & _HDMI_AVI_INFO_VARIATION_WD) == _HDMI_AVI_INFO_VARIATION_WD) && (GET_DIGITAL_COLOR_INFO_CHANGE_RESET() == _TRUE))
        {
            if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_41_PORT_PAGE71_HDMI_VWDSR, _BIT0) == 0x00)
            {
                // Clear AVI Info Frame Variation flag
                RxSetBit(P71_CC_HDMI_GPVS, ~(_BIT6 | _BIT5 | _BIT0), _BIT0);

                // Enable Color Space/ Colorimetry Change Detection
                ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_45_PORT_PAGE71_HDMI_PVGCR0, ~(_BIT3 | _BIT0), (_BIT3 | _BIT0));

                // Enable AVI Info Frame Variation Watch Dog
                ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_41_PORT_PAGE71_HDMI_VWDSR, ~_BIT0, _BIT0);
            }
        }

        if((ucWDType & _HDMI_AV_MUTE_WD) == _HDMI_AV_MUTE_WD)
        {
            if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, _BIT7) == 0x00)
            {
                // CLR AVMute Flag
                RxSetBit(P71_CB_HDMI_SR, ~_BIT7, _BIT7);

                // Enable AVMute WD
                ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT7, _BIT7);
            }
        }
    }
    else
    {
        if((ucWDType & _HDMI_AVI_INFO_VARIATION_WD) == _HDMI_AVI_INFO_VARIATION_WD)
        {
            // Disable packet variation Watch Dog
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_41_PORT_PAGE71_HDMI_VWDSR, ~_BIT0, 0x00);

            ScalerSetDataPortByte(RXA(P71_C9_HDMI_AP), _P71_CA_PT_45_PORT_PAGE71_HDMI_PVGCR0, 0x00);

            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_46_PORT_PAGE71_HDMI_PVGCR1, ~_BIT0, 0x00);
        }

        if((ucWDType & _HDMI_AV_MUTE_WD) == _HDMI_AV_MUTE_WD)
        {
            // Disable AV Mute Watch Dog
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT7, 0x00);
        }
    }
}
void ScalerTMDSRx2HdmiWatchDog(BYTE ucWDType, bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdmiWatchDog(ucWDType, bEnable);
    RX_CUR = ucOld;
}

#endif // End of #if(_D2_HDMI_SUPPORT == _ON)

//--------------------------------------------------
// Description  : TMDS Power Saving Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxPowerSavingProc(void)
{
    // Set Power Saving DDC Debounce Counter
    isr_g_usDDCDebounceCnt = _TMDS_DDC_DEBOUNCE_PS;
    ScalerTMDSRxFreqDetectDisable();

    // Switch TMDS Input/Output to Auto
    RxSetBit(P71_A6_TMDS_OUTCTL, ~_BIT7, _BIT7);
    RxSetBit(P71_A7_TMDS_PWDCTL, ~_BIT4, _BIT4);

    // Set Freq. Stable Time: 5 times
    RxSetByte(P71_EC_HDMI_FREQDET_STABLE, 0x05);

    // Set Freq. Shift Offset to Max
    RxSetBit(P71_E7_HDMI_FREQDET_OFFSET, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
    {
        // Set Upper Bound
        RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_MHL_FREQ_PS_UPPER_BOUND));
        RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_MHL_FREQ_PS_UPPER_BOUND));
    }
    else
#endif
    {
        // Set Upper Bound
        RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_FREQ_PS_HIGH_SPEED_UPPER_BOUND));
        RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_FREQ_PS_HIGH_SPEED_UPPER_BOUND));
    }

    // Set Lower Bound
    RxSetByte(P71_EA_HDMI_FREQDET_LOWER_M, HIBYTE(_TMDS_FREQ_PS_LOWER_BOUND));
    RxSetByte(P71_EB_HDMI_FREQDET_LOWER_L, LOBYTE(_TMDS_FREQ_PS_LOWER_BOUND));
}
void ScalerTMDSRx2PowerSavingProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxPowerSavingProc();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS Freq. Detection IRQ Disable and Clear Clock Counter
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxFreqDetectDisable(void)
{
    // Disable TMDS Freq. Detect IRQ
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00);
    RxSetBit(P71_EF_HDMI_ERROR_TH, ~_BIT7, 0x00);

    // Clear TMDS Clk Count
    isr_g_usTMDSRxClkCount[RX_CUR] = 0;

    // Clear PHY SET flag and a pending deferred set-up (IRQ already disabled above)
    isr_g_ucTMDSRxPhyPend[RX_CUR] = _FALSE;
    RXSEL((CLR_TMDS_RX2_PHY_SET()), (CLR_TMDS_RX3_PHY_SET()));

    // Disable HDMI MAC Power
    RxSetBit(P71_A7_TMDS_PWDCTL, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

    // Disable CED Function
    RxSetBit(P71_0B_HDMI_CTRL_0B, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), 0x00);

    // Pop Up CED Error For Clear Error Counter
    RxSetBit(P71_0C_HDMI_CTRL_0C, ~_BIT7, _BIT7);

    // Disable CED Lock Transition IRQ & Flag
    RxSetBit(P71_17_HDMI_CTRL_17, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));
    RxSetBit(P71_18_HDMI_CTRL_18, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

    // Set Read Request 1ms reference clock to internal OSC
    RxSetBit(P71_1A_HDMI_CTRL_1A, ~_BIT3, _BIT3);

    // Set time interval form bus free to Read Request(4.7us~500us)
    RxSetBit(P71_1B_HDMI_CTRL_1B, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | _BIT0));
}
void ScalerTMDSRx2FreqDetectDisable(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxFreqDetectDisable();
    RX_CUR = ucOld;
}

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
#if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)
//--------------------------------------------------
// Description  : TMDS Port Source/Sync Scanning and Setting
// Input Value  : Input Port
// Output Value : Source DVI --> DVI Format
//                Source HDMI --> HDMI Format
//                Source None --> No Stable Sync
//--------------------------------------------------
BYTE ScalerTMDSRxTMDSScanInputPort(BYTE ucInputType)
{
    BYTE ucTMDSType = _SOURCE_NONE;

    BYTE ucTMDSVideoDataType = _TMDS_VIDEO_DATA_NONE;

#if(_D2_HDMI_SUPPORT == _ON)
    WORD usInputPixelClk = 0;
#endif

    ucInputType = ucInputType;

    if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) != _TMDS_HPD_NONE)
    {
        AWTO_SCAN_STAGE(AWTO_SCAN_TMDS_HPD);
        return _SOURCE_NONE;
    }

    // Set-up still pending: SysTMDSRxHandler runs it next pass; scanning now would check CDR with no settle time
    if(isr_g_ucTMDSRxPhyPend[RX_CUR] == _TRUE)
    {
        return _SOURCE_NONE;
    }

    if(RXSEL((GET_TMDS_RX2_PHY_SET()), (GET_TMDS_RX3_PHY_SET())) == _TRUE)
    {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
        {
            // Set DIGITAL_PORT_SWITCH Flag for MHL
            RXSEL((SET_DIGITAL_PORT_SWITCH_TO_D2()), (SET_DIGITAL_PORT_SWITCH_TO_D3()));
        }
#endif

        // Delay for PHY Stable
        ScalerTimerDelayXms(2);

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

#if(_D2_HDMI_2_0_SUPPORT == _ON)

        if(((AWTO_SCAN_STAGE(1), ScalerTMDSRxCheckCDRStable(isr_g_usTMDSRxClkCount[RX_CUR])) == _FALSE) || ((AWTO_SCAN_STAGE(2), ScalerTMDSRxCheckDataDFE()) == _FALSE) ||
           ((RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE) && (RXSEL((ScalerMHLRx2DetectClkMode()), (ScalerMHLRx3DetectClkMode())) == _FALSE)) ||
           ((AWTO_SCAN_STAGE(3), ScalerTMDSRxTMDSVideoDetect(_WAIT)) == _TMDS_VIDEO_DATA_NONE))

#else

        // Detect MHL Mode
        if(((AWTO_SCAN_STAGE(1), ScalerTMDSRxCheckCDRStable(isr_g_usTMDSRxClkCount[RX_CUR])) == _FALSE) || ((AWTO_SCAN_STAGE(2), ScalerTMDSRxCheckDataDFE()) == _FALSE) ||
           ((RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE) && (RXSEL((ScalerMHLRx2DetectClkMode()), (ScalerMHLRx3DetectClkMode())) == _FALSE)))

#endif

#else // Else of #if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

#if(_D2_HDMI_2_0_SUPPORT == _ON)

        if(((AWTO_SCAN_STAGE(1), ScalerTMDSRxCheckCDRStable(isr_g_usTMDSRxClkCount[RX_CUR])) == _FALSE) || ((AWTO_SCAN_STAGE(2), ScalerTMDSRxCheckDataDFE()) == _FALSE) || ((AWTO_SCAN_STAGE(3), ScalerTMDSRxTMDSVideoDetect(_WAIT)) == _TMDS_VIDEO_DATA_NONE))
#else
        if(((AWTO_SCAN_STAGE(1), ScalerTMDSRxCheckCDRStable(isr_g_usTMDSRxClkCount[RX_CUR])) == _FALSE) || ((AWTO_SCAN_STAGE(2), ScalerTMDSRxCheckDataDFE()) == _FALSE))
#endif

#endif // End of #if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

            if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
            {
                // Set Upper Bound
                RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));
                RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_MHL_FREQ_NORMAL_UPPER_BOUND));
            }
            else
#endif
            {
                // Set Upper Bound
                RxSetByte(P71_E8_HDMI_FREQDET_UPPER_M, HIBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
                RxSetByte(P71_E9_HDMI_FREQDET_UPPER_L, LOBYTE(_TMDS_FREQ_NORMAL_HIGH_SPEED_UPPER_BOUND));
            }

            // Set Lower Bound
            RxSetByte(P71_EA_HDMI_FREQDET_LOWER_M, HIBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));
            RxSetByte(P71_EB_HDMI_FREQDET_LOWER_L, LOBYTE(_TMDS_FREQ_NORMAL_LOWER_BOUND));

            // Set Stable Time (0x3F = about 5ms)
            RxSetByte(P71_EC_HDMI_FREQDET_STABLE, 0x3F);

#if(_D2_HDMI_2_0_SUPPORT == _ON)

            AWTO_SCAN_STAGE(AWTO_SCAN_TMDS_LOCK + g_ucAwtoScanStage + ((RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) != 0) ? 3 : 0));    // lock step failed, 1:10 / 1:40 tried
            if((RXSEL((GET_TMDS_RX2_HIGH_SPEED_MODE()), (GET_TMDS_RX3_HIGH_SPEED_MODE())) == _FALSE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) != _TMDS_MHL_MODE)) // HDMI mode
            {
                DebugMessageRx2("TMDS Rx2 First 1:10 set phy not success", 1);

                RXSEL((SET_TMDS_RX2_HIGH_SPEED_MODE()), (SET_TMDS_RX3_HIGH_SPEED_MODE()));
            }
            else
            {
                RXSEL((CLR_TMDS_RX2_HIGH_SPEED_MODE()), (CLR_TMDS_RX3_HIGH_SPEED_MODE()));
            }
#endif
            RXSEL((CLR_TMDS_RX2_PHY_SET()), (CLR_TMDS_RX3_PHY_SET())); AWTO_TMDS_MEM_CLR((AWTO_TMDS_MEM_D2 << RX_CUR));     // a failed try drops the remembered mode

            // Disable Freq. Unstable IRQ
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00);

            // Reset Freq. Detect Counter(Toggle)
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, 0x00);
            RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, _BIT7);

            // Enable Freq. Stable IRQ
            RxSetBit(P71_EF_HDMI_ERROR_TH, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

            return _SOURCE_NONE;
        }

        // Clear RGBHV Flag
        RxSetBit(P71_A4_TMDS_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3));

        // Clear Info Packet SRAM
        RxSetBit(P71_AD_TMDS_CPS, ~_BIT3, _BIT3);
        RxSetBit(P71_AD_TMDS_CPS, ~_BIT3, 0x00);

        // Clear AVI infoframe & GCP packet Detection Flag
        RxSetBit(P71_CC_HDMI_GPVS, ~_BIT6, _BIT6);
        RxSetBit(P71_CC_HDMI_GPVS, ~_BIT5, _BIT5);

#if(_HDMI_FREESYNC_SUPPORT == _ON)
        // Clear DRR flag
        CLR_FREESYNC_ENABLED();
#endif

#if((_HDMI_FREESYNC_SUPPORT == _ON) || (_HDMI_FREESYNC_II_SUPPORT == _ON))
        // Clear SPD infoframe
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6), _BIT7);
#endif

#if(_HDMI_HDR10_SUPPORT == _ON)
        // Clear SPD infoframe
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6), _BIT6);
#endif

        DebugMessageRx2("9. Freq Check Pass => Pixel Clock", GET_INPUT_PIXEL_CLK());
        DebugMessageRx2("7. TMDS Lane0 LE Min", g_pucTMDSRxLEMin[RX_CUR][0]);
        DebugMessageRx2("7. TMDS Lane1 LE Min", g_pucTMDSRxLEMin[RX_CUR][1]);
        DebugMessageRx2("7. TMDS Lane2 LE Min", g_pucTMDSRxLEMin[RX_CUR][2]);
        DebugMessageRx2("7. TMDS Lane0 LE Max", g_pucTMDSRxLEMax[RX_CUR][0]);
        DebugMessageRx2("7. TMDS Lane1 LE Max", g_pucTMDSRxLEMax[RX_CUR][1]);
        DebugMessageRx2("7. TMDS Lane2 LE Max", g_pucTMDSRxLEMax[RX_CUR][2]);

#if(_D2_HDMI_2_0_SUPPORT == _ON)

        // Disable Reset HDMI/DVI Format
        RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), 0x00);

        DebugMessageRx2("HDMI 2.0 Error Boundary set High Byte", RxGetByte(P71_14_HDMI_CTRL_14));
        DebugMessageRx2("HDMI 2.0 Error Boundary set Low Byte", RxGetByte(P71_15_HDMI_CTRL_15));
#endif

        if(ScalerTMDSRxFormatDetect() == _SOURCE_HDMI)
        {
            DebugMessageRx2("Format Detect HDMI", 0x00);

#if(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_BY_INPUT)
            ScalerSetDataPortBit(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, ~_BIT1, _BIT1);
#endif

#if(_HDMI_FROM_DVI_CONNECT == _OFF)
            if(GET_PORT_TYPE(ucInputType) == _PORT_DVI)
            {
                return _SOURCE_NONE;
            }
#endif
            ucTMDSType = _SOURCE_HDMI;
        }
        else
        {
#if(_TMDS_HDCP_FEATURE == _HDCP_FEATURE_BY_INPUT)
            ScalerSetDataPortBit(RXA(P71_C3_HDCP_AP), _P71_C4_PT_40_PORT_PAGE71_BCAPS, ~_BIT1, 0x00);
#endif

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
            if(RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())) == _TMDS_MHL_PPMODE_PHY_SETTING)
            {
                ucTMDSType = _SOURCE_HDMI;
            }
            else
#endif
            {
                ucTMDSType = _SOURCE_DVI;
            }
        }

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        // Mute ASUS Padfone until Source Read Ri Done (Incase of Color Format Error)
        if(((RXSEL((GET_MHL_RX2_ADOPTER_ID_HBYTE()), (GET_MHL_RX3_ADOPTER_ID_HBYTE())) == _ASUS_PADFONE2_ADOPTER_ID_HBYTE) && (RXSEL((GET_MHL_RX2_ADOPTER_ID_LBYTE()), (GET_MHL_RX3_ADOPTER_ID_LBYTE())) == _ASUS_PADFONE2_ADOPTER_ID_LBYTE)) &&
           !(((RxGetBit(P71_A9_TMDS_ABC0, _BIT7) == _BIT7) || (RxGetBit(P71_AE_TMDS_RPS, (_BIT1)) == _BIT1)) && (RxGetBit(P71_A9_TMDS_ABC0, _BIT6) == _BIT6)))
        {
            return _SOURCE_NONE;
        }
#endif

        ucTMDSVideoDataType = ScalerTMDSRxTMDSVideoDetect(_WAIT);

        if(ucTMDSVideoDataType == _TMDS_VIDEO_DATA_DE_ONLY)
        {
            DebugMessageRx2("DE Only Mode", 0x00);
            AWTO_SCAN_STAGE(AWTO_SCAN_TMDS_DE);

#if(_DVI_DE_ONLY_SUPPORT == _ON)
            if(ucTMDSType == _SOURCE_DVI)
            {
                // Enable DE Only Mode
                RxSetBit(P71_A7_TMDS_PWDCTL, ~_BIT7, _BIT7);
            }
            else
            {
                return _SOURCE_NONE;
            }
#else
            return _SOURCE_NONE;
#endif
        }
        else if(ucTMDSVideoDataType == _TMDS_VIDEO_DATA_RGBHV)
        {
            // Enable DE Only Mode
            RxSetBit(P71_A7_TMDS_PWDCTL, ~_BIT7, _BIT7);
        }
        else
        {
            AWTO_SCAN_STAGE(AWTO_SCAN_TMDS_VIDEO);
            return _SOURCE_NONE;
        }

        if(GET_INPUT_PIXEL_CLK() > 3400)
        {
            // [1] De_inverse = 1'b0 --> Adapation Only for Data island Area (Transition Minimum)
            // [0] De_brank_en = 1'b1 --> Enable Blank Function of gdi_de
            RxSetBit(P7B_AF_L0_GDI_DE, ~(_BIT1 | _BIT0), _BIT0);
            RxSetBit(P7B_BF_L1_GDI_DE, ~(_BIT1 | _BIT0), _BIT0);
            RxSetBit(P7B_CF_L2_GDI_DE, ~(_BIT1 | _BIT0), _BIT0);
        }
        else
        {
            // [1] De_inverse = 1'b1 --> Adapation Only for Data Area (Transition Minimum)
            // [0] De_brank_en = 1'b1 --> Enable Blank Function of gdi_de
            RxSetBit(P7B_AF_L0_GDI_DE, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));
            RxSetBit(P7B_BF_L1_GDI_DE, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));
            RxSetBit(P7B_CF_L2_GDI_DE, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));
        }

#if(_D2_HDMI_SUPPORT == _ON)
        if(ucTMDSType == _SOURCE_HDMI)
        {
            // HDMI packet detect --> AVI infoframe & GCP packet
            ScalerTMDSRxHdmiPacketDetect(_WAIT);

            ScalerSyncTMDSRxHdmiVideoSetting();

            SET_COLOR_DEPTH(ScalerTMDSRxHdmiGetColorDepth());

            if((GET_COLOR_DEPTH() != _COLOR_DEPTH_8_BITS) && (GET_COLOR_SPACE() != _COLOR_SPACE_YCBCR422))
            {
                DebugMessageRx2("Deep Color Mode Detected", GET_COLOR_DEPTH());

                // Backup Input Pixel clk
                usInputPixelClk = GET_INPUT_PIXEL_CLK();

                SET_INPUT_PIXEL_CLK((GET_INPUT_PIXEL_CLK() << 3) / GET_COLOR_DEPTH());

                if(ScalerTMDSRxHdmiDeepColorProc(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE)
                {
                    // Restore Input Pixel clk
                    SET_INPUT_PIXEL_CLK(usInputPixelClk);
                    AWTO_SCAN_STAGE(AWTO_SCAN_TMDS_DEEP);

                    return _SOURCE_NONE;
                }

                // Turn On Deep Color Block
                RxSetBit(P71_B5_TMDS_UDC0, ~_BIT7, _BIT7);

                if(GET_COLOR_SPACE() == _COLOR_SPACE_YCBCR420)
                {
                    // HDMI Output Div2 Enable
                    RxSetBit(P71_AD_TMDS_CPS, ~_BIT7, _BIT7);
                }
                else
                {
                    // HDMI Output Div2 Disable
                    RxSetBit(P71_AD_TMDS_CPS, ~_BIT7, 0x00);
                }
            }
            else
            {
                // Turn off Deep Color Block
                RxSetBit(P71_B5_TMDS_UDC0, ~_BIT7, 0x00);

                // HDMI Output Div2 Disable
                RxSetBit(P71_AD_TMDS_CPS, ~_BIT7, 0x00);
            }

#if(_HDMI_FREESYNC_SUPPORT == _ON)
            if(RXSEL((GET_HDMIRX2_AMD_SPD_INFO(_SPD_INFO_FREESYNC_SUPPORT)), (GET_HDMIRX3_AMD_SPD_INFO(_SPD_INFO_FREESYNC_SUPPORT))) == _ENABLE)
            {
                SET_HDMI_FREESYNC_ENABLED();

                // Get SPD Free Sync Vfreq Max
                g_usFREESYNCVFreq_max = (WORD)RXSEL((GET_HDMIRX2_AMD_SPD_INFO(_SPD_INFO_FREESYNC_MAX_VFREQ)), (GET_HDMIRX3_AMD_SPD_INFO(_SPD_INFO_FREESYNC_MAX_VFREQ))) * 10;
                g_usFREESYNCVFreq_min = (WORD)RXSEL((GET_HDMIRX2_AMD_SPD_INFO(_SPD_INFO_FREESYNC_MIN_VFREQ)), (GET_HDMIRX3_AMD_SPD_INFO(_SPD_INFO_FREESYNC_MIN_VFREQ))) * 10;

                // Disable DE Only Mode
                RxSetBit(P71_A7_TMDS_PWDCTL, ~_BIT7, 0x00);
            }
#endif
        }
        else
        {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
            // Guard Band reference disable for __data remapping
            RxSetBit(P76_B2_MHL_CTRL_12, ~_BIT7, 0x00);
#endif

            RXSEL((CLR_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (CLR_HDMI_RX3_AVI_INFO_FRAME_RECEIVED()));

            RXSEL((CLR_HDMI_RX2_GCP_RECEIVED()), (CLR_HDMI_RX3_GCP_RECEIVED()));

            // Disable All WD when DVI
            ScalerTMDSRxHdmiWatchDog((_HDMI_AVI_INFO_VARIATION_WD | _HDMI_AV_MUTE_WD), _DISABLE);

            ScalerTMDSRxDviVideoSetting();

            SET_COLOR_DEPTH(_COLOR_DEPTH_8_BITS);

            // Turn off Deep Color Block
            RxSetBit(P71_B5_TMDS_UDC0, ~_BIT7, 0x00);
        }
#else

        ScalerTMDSRxDviVideoSetting();

        SET_COLOR_DEPTH(_COLOR_DEPTH_8_BITS);

        // Turn off Deep Color Block
        RxSetBit(P71_B5_TMDS_UDC0, ~_BIT7, 0x00);
#endif

        // Enable Video Output
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_30_PORT_PAGE71_HDMI_AVMCR, ~_BIT3, _BIT3);
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_80_PORT_PAGE71_HDMI_DPC_SET0, ~_BIT7, _BIT7);

        // Enable RGB Clk Output
        RxSetBit(P71_A6_TMDS_OUTCTL, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT6 | _BIT5 | _BIT4 | _BIT3));

        // solve philip DVD issue
        if(RxGetBit(P7B_E4_GAIN_3, _BIT1) == _BIT1)
        {
            // Disable LE, Vth, Tap0~4 Adaptation
            RxSetByte(P7B_A1_L0_DFE_EN_2, 0x00);
            RxSetByte(P7B_B1_L1_DFE_EN_2, 0x00);
            RxSetByte(P7B_C1_L2_DFE_EN_2, 0x00);

            // [1] reg_en_eqen_manual_l0 = 1'b0
            RxSetBit(P7B_12_ANA_CDR, ~_BIT1, 0x00);

            // Enable Sumamp High Gain Mode
            RxSetBit(P7B_1D_CMU_03, ~_BIT4, _BIT4);
        }

        return ucTMDSType;
    }

    return _SOURCE_NONE;
}
BYTE ScalerTMDSRx2TMDSScanInputPort(BYTE ucInputType)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxTMDSScanInputPort(ucInputType);
    RX_CUR = ucOld;

    return xRet;
}
#endif // End of #if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)

//--------------------------------------------------
// Description  : Detect TMDS Format
// Input Value  : None
// Output Value : Return DVI or HDMI format
//--------------------------------------------------
BYTE ScalerTMDSRxFormatDetect(void)
{
    // Polling at least 3 frame for HW auto detect TMDS format
    if(ScalerTimerPollingFlagProc(130, RXA(P71_CB_HDMI_SR), _BIT0, _TRUE) == _TRUE)
    {
        RxSetBit(P71_AF_TMDS_WDC, ~_BIT0, 0x00);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE)
        {
            // Check if HDMI 2.0 ON
            if(RxGetBit(P71_00_HDMI_CTRL_00, _BIT0) == _BIT0)
            {
                // Set Manual Format to HDMI
                ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT3 | _BIT2), (_BIT3 | _BIT2));

                // Toggle HW Format Detect Flag Reset
                RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), _BIT7);
                RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), 0x00);

                RXSEL((SET_TMDS_RX2_HDMI_2_0_FORMAT_RESET_WAITING()), (SET_TMDS_RX3_HDMI_2_0_FORMAT_RESET_WAITING()));

                ScalerTimerReactiveTimerEvent(130, RXSEL((_SCALER_TIMER_EVENT_RX2_HDMI2_FORMAT_RESET_WAIT), (_SCALER_TIMER_EVENT_RX3_HDMI2_FORMAT_RESET_WAIT)));
            }

            // Detect Scrambling Control Symbol
            if(RxGetBit(P71_01_HDMI_CTRL_01, _BIT3) == _BIT3)
            {
                // Enable Scrambling Status in SCDC
                ScalerSetDataPortBit(RXA(P71_39_HDMI_CTRL_39), _P71_3A_PT_21_PORT_PAGE71_HDMI_SCDC_21, ~_BIT0, _BIT0);
            }
        }
#endif

#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)

        if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_MHL_MODE)
        {
            // Set Manual Format to HDMI
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT3 | _BIT2), (_BIT3 | _BIT2));
        }
#endif
        return _SOURCE_HDMI;
    }
    else
    {
        RxSetBit(P71_AF_TMDS_WDC, ~_BIT0, _BIT0);

        if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE)
        {
#if(_D2_HDMI_2_0_SUPPORT == _ON)
            if(RxGetBit(P71_00_HDMI_CTRL_00, _BIT0) == _BIT0)
            {
                ScalerTimerCancelTimerEvent(RXSEL((_SCALER_TIMER_EVENT_RX2_HDMI2_FORMAT_RESET_WAIT), (_SCALER_TIMER_EVENT_RX3_HDMI2_FORMAT_RESET_WAIT)));
            }
#endif
            // Set Format Detect HW Auto Mode
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT3 | _BIT2), 0x00);
        }
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        else
        {
            // Manual Set to DVI Mode
            ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, ~(_BIT7 | _BIT6 | _BIT3 | _BIT2), _BIT3);
        }
#endif
        return _SOURCE_DVI;
    }
}

//--------------------------------------------------
// Description  : Check whether HDCP is enabled
// Input Value  : None
// Output Value : TRUE => HDCP Enabled
//--------------------------------------------------
bit ScalerTMDSRxHdcpEnabled(void)
{
    BYTE pucHDCPFrameCount[2];
    memset(pucHDCPFrameCount, 0, sizeof(pucHDCPFrameCount));

#if(_TMDS_HDCP_2_2_SUPPORT == _ON)
    if((RxGetBit(P71_C0_HDCP_CR, _BIT0) == _BIT0) && (RxGetBit(P2D_26_HDCP_I2C_CTRL_0, _BIT7) == 0x00))
#endif
    {
        ScalerGetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C0_PORT_PAGE71_HDCP_FCR, 1, &pucHDCPFrameCount[0], _NON_AUTOINC);

        // Wait 2Vsync to make sure frame counter changing, and timeout 45ms (margin + 1/24 frame+rate)
        RxSetBit(P71_A4_TMDS_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), _BIT3);
        ScalerTimerPollingFlagProc(45, RXA(P71_A4_TMDS_CTRL), _BIT3, _TRUE);
        RxSetBit(P71_A4_TMDS_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), _BIT3);
        ScalerTimerPollingFlagProc(45, RXA(P71_A4_TMDS_CTRL), _BIT3, _TRUE);

        ScalerGetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C0_PORT_PAGE71_HDCP_FCR, 1, &pucHDCPFrameCount[1], _NON_AUTOINC);

        if(pucHDCPFrameCount[0] != pucHDCPFrameCount[1])
        {
            return _TRUE;
        }

        return _FALSE;
    }
#if(_TMDS_HDCP_2_2_SUPPORT == _ON)
    else if((RxGetBit(P71_C0_HDCP_CR, _BIT0) == 0x00) && (RxGetBit(P2D_26_HDCP_I2C_CTRL_0, _BIT7) == _BIT7))
    {
        if(RxGetByte(P2D_2C_HDCP_I2C_CTRL_6) == 0x10)
        {
            return _TRUE;
        }
        else
        {
            return _FALSE;
        }
    }
    else
    {
        return _FALSE;
    }
#endif
}
bit ScalerTMDSRx2HdcpEnabled(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdcpEnabled();
    RX_CUR = ucOld;

    return xRet;
}
#endif // End of #if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)

//--------------------------------------------------
// Description  : DFE Adaptation in Normal Signal
// Input Value  : None
// Output Value : True --> DFE Normal
//                False --> DFE Abnormal
//--------------------------------------------------
bit ScalerTMDSRxCheckDataDFE(void)
{
    BYTE ucTemp = 0;
    BYTE ucCnt = 0;

    // DFE Check only under HDMI Mode.
    // MHL has only 1 __data Lane --> Skip DFE Check Process and Function return True!
    if(RxGetBit(P7B_17_BANDGAP_03, _BIT1) != _BIT1)
    {
        for(pData[0] = 0; pData[0] <= 2; pData[0]++)
        {
            // Sel lane
            RxSetBit(P7B_F2_COEF_3, ~(_BIT7 | _BIT6), pData[0] << 6);

            // Read VTH
            RxSetBit(P7B_F0_COEF_1, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

            if((RxGetByte(P7B_F1_COEF_2) & 0x1F) == 0)
            {
                for(ucCnt = 0; ucCnt < 3; ucCnt++)
                {
                    // Read TAP0
                    RxSetBit(P7B_F0_COEF_1, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT0);

                    ucTemp = (RxGetByte(P7B_F1_COEF_2) & 0x1F);

                    if(ucTemp < 21)
                    {
                        return _TRUE;
                    }
                    else if(ucCnt == 2)
                    {
                        DebugMessageRx2("DFE Abnormal ", 0);
                        return _FALSE;
                    }
                }
            }
        }
    }

    return _TRUE;
}
bit ScalerTMDSRx2CheckDataDFE(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxCheckDataDFE();
    RX_CUR = ucOld;

    return xRet;
}

//--------------------------------------------------
// Description  : On Line Check TMDS stability
// Input Value  : ucSourceType --> Source Type
// Output Value : True --> TMDS Stable
//                False --> TMDS Unstable
//--------------------------------------------------
bit ScalerTMDSRxTMDSStableDetect(BYTE ucSourceType)
{
    // CLR SCL/SDA Toggle Flag
    RXSEL((CLR_TMDS_RX2_DDC_DETECTED()), (CLR_TMDS_RX3_DDC_DETECTED()));

    if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) != _TMDS_HPD_NONE)
    {
        DebugMessageRx2("Rx2 HPD Toggle!!", 0);
        return _FALSE;
    }

    if(ScalerTMDSRxCheckCDRStable(isr_g_usTMDSRxClkCount[RX_CUR]) == _FALSE)
    {
        DebugMessageRx2("CDR Unstable!!", ucSourceType);
        return _FALSE;
    }

    // Check TMDS Clock Output Disable
    if(RxGetBit(P71_A6_TMDS_OUTCTL, _BIT3) == 0x00)
    {
        DebugMessageRx2("TMDS Clock Output has been disable", ucSourceType);
        return _FALSE;
    }

#if(_D2_HDMI_2_0_SUPPORT == _ON)

    if((RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE) && (RxGetBit(P71_00_HDMI_CTRL_00, _BIT0) == _BIT0))
    {
        if(ucSourceType == _SOURCE_HDMI)
        {
            if(RXSEL((GET_TMDS_RX2_HDMI_2_0_FORMAT_RESET_WAITING()), (GET_TMDS_RX3_HDMI_2_0_FORMAT_RESET_WAITING())) == _FALSE)
            {
                if(ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_00_PORT_PAGE71_HDMI_SCR, _BIT3) != _BIT3)
                {
                    return _FALSE;
                }
                else
                {
                    if(RxGetBit(P71_CB_HDMI_SR, _BIT0) == 0x00)
                    {
                        DebugMessageRx2("TMDS Format Changed", ucSourceType);

                        return _FALSE;
                    }
                    else
                    {
                        // Toggle HW Format Detect Flag Reset
                        RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), _BIT7);
                        RxSetBit(P71_01_HDMI_CTRL_01, ~(_BIT7 | _BIT3), 0x00);

                        RXSEL((SET_TMDS_RX2_HDMI_2_0_FORMAT_RESET_WAITING()), (SET_TMDS_RX3_HDMI_2_0_FORMAT_RESET_WAITING()));

                        ScalerTimerReactiveTimerEvent(130, RXSEL((_SCALER_TIMER_EVENT_RX2_HDMI2_FORMAT_RESET_WAIT), (_SCALER_TIMER_EVENT_RX3_HDMI2_FORMAT_RESET_WAIT)));
                    }
                }
            }
        }
        else
        {
            if(RxGetBit(P71_CB_HDMI_SR, _BIT0) == _BIT0)
            {
                DebugMessageRx2("TMDS Format Changed", ucSourceType);
                return _FALSE;
            }
        }
    }
    else
#endif
    {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if((RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())) == _TMDS_24BIT_PHY_SETTING) ||
           ((RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())) == _TMDS_MHL_PPMODE_PHY_SETTING) && (ucSourceType == _SOURCE_DVI)))
#endif
        {
            if(ucSourceType == _SOURCE_HDMI)
            {
                if(RxGetBit(P71_CB_HDMI_SR, _BIT0) == 0x00)
                {
                    DebugMessageRx2("TMDS Format Changed", ucSourceType);
                    return _FALSE;
                }
            }
            else
            {
                if(RxGetBit(P71_CB_HDMI_SR, _BIT0) == _BIT0)
                {
                    DebugMessageRx2("TMDS Format Changed", ucSourceType);
                    return _FALSE;
                }
            }
        }
    }

    if(RXSEL((GET_TMDS_RX2_Z0_ASSERTED()), (GET_TMDS_RX3_Z0_ASSERTED())) == _TRUE)
    {
        if((RxGetBit(P71_A9_TMDS_ABC0, _BIT6) == _BIT6) && (!((((RxGetBit(P71_A9_TMDS_ABC0, _BIT7)) == _BIT7) || ((RxGetBit(P71_AE_TMDS_RPS, _BIT1)) == _BIT1)) && ((RxGetBit(P71_A9_TMDS_ABC0, _BIT5)) == _BIT5))))
        {
            RXSEL((SET_TMDS_RX2_HPD_TRIGGER_EVENT(_TMDS_HPD_NORMAL)), (SET_TMDS_RX3_HPD_TRIGGER_EVENT(_TMDS_HPD_NORMAL)));

            RXSEL((CLR_TMDS_RX2_Z0_ASSERTED()), (CLR_TMDS_RX3_Z0_ASSERTED()));

            DebugMessageRx2("7. HDCP Abnormal !!!!!", 0);

            // MHL mode of MHL PORT will not return FALSE
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
            if(RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE)
            {
                return _FALSE;
            }
#else
            return _FALSE;
#endif
        }
        else if(((RxGetBit(P71_A9_TMDS_ABC0, _BIT7) == (_BIT7)) || (RxGetBit(P71_AE_TMDS_RPS, _BIT1) == (_BIT1))) && (RxGetBit(P71_A9_TMDS_ABC0, _BIT5) == (_BIT5)))
        {
            RXSEL((CLR_TMDS_RX2_Z0_ASSERTED()), (CLR_TMDS_RX3_Z0_ASSERTED()));

            DebugMessageRx2("7. HDCP Normal", 0);
        }
    }

    if(ucSourceType == _SOURCE_DVI)
    {
        if(RXSEL((GET_TMDS_RX2_RGBHV_DETECTING()), (GET_TMDS_RX3_RGBHV_DETECTING())) == _FALSE)
        {
            // TMDS Video Detected
#if(_DVI_DE_ONLY_SUPPORT == _OFF)
            if(ScalerTMDSRxTMDSVideoDetect(_NOT_WAIT) != _TMDS_VIDEO_DATA_RGBHV)
#else
            if(ScalerTMDSRxTMDSVideoDetect(_NOT_WAIT) == _TMDS_VIDEO_DATA_NONE)
#endif
            {
                DebugMessageRx2("TMDS Video format changed", ucSourceType);

                return _FALSE;
            }
        }
    }

#if(_D2_HDMI_SUPPORT == _ON)

    if(ucSourceType == _SOURCE_HDMI)
    {
        if(RXSEL((GET_HDMI_RX2_PACKET_DETECTING()), (GET_HDMI_RX3_PACKET_DETECTING())) == _FALSE)
        {
            // HDMI Packet Detected
            ScalerTMDSRxHdmiPacketDetect(_NOT_WAIT);

            if(RXSEL((GET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (GET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED())) == _TRUE)
            {
                if(ScalerSyncTMDSRxHdmiColorInfoChanged() == _TRUE)
                {
                    DebugMessageRx2("Color Info Changed", ucSourceType);
                    return _FALSE;
                }

                if(ScalerTMDSRxHdmiAviPixelRepInfoChanged() == _TRUE)
                {
                    DebugMessageRx2("Pixel Repetition Info Changed", ucSourceType);
                    return _FALSE;
                }
            }
            else
            {
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
                if(RXSEL((GET_TMDS_RX2_CLK_MODE()), (GET_TMDS_RX3_CLK_MODE())) == _TMDS_24BIT_PHY_SETTING)
#endif
                {
                    if(GET_COLOR_SPACE() != _COLOR_SPACE_RGB)
                    {
                        DebugMessageRx2("HDMI Info Frame Not Received and not RGB", ucSourceType);
                        return _FALSE;
                    }
                }

#if(_RGB_QUANTIZATION_RANGE_SUPPORT == _ON)
                if(GET_COLOR_RGB_QUANTIZATION_RANGE() != _RGB_QUANTIZATION_RESERVED)
                {
                    DebugMessageRx2("No Quantization Range Specified", ucSourceType);
                    return _FALSE;
                }
#endif

                if(RXSEL((GET_TMDS_RX2_AVI_PIXEL_REPETITION()), (GET_TMDS_RX3_AVI_PIXEL_REPETITION())) != _AVI_PIXEL_REPETITION_0)
                {
                    DebugMessageRx2("Pixel Repetition Not Received and not Pixel repetition 0", ucSourceType);
                    return _FALSE;
                }
            }

            if(GET_DIGITAL_COLOR_INFO_CHANGE_RESET() == _TRUE)
            {
                if((ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_41_PORT_PAGE71_HDMI_VWDSR, _BIT0) == _BIT0) && (RxGetBit(P71_CC_HDMI_GPVS, _BIT0) == _BIT0))
                {
                    DebugMessageRx2("HDMI AVI info frame has changed", ucSourceType);
                    return _FALSE;
                }
            }

            if(RXSEL((GET_HDMI_RX2_GCP_RECEIVED()), (GET_HDMI_RX3_GCP_RECEIVED())) == _TRUE)
            {
                if((GET_COLOR_SPACE() != _COLOR_SPACE_YCBCR422) && (ScalerTMDSRxHdmiGetColorDepth() != GET_COLOR_DEPTH()))
                {
                    DebugMessageRx2("Color Depth Has Changed", GET_COLOR_DEPTH());
                    return _FALSE;
                }
            }
            else
            {
                if((GET_COLOR_SPACE() != _COLOR_SPACE_YCBCR422) && (GET_COLOR_DEPTH() != _COLOR_DEPTH_8_BITS))
                {
                    DebugMessageRx2("HDMI GCP PACKET Not Received and not 8 bit", ucSourceType);
                    return _FALSE;
                }
            }

#if(_HDMI_FREESYNC_SUPPORT == _ON)
            if(RXSEL((GET_TMDS_RX2_SPD_INFO_FRAME_RECEIVED()), (GET_TMDS_RX3_SPD_INFO_FRAME_RECEIVED())) == _TRUE)
            {
                if((bit)RXSEL((GET_HDMIRX2_AMD_SPD_INFO(_SPD_INFO_FREESYNC_SUPPORT)), (GET_HDMIRX3_AMD_SPD_INFO(_SPD_INFO_FREESYNC_SUPPORT))) != GET_HDMI_FREESYNC_ENABLED())
                {
                    DebugMessageRx2("HDMI Freesync Status Change", GET_HDMI_FREESYNC_ENABLED());
                    return _FALSE;
                }
            }
            else
            {
                if(GET_HDMI_FREESYNC_ENABLED() == _TRUE)
                {
                    DebugMessageRx2("HDMI Freesync Status Change", GET_HDMI_FREESYNC_ENABLED());
                    return _FALSE;
                }
            }
#endif
        }
    }

#endif

#if(_TMDS_TOGGLE_HPD_Z0_FOR_ACER == _ON)

    if(RXSEL((GET_TMDS_RX2_TOGGLE_Z0()), (GET_TMDS_RX3_TOGGLE_Z0())) == _TRUE)
    {
        RXSEL((SET_TMDS_RX2_TOGGLE_Z0_EVENT()), (SET_TMDS_RX3_TOGGLE_Z0_EVENT()));

        return _FALSE;
    }

#endif

    return _TRUE;
}
bit ScalerTMDSRx2TMDSStableDetect(BYTE ucSourceType)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxTMDSStableDetect(ucSourceType);
    RX_CUR = ucOld;

    return xRet;
}

//--------------------------------------------------
// Description  : TMDS Hot Plug Event
// Input Value  : None
// Output Value :
//--------------------------------------------------
void ScalerTMDSRxHotPlugEvent(void)
{
    ScalerTMDSRxBeforeHotPlugEventProc();

    // ACER mode and DVI port will only toggle Z0 130ms
#if((_D2_INPUT_PORT_TYPE == _D2_DVI_PORT) && (_TMDS_TOGGLE_HPD_Z0_FOR_ACER == _ON))
    if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) == _TMDS_HPD_ACER)
    {
        // MHL mode of MHL PORT can not pull HPD
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
        if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE))
#else
        if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE))
#endif
        {
            ScalerTimerDelayXms(_TMDS_ACER_HPD_TIME);
        }
    }
    else
#endif
    {
        // HPD Low
        ScalerTMDSRxHotPlugLowProc();

        // wait
        if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) == _TMDS_HPD_NORMAL)
        {
            ScalerTMDSRxHotPlugHighProc(GET_HDMI_HOTPLUG_TIME());
        }
        else if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) == _TMDS_HPD_HDCP_2_2)
        {
            ScalerTMDSRxHotPlugHighProc(_TMDS_HDCP_2_2_HPD_TIME);
        }
        else if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) == _TMDS_HPD_ACER)
        {
            ScalerTMDSRxHotPlugHighProc(_TMDS_ACER_HPD_TIME);
        }
        else if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) == _TMDS_HPD_EDID_SWITCH)
        {
            ScalerTMDSRxHotPlugHighProc(_TMDS_EDID_SWITCH_HPD_TIME);
        }
        else
        {
            ScalerTMDSRxHotPlugHighProc(GET_HDMI_HOTPLUG_TIME());
        }
    }

    // Restore Slave Address and Z0 Status
    ScalerTMDSRxAfterHotPlugEventProc();

    DebugMessageRx2("Rx2 HPD Toggle!!", 0);

#if(_TMDS_TOGGLE_HPD_Z0_FOR_ACER == _ON)
    if(RXSEL((GET_TMDS_RX2_TOGGLE_Z0_EVENT()), (GET_TMDS_RX3_TOGGLE_Z0_EVENT())) == _TRUE)
    {
        RXSEL((CLR_TMDS_RX2_TOGGLE_Z0()), (CLR_TMDS_RX3_TOGGLE_Z0()));
        RXSEL((CLR_TMDS_RX2_TOGGLE_Z0_EVENT()), (CLR_TMDS_RX3_TOGGLE_Z0_EVENT()));
    }
#endif

    RXSEL((CLR_TMDS_RX2_HPD_TRIGGER_EVENT()), (CLR_TMDS_RX3_HPD_TRIGGER_EVENT()));
}
void ScalerTMDSRx2HotPlugEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHotPlugEvent();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS Switch Slave Address
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxSwitchSlaveAddr(void)
{
    ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C2_PORT_PAGE71_HDCP_SLAVE_ADD, 0x7F);
}
void ScalerTMDSRx2SwitchSlaveAddr(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxSwitchSlaveAddr();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS Before Hot Plug Event Process
// Input Value  : None
// Output Value : Hot Plug time
//--------------------------------------------------
void ScalerTMDSRxBeforeHotPlugEventProc(void)
{
    // MHL mode of MHL PORT can not pull HPD
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE))
#else
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE))
#endif
    {
        // Save Z0 Status
        g_ucTMDSRxZ0Status[RX_CUR] = RxGetBit(P7B_18_IMPEDANCE_00, (_BIT7 | _BIT6 | _BIT5 | _BIT4));

        // Backup Slave Address
        ScalerGetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C2_PORT_PAGE71_HDCP_SLAVE_ADD, 1, &g_ucTMDSRxSlaveAddr[RX_CUR], _NON_AUTOINC);

#if((_TMDS_HDCP_2_2_SUPPORT == _ON) && ((_D2_INPUT_PORT_TYPE == _D2_HDMI_PORT) || (_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)))
        // Reset HDCP 2.2
        RXSEL((ScalerTMDSRx2Hdcp2ResetProc()), (ScalerTMDSRx3Hdcp2ResetProc()));
#endif

#if(_D2_HDMI_2_0_SUPPORT == _ON)
        // Disable HDMI 2.0 SCDC Function
        RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, 0x00);
#endif

        // Disable Z0
        RxSetBit(P7B_18_IMPEDANCE_00, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), 0x00);
    }
    else if(RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _FALSE)
    {
        // Reset DDC2
        RXREG(MCU_FE65_DDC2_DDC_CONTROL_1, MCU_FE6E_DDC3_DDC_CONTROL_1) |= _BIT1;
    }
}
void ScalerTMDSRx2BeforeHotPlugEventProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxBeforeHotPlugEventProc();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS After Hot Plug Event Process
// Input Value  : None
// Output Value :
//--------------------------------------------------
void ScalerTMDSRxAfterHotPlugEventProc(void)
{
    // MHL mode of MHL PORT can not pull HPD
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE))
#else
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE))
#endif
    {
        // Restore Slave Address
        ScalerSetDataPortByte(RXA(P71_C3_HDCP_AP), _P71_C4_PT_C2_PORT_PAGE71_HDCP_SLAVE_ADD, g_ucTMDSRxSlaveAddr[RX_CUR]);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
        // Enable HDMI 2.0 SCDC Function
        RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, _BIT7);
#endif

        // Restore Z0 Status
        RxSetBit(P7B_18_IMPEDANCE_00, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), g_ucTMDSRxZ0Status[RX_CUR]);
    }
}
void ScalerTMDSRx2AfterHotPlugEventProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxAfterHotPlugEventProc();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : HDCP 1.4 R0 IIC 20k issue Function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdcp1p4AksvClear(void)
{
    // Disable R0 ready bit
    RxSetBit(P71_AE_TMDS_RPS, ~_BIT1, 0x00);
}
void ScalerTMDSRx2Hdcp1p4AksvClear(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdcp1p4AksvClear();
    RX_CUR = ucOld;
}

#endif // End of #if(_D2_TMDS_SUPPORT == _ON)

#if(_D2_HDMI_2_0_SUPPORT == _ON)
BYTE AwtoTmdsRx2Hs(void)                          // sync log: the 1:40 (HDMI 2.0) PHY mode is set
{
    return (GET_TMDS_RX2_HIGH_SPEED_MODE() != 0);
}
#endif
