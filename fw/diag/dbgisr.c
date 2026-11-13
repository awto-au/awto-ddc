#include "ScalerCommonFunctionInclude.h"

#if(_AWTO_DBGISR == _ON)
// awto #38: answer 0x3A (XDATA byte) and 0x3C (XDATA block: lo, hi, len, seq) here, FIFO loaded before the SCL release.
// 0x3C reply = len data bytes + checksum (seq + lo + hi + sum of data); the host rejects a stale or garbled reply.
// #28: the write staging 0x01 [hi] / 0x03 [val] and the write 0x3B [lo] are done here too, so SCL is held ~30 us, not until
// the next main-loop pass: NVIDIA's I2C engine fails the next START (EIO) while SCL is still held (unit 1, 0x3B after 0x03).
// EXINT1 context (ScalerDebugIntProc_EXINT1, after the data read). _TRUE = answered, SCL released: the caller returns.
bit AwtoDbgIsrCmd_EXINT1(void)
{
    if(((isr_g_pucDdcciData[0] == 0x01) || (isr_g_pucDdcciData[0] == 0x03) || (isr_g_pucDdcciData[0] == 0x3B)) && (isr_g_ucDdcciCommandNumber == 1))
    {
        if(isr_g_pucDdcciData[0] == 0x01)
        {
            isr_g_pucDdcciData[2] = isr_g_pucDdcciData[1];
        }
        else if(isr_g_pucDdcciData[0] == 0x03)
        {
            isr_g_pucDdcciData[3] = isr_g_pucDdcciData[1];
        }
        else
        {
            *((volatile __xdata BYTE *)(((WORD)isr_g_pucDdcciData[2] << 8) | isr_g_pucDdcciData[1])) = isr_g_pucDdcciData[3];
        }
        isr_g_ucDdcciCommandNumber = 0;
        DELAY_30US_EXINT();
#if(_AWTO_DBG_FOLLOW == _ON)
        AWTO_DBG_SCL(&= ~_BIT0);
#else
        MCU_FE66_DDC2_DDC_CONTROL_2 &= ~_BIT0;
#endif
        return _TRUE;
    }
#if(_AWTO_NET == _ON)
    // #80 Transport B: write 0x3D [seq ctl ack data[n] chk] -> FIFO [seq flags rxfree m data[20] chk], fixed 25 B;
    // chk = 0x3D + sum of the bytes before it. A repeated seq re-sends the reply and applies nothing (host retry).
    if((isr_g_pucDdcciData[0] == 0x3D) && (isr_g_ucDdcciCommandNumber >= 4))
    {
        BYTE ucAwtoK = isr_g_ucDdcciCommandNumber;
        BYTE ucAwtoI;
        BYTE ucAwtoS = 0x3D;
        BYTE ucAwtoF = 0;
        BYTE ucAwtoM;

        for(ucAwtoI = 1; ucAwtoI < ucAwtoK; ucAwtoI++)
        {
            ucAwtoS += isr_g_pucDdcciData[ucAwtoI];
        }
        if(ucAwtoS != isr_g_pucDdcciData[ucAwtoK])
        {
            ucAwtoF = AWTO_NET_F_BAD;
        }
        else if(isr_g_pucDdcciData[1] == g_stAwtoNet.ucBSeq)
        {
            ucAwtoF = g_stAwtoNet.ucBFlags;
        }
        else if(g_stAwtoNet.ucReset == 0)
        {
            ucAwtoM = g_stAwtoNet.ucTxHead - g_stAwtoNet.ucTxTail;
            g_stAwtoNet.ucTxTail += (isr_g_pucDdcciData[3] < ucAwtoM) ? isr_g_pucDdcciData[3] : ucAwtoM;
            ucAwtoM = AWTO_NET_RING - (BYTE)(g_stAwtoNet.ucRxHead - g_stAwtoNet.ucRxTail);
            ucAwtoK -= 4;
            if((isr_g_pucDdcciData[2] & AWTO_NET_CTL_RESET) != 0)
            {
                g_stAwtoNet.ucReset = 1;
            }
            else if(ucAwtoK <= ucAwtoM)
            {
                for(ucAwtoI = 0; ucAwtoI < ucAwtoK; ucAwtoI++)
                {
                    g_stAwtoNet.pucRx[(BYTE)(g_stAwtoNet.ucRxHead + ucAwtoI) & AWTO_NET_MASK] = isr_g_pucDdcciData[4 + ucAwtoI];
                }
                g_stAwtoNet.ucRxHead += ucAwtoK;
                ucAwtoF = AWTO_NET_F_ACC;
            }
            else
            {
                ucAwtoF = AWTO_NET_F_FULL;
            }
            g_stAwtoNet.ucCtl = isr_g_pucDdcciData[2] & ~AWTO_NET_CTL_RESET;
            g_stAwtoNet.ucBSeq = isr_g_pucDdcciData[1];
            g_stAwtoNet.ucBFlags = ucAwtoF;
        }
        g_ucAwtoNetRun = 1;
        ucAwtoM = (g_stAwtoNet.ucReset != 0) ? 0 : (BYTE)(g_stAwtoNet.ucTxHead - g_stAwtoNet.ucTxTail);
        ucAwtoF |= AWTO_NET_F_UP | ((g_stAwtoNet.ucReset != 0) ? AWTO_NET_F_RESET : 0) |
                   (((g_stAwtoNet.ucCtl & AWTO_NET_CTL_ECHO) != 0) ? AWTO_NET_F_ECHO : 0);
        if(ucAwtoM > AWTO_NET_B_MAX)
        {
            ucAwtoM = AWTO_NET_B_MAX;
            ucAwtoF |= AWTO_NET_F_MORE;
        }
        MCU_FF2A_IIC_IRQ_CONTROL2 |= (_BIT6 | _BIT5);
        MCU_FF2A_IIC_IRQ_CONTROL2 &= (~_BIT6);
        ucAwtoK = AWTO_NET_RING - (BYTE)(g_stAwtoNet.ucRxHead - g_stAwtoNet.ucRxTail);
        ucAwtoS = 0x3D + isr_g_pucDdcciData[1] + ucAwtoF + ucAwtoK + ucAwtoM;
        MCU_FF26_IIC_DATA_OUT = isr_g_pucDdcciData[1];
        MCU_FF26_IIC_DATA_OUT = ucAwtoF;
        MCU_FF26_IIC_DATA_OUT = ucAwtoK;
        MCU_FF26_IIC_DATA_OUT = ucAwtoM;
        for(ucAwtoI = 0; ucAwtoI < AWTO_NET_B_MAX; ucAwtoI++)
        {
            ucAwtoK = (ucAwtoI < ucAwtoM) ? g_stAwtoNet.pucTx[(BYTE)(g_stAwtoNet.ucTxTail + ucAwtoI) & AWTO_NET_MASK] : 0;
            ucAwtoS += ucAwtoK;
            MCU_FF26_IIC_DATA_OUT = ucAwtoK;
        }
        MCU_FF26_IIC_DATA_OUT = ucAwtoS;
        MCU_FF2A_IIC_IRQ_CONTROL2 &= (~_BIT5);
        isr_g_ucDdcciCommandNumber = 0;
        DELAY_30US_EXINT();
#if(_AWTO_DBG_FOLLOW == _ON)
        AWTO_DBG_SCL(&= ~_BIT0);
#elif(_DEBUG_DDC_CHANNEL_SEL == _DDC2)
        MCU_FE66_DDC2_DDC_CONTROL_2 &= ~_BIT0;
#else
#error _AWTO_NET: SCL release only written for _DDC2
#endif
        return _TRUE;
    }
#endif
    if(((isr_g_pucDdcciData[0] == 0x3A) && (isr_g_ucDdcciCommandNumber >= 1)) || ((isr_g_pucDdcciData[0] == 0x3C) && (isr_g_ucDdcciCommandNumber == 4)))
    {
        volatile __xdata BYTE *pucAwtoSrc = (volatile __xdata BYTE *)(((WORD)isr_g_pucDdcciData[2] << 8) | isr_g_pucDdcciData[1]);
        BYTE ucAwtoLen = 1;
        BYTE ucAwtoSum = isr_g_pucDdcciData[4] + isr_g_pucDdcciData[1] + isr_g_pucDdcciData[2];
        BYTE ucAwtoV;

        if(isr_g_pucDdcciData[0] == 0x3C)
        {
            ucAwtoLen = (isr_g_pucDdcciData[3] > _AWTO_DBGISR_BLK_MAX) ? _AWTO_DBGISR_BLK_MAX : isr_g_pucDdcciData[3];
        }
        MCU_FF2A_IIC_IRQ_CONTROL2 |= (_BIT6 | _BIT5);
        MCU_FF2A_IIC_IRQ_CONTROL2 &= (~_BIT6);
        while((ucAwtoLen != 0) && ((MCU_FF29_IIC_STATUS2 & _BIT2) == 0))
        {
            ucAwtoV = *pucAwtoSrc++;
            ucAwtoSum += ucAwtoV;
            MCU_FF26_IIC_DATA_OUT = ucAwtoV;
            ucAwtoLen--;
        }
        if(isr_g_pucDdcciData[0] == 0x3C)
        {
            MCU_FF26_IIC_DATA_OUT = ucAwtoSum;
        }
        MCU_FF2A_IIC_IRQ_CONTROL2 &= (~_BIT5);
        isr_g_ucDdcciCommandNumber = 0;
        DELAY_30US_EXINT();
#if(_AWTO_DBG_FOLLOW == _ON)
        AWTO_DBG_SCL(&= ~_BIT0);
#elif(_DEBUG_DDC_CHANNEL_SEL == _DDC2)
        MCU_FE66_DDC2_DDC_CONTROL_2 &= ~_BIT0;
#else
#error _AWTO_DBGISR: SCL release only written for _DDC2
#endif
        return _TRUE;
    }
    return _FALSE;
}
#endif
