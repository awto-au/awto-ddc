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
// ID Code      : ScalerTMDSRx3_SeptPhy.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#include "ScalerFunctionInclude.h"

#if(_D3_TMDS_SUPPORT == _ON)

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3DviVideoSetting(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxDviVideoSetting();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3FirstActiveProc(BYTE ucSourceType)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxFirstActiveProc(ucSourceType);
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3PowerOffProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxPowerOffProc();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
BYTE ScalerTMDSRx3TMDSVideoDetect(bit bWait)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxTMDSVideoDetect(bWait);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3TMDSVideoDetectEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxTMDSVideoDetectEvent();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3PSIntHandler_EXINT0(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxPSIntHandler_EXINT0();
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
bit ScalerTMDSRx3HdmiAviPixelRepInfoChanged(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdmiAviPixelRepInfoChanged();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
BYTE ScalerTMDSRx3HdmiGetAVIInfo(EnumAviInfoContent enumContent)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdmiGetAVIInfo(enumContent);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
BYTE ScalerTMDSRx3HdmiGetColorDepth(void)
{
    BYTE xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdmiGetColorDepth();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
void ScalerTMDSRx3HdmiPacketDetectEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdmiPacketDetectEvent();
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_HDMI_2_0_SUPPORT == _ON) && (_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON))
void ScalerTMDSRx3HDMI2HPDRRIRQEnable(bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHDMI2HPDRRIRQEnable(bEnable);
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_HDMI_2_0_SUPPORT == _ON))
void ScalerTMDSRx3Hdmi2FormatResetEvent(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHdmi2FormatResetEvent();
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_HDMI_2_0_SUPPORT == _ON))
void ScalerTMDSRx3ReadRequestProc_EXINT0(BYTE ucRROutCome)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxReadRequestProc_EXINT0(ucRROutCome);
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_HDMI_2_0_SUPPORT == _ON))
void ScalerTMDSRx3ReadRequestTimerEventEnable_WDINT(bit bEnable)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxReadRequestTimerEventEnable_WDINT(bEnable);
    RX_CUR = ucOld;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT))
bit ScalerTMDSRx3HdmiDeepColorProc(WORD usTmdsClkCnt)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxHdmiDeepColorProc(usTmdsClkCnt);
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT) && (_D3_INPUT_PORT_TYPE != _D3_NO_PORT))
bit ScalerTMDSRx3TMDSNormalPreDetect(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxTMDSNormalPreDetect();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if((_D3_TMDS_SUPPORT == _ON) && (_D3_INPUT_PORT_TYPE != _D3_DUAL_DVI_PORT) && (_D3_INPUT_PORT_TYPE != _D3_NO_PORT))
bit ScalerTMDSRx3TMDSPSPreDetect(void)
{
    bit xRet;
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    xRet = ScalerTMDSRxTMDSPSPreDetect();
    RX_CUR = ucOld;

    return xRet;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3HotPlugLowProc(void)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHotPlugLowProc();
    RX_CUR = ucOld;
}
#endif

#if(_D3_TMDS_SUPPORT == _ON)
void ScalerTMDSRx3HotPlugHighProc(WORD usHpdTime)
{
    BYTE ucOld = RX_CUR;

    RX_CUR = 1;
    ScalerTMDSRxHotPlugHighProc(usHpdTime);
    RX_CUR = ucOld;
}
#endif

#endif
