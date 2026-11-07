#if(_AWTO_DBGISR == _ON)
// awto #38: answer 0x3A (XDATA byte) and 0x3C (XDATA block: lo, hi, len, seq) here, FIFO loaded before the SCL release.
// 0x3C reply = len data bytes + checksum (seq + lo + hi + sum of data); the host rejects a stale or garbled reply.
                if(((g_pucDdcciData[0] == 0x3A) && (g_ucDdcciCommandNumber >= 1)) || ((g_pucDdcciData[0] == 0x3C) && (g_ucDdcciCommandNumber == 4)))
                {
                    volatile __xdata BYTE *pucAwtoSrc = (volatile __xdata BYTE *)(((WORD)g_pucDdcciData[2] << 8) | g_pucDdcciData[1]);
                    BYTE ucAwtoLen = 1;
                    BYTE ucAwtoSum = g_pucDdcciData[4] + g_pucDdcciData[1] + g_pucDdcciData[2];
                    BYTE ucAwtoV;

                    if(g_pucDdcciData[0] == 0x3C)
                    {
                        ucAwtoLen = (g_pucDdcciData[3] > _AWTO_DBGISR_BLK_MAX) ? _AWTO_DBGISR_BLK_MAX : g_pucDdcciData[3];
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
                    if(g_pucDdcciData[0] == 0x3C)
                    {
                        MCU_FF26_IIC_DATA_OUT = ucAwtoSum;
                    }
                    MCU_FF2A_IIC_IRQ_CONTROL2 &= (~_BIT5);
                    g_ucDdcciCommandNumber = 0;
                    DELAY_30US_EXINT();
#if(_AWTO_DBG_FOLLOW == _ON)
                    AWTO_DBG_SCL(&= ~_BIT0);
#elif(_DEBUG_DDC_CHANNEL_SEL == _DDC2)
                    MCU_FE66_DDC2_DDC_CONTROL_2 &= ~_BIT0;
#else
#error _AWTO_DBGISR: SCL release only written for _DDC2
#endif
                    return;
                }
#endif
