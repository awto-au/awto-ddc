// Parked from fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonSync.c (#305, #44): append to the live file to restore (scripts/sdk_park_funcs.py restore).

#if(_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get FREESYNC Mode Enabled
// Input Value  : None
// Output Value : True  --> Enabled
//                False --> Disabled
//--------------------------------------------------
bit ScalerSyncGetFREESYNCEnable(void)
{
    return GET_FREESYNC_ENABLED();
}

#if((_DEBUG_MESSAGE_SUPPORT == _OFF) && (_HDMI_FREESYNC_SUPPORT == _ON) && (_HDMI_FREESYNC_CAPABILITY_SWITCH_METHOD == _MCCS_SWITCH_MODE))
//--------------------------------------------------
// Description  : Get HDMI FREESYNC VCP
// Input Value  : None
// Output Value : HDMI FREESYNC VCP
//                False --> Disabled
//--------------------------------------------------
BYTE ScalerSyncGetHDMIFREESYNCVcp_EXINT1(void)
{
    return GET_HDMI_FREESYNC_VCP();
}

//--------------------------------------------------
// Description  : Set HDMI FREESYNC VCP
// Input Value  : HDMI FREESYNC VCP
// Output Value : None
//--------------------------------------------------
void ScalerSyncSetHDMIFREESYNCVcp_EXINT1(BYTE ucVcpCode)
{
    g_ucHDMIFREESYNCVCPReceive = ucVcpCode;
}
#endif
#endif

#if(_ULTRA_HDR_SUPPORT == _ON)
#if(_FREESYNC_II_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get Current FreeSync II __data enable status
// Input Value  : enumSourceSearchPort --> Input port
// Output Value : _TRUE/_FALSE
//--------------------------------------------------
bit ScalerSyncFreeSyncIICheckPortStatus(EnumSourceSearchPort enumSourceSearchPort)
{
    switch(enumSourceSearchPort)
    {
        case _D0_INPUT_PORT:

#if((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
        case _D6_INPUT_PORT:
#endif
#if(_D0_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#elif(_D0_INPUT_PORT_TYPE == _D0_DP_PORT)
            if(_DP_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif
            break;

        case _D1_INPUT_PORT:

#if(_D1_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#elif(_D1_INPUT_PORT_TYPE == _D1_DP_PORT)
            if(_DP_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif

            break;

        case _D2_INPUT_PORT:
#if(_D2_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#elif(_D2_INPUT_PORT_TYPE == _D2_DP_PORT)
            if(_DP_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif

            break;

        case _D3_INPUT_PORT:
#if(_D3_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif
            break;

        case _D4_INPUT_PORT:
#if(_D4_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif
            break;

        case _D5_INPUT_PORT:
#if(_D5_HDMI_SUPPORT == _ON)
            if(_HDMI_FREESYNC_II_SUPPORT == _OFF)
            {
                return _FALSE;
            }
#endif
            break;

        default:
            return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : Get Current FreeSync II data
// Input Value  : pstFreeSyncIIMetadata --> FreeSync II data
//                enumSourceSearchPort --> Input port
// Output Value : _FALSE: no receive
//--------------------------------------------------
bit ScalerSyncFreeSyncIIGetCurrentStatus(StructFreeSyncIIInfo *pstFreeSyncIIMetadata, EnumSourceSearchPort enumSourceSearchPort)
{
    if(ScalerSyncFreeSyncIICheckPortStatus(enumSourceSearchPort) == _TRUE)
    {
        bit bFreeSyncIIInfoReceive = 0;
        BYTE pucFreeSyncIIInfoData[_HW_DP_INFOFRAME_RSV0_LENGTH];

        memset(pucFreeSyncIIInfoData, 0, _HW_DP_INFOFRAME_RSV0_LENGTH);

        switch(enumSourceSearchPort)
        {
#if(_D0_INPUT_PORT_TYPE == _D0_DP_PORT)

#if(_DP_FREESYNC_II_SUPPORT == _ON)
            case _D0_INPUT_PORT:

#if((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
            case _D6_INPUT_PORT:
#endif

#if(_DP_HDR10_SUPPORT == _ON)
                bFreeSyncIIInfoReceive = GET_DP_RX0_AMD_SPD_INFO_FRAME_RECEIVED();
#else
                bFreeSyncIIInfoReceive = _TRUE;
#endif
                memcpy(pucFreeSyncIIInfoData, g_pucDPRx0RSV0Backup, _HW_DP_INFOFRAME_RSV0_LENGTH);
                break;
#endif // End of #if(_DP_FREESYNC_II_SUPPORT == _ON)

#endif

#if(_D1_INPUT_PORT_TYPE == _D1_DP_PORT)

#if(_DP_FREESYNC_II_SUPPORT == _ON)
            case _D1_INPUT_PORT:

#if(_DP_HDR10_SUPPORT == _ON)
                bFreeSyncIIInfoReceive = GET_DP_RX1_AMD_SPD_INFO_FRAME_RECEIVED();
#else
                bFreeSyncIIInfoReceive = _TRUE;
#endif
                memcpy(pucFreeSyncIIInfoData, g_pucDPRx1RSV0Backup, _HW_DP_INFOFRAME_RSV0_LENGTH);
                break;
#endif // End of #if(_DP_FREESYNC_II_SUPPORT == _ON)

#elif(_D1_HDMI_SUPPORT == _ON)

#if(_HDMI_FREESYNC_II_SUPPORT == _ON)
            case _D1_INPUT_PORT:

#if(_TMDS_PAGE2_COMBO_EXIST == _ON)
                bFreeSyncIIInfoReceive = GET_TMDS_RX0_SPD_INFO_FRAME_RECEIVED();
#else
                bFreeSyncIIInfoReceive = GET_TMDS_RX1_SPD_INFO_FRAME_RECEIVED();
#endif

                GET_TMDSRX1_FREESYNCII_DATA(pucFreeSyncIIInfoData);

                break;
#endif // End of #if(_HDMI_FREESYNC_II_SUPPORT == _ON)

#endif

#if(_D2_INPUT_PORT_TYPE == _D2_DP_PORT)

#if(_DP_FREESYNC_II_SUPPORT == _ON)
            case _D2_INPUT_PORT:

#if(_DP_HDR10_SUPPORT == _ON)
                // RL6492: _DIGITAL_PORT_COMBO_PHY_D1_D2
                bFreeSyncIIInfoReceive = GET_DP_RX1_AMD_SPD_INFO_FRAME_RECEIVED();
#else
                bFreeSyncIIInfoReceive = _TRUE;
#endif
                memcpy(pucFreeSyncIIInfoData, g_pucDPRx1RSV0Backup, _HW_DP_INFOFRAME_RSV0_LENGTH);
                break;
#endif // End of #if(_DP_FREESYNC_II_SUPPORT == _ON)

#elif(_D2_HDMI_SUPPORT == _ON)

#if(_HDMI_FREESYNC_II_SUPPORT == _ON)
            case _D2_INPUT_PORT:

#if(_TMDS_PAGE2_COMBO_EXIST == _ON)
                bFreeSyncIIInfoReceive = GET_TMDS_RX0_SPD_INFO_FRAME_RECEIVED();
#else
                bFreeSyncIIInfoReceive = GET_TMDS_RX2_SPD_INFO_FRAME_RECEIVED();
#endif

                GET_TMDSRX2_FREESYNCII_DATA(pucFreeSyncIIInfoData);
                break;
#endif // End of #if(_HDMI_FREESYNC_II_SUPPORT == _ON)

#endif

#if(_D3_HDMI_SUPPORT == _ON)
#if(_HDMI_FREESYNC_II_SUPPORT == _ON)
            case _D3_INPUT_PORT:

                bFreeSyncIIInfoReceive = GET_TMDS_RX3_SPD_INFO_FRAME_RECEIVED();
                GET_TMDSRX3_FREESYNCII_DATA(pucFreeSyncIIInfoData);
                break;
#endif // End of #if(_HDMI_FREESYNC_II_SUPPORT == _ON)
#endif

#if(_D4_HDMI_SUPPORT == _ON)
#if(_HDMI_FREESYNC_II_SUPPORT == _ON)
            case _D4_INPUT_PORT:

                bFreeSyncIIInfoReceive = GET_TMDS_RX4_SPD_INFO_FRAME_RECEIVED();
                GET_TMDSRX4_FREESYNCII_DATA(pucFreeSyncIIInfoData);
                break;
#endif // End of #if(_HDMI_FREESYNC_II_SUPPORT == _ON)
#endif

#if(_D5_HDMI_SUPPORT == _ON)
#if(_HDMI_FREESYNC_II_SUPPORT == _ON)
            case _D5_INPUT_PORT:

                bFreeSyncIIInfoReceive = GET_TMDS_RX5_SPD_INFO_FRAME_RECEIVED();
                GET_TMDSRX5_FREESYNCII_DATA(pucFreeSyncIIInfoData);
                break;
#endif // End of #if(_HDMI_FREESYNC_II_SUPPORT == _ON)
#endif

            default:
                break;
        }

        // Check HDR Version/ Length & InfoFrame receive bit
        if((bFreeSyncIIInfoReceive == _TRUE) && (pucFreeSyncIIInfoData[1] == 0x1A) && (pucFreeSyncIIInfoData[2] == 0x00) && (pucFreeSyncIIInfoData[3] == 0x00))
        {
            pstFreeSyncIIMetadata->b1NativeColorSpaceEnable = (bit)(pucFreeSyncIIInfoData[6] & _BIT3);
            pstFreeSyncIIMetadata->b1BacklightControlEnable = (bit)(pucFreeSyncIIInfoData[6] & _BIT4);
            pstFreeSyncIIMetadata->b1LocalDimmingDisable = (bit)(pucFreeSyncIIInfoData[6] & _BIT5);
            pstFreeSyncIIMetadata->b5EOTFType = (pucFreeSyncIIInfoData[9] & 0x1F);
            pstFreeSyncIIMetadata->ucBacklightControlRatio = pucFreeSyncIIInfoData[10];

            return _TRUE;
        }
    }

    pstFreeSyncIIMetadata->b1NativeColorSpaceEnable = 0;
    pstFreeSyncIIMetadata->b1BacklightControlEnable = 0;
    pstFreeSyncIIMetadata->b1LocalDimmingDisable = 0;
    pstFreeSyncIIMetadata->b5EOTFType = 0x00;
    pstFreeSyncIIMetadata->ucBacklightControlRatio = 0x00;

    return _FALSE;
}
#endif // End of #if(_FREESYNC_II_SUPPORT == _ON)
#endif

#if(_DP_SUPPORT == _ON)
#if(_DP_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Dp Freesync Capability Switch
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerSyncDpFreesyncCapabilitySwitchProc(BYTE ucInputPort)
{
    switch(ucInputPort)
    {
#if(_D0_INPUT_PORT_TYPE == _D0_DP_PORT)
        case _D0_INPUT_PORT:

            if(GET_DP_RX0_FREESYNC_CAPABILITY_SWITCH() == _TRUE)
            {
                CLR_DP_RX0_FREESYNC_CAPABILITY_SWITCH();

                if(GET_DP_RX0_FREESYNC_SUPPORT() == _FREESYNC_SUPPORT_ON)
                {
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
                }
                else
                {
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
                }

                return _TRUE;
            }

            break;
#endif

#if(_D1_INPUT_PORT_TYPE == _D1_DP_PORT)
        case _D1_INPUT_PORT:

            if(GET_DP_RX1_FREESYNC_CAPABILITY_SWITCH() == _TRUE)
            {
                CLR_DP_RX1_FREESYNC_CAPABILITY_SWITCH();

                if(GET_DP_RX1_FREESYNC_SUPPORT() == _FREESYNC_SUPPORT_ON)
                {
#if(_HW_DIGITAL_PORT_COMBO_PHY_TYPE == _DIGITAL_PORT_COMBO_PHY_ALL)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
#else
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
#endif
                }
                else
                {
#if(_HW_DIGITAL_PORT_COMBO_PHY_TYPE == _DIGITAL_PORT_COMBO_PHY_ALL)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
#else
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
#endif
                }

                return _TRUE;
            }

            break;
#endif

#if(_D2_INPUT_PORT_TYPE == _D2_DP_PORT)
        case _D2_INPUT_PORT:

            if(GET_DP_RX2_FREESYNC_CAPABILITY_SWITCH() == _TRUE)
            {
                CLR_DP_RX2_FREESYNC_CAPABILITY_SWITCH();

                if(GET_DP_RX2_FREESYNC_SUPPORT() == _FREESYNC_SUPPORT_ON)
                {
#if(_HW_DIGITAL_PORT_COMBO_PHY_TYPE == _DIGITAL_PORT_COMBO_PHY_ALL)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
#else
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
#endif
                }
                else
                {
#if(_HW_DIGITAL_PORT_COMBO_PHY_TYPE == _DIGITAL_PORT_COMBO_PHY_ALL)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
#else
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx1SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
#endif
                }

                return _TRUE;
            }

            break;
#endif

#if((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
        case _D6_INPUT_PORT:

            if(GET_DP_RX6_FREESYNC_CAPABILITY_SWITCH() == _TRUE)
            {
                CLR_DP_RX6_FREESYNC_CAPABILITY_SWITCH();

                if(GET_DP_RX6_FREESYNC_SUPPORT() == _FREESYNC_SUPPORT_ON)
                {
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, _BIT6);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, _BIT6);
#endif
                }
                else
                {
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x00, 0x07, ~_BIT6, 0x00);

#if(_HW_DP_DPCD_EXT_CAP_PHYSICAL_ADDRESS_SUPPORT == _ON)
                    ScalerDpRx0SetDpcdBitValue(0x00, 0x22, 0x07, ~_BIT6, 0x00);
#endif
                }

                return _TRUE;
            }

            break;
#endif

        default:

            break;
    }

    return _FALSE;
}
#endif
#endif

#if(_DP_TX_SUPPORT == _ON)
#if(_DP_HDCP14_CTS_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check Downstream HDCP Reauth Execute or not
// Input Value  : None
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerSyncDpHdcpDownstreamReAuthCheck(void)
{
#if((_D0_DP_EXIST == _ON) || ((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0)))
    if(GET_DP_RX_HDCP_UPSTREAM_PORT() == _HDCP_D0_PORT)
    {
        // In SST mode
        if(ScalerDpRx0GetDpcdBitInfo(0x00, 0x01, 0x11, _BIT0) == 0x00)
        {
            return ((ScalerDpRx0HdcpCheckValid() == _TRUE) && (ScalerDpRx0HDCPCheckLvp() == _TRUE));
        }
    }
#endif

#if(_D1_DP_EXIST == _ON)
    if(GET_DP_RX_HDCP_UPSTREAM_PORT() == _HDCP_D1_PORT)
    {
        // In SST mode
        if(ScalerDpRx1GetDpcdBitInfo(0x00, 0x01, 0x11, _BIT0) == 0x00)
        {
            return ((ScalerDpRx1HdcpCheckValid() == _TRUE) && (ScalerDpRx1HDCPCheckLvp() == _TRUE));
        }
    }
#endif

    return _FALSE;
}
#endif
#endif

#if(_DP_TX_SUPPORT == _ON)
#if(_DP_HDCP_2_2_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get Upstream HDCP2 event
// Input Value  : None
// Output Value : EnumDpRxHdcp2UpstreamAuthStatus
//--------------------------------------------------
EnumDpRxHdcp2UpstreamAuthStatus ScalerSyncDpHdcp2GetUpstreamEvent(void)
{
#if((_D0_DP_EXIST == _ON) || ((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0)))
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D0_PORT)
    {
        return GET_DP_RX0_HDCP2_UPSTREAM_EVENT();
    }
#endif

#if(_D1_DP_EXIST == _ON)
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D1_PORT)
    {
        return GET_DP_RX1_HDCP2_UPSTREAM_EVENT();
    }
#endif

    return _DP_RX_HDCP2_UPSTREAM_AUTH_EVENT_NONE;
}

//--------------------------------------------------
// Description  : Get Upstream HDCP2 ContentStreamManagementStatus
// Input Value  : None
// Output Value : TRUE or FALSE
//--------------------------------------------------
bit ScalerSyncDpHdcp2GetContentStreamManagementStatus(void)
{
#if((_D0_DP_EXIST == _ON) || ((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0)))
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D0_PORT)
    {
        if(GET_DP_RX0_HDCP2_MODE() == _ENABLE)
        {
            return GET_DP_RX0_HDCP2_CONTENT_STREAM_MANAGEMENT();
        }
        else
        {
            return GET_DP_RX0_HDCP2_HDCP1_CONTENT_STREAM_MANAGEMENT();
        }
    }
#endif

#if(_D1_DP_EXIST == _ON)
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D1_PORT)
    {
        if(GET_DP_RX1_HDCP2_MODE() == _ENABLE)
        {
            return GET_DP_RX1_HDCP2_CONTENT_STREAM_MANAGEMENT();
        }
        else
        {
            return GET_DP_RX1_HDCP2_HDCP1_CONTENT_STREAM_MANAGEMENT();
        }
    }
#endif

    return _FALSE;
}

//--------------------------------------------------
// Description  : Get DP HDCP2.2 Mode Status
// Input Value  : None
// Output Value : TRUE or FALSE
//--------------------------------------------------
bit ScalerSyncDpGetHdcp2ModeStatus(void)
{
#if((_D0_DP_EXIST == _ON) || ((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0)))
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D0_PORT)
    {
        return GET_DP_RX0_HDCP2_MODE();
    }
#endif

#if(_D1_DP_EXIST == _ON)
    if(GET_DP_RX_HDCP2_UPSTREAM_PORT() == _HDCP_D1_PORT)
    {
        return GET_DP_RX1_HDCP2_MODE();
    }
#endif

    return _FALSE;
}

//--------------------------------------------------
// Description  : Change DP HDCP2.2 Repeater Capable Base On DPTX Clone Status
// Input Value  : InputPort, PortType, Clone Mode or not
// Output Value : None
//--------------------------------------------------
void ScalerSyncDpHdcpRepeaterCapableProc(BYTE ucInputPort, BYTE ucPortType)
{
#if(_D0_DP_EXIST == _ON)
    ScalerDpRx0Hdcp2RepeaterCapableProc(ucInputPort, ucPortType);
#endif

#if(_D1_DP_EXIST == _ON)
    ScalerDpRx1Hdcp2RepeaterCapableProc(ucInputPort, ucPortType);
#endif
}
#endif
#endif

#if(_DP_MST_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Dp Rx Fake Power Saving Check
// Input Value  : None
// Output Value : True  --> Fake Power Saving
//                False --> Power Saving
//--------------------------------------------------
bit ScalerSyncDpFakePowerSavingCheck(void)
{
    if(g_enumDpMSTCapablePort != _DP_MST_NO_PORT)
    {
        if(GET_DP_SOURCE_FIRST_POWER_ON() == _TRUE)
        {
            return _TRUE;
        }

        // Source writes 00600h = 0x01, go to fake power saving for 3s.
        if(GET_DP_RX_MST_SOURCE_WRITE_POWER_UP() != _DP_SOURCE_WRITE_POWER_UP_NONE)
        {
            return _TRUE;
        }

        if(GET_DP_CHECK_AUX_CH_POWER_STATUS() == _DP_RX_AUX_POWER_STATUS_OFF)
        {
            return _FALSE;
        }

        if((GET_REG_DP_DPCD_INFO(0x00, 0x01, 0x11) & _BIT0) == _BIT0)
        {
            return _TRUE;
        }

        if(GET_DP_RX_MST_MODE_STATE() != _DP_RX_MST_MODE_STATUS_NONE_MSG)
        {
            return _TRUE;
        }

        // Check if MSG Processing or Stream Propagating
        if((ScalerDpRxMstCheckMsgTransition() == _TRUE) || (GET_REG_DP_DPCD_INFO(0x00, 0x02, 0xC1) != 0))
        {
            return _TRUE;
        }

        return GET_DP_LT_STATUS_CHCEK();
    }

    return _FALSE;
}

//--------------------------------------------------
// Description  : Dp Rx Fake Power Off Check
// Input Value  : enumInputPort
// Output Value : True  --> Fake Power Off
//                False --> Power Off
//--------------------------------------------------
bit ScalerSyncDpFakePowerOffCheck(EnumSourceSearchPort enumInputPort)
{
    CLR_DP_RX_MST_DC_OFF_HPD_TOGGLE_HOLD();

    if(((g_enumDpMSTCapablePort == _DP_MST_RX0_PORT) && (enumInputPort == _D0_INPUT_PORT)) ||
#if((_D6_INPUT_PORT_TYPE == _D6_DP_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
       ((g_enumDpMSTCapablePort == _DP_MST_RX0_PORT) && (enumInputPort == _D6_INPUT_PORT)) ||
#endif
       ((g_enumDpMSTCapablePort == _DP_MST_RX1_PORT) && (enumInputPort == _D1_INPUT_PORT)))
    {
        // Let MSG keep proccessing
        if((GET_REG_DP_DPCD_INFO(0x00, 0x01, 0x11) & _BIT1) == _BIT1)
        {
            // Keep HPD high if upstream is source
            if((GET_REG_DP_DPCD_INFO(0x00, 0x01, 0x11) & _BIT2) == _BIT2)
            {
                // DP Rx MST DC OFF HPD Toggle Not Process
                SET_DP_RX_MST_DC_OFF_HPD_TOGGLE_HOLD();
            }

            return _TRUE;
        }
    }

    return _FALSE;
}

//--------------------------------------------------
// Description  : Check if Event is Valid
// Input Value  : ucEventIndex --> Event to be checked
// Output Value : Validity(_TRUE/_FALSE)
//--------------------------------------------------
void ScalerSyncDpSourceWritePowerUpProc(void)
{
#if(_D0_DP_EXIST == _TRUE)
    if(GET_DP_RX0_SOURCE_WRITE_POWER_UP() == _DP_SOURCE_WRITE_POWER_UP_TRIGGERED)
    {
        DebugMessageRx0("Rx0 Source Writes 600h = 0x01", 0);

        ScalerTimerReactiveTimerEvent(SEC(3), _SCALER_TIMER_EVENT_DP_RX0_SOURCE_WRITE_POWER_UP_TIMEOUT);

        SET_DP_RX0_SOURCE_WRITE_POWER_UP(_DP_SOURCE_WRITE_POWER_UP_TIMER_ACTIVE);
    }
#endif

#if(_D1_DP_EXIST == _TRUE)
    if(GET_DP_RX1_SOURCE_WRITE_POWER_UP() == _DP_SOURCE_WRITE_POWER_UP_TRIGGERED)
    {
        DebugMessageRx1("Rx1 Source Writes 600h = 0x01", 0);

        ScalerTimerReactiveTimerEvent(SEC(3), _SCALER_TIMER_EVENT_DP_RX1_SOURCE_WRITE_POWER_UP_TIMEOUT);

        SET_DP_RX1_SOURCE_WRITE_POWER_UP(_DP_SOURCE_WRITE_POWER_UP_TIMER_ACTIVE);
    }
#endif
}

//--------------------------------------------------
// Description  : Clear Source Write Power Up
// Input Value  : EnumInputPort
// Output Value : None
//--------------------------------------------------
void ScalerSyncDpRxClrSourceWritePowerUp(EnumSourceSearchPort enumInputPort)
{
    switch(enumInputPort)
    {
#if(_D0_INPUT_PORT_TYPE == _D0_DP_PORT)
        case _D0_INPUT_PORT:

            CLR_DP_RX0_SOURCE_WRITE_POWER_UP();

            break;
#endif

#if(_D1_INPUT_PORT_TYPE == _D1_DP_PORT)
        case _D1_INPUT_PORT:

            CLR_DP_RX1_SOURCE_WRITE_POWER_UP();

            break;
#endif

        default:

            break;
    }
}
#endif // End of #if(_DP_MST_SUPPORT == _ON)
