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
// ID Code      : ScalerTMDSRx2_SeptPhy.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define RX_SHARE_BODY
#include "ScalerFunctionInclude.h"

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************

//****************************************************************************
// CODE TABLES
//****************************************************************************

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
#if(_D2_TMDS_SUPPORT == _ON)
void ScalerTMDSRxDviVideoSetting(void);
void ScalerTMDSRxFirstActiveProc(BYTE ucSourceType);
void ScalerTMDSRxPowerOffProc(void);
BYTE ScalerTMDSRxTMDSVideoDetect(bit bWait);
void ScalerTMDSRxTMDSVideoDetectEvent(void);
void ScalerTMDSRxPSIntHandler_EXINT0(void);

#if(_D2_HDMI_SUPPORT == _ON)
bit ScalerTMDSRxHdmiAviPixelRepInfoChanged(void);
BYTE ScalerTMDSRxHdmiGetAVIInfo(EnumAviInfoContent enumContent);
BYTE ScalerTMDSRxHdmiGetColorDepth(void);
void ScalerTMDSRxHdmiPacketDetectEvent(void);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
#if(_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON)
void ScalerTMDSRxHDMI2HPDRRIRQEnable(bit bEnable);
#endif
void ScalerTMDSRxHdmi2FormatResetEvent(void);
void ScalerTMDSRxReadRequestProc_EXINT0(BYTE ucRROutCome);
void ScalerTMDSRxReadRequestTimerEventEnable_WDINT(bit bEnable);
#endif

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
bit ScalerTMDSRxHdmiDeepColorProc(WORD usTmdsClkCnt);
bit ScalerTMDSRxHdmiWaitDeepColorPllLock(void);
#endif

#endif

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
#if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)
bit ScalerTMDSRxTMDSNormalPreDetect(void);
bit ScalerTMDSRxTMDSPSPreDetect(void);
#endif

#endif

void ScalerTMDSRxHotPlugLowProc(void);
void ScalerTMDSRxHotPlugHighProc(WORD usHpdTime);
#endif

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
#if(_D2_TMDS_SUPPORT == _ON)
//--------------------------------------------------
// Description  : TMDS Video Setting
// Input Value  : Source Type
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxDviVideoSetting(void)
{
    // Manual Set Color Space and disable pixel repetition
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_51_PORT_PAGE71_HDMI_ACRCR, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), 0x00);

    // Disable Down Sampling
    ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_50_PORT_PAGE71_HDMI_VCR, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

    // Waiting for Down Sampling Effect
    ScalerTimerDelayXms(20);

    SET_COLOR_SPACE(_COLOR_SPACE_RGB);
    SET_COLOR_RGB_QUANTIZATION_RANGE(_RGB_QUANTIZATION_FULL_RANGE);

    ScalerTMDSRxSetPorchColor(GET_COLOR_SPACE());
}
void ScalerTMDSRx2DviVideoSetting(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxDviVideoSetting();
    RX_CUR = ucOld;
}
//--------------------------------------------------
// Description  : Process Required when Switched to Active State
// Input Value  : Input Source
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxFirstActiveProc(BYTE ucSourceType)
{
    ucSourceType = ucSourceType;
}
void ScalerTMDSRx2FirstActiveProc(BYTE ucSourceType)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxFirstActiveProc(ucSourceType);
    RX_CUR = ucOld;
}
//--------------------------------------------------
// Description  : TMDS Power Off Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxPowerOffProc(void)
{
    // Disable EDID read/ SCL toggle IRQ
    RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) = ((RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) & ~(_BIT3 | _BIT1)) | (_BIT2 | _BIT0));

    ScalerTMDSRxFreqDetectDisable();
}
void ScalerTMDSRx2PowerOffProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxPowerOffProc();
    RX_CUR = ucOld;
}
//--------------------------------------------------
// Description  : Detect TMDS video mode
// Input Value  : bWait => Whether to wait then read
// Output Value : TMDS video type
//--------------------------------------------------
BYTE ScalerTMDSRxTMDSVideoDetect(bit bWait)
{
    BYTE ucTemp = _TMDS_VIDEO_DATA_NONE;

    if(bWait == _WAIT)
    {
        // Wait at least 1 frame for HW auto update TMDS video RGBHV valid value
        ScalerTimerPollingFlagProc(45, RXA(P71_A4_TMDS_CTRL), _BIT3, _TRUE);

        // Wait for HW update DE flag
        if(ScalerTimerPollingFlagProc(20, RXA(P71_A4_TMDS_CTRL), (_BIT7 | _BIT6 | _BIT5), _TRUE) == _TRUE)
        {
            // H/Vsync received
            if(RxGetBit(P71_A4_TMDS_CTRL, (_BIT4 | _BIT3)) == (_BIT4 | _BIT3))
            {
                ucTemp = _TMDS_VIDEO_DATA_RGBHV;
            }
            else
            {
                ucTemp = _TMDS_VIDEO_DATA_DE_ONLY;
            }
        }
        else
        {
            ucTemp = _TMDS_VIDEO_DATA_NONE;
        }

        RXSEL((CLR_TMDS_RX2_RGBHV_DETECTING()), (CLR_TMDS_RX3_RGBHV_DETECTING()));

        return ucTemp;
    }
    else
    {
        // R/G/B __data detected
        if(RxGetBit(P71_A4_TMDS_CTRL, (_BIT7 | _BIT6 | _BIT5)) == (_BIT7 | _BIT6 | _BIT5))
        {
            // H/Vsync received
            if(RxGetBit(P71_A4_TMDS_CTRL, (_BIT4 | _BIT3)) == (_BIT4 | _BIT3))
            {
                ucTemp = _TMDS_VIDEO_DATA_RGBHV;
            }
            else
            {
                ucTemp = _TMDS_VIDEO_DATA_DE_ONLY;
            }
        }
        else
        {
            ucTemp = _TMDS_VIDEO_DATA_NONE;
        }

        // Clear video Detection Flag
        RxSetBit(P71_A4_TMDS_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3));

        RXSEL((SET_TMDS_RX2_RGBHV_DETECTING()), (SET_TMDS_RX3_RGBHV_DETECTING()));

        // Activate TMDS video Detection Event
        ScalerTimerActiveTimerEvent(45, RXSEL((_SCALER_TIMER_EVENT_RX2_TMDS_VIDEO_DETECT), (_SCALER_TIMER_EVENT_RX3_TMDS_VIDEO_DETECT)));

        return ucTemp;
    }
}
BYTE ScalerTMDSRx2TMDSVideoDetect(bit bWait)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxTMDSVideoDetect(bWait);
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : TMDS video Detect Event
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxTMDSVideoDetectEvent(void)
{
    RXSEL((CLR_TMDS_RX2_RGBHV_DETECTING()), (CLR_TMDS_RX3_RGBHV_DETECTING()));
}
void ScalerTMDSRx2TMDSVideoDetectEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxTMDSVideoDetectEvent();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : TMDS Interrupt Process In PS/PD State(EXINT0 Only)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxPSIntHandler_EXINT0(void)
{
#if(_D2_HDMI_2_0_SUPPORT == _ON)
    BYTE pucBackUp[4];
#else
    BYTE pucBackUp[2];
#endif

    pucBackUp[0] = RxGetByte(P71_C9_HDMI_AP);
    pucBackUp[1] = RxGetByte(P71_C8_HDMI_APC);

    // Set CA Port non-auto increase
    RxSetBit(P71_C8_HDMI_APC, ~_BIT0, 0x00);

#if(_D2_HDMI_2_0_SUPPORT == _ON)
    pucBackUp[2] = RxGetByte(P71_39_HDMI_CTRL_39);
    pucBackUp[3] = RxGetByte(P71_38_HDMI_CTRL_38);
#endif

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

            // Enable Rising to Falling edge IRQ
            RxSetBit(P71_23_HDMI_CTRL_23, ~_BIT6, _BIT6);
        }
    }
#endif // End of #if(_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON)
#endif // End of #if(_D2_HDMI_2_0_SUPPORT == _ON)

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
void ScalerTMDSRx2PSIntHandler_EXINT0(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxPSIntHandler_EXINT0();
    RX_CUR = ucOld;
}

#if(_D2_HDMI_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Detect HDMI AVI pixel repetition
// Input Value  : None
// Output Value : _TRUE => Current Info is different from previous setting
//--------------------------------------------------
bit ScalerTMDSRxHdmiAviPixelRepInfoChanged(void)
{
    // Check Tmds Pixel Repetition
    if(ScalerTMDSRxHdmiGetAVIInfo(_AVI_INFO_PIXEL_REPETITION) != RXSEL((GET_TMDS_RX2_AVI_PIXEL_REPETITION()), (GET_TMDS_RX3_AVI_PIXEL_REPETITION())))
    {
        return _TRUE;
    }

    return _FALSE;
}
bit ScalerTMDSRx2HdmiAviPixelRepInfoChanged(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdmiAviPixelRepInfoChanged();
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : Get HDMI AVI Info Contents
// Input Value  : Content of Interest
// Output Value : Content Value
//--------------------------------------------------
BYTE ScalerTMDSRxHdmiGetAVIInfo(EnumAviInfoContent enumContent)
{
    if(RXSEL((GET_HDMI_RX2_AVI_INFO_FRAME_RECEIVED()), (GET_HDMI_RX3_AVI_INFO_FRAME_RECEIVED())) == _TRUE)
    {
        switch(enumContent)
        {
            case _AVI_INFO_COLOR_SPACE:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x04, (_BIT6 | _BIT5)) >> 5);

            case _AVI_INFO_COLORIMETRY:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x05, (_BIT7 | _BIT6)) >> 6);

            case _AVI_INFO_EXTENDED_COLORIMETRY:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x06, (_BIT6 | _BIT5 | _BIT4)) >> 4);

            case _AVI_INFO_RGB_QUANTIZATION:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x06, (_BIT3 | _BIT2)) >> 2);

            case _AVI_INFO_YCC_QUANTIZATION:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x08, (_BIT7 | _BIT6)) >> 6);

            case _AVI_INFO_SCAN_INFO:

                return ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x04, (_BIT1 | _BIT0));

            case _AVI_INFO_IT_CONTENT:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x06, _BIT7) >> 7);

            case _AVI_INFO_PIXEL_REPETITION:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x08, (_BIT3 | _BIT2 | _BIT1 | _BIT0)));

            case _AVI_INFO_AR:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x05, (_BIT5 | _BIT4)) >> 4);

            case _AVI_INFO_VIC:

                return (ScalerGetDataPortBit(RXA(P71_CD_HDMI_PSAP), 0x07, (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0)));

            default:

                break;
        }
    }

    return 0xFF;
}
BYTE ScalerTMDSRx2HdmiGetAVIInfo(EnumAviInfoContent enumContent)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdmiGetAVIInfo(enumContent);
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : Get Color Depth
// Input Value  : None
// Output Value : Received Color Depth
//--------------------------------------------------
BYTE ScalerTMDSRxHdmiGetColorDepth(void)
{
    if(GET_COLOR_SPACE() == _COLOR_SPACE_YCBCR422)
    {
        return _COLOR_DEPTH_12_BITS;
    }

    if(RXSEL((GET_HDMI_RX2_GCP_RECEIVED()), (GET_HDMI_RX3_GCP_RECEIVED())) == _TRUE)
    {
        if(RxGetBit(P71_B4_TMDS_DPC0, 0x07) == 0x05)
        {
            return _COLOR_DEPTH_10_BITS;
        }
        else if(RxGetBit(P71_B4_TMDS_DPC0, 0x07) == 0x06)
        {
            return _COLOR_DEPTH_12_BITS;
        }
        else if(RxGetBit(P71_B4_TMDS_DPC0, 0x07) == 0x07)
        {
            return _COLOR_DEPTH_16_BITS;
        }
    }

    return _COLOR_DEPTH_8_BITS;
}
BYTE ScalerTMDSRx2HdmiGetColorDepth(void)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdmiGetColorDepth();
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : HDMI Info Frame Packet Detect Event
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdmiPacketDetectEvent(void)
{
    RXSEL((CLR_HDMI_RX2_PACKET_DETECTING()), (CLR_HDMI_RX3_PACKET_DETECTING()));
}
void ScalerTMDSRx2HdmiPacketDetectEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdmiPacketDetectEvent();
    RX_CUR = ucOld;
}

#if(_D2_HDMI_2_0_SUPPORT == _ON)
#if(_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON)
//--------------------------------------------------
// Description  : TMDS HPD IRQ Enable
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHDMI2HPDRRIRQEnable(bit bEnable)
{
    if(bEnable == _ENABLE)
    {
        // Set HPD Debounce = 700 Clock Cycle
        // Set HPD IRQ Detect Rising to Falling Edge IRQ
        RxSetBit(P71_23_HDMI_CTRL_23, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), (_BIT5 | _BIT4 | _BIT3 | _BIT1));

        // Enable HDMI HPD IRQ Enable
        RxSetBit(P71_23_HDMI_CTRL_23, ~_BIT6, _BIT6);

        // Write 1 Clear Read Request
        RxSetBit(P71_25_HDMI_CTRL_25, ~_BIT3, _BIT3);

        // Enable HDMI 2.0 SCDC IIC Module
        RxSetBit(P71_19_HDMI_CTRL_19, ~_BIT7, _BIT7);

        // Clear HDMI 2.0 Read Request Enable
        RXSEL((CLR_HDMI_2_0_RX2_RR_ENABLE()), (CLR_HDMI_2_0_RX3_RR_ENABLE()));

        // Enable HDMI 2.0 Read Request Enable Detect IRQ
        RxSetBit(P71_26_HDMI_CTRL_26, ~_BIT3, _BIT3);
    }
    else
    {
        // Write 1 Clear Read Request
        RxSetBit(P71_25_HDMI_CTRL_25, ~_BIT3, _BIT3);

        // Clear HDMI 2.0 Read Request Enable
        RXSEL((CLR_HDMI_2_0_RX2_RR_ENABLE()), (CLR_HDMI_2_0_RX3_RR_ENABLE()));

        // Disable HDMI 2.0 Read Request Enable Detect IRQ
        RxSetBit(P71_26_HDMI_CTRL_26, ~_BIT3, 0x00);
    }
}
void ScalerTMDSRx2HDMI2HPDRRIRQEnable(bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHDMI2HPDRRIRQEnable(bEnable);
    RX_CUR = ucOld;
}
#endif

//--------------------------------------------------
// Description  : TMDS Format Reset Event
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxHdmi2FormatResetEvent(void)
{
    RXSEL((CLR_TMDS_RX2_HDMI_2_0_FORMAT_RESET_WAITING()), (CLR_TMDS_RX3_HDMI_2_0_FORMAT_RESET_WAITING()));
}
void ScalerTMDSRx2Hdmi2FormatResetEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHdmi2FormatResetEvent();
    RX_CUR = ucOld;
}
//--------------------------------------------------
// Description  : TMDS Read Request Outcome Case Processing(EXINT0 Only)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxReadRequestProc_EXINT0(BYTE ucRROutCome)
{
    // Get Read Request Outcome Case
    switch(ucRROutCome)
    {
        case _HDMI_2_0_READ_REQUEST_ACK_DONE:
        case _HDMI_2_0_READ_REQUEST_ACK_STOP:

            break;

        case _HDMI_2_0_READ_REQUEST_NACK1:

            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // FW Manual Enable Read Request
                RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);
            }

            break;

        case _HDMI_2_0_READ_REQUEST_NACK2:

#if(_WD_TIMER_INT_SUPPORT == _ON)
            if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
            {
                // Enable Read Request Retry
                ScalerTimerWDActivateTimerEvent_EXINT0(10, RXSEL((_SCALER_WD_TIMER_EVENT_RX2_HDMI_RR_RETRY), (_SCALER_WD_TIMER_EVENT_RX3_HDMI_RR_RETRY)));
            }
#endif

            break;

        default:

            break;
    }
}
void ScalerTMDSRx2ReadRequestProc_EXINT0(BYTE ucRROutCome)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxReadRequestProc_EXINT0(ucRROutCome);
    RX_CUR = ucOld;
}
//--------------------------------------------------
// Description  : TMDS Read Request Timer Event Enable
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerTMDSRxReadRequestTimerEventEnable_WDINT(bit bEnable)
{
    if(bEnable == _ENABLE)
    {
        if(RXSEL((GET_HDMI_2_0_RX2_RR_ENABLE()), (GET_HDMI_2_0_RX3_RR_ENABLE())) == _TRUE)
        {
            // FW Manual Enable Read Request
            RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, _BIT7);
        }
    }
    else
    {
        // Disable Read Request Enable
        RxSetBit(P71_1B_HDMI_CTRL_1B, ~_BIT7, 0x00);
    }
}
void ScalerTMDSRx2ReadRequestTimerEventEnable_WDINT(bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxReadRequestTimerEventEnable_WDINT(bEnable);
    RX_CUR = ucOld;
}
#endif

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
//--------------------------------------------------
// Description  : HDMI Deep Color Proc
// Input Value  : void
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerTMDSRxHdmiDeepColorProc(WORD usTmdsClkCnt)
{
    // Setting Deep Color PLL
    if(ScalerTMDSRxHdmiSetDeepColorPll(usTmdsClkCnt, GET_COLOR_DEPTH()) == _FALSE)
    {
        return _FALSE;
    }

    // Wait for Phase lock
    if(ScalerTMDSRxHdmiWaitDeepColorPllLock() == _FALSE)
    {
        return _FALSE;
    }

    return _TRUE;
}
bit ScalerTMDSRx2HdmiDeepColorProc(WORD usTmdsClkCnt)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxHdmiDeepColorProc(usTmdsClkCnt);
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : Wait for Deep Color PLL Phase Lock
// Input Value  : None
// Output Value : _TRUE = > Phase Locked
//--------------------------------------------------
bit ScalerTMDSRxHdmiWaitDeepColorPllLock(void)
{
    BYTE ucTemp = 0;

    do
    {
        ScalerSetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_82_PORT_PAGE71_HDMI_DPC_SET2, ~(_BIT4 | _BIT3), (_BIT4 | _BIT3));

        // Delay for PLL Phase Lock
        ScalerTimerDelayXms(2);

        ucTemp++;
    }
    while((ScalerGetDataPortBit(RXA(P71_C9_HDMI_AP), _P71_CA_PT_82_PORT_PAGE71_HDMI_DPC_SET2, _BIT1) != 0) && (ucTemp <= 15));

    if(ucTemp > 15)
    {
        return _FALSE;
    }

    return _TRUE;
}
#endif
#endif

#if(_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT)
#if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)
//--------------------------------------------------
// Description  : Signal PreDetection for TMDS(Power Normal)
// Input Value  : Input Port
// Output Value : True : TMDS Signal Detected
//              : False : No Signal
//--------------------------------------------------
bit ScalerTMDSRxTMDSNormalPreDetect(void)
{
    // DDC handshake Detected
    if(RXSEL((GET_TMDS_RX2_DDC_DETECTED()), (GET_TMDS_RX3_DDC_DETECTED())) == _TRUE)
    {
        DebugMessageRx2("7. Normal D2 DDC", 0);

        RXSEL((CLR_TMDS_RX2_DDC_DETECTED()), (CLR_TMDS_RX3_DDC_DETECTED()));

        return _TRUE;
    }

    // Enable DDC Toggle IRQ
    if(((RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) & _BIT3) != _BIT3) && (RXSEL((GET_TMDS_RX2_DDC_DETECTED()), (GET_TMDS_RX3_DDC_DETECTED())) != _TRUE))
    {
        RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) |= _BIT2;
        RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) |= _BIT3;

        RXSEL((CLR_TMDS_RX2_DDC_DETECTED()), (CLR_TMDS_RX3_DDC_DETECTED()));
    }

    ScalerTimerDelayXms(6);

    if(RXSEL((GET_TMDS_RX2_PHY_SET()), (GET_TMDS_RX3_PHY_SET())) == _TRUE)
    {
        return _TRUE;
    }

    return _FALSE;
}
bit ScalerTMDSRx2TMDSNormalPreDetect(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxTMDSNormalPreDetect();
    RX_CUR = ucOld;

    return xRet;
}
//--------------------------------------------------
// Description  : Signal Detection for TMDS(Power Saving)
// Input Value  : Input Port
// Output Value : True : TMDS Signal Detected
//              : False : No Signal
//--------------------------------------------------
bit ScalerTMDSRxTMDSPSPreDetect(void)
{
#if(_AWTO_PS_WAKE == _ON)
    if(RXSEL((GET_TMDS_RX2_DDC_DETECTED()), (GET_TMDS_RX3_DDC_DETECTED())) == _TRUE)
    {
        RXSEL((CLR_TMDS_RX2_DDC_DETECTED()), (CLR_TMDS_RX3_DDC_DETECTED()));
        AwtoPsDdcSeen(RXSEL(_D2_INPUT_PORT, _D3_INPUT_PORT));
    }
    if((RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) & _BIT3) != _BIT3)
    {
        RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) = (RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) & ~_BIT0) | (_BIT3 | _BIT2);
    }
    return _FALSE;
#else
    // DDC handshake Detected
    if(RXSEL((GET_TMDS_RX2_DDC_DETECTED()), (GET_TMDS_RX3_DDC_DETECTED())) == _TRUE)
    {
        DebugMessageRx2("7. PowerSaving D2 DDC", 0);

        RXSEL((CLR_TMDS_RX2_DDC_DETECTED()), (CLR_TMDS_RX3_DDC_DETECTED()));

#if(_DP_HDMI_COMPATIBLE_MODE == _ON)
        RXSEL((SET_D2_HDMI_PS_WAKEUP()), (SET_D3_HDMI_PS_WAKEUP()));
#endif

#if(_TMDS_TOGGLE_HPD_Z0_FOR_ACER == _ON)
        RXSEL((SET_TMDS_RX2_TOGGLE_Z0()), (SET_TMDS_RX3_TOGGLE_Z0()));
#endif
        return _TRUE;
    }

    // Enable DDC Toggle IRQ
    if(((RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) & _BIT3) != _BIT3) && (RXSEL((GET_TMDS_RX2_DDC_DETECTED()), (GET_TMDS_RX3_DDC_DETECTED())) != _TRUE))
    {
        RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) |= _BIT2;
        RXREG(MCU_FE69_DDC2_EDID_IRQ, MCU_FE72_DDC3_EDID_IRQ) |= _BIT3;
    }

#if(_AWTO_PS_WAKE == _OFF)
    // Reset Freq. Detect Counter(Toggle) & Choose Measure Clk to TMDS Clk
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT7 | _BIT5 | _BIT4), 0x00);
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, _BIT7);

    // Clear Freq. Stable Flag
    RxSetBit(P71_EF_HDMI_ERROR_TH, ~_BIT6, _BIT6);

    // Clear Unstable Flag
    RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT2, _BIT2);

    // Delay enough time for freq. measure (calculated for measure 5 times)
    ScalerTimerDelayXms(5);

    // Detect Freq. Measure Stable
    if((RxGetBit(P71_E6_HDMI_FREQDET_CTRL, (_BIT6 | _BIT2)) == _BIT6) && (RxGetBit(P71_EF_HDMI_ERROR_TH, _BIT6) == _BIT6))
#else
    if(AwtoPsTmdsLive(0x71 + RX_CUR) != 0)
#endif
    {
#if(_DP_HDMI_COMPATIBLE_MODE == _ON)
        RXSEL((SET_D2_HDMI_PS_WAKEUP()), (SET_D3_HDMI_PS_WAKEUP()));
#endif

#if(_TMDS_TOGGLE_HPD_Z0_FOR_ACER == _ON)
        RXSEL((SET_TMDS_RX2_TOGGLE_Z0()), (SET_TMDS_RX3_TOGGLE_Z0()));
#endif
        return _TRUE;
    }
    else
    {
        // Disable Freq. Detection
#if(_AWTO_PS_WAKE == _OFF)
        RxSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT7, 0x00);
#endif

        return _FALSE;
    }

    return _FALSE;
#endif
}
bit ScalerTMDSRx2TMDSPSPreDetect(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    xRet = ScalerTMDSRxTMDSPSPreDetect();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#endif

//--------------------------------------------------
// Description  : HPD Low Process
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerTMDSRxHotPlugLowProc(void)
{
    // MHL mode of MHL PORT can not pull HPD
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE))
#else
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE))
#endif
    {
        RXSTMT(PCB_D2_HOTPLUG(_D2_HOT_PLUG_LOW), PCB_D3_HOTPLUG(_D3_HOT_PLUG_LOW));

#if(_DP_HDMI_COMPATIBLE_MODE == _ON)
        if(RXSEL((GET_TMDS_RX2_HPD_TRIGGER_EVENT()), (GET_TMDS_RX3_HPD_TRIGGER_EVENT())) != _TMDS_HPD_EIZO_PS_WAKEUP)
#endif
        {
            ScalerTMDSRxSwitchSlaveAddr();
        }
    }
}
void ScalerTMDSRx2HotPlugLowProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHotPlugLowProc();
    RX_CUR = ucOld;
}

//--------------------------------------------------
// Description  : HPD High Process
// Input Value  : usHpdTime
// Output Value :
//--------------------------------------------------
void ScalerTMDSRxHotPlugHighProc(WORD usHpdTime)
{
    // MHL mode of MHL PORT can not pull HPD
#if(_D2_INPUT_PORT_TYPE == _D2_MHL_PORT)
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE) && (RXSEL((GET_D2_TMDS_MODE()), (GET_D3_TMDS_MODE())) == _TMDS_HDMI_MODE))
#else
    if((GET_HDMI_HOTPLUG_TOGGLE() == _TRUE) && (RXSEL((GET_D2_CABLE_STATUS()), (GET_D3_CABLE_STATUS())) == _TRUE))
#endif
    {
        ScalerTimerDelayXms(usHpdTime);

        RXSTMT(PCB_D2_HOTPLUG(_D2_HOT_PLUG_HIGH), PCB_D3_HOTPLUG(_D3_HOT_PLUG_HIGH));
    }
}
void ScalerTMDSRx2HotPlugHighProc(WORD usHpdTime)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 0;
    ScalerTMDSRxHotPlugHighProc(usHpdTime);
    RX_CUR = ucOld;
}
#endif
