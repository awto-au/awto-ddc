// awto-ddc#26/#56: cheap debug-message entry points, #included into ScalerCommonDebug.c by keil2sdcc (INSERTS).
// Every message goes into a 40-entry ring first (never blocks); the host channel (wire format {0x01,id_hi,id_lo,0})
// is used only while the host has it enabled, and a host that stops reading is dropped after AWTO_MSG_HOST_MS.
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
#define AWTO_MSG_HOST_MS    100     // host-silence limit: poll gap 2 ms + one fetch ~5 ms, x20; expiry = channel off, message stays in ring

static unsigned char __xdata g_pucAwtoMsgBuf[4];
static unsigned int s_usAwtoMsgT0;
__xdata StAwtoMsg g_pstAwtoMsgRing[AWTO_MSG_RING];
__xdata unsigned char g_ucAwtoMsgHead;      // next slot to write = oldest entry once wrapped
__xdata unsigned int g_usAwtoMsgSeq;        // messages since boot (wraps): the overlay redraws when it changed
__xdata unsigned char g_ucAwtoMsgLog;       // test cmd 0x22/0x23: on-screen log requested (#56)
__xdata unsigned char g_ucAwtoMsgOn;        // #74: 0 (reset value) = messages off; test cmd 0x28/0x29, NVRAM

// Called from the host-wait loop of ScalerDebugMessage (keil2sdcc rule): 0 = give up waiting.
unsigned char AwtoMsgWait(void)
{
    AWTO_WDT_FEED(AWTO_WDT_S_MSG);          // bounded wait: AWTO_MSG_HOST_MS per message (#131)
    if((unsigned int)((WORD)AwtoMs() - s_usAwtoMsgT0) >= AWTO_MSG_HOST_MS)
    {
        g_bDebugMessageEven = _FALSE;       // host re-arms with 0x55 (rtd_diag resends it while idle)
        g_pucDdcciData[0] = 0;              // a stale 0x55 would re-enable it at the next message
        g_bDebugMessageStart = 0;
        return 0;
    }
    return 1;
}

void AwtoMsgV(unsigned int usId, unsigned long ulValue)
{
    if(g_ucAwtoMsgOn == 0)
    {
        return;                             // #74: off = no ring, no host channel
    }
    g_pstAwtoMsgRing[g_ucAwtoMsgHead].usId = usId;
    g_pstAwtoMsgRing[g_ucAwtoMsgHead].ulValue = ulValue;
    g_ucAwtoMsgHead = (g_ucAwtoMsgHead + 1 >= AWTO_MSG_RING) ? 0 : g_ucAwtoMsgHead + 1;
    g_usAwtoMsgSeq++;
    if((g_bDebugMessageEven == _FALSE) && (g_pucDdcciData[0] != 0x55))
    {
        return;                             // host channel off: no bus access, no wait
    }
    g_pucAwtoMsgBuf[0] = 0x01;
    g_pucAwtoMsgBuf[1] = usId >> 8;
    g_pucAwtoMsgBuf[2] = usId;
    g_pucAwtoMsgBuf[3] = 0;
    s_usAwtoMsgT0 = (WORD)AwtoMs();
    ScalerDebugMessage(g_pucAwtoMsgBuf, ulValue);
}

void AwtoMsg0(unsigned int usId)
{
    AwtoMsgV(usId, 0);
}
#endif
