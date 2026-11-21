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
// ID Code      : RL6449_Series_TMDSRxShareInclude.h
// Update Note  : D2 (Rx2) and D3 (Rx3) run one TMDS implementation; the port is d_isr_g_ucTMDSRxPort (0 = D2, 1 = D3)
//----------------------------------------------------------------------------------------------------

#if((_D2_TMDS_SUPPORT == _ON) && (_D3_TMDS_SUPPORT == _ON))
//--------------------------------------------------
// Port select. The ScalerTMDSRx2* / Rx3* entry points set it; ISR-level entries restore the caller's value
//--------------------------------------------------
extern volatile BYTE __data d_isr_g_ucTMDSRxPort;
#define RX_CUR                                          (d_isr_g_ucTMDSRxPort)
#define RXSEL(x2, x3)                                   (RX_CUR ? (x3) : (x2))
#define RXSTMT(s2, s3)                                  if(RX_CUR) { s3; } else { s2; }
#define RXA(usAddr)                                     ((WORD)(usAddr) + ((WORD)RX_CUR << 8))
#define RXREG(r2, r3)                                   (*((volatile BYTE xdata *)(RX_CUR ? (WORD)&(r3) : (WORD)&(r2))))

//--------------------------------------------------
// Per-port state of the shared body, index = port
//--------------------------------------------------
extern volatile WORD isr_g_usTMDSRxClkCount[2];
extern volatile WORD isr_g_usTMDSRxPhyCount[2];
extern volatile WORD isr_g_usTMDSRxPhyClk[2];
extern volatile BYTE isr_g_ucTMDSRxPhyPend[2];
extern volatile BYTE g_pucTMDSRxLEMax[2][3];
extern volatile BYTE g_pucTMDSRxLEMin[2][3];
extern BYTE g_pucTMDSRxTap0Min[2][3];
extern BYTE g_pucTMDSRxTap0Max[2][3];
extern BYTE g_ucTMDSRxTap0Init[2];
extern BYTE g_pucTMDSRxTap1Max[2][3];
extern volatile BYTE isr_g_ucTMDSRxClkIRQ[2];
extern BYTE g_ucTMDSRxZ0Status[2];
extern BYTE g_ucTMDSRxSlaveAddr[2];

extern BYTE RxRegGetByte(WORD usAddr);
extern BYTE RxRegGetBit(WORD usAddr, BYTE ucAnd);
extern void RxRegSetByte(WORD usAddr, BYTE ucValue);
extern void RxRegSetBit(WORD usAddr, BYTE ucAnd, BYTE ucOr);
#define RxGetByte(usAddr)                               RxRegGetByte(usAddr)
#define RxGetBit(usAddr, ucAnd)                         RxRegGetBit((usAddr), (BYTE)(ucAnd))
#define RxSetByte(usAddr, ucValue)                      RxRegSetByte((usAddr), (BYTE)(ucValue))
#define RxSetBit(usAddr, ucAnd, ucOr)                   RxRegSetBit((usAddr), (BYTE)(ucAnd), (BYTE)(ucOr))

//--------------------------------------------------
// Shared bodies
//--------------------------------------------------
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxInitial(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxInterruptInitial(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxSetDFEInitial_EXINT0(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxFLDBandFineTune_EXINT0(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxSetPhy_EXINT0(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxPhySetDeferred(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxIntHandler_EXINT0(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern bit ScalerTMDSRxCheckCDRStable(WORD usClkCount);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern BYTE ScalerTMDSRxCheckCDRStable_EXINT0(WORD usClkCount);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern WORD ScalerTMDSRxMeasureClk(BYTE ucMeasureClk);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern WORD ScalerTMDSRxMeasureClk_EXINT0(BYTE ucMeasureClk);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxSetPorchColor(EnumColorSpace enumColorFormat);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT))
extern bit ScalerTMDSRxHdmiSetDeepColorPll(WORD usTMDSClkCount, BYTE ucColorDepth);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern void ScalerTMDSRxHdmiPacketDetect(bit bWait);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern void ScalerTMDSRxHdmiAVMuteProc(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern void ScalerTMDSRxHdmiWatchDog(BYTE ucWDType, bit bEnable);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxPowerSavingProc(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxFreqDetectDisable(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT) && (_D2_INPUT_PORT_TYPE != _D2_NO_PORT))
extern BYTE ScalerTMDSRxTMDSScanInputPort(BYTE ucInputType);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT))
extern BYTE ScalerTMDSRxFormatDetect(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT))
extern bit ScalerTMDSRxHdcpEnabled(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern bit ScalerTMDSRxCheckDataDFE(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern bit ScalerTMDSRxTMDSStableDetect(BYTE ucSourceType);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxHotPlugEvent(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxSwitchSlaveAddr(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxBeforeHotPlugEventProc(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxAfterHotPlugEventProc(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxHdcp1p4AksvClear(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxDviVideoSetting(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxFirstActiveProc(BYTE ucSourceType);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxPowerOffProc(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern BYTE ScalerTMDSRxTMDSVideoDetect(bit bWait);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxTMDSVideoDetectEvent(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxPSIntHandler_EXINT0(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern bit ScalerTMDSRxHdmiAviPixelRepInfoChanged(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern BYTE ScalerTMDSRxHdmiGetAVIInfo(EnumAviInfoContent enumContent);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern BYTE ScalerTMDSRxHdmiGetColorDepth(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON))
extern void ScalerTMDSRxHdmiPacketDetectEvent(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_HDMI_2_0_SUPPORT == _ON) && (_TMDS_HDMI_2_0_SCDC_RR_CTS_SUPPORT == _ON))
extern void ScalerTMDSRxHDMI2HPDRRIRQEnable(bit bEnable);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_HDMI_2_0_SUPPORT == _ON))
extern void ScalerTMDSRxHdmi2FormatResetEvent(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_HDMI_2_0_SUPPORT == _ON))
extern void ScalerTMDSRxReadRequestProc_EXINT0(BYTE ucRROutCome);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_HDMI_2_0_SUPPORT == _ON))
extern void ScalerTMDSRxReadRequestTimerEventEnable_WDINT(bit bEnable);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT))
extern bit ScalerTMDSRxHdmiDeepColorProc(WORD usTmdsClkCnt);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_HDMI_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT))
extern bit ScalerTMDSRxHdmiWaitDeepColorPllLock(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT) && (_D2_INPUT_PORT_TYPE != _D2_NO_PORT))
extern bit ScalerTMDSRxTMDSNormalPreDetect(void);
#endif
#if((_D2_TMDS_SUPPORT == _ON) && (_D2_INPUT_PORT_TYPE != _D2_DUAL_DVI_PORT) && (_D2_INPUT_PORT_TYPE != _D2_NO_PORT))
extern bit ScalerTMDSRxTMDSPSPreDetect(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxHotPlugLowProc(void);
#endif
#if(_D2_TMDS_SUPPORT == _ON)
extern void ScalerTMDSRxHotPlugHighProc(WORD usHpdTime);
#endif
#endif
