#include "UserCommonInclude.h"

#if(_AWTO_WDT == _ON)

// Health monitor (docs/monitoring.md): every AWTO_MON_MS (called from AwtoDiagMainPass) the slow values go into g_stAwtoMon and,
// as decoded sync rows, a changed one at once and all of them every AWTO_MON_BEAT_K samples. Read-only: no register is written.
// Registry row monitor off = nothing sampled.
__xdata StAwtoMon g_stAwtoMon;
static __xdata BYTE s_ucMonBeat;                // samples since the last heartbeat (0 = this one is a heartbeat)
static __xdata BYTE s_pucMonAdc[4];             // last logged
static __xdata WORD s_usMonTrim;
static __xdata BYTE s_ucMonPoke;
static __xdata BYTE s_ucMonStack;

static BYTE AwtoMonMoved(BYTE ucA, BYTE ucB, BYTE ucStep)
{
    return (((ucA > ucB) ? (ucA - ucB) : (ucB - ucA)) >= ucStep) ? 1 : 0;
}

void AwtoMonSample(void)
{
    BYTE ucI;
    BYTE ucBeat;
    BYTE ucAdc = 0;
    WORD usTrim;
    WORD usLoop;
    DWORD ulUp;
    BYTE ucLog;

    if(g_stAwtoMon.ucMagic0 != 'M')
    {
        for(ucI = 0; ucI < sizeof(StAwtoMon); ucI++)
        {
            ((BYTE __xdata *)&g_stAwtoMon)[ucI] = 0;
        }
        g_stAwtoMon.ucMagic0 = 'M';
        g_stAwtoMon.ucMagic1 = 'N';
        g_stAwtoMon.ucVersion = 1;
    }
    g_stAwtoMon.ucOn = (AWTO_SET(MONITOR) != 0) ? 1 : 0;
    if(g_stAwtoMon.ucOn == 0)
    {
        s_ucMonBeat = 0;                        // switched on again: the first sample is a heartbeat
        return;
    }
    g_stAwtoMon.pucAdc[0] = PCB_ADKEY1();
    g_stAwtoMon.pucAdc[1] = PCB_ADKEY2();
    g_stAwtoMon.pucAdc[2] = MCU_FF0B_ADC_A2_CONVERT_RESULT;
    g_stAwtoMon.pucAdc[3] = MCU_FF0C_ADC_A3_CONVERT_RESULT;
    usTrim = ((WORD)(ScalerGetByte(AWTO_R_EMB_BGRES) & AWTO_F_EMB_BGRES_TRIM_CNT_H) << 4) | ScalerGetByte(AWTO_R_OSC_TRIM_CNT);
    g_stAwtoMon.ucTrimHi = (BYTE)(usTrim >> 8);
    g_stAwtoMon.ucTrimLo = (BYTE)usTrim;
    usLoop = isr_g_stAwtoDiag.usLoopRate;
    g_stAwtoMon.ucLoopHi = (BYTE)(usLoop >> 8);
    g_stAwtoMon.ucLoopLo = (BYTE)usLoop;
    g_stAwtoMon.ucMaxPoke = isr_g_stAwtoWdt.ucMaxPoke;
    g_stAwtoMon.ucPokeSite = g_ucAwtoPokeSite;
    g_stAwtoMon.ucStack = g_ucAwtoStackHigh;
    g_stAwtoMon.ucBoot = AwtoBootReason();
    ulUp = AwtoMs() / 1000;
    g_stAwtoMon.pucUp[0] = (BYTE)(ulUp >> 16);
    g_stAwtoMon.pucUp[1] = (BYTE)(ulUp >> 8);
    g_stAwtoMon.pucUp[2] = (BYTE)ulUp;
    g_stAwtoMon.ucBeat++;
    ucBeat = (s_ucMonBeat == 0) ? 1 : 0;
    s_ucMonBeat = (s_ucMonBeat + 1 >= AWTO_MON_BEAT_K) ? 0 : s_ucMonBeat + 1;
    if((SysPowerGetPowerStatus() == _POWER_STATUS_SAVING) && (g_stAwtoGpio.ucOpen != 0))
    {
        return;                                 // a sync row redraws the open console: no OSD drawing in power saving
    }
    for(ucI = 0; ucI < 4; ucI++)
    {
        ucAdc |= AwtoMonMoved(g_stAwtoMon.pucAdc[ucI], s_pucMonAdc[ucI], AWTO_MON_ADC_STEP);
    }
    ucLog = 0;
    if((ucBeat != 0) || (ucAdc != 0))
    {
        for(ucI = 0; ucI < 4; ucI++)
        {
            s_pucMonAdc[ucI] = g_stAwtoMon.pucAdc[ucI];
        }
        AwtoSyncPush(AWTO_SYNC_EV_MON, AWTO_MON_EV_ADC, ((DWORD)g_stAwtoMon.pucAdc[0] << 24) | ((DWORD)g_stAwtoMon.pucAdc[1] << 16) |
                     ((WORD)g_stAwtoMon.pucAdc[2] << 8) | g_stAwtoMon.pucAdc[3]);
        ucLog++;
    }
    if((ucBeat != 0) || ((usTrim > s_usMonTrim) ? ((usTrim - s_usMonTrim) >= AWTO_MON_TRIM_STEP) : ((s_usMonTrim - usTrim) >= AWTO_MON_TRIM_STEP)))
    {
        s_usMonTrim = usTrim;
        AwtoSyncPush(AWTO_SYNC_EV_MON, AWTO_MON_EV_TRIM, usTrim);
        ucLog++;
    }
    if((ucBeat != 0) || (g_stAwtoMon.ucMaxPoke != s_ucMonPoke))
    {
        s_ucMonPoke = g_stAwtoMon.ucMaxPoke;
        AwtoSyncPush(AWTO_SYNC_EV_MON, AWTO_MON_EV_LOOP, ((DWORD)usLoop << 16) | (((WORD)g_stAwtoMon.ucMaxPoke * 293) >> 6));
        ucLog++;
    }
    if((ucBeat != 0) || (g_stAwtoMon.ucStack != s_ucMonStack))
    {
        s_ucMonStack = g_stAwtoMon.ucStack;
        AwtoSyncPush(AWTO_SYNC_EV_MON, AWTO_MON_EV_UP, (ulUp << 8) | g_stAwtoMon.ucStack);
        ucLog++;
    }
    AWTO_MON_FLASH_CHECK(ucBeat);
    g_stAwtoMon.ucRows = (g_stAwtoMon.ucRows > 255 - ucLog) ? 255 : g_stAwtoMon.ucRows + ucLog;
}
#endif
