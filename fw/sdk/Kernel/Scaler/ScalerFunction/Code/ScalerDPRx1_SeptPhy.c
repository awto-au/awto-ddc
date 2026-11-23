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
// ID Code      : ScalerDPRx1_SeptPhy.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

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
#if(_D1_DP_EXIST == _ON)
BYTE g_ucDpRx1PhyCtsCtrl;
EnumHDCPType g_enumDpRx1HdcpMode;
StructDpLanesMapping isr_g_stDpRx1LanesMapping [[awto::isr_shared("main sets it at DP Rx1 init; EXINT0 and T0 only read the lane map")]];

#if(_DP_MST_SUPPORT == _ON)
StructDPRxMiscInfo g_stDpRx1MiscInfo;
BYTE g_pucDpRx1MstTimeSlotBackup[13];
BYTE g_pucDpMacRx1MstStMuxBackup[5];
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
StructDpLinkInfo g_stDpRx1LinkInfo;
#endif

DPRX_TP1INIT_DEF
BYTE g_ucDpRx1LTPatternSet;
BYTE g_ucDpRx1Tp1PermitSwingLevel0;


//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void ScalerDpRx1AVMute(void);
void ScalerDpRx1AdjustVsyncDelay(void);
bit ScalerDpRx1AlignCheck(void);
void ScalerDpRx1ScrambleSetting(void);

#if((_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON) && (_HW_DP_LANE_VALID_CHECK_SUPPORT == _ON))
bit ScalerDpRx1LaneValidCheck(void);
#endif

#if(_AWTO_HDCP == _ON)
void ScalerDpRx1CheckHdcpCpirqStatus(void);
#endif

#if(_FORMAT_CONVERSION_SUPPORT == _ON)
bit ScalerDpRx1CheckVgipVsBypass(void);
#endif

void ScalerDpRx1CrcCalculate(void);

#if(_DP_DYNAMIC_ADJUST_LINK_RATE_SUPPORT == _ON)
void ScalerDpRx1CalculateLinkRate(EnumDpLaneCount enumDpLaneCount);
#endif

#if(_HW_HS_TRACKING_GEN_TYPE == _HS_TRACKING_GEN_2)
void ScalerDpRx1HSActiveTrackingMode(EnumDpHSTrackingType enumHSTrackingType);
#endif
void ScalerDpRx1SetNoVideoStreamIRQ(bit bEn);
void ScalerDpRx1DpcdLinkStatusReset(EnumDpResetStatus enumDpResetStatus);
DWORD ScalerDpRx1GetBStoVSDelay(void);
BYTE ScalerDpRx1GetDpcdBitInfo(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucDpcdBit);
BYTE ScalerDpRx1GetDpcdInfo(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL);
bit ScalerDpRx1GetVideoStream(void);
EnumDpHotPlugTime ScalerDpRx1BeforeHpdToggleProc(EnumDpHotPlugAssertType enumHpdType);
void ScalerDpRx1AfterHpdToggleProc(void);
void ScalerDpRx1Initial(EnumDpVersionType enumDpVersion, EnumDpLaneCount enumDpLaneCount, EnumDPMSTPort enumDpRxMstPort, EnumFreeSyncSupport enumFreeSyncSupport);
bit ScalerDpRx1MarginLinkCheck(void);
void ScalerDpRx1LinkStatusIRQ(void);
void ScalerDpRx1AuxSet(void);
void ScalerDpRx1ErrorCounterUpdate_EXINT0(DPRX_PD1);
void ScalerDpRx1ErrorCounterDisable_EXINT0(void);
void ScalerDpRx1ErrorCounterEnable_EXINT0(DPRX_PD EnumDpLinkTrainingType enumDpLtType);

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
bit ScalerDpRx1DecodeErrorCountCheck(WORD usTimeCriteria, BYTE ucErrorCriteria);
bit ScalerDpRx1DecodeErrorCountLaneMeasure(BYTE ucErrorCriteria, BYTE ucDpRx1LaneNumber);
bit ScalerDpRx1LaneBsCheck(void);
#endif

bit ScalerDpRx1MSAActiveChange(void);
bit ScalerDpRx1PSPreDetect(void);
void ScalerDpRx1SetDpLaneMapping(EnumTypeCPinCfgType enumPinAssignment, EnumTypeCOrientation enumOrientation);
void ScalerDpRx1SecDataBlockReset(void);
void ScalerDpRx1SetDpcdBitValue(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucNotDpcdBit, BYTE ucDpcdBit);
void ScalerDpRx1SetDpcdValue(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucDpcdValue);
void ScalerDpRx1SinkStatusSet(EnumDpSinkReceivePort enumReceiverPort, EnumDpSinkStatus enumInSync);
void ScalerDpRx1ChangeHdcpDpcdCapability(bit bEn);

#if(_DP_RX1_ASSR_MODE_SUPPORT == _ON)
void ScalerDpRx1ASSRModeSetting(void);
#endif

#if(_DP_FREESYNC_SUPPORT == _ON)
bit ScalerDpRx1GetFREESYNCStatusChange(void);
void ScalerDpRx1SetFREESYNCMsaForLut(WORD usDpHtotal);
#endif

#if(_DP_MST_SUPPORT == _ON)
void ScalerDpRx1MstInfoBackup(EnumDpMstBackup enumDpMstBackup);

#if(_DP_TX_SUPPORT == _ON)
void ScalerDpRx1HDCPAuthShaRun(bit bIsFirst);
void ScalerDpRx1HDCPChangeAuthState(EnumDPRxHDCPAuthState enumHDCPAuthState);
bit ScalerDpRx1HDCPCheckBinfo(void);
bit ScalerDpRx1HDCPCheckLvp(void);
void ScalerDpRx1HDCPFakeAuthenProc(void);
void ScalerDpRx1HDCPHandler(void);
void ScalerDpRx1HDCPLoadKsvFifo(void);
void ScalerDpRx1HDCPLoadShaToDpcd(void);
void ScalerDpRx1HDCPSetKsvFifoFirst(void);
void ScalerDpRx1HDCPSetReadIrqTimeout(void);
void ScalerDpRx1HDCPSetRepeaterProcTimeout(void);
void ScalerDpRx1HDCPSha1Calculate(BYTE *pucInputArray, BYTE ucCalCount);
void ScalerDpRx1HDCPWriteShaInput(void);
#if(_DP_HDCP14_CTS_SUPPORT == _ON)
bit ScalerDpRx1HDCPDeviceCountChange(void);
#endif
void ScalerDpRx1MstToSstProc(void);
void ScalerDpRx1MstToSstSetColorInfo(void);
bit ScalerDpRx1MstToSstStableDetect(void);
#endif

#endif

#if(_DP_TX_SUPPORT == _ON)
void ScalerDpRx1UpdateSinkCount(BYTE ucSinkCount);
#endif

void ScalerDpRx1AdjustLaneFLDBand(BYTE ucDpRx1LaneNumber, WORD usVCOBandDiff);
bit ScalerDpRx1CDRCheck(BYTE ucDpLinkRate, BYTE ucDpcdLane);
void ScalerDpRx1CpIRQ(EnumDpRxBStatusType enumBStatusType);
#if(_DP_HDCP_2_2_SUPPORT == _ON)
void ScalerDpRx1CpIRQ_EXINT0(EnumDpRxBStatusType enumBStatusType);
#endif
bit ScalerDpRx1DFECheck(void);
bit ScalerDpRx1DecodeCheck(void);
bit ScalerDpRx1DisplayFormatSetting(void);
bit ScalerDpRx1FifoCheck(EnumDpFifoCheckCondition enumFifoCheckCondition);
void ScalerDpRx1HDCPBlockReset(void);
#if(_AWTO_HDCP == _ON)
bit ScalerDpRx1HdcpCheckValid(void);
bit ScalerDpRx1HdcpCheckEnabled(void);
bit ScalerDpRx1HdcpMeasureCheck(void);
bit ScalerDpRx1HdcpReAuthStatusCheck(void);
#endif
void ScalerDpRx1MacInitial(void);
bit ScalerDpRx1MeasureLaneCDRClk(BYTE ucDpLinkRate, BYTE ucDpRx1LaneNumber);

#if(_DP_LINK_RATE_CHANGE_WO_LT_SUPPORT == _ON)
void ScalerDpRx1LinkRateChangeRebuildPhy(void);
bit ScalerDpRx1LinkRateChange(void);
#endif

bit ScalerDpRx1NormalPreDetect(void);
bit ScalerDpRx1PhyCtsTp1Check(void);
bit ScalerDpRx1PhyCtsTp2Check(void);
void ScalerDpRx1PhyInitial(void);
BYTE ScalerDpRx1ScanInputPort(void);
void ScalerDpRx1SetDFEInitial(EnumDpLinkRate enumDpLinkRate);
void ScalerDpRx1SetFifoIRQ(bit bEn);
void ScalerDpRx1SetFifoWD(bit bEn);
bit ScalerDpRx1StableDetect(void);
void ScalerDpRx1ValidSignalDetectionActiveEvent(void);

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
void ScalerDpRx1TimingInfoBackup(void);
#endif

#if(_DP_MST_SUPPORT == _ON)
bit ScalerDpRx1LTStatusCheck(void);

#if(_DP_TX_SUPPORT == _ON)
void ScalerDpRx1HDCPEnableReadIrq(bit bEnable);
void ScalerDpRx1MstToSstAdjustVsyncDelay(void);
bit ScalerDpRx1MstToSstDisplayFormatSetting(void);
bit ScalerDpRx1MstToSstFifoCheck(EnumDpFifoCheckCondition enumFifoCheckCondition);
DWORD ScalerDpRx1MstToSstGetBStoVSDelay(void);
bit ScalerDpRx1MstToSstGetVideoInfo(void);
bit ScalerDpRx1MstToSstGetVideoStream(void);
bit ScalerDpRx1MstToSstMSAActiveChange(void);
bit ScalerDpRx1MstToSstMSACheck(void);
bit ScalerDpRx1MstToSstMeasureInput(void);
bit ScalerDpRx1MstToSstMiscCheck(void);
BYTE ScalerDpRx1MstToSstScanInputPort(void);
void ScalerDpRx1MstToSstVideoSetting(void);

#if(_DP_FREESYNC_SUPPORT == _ON)
WORD ScalerDpRx1MstToSstGetBStoHSDelay(WORD usDpHtotal);
#endif

#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)
bit ScalerDpRx1MstToSstVscCheck(void);
#endif

void ScalerDpRx1DfpDeviceDetailConfigReset(void);
void ScalerDpRx1DfpDeviceDetailConfig(void);
#endif

#endif

#endif // #End of #if(_D1_DP_EXIST == _ON)

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
#if(_D1_DP_EXIST == _ON)
//--------------------------------------------------
// Description  : DP RGB Output Disable
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1AVMute(void)
{
    if(ScalerGetBit(PB9_3A_DP_IRQ_CTRL0, (_BIT1 | _BIT0)) == (_BIT1 | _BIT0))
    {
        // Set free run & force to BG
        ScalerSetBit(P0_28_VIDEO_DISPLAY_CONTROL_REG, ~(_BIT5 | _BIT3), _BIT5);
    }

    // Disable fifo overflwo/ underflwo IRQ
    ScalerSetBit(PB9_3A_DP_IRQ_CTRL0, ~(_BIT1 | _BIT0), 0x00);

    // Disable RGB Output
    ScalerSetBit(PB8_31_DP_OUTPUT_CTRL, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

#if(_AUDIO_SUPPORT == _ON)
    // Disable Audio Channel
    ScalerAudioDpAudioEnable(_DISABLE, _D1_INPUT_PORT);
#endif
}
//--------------------------------------------------
// Description  : DP Adjust Vsync Delay
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1AdjustVsyncDelay(void)
{
    DWORD ulBStoVSDelayDeltaOverflow = 0;
    DWORD ulBStoVSDelayDeltaUnderflow = 0;

    if(ScalerGetBit(PB8_21_PG_CTRL_1, (_BIT1 | _BIT0)) == 0x00)// Fifo Ok
    {
        return;
    }
    else if(ScalerGetBit(PB8_21_PG_CTRL_1, _BIT0) == _BIT0) // Fifo Overflow
    {
        // Get Htotal
        ScalerRead(PB9_08_MSA_HTT_0, 2, &pData[0], _AUTOINC);

        // ((Link Clk * 256)/ Stream CLK) * Htotal / 256 --> 1 Line
        ulBStoVSDelayDeltaOverflow = (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 270UL) * 256) / ((DWORD)GET_INPUT_PIXEL_CLK()) * ((DWORD)PDATA_WORD(0)) / 256;

        DebugMessageRx1("7. Fifo Overflow --> nVidia Case", ulBStoVSDelayDeltaOverflow);
    }
    else if(ScalerGetBit(PB8_21_PG_CTRL_1, _BIT1) == _BIT1) // Fifo Underflow
    {
        // Get Hactive
        ScalerRead(PB9_0C_MSA_HWD_0, 2, &pData[0], _AUTOINC);

        if(PDATA_WORD(0) != 1366)
        {
            return;
        }

        PDATA_WORD(0) = PDATA_WORD(0) - 2;

        // Set Hactive
        ScalerSetByte(PB8_45_MN_DPF_HWD_M, pData[0]);
        ScalerSetByte(PB8_46_MN_DPF_HWD_L, pData[1]);

        // ((Link Clk * 2)/ Stream CLK) --> 2 pixels
        ulBStoVSDelayDeltaUnderflow = (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 270) * 2) / ((DWORD)GET_INPUT_PIXEL_CLK());

        DebugMessageRx1("7. Fifo Underflow --> QD882 Case", ulBStoVSDelayDeltaUnderflow);
    }

    // For Initial Value Before Use PDATA_DWORD(0)
    pData[0] = 0;

    // Get BStoVSDelay Even
    ScalerRead(PB8_32_EVBLK2VS_H, 3, &pData[1], _AUTOINC);

    // For Initial Value Before Use PDATA_DWORD(1)
    pData[4] = 0;

    // Get BStoVSDelay Odd
    ScalerRead(PB8_35_OVBLK2VS_H, 3, &pData[5], _AUTOINC);

    // BStoVSDelay = BStoVSDelay + (Nvid * 256 / Mvid) * ((DWORD)Htotal) / 256;
    PDATA_DWORD(0) = PDATA_DWORD(0) - ((ulBStoVSDelayDeltaOverflow + ulBStoVSDelayDeltaUnderflow) / 2);

    // BStoVSDelay = BStoVSDelay + (Nvid * 256 / Mvid) * ((DWORD)Htotal) / 256;
    PDATA_DWORD(1) = PDATA_DWORD(1) - ((ulBStoVSDelayDeltaOverflow + ulBStoVSDelayDeltaUnderflow) / 2);

    // Set Even Field BS to VS Delay
    ScalerSetByte(PB8_32_EVBLK2VS_H, pData[1]);
    ScalerSetByte(PB8_33_EVBLK2VS_M, pData[2]);
    ScalerSetByte(PB8_34_EVBLK2VS_L, pData[3]);

    // Set Odd Field BS to VS Delay
    ScalerSetByte(PB8_35_OVBLK2VS_H, pData[5]);
    ScalerSetByte(PB8_36_OVBLK2VS_M, pData[6]);
    ScalerSetByte(PB8_37_OVBLK2VS_L, pData[7]);

    // Enable Double Buffer
    ScalerSetBit(PB8_30_DPF_CTRL_0, ~_BIT6, _BIT6);

    // Reset Display Format Gen
    ScalerSetBit(PB8_30_DPF_CTRL_0, ~_BIT7, 0x00);
    ScalerSetBit(PB8_30_DPF_CTRL_0, ~_BIT7, _BIT7);

    // Polling Vertical BS
    ScalerTimerPollingFlagProc(50, PB9_01_DP_VBID, _BIT0, _TRUE);

    // Delay for PG Stable
    ScalerTimerDelayXms(AWTO_DP_ONE_FRAME());
}
//--------------------------------------------------
// Description  : Check Valid Lane Alignment
// Input Value  : None
// Output Value : True --> Align
//--------------------------------------------------
bit ScalerDpRx1AlignCheck(void)
{
#if(_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON)

    if(GET_DP_ILLEGAL_IDLE_PATTERN_CHECK() == _TRUE)
    {
        if(GET_DP_RX1_SOURCE_TYPE_JUDGE() == _FALSE)
        {
#if(_HW_DP_LANE_VALID_CHECK_SUPPORT == _ON)
            if(ScalerDpRx1LaneValidCheck() == _FALSE)
            {
                return _TRUE;
            }
#else
            return _TRUE;
#endif
        }
    }

#endif

    if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F) == _DP_ONE_LANE)
    {
        return _TRUE;
    }
    else
    {
        if(ScalerGetBit(PB0_0E_DESKEW_PHY, _BIT4) == 0x00)
        {
            if(ScalerGetBit(PB0_0E_DESKEW_PHY, (_BIT7 | _BIT6)) != (_BIT7 | _BIT6))
            {
                ScalerSetBit(PB0_0E_DESKEW_PHY, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

                ScalerTimerDelayXms(3);
            }
            else
            {
                return _FALSE;
            }
        }
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : DP Scramble Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ScrambleSetting(void)
{
    BYTE ucBackUp = ScalerGetByte(PBA_D0_AUX_MODE_SET);
    bit bEnhanceChange = _FALSE;
    bit bScrambleChange = _FALSE;

    SET_DP_RX1_AUX_MANUAL_MODE();

    if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x01, 0x01, _BIT7) == _BIT7) != (ScalerGetBit(PB0_01_PHY_DIG_RESET_CTRL, _BIT2) == _BIT2))
    {
        bEnhanceChange = _TRUE;

        if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x01, 0x01, _BIT7) == _BIT7)
        {
            // Enable Enhancement Control Mode --> MAC
            ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT2, _BIT2);
        }
        else
        {
            // Disable Enhancement Control Mode --> MAC
            ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT2, 0x00);
        }
    }

    if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x01, 0x02, _BIT5) == _BIT5) != (ScalerGetBit(PB0_07_SCRAMBLE_CTRL, _BIT5) == _BIT5))
    {
        bScrambleChange = _TRUE;

        if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x01, 0x02, _BIT5) == _BIT5)
        {
            // Disable Scrambling
            ScalerSetBit(PB0_07_SCRAMBLE_CTRL, ~_BIT5, _BIT5);
        }
        else
        {
            // Enable Scrambling
            ScalerSetBit(PB0_07_SCRAMBLE_CTRL, ~_BIT5, 0x00);
        }
    }

    if((bEnhanceChange == _TRUE) || (bScrambleChange == _TRUE))
    {
        SET_DP_RX1_AUX_AUTO_MODE();

        // Delay 2ms for Scramble
        ScalerTimerDelayXms(2);

        SET_DP_RX1_AUX_MANUAL_MODE();
    }

    if((ucBackUp & _BIT1) == _BIT1)
    {
        SET_DP_RX1_AUX_AUTO_MODE();
    }
}

#if((_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON) && (_HW_DP_LANE_VALID_CHECK_SUPPORT == _ON))
//--------------------------------------------------
// Description  : Check Lane Valid
// Input Value  : None
// Output Value : True --> ok, False --> Lane Valid Error
//--------------------------------------------------
bit ScalerDpRx1LaneValidCheck(void)
{
    // Enable Lane Valid Detect
    ScalerSetBit(PB0_00_HD_DP_SEL, ~_BIT3, 0x00);
    ScalerSetBit(PB0_00_HD_DP_SEL, ~_BIT3, _BIT3);

    // Delay Time us [150,x]
    DELAY_XUS(150);

    switch(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)
    {
        case _DP_ONE_LANE:

            if(((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (ScalerGetBit(PB0_00_HD_DP_SEL, _BIT7) == 0x00)) ||
               ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (ScalerGetBit(PB0_00_HD_DP_SEL, _BIT6) == 0x00)) ||
               ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (ScalerGetBit(PB0_00_HD_DP_SEL, _BIT5) == 0x00)) ||
               ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (ScalerGetBit(PB0_00_HD_DP_SEL, _BIT4) == 0x00)))
            {
                return _FALSE;
            }

            break;

        case _DP_TWO_LANE:

            if(((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT7 | _BIT6)) == 0x00)) ||
               ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT7 | _BIT5)) == 0x00)) ||
               ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT7 | _BIT4)) == 0x00)) ||
               ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT6 | _BIT5)) == 0x00)) ||
               ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT6 | _BIT4)) == 0x00)) ||
               ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2))) &&
                (ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT5 | _BIT4)) == 0x00)))
            {
                return _FALSE;
            }

            break;

        case _DP_FOUR_LANE:

            if(ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT7 | _BIT6 | _BIT5 | _BIT4)) == 0x00)
            {
                return _FALSE;
            }

            break;

        default:

            return _FALSE;

            break;
    }

    return _TRUE;
}
#endif

#if(_AWTO_HDCP == _ON)
//--------------------------------------------------
// Description  : Clear CPIRQ Flag
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1CheckHdcpCpirqStatus(void)
{
    if((ScalerGetByte(PB0_1E_HDCP_INTGT_VRF_ANS_MSB) == 0x53) && (ScalerGetByte(PB0_1F_HDCP_INTGT_VRF_ANS_LSB) == 0x1F))
    {
        if((ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x01) & _BIT2) == _BIT2)
        {
#if(_DP_HDCP_2_2_SUPPORT == _ON)
            // Check HDCP22 decode
            if(GET_DP_RX1_HDCP_MODE() == _HDCP_22)
            {
                if(ScalerDpRx1GetDpcdInfo(0x06, 0x94, 0x93) == 0x00)
                {
                    // Clear Link Status CPIRQ Flag
                    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x01, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x01) & ~_BIT2));
                }
            }
            else
#endif
            {
                if(ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x29) == 0x00)
                {
                    // Clear Link Status CPIRQ Flag
                    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x01, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x01) & ~_BIT2));
                }
            }
        }
    }
}

#endif

#if(_FORMAT_CONVERSION_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check VGIP VS bypass for DP
// Input Value  : None
// Output Value : _TRUE / _FALSE
//--------------------------------------------------
bit ScalerDpRx1CheckVgipVsBypass(void)
{
    // Get Hstart
    ScalerRead(PB8_43_MN_DPF_HST_M, 2, &pData[0], _AUTOINC);

    // Get Vstart
    ScalerRead(PB8_4B_MN_DPF_VST_M, 2, &pData[2], _AUTOINC);

    // Check for nVedia 2560x1440@144Hz timing (reduced blanking)
    if((PDATA_WORD(0) < _VGIP_IH_CAPTURE_MIN_VALUE) ||
       (PDATA_WORD(1) <= _VGIP_IV_CAPTURE_MIN_VALUE))
    {
        DebugMessageRx1("DP RX1 VGIP VS Bypass Mode", PDATA_WORD(0));

        return _TRUE;
    }

    return _FALSE;
}
#endif

//--------------------------------------------------
// Description  : DP CRC Calculate
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1CrcCalculate(void)
{
    if(GET_DP_RX1_CRC_CALCULATE() == _TRUE)
    {
        DebugMessageRx1("7. DP CRC Test Start", 0);

        if(GET_COLOR_SPACE() == _COLOR_SPACE_YCBCR422)
        {
            ScalerSetBit(PB8_70_DP_CRC_CTRL, ~_BIT4, _BIT4);
        }
        else
        {
            ScalerSetBit(PB8_70_DP_CRC_CTRL, ~_BIT4, 0x00);
        }

        // Start CRC Calculation
        ScalerSetBit(PB8_70_DP_CRC_CTRL, ~_BIT7, _BIT7);

        if(ScalerTimerPollingFlagProc(_DP_MEASURE_POLLING_TIMEOUT, PB8_70_DP_CRC_CTRL, _BIT6, _TRUE) == _TRUE)
        {
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x40, ScalerGetByte(PB8_72_DP_CRC_R_L));
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x41, ScalerGetByte(PB8_71_DP_CRC_R_M));
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x42, ScalerGetByte(PB8_74_DP_CRC_G_L));
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x43, ScalerGetByte(PB8_73_DP_CRC_G_M));
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x44, ScalerGetByte(PB8_76_DP_CRC_B_L));
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x45, ScalerGetByte(PB8_75_DP_CRC_B_M));

            CLR_DP_RX1_CRC_CALCULATE();

            // Update _TEST_CRC_COUNT
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x46, 0x21);
        }

        // Stop CRC Calculation
        ScalerSetBit(PB8_70_DP_CRC_CTRL, ~_BIT7, 0x00);
    }
}

#if(_DP_DYNAMIC_ADJUST_LINK_RATE_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Link Rate Set
// Input Value  : MST Port and Lane Count
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1CalculateLinkRate(EnumDpLaneCount enumDpLaneCount)
{
    BYTE ucLinkRate = 0;

    if((ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x00) >= _DP_VERSION_1_2) || (ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == _BIT7))
    {
        if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x21, _BIT0) == 0x00)
        {
#if(_D1_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)

            ucLinkRate = DP_LINK_RATE_ADJUST(enumDpLaneCount, _INPUTCLOCK_RANG_USBC);

            if(ucLinkRate > _D1_DP_LINK_CLK_RATE)
            {
                ucLinkRate = _D1_DP_LINK_CLK_RATE;
            }

            if(ucLinkRate >= _DP_HIGH_SPEED2_540MHZ)
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _DP_LINK_HBR2);
            }
            else
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, ucLinkRate);
            }

            // When Define Extended Rx Cap Should Set DPCD 0x02201
#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
            ScalerDpRx1SetDpcdValue(0x00, 0x22, 0x01, ucLinkRate);
#else
            isr_g_ucDpRx1DPCD02201hValue = ucLinkRate;
#endif

#else // Else of #if(_D1_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)

            ucLinkRate = DP_LINK_RATE_ADJUST(enumDpLaneCount, _INPUTCLOCK_RANG_DP);

            if(ucLinkRate > _D1_DP_LINK_CLK_RATE)
            {
                ucLinkRate = _D1_DP_LINK_CLK_RATE;
            }

            if(ucLinkRate >= _DP_HIGH_SPEED2_540MHZ)
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _DP_LINK_HBR2);
            }
            else
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, ucLinkRate);
            }

            // When Define Extended Rx Cap Should Set DPCD 0x02201
#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
            ScalerDpRx1SetDpcdValue(0x00, 0x22, 0x01, ucLinkRate);
#else
            isr_g_ucDpRx1DPCD02201hValue = ucLinkRate;
#endif

#endif // End of #if(_D1_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
        }
        else
        {
            if(_D1_DP_LINK_CLK_RATE >= _DP_HIGH_SPEED2_540MHZ)
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _DP_LINK_HBR2);
            }
            else
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _D1_DP_LINK_CLK_RATE);
            }

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
            // When Define Extended Rx Cap Should Set DPCD 0x02201
            ScalerDpRx1SetDpcdValue(0x00, 0x22, 0x01, _D1_DP_LINK_CLK_RATE);
#else
            // When Define Extended Rx Cap Should Set DPCD 0x02201
            isr_g_ucDpRx1DPCD02201hValue = _D1_DP_LINK_CLK_RATE;
#endif
        }
    }
}
#endif

#if(_HW_HS_TRACKING_GEN_TYPE == _HS_TRACKING_GEN_2)
//--------------------------------------------------
// Description  : DP Hs Tracking Active Region Setting
// Input Value  : Hs Tracking Type
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HSActiveTrackingMode(EnumDpHSTrackingType enumHSTrackingType)
{
    if(enumHSTrackingType == _DP_HS_TRACKING_FW_MODE)
    {
        // HS Tracking Region By FW Setting
        ScalerSetBit(PB8_B9_MN_SCLKG_SDM_TEST, ~_BIT7, _BIT7);

        // BE Start Num = 2 line
        ScalerSetBit(PB8_C7_VBID_MAN_MADE, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), _BIT5);

        // BE End Num = 2 line
        ScalerSetBit(PB8_C7_VBID_MAN_MADE, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT1);
    }
    else
    {
        // HS Tracking Region By FW Setting
        ScalerSetBit(PB8_B9_MN_SCLKG_SDM_TEST, ~_BIT7, 0x00);
    }
}
#endif

//--------------------------------------------------
// Description  : Enable DP Fifo Under/OverFlow IRQ
// Input Value  : _ENABLE/ DISABLE
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetNoVideoStreamIRQ(bit bEn)
{
    // VB-ID[3] Change Flag
    ScalerSetBit(PB9_36_DP_GLB_STATUS, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), _BIT6);

    // VB-ID[3] Change IRQ
    ScalerSetBit(PB9_3B_DP_IRQ_CTRL1, ~_BIT4, ((bEn == _ENABLE) ? _BIT4 : 0x00));
}

//--------------------------------------------------
// Description  : DPCD Link Status Field Reset
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1DpcdLinkStatusReset(EnumDpResetStatus enumDpResetStatus)
{
    DebugMessageRx1("DP Rx1 Dpcd Link Status Reset", 0);

    pData[0] = ScalerGetByte(PBA_D0_AUX_MODE_SET);

    SET_DP_RX1_AUX_MANUAL_MODE();

    if(enumDpResetStatus == _DP_DPCD_LINK_STATUS_INITIAL)
    {
        // Set DPCD 00600h to 0x01
        ScalerDpRx1SetDpcdBitValue(0x00, 0x06, 0x00, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);
    }

    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x02, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x03, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x04, 0x80);
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x05, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x06, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x07, 0x00);

    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_LINK_TRAINING_NONE);

    CLR_DP_RX1_BACKUP_PD_LINK_STATUS_FLG();

    if((pData[0] & _BIT1) == _BIT1)
    {
        SET_DP_RX1_AUX_AUTO_MODE();
    }

#if(_DP_MST_SUPPORT == _ON)

    if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
    {
        pData[0] = ScalerGetByte(PBA_D0_AUX_MODE_SET);

        SET_DP_RX1_AUX_AUTO_MODE();

        pData[1] = ScalerDpRx1GetDpcdInfo(0x00, 0x20, 0x05);
        ScalerDpRx1SetDpcdValue(0x00, 0x20, 0x05, (pData[1] | _BIT1));

        ScalerDpRx1SetDpcdValue(0x00, 0x02, 0xC0, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0xC0) & ~_BIT1));

        if((pData[0] & _BIT1) != _BIT1)
        {
            SET_DP_RX1_AUX_MANUAL_MODE();
        }
    }

#endif
}
//--------------------------------------------------
// Description  : DP BS to VS Delay Calculation
// Input Value  : None
// Output Value : BS to VS Delay
//--------------------------------------------------
DWORD ScalerDpRx1GetBStoVSDelay(void)
{
    DWORD ulVFrontPorch = 0;
    DWORD ulHFrontPorch = 0;
    WORD usFifoOffset = 0;

    // Get Htotal
    ScalerRead(PB9_08_MSA_HTT_0, 2, &pData[2], _AUTOINC);

    // VFrontPorch = 3 * Htotal * (Link Clk / Stream CLK)
    ulVFrontPorch = ((DWORD)GET_DP_RX1_VFRONT_PORCH()) * ((DWORD)PDATA_WORD(1) * 256) / ((DWORD)GET_INPUT_PIXEL_CLK()) *
                    ((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 270) / 256;

    // Get Hactive
    ScalerRead(PB9_0C_MSA_HWD_0, 2, pData, _AUTOINC);

    // Get HSW
    pData[4] = ScalerGetBit(PB9_0E_MSA_HSW_0, (_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
    pData[5] = ScalerGetByte(PB9_0F_MSA_HSW_1);

    // Get HSW min by Measure clock
    PDATA_WORD(3) = ((DWORD) _DP_HSYNC_WIDTH_MEASURE_COUNTER * GET_INPUT_PIXEL_CLK() * 100) / _MEASURE_CLK + 1;

    // Check HSW <= HSW min
    if(PDATA_WORD(2) <= PDATA_WORD(3))
    {
        // Check if H porch is more than HSW min
        if((PDATA_WORD(1) - PDATA_WORD(0)) >= PDATA_WORD(3))
        {
            // HSW = HSW min
            PDATA_WORD(2) = PDATA_WORD(3);
        }
        else
        {
            // HSW = Max H Porch
            PDATA_WORD(2) = (PDATA_WORD(1) - PDATA_WORD(0));
        }
    }

    // DPF H Front Porch must not be less than 8 (HW constraint)
    // Check if H porch is more than 8
    if((PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(2)) <= _DP_HSYNC_FRONT_PORCH)
    {
        // HSW < HSW min
        if(PDATA_WORD(2) < PDATA_WORD(3))
        {
            // Hstart = HSW
            PDATA_WORD(4) = PDATA_WORD(2);
        }
        else if((PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(3) >= _DP_HSYNC_FRONT_PORCH))
        {
            // HSW = H porch - _DP_HSYNC_FRONT_PORCH
            PDATA_WORD(2) = PDATA_WORD(1) - PDATA_WORD(0) - _DP_HSYNC_FRONT_PORCH;

            // Hstart = HSW
            PDATA_WORD(4) = PDATA_WORD(2);
        }
        else
        {
            // HSW = HSW min
            PDATA_WORD(2) = PDATA_WORD(3);

            // Hstart = HSW min
            PDATA_WORD(4) = PDATA_WORD(3);
        }
    }
    else
    {
        // Hstart = Htotal - Hactive - _DP_HSYNC_FRONT_PORCH
        PDATA_WORD(4) = PDATA_WORD(1) - PDATA_WORD(0) - _DP_HSYNC_FRONT_PORCH;
    }

    // HFrontPorch = (Htotal - Hactive - Hstart) * (Link Clk / Stream CLK)
    ulHFrontPorch = (((DWORD)(PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(4))) * (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270) / ((DWORD)GET_INPUT_PIXEL_CLK()));

    pData[15] = GET_COLOR_DEPTH();

    // DP fifo size = 256 x 96bit
    if(GET_COLOR_SPACE() == _COLOR_SPACE_YCBCR422)
    {
        // FifoOffset = (1/2 * (256 * 96) / (2 * depth per color)), color format is YCbCr 4:2:2
        usFifoOffset = _HW_DP_RX_VIDEO_FIFO_SIZE / (4 * (WORD)pData[15]);
    }
    else
    {
        // FifoOffset = (1/2 * (256 * 96) / (3 * depth per color)), color format is RGB or YCbCr 4:4:4 or others
        usFifoOffset = _HW_DP_RX_VIDEO_FIFO_SIZE / (6 * (WORD)pData[15]);
    }

    // FifoOffset = (1/2 * (256 * 96) / (3 * depth per color)) * (Link Clk / Stream CLK))
    usFifoOffset = (WORD)(((DWORD)usFifoOffset) * (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270) / ((DWORD)GET_INPUT_PIXEL_CLK()));

    return ((ulVFrontPorch + ulHFrontPorch + (DWORD)usFifoOffset) / 2);
}
//--------------------------------------------------
// Description  : Get DPCD Table Information
// Input Value  : ucDpcdAccessPortH --> High Byte of DPCD Address
//                ucDpcdAccessPortM --> Middle Byte of DPCD Address
//                ucDpcdAccessPortL --> Low Bye of DPCD Adress
// Output Value : DPCD Information
//--------------------------------------------------
BYTE ScalerDpRx1GetDpcdBitInfo(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucDpcdBit)
{
    // Release Aux
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT7, 0x00);

    ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, ucDpcdAccessPortH);
    ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, ucDpcdAccessPortM);
    ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, ucDpcdAccessPortL);

    AWTO_DPCD_SETTLE() return ScalerGetBit(PBA_C4_DPCD_DATA_PORT, ucDpcdBit);
}
//--------------------------------------------------
// Description  : Get DPCD Table Information
// Input Value  : ucDpcdAccessPortH --> High Byte of DPCD Address
//                ucDpcdAccessPortM --> Middle Byte of DPCD Address
//                ucDpcdAccessPortL --> Low Bye of DPCD Adress
// Output Value : DPCD Information
//--------------------------------------------------
BYTE ScalerDpRx1GetDpcdInfo(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL)
{
    // Release Aux
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT7, 0x00);

    ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, ucDpcdAccessPortH);
    ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, ucDpcdAccessPortM);
    ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, ucDpcdAccessPortL);

    AWTO_DPCD_SETTLE() return ScalerGetByte(PBA_C4_DPCD_DATA_PORT);
}
//--------------------------------------------------
// Description  : Check Dp Video Straam VBID
// Input Value  : None
// Output Value : True --> Get Video Stream
//--------------------------------------------------
bit ScalerDpRx1GetVideoStream(void)
{
#if(_DP_MST_SUPPORT == _ON)
    if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
    {
        // Check if ST_Source is Assigned the STx Stream In MST Mode
        if((ScalerGetBit(PB0_01_PHY_DIG_RESET_CTRL, _BIT7) == _BIT7) &&
           (ScalerGetBit(PB8_0D_SOURCE_SEL_0, (_BIT6 | _BIT5 | _BIT4)) == 0x00))
        {
            return _FALSE;
        }
    }
#endif

    if(ScalerGetBit(PB9_01_DP_VBID, _BIT3) == 0x00)
    {
        return _TRUE;
    }

    return _FALSE;
}

//--------------------------------------------------
// Description  : Dp Before Hpd Toggle Process
// Input Value  : EnumDpHotPlugAssertType
// Output Value : None
//--------------------------------------------------
EnumDpHotPlugTime ScalerDpRx1BeforeHpdToggleProc(EnumDpHotPlugAssertType enumHpdType)
{
    if(enumHpdType == _DP_HPD_NONE)
    {
        return _DP_HPD_TIME_NONE;
    }

    if(enumHpdType == _DP_HPD_ASSERTED)
    {
        if(PCB_D1_HOTPLUG_DETECT() == _D1_HOT_PLUG_HIGH)
        {
            return _DP_HPD_TIME_NONE;
        }
    }

    ScalerTimerWDCancelTimerEvent(_SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY); AWTO_DP_FRAME_CLEAR();     // HPD toggle: the next source may run at another rate
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HOTPLUG_ASSERTED);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_LONG_HOTPLUG_EVENT);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_LINK_STATUS_IRQ);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_VALID_SIGNAL_DETECT_CHECK);

#if((_DP_HDCP_2_2_SUPPORT == _ON) && (_WD_TIMER_INT_SUPPORT == _ON))
    ScalerTimerWDCancelTimerEvent(_SCALER_WD_TIMER_EVENT_DP_RX1_HDCP2_SKE);
#endif

#if(_DP_MST_SUPPORT == _ON)
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_AUX_CH_NO_POWER_CHECK_DEBOUNCE);
#if(_DP_TX_SUPPORT == _ON)
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_CPIRQ_EVENT);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_REPEATER_PROC_TIMEOUT);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_READ_IRQ_TIMEOUT);
#endif
#endif

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
    if((enumHpdType != _DP_HDCP_LONG_HPD_EVENT) && (enumHpdType != _DP_HBR2_MARGIN_LINK_HPD_EVENT) && ((ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x00) >= _DP_VERSION_1_2) || (ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == _BIT7)))
    {
#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
        if(((ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == 0x00) && (ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x01) < _D1_DP_LINK_CLK_RATE)) ||
           ((ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == _BIT7) && (ScalerDpRx1GetDpcdInfo(0x00, 0x22, 0x01) < _D1_DP_LINK_CLK_RATE)))
#else
        if(((ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == 0x00) && (ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x01) < _D1_DP_LINK_CLK_RATE)) ||
           ((ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x0E, _BIT7) == _BIT7) && (isr_g_ucDpRx1DPCD02201hValue < _D1_DP_LINK_CLK_RATE)))
#endif
        {
            if(_D1_DP_LINK_CLK_RATE >= _DP_HIGH_SPEED2_540MHZ)
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _DP_LINK_HBR2);
            }
            else
            {
                ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x01, _D1_DP_LINK_CLK_RATE);
            }

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
            // When Define Extended Rx Cap Should Set DPCD 0x02201
            ScalerDpRx1SetDpcdValue(0x00, 0x22, 0x01, _D1_DP_LINK_CLK_RATE);
#else
            // When Define Extended Rx Cap Should Set DPCD 0x02201
            isr_g_ucDpRx1DPCD02201hValue = _D1_DP_LINK_CLK_RATE;
#endif
            DebugMessageRx1("Flag Clear_Hotplug Event_D1", _D1_DP_LINK_CLK_RATE);
        }
    }
#endif

#if(_DP_DYNAMIC_ADJUST_LINK_RATE_SUPPORT == _ON)
    if(enumHpdType != _DP_HBR2_MARGIN_LINK_HPD_EVENT)
    {
        ScalerDpRx1CalculateLinkRate(GET_DP_RX_D1_PORT_TARGET_LANE_COUNT());
    }
#endif

    if(enumHpdType != _DP_HPD_ASSERTED)
    {
        ScalerDpRx1AVMute();

        ScalerDpRx1DpcdLinkStatusReset(_DP_DPCD_LINK_STATUS_INITIAL);

#if(_DP_MST_SUPPORT == _ON)
        if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
        {
            ScalerDpRx1MstInfoBackup(_DP_MST_BACKUP_INFO);

            ScalerDpMstReset(_DP_MST_RX1_PORT);
        }
#endif

#if(_DP_TX_SUPPORT == _ON)
        if(GET_DP_RX_HDCP_UPSTREAM_PORT() == _HDCP_D1_PORT)
        {
            ScalerDpTxForceIdlePatternSetting();
        }
#endif

#if(_DP_HPD_LOW_AUX_NOT_REPLY_SUPPORT == _ON)
        // Reset Aux Phy
        ScalerSetBit(PBA_65_AUX_5, ~_BIT7, 0x00);
#endif
    }

    if(enumHpdType == _DP_HPD_LOW)
    {
        DebugMessageRx1("_D1_HOT_PLUG_LOW", 0);

        PCB_D1_HOTPLUG(_D1_HOT_PLUG_LOW);

        return _DP_HPD_TIME_NONE;
    }
    else if(enumHpdType == _DP_HPD_LOW_RESET_AUX)
    {
        // Reset Aux Phy
        ScalerSetBit(PBA_65_AUX_5, ~_BIT7, 0x00);

        DebugMessageRx1("_D1_HOT_PLUG_LOW", 0);

        PCB_D1_HOTPLUG(_D1_HOT_PLUG_LOW);

        return _DP_HPD_TIME_NONE;
    }

    // Reset DDC1
    MCU_FF2D_DDC1_DDC_CONTROL_1 |= _BIT1;

#if(_DP_FREESYNC_SUPPORT == _ON)
    SET_DP_RX1_AUX_MANUAL_MODE();
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0x07, 0x00);
    SET_DP_RX1_AUX_AUTO_MODE();
#endif

    ScalerDpRx1HDCPUnplugReset();

#if(_D1_DP_ASSR_MODE_SUPPORT == _ON)
    SET_DP_RX1_AUX_MANUAL_MODE();
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0x0A, 0x00);
    SET_DP_RX1_AUX_AUTO_MODE();
#endif

    if(enumHpdType == _DP_LONG_HPD_EVENT)
    {
        return _DP_LONG_HPD_TIME;
    }
    else if(enumHpdType == _DP_HDCP_LONG_HPD_EVENT)
    {
        return _DP_HDCP_LONG_HPD_TIME;
    }
    else if(enumHpdType == _DP_MST_LONG_HPD_EVENT)
    {
        // Reset Aux Phy
        ScalerSetBit(PBA_65_AUX_5, ~_BIT7, 0x00);

#if((_DP_TX_SUPPORT == _ON) && (_D1_DP_MST_PORT_SUPPORT == _ON))
        // No Receiving Topology Rebuild MSG within 4s
        if(GET_DP_TX_WAIT_TOPOLOGY_REBUILD_MSG() == _TRUE)
        {
            CLR_DP_TX_WAIT_TOPOLOGY_REBUILD_MSG();

            return _DP_MST_FORCE_LONG_HPD_TIME;
        }
        else
#endif
        {
            return _DP_MST_LONG_HPD_TIME;
        }
    }
#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
    else if(enumHpdType == _DP_HBR2_MARGIN_LINK_HPD_EVENT)
    {
        return _DP_HBR2_MARGIN_LINK_HPD_TIME;
    }
#endif
    else if(enumHpdType == _DP_HPD_ASSERTED)
    {
        return _DP_HPD_ASSERTED_TIME;
    }

    return _DP_HPD_TIME_NONE;
}

//--------------------------------------------------
// Description  : Dp After Hpd Toggle Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1AfterHpdToggleProc(void)
{
    // Release Aux Phy
    ScalerSetBit(PBA_65_AUX_5, ~_BIT7, _BIT7); AWTO_LT_LOG_M(0x20) AWTO_DPCD_PROBE_RUN()

    SET_DP_RX1_AUX_MANUAL_MODE();

    if((GET_DP_RX1_LINK_TRAINING_STATUS() != _DP_NORMAL_LINK_TRAINING_PASS) && (GET_DP_RX1_LINK_TRAINING_STATUS() != _DP_FAKE_LINK_TRAINING_PASS))
    {
        ScalerDpRx1SetDpcdValue(0x00, 0x01, 0x00, 0x00); AWTO_LT_LOG_V(0x21, 0)
        ScalerDpRx1SetDpcdValue(0x00, 0x01, 0x01, (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0xE0));
    }

    SET_DP_RX1_AUX_AUTO_MODE();

    if(ScalerSyncDpCableStatus(_D1_INPUT_PORT) == _TRUE)
    {
        ScalerDpRx1ValidSignalDetectionActiveEvent();

#if(_DP_TX_SUPPORT == _ON)
#if(_DP_DPCD_DFP_PRESENT_REF_TO == _DP_MST_CAPABILITY)
        if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x21, _BIT0) == 0x00)
        {
            ScalerDpRx1UpdateSinkCount(1);
        }
        else
#endif
        {
            ScalerDpRx1UpdateSinkCount(GET_DP_TX_DOWNSTREAM_SINK_COUNT() + 1);
        }
#endif
    }
}

//--------------------------------------------------
// Description  : Initial Setting for DP
// Input Value  : _DP_VERSION_1_1 or _DP_VERSION_1_2
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1Initial(EnumDpVersionType enumDpVersion, EnumDpLaneCount enumDpLaneCount, EnumDPMSTPort enumDpRxMstPort, EnumFreeSyncSupport enumFreeSyncSupport)
{
    ScalerDpRx1AuxPowerOnInitial();

    ScalerDpRx1DpcdInitial(enumDpVersion, enumDpLaneCount, enumDpRxMstPort, enumFreeSyncSupport);

    // Must be initialized "AFTER DPCD setting" to avoid entering interruption unexpectively
    ScalerDpRx1AuxIntInitial();

    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_LINK_TRAINING_NONE);

    SET_DP_RX1_FAKE_LINK_TRAINING();

    SET_DP_RX_TARGET_MST_PORT(enumDpRxMstPort);
    SET_DP_RX_D1_PORT_TARGET_VERSION(enumDpVersion);
    SET_DP_RX_D1_PORT_TARGET_LANE_COUNT(enumDpLaneCount);

    SET_DP_RX1_HDCP_MODE_BACKUP(_HDCP_14);

    ScalerDpRx1SetDpLaneMapping(_TYPE_C_PIN_ASSIGNMENT_C, _TYPE_C_ORIENTATION_UNFLIP);

#if(_DP_MST_SUPPORT == _ON)
    CLR_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE();
    CLR_DP_RX1_CHECK_AUX_CH_POWER_STATUS();
#endif

#if(_DP_TX_SUPPORT == _ON)
    CLR_DP_RX1_HDCP_AUTH_AKSV_WRITTEN();
#endif
}

//--------------------------------------------------
// Description  : DP Margin Link Check
// Input Value  : None
// Output Value : _TRUE : Link ok ; _FALSE : Margin Link
//--------------------------------------------------
bit ScalerDpRx1MarginLinkCheck(void)
{
    switch(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00))
    {
        case _DP_LINK_HBR2:

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
            if((ScalerDpRx1DFECheck() == _TRUE) &&
               (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE) &&
               (ScalerDpRx1LaneBsCheck() == _TRUE) &&
               (ScalerDpRx1DecodeErrorCountCheck(_DP_HBR2_MARGIN_LINK_TIME_CRITERIA, _DP_HBR2_MARGIN_LINK_ERROR_CRITERIA) == _FALSE))
            {
                if((ScalerDpRx1DFECheck() == _TRUE) &&
                   (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE) &&
                   (ScalerDpRx1LaneBsCheck() == _TRUE))
                {
                    if(ScalerSyncDpCableStatus(_D1_INPUT_PORT) == _TRUE)
                    {
                        SET_DP_RX_D1_MARGIN_LINK_HBR2();
                        return _FALSE;
                    }
                }
            }
#else
            return _TRUE;
#endif
            break;

        default:
            break;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : Dp Interrupt Request
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1LinkStatusIRQ(void)
{
    SET_DP_RX1_AUX_MANUAL_MODE();

    if((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_LINK_TRAINING_FAIL) || (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_LINK_STATUS_FAIL))
    {
        ScalerDpRx1DpcdLinkStatusReset(_DP_DPCD_LINK_STATUS_RESET);

        SET_DP_RX1_AUX_AUTO_MODE();

        ScalerDpRx1HDCPBlockReset();

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        ScalerDpRx1Hdcp2ResetProc();
#endif

        if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) != _BIT1) &&
           (ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) != (_BIT2 | _BIT0)))
        {
            ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_LONG_HOTPLUG_EVENT);

#if((_DP_HDCP_2_2_SUPPORT == _ON) && (_WD_TIMER_INT_SUPPORT == _ON))
            ScalerTimerWDCancelTimerEvent(_SCALER_WD_TIMER_EVENT_DP_RX1_HDCP2_SKE);
#endif

            ScalerDpRx1HpdIrqAssert();
        }
    }

    SET_DP_RX1_AUX_AUTO_MODE();
}

//-------------------------------------------------------
// Description  : Set Aux Diff mode or Single-eneded mode
// Input Value  : None
// Output Value : None
//-------------------------------------------------------
void ScalerDpRx1AuxSet(void)
{
    if(GET_DP_AUX_DIFF_MODE() == _FALSE)
    {
        // Set TX VLDO = 1.05V, Open AUX ADJR_P, Rx Common Mode from 3.3V
        ScalerSetByte(PBA_61_AUX_1, ((_DP_AUX_SWING_1050_MV << 5) | _BIT4));

        // [5]Enable Single-Ended Mode, [4:3]Aux Vth-->50mV, [0]Aux 50ohm auto K(Enable Big_Z0_P)
        ScalerSetByte(PBA_62_AUX_2, 0x29);

        // [4]Enable Big_Z0_N, [3:0]Open ADJR_N
        ScalerSetBit(PBA_66_AUX_6, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT4);
    }
    else
    {
        // Set TX VLDO = 1.05V, Rx Common Mode from 3.3V
        ScalerSetBit(PBA_61_AUX_1, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), ((_DP_AUX_SWING_1050_MV << 5) | _BIT4));

        // [5]Disable Single-Ended Mode, [4:3]Aux Vth-->50mV, [0]Aux 50ohm auto K(Enable Big_Z0_P)
        ScalerSetByte(PBA_62_AUX_2, 0x09);

        // [4]Enable Big_Z0_N
        ScalerSetBit(PBA_66_AUX_6, ~_BIT4, _BIT4);

        // AUX RX1 P Channel Resistance Setting
        ScalerSetBit(PBA_61_AUX_1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), GET_DP_AUX_ADJR_SETTING());

        // AUX RX1 N Channel Resistance Setting
        ScalerSetBit(PBA_66_AUX_6, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), GET_DP_AUX_ADJR_SETTING());
    }
}

//--------------------------------------------------
// Description  : DP Error Counter Update
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ErrorCounterUpdate_EXINT0(DPRX_PD1)
{
    WORD usErrorTemp = 0;

    switch(g_pucDpRxLaneCount_P(DPRX_P))
    {
        case _DP_ONE_LANE:

            // Store Lane0 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE0 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x10, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            break;

        case _DP_TWO_LANE:

            // Store Lane0 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE0 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x10, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            // Store Lane1 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE1 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x12, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x13, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            break;

        default:
        case _DP_FOUR_LANE:

            // Store Lane0 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE0 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x10, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            // Store Lane1 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE1 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x12, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x13, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            // Store Lane2 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE2 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x14, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x15, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            // Store Lane3 Error
            ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_D1_DP_LANE3 << 3));

            usErrorTemp = (((WORD)ScalerGetByte_EXINT(PB0_0B_BIST_PATTERN3) << 8) | (ScalerGetByte_EXINT(PB0_0C_BIST_PATTERN4)));

            if((usErrorTemp >= 49) && (usErrorTemp <= 100))
            {
                usErrorTemp = 50;
            }

            ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x16, LOBYTE(usErrorTemp));
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x17, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(usErrorTemp));

            break;
    }

    // Reset 8B/10B Error Counter
    ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
    ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);
}

//--------------------------------------------------
// Description  : DP Error Counter Disable
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ErrorCounterDisable_EXINT0(void)
{
    // Disable Wildcard IRQ for Error Counter
    ScalerSetBit_EXINT(PBA_FB_DUMMY_1, ~(_BIT7 | _BIT5 | _BIT3 | _BIT1 | _BIT0), 0x00);

    // Disable 8B/10B Error Counter
    ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT2 | _BIT1 | _BIT0), 0x00);

    // Enable DPCD Auto Increment
    ScalerSetBit_EXINT(PBA_C0_DPCD_CTRL, ~_BIT0, _BIT0);

    // Set DPCD 0x21xh
    ScalerSetByte_EXINT(PBA_C1_DPCD_ADDR_PORT_H, 0x00);
    ScalerSetByte_EXINT(PBA_C2_DPCD_ADDR_PORT_M, 0x02);
    ScalerSetByte_EXINT(PBA_C3_DPCD_ADDR_PORT_L, 0x10);

    // Set DPCD 0x210-0x217 = 0x00
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);
    ScalerSetByte_EXINT(PBA_C4_DPCD_DATA_PORT, 0x00);

    // Disable DPCD Auto Increment
    ScalerSetBit_EXINT(PBA_C0_DPCD_CTRL, ~_BIT0, 0x00);
}

//--------------------------------------------------
// Description  : DP Error Counter Enable
// Input Value  : DP Link Training Type
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ErrorCounterEnable_EXINT0(DPRX_PD EnumDpLinkTrainingType enumDpLtType)
{
    // Enable DPCD Error Count Valid Flag
    switch(g_pucDpRxLaneCount_P(DPRX_P))
    {
        case _DP_ONE_LANE:

            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~_BIT7, _BIT7);

            break;

        case _DP_TWO_LANE:

            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~_BIT7, _BIT7);
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x13, ~_BIT7, _BIT7);

            break;

        default:
        case _DP_FOUR_LANE:

            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x11, ~_BIT7, _BIT7);
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x13, ~_BIT7, _BIT7);
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x15, ~_BIT7, _BIT7);
            ScalerDpRx1SetDpcdBitValue_EXINT0(0x00, 0x02, 0x17, ~_BIT7, _BIT7);

            break;
    }

    if(enumDpLtType == _DP_NORMAL_LT)
    {
        // Enable 8B/10B Error Counter
        ScalerSetBit_EXINT(PB0_08_BIST_PATTERN_SEL, ~(_BIT2 | _BIT1 | _BIT0), _BIT1);
    }

    // Enable Read Error Counter IRQ, Clear IRQ Flag
    ScalerSetBit_EXINT(PBA_FB_DUMMY_1, ~(_BIT7 | _BIT5 | _BIT3 | _BIT1 | _BIT0), (_BIT1 | _BIT0));
}

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check 8b10b Error Count
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1DecodeErrorCountCheck(WORD usTimeCriteria, BYTE ucErrorCriteria)
{
    ScalerDpRx1DecodeErrorCountReset();

    ScalerTimerDelayXms(usTimeCriteria);

    switch(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)
    {
        case _DP_ONE_LANE:

            if(ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE0) == _TRUE)
            {
                return _TRUE;
            }

            break;

        case _DP_TWO_LANE:

            if((ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE0) == _TRUE) &&
               (ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE1) == _TRUE))
            {
                return _TRUE;
            }

            break;

        case _DP_FOUR_LANE:
        default:

            if((ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE0) == _TRUE) &&
               (ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE1) == _TRUE) &&
               (ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE2) == _TRUE) &&
               (ScalerDpRx1DecodeErrorCountLaneMeasure(ucErrorCriteria, _D1_DP_LANE3) == _TRUE))
            {
                return _TRUE;
            }

            break;
    }

    DebugMessageRx1("7. DP Error Count Fail", 0);

    return _FALSE;
}

//--------------------------------------------------
// Description : Measure 8b10b Error Count Per Lane
// Input Value  : DP Lane
// Output Value : True --> locked; False --> unlocked
//--------------------------------------------------
bit ScalerDpRx1DecodeErrorCountLaneMeasure(BYTE ucErrorCriteria, BYTE ucDpRx1LaneNumber)
{
    WORD usErrorCountLaneMeasure = 0;

    // Select Lane
    ScalerSetBit(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (ucDpRx1LaneNumber << 3));

    usErrorCountLaneMeasure = ((((WORD)ScalerGetByte(PB0_0B_BIST_PATTERN3)) << 8) | ScalerGetByte(PB0_0C_BIST_PATTERN4));

    if(usErrorCountLaneMeasure > ucErrorCriteria)
    {
        DebugMessageRx1("DP Lane", ucDpRx1LaneNumber);
        DebugMessageRx1("DP Lane Burst Error", usErrorCountLaneMeasure);

        return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description : Check Lane BS
// Input Value  : None
// Output Value : True --> valid, False --> invalid
//--------------------------------------------------
bit ScalerDpRx1LaneBsCheck(void)
{
    // Detect Enable
    ScalerSetBit(PB0_00_HD_DP_SEL, ~_BIT3, 0x00);
    ScalerSetBit(PB0_00_HD_DP_SEL, ~_BIT3, _BIT3);

    // Delay for 8192 x 10 x 8 x 2 / 1.62G = 809us
    DELAY_XUS(850);

    // Check Lane Bs
    if(ScalerGetBit(PB0_00_HD_DP_SEL, (_BIT7 | _BIT6 | _BIT5 | _BIT4)) == 0x00)
    {
        return _FALSE;
    }

    return _TRUE;
}
#endif

//--------------------------------------------------
// Description  : Check DP Vactive / Hactive Information
// Input Value  : None
// Output Value : True --> DP Vactive / Hactive Information Check Ok
//--------------------------------------------------
bit ScalerDpRx1MSAActiveChange(void)
{
    // Pop up Main Stream Attributes
    ScalerSetBit(PB9_00_MN_STRM_ATTR_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT3 | _BIT2), (_BIT7 | _BIT6 | _BIT5 | _BIT3));

    // Get Display Format Hactive
    ScalerRead(PB8_45_MN_DPF_HWD_M, 2, &pData[0], _AUTOINC);

    // Get MSA Hactive
    ScalerRead(PB9_0C_MSA_HWD_0, 2, &pData[2], _AUTOINC);

    // Get Display Format Vactive
    ScalerRead(PB8_4D_MN_DPF_VHT_M, 2, &pData[4], _AUTOINC);

    // Get MSA Vactive
    ScalerRead(PB9_16_MSA_VHT_0, 2, &pData[6], _AUTOINC);

    if((PDATA_WORD(0) != PDATA_WORD(1)) || (PDATA_WORD(2) != PDATA_WORD(3)))
    {
        return _TRUE;
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Signal Detection for DP(Power Saving)
// Input Value  : None
// Output Value : True : DP Signal Detected
//              : False : No Signal
//--------------------------------------------------
bit ScalerDpRx1PSPreDetect(void)
{
    // Back to noraml for DP PHY CTS
    if(GET_DP_RX1_PHY_CTS_FLG() == _TRUE)
    {
        return _TRUE;
    }

    if(GET_DP_RX1_VALID_VIDEO_CHECK() == _TRUE)
    {
        DebugMessageRx1("7. Valid Video Check", 0);

        return _TRUE;
    }

#if(_AWTO_PS_WAKE == _ON)
    if(GET_DP_RX1_PS_AUX_TOGGLE() == _TRUE) { CLR_DP_RX1_PS_AUX_TOGGLE(); AwtoPsAuxSeen(_D1_INPUT_PORT); }
#else
    if(GET_DP_RX1_PS_AUX_TOGGLE() == _TRUE) { return _TRUE; }
#endif


    if(GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_NORMAL_LINK_TRAINING_PASS)
    {
        DebugMessageRx1("7. Normal Link Training under Fake Power Saving Case", 0);

        return _TRUE;
    }

#if(_DP_MST_SUPPORT == _ON)

    if(ScalerDpRxMstStreamMuxCheck(_DP_ST_SOURCE1) != 0x00)
    {
        return _TRUE;
    }

    if(GET_DP_RX1_AUX_CH_POWER_ON_WAKE_UP() == _TRUE)
    {
        CLR_DP_RX1_AUX_CH_POWER_ON_WAKE_UP();

        return _TRUE;
    }
#endif

    if(((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS) &&
        ((ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) != _BIT1) &&
         (ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) != (_BIT2 | _BIT0)))) ||
       (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS_VBIOS))
    {
#if((_SLEEP_AUDIO_SUPPORT == _ON) && ((_PS_AUDIO_INPUT == _PS_AUDIO_BOTH) || (_PS_AUDIO_INPUT == _PS_AUDIO_DP)))

        if(ScalerAudioGetDigitalAudioSource(_D1_INPUT_PORT) == _DIGITAL_AUDIO_SOURCE_DP)
        {
            DebugMessageAudio("00. DP Power Saving Audio : Idle Pattern Case", ScalerAudioGetDigitalAudioSource(_D1_INPUT_PORT));
            return _TRUE;
        }
#endif
        DebugMessageRx1("7. Idle Pattern Case", 0);

        return _TRUE;
    }

    return _FALSE;
}

//--------------------------------------------------
// Description  : Set DP Lane Mapping Type
// Input Value  : ucLanetype --> Lane Mapping Type
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetDpLaneMapping(EnumTypeCPinCfgType enumPinAssignment, EnumTypeCOrientation enumOrientation)
{
    if(enumOrientation == _TYPE_C_ORIENTATION_UNFLIP)
    {
        if(enumPinAssignment == _TYPE_C_PIN_ASSIGNMENT_E)
        {
            // Lane 0 <--> Lane 2
            // Lane 1 <--> Lane 3
            SET_DP_RX1_PCB_LANE0_MAPPING(_D1_DP_PCB_LANE2_MAPPING);
            SET_DP_RX1_PCB_LANE1_MAPPING(_D1_DP_PCB_LANE3_MAPPING);
            SET_DP_RX1_PCB_LANE2_MAPPING(_D1_DP_PCB_LANE0_MAPPING);
            SET_DP_RX1_PCB_LANE3_MAPPING(_D1_DP_PCB_LANE1_MAPPING);
            SET_DP_RX1_PCB_LANE0_PN_SWAP(!_D1_DP_PCB_LANE0_PN_SWAP);
            SET_DP_RX1_PCB_LANE1_PN_SWAP(!_D1_DP_PCB_LANE1_PN_SWAP);
            SET_DP_RX1_PCB_LANE2_PN_SWAP(!_D1_DP_PCB_LANE2_PN_SWAP);
            SET_DP_RX1_PCB_LANE3_PN_SWAP(!_D1_DP_PCB_LANE3_PN_SWAP);

#if(_D1_DP_TYPE_C_PIN_E_AUXPN_SWAP == _SWAP_BY_SCALER)
            // Enable Aux PN Pull High Low Swap PCB Function
            PCB_D1_AUX_PN_1M_PULL_H_L_SWAP(_AUX_PN_1M_PULL_HI_LOW_SWAP_ON);

            // Enable Aux Digital Phy PN Swap
            ScalerSetBit(PBA_72_AUX_DIG_PHY2, ~_BIT0, _BIT0);
#else
            // Disable Aux PN Pull High Low Swap PCB Function
            PCB_D1_AUX_PN_1M_PULL_H_L_SWAP(_AUX_PN_1M_PULL_HI_LOW_SWAP_OFF);

            // Disable Aux Digital Phy PN Swap
            ScalerSetBit(PBA_72_AUX_DIG_PHY2, ~_BIT0, 0x00);
#endif
        }
        else // Normal Cable Mode
        {
            SET_DP_RX1_PCB_LANE0_MAPPING(_D1_DP_PCB_LANE0_MAPPING);
            SET_DP_RX1_PCB_LANE1_MAPPING(_D1_DP_PCB_LANE1_MAPPING);
            SET_DP_RX1_PCB_LANE2_MAPPING(_D1_DP_PCB_LANE2_MAPPING);
            SET_DP_RX1_PCB_LANE3_MAPPING(_D1_DP_PCB_LANE3_MAPPING);
            SET_DP_RX1_PCB_LANE0_PN_SWAP(_D1_DP_PCB_LANE0_PN_SWAP);
            SET_DP_RX1_PCB_LANE1_PN_SWAP(_D1_DP_PCB_LANE1_PN_SWAP);
            SET_DP_RX1_PCB_LANE2_PN_SWAP(_D1_DP_PCB_LANE2_PN_SWAP);
            SET_DP_RX1_PCB_LANE3_PN_SWAP(_D1_DP_PCB_LANE3_PN_SWAP);

            // Disable Aux PN Pull High Low Swap PCB Function
            PCB_D1_AUX_PN_1M_PULL_H_L_SWAP(_AUX_PN_1M_PULL_HI_LOW_SWAP_OFF);

            // Disable Aux Digital Phy PN Swap
            ScalerSetBit(PBA_72_AUX_DIG_PHY2, ~_BIT0, 0x00);
        }
    }
    else
    {
        if(enumPinAssignment == _TYPE_C_PIN_ASSIGNMENT_E)
        {
            // Lane 0 <--> Lane 2
            // Lane 1 <--> Lane 3
            SET_DP_RX1_PCB_LANE0_MAPPING(_D1_DP_PCB_LANE1_MAPPING);
            SET_DP_RX1_PCB_LANE1_MAPPING(_D1_DP_PCB_LANE0_MAPPING);
            SET_DP_RX1_PCB_LANE2_MAPPING(_D1_DP_PCB_LANE3_MAPPING);
            SET_DP_RX1_PCB_LANE3_MAPPING(_D1_DP_PCB_LANE2_MAPPING);
            SET_DP_RX1_PCB_LANE0_PN_SWAP(!_D1_DP_PCB_LANE0_PN_SWAP);
            SET_DP_RX1_PCB_LANE1_PN_SWAP(!_D1_DP_PCB_LANE1_PN_SWAP);
            SET_DP_RX1_PCB_LANE2_PN_SWAP(!_D1_DP_PCB_LANE2_PN_SWAP);
            SET_DP_RX1_PCB_LANE3_PN_SWAP(!_D1_DP_PCB_LANE3_PN_SWAP);

            // Disable Aux PN Pull High Low Swap PCB Function
            PCB_D1_AUX_PN_1M_PULL_H_L_SWAP(_AUX_PN_1M_PULL_HI_LOW_SWAP_OFF);

            // Disable Aux Digital Phy PN Swap
            ScalerSetBit(PBA_72_AUX_DIG_PHY2, ~_BIT0, 0x00);
        }
        else // Normal Cable Mode
        {
            SET_DP_RX1_PCB_LANE0_MAPPING(_D1_DP_PCB_LANE3_MAPPING);
            SET_DP_RX1_PCB_LANE1_MAPPING(_D1_DP_PCB_LANE2_MAPPING);
            SET_DP_RX1_PCB_LANE2_MAPPING(_D1_DP_PCB_LANE1_MAPPING);
            SET_DP_RX1_PCB_LANE3_MAPPING(_D1_DP_PCB_LANE0_MAPPING);
            SET_DP_RX1_PCB_LANE0_PN_SWAP(_D1_DP_PCB_LANE0_PN_SWAP);
            SET_DP_RX1_PCB_LANE1_PN_SWAP(_D1_DP_PCB_LANE1_PN_SWAP);
            SET_DP_RX1_PCB_LANE2_PN_SWAP(_D1_DP_PCB_LANE2_PN_SWAP);
            SET_DP_RX1_PCB_LANE3_PN_SWAP(_D1_DP_PCB_LANE3_PN_SWAP);

            // Enable Aux PN Pull High Low Swap PCB Function
            PCB_D1_AUX_PN_1M_PULL_H_L_SWAP(_AUX_PN_1M_PULL_HI_LOW_SWAP_ON);

            // Enable Aux Digital Phy PN Swap
            ScalerSetBit(PBA_72_AUX_DIG_PHY2, ~_BIT0, _BIT0);
        }
    }
}

//--------------------------------------------------
// Description  : Dp Secondary Data Reset
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SecDataBlockReset(void)
{
    // Set S __code by FW manual
    ScalerSetBit(PB9_58_SCODE_0, ~_BIT7, _BIT7);

    // Sec Data Block Reset
    ScalerSetBit(PB8_00_MAC_DIG_RESET_CTRL, ~_BIT4, _BIT4);
    ScalerSetBit(PB8_00_MAC_DIG_RESET_CTRL, ~_BIT4, 0x00);

    // Set S __code by HW auto
    ScalerSetBit(PB9_58_SCODE_0, ~_BIT7, 0x00);
}
//--------------------------------------------------
// Description  : Set DPCD Table Information
// Input Value  : ucDpcdAccessPortH --> High Byte of DPCD Address
//                ucDpcdAccessPortM --> Middle Byte of DPCD Address
//                ucDpcdAccessPortL --> Low Bye of DPCD Adress
//                ucDpcdValue --> DPCD Value
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetDpcdBitValue(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucNotDpcdBit, BYTE ucDpcdBit)
{
    // Release Aux
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT7, 0x00);

    ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, ucDpcdAccessPortH);
    ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, ucDpcdAccessPortM);
    ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, ucDpcdAccessPortL);
    AWTO_DPCD_SETTLE() ScalerSetBit(PBA_C4_DPCD_DATA_PORT, ~(~ucNotDpcdBit), ucDpcdBit);
}
//--------------------------------------------------
// Description  : Set DPCD Table Information
// Input Value  : ucDpcdAccessPortH --> High Byte of DPCD Address
//                ucDpcdAccessPortM --> Middle Byte of DPCD Address
//                ucDpcdAccessPortL --> Low Bye of DPCD Adress
//                ucDpcdValue --> DPCD Value
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetDpcdValue(BYTE ucDpcdAccessPortH, BYTE ucDpcdAccessPortM, BYTE ucDpcdAccessPortL, BYTE ucDpcdValue)
{
    // Release Aux
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT7, 0x00);

    ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, ucDpcdAccessPortH);
    ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, ucDpcdAccessPortM);
    ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, ucDpcdAccessPortL);
    AWTO_DPCD_SETTLE() ScalerSetByte(PBA_C4_DPCD_DATA_PORT, ucDpcdValue);
}
//--------------------------------------------------
// Description  : DP Sink Status Setting
// Input Value  : Receive Port, Sync Status
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SinkStatusSet(EnumDpSinkReceivePort enumReceiverPort, EnumDpSinkStatus enumInSync)
{
    if(enumInSync == _DP_SINK_IN_SYNC)
    {
        if(enumReceiverPort == _DP_SINK_REVEICE_PORT0)
        {
            // Set Receive Port 0 in Sync
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x05, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x05) | _BIT0));
        }
        else if(enumReceiverPort == _DP_SINK_REVEICE_PORT1)
        {
            // Set Receive Port 1 in Sync
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x05, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x05) | _BIT1));
        }
    }
    else
    {
        if(enumReceiverPort == _DP_SINK_REVEICE_PORT0)
        {
            // Set Receive Port 0 Out of Sync
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x05, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x05) & ~_BIT0));
        }
        else if(enumReceiverPort == _DP_SINK_REVEICE_PORT1)
        {
            // Set Receive Port 1 Out of Sync
            ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x05, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x05) & ~_BIT1));
        }
    }
}

//--------------------------------------------------
// Description  : Dp HDCP DPCD capability Switch
// Input Value  : _ENABLE or _DISABLE
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ChangeHdcpDpcdCapability(bit bEn)
{
#if(_AWTO_HDCP == _OFF)
    bEn = bEn;    // awto: only _DISABLE is called without HDCP (#44)
#endif
#if(_AWTO_HDCP == _ON)    // awto: enable branch only with HDCP (#44)
    if(bEn == _ENABLE)
    {
        // Clear flag for write 68xxx int
        ScalerSetBit(PBA_DA_AUX_FIFO_RST, ~_BIT1, _BIT1);

        // Enable Write 68xxx int
        ScalerSetBit(PBA_DA_AUX_FIFO_RST, ~_BIT2, _BIT2);

#if((_DP_TX_SUPPORT == _ON) && (_D1_DP_MST_PORT_SUPPORT == _ON))
        // Clear flag for Write AKSV int
        ScalerSetBit(PBA_A5_AUX_RESERVE5, ~(_BIT2 | _BIT1 | _BIT0), _BIT2);

        // Enable Write AKSV int
        ScalerSetBit(PBA_A5_AUX_RESERVE5, ~_BIT6, _BIT6);

        // Enable HDCP and repeater support
        ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x28, 0x03);
#else
        // Enable HDCP support
        ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x28, 0x01);
#endif

#if((_EIZO_CUSTOMIZED_VALUE_OF_DPCD_SUPPORT == _ON) && (_DP_TX_SUPPORT == _ON))
        if(ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x00) > _DP_VERSION_1_1)
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x28, 0x03);
        }
#endif

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        // Enable the HDCP2.2 capability
        for(pData[0] = 0; pData[0] < 3; pData[0]++)
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x92, (0x1D + pData[0]), g_pucDPRx1Caps[pData[0]]);
        }
#endif
    }
    else
#endif
    {
        // Disable Write 68xxx int
        ScalerSetBit(PBA_DA_AUX_FIFO_RST, ~_BIT2, 0x00);

#if((_DP_TX_SUPPORT == _ON) && (_D1_DP_MST_PORT_SUPPORT == _ON))
        // Disable Write AKSV int
        ScalerSetBit(PBA_A5_AUX_RESERVE5, ~_BIT6, 0x00);
#endif
        // Disable HDCP support
        ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x28, 0x00);

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        // Disable the HDCP2.2 capability
        for(pData[0] = 0; pData[0] < 3; pData[0]++)
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x92, (0x1D + pData[0]), 0x00);
        }
#endif
    }
}

#if(_DP_RX1_ASSR_MODE_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP ASSR Mode On/ Off
// Input Value  : _ON/ _OFF
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ASSRModeSetting(void)
{
    if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x0A) & _BIT0) == _BIT0)
    {
        // Scramble seed equal to 0xFFFE
        ScalerSetBit(PB0_07_SCRAMBLE_CTRL, ~_BIT4, _BIT4);
    }
    else
    {
        // Scramble seed equal to 0xFFFF
        ScalerSetBit(PB0_07_SCRAMBLE_CTRL, ~_BIT4, 0x00);
    }
}
#endif



#if(_DP_TX_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Sink Count Update
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1UpdateSinkCount(BYTE ucSinkCount)
{
    BYTE ucRxPreSinkCount = ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x00);
    BYTE ucRxCurSinkCount = ((ucRxPreSinkCount & _BIT6) | ucSinkCount);

    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x00, ucRxCurSinkCount);

    if(ucSinkCount > 1)
    {
        ScalerDpRx1DfpDeviceDetailConfig();
    }
    else
    {
        ScalerDpRx1DfpDeviceDetailConfigReset();
    }

    if((ucRxPreSinkCount != ucRxCurSinkCount) && (PCB_D1_HOTPLUG_DETECT() == _D1_HOT_PLUG_HIGH))
    {
        ScalerDpRx1SetDpcdBitValue(0x00, 0x02, 0x04, ~_BIT6, _BIT6);
        ScalerDpRx1HpdIrqAssert();
    }
}
#endif // End of #if(_DP_TX_SUPPORT == _ON)

//--------------------------------------------------
// Description  : DP FLD Band Finetune
// Input Value  : LaneNumber
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1AdjustLaneFLDBand(BYTE ucDpRx1LaneNumber, WORD usVCOBandDiff)
{
    BYTE ucBestVCOBand = 0;
    BYTE ucAutoVCOBand = 0;

    switch(ucDpRx1LaneNumber)
    {
        default:
        case _DP_SCALER_LANE0:

            ucAutoVCOBand = (ScalerGetByte(P7A_36_ANA_CDR_11) & 0x7F);

            break;

        case _DP_SCALER_LANE1:

            ucAutoVCOBand = (ScalerGetByte(P7A_37_ANA_CDR_12) & 0x7F);

            break;

        case _DP_SCALER_LANE2:

            ucAutoVCOBand = (ScalerGetByte(P7A_38_ANA_CDR_13) & 0x7F);

            break;

        case _DP_SCALER_LANE3:

            ucAutoVCOBand = (ScalerGetByte(P7A_39_ANA_CDR_14) & 0x7F);

            break;
    }

    // [1:0] freqdet_lane_sel
    ScalerSetBit(PB0_51_DP_SIG_DET_1, ~(_BIT1 | _BIT0), ucDpRx1LaneNumber);

    // [6] LANE_COUNT_CLEAR = 0 -> Keep the LANE_COUNT value
    ScalerSetBit(PB0_52_DP_SIG_DET_2, ~_BIT6, 0x00);

    // [7] DP_SIG_DET_EN = 1'b1 -> Enable Signal Detection
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, _BIT7);

    // Delay Time us [5,150] Polling for Measure Done
    for(pData[0] = 0; pData[0] <= 30; pData[0]++)
    {
        DELAY_5US();

        if(ScalerGetBit(PB0_50_DP_SIG_DET_0, _BIT6) == _BIT6)
        {
            break;
        }
    }

    if(ScalerGetBit(PB0_50_DP_SIG_DET_0, _BIT6) == _BIT6)
    {
        isr_g_ppusDpRxClockCount1_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] = ((((WORD)ScalerGetByte(PB0_53_DP_SIG_DET_3)) << 8) | ScalerGetByte(PB0_54_DP_SIG_DET_4));

        if(isr_g_ppusDpRxClockCount1_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] < isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber])
        {
            ucBestVCOBand = ucAutoVCOBand + (((isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - isr_g_ppusDpRxClockCount1_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber]) / usVCOBandDiff) + 1);
        }
        else
        {
            ucBestVCOBand = ucAutoVCOBand - ((isr_g_ppusDpRxClockCount1_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber]) / usVCOBandDiff);
        }
    }
    else
    {
        ucBestVCOBand = ucAutoVCOBand;
    }

    // [7] DP_SIG_DET_EN = 0 -> Disable Signal Detection
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);

    // Manually Reload FLD Band
    switch(ucDpRx1LaneNumber)
    {
        default:
        case _DP_SCALER_LANE0:

            ScalerSetBit(P7A_32_ANA_CDR_07, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), ucBestVCOBand);

            break;

        case _DP_SCALER_LANE1:

            ScalerSetBit(P7A_33_ANA_CDR_08, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), ucBestVCOBand);

            break;

        case _DP_SCALER_LANE2:

            ScalerSetBit(P7A_34_ANA_CDR_09, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), ucBestVCOBand);

            break;

        case _DP_SCALER_LANE3:

            ScalerSetBit(P7A_35_ANA_CDR_10, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), ucBestVCOBand);

            break;
    }
}
//--------------------------------------------------
// Description  : Check Valid Lane CDR
// Input Value  : None
// Output Value : True --> CDR Lock
//--------------------------------------------------
bit ScalerDpRx1CDRCheck(BYTE ucDpLinkRate, BYTE ucDpcdLane)
{
#if(_HW_DP_GDI_RX1_DFE_TYPE == _PASSIVE_DFE)
    CLR_DP_RX1_SIGNALDETECT_INT_HAPPENED();
#endif

    switch(ucDpcdLane)
    {
        case _DP_ONE_LANE:

            if(ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE0) == _TRUE)
            {
                return _TRUE;
            }

            break;

        case _DP_TWO_LANE:

            if((ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE0) == _TRUE) &&
               (ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE1) == _TRUE))
            {
                return _TRUE;
            }

            break;

        case _DP_FOUR_LANE:
        default:

            if((ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE0) == _TRUE) &&
               (ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE1) == _TRUE) &&
               (ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE2) == _TRUE) &&
               (ScalerDpRx1MeasureLaneCDRClk(ucDpLinkRate, _D1_DP_LANE3) == _TRUE))
            {
                return _TRUE;
            }

            break;
    }

#if(_HW_DP_GDI_RX1_DFE_TYPE == _PASSIVE_DFE)
    if(GET_DP_RX1_SIGNALDETECT_INT_HAPPENED() == _TRUE)
    {
        return _TRUE;
    }
    else
#endif
    {
        DebugMessageRx1("7. wuzanne test : DP CDR Unlock", 0);

        return _FALSE;
    }
}
//--------------------------------------------------
// Description  : DP Content Protection Interrupt Request
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1CpIRQ(EnumDpRxBStatusType enumBStatusType)
{
    switch(enumBStatusType)
    {
        case _DP_HDCP_BSTATUS_LINK_INTEGRITY_FAIL:

            if(GET_DP_RX1_HDCP_MODE() == _HDCP_14)
            {
#if(_DP_MST_SUPPORT == _ON)
                if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x11) & _BIT0) == 0x00)
                {
                    // Reset HDCP Block
                    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, _BIT0);
                    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, 0x00);
                }

                if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x11) & _BIT1) == _BIT1)
                {
                    ScalerDpRx1SetDpcdValue(0x00, 0x20, 0x05, (ScalerDpRx1GetDpcdInfo(0x00, 0x20, 0x05) | _BIT2));
                }
#else
                // Reset HDCP Block
                ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, _BIT0);
                ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, 0x00);
#endif

                SET_DP_RX1_AUX_MANUAL_MODE();

                // Clear Aksv
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x07, 0x00);
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x08, 0x00);
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x09, 0x00);
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0A, 0x00);
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0B, 0x00);

                SET_DP_RX1_AUX_AUTO_MODE();

                // Set B Status
                ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x29, (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x29) | enumBStatusType));
            }
#if(_DP_HDCP_2_2_SUPPORT == _ON)
            else
            {
                // Disable HDCP 2.2 Module
                SET_DP_RX1_HDCP_MODE(_HDCP_14);

                // Disable HDCP2.2 Auth. Done
                ScalerSetBit(PB0_20_HDCP_DEBUG, ~_BIT4, 0x00);

                // Reset HDCP Block
                ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, _BIT0);
                ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, 0x00);

                ScalerDpRx1SetDpcdValue(0x06, 0x94, 0x93, (ScalerDpRx1GetDpcdInfo(0x06, 0x94, 0x93) | _BIT4));

                // Clear Authentication Done Flag
                CLR_DP_RX1_HDCP2_AUTHENTICATION_DONE();
            }
#endif
            break;

        case _DP_HDCP_BSTATUS_REAUTH_REQ:

            ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x29, (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x29) | _BIT3));

            break;

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        case _DP_HDCP2_RXSTATUS_REAUTH_REQ:

            ScalerDpRx1SetDpcdValue(0x06, 0x94, 0x93, (ScalerDpRx1GetDpcdInfo(0x06, 0x94, 0x93) | _BIT3));

            break;
#endif

        case _DP_HDCP_BSTATUS_V_READY:
        case _DP_HDCP_BSTATUS_R0_AVAILABLE:

            // Set B Status
            ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x29, (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x29) | enumBStatusType));

            break;

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        case _DP_HDCP2_H_PRIME_AVAILABLE:
        case _DP_HDCP2_PARING_AVAILABLE:

            ScalerDpRx1SetDpcdValue(0x06, 0x94, 0x93, (ScalerDpRx1GetDpcdInfo(0x06, 0x94, 0x93) | (enumBStatusType >> 3)));

            break;

        case _DP_HDCP2_V_READY:

            ScalerDpRx1SetDpcdValue(0x06, 0x94, 0x93, (ScalerDpRx1GetDpcdInfo(0x06, 0x94, 0x93) | (enumBStatusType >> 6)));

            break;
#endif

        default:

            break;
    }

    // Link Status CPIRQ Flag
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0x01, (ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x01) | _BIT2));

    ScalerDpRx1HpdIrqAssert();
}


//--------------------------------------------------
// Description : check DFE Coef
// Input Value  : None
// Output Value : True --> valid, False --> invalid
//--------------------------------------------------
// One lane of the DFE coefficient check: Vth == 0x00 with Tap0 == 0x15 is invalid. ucMap = the lane's scaler lane (_D1_DP_LANEn).
static bit ScalerDpRx1DFELaneCheck(BYTE ucMap)
{
    BYTE ucVth;
    BYTE ucTap0;

    // Read Lane DFE
    ScalerSetBit(P7A_F2_COEF_3, ~(_BIT7 | _BIT6), (ucMap << 6));

    // Read Back Vth
    ScalerSetBit(P7A_F0_COEF_1, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    ucVth = (ScalerGetByte(P7A_F1_COEF_2) & 0x0F);

    // Read Back Tap0
    ScalerSetBit(P7A_F0_COEF_1, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT0);
    ucTap0 = (ScalerGetByte(P7A_F1_COEF_2) & 0x1F);

    if((((WORD)ucVth << 8) | ucTap0) == 0x0015)
    {
        DebugMessageRx1("7. Lane DFE Fail", ucMap);

        return _FALSE;
    }

    return _TRUE;
}

bit ScalerDpRx1DFECheck(void)
{
    if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR2)
    {
        return _TRUE;
    }

    switch(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)
    {
        case _DP_FOUR_LANE:

            if((ScalerDpRx1DFELaneCheck(_D1_DP_LANE2) == _FALSE) || (ScalerDpRx1DFELaneCheck(_D1_DP_LANE3) == _FALSE) ||
               (ScalerDpRx1DFELaneCheck(_D1_DP_LANE1) == _FALSE) || (ScalerDpRx1DFELaneCheck(_D1_DP_LANE0) == _FALSE))
            {
                return _FALSE;
            }

            break;

        case _DP_TWO_LANE:

            if((ScalerDpRx1DFELaneCheck(_D1_DP_LANE1) == _FALSE) || (ScalerDpRx1DFELaneCheck(_D1_DP_LANE0) == _FALSE))
            {
                return _FALSE;
            }

            break;

        case _DP_ONE_LANE:

            if(ScalerDpRx1DFELaneCheck(_D1_DP_LANE0) == _FALSE)
            {
                return _FALSE;
            }

            break;

        default:
            return _FALSE;
            break;
    }

    return _TRUE;
}
//--------------------------------------------------
// Description : check DP 8b/10b Decode Error
// Input Value  : None
// Output Value : True --> ok, False --> 8b/10b Decode Error
//--------------------------------------------------
bit ScalerDpRx1DecodeCheck(void)
{
#if(_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON)

    if(GET_DP_ILLEGAL_IDLE_PATTERN_CHECK() == _TRUE)
    {
        if(GET_DP_RX1_SOURCE_TYPE_JUDGE() == _FALSE)
        {
#if(_HW_DP_LANE_VALID_CHECK_SUPPORT == _ON)
            if(ScalerDpRx1LaneValidCheck() == _FALSE)
            {
                return _TRUE;
            }
#else
            return _TRUE;
#endif
        }
    }

#endif

    pData[1] = 3;

    while(pData[1] > 0)
    {
        // Clear 8b/10b Decode Error Flag
        ScalerSetBit(PB0_06_DECODE_10B8B_ERROR, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

        // Delay Time us [150,x]
        DELAY_XUS(150);

        switch(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)
        {
            case _DP_ONE_LANE:

                if(((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, _BIT0) == 0x00)) ||
                   ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, _BIT1) == 0x00)) ||
                   ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, _BIT2) == 0x00)) ||
                   ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, _BIT3) == 0x00)))
                {
                    return _TRUE;
                }

                break;

            case _DP_TWO_LANE:

                if(((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT1 | _BIT0)) == 0x00)) ||
                   ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT2 | _BIT0)) == 0x00)) ||
                   ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE0) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE0))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT3 | _BIT0)) == 0x00)) ||
                   ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT2 | _BIT1)) == 0x00)) ||
                   ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE1) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE1))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT3 | _BIT1)) == 0x00)) ||
                   ((((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE2) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE3)) || ((GET_DP_RX1_PCB_LANE0_MAPPING() == _DP_SCALER_LANE3) && (GET_DP_RX1_PCB_LANE1_MAPPING() == _DP_SCALER_LANE2))) &&
                    (ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT3 | _BIT2)) == 0x00)))
                {
                    return _TRUE;
                }

                break;

            case _DP_FOUR_LANE:

                if(ScalerGetBit(PB0_06_DECODE_10B8B_ERROR, (_BIT3 | _BIT2 | _BIT1 | _BIT0)) == 0x00)
                {
                    return _TRUE;
                }

                break;

            default:

                return _FALSE;

                break;
        }

        pData[1]--;
    }

    DebugMessageRx1("7. DP 8b/10b Decode Error", 0);

    return _FALSE;
}
//--------------------------------------------------
// Description  : DP Display Format Generator Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1DisplayFormatSetting(void)
{
    BYTE ucOddFlg = 0;
    WORD usDpVtotal = 0;
    WORD usDpHactive = 0;
    DWORD ulStreamClkValue = 0;
    DWORD ulVBs2BsCount = 0;

#if(_DP_FREESYNC_SUPPORT == _ON)
    WORD usHBs2BsCount = 0;
    DWORD ulDpMvidValue = 0;
    DWORD ulDpNvidValue = 0;
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
    if(GET_AIO_MODERN_STANDBY_MODE() == _TRUE)
    {
        // Restore VBs2Bs Count
        ulVBs2BsCount = g_stDpRx1LinkInfo.ulVBsToBsCountN;
    }
    else
#endif
    {
        // Measurement Enable
        ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, 0x00);
        ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, _BIT7);

        if(ScalerTimerPollingFlagProc(_DP_MEASURE_POLLING_TIMEOUT, PB8_58_MN_MEAS_CTRL, _BIT6, _TRUE) == _FALSE)
        {
            return _FALSE;
        }

        // Pop up The result
        SET_DP_RX1_MEASURE_POP_UP();

        // Measurement Disable
        ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, 0x00);

        // VBs2BS count in GDI clk
        ulVBs2BsCount = ((((DWORD)(ScalerGetByte(PB8_58_MN_MEAS_CTRL) & 0x1F)) << 16) | (((DWORD)ScalerGetByte(PB8_59_MN_MEAS_VLN_M)) << 8) | ((DWORD)ScalerGetByte(PB8_5A_MN_MEAS_VLN_L)));
    }

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_FREESYNC_ENABLED() == _TRUE)
    {
        // Get IVfreq
        PDATA_DWORD(0) = ((DWORD)_GDI_CLK_KHZ * 1000 / (ulVBs2BsCount / 10));

        if((PDATA_DWORD(0) < (_PANEL_FREESYNC_MIN_FRAME_RATE - _FRAME_SYNC_MARGIN)) || (PDATA_DWORD(0) > (_PANEL_FREESYNC_MAX_FRAME_RATE + _FRAME_SYNC_MARGIN)))
        {
            return _FALSE;
        }

        // HBs2Bs count in Link Clk / 2
        usHBs2BsCount = (((DWORD)ScalerGetByte(PB8_5B_MN_MEAS_HLN_M)) << 8) | ((DWORD)ScalerGetByte(PB8_5C_MN_MEAS_HLN_L));

        // VTotal in line, Link Clk / 2 : (Link Rate * 27 / 2)
        usDpVtotal = ulVBs2BsCount * (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 27 / 2) / usHBs2BsCount * 1000 / _GDI_CLK_KHZ;

        ulDpMvidValue = ((((DWORD)ScalerGetByte(PB9_1A_MSA_MVID_0)) << 16) | (((DWORD)ScalerGetByte(PB9_1B_MSA_MVID_1)) << 8) | ((DWORD)ScalerGetByte(PB9_1C_MSA_MVID_2)));

        ulDpNvidValue = ((((DWORD)ScalerGetByte(PB9_1D_MSA_NVID_0)) << 16) | (((DWORD)ScalerGetByte(PB9_1E_MSA_NVID_1)) << 8) | ((DWORD)ScalerGetByte(PB9_1F_MSA_NVID_2)));

        // [5] ln_ck_sel = 1'b1 -> CDR Clock
        // [4:0] DP_XTAL_CYCLE = 5'b00100 -> XTAL Counter Cycles = 2000
        ScalerSetBit(PB0_50_DP_SIG_DET_0, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT2));

        // [1:0] freqdet_lane_sel = 2'b00 -> Lane0
        ScalerSetBit(PB0_51_DP_SIG_DET_1, ~(_BIT1 | _BIT0), _D1_DP_LANE0);

        // [6] LANE_COUNT_CLEAR = 0 -> Keep the LANE_COUNT value
        ScalerSetBit(PB0_52_DP_SIG_DET_2, ~_BIT6, 0x00);

        // [7] DP_SIG_DET_EN = 1'b1 -> Enable Signal Detection
        ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);
        ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, _BIT7);

        // Waiting for Measure Done
        ScalerTimerDelayXms(2);

        PDATA_WORD(0) = ((((WORD)ScalerGetByte(PB0_53_DP_SIG_DET_3)) << 8) | ScalerGetByte(PB0_54_DP_SIG_DET_4));

        // [7] DP_SIG_DET_EN = 0 -> Disable Signal Detection
        ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);

        PDATA_DWORD(0) = ((DWORD)PDATA_WORD(0)) * _GDI_CLK_KHZ;

        // Calculate streamclk
        ulStreamClkValue = ((DWORD)ulDpMvidValue * (PDATA_DWORD(0) / ulDpNvidValue) + (PDATA_DWORD(0) % ulDpNvidValue * 100 / ulDpNvidValue * (DWORD)ulDpMvidValue / 100));
    }
    else
#endif
    {
        usDpVtotal = ((((WORD)ScalerGetByte(PB9_10_MSA_VTTE_0)) << 8) | ((WORD)ScalerGetByte(PB9_11_MSA_VTTE_1)));

        // Calculate streamclk (Unit is Hz)
        ulStreamClkValue = (((((((DWORD)ScalerGetByte(PB9_08_MSA_HTT_0)) << 8) | ((WORD)ScalerGetByte(PB9_09_MSA_HTT_1))) * ((DWORD)usDpVtotal) * 100) / ulVBs2BsCount) * _GDI_CLK_KHZ * 10);
    }

    // Input Pixel CLK Unit is 0.1 M
    SET_INPUT_PIXEL_CLK(ulStreamClkValue / 100000);

    // Disable Generate Display Format
    ScalerSetBit(PB8_30_DPF_CTRL_0, ~_BIT7, 0x00);

    // DP Display Format Generator Reset
    ScalerSetBit(PB8_00_MAC_DIG_RESET_CTRL, ~_BIT7, _BIT7);
    ScalerSetBit(PB8_00_MAC_DIG_RESET_CTRL, ~_BIT7, 0x00);

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
    if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
    {
        // Delay a Complete Frame
        AWTO_DP_FRAME_SET(ulVBs2BsCount);
        ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());
    }

    // Set Vactive
    ScalerRead(PB9_16_MSA_VHT_0, 2, &pData[4], _AUTOINC);
    ScalerSetByte(PB8_4D_MN_DPF_VHT_M, pData[4]);
    ScalerSetByte(PB8_4E_MN_DPF_VHT_L, pData[5]);

    // Set Hactive
    ScalerRead(PB9_0C_MSA_HWD_0, 2, pData, _AUTOINC);
    ScalerSetByte(PB8_45_MN_DPF_HWD_M, pData[0]);
    ScalerSetByte(PB8_46_MN_DPF_HWD_L, pData[1]);
    usDpHactive = PDATA_WORD(0);

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_FREESYNC_ENABLED() == _TRUE)
    {
        // HTotal in Pixel Clk, Link Clk / 2 : (Link Rate * 27 / 2)
        WORD usDpHtotal = (DWORD)usHBs2BsCount * (GET_INPUT_PIXEL_CLK() / 10) / (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 27 / 2);

        // Set Htotal
        ScalerSetByte(PB8_41_MN_DPF_HTT_M, HIBYTE(usDpHtotal));
        ScalerSetByte(PB8_42_MN_DPF_HTT_L, LOBYTE(usDpHtotal));

        // Set Hstart
        ScalerSetByte(PB8_43_MN_DPF_HST_M, HIBYTE(_DP_DE_ONLY_MODE_HSTART));
        ScalerSetByte(PB8_44_MN_DPF_HST_L, LOBYTE(_DP_DE_ONLY_MODE_HSTART));

        // Set HSW
        ScalerSetByte(PB8_47_MN_DPF_HSW_M, HIBYTE(_DP_DE_ONLY_MODE_HSW));
        ScalerSetByte(PB8_48_MN_DPF_HSW_L, LOBYTE(_DP_DE_ONLY_MODE_HSW));

        // Set Vstart
        ScalerSetByte(PB8_4B_MN_DPF_VST_M, HIBYTE(_DP_DE_ONLY_MODE_VSTART));
        ScalerSetByte(PB8_4C_MN_DPF_VST_L, LOBYTE(_DP_DE_ONLY_MODE_VSTART));

        // Set VSW
        ScalerSetByte(PB8_4F_MN_DPF_VSW_M, HIBYTE(_DP_DE_ONLY_MODE_VSW));
        ScalerSetByte(PB8_50_MN_DPF_VSW_L, LOBYTE(_DP_DE_ONLY_MODE_VSW));

        PDATA_WORD(0) = GET_DPRX1_BS_TO_HS_DELAY(usDpHtotal);

        // Set HBs2Bs
        ScalerSetByte(PB8_38_BS2HS_0, pData[0]);
        ScalerSetByte(PB8_39_BS2HS_1, pData[1]);

        ScalerDpRx1InterlaceCheck(&usDpVtotal, &ucOddFlg);

        // Set DE Only Mode Vsync Front Porch
        ScalerSetByte(PB8_40_VS_FRONT_PORCH, GET_DP_RX1_VFRONT_PORCH());

        // Set DE Only Mode
        ScalerSetBit(PB8_30_DPF_CTRL_0, ~(_BIT7 | _BIT5 | _BIT4), _BIT4);

        // Choose Frame start BE to Reset FIFO
        ScalerSetBit(PB8_20_PG_CTRL_0, ~_BIT5, 0x00);

        // Set DP FREESYNC Mode Enable
        ScalerSetBit(PB8_F0_DP_RSV0, ~_BIT0, _BIT0);

        ScalerDpRx1SetFREESYNCMsaForLut(usDpHtotal);

        DebugMessageRx1("FREESYNC Mode Enabled!!", ScalerGetByte(PB8_30_DPF_CTRL_0));
    }
    else
#endif
    {
        DWORD ulBs2VsDelay = 0;

        // Set Htotal
        ScalerRead(PB9_08_MSA_HTT_0, 2, &pData[2], _AUTOINC);
        ScalerSetByte(PB8_41_MN_DPF_HTT_M, pData[2]);
        ScalerSetByte(PB8_42_MN_DPF_HTT_L, pData[3]);

        // Get HSW
        pData[4] = ScalerGetBit(PB9_0E_MSA_HSW_0, (_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
        pData[5] = ScalerGetByte(PB9_0F_MSA_HSW_1);

        // Get HSW min by Measure clock
        PDATA_WORD(3) = ((DWORD) _DP_HSYNC_WIDTH_MEASURE_COUNTER * GET_INPUT_PIXEL_CLK() * 100) / _MEASURE_CLK + 1;

        // Check HSW <= HSW min
        if(PDATA_WORD(2) <= PDATA_WORD(3))
        {
            // Check if H porch is more than HSW min
            if((PDATA_WORD(1) - usDpHactive) >= PDATA_WORD(3))
            {
                // HSW = HSW min
                PDATA_WORD(2) = PDATA_WORD(3);
            }
            else
            {
                // HSW = Max H Porch
                PDATA_WORD(2) = (PDATA_WORD(1) - usDpHactive);
            }
        }

        // DPF H Front Porch must not be less than 8 (HW constraint)
        // Check if H porch is more than 8
        if((PDATA_WORD(1) - usDpHactive - PDATA_WORD(2)) <= _DP_HSYNC_FRONT_PORCH)
        {
            // HSW < HSW min
            if(PDATA_WORD(2) < PDATA_WORD(3))
            {
                // Hstart = HSW
                PDATA_WORD(4) = PDATA_WORD(2);
            }
            else if((PDATA_WORD(1) - usDpHactive - PDATA_WORD(3) >= _DP_HSYNC_FRONT_PORCH))
            {
                // HSW = H porch - _DP_HSYNC_FRONT_PORCH
                PDATA_WORD(2) = PDATA_WORD(1) - usDpHactive - _DP_HSYNC_FRONT_PORCH;

                // Hstart = HSW
                PDATA_WORD(4) = PDATA_WORD(2);
            }
            else
            {
                // HSW = HSW min
                PDATA_WORD(2) = PDATA_WORD(3);

                // Hstart = HSW min
                PDATA_WORD(4) = PDATA_WORD(3);
            }
        }
        else
        {
            // Hstart = Htotal - Hactive - _DP_HSYNC_FRONT_PORCH
            PDATA_WORD(4) = PDATA_WORD(1) - usDpHactive - _DP_HSYNC_FRONT_PORCH;
        }

        // Set HSW and HSP => positive
        ScalerSetByte(PB8_47_MN_DPF_HSW_M, (pData[4] & ~_BIT7));
        ScalerSetByte(PB8_48_MN_DPF_HSW_L, pData[5]);

        // Set Hstart
        ScalerSetByte(PB8_43_MN_DPF_HST_M, pData[8]);
        ScalerSetByte(PB8_44_MN_DPF_HST_L, pData[9]);

        DebugMessageRx1("###Origin usVTotal###", usDpVtotal);

        if(ScalerDpRx1InterlaceCheck(&usDpVtotal, &ucOddFlg) == _TRUE) // Interlace
        {
            DebugMessageRx1("7. IIIIIInterLace Vtotal", usDpVtotal);
        }
        else // Progressive
        {
            DebugMessageRx1("7. PPPPProgressive", 0);
        }

        // Set Vtotal
        ScalerSetByte(PB8_49_MN_DPF_VTT_M, (usDpVtotal >> 8));
        ScalerSetByte(PB8_4A_MN_DPF_VTT_L, (usDpVtotal & 0xFF));

        // Get Vactive
        ScalerRead(PB9_16_MSA_VHT_0, 2, &pData[4], _AUTOINC);

        // V Front porch must not be less than 2 because of V scaling down.
        // Set Vstart -> (Vtotal - Vactive - Frontporch)
        PDATA_WORD(0) = usDpVtotal - PDATA_WORD(2) - GET_DP_RX1_VFRONT_PORCH();
        ScalerSetByte(PB8_4B_MN_DPF_VST_M, pData[0]);
        ScalerSetByte(PB8_4C_MN_DPF_VST_L, pData[1]);

        // Set VSW; Set VSP => Positive
        ScalerSetByte(PB8_4F_MN_DPF_VSW_M, (HIBYTE(_DP_VSYNC_WIDTH) & ~_BIT7));
        ScalerSetByte(PB8_50_MN_DPF_VSW_L, LOBYTE(_DP_VSYNC_WIDTH));

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
        if(GET_AIO_MODERN_STANDBY_MODE() == _TRUE)
        {
            // Set Odd Field BS to VS Delay
            ScalerSetByte(PB8_35_OVBLK2VS_H, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayOdd >> 16));
            ScalerSetByte(PB8_36_OVBLK2VS_M, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayOdd >> 8));
            ScalerSetByte(PB8_37_OVBLK2VS_L, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayOdd >> 0));

            // Set Even Field BS to VS Delay
            ScalerSetByte(PB8_32_EVBLK2VS_H, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayEven >> 16));
            ScalerSetByte(PB8_33_EVBLK2VS_M, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayEven >> 8));
            ScalerSetByte(PB8_34_EVBLK2VS_L, (BYTE)(g_stDpRx1LinkInfo.ulVBsToBsDelayEven >> 0));
        }
        else
#endif
        {
            ulBs2VsDelay = ScalerDpRx1GetBStoVSDelay();

            // Set Odd Field BS to VS Delay
            ScalerSetByte(PB8_35_OVBLK2VS_H, (BYTE)(ulBs2VsDelay >> 16));
            ScalerSetByte(PB8_36_OVBLK2VS_M, (BYTE)(ulBs2VsDelay >> 8));
            ScalerSetByte(PB8_37_OVBLK2VS_L, (BYTE)(ulBs2VsDelay >> 0));

            if((bit)ucOddFlg == _TRUE)
            {
                // Get Htotal
                ScalerRead(PB9_08_MSA_HTT_0, 2, &pData[10], _AUTOINC);

                // BStoVSDelay = BStoVSDelay + (Link Clk * 256 / Stream Clk) * ((DWORD)Htotal) / 256;
                ulBs2VsDelay += ((((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270UL) * 256) / ((DWORD)GET_INPUT_PIXEL_CLK()) * ((DWORD)PDATA_WORD(5)) / 256 / 2;

                SET_DP_RX1_INTERLACE_VTOTAL_NUMBER(_ODD);
            }
            else
            {
                SET_DP_RX1_INTERLACE_VTOTAL_NUMBER(_EVEN);
            }

            // Set Even Field BS to VS Delay
            ScalerSetByte(PB8_32_EVBLK2VS_H, (BYTE)(ulBs2VsDelay >> 16));
            ScalerSetByte(PB8_33_EVBLK2VS_M, (BYTE)(ulBs2VsDelay >> 8));
            ScalerSetByte(PB8_34_EVBLK2VS_L, (BYTE)(ulBs2VsDelay >> 0));
        }

        // Choose VS Rising to Reset FIFO
        ScalerSetBit(PB8_20_PG_CTRL_0, ~_BIT5, 0x00);

        // Set DP FREESYNC Mode Disable
        ScalerSetBit(PB8_F0_DP_RSV0, ~_BIT0, 0x00);

        // Set full last line Mode
        ScalerSetBit(PB8_30_DPF_CTRL_0, ~(_BIT7 | _BIT5 | _BIT4), 0x00);

        DebugMessageRx1("FREESYNC Mode Disabled", ScalerGetByte(PB8_30_DPF_CTRL_0));
    }

    // Double Buffer to Apply Display Format Setting
    ScalerSetBit(PB8_30_DPF_CTRL_0, ~_BIT6, _BIT6);

    ScalerDpRx1VideoSetting();

    return _TRUE;
}
//--------------------------------------------------
// Description  : DP Video Fifo Check
// Input Value  : Fifo Check Condition
// Output Value : True --> Fifo not over/underflow
//--------------------------------------------------
bit ScalerDpRx1FifoCheck(EnumDpFifoCheckCondition enumFifoCheckCondition)
{
    if(enumFifoCheckCondition == _DP_FIFO_DELAY_CHECK)
    {
        ScalerSetBit(PB8_21_PG_CTRL_1, ~(_BIT4 | _BIT2 | _BIT0), (_BIT4 | _BIT2 | _BIT0));

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
        if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
        {
            // awto: PB8_21 under/overflow flags are latched (write 1 clears): one check after the 2 frames covers them (#314)
            ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());

            if((ScalerGetBit(PB8_21_PG_CTRL_1, _BIT4) == _BIT4) || (ScalerGetBit(PB8_21_PG_CTRL_1, _BIT2) == _BIT2))
            {
                return _FALSE;
            }
        }
    }
    else
    {
        if((ScalerGetBit(PB8_21_PG_CTRL_1, _BIT4) == _BIT4) || (ScalerGetBit(PB8_21_PG_CTRL_1, _BIT2) == _BIT2))
        {
            return _FALSE;
        }
    }

    if(ScalerGetBit(PB9_3B_DP_IRQ_CTRL1, _BIT4) == 0x00)
    {
        // Enable DP No Video Stream IRQ
        ScalerDpRx1SetNoVideoStreamIRQ(_ENABLE);
    }

    if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x02, 0x05, _BIT0) == 0x00)
    {
        // Set DP Receive Port0 In Sync
        ScalerDpRx1SinkStatusSet(_DP_SINK_REVEICE_PORT0, _DP_SINK_IN_SYNC);
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : HDCP Reset For Dp Rx1
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPBlockReset(void)
{
    // Reset HDCP Block
    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, _BIT0);
    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT0, 0x00);

#if(_AWTO_HDCP == _ON)    // awto: HDCP DPCD space is idle-zero without HDCP (#44)
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x29, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2A, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2B, 0x00);

    for(pData[0] = 0; pData[0] < 20; pData[0]++)
    {
        ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x14 + pData[0]), 0x00);
    }

    for(pData[0] = 0; pData[0] < 15; pData[0]++)
    {
        ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x2C + pData[0]), 0x00);
    }

    SET_DP_RX1_AUX_MANUAL_MODE();

    // Clear Aksv
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x07, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x08, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x09, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0A, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0B, 0x00);

    SET_DP_RX1_AUX_AUTO_MODE();
#else
    // awto: only the source-written Aksv is cleared; V' / RxStatus / KSV FIFO are written by HDCP code only (#44)
    SET_DP_RX1_AUX_MANUAL_MODE();

    // Clear Aksv
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x07, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x08, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x09, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0A, 0x00);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x0B, 0x00);

    SET_DP_RX1_AUX_AUTO_MODE();
#endif

#if((_DP_TX_SUPPORT == _ON) && (_DP_MST_SUPPORT == _ON))
    ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_IDLE);
#endif
}

#if(_AWTO_HDCP == _ON)
//--------------------------------------------------
// Description  : Check whether HDCP is valid
// Input Value  : None
// Output Value : TRUE => HDCP valid
//--------------------------------------------------
bit ScalerDpRx1HdcpCheckValid(void)
{
    if(GET_DP_RX1_HDCP_MODE() == _HDCP_14)
    {
        if(ScalerGetBit(PB0_20_HDCP_DEBUG, (_BIT7 | _BIT6 | _BIT5)) == (_BIT7 | _BIT6 | _BIT5))
        {
            return _TRUE;
        }
    }
#if(_DP_HDCP_2_2_SUPPORT == _ON)
    else
    {
        if(ScalerGetBit(PB0_20_HDCP_DEBUG, _BIT4) == _BIT4)
        {
            if((ScalerGetByte(PB0_1E_HDCP_INTGT_VRF_ANS_MSB) == 0x53) && (ScalerGetByte(PB0_1F_HDCP_INTGT_VRF_ANS_LSB) == 0x1F))
            {
                return _TRUE;
            }
        }
    }
#endif

    return _FALSE;
}

//--------------------------------------------------
// Description  : Check whether HDCP is enabled
// Input Value  : None
// Output Value : TRUE => HDCP Enabled
//--------------------------------------------------
bit ScalerDpRx1HdcpCheckEnabled(void)
{
    if(GET_DP_RX1_HDCP_MODE() == _HDCP_14)
    {
        if(ScalerGetBit(PB0_20_HDCP_DEBUG, (_BIT7 | _BIT5)) == (_BIT7 | _BIT5))
        {
            if((ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x07) != 0x00) ||
               (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x08) != 0x00) ||
               (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x09) != 0x00) ||
               (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0A) != 0x00) ||
               (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0B) != 0x00))
            {
                return _TRUE;
            }
        }
    }
#if(_DP_HDCP_2_2_SUPPORT == _ON)
    else
    {
        if(ScalerGetBit(PB0_20_HDCP_DEBUG, _BIT4) == _BIT4)
        {
            return _TRUE;
        }
    }
#endif

    return _FALSE;
}
//--------------------------------------------------
// Description  : DP HDCP Measure Check
// Input Value  : None
// Output Value : FALSE => Measure Check Fail
//--------------------------------------------------
bit ScalerDpRx1HdcpMeasureCheck(void)
{
    DWORD ulLinkClk = 0;
    WORD usHTotalCount = 0;

    // Pop up Main Stream Attributes
    ScalerSetBit(PB9_00_MN_STRM_ATTR_CTRL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT3 | _BIT2), (_BIT7 | _BIT6 | _BIT5 | _BIT3));

    // Get Vtotal
    ScalerRead(PB9_10_MSA_VTTE_0, 2, &pData[10], _AUTOINC);

    if(PDATA_WORD(5) == 0)
    {
        return _FALSE;
    }

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_FREESYNC_ENABLED() == _TRUE)
    {
        return _FALSE;
    }
#endif

    // [5] ln_ck_sel = 1'b1 -> CDR Clock
    // [4:0] DP_XTAL_CYCLE = 5'b00100 -> XTAL Counter Cycles = 2000
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT2));

    // [1:0] freqdet_lane_sel = 2'b00 -> Lane0
    ScalerSetBit(PB0_51_DP_SIG_DET_1, ~(_BIT1 | _BIT0), _D1_DP_LANE0);

    // [6] LANE_COUNT_CLEAR = 0 -> Keep the LANE_COUNT value
    ScalerSetBit(PB0_52_DP_SIG_DET_2, ~_BIT6, 0x00);

    // [7] DP_SIG_DET_EN = 1'b1 -> Enable Signal Detection
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, _BIT7);

    // Waiting for Measure Done
    ScalerTimerDelayXms(2);

    if(ScalerGetBit(PB0_50_DP_SIG_DET_0, _BIT6) == _BIT6)
    {
        PDATA_WORD(0) = ((((WORD)ScalerGetByte(PB0_53_DP_SIG_DET_3)) << 8) | ScalerGetByte(PB0_54_DP_SIG_DET_4));
    }
    else
    {
        if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR2)
        {
            PDATA_WORD(0) = 0x4E20;
        }
        else if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR)
        {
            PDATA_WORD(0) = 0x2710;
        }
        else // Both Default && _DP_LINK_RBR Case
        {
            PDATA_WORD(0) = 0x1770;
        }
    }

    // [7] DP_SIG_DET_EN = 0 -> Disable Signal Detection
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);

    PDATA_DWORD(0) = (((DWORD)PDATA_WORD(0)) * _GDI_CLK_KHZ);

    // Link Clk in KHz
    ulLinkClk = (PDATA_DWORD(0) / 1000);

    DebugMessageRx1("Current Link Clk", ulLinkClk);

    // Start to Measure Vertical BS to BS Counter by GDI Clock
    ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, 0x00);
    ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, _BIT7);

    if(ScalerTimerPollingFlagProc(_DP_MEASURE_POLLING_TIMEOUT, PB8_58_MN_MEAS_CTRL, _BIT6, _TRUE) == _FALSE)
    {
        return _FALSE;
    }

    // Pop up The result
    SET_DP_RX1_MEASURE_POP_UP();

    // Get Measure Result
    ScalerRead(PB8_58_MN_MEAS_CTRL, 3, &pData[1], _AUTOINC);

    // Get Measure Htotal Counts
    ScalerRead(PB8_5B_MN_MEAS_HLN_M, 2, &pData[6], _AUTOINC);

    // Disable Measure Block
    ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, 0x00);

    // Convert HTotal Count from 1/2 Link Clk to GDI Clk
    usHTotalCount = ((DWORD)PDATA_WORD(3) * _GDI_CLK_KHZ * 2 + (ulLinkClk >> 1)) / ulLinkClk;

    PDATA_DWORD(0) = (PDATA_DWORD(0) & 0x001FFFFF);
    PDATA_DWORD(1) = ((DWORD)usHTotalCount & 0x0000FFFF);

    PDATA_WORD(2) = PDATA_DWORD(0) / PDATA_DWORD(1);

    // 2% Tolerance
    if((ABSDWORD(PDATA_WORD(2), PDATA_WORD(5))) > (PDATA_WORD(5) * 2 / 100))
    {
        return _FALSE;
    }

    return _TRUE;
}
//--------------------------------------------------
// Description  : Check DP Hdcp ReAuth Process
// Input Value  : None
// Output Value : TRUE or FALSE
//--------------------------------------------------
bit ScalerDpRx1HdcpReAuthStatusCheck(void)
{
    if(GET_DP_RX1_HDCP_MODE() == _HDCP_14)
    {
        if((ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x07) != 0x00) || (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x08) != 0x00) ||
           (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x09) != 0x00) || (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0A) != 0x00) ||
           (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0B) != 0x00))
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
        return _TRUE;
    }
}

#endif // End of #if(_AWTO_HDCP == _ON)

//--------------------------------------------------
// Description  : Dp Mac Initial Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MacInitial(void)
{
    // Set Digital Phy to Normal
    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT1, 0x00);

    // DP RGB Output Enable
    ScalerSetBit(PB8_31_DP_OUTPUT_CTRL, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

    // DP CLK Output Enable
    ScalerSetBit(PB8_B8_MN_SCLKG_SDM_CTRL, ~_BIT6, _BIT6);

    // 0x00:disable error correction, 0xF4:enable all error correction
    ScalerSetBit(PB9_00_MN_STRM_ATTR_CTRL, ~_BIT1, _BIT1);

    // Disable DP Fifo Under/OverFlow Watch Dog
    ScalerDpRx1SetFifoWD(_DISABLE);

    // Disable DP Fifo Under/OverFlow IRQ
    ScalerDpRx1SetFifoIRQ(_DISABLE);

    // Disable DP No Video Stream IRQ
    ScalerDpRx1SetNoVideoStreamIRQ(_DISABLE);

    ScalerDpRx1SetInitialRSV0InfoType();

#if((_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON) && (_HW_DP_VSC_SDP_REG_SUPPORT != _ON))
    ScalerDpRx1SetInitialRSV1InfoType();
#endif

    CLR_DP_RX1_MSA_FAIL_MAC_RESET_COUNT();
}
//--------------------------------------------------
// Description : check DP CDR locked or unlocked
// Input Value  : DP Lane
// Output Value : True --> locked; False --> unlocked
//--------------------------------------------------
bit ScalerDpRx1MeasureLaneCDRClk(BYTE ucDpLinkRate, BYTE ucDpRx1LaneNumber)
{
    WORD usCDRClockCount = 0;

    switch(ucDpLinkRate)
    {
        case _DP_LINK_HBR2:

            if((abs(isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - 0x2710)) > (0x2710 >> 4))
            {
                return _TRUE;
            }

            break;

        case _DP_LINK_HBR:

            if((abs(isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - 0x1388)) > (0x1388 >> 4))
            {
                return _TRUE;
            }

            break;

        default:
        case _DP_LINK_RBR:

            if((abs(isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - 0xBB8)) > (0xBB8 >> 4))
            {
                return _TRUE;
            }

            break;
    }

    // Select Measure CDR Clock & XTAL 27M Count 1000 Times
    ScalerSetByte(PB0_50_DP_SIG_DET_0, 0x23);

    // Select CDR Lane
    ScalerSetBit(PB0_51_DP_SIG_DET_1, ~(_BIT1 | _BIT0), ucDpRx1LaneNumber);

    // [6] LANE_COUNT_CLEAR = 0 -> Keep the LANE_COUNT value
    ScalerSetBit(PB0_52_DP_SIG_DET_2, ~_BIT6, 0x00);

    // Toggle Start Measure
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, 0x00);
    ScalerSetBit(PB0_50_DP_SIG_DET_0, ~_BIT7, _BIT7);

    // Delay Time us [5,150] Polling for Measure Done
    for(pData[0] = 0; pData[0] <= 30; pData[0]++)
    {
        DELAY_5US();

        if(ScalerGetBit(PB0_50_DP_SIG_DET_0, _BIT6) == _BIT6)
        {
            break;
        }
    }

    if(ScalerGetBit(PB0_50_DP_SIG_DET_0, _BIT6) == 0x00)
    {
        return _FALSE;
    }

    usCDRClockCount = ((((WORD)ScalerGetByte(PB0_53_DP_SIG_DET_3)) << 8) | ScalerGetByte(PB0_54_DP_SIG_DET_4));

    if(abs(isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] - usCDRClockCount) > (isr_g_ppusDpRxClockCount_P(_DP_RX1_PORT_INDEX)[ucDpRx1LaneNumber] >> 7))
    {
        return _FALSE;
    }

    return _TRUE;
}

#if(_DP_LINK_RATE_CHANGE_WO_LT_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Rebuild PHY when DPCD Link Rate != PHY Link Rate
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1LinkRateChangeRebuildPhy(void)
{
    SET_DP_RX1_AUX_MANUAL_MODE();

    if((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_NORMAL_LINK_TRAINING_PASS) && (ScalerDpRx1LinkRateChange() == _TRUE))
    {
        ScalerDpRx1RebuildPhy(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01));

        SET_DP_RX1_AUX_AUTO_MODE();

        // De-Skew Circuit Reset
        ScalerSetBit(PB0_0E_DESKEW_PHY, ~(_BIT7 | _BIT6), 0x00);
        ScalerSetBit(PB0_0E_DESKEW_PHY, ~(_BIT7 | _BIT6), _BIT6);

        // Mac Reset After Link Clock Stable
        ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT1, _BIT1);
        ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT1, 0x00);

        // Delay for Lane Alignment after Mac Reset
        ScalerTimerDelayXms(2);
    }

    SET_DP_RX1_AUX_AUTO_MODE();
}

//--------------------------------------------------
// Description  : Check DPCD Link Rate = PHY Link Rate?
// Input Value  : None
// Output Value : True : Link Rate Change
//              : False :
//--------------------------------------------------
bit ScalerDpRx1LinkRateChange(void)
{
    EnumDpLinkRate enumPhyRate = _DP_LINK_NONE;

    if(ScalerGetBit(P7A_23_CMU_09, (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2)) == (_BIT3 | _BIT2))
    {
        enumPhyRate = _DP_LINK_HBR2;
    }
    else if(ScalerGetBit(P7A_23_CMU_09, (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2)) == (_BIT5 | _BIT3))
    {
        enumPhyRate = _DP_LINK_HBR;
    }
    else if(ScalerGetBit(P7A_23_CMU_09, (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2)) == (_BIT6 | _BIT5))
    {
        enumPhyRate = _DP_LINK_RBR;
    }

    if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == enumPhyRate)
    {
        return _FALSE;
    }
    else
    {
        return _TRUE;
    }
}
#endif

//--------------------------------------------------
// Description  : Signal PreDetection for DP(Power Normal)
// Input Value  : None
// Output Value : True : DP Signal Detected
//              : False : No Signal
//--------------------------------------------------
bit ScalerDpRx1NormalPreDetect(void)
{
    // For Dp PHY CTS Test
#if(_AWTO_DP_PHYCTS == _ON)
    if((GET_DP_RX1_PHY_CTS_FLG() == _TRUE) || (ScalerDpRx1GetDpcdBitInfo(0x00, 0x02, 0x70, _BIT7) == _BIT7))
    {
        ScalerDpRx1PhyCTS();

        return _FALSE;
    }
#endif

#if(_DP_MST_SUPPORT == _ON)

    if(GET_DP_RX1_AUX_CH_POWER_ON_WAKE_UP() == _TRUE)
    {
        CLR_DP_RX1_AUX_CH_POWER_ON_WAKE_UP();
    }

#endif

#if(_DP_RX1_ASSR_MODE_SUPPORT == _ON)

    // ASSR Mode Setting
    ScalerDpRx1ASSRModeSetting();

#endif

#if(_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON)
    CLR_DP_RX1_SOURCE_TYPE_JUDGE();
#endif

    switch(GET_DP_RX1_LINK_TRAINING_STATUS())
    {
        case _DP_NORMAL_LINK_TRAINING_PASS:
        case _DP_LINK_STATUS_FAIL:

            CLR_DP_RX1_VALID_VIDEO_CHECK();

#if(_DP_MST_SUPPORT == _ON)
            ScalerDpRx1MstInfoBackup(_DP_MST_BACKUP_INFO_RESET);
#endif
            if((ScalerDpRx1CDRCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE) &&
               ((ScalerDpRx1DFECheck() == _TRUE) || (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE)) &&
               (ScalerDpRx1MarginLinkCheck() == _TRUE) &&
               (ScalerDpRx1AlignCheck() == _TRUE) &&
               (ScalerDpRx1DecodeCheck() == _TRUE))
            {
                /*
                DebugMessageRx1("9. Lane0 LE Diff", (g_pucDpRx1LEMaxTemp[0] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[0]));
                DebugMessageRx1("9. Lane1 LE Diff", (g_pucDpRx1LEMaxTemp[1] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[1]));
                DebugMessageRx1("9. Lane2 LE Diff", (g_pucDpRx1LEMaxTemp[2] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[2]));
                DebugMessageRx1("9. Lane3 LE Diff", (g_pucDpRx1LEMaxTemp[3] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[3]));
                DebugMessageRx1("9. Lane0 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[0]);
                DebugMessageRx1("9. Lane1 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[1]);
                DebugMessageRx1("9. Lane2 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[2]);
                DebugMessageRx1("9. Lane3 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[3]);
                DebugMessageRx1("9. Lane0 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[0] - g_pucDpRx1Tap0MinTemp[0]));
                DebugMessageRx1("9. Lane1 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[1] - g_pucDpRx1Tap0MinTemp[1]));
                DebugMessageRx1("9. Lane2 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[2] - g_pucDpRx1Tap0MinTemp[2]));
                DebugMessageRx1("9. Lane3 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[3] - g_pucDpRx1Tap0MinTemp[3]));
                DebugMessageRx1("9. Lane0 Tap0 Max", g_pucDpRx1Tap0MaxTemp[0]);
                DebugMessageRx1("9. Lane1 Tap0 Max", g_pucDpRx1Tap0MaxTemp[1]);
                DebugMessageRx1("9. Lane2 Tap0 Max", g_pucDpRx1Tap0MaxTemp[2]);
                DebugMessageRx1("9. Lane3 Tap0 Max", g_pucDpRx1Tap0MaxTemp[3]);
                DebugMessageRx1("9. FLD Band", ScalerGetByte(PB0_BF_LANE0_A_CDR_02));
                DebugMessageRx1("9. Best FLD Band", ScalerGetByte(PB0_BE_LANE0_A_CDR_01));
                DebugMessageRx1("9. Lane0 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[0] - g_pucDpRx1Tap0MinTemp2[0]));
                DebugMessageRx1("9. Lane1 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[1] - g_pucDpRx1Tap0MinTemp2[1]));
                DebugMessageRx1("9. Lane2 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[2] - g_pucDpRx1Tap0MinTemp2[2]));
                DebugMessageRx1("9. Lane3 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[3] - g_pucDpRx1Tap0MinTemp2[3]));
                DebugMessageRx1("9. Lane0 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[0]);
                DebugMessageRx1("9. Lane1 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[1]);
                DebugMessageRx1("9. Lane2 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[2]);
                DebugMessageRx1("9. Lane3 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[3]);
                DebugMessageRx1("9. TP2 Check Result", g_pucDpRxEQCRC_P(_DP_RX1_PORT_INDEX));
                */

                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_LINK_STATUS_IRQ);

#if(_DP_RX_MI_DONGLE_SUPPORT == _ON)
                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_LONG_HOTPLUG_EVENT);

                g_ucDpRx1FakeLTLaneCount = g_pucDpRxLaneCount_P(_DP_RX1_PORT_INDEX);
#endif
                if(GET_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH() == _TRUE)
                {
#if(_DP_ULTRA_HDR_SUPPORT == _ON)
                    ScalerSyncDpSecDataResetProc(_D1_INPUT_PORT);

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
                    if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
                    {
                        // Need to delay 3 Frames totally after Secondary Data Block Reset
                        ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());
                    }
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
                    if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
                    {
                        ScalerTimerDelayXms(AWTO_DP_ONE_FRAME());
                    }

                    CLR_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH();
                }

                SET_DP_RX1_AUX_MANUAL_MODE();

                if(GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_LINK_STATUS_FAIL)
                {
                    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_NORMAL_LINK_TRAINING_PASS);

                    ScalerDpRx1ScrambleSetting();
                }

                SET_DP_RX1_AUX_AUTO_MODE();

                if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == _BIT1) ||
                   (ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == (_BIT2 | _BIT0)))
                {
                    return _FALSE;
                }

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
                CLR_DP_RX_D1_MARGIN_LINK_HBR2();
#endif

                return _TRUE;
            }
            else
            {
                DebugMessageRx1("7. Link Status Fail IRQ", 0);

#if(_DP_LINK_RATE_CHANGE_WO_LT_SUPPORT == _ON)
                ScalerDpRx1LinkRateChangeRebuildPhy();
#endif
                SET_DP_RX1_AUX_MANUAL_MODE();

                if((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_NORMAL_LINK_TRAINING_PASS) || (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_LINK_STATUS_FAIL))
                {
                    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_LINK_STATUS_FAIL);

                    ScalerTimerActiveTimerEvent(SEC(0.1), _SCALER_TIMER_EVENT_DP_RX1_LINK_STATUS_IRQ);
                }

                SET_DP_RX1_AUX_AUTO_MODE();
            }

            break;

        case _DP_LINK_TRAINING_FAIL:

            ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_LINK_STATUS_IRQ);

            ScalerDpRx1LinkStatusIRQ();

            break;

        case _DP_FAKE_LINK_TRAINING_PASS:
        case _DP_FAKE_LINK_TRAINING_PASS_VBIOS:

            CLR_DP_RX1_VALID_VIDEO_CHECK();

#if(_DP_MST_SUPPORT == _ON)
            ScalerDpRx1MstInfoBackup(_DP_MST_BACKUP_INFO_RESET);
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
            if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
            {
                ScalerTimerDelayXms(30);
            }

            DebugMessageRx1("7. DP Rebuild PHY", GET_DP_RX1_LINK_TRAINING_STATUS());

            ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_LINK_STATUS_IRQ);

            SET_DP_RX1_AUX_MANUAL_MODE();

            if((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS) || (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS_VBIOS))
            {
                ScalerDpRx1RebuildPhy(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01));
            }

            SET_DP_RX1_AUX_AUTO_MODE();

            // De-Skew Circuit Reset
            ScalerSetBit(PB0_0E_DESKEW_PHY, ~(_BIT7 | _BIT6), 0x00);
            ScalerSetBit(PB0_0E_DESKEW_PHY, ~(_BIT7 | _BIT6), _BIT6);

            // Mac Reset After Link Clock Stable
            ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT1, _BIT1);
            ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT1, 0x00);

            // Delay for Lane Alignment after Mac Reset
            ScalerTimerDelayXms(2);

            if(GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS)
            {
                ScalerDpRx1DecodeErrorCountReset();
            }

            if((ScalerDpRx1CDRCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE) &&
               ((ScalerDpRx1DFECheck() == _TRUE) || (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE)) &&
               (ScalerDpRx1MarginLinkCheck() == _TRUE) &&
               (ScalerDpRx1AlignCheck() == _TRUE) &&
               (ScalerDpRx1DecodeCheck() == _TRUE))
            {
                DebugMessageRx1("7. Rebuild Phy Pass", 0);

                /*
                DebugMessageRx1("9. Lane0 LE Diff", (g_pucDpRx1LEMaxTemp[0] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[0]));
                DebugMessageRx1("9. Lane1 LE Diff", (g_pucDpRx1LEMaxTemp[1] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[1]));
                DebugMessageRx1("9. Lane2 LE Diff", (g_pucDpRx1LEMaxTemp[2] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[2]));
                DebugMessageRx1("9. Lane3 LE Diff", (g_pucDpRx1LEMaxTemp[3] - g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[3]));
                DebugMessageRx1("9. Lane0 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[0]);
                DebugMessageRx1("9. Lane1 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[1]);
                DebugMessageRx1("9. Lane2 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[2]);
                DebugMessageRx1("9. Lane3 LE Min", g_ppucDpRxLEMinTemp_P(_DP_RX1_PORT_INDEX)[3]);
                DebugMessageRx1("9. Lane0 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[0] - g_pucDpRx1Tap0MinTemp[0]));
                DebugMessageRx1("9. Lane1 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[1] - g_pucDpRx1Tap0MinTemp[1]));
                DebugMessageRx1("9. Lane2 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[2] - g_pucDpRx1Tap0MinTemp[2]));
                DebugMessageRx1("9. Lane3 Tap0 Diff", (g_pucDpRx1Tap0MaxTemp[3] - g_pucDpRx1Tap0MinTemp[3]));
                DebugMessageRx1("9. Lane0 Tap0 Max", g_pucDpRx1Tap0MaxTemp[0]);
                DebugMessageRx1("9. Lane1 Tap0 Max", g_pucDpRx1Tap0MaxTemp[1]);
                DebugMessageRx1("9. Lane2 Tap0 Max", g_pucDpRx1Tap0MaxTemp[2]);
                DebugMessageRx1("9. Lane3 Tap0 Max", g_pucDpRx1Tap0MaxTemp[3]);
                DebugMessageRx1("9. FLD Band", ScalerGetByte(PB0_BF_LANE0_A_CDR_02));
                DebugMessageRx1("9. Best FLD Band", ScalerGetByte(PB0_BE_LANE0_A_CDR_01));
                DebugMessageRx1("9. D10.2 Counter", g_usDpRx1ClockCount);
                DebugMessageRx1("9. D10.2 Counter1", g_usDpRx1ClockCount1);
                DebugMessageRx1("9. Lane0 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[0] - g_pucDpRx1Tap0MinTemp2[0]));
                DebugMessageRx1("9. Lane1 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[1] - g_pucDpRx1Tap0MinTemp2[1]));
                DebugMessageRx1("9. Lane2 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[2] - g_pucDpRx1Tap0MinTemp2[2]));
                DebugMessageRx1("9. Lane3 Tap0 Diff 2", (g_pucDpRx1Tap0MaxTemp2[3] - g_pucDpRx1Tap0MinTemp2[3]));
                DebugMessageRx1("9. Lane0 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[0]);
                DebugMessageRx1("9. Lane1 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[1]);
                DebugMessageRx1("9. Lane2 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[2]);
                DebugMessageRx1("9. Lane3 Tap0 Max 2", g_pucDpRx1Tap0MaxTemp2[3]);
                DebugMessageRx1("9. Best FLD Band", ScalerGetByte(PB0_BE_LANE0_A_CDR_01));
                DebugMessageRx1("9. TP2 Check Result", g_pucDpRxEQCRC_P(_DP_RX1_PORT_INDEX));
                DebugMessageRx1("9. DP Requeset", ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x06));
                DebugMessageRx1("9. DP Requeset", ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x07));
                DebugMessageRx1("9. Lane0 Tap1 Max", ScalerGetByte(P7A_A5_L0_INIT_3));
                DebugMessageRx1("9. Lane1 Tap1 Max", ScalerGetByte(P7A_B5_L1_INIT_3));
                DebugMessageRx1("9. Lane2 Tap1 Max", ScalerGetByte(P7A_C5_L2_INIT_3));
                DebugMessageRx1("9. Lane3 Tap1 Max", ScalerGetByte(P7A_D5_L3_INIT_3));
                */

                SET_DP_RX1_AUX_MANUAL_MODE();

                if((GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS) || (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS_VBIOS))
                {
                    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_NORMAL_LINK_TRAINING_PASS);
                    CLR_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH();

                    ScalerDpRx1ScrambleSetting();
                }

                SET_DP_RX1_AUX_AUTO_MODE();

#if(_DP_ULTRA_HDR_SUPPORT == _ON)
                ScalerSyncDpSecDataResetProc(_D1_INPUT_PORT);

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
                if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
                {
                    // Need to delay 3 Frames totally after Secondary Data Block Reset
                    ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());
                }
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
                if(GET_AIO_MODERN_STANDBY_MODE() == _FALSE)
#endif
                {
                    ScalerTimerDelayXms(AWTO_DP_ONE_FRAME());
                }

                if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == _BIT1) ||
                   (ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == (_BIT2 | _BIT0)))
                {
                    return _FALSE;
                }

#if(_DP_HBR2_MARGIN_LINK_SUPPORT == _ON)
                CLR_DP_RX_D1_MARGIN_LINK_HBR2();
#endif

#if((_DP_MST_SUPPORT == _ON) && (_DP_TX_SUPPORT == _ON))
                if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
                {
                    // Reset Daisy Chain Async-fifo
                    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT6, _BIT6);
                    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT6, 0x00);
                }
#endif
                return _TRUE;
            }
            else
            {
                DebugMessageRx1("7. DP Rebuild PHY Fail", 0);

                SET_DP_RX1_AUX_MANUAL_MODE();

                if(GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS_VBIOS)
                {
                    ScalerDpRx1DpcdLinkStatusReset(_DP_DPCD_LINK_STATUS_INITIAL);

                    ScalerDpRx1HDCPBlockReset();

#if(_DP_HDCP_2_2_SUPPORT == _ON)
                    ScalerDpRx1Hdcp2ResetProc();
#endif
                }
                else if(GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS)
                {
#if(_DP_RX_MI_DONGLE_SUPPORT == _ON)
                    ScalerTimerActiveTimerEvent(SEC(1), _SCALER_TIMER_EVENT_DP_RX1_LONG_HOTPLUG_EVENT);
#endif
                    SET_DP_RX1_LINK_TRAINING_STATUS(_DP_LINK_STATUS_FAIL);

                    SET_DP_RX1_AUX_AUTO_MODE();

                    return _TRUE;
                }

                SET_DP_RX1_AUX_AUTO_MODE();
            }

            break;

        case _DP_LINK_TRAINING_NONE:

            if(GET_DP_RX1_VALID_VIDEO_CHECK() == _TRUE)
            {
                ScalerDpRx1ValidSignalDetection();

                DebugMessageRx1("7. VBIOS Check !!!!!!!", GET_DP_RX1_FAKE_LINK_TRAINING());
            }

            break;

        default:

            break;
    }

    if(GET_DP_RX1_VALID_VIDEO_CHECK() == _TRUE)
    {
        CLR_DP_RX1_VALID_VIDEO_CHECK();

#if(_DP_MST_SUPPORT == _ON)
        ScalerDpRx1MstInfoBackup(_DP_MST_BACKUP_INFO_RESET);
#endif
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Check Dp Training Pattern 1 for PHY CTS
// Input Value  : None
// Output Value : TRUE --> TP1 Pass
//--------------------------------------------------
#if(_AWTO_DP_PHYCTS == _ON)
bit ScalerDpRx1PhyCtsTp1Check(void)
{
    // Wait for 10ms
    ScalerTimerDelayXms(10);

    // Clear 8B/10B Decode Error Flags
    ScalerSetBit(PB0_06_DECODE_10B8B_ERROR, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Wait for 2ms
    ScalerTimerDelayXms(2);

    ScalerSetByte(P7A_0C_SDM_01, ScalerGetByte(PB0_06_DECODE_10B8B_ERROR));
    ScalerSetByte(P7A_0D_SDM_02, ScalerGetByte(PB0_14_EQ_CRC_3));

    switch(g_ucDpRx1PhyCtsCtrl & 0x30)
    {
        case 0x00: // Lane0 Test

            // EQ auto K,Check lane0 CRC
            pData[0] = 0x10;

            break;

        case 0x10: // Lane1 Test

            // EQ auto K,Check lane1 CRC
            pData[0] = 0x20;

            break;

        case 0x20: // Lane2 Test

            // EQ auto K,Check lane2 CRC
            pData[0] = 0x40;

            break;

        case 0x30: // Lane3 Test

            // EQ auto K,Check lane3 CRC
            pData[0] = 0x80;

            break;

        default:

            pData[0] = 0x00;

            break;
    }

    if(((ScalerGetByte(P7A_0C_SDM_01) & 0x0F) == 0x00) &&
       ((ScalerGetByte(P7A_0D_SDM_02) & pData[0]) != 0x00))
    {
        return _TRUE;
    }

    return _FALSE;
}
#endif
//--------------------------------------------------
// Description  : Check Dp Training Pattern 2 for PHY CTS
// Input Value  : None
// Output Value : TRUE --> TP2 Pass
//--------------------------------------------------
#if(_AWTO_DP_PHYCTS == _ON)
bit ScalerDpRx1PhyCtsTp2Check(void)
{
    ScalerTimerDelayXms(10);

    switch(g_ucDpRx1PhyCtsCtrl & 0x30)
    {
        case 0x00: // Lane0 Test

            ScalerSetBit(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), 0x00);

            break;

        case 0x10: // Lane1 Test

            ScalerSetBit(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), _BIT3);

            break;

        case 0x20: // Lane2 Test

            ScalerSetBit(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), _BIT4);

            break;

        case 0x30: // Lane3 Test

            ScalerSetBit(PB0_08_BIST_PATTERN_SEL, ~(_BIT4 | _BIT3), (_BIT4 | _BIT3));

            break;

        default:
            break;
    }

    // Mac Use Xtal Clk
    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT6, _BIT6);

    // Clear EQ-CRC
    ScalerSetBit(PB0_12_EQ_CRC_1, ~(_BIT7 | _BIT6), _BIT6);

    // Start Calculate EQ-CRC
    ScalerSetBit(PB0_12_EQ_CRC_1, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

    ScalerTimerDelayXms(2);

    ScalerSetByte(P7A_0C_SDM_01, ScalerGetByte(PB0_12_EQ_CRC_1));
    ScalerSetByte(P7A_0D_SDM_02, ScalerGetByte(PB0_13_EQ_CRC_2));

    // Stop Calculate EQ-CRC
    ScalerSetBit(PB0_12_EQ_CRC_1, ~(_BIT7 | _BIT6), _BIT6);

    switch(g_ucDpRx1PhyCtsCtrl & 0x30)
    {
        case 0x00: // Lane0 Test

            pData[0] = 0x01;

            break;

        case 0x10: // Lane1 Test

            pData[0] = 0x02;

            break;

        case 0x20: // Lane2 Test

            pData[0] = 0x04;

            break;

        case 0x30: // Lane3 Test

            pData[0] = 0x08;

            break;

        default:

            pData[0] = 0x00;

            break;
    }

    if((ScalerGetByte(P7A_0C_SDM_01) & pData[0]) != 0x00)
    {
        return _TRUE;
    }

    return _FALSE;
}
#endif
//--------------------------------------------------
// Description  : DP Phy Initial Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1PhyInitial(void)
{
    /////////////
    // Rx Misc //
    /////////////

    // [1] mhl_mode = 1'b0 --> Disable MHL Mode
    ScalerSetBit(P7A_17_BANDGAP_03, ~_BIT1, 0x00);

    // [4] en_mhl_op = 1'b0 --> Disable D1 Port MHL OP
    // [2] HST_BUF_SEL = 1'b0 --> Disable Hysteresis Amplifier in Clock Lane
    ScalerSetBit(P7A_1B_CMU_01, ~(_BIT4 | _BIT2), 0x00);


    /////////////////////
    // CDR DFE Setting //
    /////////////////////

    // [3:1] LE_lowgain_highboost = 3'b100 --> LE HighGain Mode
    ScalerSetBit(P7A_22_CMU_08, ~(_BIT3 | _BIT2 | _BIT1), 0x00);

    // [7] SEL_DFE_DELAY = 1'b0 --> Normal DFE Delay
    ScalerSetBit(P7A_22_CMU_08, ~_BIT7, 0x00);

    // [0] De_brank_en = 1'b0 --> Disable Blank Function
    ScalerSetBit(P7A_AF_L0_GDI_DE, ~_BIT0, 0x00);
    ScalerSetBit(P7A_BF_L1_GDI_DE, ~_BIT0, 0x00);
    ScalerSetBit(P7A_CF_L2_GDI_DE, ~_BIT0, 0x00);
    ScalerSetBit(P7A_DF_L3_GDI_DE, ~_BIT0, 0x00);

    // [3:0] Set Digital PHY Sampling Edge (APHY to DPHY), Spec Suggest Use 0x0F in 6410/6432
    ScalerSetBit(PB0_05_SAMPLE_EDGE, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

    // [7] en_wide_temp = 1'b1 --> Vcp-Vcn = -0.1V
    ScalerSetBit(P7A_35_ANA_CDR_10, ~_BIT7, _BIT7);

    // [3:2] reg_cdr_kvco = 2'b01 --> Analog CDR KVCO = 700M/v
    // [1:0] reg_vcm_tune = 2'b11 --> Vcm = VDD/2
    ScalerSetBit(P7A_30_ANA_CDR_05, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

    // [4] sel_cont3 = 1'b1 --> BBPD UP/DN Pulse Div 3
    ScalerSetBit(P7A_2D_ANA_CDR_02, ~_BIT4, _BIT4);

    // [3:2] ENHANCE_SA_BIAS = 2'b00 --> SumAmp Bias = Normal
    ScalerSetBit(P7A_1D_CMU_03, ~(_BIT3 | _BIT2), 0x00);

    // [7:4] Enable Data Stream Signal Detection
    ScalerSetBit(P7A_19_IMPEDANCE_01, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT6 | _BIT5 | _BIT4));

    // DP Global Parameter MeasureCount Initial
    ScalerSyncDpMeasureCountInitial();
}
//--------------------------------------------------
// Description  : DP Port Source/Sync Scanning and Setting
// Input Value  : None
// Output Value : Source DP --> DP Sync Stable
//                Source None --> No Stable Sync
//--------------------------------------------------
BYTE ScalerDpRx1ScanInputPort(void)
{
    if(GET_DP_RX1_LINK_TRAINING_STATUS() != _DP_NORMAL_LINK_TRAINING_PASS)
    {
        return _SOURCE_NONE;
    }

    // 2nd Scramble Setting Sync
    ScalerDpRx1ScrambleSetting();

    AWTO_SW_MARK(30);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 1);
    if(ScalerDpRx1HdcpCheck() == _FALSE)
    {
        DebugMessageRx1("7. DP HDCP Check Fail", 0);

        ScalerDpRx1CpIRQ(_DP_HDCP_BSTATUS_LINK_INTEGRITY_FAIL);

#if(_DP_LONG_HPD_AFTER_CPIRQ_SUPPORT == _ON)
        if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x11) & _BIT0) == 0x00)
        {
            ScalerTimerReactiveTimerEvent(SEC(1), _SCALER_TIMER_EVENT_DP_RX1_HDCP_LONG_HOTPLUG_EVENT);
        }
#endif

        return _SOURCE_NONE;
    }

    AWTO_SW_MARK(31);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 2);
    if(ScalerDpRx1GetVideoStream() == _FALSE)
    {
        DebugMessageRx1("7. DP Video Stream Fail", 0);

        return _SOURCE_NONE;
    }

#if(_DP_FREESYNC_SUPPORT == _ON)
    if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x07) & _BIT7) == _BIT7)
    {
        SET_DP_FREESYNC_ENABLED();
    }
    else
    {
        CLR_FREESYNC_ENABLED();
    }
#endif

    AWTO_SW_MARK(32);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 3);
    if(ScalerDpRx1MSACheck() == _FALSE)
    {
        DebugMessageRx1("7. DP MSA Fail", 0);

        return _SOURCE_NONE;
    }

#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if((ScalerSyncCheckUrgentEvent() == _TRUE))
    {
        return _SOURCE_NONE;
    }
#endif

    AWTO_SW_MARK(33);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 4);
    if(ScalerDpRx1GetVideoInfo() == _FALSE)
    {
        DebugMessageRx1("7. DP Get Video Info Fail", 0);

        return _SOURCE_NONE;
    }
    else
    {
        ScalerDpRx1SetColorInfo();
    }

    AWTO_SW_MARK(34);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 5);
    if(ScalerDpRx1DisplayFormatSetting() == _FALSE)
    {
        DebugMessageRx1("7. DP Display Format Fail", 0);

        return _SOURCE_NONE;
    }

#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if((ScalerSyncCheckUrgentEvent() == _TRUE))
    {
        return _SOURCE_NONE;
    }
#endif

    AWTO_SW_MARK(35);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 6);
    if(ScalerDpRx1StreamClkRegenerate() == _FALSE)
    {
        DebugMessageRx1("7. DP SteamClk Fail", 0);

        return _SOURCE_NONE;
    }

#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if((ScalerSyncCheckUrgentEvent() == _TRUE))
    {
        return _SOURCE_NONE;
    }
#endif

    AWTO_SW_MARK(36);
    AWTO_SCAN_STAGE(AWTO_SCAN_DP_LT + 7);
    if(ScalerDpRx1FifoCheck(_DP_FIFO_DELAY_CHECK) == _FALSE)
    {
#if(_DP_FREESYNC_SUPPORT == _ON)
        if(GET_FREESYNC_ENABLED() == _TRUE)
        {
            return _SOURCE_NONE;
        }
        else
#endif
        {
#if(_URGENT_EVENT_CHECK_MODE == _ON)
            if((ScalerSyncCheckUrgentEvent() == _TRUE))
            {
                return _SOURCE_NONE;
            }
#endif

            ScalerDpRx1AdjustVsyncDelay();

#if(_URGENT_EVENT_CHECK_MODE == _ON)
            if((ScalerSyncCheckUrgentEvent() == _TRUE))
            {
                return _SOURCE_NONE;
            }
#endif

            if(ScalerDpRx1FifoCheck(_DP_FIFO_DELAY_CHECK) == _FALSE)
            {
#if(_URGENT_EVENT_CHECK_MODE == _ON)
                if((ScalerSyncCheckUrgentEvent() == _TRUE))
                {
                    return _SOURCE_NONE;
                }
#endif

                ScalerDpRx1AdjustVsyncDelay();

#if(_URGENT_EVENT_CHECK_MODE == _ON)
                if((ScalerSyncCheckUrgentEvent() == _TRUE))
                {
                    return _SOURCE_NONE;
                }
#endif

                if(ScalerDpRx1FifoCheck(_DP_FIFO_DELAY_CHECK) == _FALSE)
                {
                    DebugMessageRx1("7. DP Fifo Fail", 0);

                    return _SOURCE_NONE;
                }
            }
        }
    }

    AWTO_SW_MARK(37);
    ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_LONG_HOTPLUG_EVENT);

#if(_DP_FREESYNC_SUPPORT == _ON)
    // Measurement Enable for On-Line VFreq check
    ScalerSetBit(PB8_58_MN_MEAS_CTRL, ~_BIT7, _BIT7);
#endif

    ScalerSetBit(PB8_31_DP_OUTPUT_CTRL, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

#if(_AUDIO_SUPPORT == _ON)
    // Enable Audio Channel
    ScalerAudioDpAudioEnable(_ENABLE, _D1_INPUT_PORT);
#endif

#if(_DP_MST_SUPPORT == _ON)
    CLR_DP_RX1_SOURCE_FIRST_POWER_ON();
#endif

#if(_DP_ULTRA_HDR_SUPPORT == _ON)
    ScalerDpRx1InfoFrameRSV0Initial();
#endif

#if(_DP_FREESYNC_SUPPORT == _ON)
    ScalerFreeSyncDpRx1GetSPDVfreqMaxMin();
#endif

#if((_DP_HDR10_SUPPORT == _ON) && (_AUDIO_SUPPORT == _ON))
    ScalerDpRx1SwitchHDR10CmpAudioInfo();
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
    ScalerDpRx1TimingInfoBackup();
#endif

    DebugMessageRx1("Source DP Rx1 Found", 0);

#if(_DP_ILLEGAL_IDLE_PATTERN_CHECK_SUPPORT == _ON)
    SET_DP_RX1_SOURCE_TYPE_JUDGE();
#endif

    return _SOURCE_DP;
}
//--------------------------------------------------
// Description  : DP PHY DFE Initial Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetDFEInitial(EnumDpLinkRate enumDpLinkRate)
{
    // [6] Enable Timer Control DFE Loop
    // [5:4] Reduce Gain to 1/4
    // [3] Disable Running Length Detection
    // [2] bypass Blank out Case-3 Symbol
    ScalerSetBit(P7A_A0_L0_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    ScalerSetBit(P7A_B0_L1_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    ScalerSetBit(P7A_C0_L2_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));
    ScalerSetBit(P7A_D0_L3_DFE_EN_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT6 | _BIT5));

    // [7:6] adapt_mode[1:0] = 2'b11 --> Amplitude-based Adaptation with Independent LE Loop(Loop Mode 3)
    // [5] edge_det_mode = 1 --> Edge Lag Data
    // [4] transition_only = 1 --> Only Transition Bit is Effective
    // [3] le_auto_reload = 0 --> Disable Auto-reload LE Coefficient
    // [2:0] tap1_delay[2:0] = 3'b010 --> Tap1+LE Delay 2us after Tap0
    ScalerSetByte(P7A_E0_MODE_TIMER, 0xF2);

    // Set DFE Delay Time
    ScalerSetByte(P7A_E1_TIMER, 0x01);

    // Tap0,Tap1 Loop Gain 1/512
    ScalerSetBit(P7A_E2_GAIN_1, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT2));

    // Tap2,Tap3 Loop Gain 1/512
    ScalerSetBit(P7A_E3_GAIN_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT2));

    // Tap4,Servo Loop Gain 1/512
    ScalerSetBit(P7A_E4_GAIN_3, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2), (_BIT5 | _BIT3));

    // LE Gain1 Loop Gain 1/256, LE Gain2 Loop Gain 0, LE Pre-Courser Gain 0
    ScalerSetBit(P7A_E5_GAIN_4, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1), (_BIT6 | _BIT4 | _BIT3));
    ScalerSetBit(P7A_FA_GAIN_PREC, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1));

    // Tap0 Max is 21
    ScalerSetByte(P7A_E6_LIMIT_1, 0x35);

    if(enumDpLinkRate == _DP_LINK_HBR2)
    {
        if(GET_DP_RX1_PHY_CTS_FLG() == _TRUE)
        {
            // Tap1 Min is 49
            ScalerSetBit(P7A_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT0));
        }
        else
        {
            // Tap1 Min is 46
            ScalerSetBit(P7A_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT3 | _BIT2 | _BIT1));
        }
    }
    else
    {
        // Tap1 Min is 51
        ScalerSetBit(P7A_E7_LIMIT_2, ~(_BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT5 | _BIT4 | _BIT1 | _BIT0));
    }

    // Tap2 Max is 6, Min is -6
    ScalerSetBit(P7A_E8_LIMIT_3, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT5 | _BIT4));
    ScalerSetBit(P7A_E8_LIMIT_3, ~(_BIT2 | _BIT1 | _BIT0), _BIT0);
    ScalerSetBit(P7A_E9_LIMIT_4, ~(_BIT7 | _BIT6), _BIT7);

    // Tap3 Max is 0, Min is -3
    ScalerSetBit(P7A_E9_LIMIT_4, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    ScalerSetBit(P7A_EA_LIMIT_5, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT4 | _BIT3));

    // Tap4 Max is 0, Min is -3
    ScalerSetBit(P7A_EA_LIMIT_5, ~(_BIT2 | _BIT1 | _BIT0), 0x00);
    ScalerSetBit(P7A_EB_LIMIT_6, ~(_BIT7 | _BIT6), 0x00);
    ScalerSetBit(P7A_EB_LIMIT_6, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Tap0 Threshold = 10
    ScalerSetBit(P7A_EF_RESET_1, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), (_BIT7 | _BIT5));

    if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == 0x00)
    {
        // Set Vth Max = 6, Min = 0
        ScalerSetByte(P7A_F9_LIMIT_10, 0x60);
    }
    else if(enumDpLinkRate == _DP_LINK_HBR2)
    {
        // Set Vth Max = 6, Min = 4
        ScalerSetByte(P7A_F9_LIMIT_10, 0x64);
    }
    else
    {
        // Set Vth Max = 6, Min = 2
        ScalerSetByte(P7A_F9_LIMIT_10, 0x62);
    }

    // Set Vth/Servo-loop/Tap Divider
    ScalerSetByte(P7A_EC_LOOP_DIV_1, 0xA3);

    // Tap Divider = 10 for TP2
    ScalerSetByte(P7A_ED_LOOP_DIV_2, 0xCA);

    // [1] tap1_trans = 1'b0 --> Tap1 is Effective every bit
    // [0] tap0_trans = 1'b0 --> Tap0 is Effective every bit
    ScalerSetBit(P7A_E3_GAIN_2, ~(_BIT1 | _BIT0), 0x00);

    if(enumDpLinkRate == _DP_LINK_HBR2)
    {
        // [1:0] trans_rlength = 2'b01 --> Tap0 Run Length = 3
        ScalerSetBit(P7A_E4_GAIN_3, ~(_BIT1 | _BIT0), _BIT0);
    }
    else
    {
        // [1:0] trans_rlength = 2'b00 --> Tap0 Run Length = 2
        ScalerSetBit(P7A_E4_GAIN_3, ~(_BIT1 | _BIT0), 0x00);
    }

    // [5] servo_notrans = 1'b0 --> Servo is Effective every bit
    // [4] tap0_notrans = 1'b0 --> Tap0 is Effective every bit
    ScalerSetBit(P7A_F8_GRAY_DEC_2, ~(_BIT5 | _BIT4), 0x00);


    /////////////////////////
    // DFE Code Initialize //
    /////////////////////////

    if(enumDpLinkRate == _DP_LINK_HBR2)
    {
        if((GET_DP_RX1_PHY_CTS_FLG() == _TRUE) || (ScalerDpRx1GetDpcdBitInfo(0x00, 0x02, 0x70, _BIT7) == _BIT7))
        {
            // LE Max = 18, Initial = 16, Servo Initial = 16
            ScalerSetByte(P7A_A2_L0_LIMIT_INIT, 0x20);
            ScalerSetByte(P7A_B2_L1_LIMIT_INIT, 0x20);
            ScalerSetByte(P7A_C2_L2_LIMIT_INIT, 0x20);
            ScalerSetByte(P7A_D2_L3_LIMIT_INIT, 0x20);
            ScalerSetByte(P7A_A3_L0_INIT_1, 0xD0);
            ScalerSetByte(P7A_B3_L1_INIT_1, 0xD0);
            ScalerSetByte(P7A_C3_L2_INIT_1, 0xD0);
            ScalerSetByte(P7A_D3_L3_INIT_1, 0xD0);
        }
        else
        {
            // LE Max = 20, Initial = 12, Servo Initial = 16
            ScalerSetByte(P7A_A2_L0_LIMIT_INIT, 0x4C);
            ScalerSetByte(P7A_B2_L1_LIMIT_INIT, 0x4C);
            ScalerSetByte(P7A_C2_L2_LIMIT_INIT, 0x4C);
            ScalerSetByte(P7A_D2_L3_LIMIT_INIT, 0x4C);
            ScalerSetByte(P7A_A3_L0_INIT_1, 0x90);
            ScalerSetByte(P7A_B3_L1_INIT_1, 0x90);
            ScalerSetByte(P7A_C3_L2_INIT_1, 0x90);
            ScalerSetByte(P7A_D3_L3_INIT_1, 0x90);
        }
    }
    else
    {
        // LE Max = 20, Initial = 16, Servo Initial = 16
        ScalerSetByte(P7A_A2_L0_LIMIT_INIT, 0x40);
        ScalerSetByte(P7A_B2_L1_LIMIT_INIT, 0x40);
        ScalerSetByte(P7A_C2_L2_LIMIT_INIT, 0x40);
        ScalerSetByte(P7A_D2_L3_LIMIT_INIT, 0x40);
        ScalerSetByte(P7A_A3_L0_INIT_1, 0xD0);
        ScalerSetByte(P7A_B3_L1_INIT_1, 0xD0);
        ScalerSetByte(P7A_C3_L2_INIT_1, 0xD0);
        ScalerSetByte(P7A_D3_L3_INIT_1, 0xD0);
    }

    // Tap0 Initial Value = 18
    ScalerSetByte(P7A_A4_L0_INIT_2, 0x12);
    ScalerSetByte(P7A_B4_L1_INIT_2, 0x12);
    ScalerSetByte(P7A_C4_L2_INIT_2, 0x12);
    ScalerSetByte(P7A_D4_L3_INIT_2, 0x12);

    // Tap1 Initial Value = 15
    ScalerSetByte(P7A_A5_L0_INIT_3, 0x0F);
    ScalerSetByte(P7A_B5_L1_INIT_3, 0x0F);
    ScalerSetByte(P7A_C5_L2_INIT_3, 0x0F);
    ScalerSetByte(P7A_D5_L3_INIT_3, 0x0F);

    // Tap2 Initial Value = 0
    ScalerSetByte(P7A_A6_L0_INIT_4, 0x00);
    ScalerSetByte(P7A_B6_L1_INIT_4, 0x00);
    ScalerSetByte(P7A_C6_L2_INIT_4, 0x00);
    ScalerSetByte(P7A_D6_L3_INIT_4, 0x00);

    // Vth Initial Value = 4
    ScalerSetByte(P7A_A9_L0_INIT_7, 0x04);
    ScalerSetByte(P7A_B9_L1_INIT_7, 0x04);
    ScalerSetByte(P7A_C9_L2_INIT_7, 0x04);
    ScalerSetByte(P7A_D9_L3_INIT_7, 0x04);

    // Load Intial DFE Code
    ScalerSetByte(P7A_AA_L0_INIT_8, 0xFF);
    ScalerSetByte(P7A_BA_L1_INIT_8, 0xFF);
    ScalerSetByte(P7A_CA_L2_INIT_8, 0xFF);
    ScalerSetByte(P7A_DA_L3_INIT_8, 0xFF);

    ScalerSetByte(P7A_AA_L0_INIT_8, 0x00);
    ScalerSetByte(P7A_BA_L1_INIT_8, 0x00);
    ScalerSetByte(P7A_CA_L2_INIT_8, 0x00);
    ScalerSetByte(P7A_DA_L3_INIT_8, 0x00);

    // DFE Loop Normal
    ScalerSetBit(P7A_EF_RESET_1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);
    ScalerSetBit(P7A_EF_RESET_1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Disable All Adaptation Loop
    ScalerSetByte(P7A_A1_L0_DFE_EN_2, 0x00);
    ScalerSetByte(P7A_B1_L1_DFE_EN_2, 0x00);
    ScalerSetByte(P7A_C1_L2_DFE_EN_2, 0x00);
    ScalerSetByte(P7A_D1_L3_DFE_EN_2, 0x00);
}
//--------------------------------------------------
// Description  : Enable DP Fifo Under/OverFlow IRQ
// Input Value  : _ENABLE/ DISABLE
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetFifoIRQ(bit bEn)
{
    ScalerSetBit(PB9_3A_DP_IRQ_CTRL0, ~(_BIT1 | _BIT0), ((bEn == _ENABLE) ? (_BIT1 | _BIT0) : 0x00));
}
//--------------------------------------------------
// Description  : Enable DP Fifo Under/OverFlow Watch Dog
// Input Value  : _ENABLE/ DISABLE
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetFifoWD(bit bEn)
{
    ScalerSetBit(PB9_38_DP_VWD_CTRL, ~(_BIT5 | _BIT4), ((bEn == _ENABLE) ? (_BIT5 | _BIT4) : 0x00));
}

//--------------------------------------------------
// Description  : On Line Check DP stability
// Input Value  : None
// Output Value : True --> DP Stable
//                False --> DP Unstable
//--------------------------------------------------
bit ScalerDpRx1StableDetect(void)
{
#if(_DP_POWER_MANAGEMENT_FOR_FAST_DISPLAY_RECOVER == _ON)
    if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == _BIT1)
#else
    if((ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == _BIT1) ||
       (ScalerDpRx1GetDpcdBitInfo(0x00, 0x06, 0x00, (_BIT2 | _BIT1 | _BIT0)) == (_BIT2 | _BIT0)))
#endif
    {
        DebugMessageRx1("7. DP Power Down", 0);

        return _FALSE;
    }

    if((ScalerDpRx1CDRCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _FALSE) ||
       (ScalerDpRx1AlignCheck() == _FALSE) ||
       (ScalerDpRx1DecodeCheck() == _FALSE) ||
       ((ScalerDpRx1DFECheck() == _FALSE) && (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _FALSE)))
    {
        DebugMessageRx1("7. DP Link Fail", 0);

        return _FALSE;
    }

    if(ScalerDpRx1GetVideoStream() == _FALSE)
    {
        DebugMessageRx1("7. DP Video Stream Fail", 0);

        return _FALSE;
    }

    if(ScalerDpRx1MiscCheck() == _FALSE)
    {
        DebugMessageRx1("7. DP Misc Change", 0);

        return _FALSE;
    }

    if(ScalerDpRx1FifoCheck(_DP_FIFO_POLLING_CHECK) == _FALSE)
    {
        DebugMessageRx1("7. Fifo Under/Overflow", 0);

        return _FALSE;
    }

    if(ScalerDpRx1MSAActiveChange() == _TRUE)
    {
        DebugMessageRx1("7. MSA Timing Change", 0);

        return _FALSE;
    }

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(ScalerDpRx1GetFREESYNCStatusChange() == _TRUE)
    {
        return _FALSE;
    }
#endif

    // Clear CPIRQ Flag
    ScalerDpRx1CheckHdcpCpirqStatus();

    ScalerDpRx1CrcCalculate();

    return _TRUE;
}
//--------------------------------------------------
// Description  : Dp Rx Set Valid Signal Detection Active Event
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1ValidSignalDetectionActiveEvent(void)
{
#if(_DP_MST_SUPPORT == _ON)
    ScalerTimerActiveTimerEvent(SEC(3), _SCALER_TIMER_EVENT_DP_RX1_VALID_SIGNAL_DETECT_CHECK);
#else
    ScalerTimerActiveTimerEvent(SEC(1.2), _SCALER_TIMER_EVENT_DP_RX1_VALID_SIGNAL_DETECT_CHECK);
#endif
}

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Backup Timing Info for Modern Standby
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1TimingInfoBackup(void)
{
    // Backup Offset Value of Stream Clock
    g_stDpRx1LinkInfo.lStreamClockOffset = ((((SDWORD)ScalerGetBit(PB8_BA_MN_SCLKG_SDM_SUMC_H, (_BIT3 | _BIT2 | _BIT1 | _BIT0))) << 16) |
                                            (((WORD)ScalerGetByte(PB8_BB_MN_SCLKG_SDM_SUMC_M)) << 8) |
                                            (ScalerGetByte(PB8_BC_MN_SCLKG_SDM_SUMC_L))) >> 1;

    // Backup VBs2Bs Delay of Even Field
    g_stDpRx1LinkInfo.ulVBsToBsDelayEven = (((DWORD)ScalerGetByte(PB8_32_EVBLK2VS_H)) << 16) |
                                           (((WORD)ScalerGetByte(PB8_33_EVBLK2VS_M)) << 8) |
                                           (ScalerGetByte(PB8_34_EVBLK2VS_L));

    // Backup VBs2Bs Delay of Odd Field
    g_stDpRx1LinkInfo.ulVBsToBsDelayOdd = (((DWORD)ScalerGetByte(PB8_35_OVBLK2VS_H)) << 16) |
                                          (((WORD)ScalerGetByte(PB8_36_OVBLK2VS_M)) << 8) |
                                          (ScalerGetByte(PB8_37_OVBLK2VS_L));
}
#endif


#endif // End of #if(_D1_DP_EXIST == _ON)


BYTE AwtoDpRx1LtBusy(void)                          // sync log: link training under way (status not NONE)
{
    return (GET_DP_RX1_LINK_TRAINING_STATUS() != _DP_LINK_TRAINING_NONE);
}

BYTE AwtoDpRx1Trained(void)                         // port status (#323): the last training passed
{
    return (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_NORMAL_LINK_TRAINING_PASS);
}
