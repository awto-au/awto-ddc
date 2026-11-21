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
// ID Code      : RL6449_Series_TMDSRx3.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RL6449_SERIES_TMDSRX3__

#include "ScalerFunctionInclude.h"

#if(_D3_TMDS_SUPPORT == _ON)

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
StructTMDSCtrlInfo g_stTMDSRx3CtrlInfo;
volatile bit d_g_bTMDSRx3HDMI2RREnable = _FALSE;
volatile bit d_isr_g_bTMDSRx3HDMI2HighSpeedMode = _FALSE;
volatile bit d_isr_g_bTMDSRx3TMDSPhySet = _FALSE;
volatile bit d_isr_g_bTMDSRx3TMDSDdcDetected = _FALSE;

#if(_D3_INPUT_PORT_TYPE == _D3_MHL_PORT)
BYTE g_ucTMDSRx3ClkMode = _TMDS_24BIT_PHY_SETTING;
#endif

#if((_TMDS_HDCP_2_2_SUPPORT == _ON) && ((_D3_INPUT_PORT_TYPE == _D3_HDMI_PORT) || (_D3_INPUT_PORT_TYPE == _D3_MHL_PORT)))
BYTE g_pucTmdsRx3Caps[3];
#endif

//****************************************************************************
// FUNCTION DEFINITIONS (D3 wrappers of the shared body in RL6449_Series_TMDSRx2.c)
//****************************************************************************
#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3Initial(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxInitial();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3InterruptInitial(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxInterruptInitial();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3PhySetDeferred(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxPhySetDeferred();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3IntHandler_EXINT0(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxIntHandler_EXINT0();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
bit ScalerTMDSRx3CheckCDRStable(WORD usClkCount)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxCheckCDRStable(usClkCount);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3SetPorchColor(EnumColorSpace enumColorFormat)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxSetPorchColor(enumColorFormat);
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT))
bit ScalerTMDSRx3HdmiSetDeepColorPll(WORD usTMDSClkCount, BYTE ucColorDepth)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdmiSetDeepColorPll(usTMDSClkCount, ucColorDepth);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
void ScalerTMDSRx3HdmiPacketDetect(bit bWait)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdmiPacketDetect(bWait);
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
void ScalerTMDSRx3HdmiAVMuteProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdmiAVMuteProc();
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
void ScalerTMDSRx3HdmiWatchDog(BYTE ucWDType, bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdmiWatchDog(ucWDType, bEnable);
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3PowerSavingProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxPowerSavingProc();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3FreqDetectDisable(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxFreqDetectDisable();
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT) && (_D3_INPUT_PORT_TYPE != _D3_NO_PORT))
BYTE ScalerTMDSRx3TMDSScanInputPort(BYTE ucInputType)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxTMDSScanInputPort(ucInputType);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT))
bit ScalerTMDSRx3HdcpEnabled(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdcpEnabled();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
bit ScalerTMDSRx3CheckDataDFE(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxCheckDataDFE();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
bit ScalerTMDSRx3TMDSStableDetect(BYTE ucSourceType)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxTMDSStableDetect(ucSourceType);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3HotPlugEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHotPlugEvent();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3SwitchSlaveAddr(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxSwitchSlaveAddr();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3BeforeHotPlugEventProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxBeforeHotPlugEventProc();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3AfterHotPlugEventProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxAfterHotPlugEventProc();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3Hdcp1p4AksvClear(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdcp1p4AksvClear();
    RX_CUR = ucOld;
}
#endif

#endif // End of #if(_D3_TMDS_SUPPORT == _ON)

#if(_D3_HDMI_2_0_SUPPORT == _ON)
BYTE AwtoTmdsRx3Hs(void)                          // sync log: the 1:40 (HDMI 2.0) PHY mode is set
{
    return (GET_TMDS_RX3_HIGH_SPEED_MODE() != 0);
}
#endif
