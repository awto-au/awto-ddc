#if(_AWTO_DBG_FOLLOW == _ON)
// #28: debug IIC engine follows the active port (SDK: fixed _DEBUG_DDC_CHANNEL_SEL). Called from ScalerMcuDdcciSwitchPort's debug branch.
// #79 runtime swap (_AWTO_DBG_SWAP): the active port's DDC belongs to DDC/CI (IIC_1, 0x37) unless g_ucAwtoDbgLink != 0;
// the other engine is parked on AWTO_DBG_PARK_CH (DDC0). Never both on one channel (kvm1: both NAK), so park first, then move.
#if(_AWTO_DBG_SWAP == _ON)
__xdata BYTE g_ucAwtoDbgLink;               // 0 = DDC/CI on the active port (default), 1 = debug slave 0x35 there
__xdata WORD g_usAwtoDbgLinkSec;            // debug link seconds left (0 = until told back)
__xdata BYTE g_ucAwtoDdcciCh = AWTO_DBG_PARK_CH;    // IIC_1 channel wanted (fw/sdcc/awto_ddcci.inc re-inits with it)
static __xdata BYTE s_ucAwtoDbgPort = _D2_INPUT_PORT;
#endif

static void AwtoDbgSetFF22(BYTE ucCh)
{
    BYTE ucIrq;

    if((MCU_FF22_IIC_CH_SEL & 0x07) == ucCh)
    {
        return;
    }
    ucIrq = MCU_FF28_IIC_IRQ_CONTROL;
    MCU_FF28_IIC_IRQ_CONTROL &= ~(_BIT4 | _BIT2 | _BIT1);
    // a SCL hold on the old channel would wedge its DDC (EDID): release all, AWTO_DBG_SCL only reaches the current one
    MCU_FF20_DDC0_DDC_CONTROL_2 &= ~_BIT0;
    MCU_FF2E_DDC1_DDC_CONTROL_2 &= ~_BIT0;
    MCU_FE66_DDC2_DDC_CONTROL_2 &= ~_BIT0;
    MCU_FE6F_DDC3_DDC_CONTROL_2 &= ~_BIT0;
    MCU_FF22_IIC_CH_SEL = (MCU_FF22_IIC_CH_SEL & ~(_BIT2 | _BIT1 | _BIT0)) | ucCh;
    MCU_FF27_IIC_STATUS = 0x00;
    MCU_FF2A_IIC_IRQ_CONTROL2 |= _BIT6;     // reset the IIC data FIFO, as the SDK's mode change
    MCU_FF2A_IIC_IRQ_CONTROL2 &= ~_BIT6;
    MCU_FF28_IIC_IRQ_CONTROL = ucIrq;
}

static void AwtoDbgSelectChannel(BYTE ucInputPort)
{
    BYTE ucCh = 0x03;                       // DDC2 (_PCB_DEBUG_DDC) for ports without their own DDC
#if((_AWTO_DBG_SWAP == _ON) && (_AWTO_DDCCI_ENGINES == 3))
    BYTE ucOldPort = s_ucAwtoDbgPort;
    BYTE ucDbgIrq;
    BYTE ucDbgSlave;
#endif

    if(ucInputPort == _D1_INPUT_PORT)
    {
        ucCh = 0x02;                        // DDC1 = DP AUX I2C
    }
    else if(ucInputPort == _D3_INPUT_PORT)
    {
        ucCh = 0x04;
    }
#if(_AWTO_DBG_SWAP == _ON)
    s_ucAwtoDbgPort = ucInputPort;
#if(_AWTO_DDCCI_ENGINES == 3)
    // These IIC engines cannot share one physical DDC channel: both stop answering.  Normally the
    // three spare engines own DDC1..3 and debug is parked on unconnected DDC0.  For a debug session,
    // restore the old port and park only the listener belonging to the new active debug port.
    // Disable the debug slave for the entire route change.  Without this, moving debug through DDC0
    // briefly overlaps the parked spare engine there and wedges both engines even after they separate.
    ucDbgIrq = MCU_FF28_IIC_IRQ_CONTROL;
    ucDbgSlave = MCU_FF23_IIC_SET_SLAVE;
    MCU_FF28_IIC_IRQ_CONTROL &= ~(_BIT4 | _BIT2 | _BIT1);
    MCU_FF23_IIC_SET_SLAVE = 0x3D;
    AwtoDbgSetFF22(AWTO_DBG_PARK_CH);
    AwtoDdcciDebugLink(ucOldPort, 0);
    if((g_ucAwtoDbgLink == 0) && AWTO_DDCCI_POLL_ON())
    {
        AwtoDdcciDebugLink(ucInputPort, 0);
    }
    else
    {
        AwtoDdcciDebugLink(ucInputPort, 1);
        AwtoDbgSetFF22(ucCh);
    }
    MCU_FF27_IIC_STATUS = 0x00;
    MCU_FF2A_IIC_IRQ_CONTROL2 |= _BIT6;
    MCU_FF2A_IIC_IRQ_CONTROL2 &= ~_BIT6;
    MCU_FF23_IIC_SET_SLAVE = ucDbgSlave;
    MCU_FF28_IIC_IRQ_CONTROL = ucDbgIrq;
#else
    if((g_ucAwtoDbgLink == 0) && AWTO_DDCCI_POLL_ON())     // #67 DDC/CI row off: the debug slave keeps the port
    {
        AwtoDbgSetFF22(AWTO_DBG_PARK_CH);   // debug engine off the port first
        g_ucAwtoDdcciCh = ucCh;
        AWTO_XB(AWTO_R_IIC_1_CH_SEL) = (AWTO_XB(AWTO_R_IIC_1_CH_SEL) & ~AWTO_F_IIC_1_CH_SEL_IIC_1_CH_SEL) | ucCh;      // IIC_1 CH_SEL
    }
    else
    {
        g_ucAwtoDdcciCh = AWTO_DBG_PARK_CH;
        AWTO_XB(AWTO_R_IIC_1_CH_SEL) = (AWTO_XB(AWTO_R_IIC_1_CH_SEL) & ~AWTO_F_IIC_1_CH_SEL_IIC_1_CH_SEL) | AWTO_DBG_PARK_CH;
        AwtoDbgSetFF22(ucCh);
    }
#endif
#else
    AWTO_DDCCI_FOLLOW(ucCh);                // #60: DDC/CI engine IIC_1 on the same channel (_AWTO_DDCCI_ENGINES == 1)
    AwtoDbgSetFF22(ucCh);
#endif
}

#if(_AWTO_DBG_SWAP == _ON)
void AwtoDbgLinkSet(BYTE ucMin)             // main-loop context. 0 = back to DDC/CI; 0xFF = debug link until told back
{
    g_ucAwtoDbgLink = (ucMin != 0);
    g_usAwtoDbgLinkSec = (ucMin == 0xFF) ? 0 : (WORD)ucMin * 60;
    AwtoDbgSelectChannel(s_ucAwtoDbgPort);
}
#endif
#endif
