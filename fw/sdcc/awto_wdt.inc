// Watchdog + crash canary (#131, docs/watchdog.md), inserted into SysMain.c (fw/awto/wdt/rules.py). Record: RL6449_Project.h StAwtoWdt.
#if(_AWTO_WDT == _ON)
#define AWTO_P0_01_HOST_CTRL    0x0001          // regdb P0_01 HOST_CTRL (scaler register names are not visible in SysMain.c)
bit AwtoWdtValid(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI];
    }
    return (g_stAwtoWdt.ucMagic0 == 'W') && (g_stAwtoWdt.ucMagic1 == 'D') && (g_stAwtoWdt.ucVersion == 1) && (g_stAwtoWdt.ucCheck == ucS);
}

static void AwtoWdtSeal(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI];
    }
    g_stAwtoWdt.ucCheck = ucS;
}

static void AwtoWdtFresh(void)                  // empty record: cold RAM, a host clear, or another layout
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI] = 0;
    }
    g_stAwtoWdt.ucMagic0 = 'W';
    g_stAwtoWdt.ucMagic1 = 'D';
    g_stAwtoWdt.ucVersion = 1;
}

// Once per reset, before EA: classify the boot, keep the record, reset the live counters.
void AwtoWdtInit(void)
{
    BYTE ucOld = g_stAwtoWdt.ucBoot;
    BYTE ucNew = ((ScalerGetByte(AWTO_P0_01_HOST_CTRL) & _BIT6) == 0) ? AWTO_WDT_B_LVR : 0;

    ScalerSetBit(AWTO_P0_01_HOST_CTRL, ~(_BIT6 | _BIT0), _BIT6);   // reset_chk: an LVR clears it (regdb P0_01[6])
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
        ucOld = 0;
    }
    if((ucOld & AWTO_WDT_B_BITE) != 0)
    {
        ucNew |= AWTO_WDT_B_NEW;
    }
    else if(ucNew == 0)
    {
        ucNew |= AWTO_WDT_B_WARM;
        if(g_stAwtoWdt.ucWarm != 0xFF)
        {
            g_stAwtoWdt.ucWarm++;
        }
    }
    ucNew |= ucOld & AWTO_WDT_B_NEW;            // not yet shown: keep it over another reset
    AwtoWdtSeal();
    g_stAwtoWdt.ucBoot = ucNew;
    g_stAwtoWdt.ucFeed = 0;
    g_stAwtoWdt.ucPass = 0;
    g_stAwtoWdt.ucMaxFeed = 0;
    g_stAwtoWdt.ucMaxPass = 0;
    g_stAwtoWdt.ucTick = AWTO_WDT_CHECK_MS;
}

// Timer2 ISR context; never returns. Frame at entry: SP0 + 1 PCL, + 2 PCH, then SysTimerIntProc2's pushes (acc, psw, r7..r0, bits, dpl, dph, b).
static void AwtoWdtBite(BYTE ucSp, BYTE ucBank, BYTE ucCause)
{
    __idata BYTE *pucF = (__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME);

    EA = 0;
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
    }
    g_stAwtoWdt.ucCause = ucCause | (((g_stAwtoWdt.ucBoot & AWTO_WDT_B_TEST) != 0) ? AWTO_WDT_C_TEST : 0);
    if(g_stAwtoWdt.ucBites != 0xFF)
    {
        g_stAwtoWdt.ucBites++;
    }
    g_stAwtoWdt.ucPcHi = pucF[2];
    g_stAwtoWdt.ucPcLo = pucF[1];
    g_stAwtoWdt.ucBank = ucBank;
    g_stAwtoWdt.ucSp = (BYTE)(ucSp - AWTO_WDT_FRAME);
    g_stAwtoWdt.ucAcc = pucF[3];
    g_stAwtoWdt.ucPsw = pucF[4];
    g_stAwtoWdt.ucDpl = pucF[14];
    g_stAwtoWdt.ucDph = pucF[15];
    g_stAwtoWdt.ucB = pucF[16];
    g_stAwtoWdt.ucRetHi = pucF[0];
    g_stAwtoWdt.ucRetLo = *(__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME - 1);
    g_stAwtoWdt.ucStage = g_stAwtoDiag.ucStage;
    g_stAwtoWdt.ucMode = GET_MODE_STATE();
    g_stAwtoWdt.ucHbHi = (BYTE)(g_stAwtoDiag.usHeartbeat >> 8);
    g_stAwtoWdt.ucHbLo = (BYTE)g_stAwtoDiag.usHeartbeat;
    g_stAwtoWdt.ucUpHi = (BYTE)(g_usTimerCounter >> 8);
    g_stAwtoWdt.ucUpLo = (BYTE)g_usTimerCounter;
    g_stAwtoWdt.ucFeedAge = g_stAwtoWdt.ucFeed;
    g_stAwtoWdt.ucPassAge = g_stAwtoWdt.ucPass;
    AwtoWdtSeal();
    g_stAwtoWdt.ucBoot |= AWTO_WDT_B_BITE;
    // backstop if sof_rst does not reset: WDT normal mode, no IRQ, CNT1 = 1 -> reset after one CNT3 period (regdb FFEA/FFEB)
    MCU_FFEB_WDT_TEST = MCU_FFEB_WDT_TEST & ~(_BIT7 | _BIT4 | _BIT2);
    MCU_FFEA_WATCHDOG_TIMER = (MCU_FFEA_WATCHDOG_TIMER & ~(_BIT2 | _BIT1 | _BIT0)) | _BIT7 | _BIT6;
    MCU_FFEE_MCU_CLOCK_CONTROL |= _BIT1;          // sof_rst: chip reset, as the host's ISP 0xEE <- 0x02
    while(_TRUE)
    {
    }
}

void AwtoWdtCheck(BYTE ucSp, BYTE ucBank)       // AWTO_WDT_T2ISR every AWTO_WDT_CHECK_MS; ucSp = SP after the ISR prologue
{
    BYTE ucCause = 0;

    g_stAwtoWdt.ucTick = AWTO_WDT_CHECK_MS;
    if(g_stAwtoWdt.ucFeed != 0xFF)
    {
        g_stAwtoWdt.ucFeed++;
    }
    if(g_stAwtoWdt.ucPass != 0xFF)
    {
        g_stAwtoWdt.ucPass++;
    }
    if(g_stAwtoWdt.ucFeed > g_stAwtoWdt.ucMaxFeed)
    {
        g_stAwtoWdt.ucMaxFeed = g_stAwtoWdt.ucFeed;
    }
    if(g_stAwtoWdt.ucPass > g_stAwtoWdt.ucMaxPass)
    {
        g_stAwtoWdt.ucMaxPass = g_stAwtoWdt.ucPass;
    }
    if(g_stAwtoWdt.ucFeed >= AWTO_WDT_FEED_CHECKS)
    {
        ucCause = AWTO_WDT_C_STALL;
    }
    else if(g_stAwtoWdt.ucPass >= AWTO_WDT_PASS_CHECKS)
    {
        ucCause = AWTO_WDT_C_PASS;
    }
    if(ucCause != 0)
    {
        AwtoWdtBite(ucSp, ucBank, ucCause);
    }
}

// Test cmd 0x4C + n (#131): 0 spin (STALL), 1 spin in a feeding wait (PASS), 2 spin with EA off (hardware WDT only, no capture)
void AwtoWdtHang(BYTE ucHow)
{
    g_stAwtoWdt.ucBoot |= AWTO_WDT_B_TEST;
    if(ucHow == 2)
    {
        EA = 0;
    }
    while(_TRUE)
    {
        if(ucHow == 1)
        {
            ScalerTimerDelayXms(10);
        }
    }
}

// Main loop while AWTO_WDT_B_NEW: open the console (watchdog panel) once picture / no-signal state has settled AWTO_WDT_SHOW_MS.
// Not through the info pop-up (ucDbgPopup): the pop-up repositions the OSD after the console opened (sim render, #131).
static __xdata WORD s_usAwtoWdtSettled;         // 0 = not settled; else g_usTimerCounter | 1 when it settled

void AwtoWdtShow(void)
{
    BYTE ucMode = GET_MODE_STATE();
    WORD usNow;

    do
    {
        usNow = g_usTimerCounter;
    }
    while(usNow != g_usTimerCounter);
    if((g_stAwtoDiag.ucStage < 8) || (SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) ||
       ((ucMode != _MODE_STATUS_ACTIVE) && (ucMode != _MODE_STATUS_NOSIGNAL) && (ucMode != _MODE_STATUS_NOSUPPORT)))
    {
        s_usAwtoWdtSettled = 0;
        return;
    }
    if(s_usAwtoWdtSettled == 0)
    {
        s_usAwtoWdtSettled = usNow | 1;
        return;
    }
    if((WORD)(usNow - s_usAwtoWdtSettled) >= AWTO_WDT_SHOW_MS)
    {
        AwtoDiagConsole(1);                     // draws the watchdog panel, which clears AWTO_WDT_B_NEW
    }
}
#endif
