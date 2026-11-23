// Parked from fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDPRx1.c (#305, #44): append to the live file to restore (scripts/sdk_park_funcs.py restore).

#if(_D1_DP_EXIST == _ON)
#if(_DP_MST_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Rx1 Mst Reset
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstReset(void)
{
    SET_DP_RX1_AUX_MANUAL_MODE();

    // Reset GUID
    for(pData[0] = 0; pData[0] < 16; pData[0]++)
    {
        ScalerDpRx1SetDpcdValue(0x00, 0x00, (0x30 + pData[0]), 0x00);
    }

    // Disable 0x111/1C2 IRQ
    ScalerSetBit(PBA_B2_AUX_SPECIAL_IRQ_EN, ~(_BIT7 | _BIT4), 0x00);

    // Clear 0x111
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0x11, 0x00);

    // Clear 0x1C0 ~ 0x1C2
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0xC0, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0xC1, 0x00);
    ScalerDpRx1SetDpcdValue(0x00, 0x01, 0xC2, 0x00);

#if(_DP_MST_AUTO_SEARCH_SUPPORT == _ON)
    if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x00, 0x21, _BIT0) == _BIT0)
    {
        // Clear 0x111 IRQ Flag
        ScalerSetBit(PBA_B3_AUX_SPECIAL_IRQ_FLAG, ~_BIT7, _BIT7);

        // Enable 0x111 IRQ
        ScalerSetBit(PBA_B2_AUX_SPECIAL_IRQ_EN, ~_BIT7, _BIT7);

        // Enable 0x01000 write IRQ
        SET_REG_DP_RX_DOWN_REQUEST_ADDR_WRITTEN_IRQ_ENABLE();
    }
#else

    // Clear 0x111/1C2 IRQ Flag
    ScalerSetBit(PBA_B3_AUX_SPECIAL_IRQ_FLAG, ~(_BIT7 | _BIT4), (_BIT7 | _BIT4));

    // Enable 0x111/1C2 IRQ
    ScalerSetBit(PBA_B2_AUX_SPECIAL_IRQ_EN, ~(_BIT7 | _BIT4), (_BIT7 | _BIT4));
#endif

    SET_DP_RX1_AUX_AUTO_MODE();

    // Disable MST
    ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT7, 0x00);

    // Disable Read 2C0 INT
    CLR_REG_DP_RX_2C0_IRQ();

    // Clear 0x2C0
    ScalerDpRx1SetDpcdValue(0x00, 0x02, 0xC0, 0x00);

    // Clear Payload ID Table (0x2C1 ~ 0x2FF)
    ScalerSetBit(PBA_B0_AUX_PAYLOAD_CLEAR, ~_BIT6, _BIT6);
    ScalerSetBit(PBA_B0_AUX_PAYLOAD_CLEAR, ~_BIT6, 0x00);

    // Reset ST1 ~ ST5
    for(pData[0] = 0; pData[0] < 5; pData[0]++)
    {
        // Reset Start Position
        ScalerSetByte(PB8_03_STHD_CTRL_2 + (pData[0] << 1), 0x00);

        // Reset End Position
        ScalerSetByte(PB8_04_STHD_CTRL_3 + (pData[0] << 1), 0x00);
    }

    // Reset Daisy Chain ST3 ~ ST5
    for(pData[0] = 0; pData[0] < 3; pData[0]++)
    {
        // Reset Start Position
        ScalerSetByte(RET_REG_ADDR_DP_RX1_DAIZY_ST3_START() + (pData[0] << 1), 0x00);

        // Reset End Position
        ScalerSetByte(RET_REG_ADDR_DP_RX1_DAIZY_ST3_END() + (pData[0] << 1), 0x00);
    }

    if((GET_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_FINISH() == 0x01) || (GET_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_FINISH() == 0x01))
    {
        SET_DP_RX1_AUX_COMMAND_NO_REPLY();
    }

    // Clr Buf0/Buf1 DownRequest MSG Finish Flag
    CLR_REG_DP_RX_DOWN_REQUEST_MSG_FINISH();

    // Clr Buf0 / Buf1
    CLR_REG_DP_RX_DOWN_REQUEST_BUF0_BUF1();

    // Clr Buf0/Buf1 MSG Error Flag
    CLR_REG_DP_RX_DOWN_REQUEST_MSG_ERROR();

    // Disable MST Related IRQ
    CLR_REG_DP_RX_DOWN_REPLY_UP_REQUEST_READY_BIT_IRQ();

    // Clr 1000h Has Been Write
    CLR_REG_DP_RX_DOWN_REQUEST_ADDR_WRITTEN();

    // Clr 1200h Has Been Write
    CLR_REG_DP_RX_UP_REPLY_ADDR_WRITTEN();

    // Disable Rx Igrone Error
    ScalerSetBit(PBA_D1_DP_IIC_SET, ~_BIT3, 0x00);

    // Message Upstream Disable
    CLR_REG_DP_RX_UPSTREAM_REPLY();

    // Reset Rx MSG Block
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT6, _BIT6);
    ScalerSetBit(PBA_C0_DPCD_CTRL, ~_BIT6, 0x00);

    if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
    {
        // Clear Flag
        CLR_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_FINISH();
        CLR_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_FINISH();

        // Clear BUF0
        CLR_REG_DP_RX_DOWN_REQUEST_BUF0();
        CLR_REG_DP_RX_DOWN_REQUEST_BUF1();

        // Enable DownRequest Buf0 / Buf1 Receive Capability
        SET_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_RECEIVE_ENABLE();
        SET_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_RECEIVE_ENABLE();

        // Clear Flag
        CLR_REG_DP_RX_UP_REPLY_BUF0_MSG_FINISH();
        CLR_REG_DP_RX_UP_REPLY_BUF1_MSG_FINISH();

        // Clear BUF0
        CLR_REG_DP_RX_UP_REPLY_BUF0();
        CLR_REG_DP_RX_UP_REPLY_BUF1();

        // Enable UpReply Buf0 / Buf1 Receive Capability
        SET_REG_DP_RX_UP_REPLY_BUF0_MSG_RECEIVE_ENABLE();
        SET_REG_DP_RX_UP_REPLY_BUF1_MSG_RECEIVE_ENABLE();
    }
}

#if(_DP_MST_AUTO_SEARCH_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Rx1 Mst Reset
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstReset_EXINT0(void)
{
    BYTE ucIndex;
    // Reset GUID
    for(ucIndex = 0; ucIndex < 16; ucIndex++)
    {
        ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x00, (0x30 + ucIndex), 0x00);
    }

    // Disable 0x111/1C2 IRQ
    ScalerSetBit_EXINT(PBA_B2_AUX_SPECIAL_IRQ_EN, ~(_BIT7 | _BIT4), 0x00);

    // Clear 0x111
    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x01, 0x11, 0x00);

    // Clear 0x1C0 ~ 0x1C2
    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x01, 0xC0, 0x00);
    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x01, 0xC1, 0x00);
    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x01, 0xC2, 0x00);

    if(ScalerDpRx1GetDpcdBitInfo_EXINT0(0x00, 0x00, 0x21, _BIT0) == _BIT0)
    {
        // Clear 0x111 IRQ Flag
        ScalerSetBit_EXINT(PBA_B3_AUX_SPECIAL_IRQ_FLAG, ~_BIT7, _BIT7);

        // Enable 0x111 IRQ
        ScalerSetBit_EXINT(PBA_B2_AUX_SPECIAL_IRQ_EN, ~_BIT7, _BIT7);

        // Enable 0x01000 write IRQ
        SET_REG_DP_RX_DOWN_REQUEST_ADDR_WRITTEN_IRQ_ENABLE_EXINT();
    }

    // Disable MST
    ScalerSetBit_EXINT(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT7, 0x00);

    // Disable Read 2C0 INT
    CLR_REG_DP_RX_2C0_IRQ_EXINT();

    // Clear 0x2C0
    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0xC0, 0x00);

    // Clear Payload ID Table (0x2C1 ~ 0x2FF)
    ScalerSetBit_EXINT(PBA_B0_AUX_PAYLOAD_CLEAR, ~_BIT6, _BIT6);
    ScalerSetBit_EXINT(PBA_B0_AUX_PAYLOAD_CLEAR, ~_BIT6, 0x00);

    // Reset ST1 ~ ST5
    for(ucIndex = 0; ucIndex < 5; ucIndex++)
    {
        // Reset Start Position
        ScalerSetByte_EXINT(PB8_03_STHD_CTRL_2 + (ucIndex << 1), 0x00);

        // Reset End Position
        ScalerSetByte_EXINT(PB8_04_STHD_CTRL_3 + (ucIndex << 1), 0x00);
    }

    // Reset Daisy Chain ST3 ~ ST5
    for(ucIndex = 0; ucIndex < 3; ucIndex++)
    {
        // Reset Start Position
        ScalerSetByte_EXINT(RET_REG_ADDR_DP_RX1_DAIZY_ST3_START() + (ucIndex << 1), 0x00);

        // Reset End Position
        ScalerSetByte_EXINT(RET_REG_ADDR_DP_RX1_DAIZY_ST3_END() + (ucIndex << 1), 0x00);
    }

    if((GET_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_FINISH_EXINT() == 0x01) || (GET_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_FINISH_EXINT() == 0x01))
    {
        SET_DP_RX1_AUX_COMMAND_NO_REPLY();
    }

    // Clr Buf0/Buf1 DownRequest MSG Finish Flag
    CLR_REG_DP_RX_DOWN_REQUEST_MSG_FINISH_EXINT();

    // Clr Buf0 / Buf1
    CLR_REG_DP_RX_DOWN_REQUEST_BUF0_BUF1_EXINT();

    // Clr Buf0/Buf1 MSG Error Flag
    CLR_REG_DP_RX_DOWN_REQUEST_MSG_ERROR_EXINT();

    // Disable MST Related IRQ
    CLR_REG_DP_RX_DOWN_REPLY_UP_REQUEST_READY_BIT_IRQ_EXINT();

    // Clr 1000h Has Been Write
    CLR_REG_DP_RX_DOWN_REQUEST_ADDR_WRITTEN_EXINT();

    // Clr 1200h Has Been Write
    CLR_REG_DP_RX_UP_REPLY_ADDR_WRITTEN_EXINT();

    // Disable Rx Igrone Error
    ScalerSetBit_EXINT(PBA_D1_DP_IIC_SET, ~_BIT3, 0x00);

    // Message Upstream Disable
    CLR_REG_DP_RX_UPSTREAM_REPLY_EXINT();

    // Reset Rx MSG Block
    ScalerSetBit_EXINT(PBA_C0_DPCD_CTRL, ~_BIT6, _BIT6);
    ScalerSetBit_EXINT(PBA_C0_DPCD_CTRL, ~_BIT6, 0x00);

    if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
    {
        // Clear Flag
        CLR_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_FINISH_EXINT();
        CLR_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_FINISH_EXINT();

        // Clear BUF0
        CLR_REG_DP_RX_DOWN_REQUEST_BUF0_EXINT();
        CLR_REG_DP_RX_DOWN_REQUEST_BUF1_EXINT();

        // Enable DownRequest Buf0 / Buf1 Receive Capability
        SET_REG_DP_RX_DOWN_REQUEST_BUF0_MSG_RECEIVE_ENABLE_EXINT();
        SET_REG_DP_RX_DOWN_REQUEST_BUF1_MSG_RECEIVE_ENABLE_EXINT();

        // Clear Flag
        CLR_REG_DP_RX_UP_REPLY_BUF0_MSG_FINISH_EXINT();
        CLR_REG_DP_RX_UP_REPLY_BUF1_MSG_FINISH_EXINT();

        // Clear BUF0
        CLR_REG_DP_RX_UP_REPLY_BUF0_EXINT();
        CLR_REG_DP_RX_UP_REPLY_BUF1_EXINT();

        // Enable UpReply Buf0 / Buf1 Receive Capability
        SET_REG_DP_RX_UP_REPLY_BUF0_MSG_RECEIVE_ENABLE_EXINT();
        SET_REG_DP_RX_UP_REPLY_BUF1_MSG_RECEIVE_ENABLE_EXINT();
    }
}
#endif

//--------------------------------------------------
// Description  : Dp Rx Aux Ch Source Power Check
// Input Value  : None
// Output Value : _ON / _OFF
//--------------------------------------------------
bit ScalerDpRx1AuxChSourcePowerCheck(void)
{
    if(PCB_GET_D1_AUX_PN_1M_PULL_H_L_SWAP() == _AUX_PN_1M_PULL_HI_LOW_SWAP_ON)
    {
        return GET_PCB_D1_DP_SOURCE_POWER_PN_SWAP();
    }
    else
    {
        return GET_PCB_D1_DP_SOURCE_POWER();
    }
}

//--------------------------------------------------
// Description  : Dp Rx Aux Ch Power Status Check
// Input Value  : bCableStatus
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1AuxChPowerStatusCheck(bit bCableStatus)
{
    BYTE ucDebounceCnt = 0;

    if(g_enumDpMSTCapablePort == _DP_MST_RX1_PORT)
    {
        if(bCableStatus == _TRUE)
        {
            if(PCB_D1_HOTPLUG_DETECT() == _D1_HOT_PLUG_HIGH)
            {
                // First time check power on with debounce to avoid AUX N always low case
                if((GET_DP_RX1_CHECK_AUX_CH_POWER_STATUS() == _DP_RX_AUX_POWER_STATUS_NONE) && (ScalerDpRx1AuxChSourcePowerCheck() == _ON))
                {
                    // Debounce for 10ms
                    for(ucDebounceCnt = 0; ucDebounceCnt < 5; ucDebounceCnt++)
                    {
                        ScalerTimerDelayXms(2);

                        if(ScalerDpRx1AuxChSourcePowerCheck() == _OFF)
                        {
                            break;
                        }
                    }

                    if(ucDebounceCnt == 5)
                    {
                        SET_DP_RX1_CHECK_AUX_CH_POWER_STATUS(_DP_RX_AUX_POWER_STATUS_ON);
                    }
                }

                // Whether to Start Debounce
                if((ScalerDpRx1AuxChSourcePowerCheck() == _OFF) &&
                   (GET_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE() == _FALSE) &&
                   (GET_DP_RX1_CHECK_AUX_CH_POWER_STATUS() == _DP_RX_AUX_POWER_STATUS_ON))
                {
                    SET_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE();

                    ScalerTimerActiveTimerEvent(200, _SCALER_TIMER_EVENT_DP_RX1_AUX_CH_NO_POWER_CHECK_DEBOUNCE);
                }

                // Debouncing
                if(GET_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE() == _TRUE)
                {
                    if(ScalerDpRx1AuxChSourcePowerCheck() == _ON)
                    {
                        CLR_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE();
                        ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_AUX_CH_NO_POWER_CHECK_DEBOUNCE);
                    }
                }

                // 1.5s HotPlug has been removed because NVIDIA GTX-1080 failed while HPD togglled at the moment of PC waked up from sleep.
                if((GET_DP_RX1_CHECK_AUX_CH_POWER_STATUS() == _DP_RX_AUX_POWER_STATUS_OFF) && (ScalerDpRx1AuxChSourcePowerCheck() == _ON))
                {
                    SET_DP_RX1_CHECK_AUX_CH_POWER_STATUS(_DP_RX_AUX_POWER_STATUS_ON);

                    SET_DP_RX1_AUX_CH_POWER_ON_WAKE_UP();

                    SET_DP_RX1_SOURCE_FIRST_POWER_ON();
                }
            }
        }
        else
        {
            CLR_DP_RX1_CHECK_AUX_CH_NO_POWER_DEBOUNCE();
            CLR_DP_RX1_CHECK_AUX_CH_POWER_STATUS();

            ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_AUX_CH_NO_POWER_CHECK_DEBOUNCE);
        }
    }
}

#if(_DP_TX_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check Dp Interlace by VBID or Measure
// Input Value  : None
// Output Value : True --> Interlace
//--------------------------------------------------
bit ScalerDpRx1MstToSstInterlaceCheck(WORD *pusVTotal, BYTE *pucOddFlg)
{
    DWORD ulLinkClk = 0;
    WORD usTempVTotal = *pusVTotal;
    WORD usHTotalCount = 0;

#if(_DP_RX_INTERLACE_NEW_MODE_SUPPORT == _OFF)
    WORD usVsyncWidth = 0;
    WORD usVstart = 0;
    WORD usVactive = 0;
#endif

#if(_DP_FREESYNC_SUPPORT == _ON)
    // Set Vfront Porch
    SET_DP_RX1_MST_TO_SST_VFRONT_PORCH(_DP_VSYNC_FRONT_PORCH);

    if(GET_DP_MST_FREESYNC_ENABLED() == _TRUE)
    {
        return _FALSE;
    }
#else
    // Set Vfront Porch
    SET_DP_RX1_MST_TO_SST_VFRONT_PORCH(_DP_VSYNC_FRONT_PORCH_MST2SST);
#endif

#if(_DP_RX_INTERLACE_NEW_MODE_SUPPORT == _ON)
    // Field inverse disable and Clr Fake Interlace Flag
    ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT5 | _BIT4 | _BIT0), (_BIT5 | _BIT0));
#else
    ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT5 | _BIT4 | _BIT0), _BIT0);
#endif

    // =========== Link Clock Measure Start ===========
    PDATA_WORD(0) = ScalerDpRx1SignalDetectMeasureCount(_D1_DP_LANE0, _DP_MEASURE_TARGET_CDR_CLOCK, _DP_MEASURE_PERIOD_2000_CYCLE);

    if(PDATA_WORD(0) == 0)
    {
        if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR3)
        {
            PDATA_WORD(0) = _DP_VCO_TARGET_COUNT_2000_HBR3;
        }
        else if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR2)
        {
            PDATA_WORD(0) = _DP_VCO_TARGET_COUNT_2000_HBR2;
        }
        else if(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) == _DP_LINK_HBR)
        {
            PDATA_WORD(0) = _DP_VCO_TARGET_COUNT_2000_HBR;
        }
        else // Both Default && _DP_LINK_RBR Case
        {
            PDATA_WORD(0) = _DP_VCO_TARGET_COUNT_2000_RBR;
        }
    }

    PDATA_DWORD(0) = (((DWORD)PDATA_WORD(0)) * _GDI_CLK_KHZ);

    // Link Clk in KHz
    ulLinkClk = (PDATA_DWORD(0) / 1000);

    DebugMessageRx1("MST Current Link Clk", ulLinkClk);
    // =========== Link Clock Measure End ===========

    // =========== Continue Measure Two Frame Start ===========
    // Start to Measure Vertical BS to BS Counter by GDI Clock
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, 0x00);
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, _BIT7);

    if(ScalerTimerPollingFlagProc(_DP_MEASURE_POLLING_TIMEOUT, PA_58_MN_MEAS_CTRL, _BIT6, _TRUE) == _FALSE)
    {
        return _FALSE;
    }

    // Pop up The result
    SET_DP_RX1_MEASURE_POP_UP_MST2SST();

    // Get Measure Result
    ScalerRead(PA_58_MN_MEAS_CTRL, 3, &pData[5], _AUTOINC);

    // Delay 2ms To Get VBID
    ScalerTimerDelayXms(2);

    // Get VBID
    ScalerRead(PA_29_MST2SST_VBID, 1, &pData[1], _NON_AUTOINC);

    // Delay 1 frame
    ScalerTimerDelayXms((((PDATA_DWORD(1) & 0x001FFFFF) / (_GDI_CLK_KHZ)) + 2));

    // Pop up Measure Result
    SET_DP_RX1_MEASURE_POP_UP_MST2SST();

    // Get Measure Result
    ScalerRead(PA_58_MN_MEAS_CTRL, 3, &pData[9], _AUTOINC);

    // Get Measure Htotal Counts
    ScalerRead(PA_5B_MN_MEAS_HLN_M, 2, &pData[12], _AUTOINC);

    // Get VBID
    ScalerRead(PA_29_MST2SST_VBID, 1, &pData[2], _NON_AUTOINC);

    PDATA_DWORD(1) = (PDATA_DWORD(1) & 0x001FFFFF);
    PDATA_DWORD(2) = (PDATA_DWORD(2) & 0x001FFFFF);

    // Disable Measure Block
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, 0x00);
    // =========== Continue Measure Two Frame End ===========

    // Convert HTotal Count from 1/2 Link Clk to GDI Clk
    usHTotalCount = ((DWORD)PDATA_WORD(6) * _GDI_CLK_KHZ * 2 + (ulLinkClk >> 1)) / ulLinkClk;

    DebugMessageRx1("MST HTotal Count", usHTotalCount);

    // if VTotal Difference > 1/2 HTotal
    if((ABSDWORD(PDATA_DWORD(1), PDATA_DWORD(2))) > (usHTotalCount / 2))
    {
        if(PDATA_DWORD(1) < PDATA_DWORD(2))
        {
            usTempVTotal = ((PDATA_DWORD(1) + (usHTotalCount >> 1)) / usHTotalCount);
        }
        else
        {
            usTempVTotal = ((PDATA_DWORD(2) + (usHTotalCount >> 1)) / usHTotalCount);
        }

        *pucOddFlg = _TRUE;
    }
    else
    {
        *pucOddFlg = _FALSE;
    }

    DebugMessageRx1("MST ####Calculated usVTotal####", usTempVTotal);

    DebugMessageRx1("7.MST DelayTime", (((PDATA_DWORD(1) & 0x000FFFFF) / (_GDI_CLK_KHZ)) + 2));
    DebugMessageRx1("7.MST Frame[N] VBS2BS Counter", PDATA_DWORD(1));
    DebugMessageRx1("7.MST Frame[N + 1] VBS2BS Counter", PDATA_DWORD(2));
    DebugMessageRx1("7.MST Frame diff ABS", (ABSDWORD(PDATA_DWORD(1), PDATA_DWORD(2))));

#if(_DP_RX_INTERLACE_NEW_MODE_SUPPORT == _ON)
    // Check N and N+1 Frame Vs2Vs Count
    if((*pucOddFlg) == _TRUE)
    {
        // Enable DP Interlace
        ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT5 | _BIT0), _BIT7);

        // Enable Field Sync by BE
        ScalerSetBit(PA_F1_DP_RSV1, ~_BIT0, _BIT0);

        // HW Check Interlace
        if(ScalerGetBit(PA_56_INTERLACE_MODE_CONFIG, _BIT5) == _BIT5)
        {
            // Field reference HW
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT6 | _BIT5 | _BIT0), _BIT6);
        }
        else
        {
            // Field reference VBID
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT6 | _BIT5 | _BIT0), 0x00);
        }

        // Set Vtt odd fw mode
        SET_DP_RX1_INTERLACE_VTT_FW_MODE_MST2SST(_ODD);

        *pusVTotal = usTempVTotal;

        return _TRUE;
    }
    else
    {
        // Check VBID Field Toggle and VBID Interlace Info
        if(((pData[1] & _BIT1) != (pData[2] & _BIT1)) && (ScalerGetBit(PA_29_MST2SST_VBID, _BIT2) == _BIT2))
        {
            // Enable DP Interlace
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT5 | _BIT0), _BIT7);

            // Field reference VBID
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT6 | _BIT5 | _BIT0), 0x00);

            // Enable Field Sync by BE
            ScalerSetBit(PA_F1_DP_RSV1, ~_BIT0, _BIT0);

            // Set Vtt Even fw mode
            SET_DP_RX1_INTERLACE_VTT_FW_MODE_MST2SST(_EVEN);

            *pusVTotal = usTempVTotal;

            return _TRUE;
        }

        // Enable DP Progressive Mode
        ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT5 | _BIT0), 0x00);

        // Field reference VBID
        ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT6 | _BIT5 | _BIT0), 0x00);

        // Enable Field Sync by VBID
        ScalerSetBit(PA_F1_DP_RSV1, ~_BIT0, 0x00);

        // Set Vtt Even fw mode
        SET_DP_RX1_INTERLACE_VTT_FW_MODE_MST2SST(_EVEN);

        return _FALSE;
    }
#else
    if(ScalerGetBit(PA_29_MST2SST_VBID, _BIT2) == _BIT2) // Interlace
    {
        // Enable DP Interlace
        ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT5 | _BIT0), _BIT7);

        if((*pucOddFlg) == _FALSE)
        {
            // Disable DP Interlace
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT5 | _BIT0), 0x00);
        }

        // Get VSW
        usVsyncWidth = ((WORD)ScalerGetByte(PA_1E_MSA_VSW_0) << 8) | ScalerGetByte(PA_1F_MSA_VSW_1);
        usVsyncWidth &= 0x7FFF;

        // Get VStart
        usVstart = ((WORD)ScalerGetByte(PA_1A_MSA_VST_0) << 8) | ScalerGetByte(PA_1B_MSA_VST_1);

        // usVbackporch = usVstart - Fixed V-Sync Pulse Width, usVbackporch > usVsyncWidth + 2 lines, here 2 lines is for V-Sync Falling edge to DEN Rising Edge distance margion
        if(((pData[1] & _BIT1) != (pData[2] & _BIT1)) && (usVstart > (usVsyncWidth + _DP_VSYNC_WIDTH + 2)))
        {
            // Field Information reference to VBID
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~_BIT6, 0x00);

            // Get Vactive
            usVactive = ((WORD)ScalerGetByte(PA_1C_MSA_VHT_0) << 8) | ScalerGetByte(PA_1D_MSA_VHT_1);

            // Set Front Porch = VTotal - Active height - MSA V Start + V Sync Pulse Width
            SET_DP_RX1_MST_TO_SST_VFRONT_PORCH(usTempVTotal - usVactive - usVstart + usVsyncWidth);

            if((ScalerGetBit(PA_56_INTERLACE_MODE_CONFIG, _BIT0) == 0x00) &&
               ((((pData[1] & _BIT1) == _BIT1) && ((pData[2] & _BIT1) == 0x00) && (PDATA_DWORD(1) < PDATA_DWORD(2))) ||
                (((pData[1] & _BIT1) == 0x00) && ((pData[2] & _BIT1) == _BIT1) && (PDATA_DWORD(1) > PDATA_DWORD(2)))))
            {
                // Field inverse enable
                ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT5 | _BIT4 | _BIT0), _BIT4);
            }
        }
        else
        {
            // Field reference HW
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT6 | _BIT5 | _BIT0), _BIT6);
        }

        *pusVTotal = usTempVTotal;

        return _TRUE;
    }
    else if((ABSDWORD(PDATA_DWORD(1), PDATA_DWORD(2))) > (usHTotalCount / 2))
    {
        // Delay a Complete Frame
        ScalerTimerDelayXms(_DP_TWO_FRAME_TIME_MAX);

        if(ScalerGetBit(PA_56_INTERLACE_MODE_CONFIG, _BIT0) == _BIT0)
        {
            DebugMessageRx1("MST Fake Interlace", 0);
            *pucOddFlg = _FALSE;
        }
        else
        {
            // Enable interlace mode, field reference HW
            ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT6 | _BIT5 | _BIT0), (_BIT7 | _BIT6));

            *pusVTotal = usTempVTotal;

            return _TRUE;
        }
    }

    // Disable DP Interlace
    ScalerSetBit(PA_56_INTERLACE_MODE_CONFIG, ~(_BIT7 | _BIT6 | _BIT5 | _BIT0), 0x00);

    return _FALSE;
#endif
}

#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)

#if(_HW_DP_VSC_SDP_REG_SUPPORT != _ON)
//--------------------------------------------------
// Description  : DP Rx1 MstToSst VSC Packet Detect Event
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstToSstRSV1PacketDetectEvent(void)
{
    CLR_DP_RX1_MST2SST_RSV1_DETECTING();
}
#endif // End of #if(_HW_DP_VSC_SDP_REG_SUPPORT != _ON)
#endif // End of #if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)
#endif // End of #if(_DP_TX_SUPPORT == _ON)
#endif // End of #if(_DP_MST_SUPPORT == _ON)
#endif

#if(_D1_DP_EXIST == _ON)
#if(_DP_HDCP_2_2_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Dp IRQ Assert Proc
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HpdIrqAssert_EXINT0(void)
{
    if(PCB_D1_HOTPLUG_DETECT() == _D1_HOT_PLUG_HIGH)
    {
#if(_DP_IRQ_HPD_MODE == _DP_IRQ_HPD_T2_MODE)
        SET_DP_D1_HPD_IRQ_ASSERT_T2_EVENT();
#else

        BYTE ucBackUp2 = ScalerGetByte_EXINT(PBA_D0_AUX_MODE_SET);

#if(_DP_TX_SUPPORT == _ON)
        // Disable IRQs that take too long
        BYTE ucBackUp1 = ScalerGetBit_EXINT(PBB_72_HPD_IRQ_EN, _BIT6);
        ScalerSetBit_EXINT(PBB_72_HPD_IRQ_EN, ~_BIT6, 0x00);
#endif

        SET_DP_RX1_AUX_MANUAL_MODE_EXINT();

        PCB_D1_HOTPLUG(_D1_HOT_PLUG_LOW);

        // Default = 750us
        switch(GET_DP_IRQ_TIME_10US())
        {
            case 55:
                DELAY_XUS_EXINT(500);
                break;

            case 60:
                DELAY_XUS_EXINT(546);
                break;

            case 65:
                DELAY_XUS_EXINT(588);
                break;

            case 70:
                DELAY_XUS_EXINT(634);
                break;

            case 75:
                DELAY_XUS_EXINT(682);
                break;

            case 80:
                DELAY_XUS_EXINT(728);
                break;

            case 85:
                DELAY_XUS_EXINT(768);
                break;

            case 90:
                DELAY_XUS_EXINT(816);
                break;

            case 95:
                DELAY_XUS_EXINT(862);
                break;

            default:
                DELAY_XUS_EXINT(682);
                break;
        }

        PCB_D1_HOTPLUG(_D1_HOT_PLUG_HIGH);

        if((ucBackUp2 & _BIT1) == _BIT1)
        {
            SET_DP_RX1_AUX_AUTO_MODE_EXINT();
        }

#if(_DP_TX_SUPPORT == _ON)
        ScalerSetBit_EXINT(PBB_72_HPD_IRQ_EN, ~_BIT6, ucBackUp1);
#endif
#endif
    }
}
#endif
#endif
