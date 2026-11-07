#if(_AWTO_DBG_FOLLOW == _ON)
// #28: debug IIC engine follows the active port (SDK: fixed _DEBUG_DDC_CHANNEL_SEL). Called from ScalerMcuDdcciSwitchPort's debug branch.
static void AwtoDbgSelectChannel(BYTE ucInputPort)
{
    BYTE ucCh = 0x03;                       // DDC2 (_PCB_DEBUG_DDC) for ports without their own DDC
    BYTE ucIrq;

    if(ucInputPort == _D1_INPUT_PORT)
    {
        ucCh = 0x02;                        // DDC1 = DP AUX I2C
    }
    else if(ucInputPort == _D3_INPUT_PORT)
    {
        ucCh = 0x04;
    }
    AWTO_DDCCI_FOLLOW(ucCh);                // #60: DDC/CI engine IIC_1 on the same channel (_AWTO_DDCCI_ENGINES == 1)
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
#endif
