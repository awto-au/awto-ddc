// Parked from fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c (#305, #44): append to the live file to restore (scripts/sdk_park_funcs.py restore).

#if(_D1_DP_EXIST == _ON)
#if(_DP_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check FREESYNC Enable
// Input Value  : None
// Output Value : _TRUE: FREESYNC change
//--------------------------------------------------
bit ScalerDpRx1GetFREESYNCStatusChange(void)
{
    if((GET_FREESYNC_ENABLED() == _TRUE) && ((g_stInputTimingData.usVFreq < (_PANEL_FREESYNC_MIN_FRAME_RATE - _FRAME_SYNC_MARGIN)) || (g_stInputTimingData.usVFreq > (_PANEL_FREESYNC_MAX_FRAME_RATE + _FRAME_SYNC_MARGIN))))
    {
        DebugMessageRx1("7.FREESYNC IVF out of panel range", g_stInputTimingData.usVFreq);
        return _TRUE;
    }

    if((bit)(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x07) & _BIT7) != GET_FREESYNC_ENABLED())
    {
        DebugMessageRx1("7.FREESYNC ignore MSA 0 -> 1", 0);
        return _TRUE;
    }

    return _FALSE;
}

//--------------------------------------------------
// Description  : Set DP Freesync Htotal info
// Input Value  : Dp Timing Info
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1SetFREESYNCMsaForLut(WORD usDpHtotal)
{
    WORD usTempMeasureHtotal = usDpHtotal;
    WORD usTempMsaHtotal = ((((WORD)ScalerGetByte(PB9_08_MSA_HTT_0)) << 8) | ((WORD)ScalerGetByte(PB9_09_MSA_HTT_1)));
    WORD usTempMsaHtotalMargin = ((DWORD)usTempMeasureHtotal * _DP_FREESYNC_HTOTAL_MARGIN / 100);

    if((usTempMsaHtotal > (usTempMeasureHtotal + usTempMsaHtotalMargin)) || (usTempMsaHtotal < (usTempMeasureHtotal - usTempMsaHtotalMargin)))
    {
        SET_DP_RX1_HTOTAL(usTempMeasureHtotal);

        SET_DP_RX1_HTOTAL_MARGIN(usTempMsaHtotalMargin);

        DebugMessageRx1("7. DP Freesync Get MSA Htotal Fail", usTempMsaHtotal);
    }
    else
    {
        SET_DP_RX1_HTOTAL(usTempMsaHtotal);

        SET_DP_RX1_HTOTAL_MARGIN(1);
    }
}
#endif
#endif

#if(_D1_DP_EXIST == _ON)
#if(_DP_MST_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Backup MST Info
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstInfoBackup(EnumDpMstBackup enumDpMstBackup)
{
    EnumDpStreamSourceNum enumSourceNum = _DP_ST_SOURCE1;

    switch(enumDpMstBackup)
    {
        case _DP_MST_BACKUP_INFO:

            if((ScalerGetBit(PB0_01_PHY_DIG_RESET_CTRL, _BIT7) == _BIT7) &&
               (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_FAKE_LINK_TRAINING_PASS))
            {
                // Backup MST Enable
                g_stDpRx1MiscInfo.b1DpMstEnableBackup = _TRUE;

                // Backup Link Config
                g_stDpRx1MiscInfo.ucDpRxLinkRateBackup = ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00);
                g_stDpRx1MiscInfo.ucDpRxLaneCountBackup = (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F);

                // Backup TimeSlot Info
                memcpy(g_pucDpRx1MstTimeSlotBackup, (volatile BYTE xdata *)PB8_03_STHD_CTRL_2, sizeof(g_pucDpRx1MstTimeSlotBackup));

                for(enumSourceNum = _DP_ST_SOURCE1; enumSourceNum <= _DP_ST_SOURCE5; enumSourceNum++)
                {
                    g_pucDpMacRx1MstStMuxBackup[enumSourceNum] = GET_DP_RX_MST_ST_SOURCE_BACKUP(enumSourceNum);
                }
            }

            break;

        case _DP_MST_BACKUP_INFO_RESTORE:

            if(((ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x21) & _BIT0) == _BIT0) && (g_stDpRx1MiscInfo.b1DpMstEnableBackup == _TRUE))
            {
                // Enable MST Decode
                ScalerSetBit(PB0_01_PHY_DIG_RESET_CTRL, ~_BIT7, _BIT7);

                // Restore TimeSlot Info
                memcpy((volatile BYTE xdata *)PB8_03_STHD_CTRL_2, g_pucDpRx1MstTimeSlotBackup, sizeof(g_pucDpRx1MstTimeSlotBackup));

                for(enumSourceNum = _DP_ST_SOURCE1; enumSourceNum <= _DP_ST_SOURCE5; enumSourceNum++)
                {
                    ScalerDpRxMstStreamMuxBackup(enumSourceNum, g_pucDpMacRx1MstStMuxBackup[enumSourceNum]);
                }
            }
            g_stDpRx1MiscInfo.b1DpMstEnableBackup = _FALSE;

            break;

        case _DP_MST_BACKUP_INFO_RESET:
        default:

            g_stDpRx1MiscInfo.b1DpMstEnableBackup = _FALSE;

            break;
    }
}

#if(_DP_TX_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Dp Rx HDCP - SHA circuit Run
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPAuthShaRun(bit bIsFirst)
{
    // Set First Run For SHA-1 Circuit
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT1, ((bIsFirst == _TRUE) ? _BIT1 : 0x00));

    // Run SHA-1 Circuit
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT2, _BIT2);

    ScalerTimerPollingFlagProc(5, PB0_30_SHA_CONTRL, _BIT4, _TRUE);

    // Disable First Run and Disable SHA-1 Circuit
    ScalerSetBit(PB0_30_SHA_CONTRL, ~(_BIT2 | _BIT1), 0x00);
}

//--------------------------------------------------
// Description  : Change HDCP Auth State
// Input Value  : Target HDCP Auth State
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPChangeAuthState(EnumDPRxHDCPAuthState enumHDCPAuthState)
{
    SET_DP_RX1_HDCP_AUTH_STATE(enumHDCPAuthState);
    SET_DP_RX1_HDCP_AUTH_STATE_CHANGE();
}
//--------------------------------------------------
// Description  : Check B info
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1HDCPCheckBinfo(void)
{
    BYTE ucBInfoDevice = 0;
    BYTE ucBInfoDepth = 0;
    bit bBInfoDeviceExceed = _FALSE;
    bit bBInfoDepthExceed = _FALSE;

#if(_DP_HDCP_2_2_SUPPORT == _ON)
    if(GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE)
    {
        if(GET_DP_TX_HDCP2_REPEATER_SUPPORTED() == _TRUE)
        {
            if((GET_DP_TX_HDCP2_RXINFO_DEVICE_COUNT_EXCEED() == _TRUE) ||
               (GET_DP_TX_HDCP2_RXINFO_DEPTH_EXCEED() == _TRUE))
            {
                bBInfoDeviceExceed = (GET_DP_TX_HDCP2_RXINFO_DEVICE_COUNT_EXCEED() == _TRUE) ? _TRUE : _FALSE;
                bBInfoDepthExceed = (GET_DP_TX_HDCP2_RXINFO_DEPTH_EXCEED() == _TRUE) ? _TRUE : _FALSE;
            }
            else
            {
                ucBInfoDevice = GET_DP_TX_HDCP2_RXINFO_DEVICE_COUNT();
                ucBInfoDepth = GET_DP_TX_HDCP2_RXINFO_DEPTH();

                if(ucBInfoDevice > 125)
                {
                    ucBInfoDevice = 0x00;
                    bBInfoDeviceExceed = _TRUE;
                }

                if(ucBInfoDepth > 6)
                {
                    ucBInfoDepth = 0x00;
                    bBInfoDepthExceed = _TRUE;
                }
            }
        }

        if(bBInfoDeviceExceed == _FALSE)
        {
            ucBInfoDevice++;
        }
    }
    else if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#else
    if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#endif
    {
        if(GET_DP_TX_HDCP_DOWNSTREAM_REPEATER() == _TRUE)
        {
            if((GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT_MAX() == _TRUE) ||
               (GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT() > _DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT_EXCEED))
            {
                bBInfoDeviceExceed = _TRUE;
            }
            else
            {
                ucBInfoDevice = GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT();
            }

            if((GET_DP_TX_HDCP_DOWNSTREAM_DEPTH_MAX() == _TRUE) || (GET_DP_TX_HDCP_DOWNSTREAM_DEPTH() > 6))
            {
                bBInfoDepthExceed = _TRUE;
            }
            else
            {
                ucBInfoDepth = GET_DP_TX_HDCP_DOWNSTREAM_DEPTH();
            }
        }

        if(bBInfoDeviceExceed == _FALSE)
        {
            ucBInfoDevice++;
        }
    }

    if(bBInfoDeviceExceed == _FALSE)
    {
#if(_DP_HDCP14_CTS_SUPPORT == _ON)
        if(ucBInfoDevice == 0x00)
        {
            ucBInfoDevice = 0x01;
        }
#else
        ucBInfoDevice++;
#endif
    }
    else
    {
        ucBInfoDevice = 0x80;
    }

    if(bBInfoDepthExceed == _FALSE)
    {
        ucBInfoDepth++;
    }
    else
    {
        ucBInfoDepth = 0x08;
    }

    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2A, ucBInfoDevice);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2B, ucBInfoDepth);

    if((ucBInfoDevice == 0x80) || (ucBInfoDepth == 0x08))
    {
        return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : Check Dp Rx HDCP Link Veriffication Pattern (0x531F) for MST Mode
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1HDCPCheckLvp(void)
{
    if(((ScalerGetByte(PB0_1E_HDCP_INTGT_VRF_ANS_MSB) == 0x53) || (ScalerGetByte(PB0_1E_HDCP_INTGT_VRF_ANS_MSB) == 0x00)) &&
       ((ScalerGetByte(PB0_1F_HDCP_INTGT_VRF_ANS_LSB) == 0x1F) || (ScalerGetByte(PB0_1F_HDCP_INTGT_VRF_ANS_LSB) == 0x00)))
    {
        return _TRUE;
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Fake HDCP Authentication
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPFakeAuthenProc(void)
{
    BYTE pucSHAInput[64];

    // Set Device Count and Depth
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2A, 0x01);
    ScalerDpRx1SetDpcdValue(0x06, 0x80, 0x2B, 0x01);

    // Load KSV
    memcpy(pucSHAInput, g_pucHdcpAksvBackup, 5);

    // Load Device Count and Depth
    pucSHAInput[5] = ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A);
    pucSHAInput[6] = ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B);

    // Load M0'
    for(pData[0] = 0; pData[0] < 8; pData[0]++)
    {
        pucSHAInput[7 + pData[0]] = ScalerGetByteVar(PB0_2F_M0_BYTE_0 - pData[0]);
    }

    memset(&pucSHAInput[15], 0, 49);

    pucSHAInput[15] = 0x80;

    // Total bit numbers of SHA-1 input = KSV FIFO + B_info + M0'
    pucSHAInput[63] = 0x78;

    // Compute V'
    ScalerDpRx1HDCPSha1Calculate(pucSHAInput, 0);

    // Write Ksv to DPCD table
    SET_DP_RX1_AUX_MANUAL_MODE();

    for(pData[0] = 0; pData[0] < 15; pData[0]++)
    {
        if(pData[0] < 5)
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x2C + pData[0]), g_pucHdcpAksvBackup[pData[0]]);
        }
        else
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x2C + pData[0]), 0x00);
        }
    }

    SET_DP_RX1_AUX_AUTO_MODE();

    // Write V' to DPCD table
    ScalerDpRx1HDCPLoadShaToDpcd();
}
//--------------------------------------------------
// Description  : Dp Rx HDCP Auth Handler
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPHandler(void)
{
#if(_DP_HDCP_2_2_SUPPORT == _ON)
    if((GET_DP_RX1_HDCP2_MODE() == _DISABLE) && (GET_DP_RX1_HDCP_REPEATER_SUPPORT() == _TRUE))
#else
    if(GET_DP_RX1_HDCP_REPEATER_SUPPORT() == _TRUE)
#endif
    {
        // After receiving AKSV, handler must initialize authentication
        if(GET_DP_RX1_HDCP_AUTH_AKSV_WRITTEN() == _TRUE)
        {
            CLR_DP_RX1_HDCP_AUTH_AKSV_WRITTEN();
            CLR_DP_RX1_HDCP_AUTH_CPIRQ_TIMRE();

            ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_IDLE);

            ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_CPIRQ_EVENT);
        }

        if(GET_DP_RX_HDCP_UPSTREAM_PORT() == _HDCP_D1_PORT)
        {
            // In MST mode
            if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x11) & _BIT0) == _BIT0)
            {
                if((ScalerDpRx1HdcpCheckValid() == _TRUE) && (GET_DP_RX1_HDCP_AUTH_CPIRQ_TIMRE() == _FALSE))
                {
                    if(ScalerDpRx1HDCPCheckLvp() == _FALSE)
                    {
                        SET_DP_RX1_HDCP_AUTH_CPIRQ_TIMRE();

                        ScalerDpRx1CpIRQ(_DP_HDCP_BSTATUS_LINK_INTEGRITY_FAIL);

                        ScalerTimerActiveTimerEvent(SEC(0.02), _SCALER_TIMER_EVENT_DP_RX1_HDCP_CPIRQ_EVENT);
                    }
                }
            }
            else
            {
                // In SST mode, issue HPD event for upstream device if DPTX connect a new downstream device.
                if((GET_DP_RX1_HDCP_AUTH_STATE() != _DP_RX_HDCP_STATE_IDLE) &&
                   (ScalerDpRx1HdcpCheckValid() == _TRUE) &&
                   (ScalerDpRx1HDCPCheckLvp() == _TRUE))
                {
#if(_DP_HDCP_2_2_SUPPORT == _ON)
                    if((GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE) && (GET_DP_TX_HDCP2_VERSION_SUPPORTED() == _TRUE))
                    {
                        if(GET_DP_TX_HDCP2_DOWNSTREAM_EVENT() == _DP_TX_HDCP2_DOWNSTREAM_AUTH_EVENT_REAUTH)
                        {
                            ScalerDpRx1SetHotPlugEvent(_DP_HDCP_LONG_HPD_EVENT);
                        }
                    }
                    else if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#else
                    if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#endif
                    {
                        if(GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_REAUTH)
                        {
                            ScalerDpRx1SetHotPlugEvent(_DP_HDCP_LONG_HPD_EVENT);
                        }
                    }
                }
            }
        }

        if((GET_DP_RX1_HDCP_AUTH_STATE() != _DP_RX_HDCP_STATE_IDLE) && (GET_DP_RX1_LINK_TRAINING_STATUS() == _DP_LINK_TRAINING_NONE))
        {
            ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_IDLE);
        }

#if(_DP_HDCP_2_2_SUPPORT == _ON)
        if((GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE) && (GET_DP_TX_HDCP2_VERSION_SUPPORTED() == _TRUE))
        {
            if((ScalerDpRx1HdcpCheckValid() == _TRUE) &&
               (GET_DP_RX1_HDCP_AUTH_STATE() >= _DP_RX_HDCP_STATE_AUTH_2) &&
               (GET_DP_TX_HDCP2_MODE() == _TRUE))
            {
                SET_DP_RX1_HDCP2_HDCP1_CONTENT_STREAM_MANAGEMENT();
            }
        }
#endif
    }

    switch(GET_DP_RX1_HDCP_AUTH_STATE())
    {
        case _DP_RX_HDCP_STATE_IDLE:

            if(GET_DP_RX1_HDCP_AUTH_STATE_CHANGE() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_STATE_CHANGE();
                CLR_DP_RX1_HDCP_AUTH_REPEATER_PROC_TIMEOUT();
                CLR_DP_RX1_HDCP_AUTH_CPIRQ_TIMRE();

#if(_DP_HDCP_2_2_SUPPORT == _ON)
                CLR_DP_RX1_HDCP2_HDCP1_CONTENT_STREAM_MANAGEMENT();
#endif

                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_REPEATER_PROC_TIMEOUT);
                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_READ_IRQ_TIMEOUT);
                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_CPIRQ_EVENT);

                ScalerDpRx1HDCPEnableReadIrq(_DISABLE);

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
                ScalerDpTxHDCPResetKsvBackup();
#endif

                SET_DP_RX1_HDCP_UPSTREAM_EVENT(_DP_RX_HDCP_UPSTREAM_AUTH_EVENT_STOP_ENCRYPTION);
            }

#if(_DP_HDCP_2_2_SUPPORT == _ON)
            if((GET_DP_RX1_HDCP2_MODE() == _DISABLE) && (GET_DP_RX1_HDCP_REPEATER_SUPPORT() == _TRUE))
#else
            if(GET_DP_RX1_HDCP_REPEATER_SUPPORT() == _TRUE)
#endif
            {
                // Check if R0' was read already by upstream device.
                if((ScalerGetBit(PB0_20_HDCP_DEBUG, (_BIT7 | _BIT5)) == (_BIT7 | _BIT5)) &&
                   ((ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x05) != 0x00) || (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x06) != 0x00)) &&
                   ((ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x29) & _DP_HDCP_BSTATUS_R0_AVAILABLE) == 0x00) &&
                   ((ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x07) != 0x00) ||
                    (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x08) != 0x00) ||
                    (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x09) != 0x00) ||
                    (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0A) != 0x00) ||
                    (ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x0B) != 0x00)))
                {
                    ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_1);
                }
            }

            break;

        case _DP_RX_HDCP_STATE_AUTH_1:

            if(GET_DP_RX1_HDCP_AUTH_STATE_CHANGE() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_STATE_CHANGE();

                if(GET_DP_RX_HDCP_UPSTREAM_PORT() == _HDCP_D1_PORT)
                {
                    // Check if downstream device support HDCP capability.
#if(_DP_HDCP_2_2_SUPPORT == _ON)
                    if((GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE) && (GET_DP_TX_HDCP2_VERSION_SUPPORTED() == _TRUE))
                    {
                        // Issue event to make DPTX start HDCP2 handshake.
                        SET_DP_RX1_HDCP2_UPSTREAM_EVENT(_DP_RX_HDCP2_UPSTREAM_AUTH_EVENT_START_HANDSHAKE);

                        ScalerTimerActiveTimerEvent(SEC(6), _SCALER_TIMER_EVENT_DP_RX1_HDCP_REPEATER_PROC_TIMEOUT);
                    }
                    else if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#else
                    if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#endif
                    {
                        // Issue event to make DPTX start HDCP handshake.
                        SET_DP_RX1_HDCP_UPSTREAM_EVENT(_DP_RX_HDCP_UPSTREAM_AUTH_EVENT_R0_PASS);

                        ScalerTimerActiveTimerEvent(SEC(6), _SCALER_TIMER_EVENT_DP_RX1_HDCP_REPEATER_PROC_TIMEOUT);
                    }
                    else
                    {
                        ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_2);
                    }
                }
                else
                {
                    ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_FAKE);
                }
            }

            // Wait for downstream pass event or device/depth max event
#if(_DP_HDCP_2_2_SUPPORT == _ON)
            if((GET_DP_TX_HDCP2_DOWNSTREAM_EVENT() == _DP_TX_HDCP2_DOWNSTREAM_AUTH_EVENT_PASS) ||
               (GET_DP_TX_HDCP2_DOWNSTREAM_EVENT() == _DP_TX_HDCP2_DOWNSTREAM_AUTH_EVENT_DEVICE_DEPTH_EXCEED) ||
               (GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_PASS) ||
               (GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_DEVICE_DEPTH_MAX))
#else
            if((GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_PASS) ||
               (GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_DEVICE_DEPTH_MAX))
#endif
            {
                ScalerTimerCancelTimerEvent(_SCALER_TIMER_EVENT_DP_RX1_HDCP_REPEATER_PROC_TIMEOUT);

                ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_2);
            }
            else if(GET_DP_RX1_HDCP_AUTH_REPEATER_PROC_TIMEOUT() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_REPEATER_PROC_TIMEOUT();

#if(_DP_HDCP_2_2_SUPPORT == _ON)
                if((GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE) && (GET_DP_TX_HDCP2_VERSION_SUPPORTED() == _TRUE))
                {
                    SET_DP_RX1_HDCP2_UPSTREAM_EVENT(_DP_RX_HDCP2_UPSTREAM_AUTH_EVENT_TIMEOUT);
                }
                else if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#else
                if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#endif
                {
                    SET_DP_RX1_HDCP_UPSTREAM_EVENT(_DP_RX_HDCP_UPSTREAM_AUTH_EVENT_TIMEOUT);
                }

                ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_DONE);
            }

            break;

        case _DP_RX_HDCP_STATE_AUTH_2:

            if(GET_DP_RX1_HDCP_AUTH_STATE_CHANGE() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_STATE_CHANGE();
            }

            if(ScalerDpRx1HDCPCheckBinfo() == _TRUE)
            {
                // Load KSV List to RX KSV FIFO
                ScalerDpRx1HDCPLoadKsvFifo();

                // Input KSV FIFO to SHA-1 and Compute V'
                ScalerDpRx1HDCPWriteShaInput();

                // Write V' into DPCD table
                ScalerDpRx1HDCPLoadShaToDpcd();

                // Set 1st KSV FIFO to DPCD table
                ScalerDpRx1HDCPSetKsvFifoFirst();

                // Enable 68xxx Read INT
                ScalerDpRx1HDCPEnableReadIrq(_ENABLE);

                ScalerTimerActiveTimerEvent(SEC(5), _SCALER_TIMER_EVENT_DP_RX1_HDCP_READ_IRQ_TIMEOUT);
            }

            // Set V' Ready Bit and Issue CP_IRQ
            ScalerDpRx1CpIRQ(_DP_HDCP_BSTATUS_V_READY);

            ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_DONE);

            break;

        case _DP_RX_HDCP_STATE_AUTH_FAKE:

            if(GET_DP_RX1_HDCP_AUTH_STATE_CHANGE() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_STATE_CHANGE();
            }

            // Enable 68xxx Read INT
            ScalerDpRx1HDCPEnableReadIrq(_DISABLE);

            // Fake Authentication
            ScalerDpRx1HDCPFakeAuthenProc();

            // Set V' Ready Bit and Issue CP_IRQ
            ScalerDpRx1CpIRQ(_DP_HDCP_BSTATUS_V_READY);

            ScalerDpRx1HDCPChangeAuthState(_DP_RX_HDCP_STATE_AUTH_DONE);

            break;

        case _DP_RX_HDCP_STATE_AUTH_DONE:

            if(GET_DP_RX1_HDCP_AUTH_STATE_CHANGE() == _TRUE)
            {
                CLR_DP_RX1_HDCP_AUTH_STATE_CHANGE();
            }

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
            if(GET_DP_TX_HDCP_DOWNSTREAM_EVENT() == _DP_TX_HDCP_DOWNSTREAM_AUTH_EVENT_PASS)
            {
                // In SST mode
                if((ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x11) & _BIT0) == 0x00)
                {
                    if((ScalerDpRx1HDCPDeviceCountChange() == _TRUE) &&
                       (ScalerDpRx1HdcpCheckValid() == _TRUE) &&
                       (ScalerDpRx1HDCPCheckLvp() == _TRUE))
                    {
                        ScalerDpRx1SetHotPlugEvent(_DP_HDCP_LONG_HPD_EVENT);
                    }
                }
            }
#endif

            if(GET_DP_RX1_HDCP_AUTH_READ_IRQ_TIMEOUT() == _TRUE)
            {
                ScalerDpRx1HDCPEnableReadIrq(_DISABLE);
            }

            break;

        default:

            break;
    }
}
//--------------------------------------------------
// Description  : Load KSV List to Rx KSV FIFO
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPLoadKsvFifo(void)
{
    bit bLoadAksv = _TRUE;

    PDATA_WORD(0) = 0;
    PDATA_WORD(1) = 0;

#if(_DP_HDCP_2_2_SUPPORT == _ON)
    if(GET_DP_TX_HDCP2_CAPABLE_SUPPORTED() == _TRUE)
    {
        if(GET_DP_TX_HDCP2_REPEATER_SUPPORTED() == _TRUE)
        {
            PDATA_WORD(1) = GET_DP_TX_HDCP2_RXINFO_DEVICE_COUNT() * 5;

            memcpy(g_pucDpTxHdcpKsvFifo, g_pucDpTxHdcp2ReceiverIdList, PDATA_WORD(1));
        }

        memcpy(&g_pucDpTxHdcpKsvFifo[PDATA_WORD(1)], g_pucDpTxHdcp2ReceiverId, 5);
        PDATA_WORD(1) += 5;

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
        bLoadAksv = _FALSE;
#endif
    }
    else if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#else
    if(GET_DP_TX_HDCP_DOWNSTREAM_SUPPORTED() == _TRUE)
#endif
    {
        if(GET_DP_TX_HDCP_DOWNSTREAM_REPEATER() == _TRUE)
        {
            PDATA_WORD(1) = (WORD) GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT() * 5;
        }

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
        // Backup BKSV of Downstream Device
        memcpy(g_pucDpTxHdcpKsvBackup, (volatile BYTE xdata *)PBB_4F_BKSV_0, 5);
#endif

        memcpy(&g_pucDpTxHdcpKsvFifo[PDATA_WORD(1)], (volatile BYTE xdata *)PBB_4F_BKSV_0, 5);
        PDATA_WORD(1) += 5;

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
        bLoadAksv = _FALSE;
#endif
    }

    if(bLoadAksv == _TRUE)
    {
        // Load KSV of TX into KSV FIFO
        memcpy(&g_pucDpTxHdcpKsvFifo[PDATA_WORD(1)], g_pucHdcpAksvBackup, 5);
        PDATA_WORD(1) += 5;
    }

    for(PDATA_WORD(0) = PDATA_WORD(1); PDATA_WORD(0) < ((WORD) _DP_TX_HDCP_DEVICE_COUNT_MAX * 5); PDATA_WORD(0)++)
    {
        g_pucDpTxHdcpKsvFifo[PDATA_WORD(0)] = 0x00;
    }
}

//--------------------------------------------------
// Description  : Dp Rx HDCP - Load SHA Result to DPCD table
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPLoadShaToDpcd(void)
{
    SET_DP_RX1_AUX_MANUAL_MODE();

    for(pData[0] = 0; pData[0] < 5; pData[0]++)
    {
        for(pData[1] = 0; pData[1] < 4; pData[1]++)
        {
            ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x14 + (pData[0] * 4) + pData[1]), ScalerGetByteVar(PB0_39_SHA_3 + (pData[0] * 4) - pData[1]));
        }
    }

    SET_DP_RX1_AUX_AUTO_MODE();
}
//--------------------------------------------------
// Description  : Load KSV List to Rx KSV FIFO
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPSetKsvFifoFirst(void)
{
    SET_DP_RX1_AUX_MANUAL_MODE();

    for(g_usDpRx1HdcpKsvFifoOffset = 0; g_usDpRx1HdcpKsvFifoOffset < 15; g_usDpRx1HdcpKsvFifoOffset++)
    {
        ScalerDpRx1SetDpcdValue(0x06, 0x80, (0x2C + g_usDpRx1HdcpKsvFifoOffset), g_pucDpTxHdcpKsvFifo[g_usDpRx1HdcpKsvFifoOffset]);
    }

    // Aux HW Control
    SET_DP_RX1_AUX_AUTO_MODE();
}
//--------------------------------------------------
// Description  : Set HDCP Read IRQ Timeout
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPSetReadIrqTimeout(void)
{
    SET_DP_RX1_HDCP_AUTH_READ_IRQ_TIMEOUT();
}
//--------------------------------------------------
// Description  : Set HDCP Repeater Proc Timeout
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPSetRepeaterProcTimeout(void)
{
    SET_DP_RX1_HDCP_AUTH_REPEATER_PROC_TIMEOUT();
}
//--------------------------------------------------
// Description  : Calculate SHA-1 Input
// Input Value  : Inpute Array, First Run
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPSha1Calculate(BYTE *pucInputArray, BYTE ucCalCount)
{
    // Reset SHA Block counter
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT3, _BIT3);

    // Start to Write SHA-1 Transform Input
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT3, 0x00);

    // Write SHA-1 Input Data, Total 512 bits
    for(pData[1] = 0; pData[1] < 16; pData[1]++)
    {
        ScalerSetByte(PB0_31_SHA_DATA1, pucInputArray[pData[1] * 4]);
        ScalerSetByte(PB0_32_SHA_DATA2, pucInputArray[1 + pData[1] * 4]);
        ScalerSetByte(PB0_33_SHA_DATA3, pucInputArray[2 + pData[1] * 4]);
        ScalerSetByte(PB0_34_SHA_DATA4, pucInputArray[3 + pData[1] * 4]);

        // Enable write 32-bit __data to SHA-1 block
        ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);
    }

    ScalerDpRx1HDCPAuthShaRun(((ucCalCount == 0x00) ? _TRUE : _FALSE));
}
//--------------------------------------------------
// Description  : Load KSV FIFO to SHA-1 Input
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPWriteShaInput(void)
{
    WORD usKsvFifoLength = 0;
    WORD usShaInputBitNumbers = 0;
    WORD usKsvLengthTemp = 0;

    usKsvFifoLength = (WORD) ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A) * 5;

    // Total bit numbers of SHA-1 input = KSV FIFO + B_info + M0'
    usShaInputBitNumbers = (usKsvFifoLength + 2 + 8) * 8;

    // Reset SHA Block counter
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT3, _BIT3);

    // Start to Write SHA-1 Transform Input
    ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT3, 0x00);

    // Write the KSV List into SHA-1 Transform Input
    do
    {
        ScalerSetByte(PB0_31_SHA_DATA1, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp]);
        ScalerSetByte(PB0_32_SHA_DATA2, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 1]);
        ScalerSetByte(PB0_33_SHA_DATA3, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 2]);
        ScalerSetByte(PB0_34_SHA_DATA4, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 3]);

        // Enable write 32-bit __data to SHA-1 block
        ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

        usKsvLengthTemp += 4;

        if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
        {
            ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
        }
    }
    while((usKsvFifoLength - usKsvLengthTemp) >= 4);

    // Write the remaining KSV, B info and M0' into SHA-1 Transform Input
    switch(usKsvFifoLength - usKsvLengthTemp)
    {
        case 1:

            ScalerSetByte(PB0_31_SHA_DATA1, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp]);
            ScalerSetByte(PB0_32_SHA_DATA2, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A));
            ScalerSetByte(PB0_33_SHA_DATA3, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B));
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_0());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_1());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_2());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_3());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_4());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_5());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_6());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_7());
            ScalerSetByte(PB0_34_SHA_DATA4, 0x80);

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            break;

        case 2:

            ScalerSetByte(PB0_31_SHA_DATA1, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp]);
            ScalerSetByte(PB0_32_SHA_DATA2, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 1]);
            ScalerSetByte(PB0_33_SHA_DATA3, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A));
            ScalerSetByte(PB0_34_SHA_DATA4, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B));

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_0());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_1());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_2());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_3());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_4());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_5());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_6());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_7());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, 0x80);
            ScalerSetByte(PB0_32_SHA_DATA2, 0x00);
            ScalerSetByte(PB0_33_SHA_DATA3, 0x00);
            ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            break;

        case 3:

            ScalerSetByte(PB0_31_SHA_DATA1, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp]);
            ScalerSetByte(PB0_32_SHA_DATA2, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 1]);
            ScalerSetByte(PB0_33_SHA_DATA3, g_pucDpTxHdcpKsvFifo[usKsvLengthTemp + 2]);
            ScalerSetByte(PB0_34_SHA_DATA4, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A));

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B));
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_0());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_1());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_2());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_3());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_4());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_5());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_6());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_7());
            ScalerSetByte(PB0_32_SHA_DATA2, 0x80);
            ScalerSetByte(PB0_33_SHA_DATA3, 0x00);
            ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            break;

        default:

            ScalerSetByte(PB0_31_SHA_DATA1, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A));
            ScalerSetByte(PB0_32_SHA_DATA2, ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B));
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_0());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_1());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_2());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_3());
            ScalerSetByte(PB0_33_SHA_DATA3, GET_DP_RX1_HDCP_M0_4());
            ScalerSetByte(PB0_34_SHA_DATA4, GET_DP_RX1_HDCP_M0_5());

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            ScalerSetByte(PB0_31_SHA_DATA1, GET_DP_RX1_HDCP_M0_6());
            ScalerSetByte(PB0_32_SHA_DATA2, GET_DP_RX1_HDCP_M0_7());
            ScalerSetByte(PB0_33_SHA_DATA3, 0x80);
            ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;

            if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
            {
                ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
            }

            break;
    }

    if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 60)
    {
        ScalerSetByte(PB0_31_SHA_DATA1, 0x00);
        ScalerSetByte(PB0_32_SHA_DATA2, 0x00);
        ScalerSetByte(PB0_33_SHA_DATA3, 0x00);
        ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

        // Enable write 32-bit __data to SHA-1 block
        ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

        usKsvLengthTemp += 4;

        if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) == 0)
        {
            ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
        }
    }

    // Write 0x00 into the remaining SHA-1 Transform Input space
    if((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) <= 56)
    {
        while((usKsvLengthTemp % _DP_HDCP_SHA1_INPUT_SIZE) < 56)
        {
            ScalerSetByte(PB0_31_SHA_DATA1, 0x00);
            ScalerSetByte(PB0_32_SHA_DATA2, 0x00);
            ScalerSetByte(PB0_33_SHA_DATA3, 0x00);
            ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

            // Enable write 32-bit __data to SHA-1 block
            ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

            usKsvLengthTemp += 4;
        }

        // The length of SHA-1 input is equal to 2^64(8 bytes)
        ScalerSetByte(PB0_31_SHA_DATA1, 0x00);
        ScalerSetByte(PB0_32_SHA_DATA2, 0x00);
        ScalerSetByte(PB0_33_SHA_DATA3, 0x00);
        ScalerSetByte(PB0_34_SHA_DATA4, 0x00);

        // Enable write 32-bit __data to SHA-1 block
        ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

        // Write the valid bit numbers into SHA-1 Transform Input
        ScalerSetByte(PB0_31_SHA_DATA1, 0x00);
        ScalerSetByte(PB0_32_SHA_DATA2, 0x00);
        ScalerSetByte(PB0_33_SHA_DATA3, HIBYTE(usShaInputBitNumbers));
        ScalerSetByte(PB0_34_SHA_DATA4, LOBYTE(usShaInputBitNumbers));

        // Enable write 32-bit __data to SHA-1 block
        ScalerSetBit(PB0_30_SHA_CONTRL, ~_BIT0, _BIT0);

        usKsvLengthTemp += 8;

        ScalerDpRx1HDCPAuthShaRun((usKsvLengthTemp == _DP_HDCP_SHA1_INPUT_SIZE) ? _TRUE : _FALSE);
    }
}

#if(_DP_HDCP14_CTS_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check Downstream Device Count/Depth is changed or not
// Input Value  : None
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerDpRx1HDCPDeviceCountChange(void)
{
    BYTE ucBInfoDevice = 0;
    BYTE ucBInfoDepth = 0;
    bit bBInfoDeviceExceed = _FALSE;
    bit bBInfoDepthExceed = _FALSE;

    if(GET_DP_TX_HDCP_DOWNSTREAM_REPEATER() == _TRUE)
    {
        if((GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT_MAX() == _TRUE) ||
           (GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT() > _DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT_EXCEED))
        {
            bBInfoDeviceExceed = _TRUE;
        }
        else
        {
            ucBInfoDevice = GET_DP_TX_HDCP_DOWNSTREAM_DEVICE_COUNT();
        }

        if((GET_DP_TX_HDCP_DOWNSTREAM_DEPTH_MAX() == _TRUE) || (GET_DP_TX_HDCP_DOWNSTREAM_DEPTH() > 6))
        {
            bBInfoDepthExceed = _TRUE;
        }
        else
        {
            ucBInfoDepth = GET_DP_TX_HDCP_DOWNSTREAM_DEPTH();
        }
    }

    if(bBInfoDeviceExceed == _FALSE)
    {
        ucBInfoDevice++;
    }
    else
    {
        ucBInfoDevice = 0x80;
    }

    if(bBInfoDepthExceed == _FALSE)
    {
        ucBInfoDepth++;
    }
    else
    {
        ucBInfoDepth = 0x08;
    }

    if((ucBInfoDevice != ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A)) ||
       (ucBInfoDepth != ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2B)))
    {
        return _TRUE;
    }

    return _FALSE;
}
#endif

//--------------------------------------------------
// Description  : Handle DP MST to SST Flow
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstToSstProc(void)
{
    if(GET_DP_TX_STREAM_SOURCE() == _DP_TX_SOURCE_NONE)
    {
        if(ScalerDpRx1MstToSstScanInputPort() == _TRUE)
        {
            if(ScalerDpRx1MstToSstMeasureInput() == _TRUE)
            {
                ScalerDpTxSetStreamSource(_DP_TX_SOURCE_MST2SST);
            }
        }
    }
    else
    {
        // Stable Check
        if(ScalerDpRx1MstToSstStableDetect() == _FALSE)
        {
            ScalerDpTxForceIdlePatternSetting();
            ScalerDpTxSetStreamSource(_DP_TX_SOURCE_NONE);

            // Disabel MST2SST Watch Dog
            CLR_REG_DP_RX_MST2SST_WATCH_DOG_ENABLE();
        }
    }
}
//--------------------------------------------------
// Description  : DP MST2SST Set Color Info Macros
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstToSstSetColorInfo(void)
{
#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)
    if(GET_DP_TX_VSC_SDP_COLOR_MODE() == _TRUE)
    {
        // Set Color Space Macro
        switch(g_stDpTxColorInfo.ucColorSpacePreValue)
        {
            case _VSC_COLOR_SPACE_0:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_RGB);
                break;

            case _VSC_COLOR_SPACE_1:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_YCBCR444);
                break;

            case _VSC_COLOR_SPACE_2:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_YCBCR422);
                break;

            case _VSC_COLOR_SPACE_3:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_YCBCR420);
                break;

            case _VSC_COLOR_SPACE_4:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_Y_ONLY);
                break;

            case _VSC_COLOR_SPACE_5:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_RAW);
                break;

            default:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_RGB);
                break;
        }
    }
    else
#endif
    {
        // Set Color Space Macro
        switch(g_stDpTxColorInfo.ucColorSpacePreValue)
        {
            case _BIT1:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_YCBCR422);
                break;

            case _BIT2:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_YCBCR444);
                break;

            case _BIT7:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_Y_ONLY);
                break;

            case (_BIT7 | _BIT1):
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_RAW);
                break;

            default:
                SET_DP_TX_INPUT_COLOR_SPACE(_COLOR_SPACE_RGB);
                break;
        }
    }

    // Set Porch Color
    if((GET_DP_TX_INPUT_COLOR_SPACE() == _COLOR_SPACE_YCBCR444) || (GET_DP_TX_INPUT_COLOR_SPACE() == _COLOR_SPACE_YCBCR422) || (GET_DP_TX_INPUT_COLOR_SPACE() == _COLOR_SPACE_YCBCR420))
    {
        SET_DP_TX_PORCH_COLOR_YCC_FULL();
    }
    else
    {
        SET_DP_TX_PORCH_COLOR_RGB();
    }

    // Set Color Depth Macro
    SET_DP_TX_INPUT_COLOR_DEPTH(g_stDpTxColorInfo.b3ColorDepthPreValue);
}
//--------------------------------------------------
// Description  : On Line Check DP MST2SST stability
// Input Value  : None
// Output Value : True --> DP MST2SST Stable
//                False --> DP MST2SST Unstable
//--------------------------------------------------
bit ScalerDpRx1MstToSstStableDetect(void)
{
    if(ScalerDpRx1MstToSstMiscCheck() == _FALSE)
    {
        return _FALSE;
    }

    if(ScalerDpRx1MstToSstFifoCheck(_DP_FIFO_POLLING_CHECK) == _FALSE)
    {
        return _FALSE;
    }

    if(ScalerDpRx1MstToSstMSAActiveChange() == _TRUE)
    {
        return _FALSE;
    }

    if(ScalerDpRxMstToSstTxMeasureTimingChange() == _TRUE)
    {
        return _FALSE;
    }

    return _TRUE;
}
#endif

#endif
#endif

#if(_D1_DP_EXIST == _ON)
#if(_DP_HDCP_2_2_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Content Protection Interrupt Request
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1CpIRQ_EXINT0(EnumDpRxBStatusType enumBStatusType)
{
    BYTE ucCpIrq;
    BYTE ucBackUp = 0;

    ucBackUp = ScalerGetByte_EXINT(PBA_D0_AUX_MODE_SET);

    switch(enumBStatusType)
    {
        case _DP_HDCP2_H_PRIME_AVAILABLE:
        case _DP_HDCP2_PARING_AVAILABLE:

            ScalerDpRx1SetDpcdValue_EXINT0(0x06, 0x94, 0x93, (ScalerDpRx1GetDpcdInfo_EXINT0(0x06, 0x94, 0x93) | (enumBStatusType >> 3)));

            break;

        default:

            break;
    }

    // Link Status CPIRQ Flag
    ucCpIrq = (ScalerDpRx1GetDpcdInfo_EXINT0(0x00, 0x02, 0x01) | _BIT2);

    // SET AUX AUTO MODE
    SET_DP_RX1_AUX_AUTO_MODE_EXINT();

    ScalerDpRx1SetDpcdValue_EXINT0(0x00, 0x02, 0x01, ucCpIrq);

    if((ucBackUp & _BIT1) == 0x00)
    {
        // SET AUX MANUAL MODE
        SET_DP_RX1_AUX_MANUAL_MODE_EXINT();
    }

    ScalerDpRx1HpdIrqAssert_EXINT0();
}
#endif
#endif

#if(_D1_DP_EXIST == _ON)
#if(_DP_MST_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Dp Rx LT Status Check
// Input Value  : None
// Output Value : True --> LT Status Pass
//                False --> LT Status Fail
//--------------------------------------------------
bit ScalerDpRx1LTStatusCheck(void)
{
    if((ScalerDpRx1CDRCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE) &&
       (ScalerDpRx1AlignCheck() == _TRUE) &&
       (ScalerDpRx1DecodeCheck() == _TRUE) &&
       ((ScalerDpRx1DFECheck() == _TRUE) || (ScalerDpRx1SignalCheck(ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x01) & 0x1F)) == _TRUE)))
    {
        return _TRUE;
    }

    return _FALSE;
}

#if(_DP_TX_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Enable HDCP Read IRQ Function
// Input Value  : bEnable
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1HDCPEnableReadIrq(bit bEnable)
{
    if(bEnable == _ENABLE)
    {
        if(ScalerDpRx1GetDpcdInfo(0x06, 0x80, 0x2A) > 3)
        {
            ScalerSetBit(PBA_FA_DUMMY_0, ~_BIT0, _BIT0);

            ScalerSetBit(PBA_FA_DUMMY_0, ~(_BIT3 | _BIT1), (_BIT3 | _BIT1));
        }
    }
    else
    {
        ScalerSetBit(PBA_FA_DUMMY_0, ~(_BIT3 | _BIT1), 0x00);

        CLR_DP_RX1_HDCP_AUTH_READ_IRQ_TIMEOUT();
    }
}
//--------------------------------------------------
// Description  : DP Adjust Vsync Delay
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstToSstAdjustVsyncDelay(void)
{
    DWORD ulBStoVSDelayDeltaOverflow = 0;
    DWORD ulBStoVSDelayDeltaUnderflow = 0;

    if(ScalerGetBit(PA_31_PG_CTRL_1, (_BIT1 | _BIT0)) == 0x00)// Fifo Ok
    {
        return;
    }
    else if(ScalerGetBit(PA_31_PG_CTRL_1, _BIT0) == _BIT0) // Fifo Overflow
    {
        // Get Htotal
        ScalerRead(PA_10_MSA_HTT_0, 2, &pData[0], _AUTOINC);

        // ((Link Clk * 256)/ Stream CLK) * Htotal / 256 --> 1 Line
        ulBStoVSDelayDeltaOverflow = (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 270UL) * 256) / ((DWORD)GET_INPUT_PIXEL_CLK()) * ((DWORD)PDATA_WORD(0)) / 256;

        DebugMessageRx1("DP MST2SST : Fifo Overflow --> nVidia Case", ulBStoVSDelayDeltaOverflow);
    }
    else if(ScalerGetBit(PA_31_PG_CTRL_1, _BIT1) == _BIT1) // Fifo Underflow
    {
        // Get Hactive
        ScalerRead(PA_14_MSA_HWD_0, 2, &pData[0], _AUTOINC);

        if(PDATA_WORD(0) != 1366)
        {
            return;
        }

        PDATA_WORD(0) = PDATA_WORD(0) - 2;

        // Set Hactive
        ScalerSetByte(PA_44_MN_DPF_HWD_M, pData[0]);
        ScalerSetByte(PA_45_MN_DPF_HWD_L, pData[1]);

        // ((Link Clk * 2)/ Stream CLK) --> 2 pixels
        ulBStoVSDelayDeltaUnderflow = (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 270) * 2) / ((DWORD)GET_INPUT_PIXEL_CLK());

        DebugMessageRx1("DP MST2SST : Fifo Underflow --> QD882 Case", ulBStoVSDelayDeltaUnderflow);
    }

    // For Initial Value Before Use PDATA_DWORD(0)
    pData[0] = 0;

    // Get BStoVSDelay Even
    ScalerRead(PA_37_EVBLK2VS_H, 3, &pData[1], _AUTOINC);

    // For Initial Value Before Use PDATA_DWORD(1)
    pData[4] = 0;

    // Get BStoVSDelay Odd
    ScalerRead(PA_3A_OVBLK2VS_H, 3, &pData[5], _AUTOINC);

    // BStoVSDelay = BStoVSDelay + (Nvid * 256 / Mvid) * ((DWORD)Htotal) / 256;
    PDATA_DWORD(0) = PDATA_DWORD(0) - ((ulBStoVSDelayDeltaOverflow + ulBStoVSDelayDeltaUnderflow) / 2);

    // BStoVSDelay = BStoVSDelay + (Nvid * 256 / Mvid) * ((DWORD)Htotal) / 256;
    PDATA_DWORD(1) = PDATA_DWORD(1) - ((ulBStoVSDelayDeltaOverflow + ulBStoVSDelayDeltaUnderflow) / 2);

    // Set Even Field BS to VS Delay
    ScalerSetByte(PA_37_EVBLK2VS_H, pData[1]);
    ScalerSetByte(PA_38_EVBLK2VS_M, pData[2]);
    ScalerSetByte(PA_39_EVBLK2VS_L, pData[3]);

    // Set Odd Field BS to VS Delay
    ScalerSetByte(PA_3A_OVBLK2VS_H, pData[5]);
    ScalerSetByte(PA_3B_OVBLK2VS_M, pData[6]);
    ScalerSetByte(PA_3C_OVBLK2VS_L, pData[7]);

    // Enable Double Buffer
    ScalerSetBit(PA_35_DPF_CTRL_0, ~_BIT6, _BIT6);

    // Reset Display Format Gen
    ScalerSetBit(PA_35_DPF_CTRL_0, ~_BIT7, 0x00);
    ScalerSetBit(PA_35_DPF_CTRL_0, ~_BIT7, _BIT7);

    // Polling Vertical BS
    ScalerTimerPollingFlagProc(50, PA_29_MST2SST_VBID, _BIT0, _TRUE);

    // Delay for PG Stable
    ScalerTimerDelayXms(_DP_ONE_FRAME_TIME_MAX);
}
//--------------------------------------------------
// Description  : DP MST2SST Display Format Generator Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1MstToSstDisplayFormatSetting(void)
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

    // Measurement Enable
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, 0x00);
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, _BIT7);

    if(ScalerTimerPollingFlagProc(_DP_MEASURE_POLLING_TIMEOUT, PA_58_MN_MEAS_CTRL, _BIT6, _TRUE) == _FALSE)
    {
        return _FALSE;
    }

    // Pop up The result
    SET_DP_RX1_MEASURE_POP_UP_MST2SST();

    // Measurement Disable
    ScalerSetBit(PA_58_MN_MEAS_CTRL, ~_BIT7, 0x00);

    // VBs2BS count in GDI clk
    ulVBs2BsCount = ((((DWORD)(ScalerGetByte(PA_58_MN_MEAS_CTRL) & 0x1F)) << 16) | (((DWORD)ScalerGetByte(PA_59_MN_MEAS_VLN_M)) << 8) | ((DWORD)ScalerGetByte(PA_5A_MN_MEAS_VLN_L)));

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_DP_MST_FREESYNC_ENABLED() == _TRUE)
    {
        // HBs2Bs count in Link Clk / 2
        usHBs2BsCount = (((DWORD)ScalerGetByte(PA_5B_MN_MEAS_HLN_M)) << 8) | ((DWORD)ScalerGetByte(PA_5C_MN_MEAS_HLN_L));

        // VTotal in line, Link Clk / 2 : (Link Rate * 27 / 2)
        usDpVtotal = ulVBs2BsCount * (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 27 / 2) / usHBs2BsCount * 1000 / _GDI_CLK_KHZ;

        ulDpMvidValue = ((((DWORD)ScalerGetByte(PA_20_MSA_MVID_00)) << 16) | (((DWORD)ScalerGetByte(PA_21_MSA_MVID_01)) << 8) | ((DWORD)ScalerGetByte(PA_22_MSA_MVID_02)));

        ulDpNvidValue = ((((DWORD)ScalerGetByte(PA_23_MSA_NVID_00)) << 16) | (((DWORD)ScalerGetByte(PA_24_MSA_NVID_01)) << 8) | ((DWORD)ScalerGetByte(PA_25_MSA_NVID_02)));

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
        usDpVtotal = ((((WORD)ScalerGetByte(PA_18_MSA_VTT_0)) << 8) | ((WORD)ScalerGetByte(PA_19_MSA_VTT_1)));

        // Calculate streamclk (Unit is Hz)
        ulStreamClkValue = (((((((DWORD)ScalerGetByte(PA_10_MSA_HTT_0)) << 8) | ((WORD)ScalerGetByte(PA_11_MSA_HTT_1))) * ((DWORD)usDpVtotal) * 100) / ulVBs2BsCount) * _GDI_CLK_KHZ * 10);
    }

    // Input Pixel CLK Unit is 0.1 M
    SET_DP_TX_INPUT_PIXEL_CLK(ulStreamClkValue / 100000);

    // Disable Generate Display Format
    ScalerSetBit(PA_35_DPF_CTRL_0, ~_BIT7, 0x00);

    // DP Display Format Generator Reset
    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT0, _BIT0);
    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT0, 0x00);

    // Delay a Complete Frame
    ScalerTimerDelayXms(_DP_TWO_FRAME_TIME_MAX);

    // Set Vactive
    ScalerRead(PA_1C_MSA_VHT_0, 2, &pData[4], _AUTOINC);
    ScalerSetByte(PA_4C_MN_DPF_VHT_M, pData[4]);
    ScalerSetByte(PA_4D_MN_DPF_VHT_L, pData[5]);

    // Set Hactive
    ScalerRead(PA_14_MSA_HWD_0, 2, pData, _AUTOINC);
    ScalerSetByte(PA_44_MN_DPF_HWD_M, pData[0]);
    ScalerSetByte(PA_45_MN_DPF_HWD_L, pData[1]);
    usDpHactive = PDATA_WORD(0);

#if(_DP_FREESYNC_SUPPORT == _ON)

    ScalerDpTxSSTSetAmdSpdInfo(_ON);

    if(GET_DP_MST_FREESYNC_ENABLED() == _TRUE)
    {
        // HTotal in Pixel Clk, Link Clk / 2 : (Link Rate * 27 / 2)
        WORD usDpHtotal = (DWORD)usHBs2BsCount * (GET_DP_TX_INPUT_PIXEL_CLK() / 10) / (ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00) * 27 / 2);

        // Set Htotal
        ScalerSetByte(PA_40_MN_DPF_HTT_M, HIBYTE(usDpHtotal));
        ScalerSetByte(PA_41_MN_DPF_HTT_L, LOBYTE(usDpHtotal));

        // Set Hstart
        ScalerSetByte(PA_42_MN_DPF_HST_M, HIBYTE(_DP_DE_ONLY_MODE_HSTART));
        ScalerSetByte(PA_43_MN_DPF_HST_L, LOBYTE(_DP_DE_ONLY_MODE_HSTART));

        // Set HSW
        ScalerSetByte(PA_46_MN_DPF_HSW_M, HIBYTE(_DP_DE_ONLY_MODE_HSW));
        ScalerSetByte(PA_47_MN_DPF_HSW_L, LOBYTE(_DP_DE_ONLY_MODE_HSW));

        // Set Vstart
        ScalerSetByte(PA_4A_MN_DPF_VST_M, HIBYTE(_DP_DE_ONLY_MODE_VSTART));
        ScalerSetByte(PA_4B_MN_DPF_VST_L, LOBYTE(_DP_DE_ONLY_MODE_VSTART));

        // Set VSW
        ScalerSetByte(PA_4E_MN_DPF_VSW_M, HIBYTE(_DP_DE_ONLY_MODE_VSW));
        ScalerSetByte(PA_4F_MN_DPF_VSW_L, LOBYTE(_DP_DE_ONLY_MODE_VSW));

        PDATA_WORD(0) = ScalerDpRx1MstToSstGetBStoHSDelay(usDpHtotal);

        // Set HBs2Bs
        ScalerSetByte(PA_3D_BS2HS_0, pData[0]);
        ScalerSetByte(PA_3E_BS2HS_1, pData[1]);

        ScalerDpRx1MstToSstInterlaceCheck(&usDpVtotal, &ucOddFlg);

        // Set DE Only Mode Vsync Front Porch
        ScalerSetByte(PA_3F_VS_FRONT_PORCH, GET_DP_RX1_VFRONT_PORCH());

        // Set DE Only Mode
        ScalerSetBit(PA_35_DPF_CTRL_0, ~(_BIT7 | _BIT5 | _BIT4), _BIT4);

        // Choose Frame start BE to Reset FIFO
        ScalerSetBit(PA_30_PG_CTRL_0, ~_BIT5, 0x00);

        // Set DP FREESYNC Mode Enable
        ScalerSetBit(PA_F0_DP_RSV0, ~_BIT0, _BIT0);

        DebugMessageRx1("MST FREESYNC Mode Enabled!!", ScalerGetByte(PA_35_DPF_CTRL_0));
    }
    else
#endif
    {
        DWORD ulBs2VsDelay = 0;

        // Set Htotal
        ScalerRead(PA_10_MSA_HTT_0, 2, &pData[2], _AUTOINC);
        ScalerSetByte(PA_40_MN_DPF_HTT_M, pData[2]);
        ScalerSetByte(PA_41_MN_DPF_HTT_L, pData[3]);

        // Get HSW
        pData[4] = ScalerGetBit(PA_16_MSA_HSW_0, (_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
        pData[5] = ScalerGetByte(PA_17_MSA_HSW_1);

        // Get HSW min by Measure clock
        PDATA_WORD(3) = ((DWORD) _DP_HSYNC_WIDTH_MEASURE_COUNTER * GET_DP_TX_INPUT_PIXEL_CLK() * 100) / _MEASURE_CLK + 1;

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

        // Get Hstart
        pData[8] = ScalerGetByte(PA_12_MSA_HST_0);
        pData[9] = ScalerGetByte(PA_13_MSA_HST_1);

        // H Front Porch = (Htotal - Hactive - Hstart) < 8
        if((PDATA_WORD(1) - usDpHactive - PDATA_WORD(4)) < _DP_HSYNC_FRONT_PORCH)
        {
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
                else if((PDATA_WORD(1) - usDpHactive - PDATA_WORD(3)) >= _DP_HSYNC_FRONT_PORCH)
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
        }

        // Set HSW and HSP => positive
        ScalerSetByte(PA_46_MN_DPF_HSW_M, (pData[4] & ~_BIT7));
        ScalerSetByte(PA_47_MN_DPF_HSW_L, pData[5]);

        // Set Hstart
        ScalerSetByte(PA_42_MN_DPF_HST_M, pData[8]);
        ScalerSetByte(PA_43_MN_DPF_HST_L, pData[9]);

        DebugMessageRx1("###Origin usVTotal###", usDpVtotal);

        if(ScalerDpRx1MstToSstInterlaceCheck(&usDpVtotal, &ucOddFlg) == _TRUE) // Interlace
        {
            DebugMessageRx1("7. MST IIIIIInterLace Vtotal", usDpVtotal);

            SET_DP_TX_INPUT_INTERLACE_MODE(_ON);
        }
        else // Progressive
        {
            DebugMessageRx1("7. MST PPPPProgressive", 0);

            SET_DP_TX_INPUT_INTERLACE_MODE(_OFF);
        }

        // Set Vtotal
        ScalerSetByte(PA_48_MN_DPF_VTT_M, (usDpVtotal >> 8));
        ScalerSetByte(PA_49_MN_DPF_VTT_L, (usDpVtotal & 0xFF));

        // Get Vactive
        ScalerRead(PA_1C_MSA_VHT_0, 2, &pData[4], _AUTOINC);

        // V Front porch must not be less than 2 because of V scaling down.
        // Set Vstart -> (Vtotal - Vactive - Frontporch)
        PDATA_WORD(0) = usDpVtotal - PDATA_WORD(2) - GET_DP_RX1_MST_TO_SST_VFRONT_PORCH();
        ScalerSetByte(PA_4A_MN_DPF_VST_M, pData[0]);
        ScalerSetByte(PA_4B_MN_DPF_VST_L, pData[1]);

        // Set VSW; Set VSP => Positive
        ScalerSetByte(PA_4E_MN_DPF_VSW_M, (HIBYTE(_DP_VSYNC_WIDTH_MST2SST) & ~_BIT7));
        ScalerSetByte(PA_4F_MN_DPF_VSW_L, LOBYTE(_DP_VSYNC_WIDTH_MST2SST));

        ulBs2VsDelay = ScalerDpRx1MstToSstGetBStoVSDelay();

        // Set Odd Field BS to VS Delay
        ScalerSetByte(PA_3A_OVBLK2VS_H, (BYTE)(ulBs2VsDelay >> 16));
        ScalerSetByte(PA_3B_OVBLK2VS_M, (BYTE)(ulBs2VsDelay >> 8));
        ScalerSetByte(PA_3C_OVBLK2VS_L, (BYTE)(ulBs2VsDelay >> 0));

        if((bit)ucOddFlg == _TRUE)
        {
            // Get Htotal
            ScalerRead(PA_10_MSA_HTT_0, 2, &pData[0], _AUTOINC);

            // BStoVSDelay = BStoVSDelay + (Link Clk * 256 / Stream Clk) * ((DWORD)Htotal) / 256;
            ulBs2VsDelay += ((((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270UL) * 256) / ((DWORD)GET_DP_TX_INPUT_PIXEL_CLK()) * ((DWORD)PDATA_WORD(0)) / 256 / 2;

            SET_DP_TX_INPUT_INTERLACE_VTOTAL_NUMBER(_ODD);
        }
        else
        {
            SET_DP_TX_INPUT_INTERLACE_VTOTAL_NUMBER(_EVEN);
        }

        // Set Even Field BS to VS Delay
        ScalerSetByte(PA_37_EVBLK2VS_H, (BYTE)(ulBs2VsDelay >> 16));
        ScalerSetByte(PA_38_EVBLK2VS_M, (BYTE)(ulBs2VsDelay >> 8));
        ScalerSetByte(PA_39_EVBLK2VS_L, (BYTE)(ulBs2VsDelay >> 0));

        // Choose VS Rising to Reset FIFO
        ScalerSetBit(PA_30_PG_CTRL_0, ~_BIT5, 0x00);

        // Set DP FREESYNC Mode Disable
        ScalerSetBit(PA_F0_DP_RSV0, ~_BIT0, 0x00);

        // Set full last line Mode
        ScalerSetBit(PA_35_DPF_CTRL_0, ~(_BIT7 | _BIT5 | _BIT4), 0x00);

        DebugMessageRx1("MST FREESYNC Mode Disabled!!", ScalerGetByte(PA_35_DPF_CTRL_0));
    }

    // Double Buffer to Apply Display Format Setting
    ScalerSetBit(PA_35_DPF_CTRL_0, ~_BIT6, _BIT6);

    ScalerDpRx1MstToSstVideoSetting();

    return _TRUE;
}
//--------------------------------------------------
// Description  : DP MST2SST Video Fifo Check
// Input Value  : Fifo Check Condition
// Output Value : True --> Fifo not over/underflow
//--------------------------------------------------
bit ScalerDpRx1MstToSstFifoCheck(EnumDpFifoCheckCondition enumFifoCheckCondition)
{
    if(enumFifoCheckCondition == _DP_FIFO_DELAY_CHECK)
    {
        ScalerSetBit(PA_31_PG_CTRL_1, ~(_BIT4 | _BIT2 | _BIT0), (_BIT4 | _BIT2 | _BIT0));

        ScalerTimerDelayXms(_DP_TWO_FRAME_TIME_MAX);

        pData[0] = 0;

        while(pData[0] < 6)
        {
            ScalerTimerDelayXms(10);

            if((ScalerGetBit(PA_31_PG_CTRL_1, _BIT4) == _BIT4) || (ScalerGetBit(PA_31_PG_CTRL_1, _BIT2) == _BIT2))
            {
                return _FALSE;
            }

            pData[0]++;
        }
    }
    else
    {
        if((ScalerGetBit(PA_31_PG_CTRL_1, _BIT4) == _BIT4) || (ScalerGetBit(PA_31_PG_CTRL_1, _BIT2) == _BIT2))
        {
            return _FALSE;
        }
    }

    return _TRUE;
}
//--------------------------------------------------
// Description  : DP MST2SST BS to VS Delay Calculation
// Input Value  : None
// Output Value : BS to VS Delay
//--------------------------------------------------
DWORD ScalerDpRx1MstToSstGetBStoVSDelay(void)
{
    DWORD ulVFrontPorch = 0;
    DWORD ulHFrontPorch = 0;
    WORD usFifoOffset = 0;

    // Get Htotal
    ScalerRead(PA_10_MSA_HTT_0, 2, &pData[2], _AUTOINC);

    // VFrontPorch = 3 * Htotal * (Link Clk / Stream CLK)
    ulVFrontPorch = ((DWORD)GET_DP_RX1_MST_TO_SST_VFRONT_PORCH()) * ((DWORD)PDATA_WORD(1) * 256) / ((DWORD)GET_DP_TX_INPUT_PIXEL_CLK()) *
                    (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270) / 256;

    // Get Hactive
    ScalerRead(PA_14_MSA_HWD_0, 2, pData, _AUTOINC);

    // Get HSW
    pData[4] = ScalerGetBit(PA_16_MSA_HSW_0, (_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
    pData[5] = ScalerGetByte(PA_17_MSA_HSW_1);

    // Get HSW min by Measure clock
    PDATA_WORD(3) = ((DWORD) _DP_HSYNC_WIDTH_MEASURE_COUNTER * GET_DP_TX_INPUT_PIXEL_CLK() * 100) / _MEASURE_CLK + 1;

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

    // Get Hstart
    pData[8] = ScalerGetByte(PA_12_MSA_HST_0);
    pData[9] = ScalerGetByte(PA_13_MSA_HST_1);

    // H Front Porch = (Htotal - Hactive - Hstart) < 8
    if((PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(4)) < _DP_HSYNC_FRONT_PORCH)
    {
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
            else if((PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(3)) >= _DP_HSYNC_FRONT_PORCH)
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
    }

    // HFrontPorch = (Htotal - Hactive - Hstart) * (Link Clk / Stream CLK)
    ulHFrontPorch = (((DWORD)(PDATA_WORD(1) - PDATA_WORD(0) - PDATA_WORD(4))) * (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270) / ((DWORD)GET_DP_TX_INPUT_PIXEL_CLK()));

    // Get MISC Info
    ScalerRead(PA_28_MSA_COLOR_BIT, 1, &pData[14], _NON_AUTOINC);

    switch(pData[14] & (_BIT2 | _BIT1 | _BIT0))
    {
        case 0x00:
            pData[15] = 6;
            break;

        case (_BIT0):
            pData[15] = 8;
            break;

        case (_BIT1):
            pData[15] = 10;
            break;

        case (_BIT1 | _BIT0):
            pData[15] = 12;
            break;

        case (_BIT2):
            pData[15] = 16;
            break;

        default:
            break;
    }

    // DP fifo size = 256 x 96bit
    if(ScalerGetBit(PA_28_MSA_COLOR_BIT, (_BIT4 | _BIT3)) == _BIT3)
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
    usFifoOffset = (WORD)(((DWORD)usFifoOffset) * (((DWORD)ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00)) * 270) / ((DWORD)GET_DP_TX_INPUT_PIXEL_CLK()));

    return ((ulVFrontPorch + ulHFrontPorch + (DWORD)usFifoOffset) / 2);
}
//--------------------------------------------------
// Description  : DP MST2SST Get Video Info
// Input Value  : None
// Output Value : _TRUE --> Get Successfully
//--------------------------------------------------
bit ScalerDpRx1MstToSstGetVideoInfo(void)
{
#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)

    CLR_DP_TX_VSC_SDP_COLOR_MODE();

    // Check MISC1[6]
    if((ScalerGetBit(PA_27_MSA_MISC_1, _BIT6)) == _BIT6)
    {
        SET_DP_TX_VSC_SDP_COLOR_MODE();

#if(_HW_DP_VSC_SDP_REG_SUPPORT == _ON)

        // Read DB16~18 --> pData[0:2]
        ScalerRead(PBC_59_VSC_RX_DB16, 3, pData, _AUTOINC);
#else
        // Delay 2 frames for SRAM ready (worst case)
        ScalerTimerDelayXms(_DP_ONE_FRAME_TIME_MAX * 2);

        SET_DP_RX1_MST2SST_RSV1_DETECTING();

        ScalerTimerActiveTimerEvent((_DP_ONE_FRAME_TIME_MAX * 3), _SCALER_TIMER_EVENT_DP_RX1_MST2SST_RSV1_PACKET_DETECT);

        // Read DB16~18 --> pData[0:2]
        ScalerGetDataPortByte(PBC_55_DP_INFO_FM_ADR, _DP_INFO_RSV1_DB16, 3, pData, _AUTOINC);
#endif
        // Set Color Info PreValue
        g_stDpTxColorInfo.ucColorSpacePreValue = (pData[0] & (_BIT7 | _BIT6 | _BIT5 | _BIT4));
        g_stDpTxColorInfo.b3ColorDepthPreValue = (pData[1] & (_BIT2 | _BIT1 | _BIT0));
    }
    else
#endif
    {
        // Get MISC0 Info
        pData[0] = ScalerGetByte(PA_26_MSA_MISC_0);

        // Set Color Info PreValue
        g_stDpTxColorInfo.ucColorSpacePreValue = ((ScalerGetBit(PA_27_MSA_MISC_1, _BIT7)) | (pData[0] & (_BIT2 | _BIT1)));
        g_stDpTxColorInfo.b3ColorDepthPreValue = ((pData[0] & (_BIT7 | _BIT6 | _BIT5)) >> 5);
    }

    return _TRUE;
}
//--------------------------------------------------
// Description  : Check Dp Video Straam VBID
// Input Value  : None
// Output Value : True --> Get Video Stream
//--------------------------------------------------
bit ScalerDpRx1MstToSstGetVideoStream(void)
{
    // Check if ST2_Source is Assigned the STx Stream In MST Mode
    if((ScalerGetBit(PB0_01_PHY_DIG_RESET_CTRL, _BIT7) == _BIT7) &&
       (ScalerGetBit(PB8_0D_SOURCE_SEL_0, (_BIT2 | _BIT1 | _BIT0)) == 0x00))
    {
        return _FALSE;
    }

    if(ScalerGetBit(PA_29_MST2SST_VBID, _BIT3) == 0x00)
    {
        return _TRUE;
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Check DP Vactive / Hactive Information
// Input Value  : None
// Output Value : True --> DP Vactive / Hactive Information Check Ok
//--------------------------------------------------
bit ScalerDpRx1MstToSstMSAActiveChange(void)
{
    // Pop up Main Stream Attributes
    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT3, _BIT3);

    // Get Display Format Hactive
    ScalerRead(PA_44_MN_DPF_HWD_M, 2, &pData[0], _AUTOINC);

    // Get MSA Hactive
    ScalerRead(PA_14_MSA_HWD_0, 2, &pData[2], _AUTOINC);

    // Get Display Format Vactive
    ScalerRead(PA_4C_MN_DPF_VHT_M, 2, &pData[4], _AUTOINC);

    // Get MSA Vactive
    ScalerRead(PA_1C_MSA_VHT_0, 2, &pData[6], _AUTOINC);

    if((PDATA_WORD(0) != PDATA_WORD(1)) || (PDATA_WORD(2) != PDATA_WORD(3)))
    {
        return _TRUE;
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Check Dp MST2SSST MSA info.
// Input Value  : None
// Output Value : True --> Get MSA
//--------------------------------------------------
bit ScalerDpRx1MstToSstMSACheck(void)
{
    // Pop up Main Stream Attributes
    ScalerSetBit(PA_00_MST2SST_RESET, ~_BIT3, _BIT3);

    // Get Hactive
    ScalerRead(PA_14_MSA_HWD_0, 2, &pData[4], _AUTOINC);

    // Get Vactive
    ScalerRead(PA_1C_MSA_VHT_0, 2, &pData[12], _AUTOINC);

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_DP_MST_FREESYNC_ENABLED() == _TRUE)
    {
        if((PDATA_WORD(2) == 0x00) || (PDATA_WORD(6) == 0x00))
        {
            return _FALSE;
        }
    }
    else
#endif
    {
        // Get Htotal
        ScalerRead(PA_10_MSA_HTT_0, 2, &pData[0], _AUTOINC);

        // Get Hstart
        ScalerRead(PA_12_MSA_HST_0, 2, &pData[2], _AUTOINC);

        // Get HSW
        ScalerRead(PA_16_MSA_HSW_0, 2, &pData[6], _AUTOINC);

        // Get Vtotal
        ScalerRead(PA_18_MSA_VTT_0, 2, &pData[8], _AUTOINC);

        // Get Vstart
        ScalerRead(PA_1A_MSA_VST_0, 2, &pData[10], _AUTOINC);

        // Get VSW
        ScalerRead(PA_1E_MSA_VSW_0, 2, &pData[14], _AUTOINC);

        if((PDATA_WORD(0) == 0x00) || (PDATA_WORD(1) == 0x00) || (PDATA_WORD(2) == 0x00) || ((PDATA_WORD(3) & 0x7FFF) == 0x00) ||
           (PDATA_WORD(4) == 0x00) || (PDATA_WORD(5) == 0x00) || (PDATA_WORD(6) == 0x00) || ((PDATA_WORD(7) & 0x7FFF) == 0x00))
        {
            return _FALSE;
        }
    }

    // Get Mvid
    ScalerRead(PA_20_MSA_MVID_00, 3, pData, _AUTOINC);

    if((((DWORD)pData[0] << 16) | ((DWORD)pData[1] << 8) | ((DWORD)pData[2] << 0)) == 0x00)
    {
        return _FALSE;
    }

    // Get Nvid
    ScalerRead(PA_23_MSA_NVID_00, 3, pData, _AUTOINC);

    if((((DWORD)pData[0] << 16) | ((DWORD)pData[1] << 8) | ((DWORD)pData[2] << 0)) == 0x00)
    {
        return _FALSE;
    }

    return _TRUE;
}
//--------------------------------------------------
// Description  : DP Rx1 MST to SST Measure
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDpRx1MstToSstMeasureInput(void)
{
    // Format Conversion Select to SST_D1
    ScalerSetBit(P31_02_FC_INPUT_DPTX_SEL, ~(_BIT6 | _BIT5 | _BIT4), (_FC_SOURCE_SST << 4));

    // DPTx CTS Fifo reset
    ScalerSetBit(PBB_D7_DPTX_CTSFIFO_CTRL, ~_BIT2, 0x00);
    ScalerSetBit(PBB_D7_DPTX_CTSFIFO_CTRL, ~_BIT2, _BIT2);

#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_DP_MST_FREESYNC_ENABLED() == _TRUE)
    {
        return ScalerDpTxMeasureInputInfo();
    }
    else
#endif
    {
        return ScalerDpTxInputMSAInfo();
    }
}
//--------------------------------------------------
// Description  : Check DP MST2SST Misc Information
// Input Value  : None
// Output Value : True --> DP Misc Check Ok
//--------------------------------------------------
bit ScalerDpRx1MstToSstMiscCheck(void)
{
#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)
    // Check MISC1[6]
    if((ScalerGetBit(PA_27_MSA_MISC_1, _BIT6)) == _BIT6)
    {
        return ScalerDpRx1MstToSstVscCheck();
    }
    else
#endif
    {
        // Get MISC0 Info
        BYTE ucMisc0 = ScalerGetByte(PA_26_MSA_MISC_0);
        BYTE ucColorSpaceValue = (ScalerGetBit(PA_27_MSA_MISC_1, _BIT7)) | (ucMisc0 & (_BIT2 | _BIT1));

        // Color Space Check
#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)

        // Color format info source change from VSC --> MISC
        if(GET_DP_TX_VSC_SDP_COLOR_MODE() == _TRUE)
        {
            switch(ucColorSpaceValue)
            {
                case _BIT1:
                    if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_YCBCR422)
                    {
                        return _FALSE;
                    }
                    break;

                case _BIT2:
                    if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_YCBCR444)
                    {
                        return _FALSE;
                    }
                    break;

                case _BIT7:
                    if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_Y_ONLY)
                    {
                        return _FALSE;
                    }
                    break;

                case (_BIT7 | _BIT1):
                    if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_RAW)
                    {
                        return _FALSE;
                    }
                    break;

                default:
                    if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_RGB)
                    {
                        return _FALSE;
                    }
                    break;
            }
        }
        else
#endif
        {
            if(ucColorSpaceValue != g_stDpTxColorInfo.ucColorSpacePreValue)
            {
                return _FALSE;
            }
        }

        // Color Depth Check
        if(ScalerGetBit(PA_28_MSA_COLOR_BIT, (_BIT2 | _BIT1 | _BIT0)) != (g_stDpTxColorInfo.b3ColorDepthPreValue))
        {
            return _FALSE;
        }

        // Get HSW
        ScalerRead(PA_16_MSA_HSW_0, 2, pData, _AUTOINC);

        // Get VSW
        ScalerRead(PA_1E_MSA_VSW_0, 2, &pData[2], _AUTOINC);

        if(((PDATA_WORD(0) & 0x7FFF) == 0x00) || ((PDATA_WORD(1) & 0x7FFF) == 0x00))
        {
            return _FALSE;
        }

        return _TRUE;
    }
}
//--------------------------------------------------
// Description  : DP Port Source/Sync Scanning and Setting
// Input Value  : None
// Output Value : Source DP --> DP Sync Stable
//                Source None --> No Stable Sync
//--------------------------------------------------
BYTE ScalerDpRx1MstToSstScanInputPort(void)
{
    if(ScalerDpRx1MstToSstGetVideoStream() == _FALSE)
    {
        return _FALSE;
    }

#if(_DP_FREESYNC_SUPPORT == _ON)
    ScalerDpTxAuxNativeRead(0x00, 0x01, 0x07, 1, pData);

    if((pData[0] & _BIT7) == _BIT7)
    {
        SET_DP_MST_FREESYNC_ENABLED();
    }
    else
    {
        CLR_DP_MST_FREESYNC_ENABLED();
    }
#endif

    if(ScalerDpRx1MstToSstMSACheck() == _FALSE)
    {
        return _FALSE;
    }

    if(ScalerDpRx1MstToSstGetVideoInfo() == _FALSE)
    {
        return _FALSE;
    }
    else
    {
        ScalerDpRx1MstToSstSetColorInfo();
    }

    if(ScalerDpRx1MstToSstDisplayFormatSetting() == _FALSE)
    {
        return _FALSE;
    }

    if(ScalerDpRx1MstToSstStreamClkRegenerate() == _FALSE)
    {
        return _FALSE;
    }

    if(ScalerDpRx1MstToSstFifoCheck(_DP_FIFO_DELAY_CHECK) == _FALSE)
    {
        ScalerDpRx1MstToSstAdjustVsyncDelay();

        if(ScalerDpRx1MstToSstFifoCheck(_DP_FIFO_DELAY_CHECK) == _FALSE)
        {
            return _FALSE;
        }
    }

    // DP MST2SST RGB Output Enable
    ScalerSetBit(PA_36_DP_OUTPUT_CTRL, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT1 | _BIT0));

    // DP MST2SST CLK Output Enable
    ScalerSetBit(PA_B8_MN_SCLKG_SDM_CTRL, ~_BIT6, _BIT6);

    // Enable Under/OverFlow WatchDog
    SET_REG_DP_RX_MST2SST_WATCH_DOG_ENABLE();

    return _TRUE;
}
//--------------------------------------------------
// Description  : DP MST2SST Video Setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1MstToSstVideoSetting(void)
{
    // Set Color Space for Display Format Gen.
    switch(GET_DP_TX_INPUT_COLOR_SPACE())
    {
        case _COLOR_SPACE_RGB:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), 0x00);
            break;

        case _COLOR_SPACE_YCBCR444:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), _BIT4);
            break;

        case _COLOR_SPACE_YCBCR422:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), _BIT3);
            break;

        case _COLOR_SPACE_YCBCR420:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), 0x00);
            break;

        case _COLOR_SPACE_Y_ONLY:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), (_BIT4 | _BIT3));
            break;

        case _COLOR_SPACE_RAW:
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), 0x00);
            break;

        default:
            // RGB
            ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT4 | _BIT3), 0x00);
            break;
    }

    // Set Color depth for Display Format Gen.
    ScalerSetBit(PA_30_PG_CTRL_0, ~(_BIT2 | _BIT1 | _BIT0), (g_stDpTxColorInfo.b3ColorDepthPreValue));
}

#if(_DP_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP BS to HS Delay Calculation
// Input Value  : None
// Output Value : BS to VS Delay
//--------------------------------------------------
WORD ScalerDpRx1MstToSstGetBStoHSDelay(WORD usDpHtotal)
{
    WORD usFifoOffset = 0;

    // Get MISC Info
    ScalerRead(PA_28_MSA_COLOR_BIT, 1, &pData[14], _NON_AUTOINC);

    switch(pData[14] & (_BIT2 | _BIT1 | _BIT0))
    {
        case 0x00:
            pData[15] = 6;
            break;

        case (_BIT0):
            pData[15] = 8;
            break;

        case (_BIT1):
            pData[15] = 10;
            break;

        case (_BIT1 | _BIT0):
            pData[15] = 12;
            break;

        case (_BIT2):
            pData[15] = 16;
            break;

        default:
            pData[15] = 8;
            break;
    }

    // DP fifo size = 256 x 96bit
    if(ScalerGetBit(PA_28_MSA_COLOR_BIT, (_BIT4 | _BIT3)) == _BIT3)
    {
        // FifoOffset = (1/2 * (256 * 96) / (2 * depth per color)), color format is YCbCr 4:2:2
        usFifoOffset = _HW_DP_RX_VIDEO_FIFO_SIZE / (4 * (WORD)pData[15]);
    }
    else
    {
        // FifoOffset = (1/2 * (256 * 96) / (3 * depth per color)), color format is RGB or YCbCr 4:4:4 or others
        usFifoOffset = _HW_DP_RX_VIDEO_FIFO_SIZE / (6 * (WORD)pData[15]);
    }

    // Get Hstart
    ScalerRead(PA_42_MN_DPF_HST_M, 2, &pData[0], _AUTOINC);

    // Get Hactive
    ScalerRead(PA_44_MN_DPF_HWD_M, 2, &pData[2], _AUTOINC);

    // H Blanking = HTotal - HActive
    PDATA_WORD(2) = usDpHtotal - PDATA_WORD(1);

    // Set BS to HS delay to (HBlanking + 1/2 FIFO - HStart), BS2HS delay: 2 pixel mode
    return ((WORD)((PDATA_WORD(2) + usFifoOffset - PDATA_WORD(0)) >> 1));
}
#endif

#if(_DP_VSC_SDP_EXT_FOR_COLORIMETRY_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check DP MST2SST VSC Information
// Input Value  : None
// Output Value : True --> DP VSC Check Ok
//--------------------------------------------------
bit ScalerDpRx1MstToSstVscCheck(void)
{
    BYTE pucVscColorFormat[3];

    memset(pucVscColorFormat, 0, sizeof(pucVscColorFormat));

#if(_HW_DP_VSC_SDP_REG_SUPPORT == _ON)

    // Read DB16~18 --> pucVscColorFormat[0:2]
    ScalerRead(PBC_59_VSC_RX_DB16, 3, pucVscColorFormat, _AUTOINC);
#else
    if(GET_DP_RX1_MST2SST_RSV1_DETECTING() == _FALSE)
    {
        // Read DB16~18 --> pucVscColorFormat[0:2]
        ScalerGetDataPortByte(PBC_55_DP_INFO_FM_ADR, _DP_INFO_RSV1_DB16, 3, pucVscColorFormat, _AUTOINC);

        SET_DP_RX1_MST2SST_RSV1_DETECTING();

        ScalerTimerActiveTimerEvent((_DP_ONE_FRAME_TIME_MAX * 3), _SCALER_TIMER_EVENT_DP_RX1_MST2SST_RSV1_PACKET_DETECT);
    }
    else
    {
        return _TRUE;
    }
#endif

    // Color Space Check
    if(GET_DP_TX_VSC_SDP_COLOR_MODE() == _FALSE)
    {
        // Color format info source change from MISC --> VSC
        switch(pucVscColorFormat[0] & (_BIT7 | _BIT6 | _BIT5 | _BIT4))
        {
            case _VSC_COLOR_SPACE_0:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_RGB)
                {
                    return _FALSE;
                }

                break;

            case _VSC_COLOR_SPACE_1:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_YCBCR444)
                {
                    return _FALSE;
                }

                break;

            case _VSC_COLOR_SPACE_2:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_YCBCR422)
                {
                    return _FALSE;
                }

                break;

            case _VSC_COLOR_SPACE_3:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_YCBCR420)
                {
                    return _FALSE;
                }

                break;

            case _VSC_COLOR_SPACE_4:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_Y_ONLY)
                {
                    return _FALSE;
                }

                break;

            case _VSC_COLOR_SPACE_5:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_RAW)
                {
                    return _FALSE;
                }

                break;

            default:
                if(GET_DP_TX_INPUT_COLOR_SPACE() != _COLOR_SPACE_RGB)
                {
                    return _FALSE;
                }

                break;
        }
    }
    else
    {
        if((pucVscColorFormat[0] & (_BIT7 | _BIT6 | _BIT5 | _BIT4)) != g_stDpTxColorInfo.ucColorSpacePreValue)
        {
            return _FALSE;
        }
    }

    // Color Depth Check
    if((pucVscColorFormat[1] & (_BIT2 | _BIT1 | _BIT0)) != (ScalerGetBit(PA_30_PG_CTRL_0, (_BIT2 | _BIT1 | _BIT0))))
    {
        return _FALSE;
    }

    return _TRUE;
}
#endif

//--------------------------------------------------
// Description  : Set DP Rx DPCD DFP Detail Cap Reset
// Input Value  : Input Port
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1DfpDeviceDetailConfigReset(void)
{
#if(_EIZO_CUSTOMIZED_VALUE_OF_DPCD_SUPPORT == _OFF)
    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x00);

    ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x80, 0x00);
#endif
}

//--------------------------------------------------
// Description  : Set DP Rx DPCD DFP Detail Set
// Input Value  : Input Port
// Output Value : None
//--------------------------------------------------
void ScalerDpRx1DfpDeviceDetailConfig(void)
{
#if(_EIZO_CUSTOMIZED_VALUE_OF_DPCD_SUPPORT == _OFF)
    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), 0x01);

    ScalerDpRx1SetDpcdValue(0x00, 0x00, 0x80, (_BIT6 | _BIT4 | _BIT3));
#endif
}
#endif

#endif
#endif
