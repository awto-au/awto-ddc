// awto-ddc#26: cheap debug-message entry points, #included into ScalerCommonDebug.c by keil2sdcc (INSERTS).
// Builds the 4-byte token {0x01, id_hi, id_lo, 0} in XDATA and forwards to ScalerDebugMessage (wire format unchanged).
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
static unsigned char __xdata g_pucAwtoMsgBuf[4];

void AwtoMsgV(unsigned int usId, unsigned long ulValue)
{
    g_pucAwtoMsgBuf[0] = 0x01;
    g_pucAwtoMsgBuf[1] = usId >> 8;
    g_pucAwtoMsgBuf[2] = usId;
    g_pucAwtoMsgBuf[3] = 0;
    ScalerDebugMessage(g_pucAwtoMsgBuf, ulValue);
}

void AwtoMsg0(unsigned int usId)
{
    AwtoMsgV(usId, 0);
}
#endif
