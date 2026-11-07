// #67 DDC/CI hooks (integrator-owned, private): VCP get/set reach the settings registry first (awto-rtdfw vcp.c).
// Inserted into RTD2014Ddcci.c by fw/awto/settings/rules.py. Runs only while DDC/CI is on (Debug link off).
#ifdef _AWTO_NEW_SETTINGS
extern BYTE vcp_get(BYTE ucCode, WORD xdata *pusCur, WORD xdata *pusMax, BYTE xdata *pucType);
extern BYTE vcp_set(BYTE ucCode, WORD usV);

static __xdata WORD s_usAwtoVcpCur;
static __xdata WORD s_usAwtoVcpMax;
static __xdata BYTE s_ucAwtoVcpType;

bit AwtoVcpGetHook(void)                           // RTDDdcciGetVCPFeature: _TRUE = our row answered
{
    if(vcp_get(g_pucDdcciRxBuf[_DDCCI_SOURCE_OPCODE], &s_usAwtoVcpCur, &s_usAwtoVcpMax, &s_ucAwtoVcpType) == 0)
    {
        return _FALSE;
    }
    UserCommonDdcciSetVCPReplyValue((s_ucAwtoVcpType != 0) ? _DDCCI_CMD_GETVCP_TP_MOMENTARY : _DDCCI_CMD_GETVCP_TP_SET_PARAMETER,
                                    s_usAwtoVcpMax, s_usAwtoVcpCur);
    return _TRUE;
}

bit AwtoVcpSetHook(void)                           // RTDDdcciSetVCPFeature: _TRUE = our row took it
{
    BYTE ucCode = g_pucDdcciRxBuf[_DDCCI_SOURCE_OPCODE];

    if(ucCode == _DDCCI_OPCODE_VCP_FACTORY_RESET)
    {
        RTDDdcciResetAllSettings();                // the vendor's own records first, then every registry row
    }
    return vcp_set(ucCode, ((WORD)g_pucDdcciRxBuf[_DDCCI_SET_HIGH_BYTE] << 8) | g_pucDdcciRxBuf[_DDCCI_SET_LOW_BYTE]);
}
#endif
